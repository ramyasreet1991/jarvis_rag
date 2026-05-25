"""
Pipeline orchestrator — runs all 4 agents sequentially, short-circuits on
Red Team hard-block, returns FinalSignal.

Usage:
    from nifty_momentum.pipeline import analyze_stock, analyze_index
    signal = analyze_stock("RELIANCE.NS")
    results = analyze_index()  # all Nifty200, ranked by composite score
"""
from __future__ import annotations

import concurrent.futures
import logging
from typing import Optional

from nifty_momentum.agents import red_team, green_team, blue_team, news_sentinel, synthesizer
from nifty_momentum.agents.blue_team import compute_momentum_ranks
from nifty_momentum.data.constituents import NIFTY200
from nifty_momentum.utils.market_data import get_fundamentals
from nifty_momentum.utils.scoring import AgentScore, FinalSignal, Signal

logger = logging.getLogger(__name__)


def analyze_stock(
    symbol: str,
    universe_momentum_ranks: Optional[dict[str, float]] = None,
) -> FinalSignal:
    """
    Run the full 4-agent pipeline for a single stock.

    Parameters
    ----------
    symbol : str  e.g. "RELIANCE.NS"
    universe_momentum_ranks : optional pre-computed momentum rank dict
        (pass when batch-processing to avoid redundant fetches)
    """
    symbol = symbol.upper()
    if not symbol.endswith(".NS"):
        symbol = symbol + ".NS"

    logger.info("Analysing %s", symbol)

    # ── Step 1: fetch fundamentals (shared across agents) ──────────────────
    fundamentals = get_fundamentals(symbol)

    # ── Step 2: Red Team (governance gate) ────────────────────────────────
    red_score = red_team.run(symbol, fundamentals)
    if red_score.blocked:
        logger.warning("%s hard-blocked by Red Team", symbol)
        return synthesizer.synthesize(symbol, {"RedTeam": red_score})

    # ── Step 3: Run remaining agents in parallel ───────────────────────────
    agent_scores: dict[str, AgentScore] = {"RedTeam": red_score}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            "GreenTeam": pool.submit(green_team.run, symbol, fundamentals),
            "BlueTeam": pool.submit(blue_team.run, symbol),
            "NewsSentinel": pool.submit(news_sentinel.run, symbol, fundamentals),
        }
        for name, fut in futures.items():
            try:
                agent_scores[name] = fut.result(timeout=30)
            except Exception as exc:
                logger.error("%s agent failed for %s: %s", name, symbol, exc)
                agent_scores[name] = AgentScore(
                    agent=name, score=50.0, confidence=0.1,
                    flags=[f"Agent error: {exc}"],
                )

    # ── Step 4: Momentum rank ──────────────────────────────────────────────
    rank = None
    if universe_momentum_ranks:
        sorted_syms = sorted(universe_momentum_ranks, key=universe_momentum_ranks.get, reverse=True)
        try:
            rank = sorted_syms.index(symbol) + 1
        except ValueError:
            pass

    return synthesizer.synthesize(symbol, agent_scores, momentum_rank=rank)


def analyze_index(
    max_workers: int = 8,
    symbols: Optional[list[str]] = None,
) -> list[FinalSignal]:
    """
    Analyse the full Nifty200 universe (or a custom list).
    Returns results sorted by composite_score descending.
    """
    universe = symbols or NIFTY200
    logger.info("Analysing %d stocks", len(universe))

    # Pre-compute momentum ranks across universe for proper percentile ranking
    logger.info("Computing momentum ranks…")
    momentum_ranks = compute_momentum_ranks(universe)

    results: list[FinalSignal] = []

    def _run(sym: str) -> FinalSignal:
        return analyze_stock(sym, universe_momentum_ranks=momentum_ranks)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        for sig in pool.map(_run, universe):
            results.append(sig)

    results.sort(key=lambda x: x.composite_score, reverse=True)
    return results


def get_top_picks(n: int = 5) -> list[FinalSignal]:
    """Return top N BUY signals from the Nifty200 universe."""
    results = analyze_index()
    buys = [r for r in results if r.signal in (Signal.STRONG_BUY, Signal.BUY)]
    return buys[:n]


def get_avoid_list() -> list[FinalSignal]:
    """Return all AVOID (hard-blocked) signals."""
    results = analyze_index()
    return [r for r in results if r.signal == Signal.AVOID]
