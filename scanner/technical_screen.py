"""Step 1 — Technical screen (entry timing).

For each ticker, computes EMA8/21/50, RSI(14), MACD(12,26,9), a volume
conviction check, and a pullback-to-support check. A ticker passes when at
least 3 of the 5 signals are bullish.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .indicators import ema, macd, rsi, sma

TRADING_DAYS_WINDOW = 100
CROSS_LOOKBACK = 3  # "in the last 1-3 sessions"
RSI_LOW, RSI_HIGH = 40, 60
RSI_OVERSOLD = 30
VOLUME_MULTIPLIER = 1.3
PULLBACK_BAND = 0.03  # within 3% of the 20/50-day SMA counts as "at support"


@dataclass
class TechnicalResult:
    ticker: str
    passed: bool
    signal_count: int
    signals: dict[str, bool]
    trigger_summary: str
    last_close: float
    ema8: float
    ema21: float
    ema50: float
    rsi14: float
    volume_ratio: float
    recent_low_20d: float
    recent_high_20d: float
    recent_low_50d: float


def _crossed_above(fast: pd.Series, slow: pd.Series, lookback: int) -> bool:
    diff = fast - slow
    recent = diff.tail(lookback + 1)
    if len(recent) < 2:
        return False
    # True if diff was <= 0 at some point in the window and is > 0 now.
    return bool((recent.iloc[:-1] <= 0).any() and recent.iloc[-1] > 0)


def _bullish_divergence(close: pd.Series, rsi_series: pd.Series, lookback: int = 15) -> bool:
    """Rough bullish divergence: price makes a lower low while RSI makes a higher low,
    following an oversold reading."""
    window_close = close.tail(lookback)
    window_rsi = rsi_series.tail(lookback)
    if len(window_close) < lookback or window_rsi.min() >= RSI_OVERSOLD:
        return False
    mid = lookback // 2
    first_close_min = window_close.iloc[:mid].min()
    second_close_min = window_close.iloc[mid:].min()
    first_rsi_min = window_rsi.iloc[:mid].min()
    second_rsi_min = window_rsi.iloc[mid:].min()
    return bool(second_close_min < first_close_min and second_rsi_min > first_rsi_min)


def analyze_ticker(ticker: str, df: pd.DataFrame) -> TechnicalResult | None:
    df = df.tail(TRADING_DAYS_WINDOW + 60) if len(df) > TRADING_DAYS_WINDOW + 60 else df
    close = df["Close"].dropna()
    volume = df["Volume"].dropna()
    if len(close) < 55:
        return None

    ema8_s = ema(close, 8)
    ema21_s = ema(close, 21)
    ema50_s = ema(close, 50)
    rsi_s = rsi(close, 14)
    macd_line, signal_line, hist = macd(close)
    sma20 = sma(close, 20)
    sma50 = sma(close, 50)

    window_close = close.tail(TRADING_DAYS_WINDOW)
    window_volume = volume.tail(TRADING_DAYS_WINDOW)

    last_close = float(close.iloc[-1])
    last_ema8, last_ema21, last_ema50 = float(ema8_s.iloc[-1]), float(ema21_s.iloc[-1]), float(ema50_s.iloc[-1])
    last_rsi = float(rsi_s.iloc[-1])

    # Signal 1: EMA8/21 bullish cross within lookback + EMA21 > EMA50 trend alignment
    ema_cross = _crossed_above(ema8_s, ema21_s, CROSS_LOOKBACK)
    trend_aligned = last_ema21 > last_ema50
    sig_ema = ema_cross and trend_aligned

    # Signal 2: RSI reset zone, or bullish divergence off oversold
    sig_rsi_reset = RSI_LOW <= last_rsi <= RSI_HIGH
    sig_rsi_divergence = _bullish_divergence(close, rsi_s)
    sig_rsi = sig_rsi_reset or sig_rsi_divergence

    # Signal 3: MACD bullish signal-line cross, or histogram turning positive, within lookback
    macd_cross = _crossed_above(macd_line, signal_line, CROSS_LOOKBACK)
    hist_recent = hist.tail(CROSS_LOOKBACK + 1)
    hist_turned_positive = bool((hist_recent.iloc[:-1] <= 0).any() and hist_recent.iloc[-1] > 0)
    sig_macd = macd_cross or hist_turned_positive

    # Signal 4: volume conviction — last session vs. prior 20-day average (excludes today)
    avg_vol_20 = float(volume.iloc[-21:-1].mean()) if len(volume) >= 21 else float(volume.mean())
    last_vol = float(volume.iloc[-1])
    volume_ratio = (last_vol / avg_vol_20) if avg_vol_20 else 0.0
    sig_volume = volume_ratio >= VOLUME_MULTIPLIER

    # Signal 5: pullback to support (near rising 20d/50d SMA), not a breakdown
    last_sma20, last_sma50 = float(sma20.iloc[-1]), float(sma50.iloc[-1])
    sma20_rising = last_sma20 > float(sma20.iloc[-6]) if len(sma20.dropna()) > 6 else False
    sma50_rising = last_sma50 > float(sma50.iloc[-6]) if len(sma50.dropna()) > 6 else False
    near_20 = sma20_rising and abs(last_close - last_sma20) / last_sma20 <= PULLBACK_BAND
    near_50 = sma50_rising and abs(last_close - last_sma50) / last_sma50 <= PULLBACK_BAND
    low_20d = float(window_close.tail(20).min())
    not_breakdown = last_close > low_20d * 0.995  # not printing a fresh 20-day low
    sig_pullback = (near_20 or near_50) and not_breakdown

    signals = {
        "ema_cross_trend": sig_ema,
        "rsi_reset_or_divergence": sig_rsi,
        "macd_bullish": sig_macd,
        "volume_conviction": sig_volume,
        "pullback_to_support": sig_pullback,
    }
    signal_count = sum(signals.values())
    passed = signal_count >= 3

    trigger_parts = []
    if sig_ema:
        trigger_parts.append("EMA8/21 cross" + (" + trend up" if trend_aligned else ""))
    if sig_rsi_reset:
        trigger_parts.append(f"RSI {last_rsi:.0f} reset")
    elif sig_rsi_divergence:
        trigger_parts.append("bullish RSI divergence")
    if macd_cross:
        trigger_parts.append("MACD cross")
    elif hist_turned_positive:
        trigger_parts.append("MACD hist turning +")
    if sig_volume:
        trigger_parts.append(f"vol {volume_ratio:.1f}x avg")
    if sig_pullback:
        trigger_parts.append("pullback to support")
    trigger_summary = ", ".join(trigger_parts) if trigger_parts else "no bullish triggers"

    return TechnicalResult(
        ticker=ticker,
        passed=passed,
        signal_count=signal_count,
        signals=signals,
        trigger_summary=trigger_summary,
        last_close=last_close,
        ema8=last_ema8,
        ema21=last_ema21,
        ema50=last_ema50,
        rsi14=last_rsi,
        volume_ratio=volume_ratio,
        recent_low_20d=low_20d,
        recent_high_20d=float(window_close.tail(20).max()),
        recent_low_50d=float(window_close.tail(50).min()) if len(window_close) >= 50 else low_20d,
    )


def run_technical_screen(price_data: dict[str, pd.DataFrame]) -> list[TechnicalResult]:
    results = []
    for ticker, df in price_data.items():
        try:
            r = analyze_ticker(ticker, df)
        except Exception:  # noqa: BLE001
            r = None
        if r is not None:
            results.append(r)
    return results
