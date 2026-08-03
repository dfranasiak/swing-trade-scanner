import numpy as np
import pandas as pd

from scanner.indicators import ema, macd, rsi, sma


def _series(values):
    return pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="B"))


def test_ema_converges_toward_recent_prices():
    s = _series([10] * 30 + [20] * 30)
    result = ema(s, 8)
    assert result.iloc[-1] > 19  # should have mostly caught up to the new level


def test_rsi_pegs_high_on_pure_uptrend():
    s = _series(list(range(1, 40)))
    result = rsi(s, 14)
    assert result.iloc[-1] > 90


def test_rsi_pegs_low_on_pure_downtrend():
    s = _series(list(range(40, 1, -1)))
    result = rsi(s, 14)
    assert result.iloc[-1] < 10


def test_macd_returns_three_series_same_length():
    s = _series(np.linspace(10, 30, 60).tolist())
    macd_line, signal_line, hist = macd(s)
    assert len(macd_line) == len(signal_line) == len(hist) == len(s)
    np.testing.assert_allclose((macd_line - signal_line).values, hist.values, atol=1e-9)


def test_sma_basic():
    s = _series([1, 2, 3, 4, 5])
    result = sma(s, 2)
    assert result.iloc[-1] == 4.5
