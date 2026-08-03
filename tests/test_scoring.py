from scanner.data import Fundamentals
from scanner.fundamental_screen import evaluate_fundamentals
from scanner.scoring import rank_candidates, score_candidate
from scanner.technical_screen import TechnicalResult


def _tech(signal_count, signals=None, volume_ratio=1.5, rsi14=50.0, ticker="TEST"):
    default_signals = {
        "ema_cross_trend": True,
        "rsi_reset_or_divergence": True,
        "macd_bullish": True,
        "volume_conviction": True,
        "pullback_to_support": False,
    }
    if signals:
        default_signals.update(signals)
    return TechnicalResult(
        ticker=ticker,
        passed=signal_count >= 3,
        signal_count=signal_count,
        signals=default_signals,
        trigger_summary="EMA8/21 cross, vol 1.5x avg",
        last_close=100.0,
        ema8=101.0,
        ema21=99.0,
        ema50=95.0,
        rsi14=rsi14,
        volume_ratio=volume_ratio,
        recent_low_20d=90.0,
        recent_high_20d=105.0,
        recent_low_50d=85.0,
    )


def test_score_is_between_0_and_100():
    tech = _tech(4)
    fund = evaluate_fundamentals(
        "TEST",
        Fundamentals(revenue_growth_yoy=0.15, earnings_growth_yoy=0.20, margin_history=[0.1, 0.12]),
    )
    candidate = score_candidate(tech, fund)
    assert 0 <= candidate.conviction_score <= 100


def test_stronger_setup_scores_higher():
    strong = score_candidate(
        _tech(5, volume_ratio=2.0, rsi14=50.0),
        evaluate_fundamentals(
            "STRONG",
            Fundamentals(revenue_growth_yoy=0.25, earnings_growth_yoy=0.30, earnings_growth_prior_q=0.10,
                         margin_history=[0.10, 0.15], debt_to_equity=40.0),
        ),
    )
    weak = score_candidate(
        _tech(3, volume_ratio=1.3, rsi14=58.0),
        evaluate_fundamentals(
            "WEAK",
            Fundamentals(revenue_growth_yoy=0.09),
        ),
    )
    assert strong.conviction_score > weak.conviction_score


def test_rank_candidates_sorts_descending_and_truncates():
    candidates = [
        score_candidate(_tech(3, ticker="A"), evaluate_fundamentals("A", Fundamentals(revenue_growth_yoy=0.09))),
        score_candidate(_tech(5, ticker="B"), evaluate_fundamentals("B", Fundamentals(revenue_growth_yoy=0.20))),
        score_candidate(_tech(4, ticker="C"), evaluate_fundamentals("C", Fundamentals(revenue_growth_yoy=0.15))),
    ]
    ranked = rank_candidates(candidates, top_n=2)
    assert len(ranked) == 2
    assert ranked[0].conviction_score >= ranked[1].conviction_score
    assert ranked[0].ticker == "B"
