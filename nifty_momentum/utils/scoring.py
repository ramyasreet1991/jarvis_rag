"""
Score utilities shared across all agents.
All scores normalised to 0-100 range.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Signal(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    WEAK_BUY = "WEAK_BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    AVOID = "AVOID"     # Red Team block
    ERROR = "ERROR"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


@dataclass
class AgentScore:
    agent: str
    score: float            # 0-100
    confidence: float       # 0-1
    flags: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    blocked: bool = False   # Red Team can hard-block


@dataclass
class FinalSignal:
    symbol: str
    signal: Signal
    composite_score: float
    risk_level: RiskLevel
    agent_scores: dict[str, AgentScore]
    rationale: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    position_size_pct: float = 0.0
    momentum_rank: Optional[int] = None
    timestamp: str = ""


def score_to_signal(score: float, blocked: bool = False) -> Signal:
    if blocked:
        return Signal.AVOID
    if score >= 85:
        return Signal.STRONG_BUY
    if score >= 70:
        return Signal.BUY
    if score >= 50:
        return Signal.WEAK_BUY
    if score >= 35:
        return Signal.HOLD
    return Signal.SELL


def score_to_position_size(score: float, signal: Signal) -> float:
    if signal in (Signal.AVOID, Signal.SELL, Signal.HOLD, Signal.ERROR):
        return 0.0
    if signal == Signal.STRONG_BUY:
        return 7.0
    if signal == Signal.BUY:
        return 4.5
    return 1.5  # WEAK_BUY


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def normalise_to_100(value: float, low: float, high: float) -> float:
    """Linear normalisation — value in [low, high] → [0, 100]."""
    if high == low:
        return 50.0
    return clamp((value - low) / (high - low) * 100)


def score_to_risk(score: float, red_flags: int = 0) -> RiskLevel:
    if red_flags > 0 or score < 35:
        return RiskLevel.VERY_HIGH
    if score < 50:
        return RiskLevel.HIGH
    if score < 70:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW
