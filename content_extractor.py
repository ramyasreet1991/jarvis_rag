"""
Jarvis RAG — Content Extractor
Pulls content from YouTube, Podcasts, Blogs, News via RSS/API/Scraping.
Optimized for RunPod RTX 4090 batch processing.
"""
import re
import json
import hashlib
import subprocess
import feedparser
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from bs4 import BeautifulSoup
import trafilatura
from youtube_transcript_api import YouTubeTranscriptApi
import podcastparser
import urllib.request

from source_vetter import Source, TrustTier


@dataclass
class ExtractedContent:
    """Unified content format from any source."""
    id: str
    title: str
    url: str
    content: str
    summary: str
    published: str
    source_name: str
    source_tier: str
    source_type: str
    credibility_score: float
    categories: List[str]
    word_count: int
    extracted_at: str

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "summary": self.summary,
            "published": self.published,
            "source_name": self.source_name,
            "source_tier": self.source_tier,
            "source_type": self.source_type,
            "credibility_score": self.credibility_score,
            "categories": self.categories,
            "word_count": self.word_count,
            "extracted_at": self.extracted_at,
        }


class ContentExtractor:
    """Multi-source content extraction with unified output."""

    def __init__(self, output_dir: str = "/workspace/extracted"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.seen_hashes = set()

    def _compute_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def _is_duplicate(self, text: str) -> bool:
        h = self._compute_hash(text)
        if h in self.seen_hashes:
            return True
        self.seen_hashes.add(h)
        return False

    def _clean_text(self, text: str) -> str:
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = re.sub(r'[^\x00-\x7F]+', ' ', text)
        return text.strip()

    # ── RSS/Blog Extraction ──────────────────────────────────────────────────

    def extract_rss(self, source: Source, max_entries: int = 20) -> List[ExtractedContent]:
        """Extract articles from RSS feed."""
        if not source.feed_url:
            return []

        try:
            feed = feedparser.parse(source.feed_url)
            results = []

            for entry in feed.entries[:max_entries]:
                content = self._extract_entry_content(entry)
                if self._is_duplicate(content):
                    continue

                results.append(ExtractedContent(
                    id=self._compute_hash(content),
                    title=entry.get("title", "Untitled"),
                    url=entry.get("link", source.url),
                    content=content,
                    summary=entry.get("summary", content[:300]),
                    published=entry.get("published", datetime.now().isoformat()),
                    source_name=source.name,
                    source_tier=source.trust_tier.value,
                    source_type=source.source_type,
                    credibility_score=source.credibility_score,
                    categories=source.categories,
                    word_count=len(content.split()),
                    extracted_at=datetime.now().isoformat(),
                ))

            return results

        except Exception as e:
            print(f"❌ RSS extraction failed for {source.name}: {e}")
            return []

    def _extract_entry_content(self, entry) -> str:
        """Extract full content from RSS entry."""
        # Try content first
        if hasattr(entry, "content") and entry.content:
            return self._clean_text(entry.content[0].value)

        # Try summary
        if hasattr(entry, "summary"):
            return self._clean_text(entry.summary)

        # Fallback: fetch URL and extract
        if hasattr(entry, "link"):
            return self._extract_webpage(entry.link)

        return ""

    def _extract_webpage(self, url: str) -> str:
        """Extract clean text from webpage using trafilatura."""
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded, include_comments=False, 
                                            include_tables=True)
                return self._clean_text(text or "")
        except Exception as e:
            print(f"⚠️ Webpage extraction failed for {url}: {e}")
        return ""

    # ── YouTube Extraction ────────────────────────────────────────────────────

    def extract_youtube(self, source: Source, max_videos: int = 10) -> List[ExtractedContent]:
        """Extract transcripts from YouTube channel RSS."""
        if not source.feed_url:
            return []

        try:
            feed = feedparser.parse(source.feed_url)
            results = []

            for entry in feed.entries[:max_videos]:
                video_url = entry.link
                video_id = self._extract_video_id(video_url)

                if not video_id:
                    continue

                transcript = self._get_transcript(video_id)
                if not transcript or self._is_duplicate(transcript):
                    continue

                results.append(ExtractedContent(
                    id=self._compute_hash(transcript),
                    title=entry.get("title", "Untitled"),
                    url=video_url,
                    content=transcript,
                    summary=transcript[:300],
                    published=entry.get("published", datetime.now().isoformat()),
                    source_name=source.name,
                    source_tier=source.trust_tier.value,
                    source_type="youtube",
                    credibility_score=source.credibility_score,
                    categories=source.categories,
                    word_count=len(transcript.split()),
                    extracted_at=datetime.now().isoformat(),
                ))

            return results

        except Exception as e:
            print(f"❌ YouTube extraction failed for {source.name}: {e}")
            return []

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL."""
        patterns = [
            r'v=([a-zA-Z0-9_-]{11})',
            r'youtu\.be/([a-zA-Z0-9_-]{11})',
            r'/embed/([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _get_transcript(self, video_id: str) -> str:
        """Get transcript using YouTube Transcript API."""
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            text = " ".join([item["text"] for item in transcript_list])
            return self._clean_text(text)
        except Exception:
            return ""

    # ── Podcast Extraction ─────────────────────────────────────────────────

    def extract_podcast(self, source: Source, max_episodes: int = 5) -> List[ExtractedContent]:
        """Extract podcast episodes via RSS + Whisper transcription."""
        if not source.feed_url:
            return []

        try:
            parsed = podcastparser.parse(source.feed_url, 
                                          urllib.request.urlopen(source.feed_url))
            episodes = parsed.get("episodes", [])[:max_episodes]
            results = []

            for ep in episodes:
                audio_url = ep.get("enclosures", [{}])[0].get("url", "")
                if not audio_url:
                    continue

                transcript = self._transcribe_audio(audio_url)
                if not transcript or self._is_duplicate(transcript):
                    continue

                results.append(ExtractedContent(
                    id=self._compute_hash(transcript),
                    title=ep.get("title", "Untitled"),
                    url=audio_url,
                    content=transcript,
                    summary=ep.get("description", transcript[:300]),
                    published=ep.get("published", datetime.now().isoformat()),
                    source_name=source.name,
                    source_tier=source.trust_tier.value,
                    source_type="podcast",
                    credibility_score=source.credibility_score,
                    categories=source.categories,
                    word_count=len(transcript.split()),
                    extracted_at=datetime.now().isoformat(),
                ))

            return results

        except Exception as e:
            print(f"❌ Podcast extraction failed for {source.name}: {e}")
            return []

    def _transcribe_audio(self, audio_url: str) -> str:
        """Download audio and transcribe with Whisper (local, GPU-accelerated)."""
        try:
            # Download audio
            audio_path = f"/tmp/podcast_{hashlib.md5(audio_url.encode()).hexdigest()[:8]}.mp3"
            subprocess.run(["wget", "-q", "-O", audio_path, audio_url], 
                         capture_output=True, timeout=60)

            # Transcribe with Whisper (GPU if available)
            result = subprocess.run(
                ["whisper", audio_path, "--model", "base", "--language", "en", 
                 "--output_format", "txt", "--output_dir", "/tmp/"],
                capture_output=True, text=True, timeout=300
            )

            # Read transcript
            txt_path = audio_path.replace(".mp3", ".txt")
            if Path(txt_path).exists():
                with open(txt_path, "r") as f:
                    return self._clean_text(f.read())

            return ""

        except Exception as e:
            print(f"⚠️ Transcription failed: {e}")
            return ""

    # ── Unified Extraction ──────────────────────────────────────────────────

    def extract_from_source(self, source: Source, 
                           max_items: int = 20) -> List[ExtractedContent]:
        """Route to correct extractor based on source type."""
        if source.source_type == "youtube":
            return self.extract_youtube(source, max_items)
        elif source.source_type == "podcast":
            return self.extract_podcast(source, max_items)
        else:
            return self.extract_rss(source, max_items)

    def batch_extract(self, sources: List[Source], 
                     max_per_source: int = 20) -> Dict[str, List[ExtractedContent]]:
        """Batch extract from multiple sources. Returns {source_name: [content]}."""
        results = {}
        total = 0

        for source in sources:
            if not source.is_eligible():
                print(f"⏭️ Skipping {source.name} (below threshold)")
                continue

            print(f"🔍 Extracting from {source.name}...")
            items = self.extract_from_source(source, max_per_source)
            results[source.name] = items
            total += len(items)
            print(f"   ✅ {len(items)} items extracted")

        print(f"
{'='*50}")
        print(f"Batch complete: {total} items from {len(results)} sources")
        return results

    def save_batch(self, results: Dict[str, List[ExtractedContent]], 
                   filename: str = None):
        """Save extracted content to JSON."""
        if not filename:
            filename = f"extracted_{datetime.now().strftime('%Y%m%d_%H%M')}.json"

        path = self.output_dir / filename
        data = {
            source: [item.to_dict() for item in items]
            for source, items in results.items()
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"💾 Saved to {path}")
        return path


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from source_vetter import SourceVetter

    vetter = SourceVetter()
    sources = vetter.load_default_sources()

    extractor = ContentExtractor()
    results = extractor.batch_extract(sources[:3], max_per_source=3)
    extractor.save_batch(results)
