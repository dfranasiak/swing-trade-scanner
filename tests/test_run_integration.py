"""End-to-end smoke test for scanner.run.main(), with network calls mocked out.

This exercises the whole CLI entrypoint the way `python -m scanner.run` does
in CI, so a NameError/AttributeError anywhere in main()'s wiring (e.g. a
stale reference left over from a rename) fails locally instead of only
surfacing on the scheduled GitHub Actions run.
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from scanner import data, run, universe


def _make_ohlcv(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 120
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    # Random walk with slight upward drift so some tickers plausibly pass the screen.
    steps = rng.normal(loc=0.15, scale=1.5, size=n)
    closes = 50 + np.cumsum(steps)
    closes = np.clip(closes, 5, None)
    volumes = rng.integers(500_000, 2_000_000, size=n).astype(float)
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes * 1.01,
            "Low": closes * 0.99,
            "Close": closes,
            "Volume": volumes,
        },
        index=idx,
    )


@pytest.fixture
def fake_universe(monkeypatch):
    tickers = [f"TST{i}" for i in range(10)]
    monkeypatch.setattr(
        universe,
        "get_sp500_universe",
        lambda: universe.Universe(tickers=tickers, snapshot_date="2026-08-04", source="fallback_csv"),
    )
    return tickers


@pytest.fixture
def fake_price_history(monkeypatch):
    def _fetch(tickers):
        return {t: _make_ohlcv(seed=i) for i, t in enumerate(tickers)}

    monkeypatch.setattr(data, "fetch_price_history", _fetch)


@pytest.fixture
def fake_fundamentals(monkeypatch):
    def _fetch(ticker):
        return data.Fundamentals(
            revenue_growth_yoy=0.12,
            earnings_growth_yoy=0.15,
            earnings_growth_prior_q=0.08,
            margin_history=[0.10, 0.11, 0.12],
            debt_to_equity=70.0,
            next_earnings_date=None,
            trading_days_to_earnings=30,
        )

    monkeypatch.setattr(data, "fetch_fundamentals", _fetch)


def test_main_runs_end_to_end_without_raising(
    tmp_path, monkeypatch, fake_universe, fake_price_history, fake_fundamentals
):
    monkeypatch.setattr(run, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(run, "REPORTS_DIR", tmp_path / "reports")

    exit_code = run.main(["--max-workers", "2"])

    assert exit_code == 0
    json_path = tmp_path / "data" / "scan-latest.json"
    assert json_path.exists()
    artifact = json.loads(json_path.read_text())
    assert artifact["universe_size"] == 10
    assert (tmp_path / "data" / "scan-latest.md").exists()
    today_str = dt.datetime.now(dt.timezone.utc).date().isoformat()
    assert (tmp_path / "reports" / f"scan-{today_str}.md").exists()
