"""
Market data fetcher — yfinance wrapper for NSE stocks.
All public; no API key required.  Cache TTL: 4h for daily prices, 24h for fundamentals.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_PRICE_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_FUND_CACHE: dict[str, tuple[float, dict]] = {}
_PRICE_TTL = 4 * 3600
_FUND_TTL = 24 * 3600


def _now() -> float:
    return time.time()


def get_price_history(symbol: str, years: int = 2) -> pd.DataFrame:
    """Return OHLCV DataFrame for last `years` years, cached 4h."""
    cached = _PRICE_CACHE.get(symbol)
    if cached and (_now() - cached[0]) < _PRICE_TTL:
        return cached[1]

    end = datetime.now()
    start = end - timedelta(days=years * 365)
    try:
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
        if df.empty:
            logger.warning("No price data for %s", symbol)
            return pd.DataFrame()
        _PRICE_CACHE[symbol] = (_now(), df)
        return df
    except Exception as exc:
        logger.error("Price fetch failed for %s: %s", symbol, exc)
        return pd.DataFrame()


def get_fundamentals(symbol: str) -> dict:
    """Return key fundamental ratios from yfinance info, cached 24h."""
    cached = _FUND_CACHE.get(symbol)
    if cached and (_now() - cached[0]) < _FUND_TTL:
        return cached[1]

    try:
        tk = yf.Ticker(symbol)
        info = tk.info or {}
        data = {
            "symbol": symbol,
            "longName": info.get("longName", symbol),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "marketCap": info.get("marketCap"),
            "trailingPE": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "priceToBook": info.get("priceToBook"),
            "priceToSales": info.get("priceToSalesTrailing12Months"),
            "returnOnEquity": info.get("returnOnEquity"),
            "returnOnAssets": info.get("returnOnAssets"),
            "debtToEquity": info.get("debtToEquity"),
            "currentRatio": info.get("currentRatio"),
            "quickRatio": info.get("quickRatio"),
            "grossMargins": info.get("grossMargins"),
            "operatingMargins": info.get("operatingMargins"),
            "profitMargins": info.get("profitMargins"),
            "revenueGrowth": info.get("revenueGrowth"),
            "earningsGrowth": info.get("earningsGrowth"),
            "freeCashflow": info.get("freeCashflow"),
            "totalCash": info.get("totalCash"),
            "totalDebt": info.get("totalDebt"),
            "enterpriseValue": info.get("enterpriseValue"),
            "ebitda": info.get("ebitda"),
            "totalRevenue": info.get("totalRevenue"),
            "pegRatio": info.get("pegRatio"),
            "beta": info.get("beta"),
            "52WeekHigh": info.get("fiftyTwoWeekHigh"),
            "52WeekLow": info.get("fiftyTwoWeekLow"),
            "sharesOutstanding": info.get("sharesOutstanding"),
            "heldPercentInsiders": info.get("heldPercentInsiders"),
            "heldPercentInstitutions": info.get("heldPercentInstitutions"),
        }
        _FUND_CACHE[symbol] = (_now(), data)
        return data
    except Exception as exc:
        logger.error("Fundamentals fetch failed for %s: %s", symbol, exc)
        return {"symbol": symbol, "error": str(exc)}


def get_current_price(symbol: str) -> Optional[float]:
    """Return latest closing price."""
    df = get_price_history(symbol, years=1)
    if df.empty:
        return None
    return float(df["Close"].iloc[-1])


def get_nifty200_index_returns() -> dict[str, float]:
    """Return 1Y returns for ^CNX200 (Nifty200 index) for relative comparison."""
    df = get_price_history("^CNX200", years=2)
    if df.empty:
        return {}
    close = df["Close"]
    result = {}
    for label, days in [("6m", 126), ("12m", 252)]:
        if len(close) > days:
            ret = float(close.iloc[-1] / close.iloc[-days] - 1)
            result[label] = ret
    return result
