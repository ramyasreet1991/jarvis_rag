"""
Green Team Agent — Fundamental Quality Screener (weight: 25%)

Scores across 6 dimensions:
  1. Profitability  — ROE > 15%, ROA > 8%, operating margin > 12%
  2. Solvency       — D/E < 0.5x, current ratio > 1.5, interest coverage > 5x
  3. Valuation      — PEG < 1.0, P/B < 3, P/S reasonable
  4. Cash Flow      — FCF yield > 5%, positive FCF margin
  5. Growth         — Revenue growth > 10%, earnings growth > 12%
  6. Capital Alloc  — ROCE proxy via ROE, margin expansion

Returns 0-100 composite score.
"""
from __future__ import annotations

import logging
import math
from typing import Optional

from nifty_momentum.utils.scoring import AgentScore, clamp, normalise_to_100

logger = logging.getLogger(__name__)


def _score_profitability(info: dict) -> tuple[float, list[str]]:
    flags: list[str] = []
    score = 0.0
    weight = 0.0

    roe = info.get("returnOnEquity")  # fraction e.g. 0.18 = 18%
    if roe is not None:
        roe_pct = roe * 100
        pts = normalise_to_100(roe_pct, 5, 35)
        score += pts * 0.40
        weight += 0.40
        if roe_pct < 10:
            flags.append(f"Low ROE {roe_pct:.1f}% (threshold 15%)")
        elif roe_pct >= 20:
            flags.append(f"Excellent ROE {roe_pct:.1f}%")

    roa = info.get("returnOnAssets")
    if roa is not None:
        roa_pct = roa * 100
        pts = normalise_to_100(roa_pct, 2, 20)
        score += pts * 0.30
        weight += 0.30

    op_margin = info.get("operatingMargins")
    if op_margin is not None:
        op_pct = op_margin * 100
        pts = normalise_to_100(op_pct, 5, 30)
        score += pts * 0.30
        weight += 0.30
        if op_pct < 8:
            flags.append(f"Thin operating margin {op_pct:.1f}%")

    return (score / weight if weight > 0 else 50.0), flags


def _score_solvency(info: dict) -> tuple[float, list[str]]:
    flags: list[str] = []
    score = 0.0
    weight = 0.0

    de = info.get("debtToEquity")  # ratio (not %)
    if de is not None:
        # Lower D/E is better; cap benefit at 0, penalise above 1.5
        pts = normalise_to_100(-de, -2.0, 0.0)
        score += pts * 0.50
        weight += 0.50
        if de > 1.0:
            flags.append(f"High D/E ratio {de:.2f}x")
        elif de < 0.3:
            flags.append(f"Very low D/E {de:.2f}x — strong balance sheet")

    cr = info.get("currentRatio")
    if cr is not None:
        pts = normalise_to_100(cr, 0.5, 3.0)
        score += pts * 0.30
        weight += 0.30
        if cr < 1.0:
            flags.append(f"Current ratio below 1 ({cr:.2f}x)")

    # Interest coverage proxy: EBIT / interest expense
    ebitda = info.get("ebitda")
    total_debt = info.get("totalDebt")
    if ebitda and total_debt and total_debt > 0:
        # rough: assume 7% avg interest rate
        interest_est = total_debt * 0.07
        icr = ebitda / interest_est
        pts = normalise_to_100(icr, 1, 20)
        score += pts * 0.20
        weight += 0.20
        if icr < 3:
            flags.append(f"Low interest coverage ~{icr:.1f}x")

    return (score / weight if weight > 0 else 50.0), flags


