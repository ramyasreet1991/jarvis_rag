#!/usr/bin/env python3
"""
Jarvis RAG — Daily Ingestion Scheduler
Runs ingest_sources.py on a configurable schedule.

Usage:
    python run_scheduler.py                      # run daily at 02:00 UTC
    python run_scheduler.py --time 06:00         # different time
    python run_scheduler.py --interval-hours 6   # every 6 hours
    python run_scheduler.py --run-now            # ingest immediately then schedule
    python run_scheduler.py --days 1             # ingest last 1 day of content

Run in background on RunPod:
    nohup python run_scheduler.py --run-now > /workspace/logs/scheduler.log 2>&1 &
    echo "Scheduler PID: $!"

Or with tmux:
    tmux new-session -d -s scheduler 'python run_scheduler.py --run-now'
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_ingestion(days: int, tier: int = None, extra_args: list = None):
    """Invoke ingest_sources.py as subprocess."""
    cmd = [sys.executable, str(BASE_DIR / "ingest_sources.py"), "--days", str(days)]
    if tier:
        cmd += ["--tier", str(tier)]
    if extra_args:
        cmd += extra_args

    log(f"Starting ingestion: {' '.join(cmd)}")
    start = time.time()
    try:
        result = subprocess.run(cmd, timeout=7200)  # 2-hour max
        elapsed = round(time.time() - start)
        if result.returncode == 0:
            log(f"Ingestion complete ({elapsed}s)")
        else:
            log(f"Ingestion exited with code {result.returncode} ({elapsed}s)")
    except subprocess.TimeoutExpired:
        log("Ingestion timed out after 2 hours")
    except Exception as e:
        log(f"Ingestion error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Schedule daily RAG ingestion")
    parser.add_argument("--time", default="02:00",
                        help="Daily run time in HH:MM UTC (default: 02:00)")
    parser.add_argument("--interval-hours", type=float, default=None,
                        help="Run every N hours instead of daily at --time")
    parser.add_argument("--days", type=int, default=1,
                        help="Ingest content from last N days (default: 1 for daily)")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], default=None,
                        help="Restrict to a specific credibility tier")
    parser.add_argument("--run-now", action="store_true",
                        help="Run ingestion immediately before starting the schedule")
    args = parser.parse_args()

    extra = []
    if args.tier:
        extra = ["--tier", str(args.tier)]

    log("══════════════════════════════════════════════")
    log("  Jarvis RAG — Ingestion Scheduler")
    if args.interval_hours:
        log(f"  Schedule : every {args.interval_hours}h")
    else:
        log(f"  Schedule : daily at {args.time} UTC")
    log(f"  Window   : last {args.days} days")
    log("══════════════════════════════════════════════")

    # ── Immediate run ──────────────────────────────────────────────────────────
    if args.run_now:
        log("Running initial ingestion now...")
        run_ingestion(args.days, args.tier, extra)

    # ── Scheduled loop ─────────────────────────────────────────────────────────
    if args.interval_hours:
        interval_sec = int(args.interval_hours * 3600)
        log(f"Sleeping {args.interval_hours}h between runs. Ctrl-C to stop.")
        while True:
            time.sleep(interval_sec)
            run_ingestion(args.days, args.tier, extra)
    else:
        # Daily at specified UTC time
        run_hour, run_min = map(int, args.time.split(":"))
        log(f"Waiting for next {args.time} UTC window. Ctrl-C to stop.")
        while True:
            now = datetime.now(timezone.utc)
            next_run = now.replace(hour=run_hour, minute=run_min, second=0, microsecond=0)
            if next_run <= now:
                # Already past today's window — schedule for tomorrow
                from datetime import timedelta
                next_run = next_run + timedelta(days=1)
            wait_sec = (next_run - now).total_seconds()
            log(f"Next run at {next_run.strftime('%Y-%m-%d %H:%M')} UTC "
                f"({round(wait_sec/3600, 1)}h from now)")
            time.sleep(wait_sec)
            run_ingestion(args.days, args.tier, extra)


if __name__ == "__main__":
    main()
