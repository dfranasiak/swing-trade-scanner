import datetime as dt
import json
from pathlib import Path

from scanner.data import Fundamentals
from scanner.fundamental_screen import evaluate_fundamentals
from scanner.report import build_artifact, build_result_row, write_json, write_markdown
from scanner.scoring import score_candidate
from scanner.technical_screen import TechnicalResult


def _candidate(ticker="TEST"):
    tech = TechnicalResult(
        ticker=ticker,
        passed=True,
        signal_count=4,
        signals={
            "ema_cross_trend": True,
            "rsi_reset_or_divergence": True,
            "macd_bullish": True,
            "volume_conviction": True,
            "pullback_to_support": False,
        },
        trigger_summary="EMA8/21 cross, vol 1.8x avg",
        last_close=100.0,
        ema8=101.0,
        ema21=99.0,
        ema50=90.0,
        rsi14=52.0,
        volume_ratio=1.8,
        recent_low_20d=88.0,
        recent_high_20d=105.0,
        recent_low_50d=80.0,
    )
    fund = evaluate_fundamentals(
        ticker,
        Fundamentals(
            revenue_growth_yoy=0.14,
            earnings_growth_yoy=0.20,
            earnings_growth_prior_q=0.10,
            margin_history=[0.10, 0.12],
            debt_to_equity=60.0,
            next_earnings_date=dt.date.today() + dt.timedelta(days=30),
            trading_days_to_earnings=20,
        ),
    )
    return score_candidate(tech, fund)


def test_stop_level_is_numeric_not_a_preformatted_string():
    row = build_result_row(_candidate())
    assert isinstance(row["stop_level"], (int, float))
    assert not isinstance(row["stop_level"], str)


def test_write_markdown_does_not_raise_on_real_candidates(tmp_path: Path):
    artifact = build_artifact(
        [_candidate("A"), _candidate("B")],
        run_timestamp=dt.datetime.now(dt.timezone.utc),
        sp500_snapshot_date="2026-08-03",
        sp500_source="wikipedia",
        universe_size=503,
        technical_pass_count=13,
        fundamental_pass_count=5,
    )
    md_path = tmp_path / "scan-latest.md"
    write_markdown(artifact, md_path)
    content = md_path.read_text()
    assert "| A |" in content
    assert "$" in content


def test_write_json_round_trips_and_stop_level_stays_numeric(tmp_path: Path):
    artifact = build_artifact(
        [_candidate()],
        run_timestamp=dt.datetime.now(dt.timezone.utc),
        sp500_snapshot_date="2026-08-03",
        sp500_source="wikipedia",
        universe_size=503,
        technical_pass_count=13,
        fundamental_pass_count=5,
    )
    json_path = tmp_path / "scan-latest.json"
    write_json(artifact, json_path)
    loaded = json.loads(json_path.read_text())
    assert isinstance(loaded["results"][0]["stop_level"], (int, float))
