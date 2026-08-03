"""Step 3 — Conviction score (0-100): 60% technical alignment strength,
40% fundamental quality."""
from __future__ import annotations

from dataclasses import dataclass

from .fundamental_screen import FundamentalResult
from .technical_screen import TechnicalResult

TECHNICAL_WEIGHT = 0.60
FUNDAMENTAL_WEIGHT = 0.40


@dataclass
class ScoredCandidate:
    ticker: str
    conviction_score: float
    technical: TechnicalResult
    fundamental: FundamentalResult
    why: str


def _technical_strength(tech: TechnicalResult) -> float:
    """0-100. Base score from how many of the 5 signals fired, plus a small
    bonus for signal *strength* (volume magnitude, RSI centering)."""
    base = (tech.signal_count / 5) * 100

    bonus = 0.0
    if tech.signals.get("volume_conviction"):
        # extra credit for a stronger-than-minimum volume spike, capped
        bonus += min((tech.volume_ratio - VOLUME_MULTIPLIER_BASELINE) * 10, 10)
    if tech.signals.get("rsi_reset_or_divergence") and 45 <= tech.rsi14 <= 55:
        bonus += 5  # centered RSI reset is the cleanest version of this signal

    return max(0.0, min(100.0, base + bonus))


VOLUME_MULTIPLIER_BASELINE = 1.3


def _fundamental_strength(fund: FundamentalResult) -> float:
    """0-100 composite of revenue growth magnitude, earnings growth,
    margin trend, and debt quality."""
    f = fund.fundamentals
    score = 0.0

    # Revenue growth: up to 40 pts, scaled so 20%+ YoY maxes it out.
    if f.revenue_growth_yoy is not None:
        score += max(0.0, min(f.revenue_growth_yoy / 0.20, 1.0)) * 40

    # Earnings growth: up to 25 pts.
    if fund.checks.get("earnings_growth") is True:
        score += 25
    elif fund.checks.get("earnings_growth") is None:
        score += 12.5  # neutral / unknown

    # Margin trend: up to 20 pts.
    if fund.checks.get("margin_trend") is True:
        score += 20
    elif fund.checks.get("margin_trend") is None:
        score += 10

    # Debt quality: up to 15 pts.
    if fund.checks.get("debt_not_deteriorating") is True:
        score += 15
    elif fund.checks.get("debt_not_deteriorating") is None:
        score += 7.5

    return max(0.0, min(100.0, score))


def score_candidate(tech: TechnicalResult, fund: FundamentalResult) -> ScoredCandidate:
    tscore = _technical_strength(tech)
    fscore = _fundamental_strength(fund)
    conviction = round(TECHNICAL_WEIGHT * tscore + FUNDAMENTAL_WEIGHT * fscore, 1)

    why = f"{tech.trigger_summary}; {fund.why}"
    return ScoredCandidate(
        ticker=tech.ticker,
        conviction_score=conviction,
        technical=tech,
        fundamental=fund,
        why=why,
    )


def rank_candidates(candidates: list[ScoredCandidate], top_n: int = 20) -> list[ScoredCandidate]:
    return sorted(candidates, key=lambda c: c.conviction_score, reverse=True)[:top_n]
