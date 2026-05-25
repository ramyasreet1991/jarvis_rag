"""
Synthesizer — Multi-agent score aggregation & signal generation.

Weights:
  RedTeam      30 %  (governance — hard-block capability)
  GreenTeam    25 %  (fundamentals)
  BlueTeam     25 %  (momentum / technicals)
  NewsSentinel 20 %  (news sentiment)

Entry / stop / target derived from Blue Team's ATR analysis.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from nifty_momentum.utils.scoring import (
    AgentScore, FinalSignal, Signal, RiskLevel,
    score_to_signal, score_to_position_size, score_to_risk, clamp,
)

logger = logging.getLogger(__name__)

_WEIGHTS = {
    "RedTeam": 0.30,
    "GreenTeam": 0.25,
    "BlueTeam": 0.25,
    "NewsSentinel": 0.20,
}


def synthesize(
    symbol: str,
    agent_scores: dict[str, AgentScore],
    momentum_rank: Optional[int] = None,
) -> FinalSignal:
    """
    Combine all agent scores into a final actionable signal.

    Parameters
    ----------
    symbol : str
    agent_scores : dict mapping agent name → AgentScore
    momentum_rank : optional int, rank within Nifty200 universe (lower=better)
    """
    # Hard-block check — any blocked agent → AVOID immediately
    for score in agent_scores.values():
        if score.blocked:
            return FinalSignal(
                symbol=symbol,
                signal=Signal.AVOID,
                composite_score=0.0,
                risk_level=RiskLevel.VERY_HIGH,
                agent_scores=agent_scores,
                rationale=f"Hard-blocked by {score.agent}: " + "; ".join(score.flags[:3]),
                position_size_pct=0.0,
                momentum_rank=momentum_rank,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    # Weighted composite
    total_weight = 0.0
    weighted_sum = 0.0
    for agent_name, weight in _WEIGHTS.items():
        if agent_name in agent_scores:
            s = agent_scores[agent_name]
            # Confidence-adjusted weight
            adj_weight = weight * s.confidence
            weighted_sum += s.score * adj_weight
            total_weight += adj_weight

    composite = clamp(weighted_sum / total_weight) if total_weight > 0 else 50.0

    # Momentum rank bonus: top 30 → +3 pts
    if momentum_rank is not None and momentum_rank <= 30:
        composite = clamp(composite + 3.0)

    signal = score_to_signal(composite)
    position_pct = score_to_position_size(composite, signal)

    # Collect all flags
    all_flags: list[str] = []
    for s in agent_scores.values():
        all_flags.extend(s.flags)

    red_flags = sum(1 for s in agent_scores.values() if s.flags and s.score < 40)
    risk_level = score_to_risk(composite, red_flags)

    # Price targets from BlueTeam details
    blue = agent_scores.get("BlueTeam")
    entry_price = None
    stop_loss = None
    target_price = None
    if blue and blue.details:
        entry_price = blue.details.get("current_price")
        stop_loss = blue.details.get("stop_loss_suggestion")
        target_price = blue.details.get("target_suggestion")

    rationale = _build_rationale(symbol, composite, signal, agent_scores, all_flags)

    return FinalSignal(
        symbol=symbol,
        signal=signal,
        composite_score=round(composite, 1),
        risk_level=risk_level,
        agent_scores=agent_scores,
        rationale=rationale,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_price=target_price,
        position_size_pct=position_pct,
        momentum_rank=momentum_rank,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _build_rationale(
    symbol: str,
    composite: float,
    signal: Signal,
    agent_scores: dict[str, AgentScore],
    flags: list[str],
) -> str:
    lines: list[str] = [
        f"{symbol} — {signal.value} (composite: {composite:.0f}/100)",
        "",
    ]
    for agent, score_obj in agent_scores.items():
        lines.append(f"  {agent}: {score_obj.score:.0f}/100 (confidence {score_obj.confidence:.0%})")

    key_flags = [f for f in flags if f and len(f) > 5][:6]
    if key_flags:
        lines.append("")
        lines.append("Key factors:")
        for f in key_flags:
            lines.append(f"  • {f}")

    return "\n".join(lines)
