"""
Jarvis RAG — Content Extractor
Pulls content from YouTube, Podcasts, Blogs, and RSS feeds.
Provides both source-object batch extraction (for the pipeline) and
individual URL-based extraction (for on-demand use).
"""
import re
import json
import hashlib
import subprocess
import feedparser
import requests
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from urllib.parse import urlparse
import urllib.request

from bs4 import BeautifulSoup
import trafilatura
from youtube_transcript_api import YouTubeTranscriptApi

from source_vetter import Source, TrustTier


# ── Shared Whisper helper (faster-whisper, GPU int8) ──────────────────────────

def _whisper_transcribe(audio_path: str, model_size: str = "large-v3") -> str:
    """
    Transcribe an audio file using faster-whisper.
    - GPU (CUDA): large-v3 + int8 — ~8x real-time on RTX 4090, WER ~2.7%
    - CPU fallback: base + float32 — lighter for M2/non-GPU environments
    Shared by YouTubeExtractor and PodcastExtractor.
    """
    try:
        from faster_whisper import WhisperModel
        import torch
        if torch.cuda.is_available():
            device, compute_type = "cuda", "int8"
        else:
            # Fall back to base model on CPU — large-v3 is too slow without GPU
            model_size = "base"
            device, compute_type = "cpu", "float32"

        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments, _ = model.transcribe(audio_path, language="en")
        return " ".join(seg.text.strip() for seg in segments)
    except Exception as e:
        print(f"  faster-whisper transcription error: {e}")
        return ""


# ── Shared Data Model ─────────────────────────────────────────────────────────

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
    # Extended fields
    author: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

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
            "author": self.author,
            "tags": self.tags,
            "metadata": self.metadata,
        }


# ── Specialised Extractor Classes ─────────────────────────────────────────────

