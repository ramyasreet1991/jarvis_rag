"""
Blue Team Agent — Momentum & Technical Analysis (weight: 25%)

Implements the NSE Nifty200 Momentum 30 methodology:
  • 6-month normalised momentum  = 126-day return / annualised 126-day std
  • 12-month normalised momentum = 252-day return / annualised 252-day std
  • Combined momentum score (50/50 z-scored across universe)

Plus supplementary technicals:
  • RSI(14)          — overbought/oversold
  • MACD(12,26,9)    — trend confirmation
  • EMA 20/50/200    — trend structure
  • ATR(14)          — volatility / stop placement
  • Volume trend     — institutional participation proxy
"""
from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np
import pandas as pd

from nifty_momentum.utils.market_data import get_price_history
from nifty_momentum.utils.scoring import AgentScore, clamp, normalise_to_100

logger = logging.getLogger(__name__)


# ── Momentum ──────────────────────────────────────────────────────────────────

def _momentum_score(close: pd.Series, lookback: int) -> Optional[float]:
    """Normalised momentum = return / annualised std (Sharpe-style)."""
    if len(close) <= lookback:
        return None
    ret = float(close.iloc[-1] / close.iloc[-lookback] - 1)
    daily_rets = close.pct_change().dropna()
    if len(daily_rets) < lookback // 2:
        return None
    std_ann = float(daily_rets.tail(lookback).std()) * math.sqrt(252)
    if std_ann == 0:
        return None
    return ret / std_ann


# ── Technical Indicators ──────────────────────────────────────────────────────

def _rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series = 100 - 100 / (1 + rs)
    val = rsi_series.iloc[-1]
    return float(val) if not math.isnan(val) else None


def _macd(close: pd.Series) -> tuple[Optional[float], Optional[float]]:
    """Returns (MACD line, signal line) latest values."""
    if len(close) < 35:
        return None, None
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    return float(macd_line.iloc[-1]), float(signal.iloc[-1])


def _ema_structure(close: pd.Series) -> tuple[bool, bool, bool]:
    """
    Returns (price > EMA20, EMA20 > EMA50, EMA50 > EMA200).
    All True = strong uptrend.
    """
    if len(close) < 202:
        return False, False, False
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
    price = float(close.iloc[-1])
    return price > ema20, ema20 > ema50, ema50 > ema200


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> Optional[float]:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr_series = tr.rolling(period).mean()
    val = atr_series.iloc[-1]
    return float(val) if not math.isnan(val) else None


def _volume_trend(volume: pd.Series, period: int = 20) -> Optional[float]:
    """Returns ratio of recent 5-day avg vol to 20-day avg vol."""
    if len(volume) < period:
        return None
    recent = float(volume.tail(5).mean())
    baseline = float(volume.tail(period).mean())
    return recent / baseline if baseline > 0 else None


# ── Main runner ───────────────────────────────────────────────────────────────

