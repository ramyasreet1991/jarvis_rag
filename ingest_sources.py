#!/usr/bin/env python3
"""
Jarvis RAG — Automated Source Ingestion
Reads sources_config.json and ingests all active sources into the RAG KB.

Usage:
    python ingest_sources.py                          # all active sources
    python ingest_sources.py --tier 1                 # Tier 1 only
    python ingest_sources.py --type rss               # RSS feeds only
    python ingest_sources.py --type youtube           # YouTube only
    python ingest_sources.py --ids hn-001,arxiv-001   # specific source IDs
    python ingest_sources.py --days 3                 # content from last N days
    python ingest_sources.py --dry-run                # list without ingesting
    python ingest_sources.py --reset-seen             # clear dedup cache

Supported extraction methods:
    rss            → feedparser + trafilatura
    api (arXiv)    → arXiv XML API
    youtube-*      → yt-dlp + Transcript API / Whisper fallback
    podcast_rss    → podcast RSS + yt-dlp audio + Whisper
    dev.to         → Dev.to articles API with reactions filter
    web-scraping   → trafilatura direct URL
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.resolve()
CONFIG_PATH = BASE_DIR / "sources_config.json"
SEEN_PATH  = Path(os.environ.get("SEEN_URLS_PATH", "/workspace/data/ingested_urls.json"))
LOG_PATH   = Path(os.environ.get("LOGS_DIR", "/workspace/logs")) / "ingest_sources.log"

API_HOST   = os.environ.get("INGEST_API_HOST", "http://localhost:8000")
API_KEY    = os.environ.get("APP_API_KEY", "jarvis-runpod-key")

# ── Dedup Cache ───────────────────────────────────────────────────────────────

def load_seen() -> set:
    if SEEN_PATH.exists():
        try:
            return set(json.loads(SEEN_PATH.read_text()))
        except Exception:
            return set()
    return set()


def save_seen(seen: set):
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(json.dumps(sorted(seen), indent=2))


def already_seen(url: str, seen: set) -> bool:
    return url in seen


def mark_seen(url: str, seen: set):
    seen.add(url)


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Date utilities ────────────────────────────────────────────────────────────

def is_recent(pub_str: str, days: int) -> bool:
    """Return True if pub_str is within the last `days` days."""
    if not pub_str or days <= 0:
        return True
    try:
        # Handle multiple formats
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z",
                    "%a, %d %b %Y %H:%M:%S %Z"):
            try:
                dt = datetime.strptime(pub_str[:25], fmt[:len(pub_str[:25])])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                return dt >= cutoff
            except ValueError:
                continue
        return True  # If can't parse, allow it through
    except Exception:
        return True


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── API Ingestion ─────────────────────────────────────────────────────────────

def post_to_api(items: List[dict], source_type: str = "rss") -> int:
    """POST items to /ingest. Returns count of successfully queued items."""
    if not items:
        return 0
    try:
        resp = requests.post(
            f"{API_HOST}/ingest",
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json={"source_type": source_type, "content_list": items},
            timeout=30,
        )
        if resp.status_code == 200:
            return len(items)
        log(f"Ingest HTTP {resp.status_code}: {resp.text[:200]}", "ERROR")
        return 0
    except Exception as e:
        log(f"Ingest request error: {e}", "ERROR")
        return 0


# ── RSS Ingester ──────────────────────────────────────────────────────────────

def ingest_rss(source: dict, days: int, seen: set, dry_run: bool) -> int:
    """Fetch RSS/Atom feed and ingest articles via trafilatura."""
    import feedparser
    try:
        import trafilatura
    except ImportError:
        trafilatura = None

    feed_url = source.get("feed_url") or source.get("url")
    log(f"  RSS: {feed_url}")

    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        log(f"  feedparser error: {e}", "WARN")
        return 0

    items = []
    for entry in feed.entries[:30]:
        url = entry.get("link", "")
        if not url or already_seen(url, seen):
            continue

        pub_str = ""
        if hasattr(entry, "published"):
            pub_str = entry.published
        elif hasattr(entry, "updated"):
            pub_str = entry.updated

        if not is_recent(pub_str, days):
            continue

        title = entry.get("title", "Untitled")

        # Get full content: try trafilatura first, fall back to feed summary
        content = ""
        if trafilatura:
            try:
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    content = trafilatura.extract(downloaded) or ""
            except Exception:
                pass

        if not content:
            content = (
                entry.get("summary", "") or
                entry.get("content", [{}])[0].get("value", "") if entry.get("content") else ""
            )

        # Strip HTML tags from feed summary
        content = re.sub(r"<[^>]+>", " ", content).strip()

        if len(content.split()) < 50:
            continue

        if dry_run:
            log(f"    [dry-run] {title[:70]}")
            mark_seen(url, seen)
            continue

        items.append({
            "title": title,
            "content": content,
            "url": url,
            "source_name": source["name"],
            "source_tier": _tier_label(source),
            "source_type": source.get("type", "blog"),
            "credibility_score": source.get("credibility_score", 0.80),
            "published": pub_str or now_iso(),
            "categories": source.get("content_focus", []),
        })
        mark_seen(url, seen)

        if len(items) >= 10:   # batch every 10
            post_to_api(items, source_type=source.get("type", "rss"))
            items = []
        time.sleep(0.3)

    if items:
        post_to_api(items, source_type=source.get("type", "rss"))

    return len(feed.entries)


# ── arXiv Ingester ────────────────────────────────────────────────────────────

def ingest_arxiv(source: dict, days: int, seen: set, dry_run: bool) -> int:
    """Fetch recent CS papers from arXiv API."""
    params = source.get("api_query_params", {})
    query  = params.get("search_query", "cat:cs.AI OR cat:cs.LG")
    max_r  = params.get("max_results", 30)
    api_url = source.get("api_endpoint", "https://arxiv.org/api/query")

    log(f"  arXiv: {query} (max {max_r})")

    try:
        resp = requests.get(
            api_url,
            params={"search_query": query, "start": 0,
                    "max_results": max_r, "sortBy": "submittedDate",
                    "sortOrder": "descending"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        log(f"  arXiv API error: {e}", "WARN")
        return 0

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        log(f"  arXiv XML parse error: {e}", "WARN")
        return 0

    items = []
    for entry in root.findall("atom:entry", ns):
        url = (entry.findtext("atom:id", "", ns) or "").strip()
        if not url or already_seen(url, seen):
            continue

        pub_str = entry.findtext("atom:published", "", ns).strip()
        if not is_recent(pub_str, days):
            continue

        title   = entry.findtext("atom:title", "", ns).strip().replace("\n", " ")
        summary = entry.findtext("atom:summary", "", ns).strip().replace("\n", " ")
        authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
        cats    = [c.get("term", "") for c in entry.findall("atom:category", ns)]

        if len(summary.split()) < 30:
            continue

        content = f"Abstract: {summary}\n\nAuthors: {', '.join(authors[:5])}"

        if dry_run:
            log(f"    [dry-run] {title[:70]}")
            mark_seen(url, seen)
            continue

        items.append({
            "title": title,
            "content": content,
            "url": url,
            "source_name": source["name"],
            "source_tier": _tier_label(source),
            "source_type": "research",
            "credibility_score": source.get("credibility_score", 0.95),
            "published": pub_str or now_iso(),
            "categories": [c.replace("cs.", "").lower() for c in cats[:5]],
        })
        mark_seen(url, seen)

    if items:
        post_to_api(items, "research")
    return len(items)


# ── YouTube Ingester ──────────────────────────────────────────────────────────

def _yt_list_recent(handle: str, days: int, max_videos: int) -> List[dict]:
    """List recent uploads via yt-dlp."""
    cutoff_str = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    cmd = [
        "yt-dlp", "--flat-playlist",
        "--playlist-end", str(max_videos * 3),
        "--dateafter", cutoff_str,
        "--print", "%(id)s\t%(title)s\t%(upload_date)s\t%(duration)s",
        "--no-warnings", "--quiet",
        f"https://www.youtube.com/{handle}/videos",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except Exception as e:
        log(f"  yt-dlp list error: {e}", "WARN")
        return []

    videos = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        vid_id, title, upload_date = parts[0], parts[1], parts[2]
        duration = int(float(parts[3])) if len(parts) > 3 and parts[3] not in ("NA", "") else 0
        if duration and (duration < 90 or duration > 5400):
            continue
        try:
            pub_dt  = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
            pub_iso = pub_dt.isoformat()
        except Exception:
            pub_iso = now_iso()
        videos.append({"id": vid_id, "title": title, "published": pub_iso})
        if len(videos) >= max_videos:
            break
    return videos


def _yt_transcript(video_id: str) -> Optional[str]:
    """Get transcript via API (fast) or Whisper (fallback)."""
    # ── Transcript API ────────────────────────────────────────────────────────
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        try:
            tl = api.list(video_id)
            transcript = tl.find_transcript(["en", "en-US", "en-GB"]).fetch()
        except Exception:
            transcript = api.fetch(video_id)
        text = " ".join(
            (seg.text if hasattr(seg, "text") else seg["text"]) for seg in transcript
        ).strip()
        if text and len(text.split()) > 80:
            return text
    except Exception:
        pass

    # ── Whisper fallback ──────────────────────────────────────────────────────
    import tempfile
    audio_path = os.path.join(tempfile.gettempdir(), f"{video_id}.mp3")
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = ["yt-dlp", "--extract-audio", "--audio-format", "mp3",
           "--audio-quality", "5", "-o", audio_path, "--no-playlist", url]
    try:
        subprocess.run(cmd, check=True, timeout=120, capture_output=True)
    except Exception as e:
        log(f"  yt-dlp audio error: {e}", "WARN")
        return None
    if not os.path.exists(audio_path):
        return None
    try:
        from faster_whisper import WhisperModel
        import torch
        if torch.cuda.is_available():
            device, ct, size = "cuda", "int8", "large-v3"
        else:
            device, ct, size = "cpu", "float32", "base"
        model = WhisperModel(size, device=device, compute_type=ct)
        segments, _ = model.transcribe(audio_path, language="en")
        return " ".join(s.text.strip() for s in segments).strip() or None
    except Exception as e:
        log(f"  Whisper error: {e}", "WARN")
        return None
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


def ingest_youtube(source: dict, days: int, seen: set, dry_run: bool,
                   max_per_channel: int = 5) -> int:
    handle = source["url"].replace("https://www.youtube.com/", "")
    if not handle.startswith("@"):
        handle = "@" + handle.lstrip("/")
    log(f"  YouTube: {handle}")

    videos = _yt_list_recent(handle, days, max_per_channel)
    if not videos:
        log(f"  No recent videos (last {days}d)", "WARN")
        return 0

    ingested = 0
    for vid in videos:
        url = f"https://www.youtube.com/watch?v={vid['id']}"
        if already_seen(url, seen):
            continue

        if dry_run:
            log(f"    [dry-run] {vid['title'][:70]}")
            mark_seen(url, seen)
            continue

        transcript = _yt_transcript(vid["id"])
        if not transcript or len(transcript.split()) < 80:
            log(f"  ⚠ No usable transcript: {vid['title'][:50]}", "WARN")
            mark_seen(url, seen)
            continue

        item = {
            "title": vid["title"],
            "content": transcript,
            "url": url,
            "source_name": source["name"],
            "source_tier": _tier_label(source),
            "source_type": "youtube",
            "credibility_score": source.get("credibility_score", 0.90),
            "published": vid["published"],
            "categories": source.get("content_focus", []),
        }
        if post_to_api([item], "youtube") > 0:
            ingested += 1
            log(f"  ✅ {vid['title'][:60]} ({len(transcript.split())} words)")
        mark_seen(url, seen)
        time.sleep(0.5)

    return ingested


# ── Podcast Ingester ──────────────────────────────────────────────────────────

def ingest_podcast(source: dict, days: int, seen: set, dry_run: bool,
                   max_episodes: int = 2) -> int:
    """Fetch latest podcast episodes and transcribe via Whisper."""
    import feedparser
    feed_url = source.get("feed_url") or source.get("url")
    log(f"  Podcast: {feed_url}")

    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        log(f"  feedparser error: {e}", "WARN")
        return 0

    ingested = 0
    for entry in feed.entries[:max_episodes * 3]:
        url = entry.get("link", "") or entry.get("id", "")
        if not url or already_seen(url, seen):
            continue

        pub_str = getattr(entry, "published", "") or ""
        if not is_recent(pub_str, days):
            continue

        title = entry.get("title", "Untitled")
        # Find audio URL from enclosures
        audio_url = None
        for enc in entry.get("enclosures", []):
            if "audio" in enc.get("type", ""):
                audio_url = enc.get("href") or enc.get("url")
                break

        if not audio_url:
            continue

        if dry_run:
            log(f"    [dry-run] {title[:70]}")
            mark_seen(url, seen)
            continue

        # Download + transcribe
        import tempfile
        audio_path = os.path.join(tempfile.gettempdir(), f"podcast_{entry.get('id','ep')[-8:]}.mp3")
        try:
            log(f"  Downloading: {title[:50]}...")
            r = requests.get(audio_url, stream=True, timeout=60)
            with open(audio_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        except Exception as e:
            log(f"  Download error: {e}", "WARN")
            continue

        try:
            from faster_whisper import WhisperModel
            import torch
            if torch.cuda.is_available():
                device, ct, size = "cuda", "int8", "large-v3"
            else:
                device, ct, size = "cpu", "float32", "base"
            model = WhisperModel(size, device=device, compute_type=ct)
            segments, _ = model.transcribe(audio_path, language="en")
            transcript = " ".join(s.text.strip() for s in segments).strip()
        except Exception as e:
            log(f"  Whisper error: {e}", "WARN")
            continue
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)

        if len(transcript.split()) < 100:
            continue

        item = {
            "title": title,
            "content": transcript,
            "url": url,
            "source_name": source["name"],
            "source_tier": _tier_label(source),
            "source_type": "podcast",
            "credibility_score": source.get("credibility_score", 0.85),
            "published": pub_str or now_iso(),
            "categories": source.get("content_focus", []),
        }
        if post_to_api([item], "podcast") > 0:
            ingested += 1
            log(f"  ✅ {title[:60]} ({len(transcript.split())} words)")
        mark_seen(url, seen)

        if ingested >= max_episodes:
            break

    return ingested


# ── Dev.to Ingester ───────────────────────────────────────────────────────────

def ingest_devto(source: dict, days: int, seen: set, dry_run: bool) -> int:
    """Fetch top articles from Dev.to API with reactions filter."""
    min_reactions = source.get("filters", {}).get("minimum_reactions", 50)
    tags = source.get("content_focus", ["kubernetes", "devops", "ai"])
    log(f"  Dev.to: tags={tags}, min_reactions={min_reactions}")

    items = []
    for tag in tags[:4]:   # cap tags to avoid rate limits
        try:
            resp = requests.get(
                "https://dev.to/api/articles",
                params={"tag": tag, "per_page": 20, "top": 7},
                timeout=20,
            )
            resp.raise_for_status()
            articles = resp.json()
        except Exception as e:
            log(f"  Dev.to API error ({tag}): {e}", "WARN")
            continue

        for art in articles:
            url = art.get("url", "")
            if not url or already_seen(url, seen):
                continue
            if art.get("positive_reactions_count", 0) < min_reactions:
                continue
            pub_str = art.get("published_at", "")
            if not is_recent(pub_str, days * 7):  # Dev.to top posts span longer
                continue

            title   = art.get("title", "Untitled")
            content = art.get("body_markdown") or art.get("description", "")
            if not content or len(content.split()) < 50:
                continue

            if dry_run:
                log(f"    [dry-run] {title[:70]} ({art.get('positive_reactions_count')} ❤)")
                mark_seen(url, seen)
                continue

            items.append({
                "title": title,
                "content": content[:8000],
                "url": url,
                "source_name": "Dev.to",
                "source_tier": _tier_label(source),
                "source_type": "blog",
                "credibility_score": source.get("credibility_score", 0.80),
                "published": pub_str or now_iso(),
                "categories": [tag],
            })
            mark_seen(url, seen)

        time.sleep(0.5)

    if items:
        post_to_api(items, "blog")
    return len(items)


# ── Web Scraper Ingester ──────────────────────────────────────────────────────

def ingest_web(source: dict, days: int, seen: set, dry_run: bool) -> int:
    """Scrape a web page or sitemap with trafilatura."""
    try:
        import trafilatura
        from trafilatura.sitemaps import sitemap_search
    except ImportError:
        log("  trafilatura not installed — skipping web scraping", "WARN")
        return 0

    url = source["url"]
    if already_seen(url, seen):
        return 0

    log(f"  Web: {url}")

    # Try sitemap first for blogs
    items = []
    try:
        links = sitemap_search(url)
        recent_links = [l for l in (links or []) if l and not already_seen(l, seen)][:10]
    except Exception:
        recent_links = [url]

    if not recent_links:
        recent_links = [url]

    for link in recent_links[:5]:
        try:
            downloaded = trafilatura.fetch_url(link)
            if not downloaded:
                continue
            content = trafilatura.extract(downloaded, include_comments=False,
                                          include_tables=False, no_fallback=True)
            if not content or len(content.split()) < 80:
                continue

            title = trafilatura.extract_metadata(downloaded).title if trafilatura.extract_metadata(downloaded) else source["name"]

            if dry_run:
                log(f"    [dry-run] {str(title)[:70]}")
                mark_seen(link, seen)
                continue

            items.append({
                "title": str(title or source["name"]),
                "content": content[:8000],
                "url": link,
                "source_name": source["name"],
                "source_tier": _tier_label(source),
                "source_type": source.get("type", "blog"),
                "credibility_score": source.get("credibility_score", 0.85),
                "published": now_iso(),
                "categories": source.get("content_focus", []),
            })
            mark_seen(link, seen)
            time.sleep(1)
        except Exception as e:
            log(f"  scrape error ({link[:60]}): {e}", "WARN")

    if items:
        post_to_api(items, source.get("type", "blog"))
    return len(items)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tier_label(source: dict) -> str:
    cred = source.get("credibility_score", 0.80)
    if cred >= 0.95:
        return "tier_1"
    if cred >= 0.80:
        return "tier_2"
    return "tier_3"


def flatten_sources(config: dict) -> List[dict]:
    """Flatten all sources from sources_config.json into a single list."""
    sources = []
    skip_keys = {"metadata", "ingestion_config", "quick_start_sources",
                 "recommended_by_use_case"}

    def add(item):
        if isinstance(item, dict) and item.get("active", True):
            sources.append(item)
        elif isinstance(item, list):
            for x in item:
                add(x)

    for key, val in config.items():
        if key in skip_keys:
            continue
        if isinstance(val, dict):
            for sub_key, sub_val in val.items():
                add(sub_val)
        else:
            add(val)

    return sources


def route_source(source: dict, days: int, seen: set, dry_run: bool,
                 max_yt: int = 5, max_pod: int = 2) -> int:
    """Dispatch ingestion based on extraction_method."""
    method = source.get("extraction_method", "rss")
    try:
        if method == "rss" or method == "atom":
            return ingest_rss(source, days, seen, dry_run)
        elif method == "api" and "arxiv" in source.get("url", ""):
            return ingest_arxiv(source, days, seen, dry_run)
        elif "youtube" in method:
            return ingest_youtube(source, days, seen, dry_run, max_yt)
        elif method == "podcast_rss":
            return ingest_podcast(source, days, seen, dry_run, max_pod)
        elif method == "dev.to" or "dev.to" in source.get("url", ""):
            return ingest_devto(source, days, seen, dry_run)
        elif method == "web-scraping":
            return ingest_web(source, days, seen, dry_run)
        else:
            log(f"  Unsupported method '{method}' for {source['name']} — skipping", "WARN")
            return 0
    except Exception as e:
        log(f"  Unhandled error in {source['name']}: {e}", "ERROR")
        return 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global API_HOST, API_KEY

    parser = argparse.ArgumentParser(description="Ingest all configured sources into Jarvis RAG KB")
    parser.add_argument("--host", default=API_HOST, help="API base URL")
    parser.add_argument("--api-key", default=API_KEY, help="API key")
    parser.add_argument("--days", type=int, default=3,
                        help="Ingest content published in last N days (default: 3)")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], default=None,
                        help="Restrict to sources of this credibility tier")
    parser.add_argument("--type", default=None,
                        help="Restrict to extraction method type: rss|youtube|podcast_rss|api")
    parser.add_argument("--ids", default=None,
                        help="Comma-separated source IDs from sources_config.json")
    parser.add_argument("--max-yt", type=int, default=5, help="Max YouTube videos per channel")
    parser.add_argument("--max-pod", type=int, default=2, help="Max podcast episodes per feed")
    parser.add_argument("--dry-run", action="store_true", help="List without ingesting")
    parser.add_argument("--reset-seen", action="store_true", help="Clear the dedup cache")
    args = parser.parse_args()

    API_HOST = args.host
    API_KEY  = args.api_key

    # Load config
    if not CONFIG_PATH.exists():
        log(f"sources_config.json not found at {CONFIG_PATH}", "ERROR")
        sys.exit(1)

    config  = json.loads(CONFIG_PATH.read_text())
    sources = flatten_sources(config)

    # Reset dedup cache if requested
    if args.reset_seen:
        if SEEN_PATH.exists():
            SEEN_PATH.unlink()
            log("Dedup cache cleared")
        else:
            log("Dedup cache was already empty")

    seen = load_seen()

    # Apply filters
    if args.ids:
        wanted = set(args.ids.split(","))
        sources = [s for s in sources if s.get("id") in wanted]

    if args.tier is not None:
        min_cred = {1: 0.90, 2: 0.75, 3: 0.0}[args.tier]
        max_cred = {1: 1.01, 2: 0.899, 3: 0.749}[args.tier]
        sources = [s for s in sources
                   if min_cred <= s.get("credibility_score", 0.80) <= max_cred]

    if args.type:
        sources = [s for s in sources if args.type in s.get("extraction_method", "")]

    print("══════════════════════════════════════════════")
    print(f"  Jarvis RAG — Source Ingestion")
    print(f"  Host     : {API_HOST}")
    print(f"  Sources  : {len(sources)}")
    print(f"  Window   : last {args.days} days")
    print(f"  Dry run  : {args.dry_run}")
    print(f"  Seen URLs: {len(seen)}")
    print("══════════════════════════════════════════════")

    if not args.dry_run:
        try:
            health = requests.get(f"{API_HOST}/health", timeout=10).json()
            status = health.get("status", "unknown")
            chunks = health.get("kb_chunks", 0)
            log(f"API: {status} | KB chunks: {chunks}")
        except Exception as e:
            log(f"Cannot reach API: {e}", "ERROR")
            sys.exit(1)

    total_ingested = 0
    start_time = time.time()

    for src in sources:
        log(f"\n▶ [{src.get('id', '?')}] {src['name']}")
        n = route_source(src, args.days, seen, args.dry_run, args.max_yt, args.max_pod)
        total_ingested += n

    # Persist updated seen URLs
    save_seen(seen)

    elapsed = round(time.time() - start_time)
    print("\n══════════════════════════════════════════════")
    print(f"  ✅ Ingestion complete")
    print(f"     Items processed : {total_ingested}")
    print(f"     Total seen URLs  : {len(seen)}")
    print(f"     Elapsed          : {elapsed}s")
    print("══════════════════════════════════════════════")


if __name__ == "__main__":
    main()