class YouTubeExtractor:
    """Extract transcripts and metadata from individual YouTube video URLs."""

    def extract(self, url: str) -> Optional[ExtractedContent]:
        try:
            video_id = self._extract_video_id(url)
            if not video_id:
                return None

            transcript = self._get_transcript(video_id)
            if not transcript:
                print(f"  No transcript available for {video_id} (no captions, Whisper failed)")
                return None

            meta = self._get_video_metadata(video_id)

            return ExtractedContent(
                id=hashlib.sha256(url.encode()).hexdigest()[:16],
                title=meta.get("title", "Unknown"),
                url=url,
                content=transcript,
                summary=meta.get("description", transcript[:300]),
                published=meta.get("published_at", datetime.now().isoformat()),
                source_name=meta.get("channel_title", "YouTube"),
                source_tier="unknown",
                source_type="youtube",
                credibility_score=0.0,
                categories=[],
                word_count=len(transcript.split()),
                extracted_at=datetime.now().isoformat(),
                author=meta.get("channel_title", "Unknown"),
                metadata={
                    "video_id": video_id,
                    "view_count": meta.get("view_count", 0),
                    "like_count": meta.get("like_count", 0),
                    "duration": meta.get("duration", ""),
                    "thumbnail": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                },
            )
        except Exception as e:
            print(f"Error extracting YouTube content from {url}: {e}")
            return None

    def _extract_video_id(self, url: str) -> Optional[str]:
        patterns = [
            r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
            r"youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})",
            r"v=([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _get_transcript(self, video_id: str) -> str:
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            return " ".join(item["text"] for item in transcript_list)
        except Exception:
            print(f"  No captions for {video_id}, falling back to Whisper...")
            return self._transcribe_video(video_id)

    def _transcribe_video(self, video_id: str) -> str:
        """Download audio via yt-dlp and transcribe with faster-whisper (GPU int8)."""
        audio_path = f"/tmp/yt_{video_id}.mp3"
        try:
            dl = subprocess.run(
                [
                    "yt-dlp", "-x", "--audio-format", "mp3",
                    "--audio-quality", "0",
                    "-o", audio_path,
                    f"https://www.youtube.com/watch?v={video_id}",
                ],
                capture_output=True, text=True, timeout=180,
            )
            if dl.returncode != 0 or not Path(audio_path).exists():
                print(f"  yt-dlp failed for {video_id}: {dl.stderr[:200]}")
                return ""

            return _whisper_transcribe(audio_path)
        except Exception as e:
            print(f"  Whisper transcription failed for {video_id}: {e}")
        finally:
            Path(audio_path).unlink(missing_ok=True)
        return ""

    def _get_video_metadata(self, video_id: str) -> Dict:
        try:
            response = requests.get(
                f"https://www.youtube.com/watch?v={video_id}",
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            soup = BeautifulSoup(response.content, "html.parser")

            title_tag = soup.find("meta", {"name": "title"})
            desc_tag = soup.find("meta", {"name": "description"})

            return {
                "title": title_tag["content"] if title_tag else "Unknown",
                "description": desc_tag["content"] if desc_tag else "",
                "channel_title": "Unknown",
                "view_count": 0,
                "like_count": 0,
                "duration": "Unknown",
            }
        except Exception:
            return {"title": "Unknown", "description": ""}


class PodcastExtractor:
    """Extract episodes from podcast RSS feeds with optional Whisper transcription."""

    def extract(self, url: str) -> Optional[ExtractedContent]:
        try:
            feed = feedparser.parse(url)
            if not feed.entries:
                return None

            entry = feed.entries[0]
            content = self._extract_episode_content(entry)
            audio_url = self._find_audio_url(entry)

            if audio_url:
                transcript = self._transcribe_audio(audio_url)
                if transcript:
                    content = transcript

            published = self._parse_rss_date(entry.get("published"))

            return ExtractedContent(
                id=hashlib.sha256((url + entry.get("title", "")).encode()).hexdigest()[:16],
                title=entry.get("title", "Unknown"),
                url=entry.get("link", url),
                content=content,
                summary=entry.get("summary", content[:300]),
                published=published.isoformat() if published else datetime.now().isoformat(),
                source_name=feed.feed.get("title", "Podcast"),
                source_tier="unknown",
                source_type="podcast",
                credibility_score=0.0,
                categories=[],
                word_count=len(content.split()),
                extracted_at=datetime.now().isoformat(),
                author=feed.feed.get("author", "Unknown"),
                metadata={
                    "feed_url": url,
                    "episode_number": entry.get("episode", ""),
                    "duration": entry.get("duration", ""),
                    "audio_url": audio_url,
                },
            )
        except Exception as e:
            print(f"Error extracting podcast from {url}: {e}")
            return None

    def _extract_episode_content(self, entry) -> str:
        for key in ("summary", "description"):
            val = entry.get(key, "")
            if val:
                return val
        content_list = entry.get("content", [])
        if content_list:
            return content_list[0].get("value", "")
        return ""

    def _find_audio_url(self, entry) -> Optional[str]:
        for link in entry.get("links", []):
            if link.get("type", "").startswith("audio/"):
                return link.get("href")
        return None

    def _transcribe_audio(self, audio_url: str) -> str:
        """Download and transcribe podcast audio via faster-whisper (GPU int8)."""
        audio_path = f"/tmp/podcast_{hashlib.md5(audio_url.encode()).hexdigest()[:8]}.mp3"
        try:
            subprocess.run(
                ["wget", "-q", "-O", audio_path, audio_url],
                capture_output=True, timeout=60,
            )
            if not Path(audio_path).exists():
                return ""
            return _whisper_transcribe(audio_path)
        except Exception as e:
            print(f"Transcription failed: {e}")
        finally:
            Path(audio_path).unlink(missing_ok=True)
        return ""

    def _parse_rss_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            return None


class BlogExtractor:
    """Extract articles from individual blog/article URLs."""

    def extract(self, url: str) -> Optional[ExtractedContent]:
        try:
            response = requests.get(url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            soup = BeautifulSoup(response.content, "html.parser")

            title = self._extract_title(soup)
            author = self._extract_author(soup)
            published_date = self._extract_publish_date(soup)
            content = self._extract_main_content(soup)
            tags = self._extract_tags(soup)
            canonical = self._extract_canonical_url(soup)

            return ExtractedContent(
                id=hashlib.sha256(url.encode()).hexdigest()[:16],
                title=title,
                url=url,
                content=content,
                summary=content[:300],
                published=published_date.isoformat() if published_date else datetime.now().isoformat(),
                source_name=urlparse(url).netloc,
                source_tier="unknown",
                source_type="blog",
                credibility_score=0.0,
                categories=[],
                word_count=len(content.split()),
                extracted_at=datetime.now().isoformat(),
                author=author,
                tags=tags,
                metadata={
                    "domain": urlparse(url).netloc,
                    "canonical_url": canonical,
                },
            )
        except Exception as e:
            print(f"Error extracting blog from {url}: {e}")
            return None

    def _extract_title(self, soup: BeautifulSoup) -> str:
        for candidate in [
            soup.find("h1"),
            soup.find("meta", {"property": "og:title"}),
            soup.find("meta", {"name": "title"}),
            soup.find("title"),
        ]:
            if candidate:
                if hasattr(candidate, "string") and candidate.string:
                    return candidate.string.strip()
                if candidate.get("content"):
                    return candidate["content"].strip()
        return "Unknown"

    def _extract_author(self, soup: BeautifulSoup) -> str:
        for candidate in [
            soup.find("meta", {"name": "author"}),
            soup.find("meta", {"property": "article:author"}),
            soup.find(class_=re.compile(r"author", re.I)),
        ]:
            if candidate:
                if candidate.get("content"):
                    return candidate["content"].strip()
                if candidate.string:
                    return candidate.string.strip()
        return "Unknown"

    def _extract_publish_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        for candidate in [
            soup.find("meta", {"property": "article:published_time"}),
            soup.find("meta", {"name": "publish_date"}),
            soup.find("time"),
        ]:
            if candidate:
                date_str = candidate.get("content") or candidate.get("datetime")
                if date_str:
                    try:
                        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    except ValueError:
                        pass
        return None

    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "nav", "footer", "button"]):
            tag.decompose()

        for selector in [
            soup.find("article"),
            soup.find(class_=re.compile(r"post-content|article-content|entry-content", re.I)),
            soup.find(id=re.compile(r"content|post|article", re.I)),
            soup.find("main"),
        ]:
            if selector:
                return selector.get_text(separator="\n", strip=True)

        body = soup.body or soup
        return body.get_text(separator="\n", strip=True) if body else ""

    def _extract_tags(self, soup: BeautifulSoup) -> List[str]:
        tags = []
        for link in soup.find_all("a", class_=re.compile(r"tag|category", re.I)):
            text = link.get_text(strip=True)
            if text:
                tags.append(text)
        keywords_meta = soup.find("meta", {"name": "keywords"})
        if keywords_meta:
            tags.extend(k.strip() for k in keywords_meta.get("content", "").split(",") if k.strip())
        return list(set(tags))[:10]

    def _extract_canonical_url(self, soup: BeautifulSoup) -> Optional[str]:
        canonical = soup.find("link", {"rel": "canonical"})
        return canonical.get("href") if canonical else None


class RSSFeedExtractor:
    """Extract all entries from a generic RSS/Atom feed URL."""

    def __init__(self):
        self._blog = BlogExtractor()

    def extract_feed(self, feed_url: str, max_entries: int = 20) -> List[ExtractedContent]:
        try:
            feed = feedparser.parse(feed_url)
            results = []

            for entry in feed.entries[:max_entries]:
                url = entry.get("link")
                if not url:
                    continue

                extracted = self._blog.extract(url)

                if not extracted:
                    published = self._parse_rss_date(entry.get("published"))
                    content = entry.get("summary") or entry.get("description") or ""
                    extracted = ExtractedContent(
                        id=hashlib.sha256(url.encode()).hexdigest()[:16],
                        title=entry.get("title", "Unknown"),
                        url=url,
                        content=content,
                        summary=content[:300],
                        published=published.isoformat() if published else datetime.now().isoformat(),
                        source_name=feed.feed.get("title", "RSS Feed"),
                        source_tier="unknown",
                        source_type="rss",
                        credibility_score=0.0,
                        categories=[],
                        word_count=len(content.split()),
                        extracted_at=datetime.now().isoformat(),
                        author=feed.feed.get("author", "Unknown"),
                        metadata={"feed_url": feed_url},
                    )

                results.append(extracted)

            return results
        except Exception as e:
            print(f"Error extracting RSS feed from {feed_url}: {e}")
            return []

    def _parse_rss_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            return None


class MultiSourceExtractor:
    """Auto-detect source type from a URL and delegate to the right extractor."""

    def __init__(self):
        self.youtube = YouTubeExtractor()
        self.podcast = PodcastExtractor()
        self.blog = BlogExtractor()
        self.rss = RSSFeedExtractor()

    def extract(self, url: str) -> Optional[ExtractedContent]:
        if "youtube.com" in url or "youtu.be" in url:
            return self.youtube.extract(url)
        if "podcast" in url.lower() or url.endswith(".xml"):
            result = self.podcast.extract(url)
            if result:
                return result
        return self.blog.extract(url)


# ── Pipeline Extractor (Source-object based) ──────────────────────────────────

class ContentExtractor:
    """
    Batch extractor that operates on Source objects from the vetting pipeline.
    Uses specialised extractors internally; saves results to disk.
    """

    def __init__(self, output_dir: str = "/workspace/extracted"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.seen_hashes: set = set()

        self._youtube = YouTubeExtractor()
        self._podcast = PodcastExtractor()
        self._blog = BlogExtractor()
        self._rss = RSSFeedExtractor()

    # ── Deduplication ────────────────────────────────────────────────────────

    def _compute_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def _is_duplicate(self, text: str) -> bool:
        h = self._compute_hash(text)
        if h in self.seen_hashes:
            return True
        self.seen_hashes.add(h)
        return False

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"[^\x00-\x7F]+", " ", text)
        return text.strip()

    # ── Per-source-type Extraction ───────────────────────────────────────────

    def extract_rss(self, source: Source, max_entries: int = 20) -> List[ExtractedContent]:
        """Extract articles from a Source's RSS feed URL."""
        if not source.feed_url:
            return []
        try:
            feed = feedparser.parse(source.feed_url)
            results = []

            for entry in feed.entries[:max_entries]:
                content = self._extract_entry_content(entry)
                if not content or self._is_duplicate(content):
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
                    author=entry.get("author", ""),
                    tags=source.categories,
                ))

            return results
        except Exception as e:
            print(f"RSS extraction failed for {source.name}: {e}")
            return []

    def _extract_entry_content(self, entry) -> str:
        if hasattr(entry, "content") and entry.content:
            return self._clean_text(entry.content[0].value)
        if hasattr(entry, "summary") and entry.summary:
            return self._clean_text(entry.summary)
        if hasattr(entry, "link"):
            return self._extract_webpage(entry.link)
        return ""

    def _extract_webpage(self, url: str) -> str:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
                return self._clean_text(text or "")
        except Exception as e:
            print(f"Webpage extraction failed for {url}: {e}")
        return ""

    def extract_youtube(self, source: Source, max_videos: int = 10) -> List[ExtractedContent]:
        """Extract transcripts from a YouTube channel's RSS feed."""
        if not source.feed_url:
            return []
        try:
            feed = feedparser.parse(source.feed_url)
            results = []

            for entry in feed.entries[:max_videos]:
                video_url = entry.link
                result = self._youtube.extract(video_url)
                if not result or self._is_duplicate(result.content):
                    continue

                # Enrich with source metadata
                result.source_name = source.name
                result.source_tier = source.trust_tier.value
                result.credibility_score = source.credibility_score
                result.categories = source.categories
                result.tags = source.categories
                result.published = entry.get("published", result.published)
                results.append(result)

            return results
        except Exception as e:
            print(f"YouTube extraction failed for {source.name}: {e}")
            return []

    def extract_podcast(self, source: Source, max_episodes: int = 5) -> List[ExtractedContent]:
        """Extract podcast episodes via RSS and optional Whisper transcription."""
        if not source.feed_url:
            return []
        try:
            result = self._podcast.extract(source.feed_url)
            if not result or self._is_duplicate(result.content):
                return []

            result.source_name = source.name
            result.source_tier = source.trust_tier.value
            result.credibility_score = source.credibility_score
            result.categories = source.categories
            result.tags = source.categories
            return [result]
        except Exception as e:
            print(f"Podcast extraction failed for {source.name}: {e}")
            return []

    # ── Unified Routing ──────────────────────────────────────────────────────

    def extract_from_source(self, source: Source, max_items: int = 20) -> List[ExtractedContent]:
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
                print(f"Skipping {source.name} (below threshold)")
                continue

            print(f"Extracting from {source.name}...")
            items = self.extract_from_source(source, max_per_source)
            results[source.name] = items
            total += len(items)
            print(f"  {len(items)} items extracted")

        print(f"\n{'='*50}")
        print(f"Batch complete: {total} items from {len(results)} sources")
        return results

    def save_batch(self, results: Dict[str, List[ExtractedContent]],
                   filename: str = None) -> Path:
        """Save extracted content to JSON."""
        if not filename:
            filename = f"extracted_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        path = self.output_dir / filename
        data = {source: [item.to_dict() for item in items]
                for source, items in results.items()}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved to {path}")
        return path


# ── Quick test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from source_vetter import SourceVetter

    vetter = SourceVetter()
    sources = vetter.load_default_sources()

    extractor = ContentExtractor()
    results = extractor.batch_extract(sources[:3], max_per_source=3)
    extractor.save_batch(results)