def run(symbol: str) -> AgentScore:
    df = get_price_history(symbol, years=2)
    if df.empty or len(df) < 30:
        return AgentScore(
            agent="BlueTeam",
            score=50.0,
            confidence=0.1,
            flags=["Insufficient price history"],
        )

    close = df["Close"].squeeze()
    high = df["High"].squeeze()
    low = df["Low"].squeeze()
    volume = df["Volume"].squeeze()

    # ── Momentum (core Nifty200 methodology) ─────────────────────────────────
    mom_6m = _momentum_score(close, 126)
    mom_12m = _momentum_score(close, 252)

    flags: list[str] = []
    momentum_raw_score = 50.0
    if mom_6m is not None and mom_12m is not None:
        # Average of the two normalised scores; map to 0-100
        # Typical range: -2 to +2 → map (-2,+2) → (0,100)
        mom_avg = (mom_6m + mom_12m) / 2
        momentum_raw_score = normalise_to_100(mom_avg, -2.0, 2.0)
        flags.append(f"6M momentum score: {mom_6m:.2f}")
        flags.append(f"12M momentum score: {mom_12m:.2f}")
    elif mom_6m is not None:
        momentum_raw_score = normalise_to_100(mom_6m, -2.0, 2.0)
    elif mom_12m is not None:
        momentum_raw_score = normalise_to_100(mom_12m, -2.0, 2.0)

    # ── RSI ──────────────────────────────────────────────────────────────────
    rsi_val = _rsi(close)
    rsi_score = 50.0
    if rsi_val is not None:
        if 40 <= rsi_val <= 70:           # sweet spot for momentum entries
            rsi_score = 75.0
        elif rsi_val > 80:                # overbought
            rsi_score = 30.0
            flags.append(f"RSI overbought ({rsi_val:.0f})")
        elif rsi_val < 30:                # oversold
            rsi_score = 40.0
            flags.append(f"RSI oversold ({rsi_val:.0f})")
        else:
            rsi_score = 55.0

    # ── MACD ─────────────────────────────────────────────────────────────────
    macd_val, macd_sig = _macd(close)
    macd_score = 50.0
    if macd_val is not None and macd_sig is not None:
        if macd_val > macd_sig:
            macd_score = 70.0
            flags.append("MACD bullish crossover")
        else:
            macd_score = 35.0
            flags.append("MACD bearish")

    # ── EMA Structure ─────────────────────────────────────────────────────────
    p_gt_20, e20_gt_50, e50_gt_200 = _ema_structure(close)
    ema_count = sum([p_gt_20, e20_gt_50, e50_gt_200])
    ema_score = ema_count / 3 * 100  # 0, 33, 67, or 100
    if ema_count == 3:
        flags.append("Strong EMA uptrend (price > 20 > 50 > 200)")
    elif ema_count == 0:
        flags.append("EMA bearish alignment")

    # ── Volume trend ──────────────────────────────────────────────────────────
    vol_ratio = _volume_trend(volume)
    vol_score = 50.0
    if vol_ratio is not None:
        if vol_ratio > 1.3:
            vol_score = 75.0
            flags.append(f"Above-average volume ({vol_ratio:.1f}x)")
        elif vol_ratio < 0.7:
            vol_score = 35.0

    # ── ATR (used for stop-loss, not scoring) ─────────────────────────────────
    atr_val = _atr(high, low, close)

    # ── Composite technical score ─────────────────────────────────────────────
    composite = clamp(
        momentum_raw_score * 0.50
        + rsi_score * 0.15
        + macd_score * 0.15
        + ema_score * 0.15
        + vol_score * 0.05
    )

    current_price = float(close.iloc[-1])
    stop_loss = (current_price - 2 * atr_val) if atr_val else None
    target = (current_price * 1.20) if composite >= 70 else (current_price * 1.10)

    return AgentScore(
        agent="BlueTeam",
        score=composite,
        confidence=0.80,
        flags=flags,
        details={
            "momentum_6m_norm": round(mom_6m, 3) if mom_6m else None,
            "momentum_12m_norm": round(mom_12m, 3) if mom_12m else None,
            "momentum_raw_score": round(momentum_raw_score, 1),
            "rsi": round(rsi_val, 1) if rsi_val else None,
            "rsi_score": round(rsi_score, 1),
            "macd_line": round(macd_val, 3) if macd_val else None,
            "macd_signal": round(macd_sig, 3) if macd_sig else None,
            "ema_alignment": f"{ema_count}/3",
            "vol_ratio": round(vol_ratio, 2) if vol_ratio else None,
            "atr": round(atr_val, 2) if atr_val else None,
            "current_price": round(current_price, 2),
            "stop_loss_suggestion": round(stop_loss, 2) if stop_loss else None,
            "target_suggestion": round(target, 2),
        },
    )


def compute_momentum_ranks(symbols: list[str]) -> dict[str, float]:
    """
    Compute raw combined momentum scores for a universe to produce z-score ranks.
    Used by synthesizer to rank the Nifty200 → top 30 selection.
    """
    raw: dict[str, float] = {}
    for sym in symbols:
        df = get_price_history(sym, years=2)
        if df.empty or len(df) < 30:
            continue
        close = df["Close"].squeeze()
        m6 = _momentum_score(close, 126)
        m12 = _momentum_score(close, 252)
        if m6 is not None and m12 is not None:
            raw[sym] = (m6 + m12) / 2
        elif m6 is not None:
            raw[sym] = m6
    return raw
