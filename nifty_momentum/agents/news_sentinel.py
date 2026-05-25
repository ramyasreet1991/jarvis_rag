"""
News Sentinel Agent — Real-time Sentiment & Event Detection (weight: 20%)

Sources:
  • ET Markets RSS, MoneyControl RSS, BusinessLine RSS
  • SEBI / BSE regulatory RSS
  • Google News RSS (no API key needed)

Scoring:
  • Positive keywords  → +points
  • Negative keywords  → -points
  • Urgency flags      → immediate score penalties
  • Recency decay      → older news weighted less

Returns 0-100 score (50 = neutral; >50 = positive sentiment).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional
import email.utils

import feedparser
import requests
from bs4 import BeautifulSoup

from nifty_momentum.utils.scoring import AgentScore, clamp

logger = logging.getLogger(__name__)

_FEEDS = [
    "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "https://www.moneycontrol.com/rss/buzzingstocks.xml",
    "https://www.thehindubusinessline.com/markets/?service=rss",
]

_GOOGLE_NEWS_TPL = "https://news.google.com/rss/search?q={query}+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en"

_POSITIVE = [
    "record profit", "beat estimate", "strong results", "upgrade", "outperform",
    "buy rating", "target raised", "new high", "contract win", "order win",
    "revenue growth", "expansion", "capacity addition", "dividend", "buyback",
    "fii buying", "dii buying", "block deal buy", "promoter buying",
    "debt free", "margin expansion", "market share gain",
]

_NEGATIVE = [
    "profit warning", "miss estimate", "downgrade", "underperform", "sell rating",
    "target cut", "52-week low", "loss", "revenue decline", "margin pressure",
    "debt concern", "default", "fraud", "scam", "probe", "investigation",
    "promoter selling", "fii selling", "block deal sell", "delisting",
    "npa", "insolvency", "write-off", "recall", "plant shutdown",
]

_URGENCY = [
    "breaking", "urgent", "halt", "circuit", "sebi order", "arrested", "raid",
    "emergency", "crisis", "blowup", "collapse",
]


def _parse_date(entry) -> Optional[datetime]:
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                ts = email.utils.parsedate_to_datetime(raw)
                return ts.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                pass
    return None


def _recency_weight(pub_dt: Optional[datetime], max_age_days: int = 30) -> float:
    """Exponential decay: today=1.0, 30-day-old=0.1."""
    if pub_dt is None:
        return 0.3
    age_days = (datetime.utcnow() - pub_dt).days
    age_days = max(0, age_days)
    return max(0.05, math.exp(-0.08 * age_days))


try:
    import math
except ImportError:
    import cmath as math  # fallback


def _sentiment(text: str) -> tuple[float, list[str]]:
    """Return (score -1 to +1, matched keywords)."""
    t = text.lower()
    pos = sum(1 for kw in _POSITIVE if kw in t)
    neg = sum(1 for kw in _NEGATIVE if kw in t)
    urgent = any(kw in t for kw in _URGENCY)
    total = pos + neg
    if total == 0:
        return 0.0, []
    raw = (pos - neg) / total
    if urgent:
        raw -= 0.4
    matched = [kw for kw in _POSITIVE if kw in t] + [kw for kw in _NEGATIVE if kw in t]
    return max(-1.0, min(1.0, raw)), matched


def _fetch_google_news(query: str) -> list[feedparser.FeedParserDict]:
    try:
        url = _GOOGLE_NEWS_TPL.format(query=requests.utils.quote(query))
        feed = feedparser.parse(url)
        return feed.entries[:15]
    except Exception:
        return []


def _fetch_general_feeds(ticker_base: str, company_tokens: list[str]) -> list[tuple[str, Optional[datetime]]]:
    """Return list of (headline_text, pub_datetime) relevant to this stock."""
    results: list[tuple[str, Optional[datetime]]] = []
    for url in _FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:30]:
                title = (e.get("title") or "").lower()
                summary = (e.get("summary") or "").lower()
                text = title + " " + summary
                if ticker_base in text or any(t in text for t in company_tokens):
                    results.append((text[:300], _parse_date(e)))
        except Exception:
            pass

    # Google News targeted search
    for e in _fetch_google_news(ticker_base.upper()):
        title = (e.get("title") or "").lower()
        results.append((title[:300], _parse_date(e)))

    return results


def run(symbol: str, fundamentals: dict) -> AgentScore:
    company_name = fundamentals.get("longName", symbol)
    ticker_base = symbol.replace(".NS", "").lower()
    company_tokens = [w for w in company_name.lower().split() if len(w) > 3][:4]

    articles = _fetch_general_feeds(ticker_base, company_tokens)

    if not articles:
        return AgentScore(
            agent="NewsSentinel",
            score=50.0,
            confidence=0.2,
            flags=["No recent news found — neutral"],
            details={"articles_found": 0},
        )

    weighted_scores: list[float] = []
    all_keywords: list[str] = []
    flags: list[str] = []
    urgency_hit = False

    for text, pub_dt in articles:
        sent, kws = _sentiment(text)
        w = _recency_weight(pub_dt)
        weighted_scores.append(sent * w)
        all_keywords.extend(kws)
        if any(kw in text for kw in _URGENCY):
            urgency_hit = True

    avg_sentiment = sum(weighted_scores) / len(weighted_scores) if weighted_scores else 0.0
    # Map (-1, +1) → (0, 100)
    score = clamp(50 + avg_sentiment * 50)

    if urgency_hit:
        score = max(score - 20, 5)
        flags.append("Urgency event detected in headlines")

    unique_kws = list(dict.fromkeys(all_keywords))[:8]
    if unique_kws:
        flags.append(f"Key themes: {', '.join(unique_kws)}")

    return AgentScore(
        agent="NewsSentinel",
        score=score,
        confidence=min(0.4 + len(articles) * 0.03, 0.75),
        flags=flags,
        details={
            "articles_found": len(articles),
            "avg_sentiment": round(avg_sentiment, 3),
            "urgency": urgency_hit,
            "keywords": unique_kws,
        },
    )