def _score_valuation(info: dict) -> tuple[float, list[str]]:
    flags: list[str] = []
    score = 0.0
    weight = 0.0

    peg = info.get("pegRatio")
    if peg is not None and peg > 0:
        pts = normalise_to_100(-peg, -4.0, 0.0)  # lower PEG is better
        score += pts * 0.45
        weight += 0.45
        if peg > 2.5:
            flags.append(f"Expensive PEG {peg:.2f}")
        elif peg < 1.0:
            flags.append(f"Attractive PEG {peg:.2f}")

    pb = info.get("priceToBook")
    if pb is not None and pb > 0:
        pts = normalise_to_100(-pb, -8.0, 0.0)
        score += pts * 0.30
        weight += 0.30

    ps = info.get("priceToSales")
    if ps is not None and ps > 0:
        pts = normalise_to_100(-ps, -10.0, 0.0)
        score += pts * 0.25
        weight += 0.25

    return (score / weight if weight > 0 else 50.0), flags


def _score_cashflow(info: dict) -> tuple[float, list[str]]:
    flags: list[str] = []
    fcf = info.get("freeCashflow")
    mktcap = info.get("marketCap")

    if not fcf or not mktcap or mktcap <= 0:
        return 50.0, ["FCF data unavailable"]

    if fcf < 0:
        flags.append(f"Negative FCF: ₹{fcf/1e7:.0f} Cr")
        return 20.0, flags

    fcf_yield = fcf / mktcap * 100  # %
    pts = normalise_to_100(fcf_yield, 0, 12)
    if fcf_yield > 7:
        flags.append(f"Strong FCF yield {fcf_yield:.1f}%")
    elif fcf_yield < 2:
        flags.append(f"Low FCF yield {fcf_yield:.1f}%")
    return pts, flags


def _score_growth(info: dict) -> tuple[float, list[str]]:
    flags: list[str] = []
    score = 0.0
    weight = 0.0

    rev_g = info.get("revenueGrowth")
    if rev_g is not None:
        rev_pct = rev_g * 100
        pts = normalise_to_100(rev_pct, -10, 40)
        score += pts * 0.50
        weight += 0.50
        if rev_pct < 5:
            flags.append(f"Weak revenue growth {rev_pct:.1f}%")
        elif rev_pct > 20:
            flags.append(f"Strong revenue growth {rev_pct:.1f}%")

    earn_g = info.get("earningsGrowth")
    if earn_g is not None:
        earn_pct = earn_g * 100
        pts = normalise_to_100(earn_pct, -20, 50)
        score += pts * 0.50
        weight += 0.50

    return (score / weight if weight > 0 else 50.0), flags


def run(symbol: str, fundamentals: dict) -> AgentScore:
    prof_score, prof_flags = _score_profitability(fundamentals)
    solv_score, solv_flags = _score_solvency(fundamentals)
    val_score, val_flags = _score_valuation(fundamentals)
    cf_score, cf_flags = _score_cashflow(fundamentals)
    gr_score, gr_flags = _score_growth(fundamentals)

    all_flags = prof_flags + solv_flags + val_flags + cf_flags + gr_flags

    # Weighted composite: quality metrics
    composite = clamp(
        prof_score * 0.30
        + solv_score * 0.20
        + val_score * 0.20
        + cf_score * 0.20
        + gr_score * 0.10
    )

    # Confidence based on data availability
    n_available = sum(1 for v in [
        fundamentals.get("returnOnEquity"), fundamentals.get("debtToEquity"),
        fundamentals.get("pegRatio"), fundamentals.get("freeCashflow"),
        fundamentals.get("revenueGrowth"),
    ] if v is not None)
    confidence = 0.5 + n_available * 0.08  # up to 0.9

    return AgentScore(
        agent="GreenTeam",
        score=composite,
        confidence=min(confidence, 0.90),
        flags=all_flags,
        details={
            "profitability": round(prof_score, 1),
            "solvency": round(solv_score, 1),
            "valuation": round(val_score, 1),
            "cashflow": round(cf_score, 1),
            "growth": round(gr_score, 1),
            "roe_pct": round((fundamentals.get("returnOnEquity") or 0) * 100, 1),
            "de_ratio": fundamentals.get("debtToEquity"),
            "peg": fundamentals.get("pegRatio"),
        },
    )
