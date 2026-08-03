"""Fetches the current S&P 500 constituent list.

The roster is pulled live on every run (never cached to disk / hardcoded)
so the scanner always screens the current index membership.
"""
from __future__ import annotations

import datetime as dt
import io
import logging
from dataclasses import dataclass

import pandas as pd
import requests

logger = logging.getLogger(__name__)

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# Fallback mirror (community-maintained, updated from the same Wikipedia table).
FALLBACK_CSV_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
)

USER_AGENT = "Mozilla/5.0 (compatible; swing-trade-scanner/1.0; +https://github.com/)"


@dataclass
class Universe:
    tickers: list[str]
    snapshot_date: str  # date this roster was fetched, ISO format
    source: str


def _normalize_ticker(raw: str) -> str:
    """Yahoo Finance uses '-' where Wikipedia uses '.' (e.g. BRK.B -> BRK-B)."""
    return raw.strip().upper().replace(".", "-")


def _fetch_from_wikipedia() -> list[str]:
    resp = requests.get(WIKIPEDIA_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(resp.text)
    constituents = tables[0]
    col = "Symbol" if "Symbol" in constituents.columns else constituents.columns[0]
    tickers = [_normalize_ticker(t) for t in constituents[col].tolist()]
    return sorted(set(tickers))


def _fetch_from_fallback() -> list[str]:
    resp = requests.get(FALLBACK_CSV_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    col = "Symbol" if "Symbol" in df.columns else df.columns[0]
    tickers = [_normalize_ticker(t) for t in df[col].tolist()]
    return sorted(set(tickers))


def get_sp500_universe() -> Universe:
    """Fetch the current S&P 500 roster from a live source.

    Tries Wikipedia first, falls back to a secondary live mirror if that
    fails. Raises if neither source is reachable — this is a hard
    dependency, not something we silently skip.
    """
    snapshot_date = dt.date.today().isoformat()
    try:
        tickers = _fetch_from_wikipedia()
        return Universe(tickers=tickers, snapshot_date=snapshot_date, source="wikipedia")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Wikipedia S&P 500 fetch failed (%s), trying fallback source", exc)

    tickers = _fetch_from_fallback()
    return Universe(tickers=tickers, snapshot_date=snapshot_date, source="fallback_csv")
