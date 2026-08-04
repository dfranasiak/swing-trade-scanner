"""Market data access layer built on yfinance (free Yahoo Finance API)."""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

OHLCV_LOOKBACK_DAYS = "150d"  # buffer beyond the 100 trading days we ultimately analyze
TRADING_DAYS_WINDOW = 100


@dataclass
class Fundamentals:
    revenue_growth_yoy: float | None = None  # fraction, e.g. 0.14 == 14%
    earnings_growth_yoy: float | None = None
    earnings_growth_prior_q: float | None = None  # prior quarter's YoY EPS growth, for "accelerating" check
    gross_margin: float | None = None
    operating_margin: float | None = None
    margin_history: list[float] = field(default_factory=list)  # operating margin, oldest->newest, up to 4 quarters
    debt_to_equity: float | None = None
    next_earnings_date: dt.date | None = None
    trading_days_to_earnings: int | None = None
    company_name: str | None = None
    industry: str | None = None
    business_summary: str | None = None  # yfinance's longBusinessSummary, verbatim (untrimmed)


def fetch_price_history(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Batch-download daily OHLCV for all tickers. Returns {ticker: DataFrame}.

    Tickers that fail to download or come back with insufficient history are
    omitted rather than raising, since a single bad symbol shouldn't kill a
    500-ticker run.
    """
    logger.info("Downloading OHLCV for %d tickers", len(tickers))
    raw = yf.download(
        tickers,
        period=OHLCV_LOOKBACK_DAYS,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False,
    )

    result: dict[str, pd.DataFrame] = {}
    single = len(tickers) == 1
    for ticker in tickers:
        try:
            df = raw if single else raw[ticker]
        except KeyError:
            continue
        df = df.dropna(how="all")
        if df.empty or len(df) < 55:  # need enough bars for EMA50 to be meaningful
            continue
        result[ticker] = df
    logger.info("Got usable OHLCV for %d/%d tickers", len(result), len(tickers))
    return result


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        f = float(value)
        if f != f:  # NaN check
            return None
        return f
    except (TypeError, ValueError):
        return None


def fetch_fundamentals(ticker: str) -> Fundamentals:
    """Best-effort fundamentals pull for a single ticker.

    yfinance fundamentals coverage is inconsistent across tickers; any field
    that can't be retrieved is left as None and surfaced as "N/A" downstream
    rather than estimated.
    """
    t = yf.Ticker(ticker)
    result = Fundamentals()

    try:
        info = t.get_info()
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: info fetch failed (%s)", ticker, exc)
        info = {}

    result.revenue_growth_yoy = _safe_float(info.get("revenueGrowth"))
    result.earnings_growth_yoy = _safe_float(info.get("earningsGrowth"))
    result.gross_margin = _safe_float(info.get("grossMargins"))
    result.operating_margin = _safe_float(info.get("operatingMargins"))
    result.debt_to_equity = _safe_float(info.get("debtToEquity"))
    result.company_name = info.get("longName") or info.get("shortName") or None
    result.industry = info.get("industry") or None
    result.business_summary = info.get("longBusinessSummary") or None

    # Quarterly operating-margin trend (up to last 4 quarters, oldest -> newest)
    try:
        qfin = t.quarterly_financials
        if qfin is not None and not qfin.empty:
            revenue_row = next((r for r in ("Total Revenue", "TotalRevenue") if r in qfin.index), None)
            opinc_row = next(
                (r for r in ("Operating Income", "OperatingIncome") if r in qfin.index), None
            )
            if revenue_row and opinc_row:
                cols = list(qfin.columns[:4])[::-1]  # oldest->newest of the 4 most recent
                margins = []
                for c in cols:
                    rev = _safe_float(qfin.loc[revenue_row, c])
                    opinc = _safe_float(qfin.loc[opinc_row, c])
                    if rev and rev != 0 and opinc is not None:
                        margins.append(opinc / rev)
                result.margin_history = margins
    except Exception as exc:  # noqa: BLE001
        logger.debug("%s: quarterly financials fetch failed (%s)", ticker, exc)

    # Prior-quarter EPS growth (to check earnings growth is *accelerating*), from
    # quarterly net income YoY. `Ticker.quarterly_earnings` is deprecated by
    # yfinance and no longer populated, so this is derived from the income
    # statement instead.
    try:
        qfin = t.quarterly_income_stmt
        if qfin is not None and not qfin.empty:
            income_row = next(
                (r for r in ("Net Income", "NetIncome") if r in qfin.index), None
            )
            if income_row and len(qfin.columns) >= 6:
                cols = list(qfin.columns[:6])  # newest -> oldest
                prior_recent = _safe_float(qfin.loc[income_row, cols[1]])
                prior_year_ago = _safe_float(qfin.loc[income_row, cols[5]])
                if prior_recent is not None and prior_year_ago:
                    result.earnings_growth_prior_q = (prior_recent - prior_year_ago) / abs(prior_year_ago)
    except Exception as exc:  # noqa: BLE001
        logger.debug("%s: quarterly income stmt fetch failed (%s)", ticker, exc)

    # Next earnings date
    try:
        edates = t.get_earnings_dates(limit=6)
        if edates is not None and not edates.empty:
            today = pd.Timestamp.now(tz=edates.index.tz) if edates.index.tz else pd.Timestamp.now()
            future = edates[edates.index >= today]
            if not future.empty:
                next_date = future.index.min()
                result.next_earnings_date = next_date.date()
                result.trading_days_to_earnings = _trading_days_between(dt.date.today(), next_date.date())
    except Exception as exc:  # noqa: BLE001
        logger.debug("%s: earnings dates fetch failed (%s)", ticker, exc)

    return result


def _trading_days_between(start: dt.date, end: dt.date) -> int:
    """Approximate count of weekday (trading) sessions between two dates."""
    if end <= start:
        return 0
    days = pd.bdate_range(start, end)
    return max(len(days) - 1, 0)
