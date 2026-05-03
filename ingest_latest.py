#!/usr/bin/env python3
"""
Jarvis RAG — Latest YouTube Ingestion Script
Fetches recent videos (default: last 30 days) from curated tech/AI channels,
extracts transcripts, and ingests them into the RAG knowledge base via the API.

Usage:
    python ingest_latest.py                          # ingest all channels, last 30 days
    python ingest_latest.py --days 7                 # last 7 days only
    python ingest_latest.py --channel fireship       # single channel
    python ingest_latest.py --max-per-channel 3      # cap videos per channel
    python ingest_latest.py --host http://localhost:8000
    python ingest_latest.py --dry-run                # list videos without ingesting

Requires on RunPod:
    pip install yt-dlp youtube-transcript-api requests
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

# ── Curated Channel Registry ──────────────────────────────────────────────────
# Format: key → {yt_handle, display_name, source_tier, credibility, categories}
CHANNELS = {
    "fireship": {
        "handle": "@Fireship",
        "name": "Fireship",
        "tier": "tier_1",
        "credibility": 0.95,
        "categories": ["dev", "web", "ai", "tools"],
    },
    "twomin": {
        "handle": "@TwoMinutePapers",
        "name": "Two Minute Papers",
        "tier": "tier_1",
        "credibility": 0.95,
        "categories": ["ai", "ml", "research"],
    },
    "karpathy": {
        "handle": "@AndrejKarpathy",
        "name": "Andrej Karpathy",
        "tier": "tier_1",
        "credibility": 1.0,
        "categories": ["ai", "ml", "llm", "deep-learning"],
    },
    "yannic": {
        "handle": "@YannicKilcher",
        "name": "Yannic Kilcher",
        "tier": "tier_1",
        "credibility": 0.95,
        "categories": ["ai", "ml", "papers"],
    },
    "aiexplained": {
        "handle": "@aiexplained-official",
        "name": "AI Explained",
        "tier": "tier_1",
        "credibility": 0.90,
        "categories": ["ai", "llm", "agi"],
    },
    "mattwolfe": {
        "handle": "@mreflow",
        "name": "Matt Wolfe",
        "tier": "tier_2",
        "credibility": 0.85,
        "categories": ["ai", "tools", "productivity"],
    },
    "lex": {
        "handle": "@lexfridman",
        "name": "Lex Fridman",
        "tier": "tier_2",
        "credibility": 0.85,
        "categories": ["ai", "tech", "interviews"],
    },
    "theaigrid": {
        "handle": "@TheAIGRID",
        "name": "The AI Grid",
        "tier": "tier_2",
        "credibility": 0.80,
        "categories": ["ai", "news", "llm"],
    },
    "samwitteveen": {
        "handle": "@samwitteveenai",
        "name": "Sam Witteveen",
        "tier": "tier_1",
        "credibility": 0.90,
        "categories": ["ai", "llm", "langchain", "rag"],
    },
    "ibm": {
        "handle": "@IBMTechnology",
        "name": "IBM Technology",
        "tier": "tier_1",
        "credibility": 0.90,
        "categories": ["cloud", "ai", "enterprise", "kubernetes"],
    },
    "gcptechshow": {
        "handle": "@googlecloudtech",
        "name": "Google Cloud Tech",
        "tier": "tier_1",
        "credibility": 0.95,
        "categories": ["cloud", "gcp", "ai", "infrastructure"],
    },
    "awsonair": {
        "handle": "@AWSEventsChannel",
        "name": "AWS Events",
        "tier": "tier_1",
        "credibility": 0.95,
        "categories": ["cloud", "aws", "infrastructure", "ai"],
    },
}


# ── Transcript Extraction ─────────────────────────────────────────────────────

def get_transcript_api(video_id: str) -> Optional[str]:
    """Try YouTube transcript API first (fast, no audio download)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_list = YouTubeTranscriptApi.get_transcript(
            video_id, languages=["en", "en-US", "en-GB"]
        )
        return " ".join(chunk["text"] for chunk in transcript_list).strip()
    except Exception:
        return None


def get_transcript_whisper(video_id: str) -> Optional[str]:
    """Fallback: download audio via yt-dlp and transcribe with faster-whisper."""
    import os
    import tempfile

    audio_path = os.path.join(tempfile.gettempdir(), f"{video_id}.mp3")
    url = f"https://www.youtube.com/watch?v={video_id}"

    # Download audio only
    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "5",
        "-o", audio_path,
        "--quiet",
        url,
    ]
    try:
        subprocess.run(cmd, check=True, timeout=120)
    except Exception as e:
        print(f"    yt-dlp error: {e}")
        return None

    if not os.path.exists(audio_path):
        return None

    # Transcribe with faster-whisper
    try:
        from faster_whisper import WhisperModel
        import torch

        if torch.cuda.is_available():
            device, compute_type, model_size = "cuda", "int8", "large-v3"
        else:
            device, compute_type, model_size = "cpu", "float32", "base"

        print(f"    Whisper {model_size} on {device}...")
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments, _ = model.transcribe(audio_path, language="en")
        transcript = " ".join(seg.text.strip() for seg in segments)
        return transcript.strip() if transcript else None
    except Exception as e:
        print(f"    Whisper error: {e}")
        return None
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


def get_transcript(video_id: str) -> Optional[str]:
    """Try API first, fall back to Whisper."""
    t = get_transcript_api(video_id)
    if t and len(t) > 200:
        return t
    print(f"    No captions — falling back to Whisper...")
    return get_transcript_whisper(video_id)


# ── Channel Video Listing ─────────────────────────────────────────────────────

