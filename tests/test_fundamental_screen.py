import datetime as dt

from scanner.data import Fundamentals
from scanner.fundamental_screen import evaluate_fundamentals


def test_strong_fundamentals_pass():
    f = Fundamentals(
        revenue_growth_yoy=0.15,
        earnings_growth_yoy=0.20,
        earnings_growth_prior_q=0.10,
        margin_history=[0.18, 0.19, 0.20, 0.21],
        debt_to_equity=80.0,
        next_earnings_date=dt.date.today() + dt.timedelta(days=30),
        trading_days_to_earnings=20,
    )
    result = evaluate_fundamentals("TEST", f)
    assert result.revenue_growth_ok
    assert not result.excluded_earnings_soon
    assert result.passed


def test_negative_revenue_growth_fails_even_with_other_strong_metrics():
    f = Fundamentals(
        revenue_growth_yoy=-0.05,
        earnings_growth_yoy=0.20,
        earnings_growth_prior_q=0.10,
        margin_history=[0.18, 0.20],
        debt_to_equity=50.0,
    )
    result = evaluate_fundamentals("TEST", f)
    assert not result.passed
    assert not result.revenue_growth_ok


def test_earnings_within_blackout_window_excludes():
    f = Fundamentals(
        revenue_growth_yoy=0.15,
        earnings_growth_yoy=0.10,
        margin_history=[0.18, 0.20],
        debt_to_equity=50.0,
        trading_days_to_earnings=2,
    )
    result = evaluate_fundamentals("TEST", f)
    assert result.excluded_earnings_soon
    assert not result.passed


def test_missing_fields_marked_neutral_not_fabricated():
    f = Fundamentals(revenue_growth_yoy=0.12)
    result = evaluate_fundamentals("TEST", f)
    # unknown secondary checks should be None (N/A), not guessed True/False
    assert result.checks["earnings_growth"] is None
    assert result.checks["margin_trend"] is None
    assert result.checks["debt_not_deteriorating"] is None
    # None is neutral, not negative -> still counts toward "neutral-or-better"
    assert result.passed


def test_confirmed_deteriorating_metrics_fail_the_secondary_bar():
    f = Fundamentals(
        revenue_growth_yoy=0.12,
        earnings_growth_yoy=-0.10,  # confirmed False
        earnings_growth_prior_q=0.05,
        margin_history=[0.20, 0.15],  # confirmed declining -> False
        debt_to_equity=None,  # unknown -> neutral
    )
    result = evaluate_fundamentals("TEST", f)
    assert result.checks["earnings_growth"] is False
    assert result.checks["margin_trend"] is False
    # only 1 of 3 (debt=None/neutral) counts -> fails the >=2 bar
    assert not result.passed
