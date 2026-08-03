import numpy as np
import pandas as pd

from scanner.technical_screen import analyze_ticker


def _make_ohlcv(closes, volumes=None):
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = pd.Series(closes, index=idx)
    if volumes is None:
        volumes = [1_000_000] * n
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


def test_bullish_setup_passes_with_multiple_signals():
    # Steady uptrend for 55 sessions, then a pullback, then a bounce that
    # crosses EMA8 back above EMA21 with a volume spike on the final session.
    uptrend = np.linspace(50, 100, 55)
    pullback = np.linspace(100, 84, 12)
    bounce = np.linspace(84, 98, 6)
    closes = np.concatenate([uptrend, pullback, bounce])
    volumes = [1_000_000] * (len(closes) - 1) + [3_000_000]  # spike on last day

    df = _make_ohlcv(closes, volumes)
    result = analyze_ticker("TEST", df)

    assert result is not None
    assert result.signal_count >= 3
    assert result.passed
    assert result.signals["volume_conviction"] is True


def test_downtrend_fails_screen():
    closes = np.linspace(100, 60, 90)
    df = _make_ohlcv(closes)
    result = analyze_ticker("TEST", df)

    assert result is not None
    assert not result.passed
    assert result.signals["ema_cross_trend"] is False


def test_insufficient_history_returns_none():
    closes = np.linspace(50, 60, 20)
    df = _make_ohlcv(closes)
    result = analyze_ticker("TEST", df)
    assert result is None