def list_recent_videos(handle: str, days: int, max_videos: int) -> list:
    """Use yt-dlp to list recent uploads from a channel."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y%m%d")

    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--playlist-end", str(max_videos * 3),   # fetch more to allow date filtering
        "--dateafter", cutoff_str,
        "--print", "%(id)s\t%(title)s\t%(upload_date)s\t%(duration)s",
        "--no-warnings",
        "--quiet",
        f"https://www.youtube.com/{handle}/videos",
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, check=False
        )
        videos = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            vid_id, title, upload_date = parts[0], parts[1], parts[2]
            duration = int(parts[3]) if len(parts) > 3 else 0
            # Skip shorts (< 90s) and very long videos (> 90 min)
            if duration and (duration < 90 or duration > 5400):
                continue
            # Parse date
            try:
                pub_dt = datetime.strptime(upload_date, "%Y%m%d").replace(
                    tzinfo=timezone.utc
                )
                pub_iso = pub_dt.isoformat()
            except Exception:
                pub_iso = datetime.now(timezone.utc).isoformat()
            videos.append({"id": vid_id, "title": title, "published": pub_iso})
            if len(videos) >= max_videos:
                break
        return videos
    except Exception as e:
        print(f"  yt-dlp list error for {handle}: {e}")
        return []


# ── API Ingestion ─────────────────────────────────────────────────────────────

def ingest_item(host: str, api_key: str, item: dict) -> bool:
    """POST a single content item to /ingest."""
    payload = {
        "source_type": "youtube",
        "content_list": [item],
    }
    try:
        resp = requests.post(
            f"{host}/ingest",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        if resp.status_code == 200:
            return True
        print(f"    Ingest HTTP {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"    Ingest request error: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest latest YouTube videos into Jarvis RAG")
    parser.add_argument("--host", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--api-key", default="jarvis-runpod-key", help="API key")
    parser.add_argument("--days", type=int, default=30, help="Fetch videos from last N days (default: 30)")
    parser.add_argument("--channel", default=None, help=f"Single channel key ({', '.join(CHANNELS.keys())})")
    parser.add_argument("--max-per-channel", type=int, default=5, help="Max videos per channel (default: 5)")
    parser.add_argument("--dry-run", action="store_true", help="List videos without ingesting")
    parser.add_argument("--min-words", type=int, default=100, help="Minimum transcript words (default: 100)")
    args = parser.parse_args()

    channels_to_run = (
        {args.channel: CHANNELS[args.channel]}
        if args.channel and args.channel in CHANNELS
        else CHANNELS
    )

    if args.channel and args.channel not in CHANNELS:
        print(f"❌ Unknown channel key: {args.channel}")
        print(f"   Available: {', '.join(CHANNELS.keys())}")
        sys.exit(1)

    print("══════════════════════════════════════════════")
    print(f"  Jarvis RAG — Latest YouTube Ingestion")
    print(f"  Host      : {args.host}")
    print(f"  Window    : last {args.days} days")
    print(f"  Channels  : {len(channels_to_run)}")
    print(f"  Max/chan   : {args.max_per_channel}")
    print(f"  Dry run   : {args.dry_run}")
    print("══════════════════════════════════════════════")

    # Verify API health
    if not args.dry_run:
        try:
            health = requests.get(f"{args.host}/health", timeout=10).json()
            status = health.get("status", "unknown")
            chunks = health.get("kb_chunks", 0)
            print(f"\n  API status : {status}  |  KB chunks: {chunks}")
        except Exception as e:
            print(f"\n  ❌ Cannot reach API at {args.host}: {e}")
            sys.exit(1)

    total_ingested = 0
    total_skipped = 0
    total_failed = 0

    for key, ch in channels_to_run.items():
        handle = ch["handle"]
        print(f"\n▶ {ch['name']} ({handle})")

        videos = list_recent_videos(handle, args.days, args.max_per_channel)
        if not videos:
            print(f"  No recent videos found (last {args.days} days)")
            continue

        print(f"  Found {len(videos)} videos")

        for vid in videos:
            vid_id = vid["id"]
            title = vid["title"]
            pub = vid["published"]
            url = f"https://www.youtube.com/watch?v={vid_id}"

            print(f"  • {title[:70]}")
            print(f"    URL: {url}")

            if args.dry_run:
                print(f"    [dry-run — skipping transcript/ingest]")
                continue

            # Fetch transcript
            print(f"    Fetching transcript...")
            transcript = get_transcript(vid_id)
            if not transcript or len(transcript.split()) < args.min_words:
                word_count = len(transcript.split()) if transcript else 0
                print(f"    ⚠️  Transcript too short ({word_count} words) — skipping")
                total_skipped += 1
                continue

            word_count = len(transcript.split())
            print(f"    ✅ Transcript: {word_count} words")

            # Build ingest item
            item = {
                "title": title,
                "content": transcript,
                "url": url,
                "source_name": ch["name"],
                "source_tier": ch["tier"],
                "source_type": "youtube",
                "credibility_score": ch["credibility"],
                "published": pub,
                "categories": ch["categories"],
            }

            # POST to ingest
            ok = ingest_item(args.host, args.api_key, item)
            if ok:
                print(f"    ✅ Ingested")
                total_ingested += 1
            else:
                print(f"    ❌ Ingest failed")
                total_failed += 1

            time.sleep(0.5)   # be kind to the API

    print("\n══════════════════════════════════════════════")
    print(f"  ✅ Ingestion complete")
    print(f"     Ingested : {total_ingested}")
    print(f"     Skipped  : {total_skipped}")
    print(f"     Failed   : {total_failed}")
    print("══════════════════════════════════════════════")


if __name__ == "__main__":
    main()
