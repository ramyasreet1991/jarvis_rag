"""
Jarvis RAG — Batch Processor
Daily orchestration: Fetch sources → Vet → Extract → Chunk → Embed → Generate content.
Optimized for RunPod RTX 4090 batch runs.
"""
import json
import time
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

from config import CONFIG
from source_vetter import SourceVetter, Source
from content_extractor import ContentExtractor, ExtractedContent
from rag_engine import RAGEngine
from content_generator import ContentGenerator, GeneratedContent


@dataclass
class BatchReport:
    """Daily batch processing report."""
    date: str
    sources_processed: int
    sources_failed: int
    articles_extracted: int
    chunks_created: int
    content_generated: Dict[str, int]
    avg_latency_ms: float
    errors: List[str]

    def to_dict(self) -> Dict:
        return {
            "date": self.date,
            "sources_processed": self.sources_processed,
            "sources_failed": self.sources_failed,
            "articles_extracted": self.articles_extracted,
            "chunks_created": self.chunks_created,
            "content_generated": self.content_generated,
            "avg_latency_ms": self.avg_latency_ms,
            "errors": self.errors,
        }


class BatchProcessor:
    """End-to-end daily batch pipeline."""

    def __init__(self):
        self.vetter = SourceVetter(threshold=CONFIG.CREDIBILITY_THRESHOLD)
        self.extractor = ContentExtractor()
        self.rag_engine = RAGEngine()
        self.generator = ContentGenerator()

        self.checkpoint_file = "/workspace/checkpoints/batch_state.json"
        self.output_dir = "/workspace/output"
        self.logs_dir = "/workspace/logs"

        Path(self.checkpoint_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.logs_dir).mkdir(parents=True, exist_ok=True)

        self.running = True
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Graceful shutdown on interrupt."""
        print("
⚠️ Interrupt received. Saving checkpoint...")
        self.running = False

    def _load_checkpoint(self) -> Dict:
        """Load last checkpoint."""
        if Path(self.checkpoint_file).exists():
            with open(self.checkpoint_file, "r") as f:
                return json.load(f)
        return {"last_source_idx": 0, "completed_sources": []}

    def _save_checkpoint(self, state: Dict):
        """Save checkpoint for resume."""
        with open(self.checkpoint_file, "w") as f:
            json.dump(state, f, indent=2)

    def _log(self, message: str):
        """Log with timestamp."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{ts}] {message}"
        print(log_line)

        # Append to log file
        log_file = Path(self.logs_dir) / f"batch_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, "a") as f:
            f.write(log_line + "
")

    def run_daily_pipeline(self, sources: Optional[List[Source]] = None,
                          max_articles_per_source: int = 10,
                          generate_content: bool = True) -> BatchReport:
        """Run the full daily pipeline."""
        start_time = time.time()
        report = BatchReport(
            date=datetime.now().strftime("%Y-%m-%d"),
            sources_processed=0,
            sources_failed=0,
            articles_extracted=0,
            chunks_created=0,
            content_generated={"youtube_shorts": 0, "blog_post": 0, 
                              "twitter_thread": 0, "newsletter": 0},
            avg_latency_ms=0,
            errors=[],
        )

        # Load sources if not provided
        if not sources:
            sources = self.vetter.load_default_sources()

        # Load checkpoint
        checkpoint = self._load_checkpoint()
        start_idx = checkpoint.get("last_source_idx", 0)
        completed = set(checkpoint.get("completed_sources", []))

        self._log(f"🚀 Starting daily batch. {len(sources)} sources total.")
        self._log(f"   Resuming from source {start_idx}")

        all_contents = []

        # Phase 1: Extract from all sources
        for i, source in enumerate(sources[start_idx:], start=start_idx):
            if not self.running:
                self._save_checkpoint({"last_source_idx": i, "completed_sources": list(completed)})
                self._log("⏸️ Batch paused. Checkpoint saved.")
                break

            if source.name in completed:
                self._log(f"⏭️ Skipping {source.name} (already processed)")
                continue

            self._log(f"🔍 [{i+1}/{len(sources)}] Processing {source.name}...")

            try:
                # Vet
                ok, reason = self.vetter.vet_source(source)
                if not ok:
                    self._log(f"   ❌ Blocked: {reason}")
                    report.sources_failed += 1
                    continue

                # Extract
                items = self.extractor.extract_from_source(source, max_articles_per_source)

                if items:
                    all_contents.extend([item.to_dict() for item in items])
                    report.articles_extracted += len(items)
                    self._log(f"   ✅ Extracted {len(items)} articles")
                else:
                    self._log(f"   ⚠️ No articles found")

                report.sources_processed += 1
                completed.add(source.name)

                # Checkpoint every N sources
                if (i + 1) % CONFIG.CHECKPOINT_INTERVAL == 0:
                    self._save_checkpoint({"last_source_idx": i + 1, 
                                          "completed_sources": list(completed)})

            except Exception as e:
                error_msg = f"{source.name}: {str(e)}"
                report.errors.append(error_msg)
                report.sources_failed += 1
                self._log(f"   ❌ Error: {error_msg}")

        if not self.running:
            return report

        # Phase 2: Ingest into RAG
        if all_contents:
            self._log(f"
📥 Ingesting {len(all_contents)} articles into RAG...")
            self.rag_engine.ingest(all_contents)
            stats = self.rag_engine.get_stats()
            report.chunks_created = stats["total_chunks"]
            self._log(f"   ✅ KB now has {stats['total_chunks']} chunks from {stats['unique_sources']} sources")

        # Phase 3: Generate content
        if generate_content and all_contents:
            self._log("
🎬 Generating content...")
            report = self._generate_daily_content(report)

        # Finalize
        elapsed = (time.time() - start_time) * 1000
        report.avg_latency_ms = round(elapsed / max(report.sources_processed, 1), 2)

        self._log(f"
{'='*60}")
        self._log(f"📊 BATCH REPORT — {report.date}")
        self._log(f"   Sources processed: {report.sources_processed}")
        self._log(f"   Sources failed: {report.sources_failed}")
        self._log(f"   Articles extracted: {report.articles_extracted}")
        self._log(f"   Chunks in KB: {report.chunks_created}")
        self._log(f"   Content generated: {report.content_generated}")
        self._log(f"   Avg latency: {report.avg_latency_ms}ms")
        self._log(f"   Errors: {len(report.errors)}")
        self._log(f"   Total time: {elapsed/1000:.1f}s")

        # Save report
        report_path = Path(self.logs_dir) / f"report_{report.date}.json"
        with open(report_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)

        # Reset checkpoint for next run
        self._save_checkpoint({"last_source_idx": 0, "completed_sources": []})

        return report

    def _generate_daily_content(self, report: BatchReport) -> BatchReport:
        """Generate daily content targets."""

        # YouTube Shorts (3/day)
        topics = ["Kubernetes trends", "AI breakthroughs", "DevOps tips"]
        for topic in topics[:CONFIG.YOUTUBE_SHORTS_DAILY]:
            try:
                docs = self.rag_engine.query(topic, top_k=5, min_credibility=0.75)
                if docs:
                    content = self.generator.generate_youtube_shorts(topic, docs)
                    self.generator.save_content(content, self.output_dir)
                    report.content_generated["youtube_shorts"] += 1
                    self._log(f"   🎬 Shorts: {content.title}")
            except Exception as e:
                report.errors.append(f"Shorts generation: {e}")

        # Blog post (1/week — only on Mondays)
        if datetime.now().weekday() == 0:  # Monday
            try:
                docs = self.rag_engine.query("weekly tech roundup", top_k=8, min_credibility=0.70)
                if docs:
                    content = self.generator.generate_blog_post("This Week in Tech", docs)
                    self.generator.save_content(content, self.output_dir)
                    report.content_generated["blog_post"] += 1
                    self._log(f"   📝 Blog: {content.title}")
            except Exception as e:
                report.errors.append(f"Blog generation: {e}")

        # Twitter threads (2/week)
        if datetime.now().weekday() in [1, 4]:  # Tue, Fri
            try:
                docs = self.rag_engine.query("tech controversy", top_k=5, min_credibility=0.70)
                if docs:
                    content = self.generator.generate_twitter_thread("Hot takes", docs)
                    self.generator.save_content(content, self.output_dir)
                    report.content_generated["twitter_thread"] += 1
                    self._log(f"   🐦 Thread: {content.title}")
            except Exception as e:
                report.errors.append(f"Twitter generation: {e}")

        # Newsletter (1/week — Sundays)
        if datetime.now().weekday() == 6:  # Sunday
            try:
                docs = self.rag_engine.query("tech news weekly", top_k=10, min_credibility=0.65)
                if docs:
                    content = self.generator.generate_newsletter(["AI", "Cloud", "Security"], docs)
                    self.generator.save_content(content, self.output_dir)
                    report.content_generated["newsletter"] += 1
                    self._log(f"   📧 Newsletter: {content.title}")
            except Exception as e:
                report.errors.append(f"Newsletter generation: {e}")

        return report

    def run_batch_query(self, queries: List[str]) -> Dict[str, List[Dict]]:
        """Run multiple queries and return results."""
        results = {}
        for query in queries:
            docs = self.rag_engine.query(query, top_k=5)
            results[query] = [{
                "content": d.page_content[:200],
                "source": d.metadata.get("source_name"),
                "tier": d.metadata.get("source_tier"),
                "credibility": d.metadata.get("credibility_score"),
            } for d in docs]
        return results


# ── CLI entry point ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Jarvis RAG Batch Processor")
    parser.add_argument("--mode", choices=["daily", "query", "stats"], default="daily")
    parser.add_argument("--queries", nargs="+", help="Queries for query mode")
    parser.add_argument("--no-generate", action="store_true", help="Skip content generation")

    args = parser.parse_args()

    processor = BatchProcessor()

    if args.mode == "daily":
        report = processor.run_daily_pipeline(generate_content=not args.no_generate)
        print(f"
✅ Batch complete. Report saved.")

    elif args.mode == "query":
        if not args.queries:
            print("Usage: python batch_processor.py --mode query --queries 'topic1' 'topic2'")
            sys.exit(1)
        results = processor.run_batch_query(args.queries)
        print(json.dumps(results, indent=2))

    elif args.mode == "stats":
        stats = processor.rag_engine.get_stats()
        print(json.dumps(stats, indent=2))
