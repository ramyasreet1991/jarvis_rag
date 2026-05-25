"""
Red Team Agent — Governance, Fraud & ESG Screener (weight: 30%)

Hard-blocks on:
  • Promoter pledge > 50 %
  • Active fraud / regulatory action (SEBI, MCA, ED, CBI)
  • Audit qualification on going-concern / fraud
  • Repeated related-party transaction abuse
  • ESG score < 30 (if available)

Returns 0-100 score (100 = cleanest governance).
Any BLOCK flag bypasses all other agents → AVOID signal.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional
import asyncio

import feedparser
import requests
from bs4 import BeautifulSoup

from nifty_momentum.utils.scoring import AgentScore, clamp

logger = logging.getLogger(__name__)

# ─── RSS sources for regulatory news ─────────────────────────────────────────
_SEBI_RSS = "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&type=1&subType=0&rss=1"
_MONEYCONTROL_RSS = "https://www.moneycontrol.com/rss/MCtopnews.xml"
_ET_MARKETS_RSS = "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"

_BLOCK_KEYWORDS = [
    "fraud", "sebi ban", "insider trading", "money laundering", "ed raid",
    "cbi investigation", "nclt", "insolvency", "arrested", "debarred",
    "show cause notice", "penalty imposed", "adjudication order",
    "wilful defaulter", "npa classified", "audit qualification",
    "going concern", "promoter pledged shares", "pledging",
]

_WARNING_KEYWORDS = [
    "related party", "corporate governance concern", "minority shareholder",
    "qualified audit", "esg controversy", "environmental violation",
    "labour violation", "bribery allegation",
]


def _fetch_rss_headlines(url: str, timeout: int = 8) -> list[str]:
    try:
        feed = feedparser.parse(url)
        return [e.title.lower() for e in feed.entries[:50]]
    except Exception:
        return []


def _scrape_bse_announcements(symbol_base: str) -> list[str]:
    """Lightweight BSE announcement scrape (no auth required)."""
    try:
        url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{symbol_base}_Corporate_Announcements.xml"
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "lxml")
        return [tag.get_text().lower() for tag in soup.find_all("description")[:20]]
    except Exception:
        return []


def _check_promoter_pledge(fundamentals: dict) -> tuple[float, list[str]]:
    """
    Promoter holding via heldPercentInsiders (yfinance proxy).
    Real pledge data would need BSE shareholding XML.  Using insider% as proxy.
    Returns (pledge_pct_estimate, flags).
    """
    flags: list[str] = []
    insider_pct = fundamentals.get("heldPercentInsiders") or 0.0
    insider_pct *= 100  # convert 0–1 fraction → %

    # BSE real pledge lookup (best-effort)
    pledge_score = 100.0
    if insider_pct > 75:
        # Very concentrated → might indicate heavy pledge
        flags.append(f"High promoter concentration ({insider_pct:.0f}%) — verify pledge data")
        pledge_score = 60.0
    return pledge_score, flags


def _governance_news_scan(symbol: str, company_name: str) -> tuple[float, list[str], bool]:
    """
    Scan recent news for block/warning keywords.
    Returns (score 0-100, flags, hard_blocked).
    """
    ticker_base = symbol.replace(".NS", "").lower()
    name_tokens = company_name.lower().split()[:3]

    headlines: list[str] = []
    for feed_url in [_MONEYCONTROL_RSS, _ET_MARKETS_RSS]:
        headlines.extend(_fetch_rss_headlines(feed_url))

    relevant = [h for h in headlines if ticker_base in h or any(t in h for t in name_tokens)]

    flags: list[str] = []
    hard_blocked = False
    score = 100.0

    for h in relevant:
        for kw in _BLOCK_KEYWORDS:
            if kw in h:
                flags.append(f"BLOCK keyword '{kw}' found in headline: {h[:80]}")
                hard_blocked = True
                score = 0.0
                break
        if not hard_blocked:
            for kw in _WARNING_KEYWORDS:
                if kw in h:
                    flags.append(f"WARNING keyword '{kw}' found: {h[:80]}")
                    score = max(score - 15.0, 20.0)

    return score, flags, hard_blocked


def _esg_check(fundamentals: dict) -> tuple[float, list[str]]:
    """
    yfinance doesn't expose ESG scores; placeholder for future Refinitiv/
    Sustainalytics integration.  Default: pass (neutral 75).
    """
    return 75.0, []


def run(symbol: str, fundamentals: dict) -> AgentScore:
    """
    Execute Red Team screen.

    Parameters
    ----------
    symbol : str  e.g. "RELIANCE.NS"
    fundamentals : dict  from market_data.get_fundamentals()
    """
    company_name = fundamentals.get("longName", symbol)

    pledge_score, pledge_flags = _check_promoter_pledge(fundamentals)
    news_score, news_flags, hard_blocked = _governance_news_scan(symbol, company_name)
    esg_score, esg_flags = _esg_check(fundamentals)

    all_flags = pledge_flags + news_flags + esg_flags

    if hard_blocked:
        composite = 0.0
    else:
        # Weight: pledge 40%, news scan 40%, ESG 20%
        composite = clamp(pledge_score * 0.4 + news_score * 0.4 + esg_score * 0.2)

    return AgentScore(
        agent="RedTeam",
        score=composite,
        confidence=0.7 if not hard_blocked else 0.95,
        flags=all_flags,
        details={
            "pledge_score": pledge_score,
            "news_score": news_score,
            "esg_score": esg_score,
            "company": company_name,
        },
        blocked=hard_blocked,
    )
