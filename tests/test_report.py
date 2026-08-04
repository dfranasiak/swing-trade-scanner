import datetime as dt
import json
from pathlib import Path

from scanner.data import Fundamentals
from scanner.fundamental_screen import evaluate_fundamentals
from scanner.report import (
    build_artifact,
    build_result_row,
    load_history,
    update_history,
    write_history,
    write_json,
    write_markdown,
)
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
            company_name="Test Corp",
            industry="Software - Application",
            business_summary="Test Corp designs and sells widgets. It also does other things.",
        ),
    )
    return score_candidate(tech, fund)


def test_stop_level_is_numeric_not_a_preformatted_string():
    row = build_result_row(_candidate())
    assert isinstance(row["stop_level"], (int, float))
    assert not isinstance(row["stop_level"], str)


def test_result_row_includes_company_name_industry_and_description():
    row = build_result_row(_candidate())
    assert row["company_name"] == "Test Corp"
    assert row["industry"] == "Software - Application"
    assert row["description"] == "Test Corp designs and sells widgets."


def test_result_row_missing_company_fields_are_na():
    tech = _candidate().technical
    fund = evaluate_fundamentals("TEST", Fundamentals(revenue_growth_yoy=0.14))
    from scanner.scoring import score_candidate as _score

    row = build_result_row(_score(tech, fund))
    assert row["company_name"] == "N/A"
    assert row["industry"] == "N/A"
    assert row["description"] == "N/A"


def test_brief_description_truncates_long_first_sentence():
    from scanner.report import _brief_description


def test_brief_description_does_not_split_on_company_suffix_abbreviations():
    from scanner.report import _brief_description

    summary = (
        "Broadcom Inc. designs, develops, and supplies various semiconductor "
        "and infrastructure software products worldwide. It operates in two "
        "segments."
    )
    result = _brief_description(summary)
    assert result != "Broadcom Inc."
    assert result.startswith("Broadcom Inc. designs, develops")
    assert "supplies various semiconductor" in result

    long_sentence = "A " + "very " * 60 + "long company description without a period"
    result = _brief_description(long_sentence, max_len=50)
    assert len(result) <= 50
    assert result.endswith("…")


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


def _artifact(tickers, run_timestamp):
    return build_artifact(
        [_candidate(t) for t in tickers],
        run_timestamp=run_timestamp,
        sp500_snapshot_date=run_timestamp.date().isoformat(),
        sp500_source="wikipedia",
        universe_size=503,
        technical_pass_count=13,
        fundamental_pass_count=len(tickers),
    )


def test_load_history_missing_file_returns_empty_list(tmp_path: Path):
    assert load_history(tmp_path / "nope.json") == []


def test_load_history_corrupt_file_returns_empty_list(tmp_path: Path):
    path = tmp_path / "history.json"
    path.write_text("{not valid json")
    assert load_history(path) == []


def test_update_history_appends_rows_tagged_with_run_date():
    day1 = dt.datetime(2026, 8, 3, 12, 0, tzinfo=dt.timezone.utc)
    artifact = _artifact(["A", "B"], day1)
    history = update_history([], artifact)
    assert len(history) == 2
    assert {row["ticker"] for row in history} == {"A", "B"}
    assert all(row["run_date"] == "2026-08-03" for row in history)


def test_update_history_accumulates_across_multiple_days():
    day1 = dt.datetime(2026, 8, 3, 12, 0, tzinfo=dt.timezone.utc)
    day2 = dt.datetime(2026, 8, 4, 12, 0, tzinfo=dt.timezone.utc)
    history = update_history([], _artifact(["A"], day1))
    history = update_history(history, _artifact(["B"], day2))
    assert len(history) == 2
    dates = {row["run_date"] for row in history}
    assert dates == {"2026-08-03", "2026-08-04"}


def test_update_history_rerun_same_day_replaces_not_duplicates():
    day1 = dt.datetime(2026, 8, 3, 12, 0, tzinfo=dt.timezone.utc)
    day1_rerun = dt.datetime(2026, 8, 3, 18, 0, tzinfo=dt.timezone.utc)
    history = update_history([], _artifact(["A", "B"], day1))
    history = update_history(history, _artifact(["A"], day1_rerun))
    # second run for the same day only found "A" -> "B" should be dropped, not duplicated
    assert len(history) == 1
    assert history[0]["ticker"] == "A"
    assert history[0]["run_timestamp_utc"] == day1_rerun.isoformat()


def test_write_and_load_history_round_trips(tmp_path: Path):
    path = tmp_path / "history.json"
    day1 = dt.datetime(2026, 8, 3, 12, 0, tzinfo=dt.timezone.utc)
    history = update_history([], _artifact(["A"], day1))
    write_history(history, path)
    reloaded = load_history(path)
    assert reloaded == history
