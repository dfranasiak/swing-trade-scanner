"""Step 2 — Fundamental screen (quality filter).

Applied only to tickers that already passed the technical screen. Revenue
growth positive is mandatory; at least 2 of the remaining 3 checks
(earnings growth, margin trend, debt) must be neutral-or-better. Tickers
reporting earnings within the next 5 trading days are excluded outright.
"""
from __future__ import annotations

from dataclasses import dataclass

from .data import Fundamentals

MIN_REVENUE_GROWTH = 0.08  # 8% YoY
EARNINGS_BLACKOUT_TRADING_DAYS = 5
MARGIN_DECLINE_TOLERANCE = -0.01  # allow up to 1pt of margin compression and still call it "stable"
MAX_DEBT_TO_EQUITY = 200.0  # yfinance debtToEquity is expressed as a percentage-like ratio


@dataclass
class FundamentalResult:
    ticker: str
    passed: bool
    excluded_earnings_soon: bool
    revenue_growth_ok: bool
    checks: dict[str, bool | None]
    fundamentals: Fundamentals
    why: str


def _margin_trend_ok(history: list[float]) -> bool | None:
    if len(history) < 2:
        return None
    delta = history[-1] - history[0]
    return delta >= MARGIN_DECLINE_TOLERANCE


def _debt_ok(debt_to_equity: float | None) -> bool | None:
    if debt_to_equity is None:
        return None
    return debt_to_equity <= MAX_DEBT_TO_EQUITY


def _earnings_growth_ok(current: float | None, prior: float | None) -> bool | None:
    if current is None:
        return None
    positive = current > 0
    if prior is None:
        return positive
    accelerating = current >= prior
    return positive and accelerating


def evaluate_fundamentals(ticker: str, fundamentals: Fundamentals) -> FundamentalResult:
    excluded_earnings_soon = (
        fundamentals.trading_days_to_earnings is not None
        and 0 <= fundamentals.trading_days_to_earnings <= EARNINGS_BLACKOUT_TRADING_DAYS
    )

    revenue_growth_ok = (
        fundamentals.revenue_growth_yoy is not None
        and fundamentals.revenue_growth_yoy > MIN_REVENUE_GROWTH
    )

    earnings_ok = _earnings_growth_ok(
        fundamentals.earnings_growth_yoy, fundamentals.earnings_growth_prior_q
    )
    margin_ok = _margin_trend_ok(fundamentals.margin_history)
    debt_ok = _debt_ok(fundamentals.debt_to_equity)

    checks = {
        "earnings_growth": earnings_ok,
        "margin_trend": margin_ok,
        "debt_not_deteriorating": debt_ok,
    }
    # Spec: secondary checks must be "neutral-or-better". A missing data point
    # (None) is neutral by definition — we never fabricate a value for it, but
    # it also isn't negative evidence, so it counts toward the pass count.
    # Only an explicit False (confirmed deterioration) counts against it.
    secondary_pass_count = sum(1 for v in checks.values() if v is not False)
    passed = (
        revenue_growth_ok
        and not excluded_earnings_soon
        and secondary_pass_count >= 2
    )

    why_parts = []
    if fundamentals.revenue_growth_yoy is not None:
        why_parts.append(f"rev growth {fundamentals.revenue_growth_yoy * 100:.1f}% YoY")
    else:
        why_parts.append("rev growth N/A")
    if earnings_ok:
        why_parts.append("EPS growth accelerating")
    if margin_ok:
        why_parts.append("margins stable/expanding")
    if debt_ok:
        why_parts.append("debt not deteriorating")
    if excluded_earnings_soon:
        why_parts.append(f"EXCLUDED: earnings in {fundamentals.trading_days_to_earnings}d")

    return FundamentalResult(
        ticker=ticker,
        passed=passed,
        excluded_earnings_soon=excluded_earnings_soon,
        revenue_growth_ok=revenue_growth_ok,
        checks=checks,
        fundamentals=fundamentals,
        why=", ".join(why_parts),
    )
