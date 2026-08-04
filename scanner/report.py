"""Step 4 — Output. Builds the ranked table and writes the JSON artifact
(consumed by the dashboard) and a Markdown report (for history/archival)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .scoring import ScoredCandidate

DISCLAIMER = (
    "Screening tool output only — not investment advice. Setups are "
    "descriptive, not buy/sell recommendations. Verify all data independently "
    "before acting."
)


def _fmt_pct(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else "N/A"


def _fmt_date(value) -> str:
    return value.isoformat() if value else "N/A"


def _fmt_str(value: str | None) -> str:
    return value if value else "N/A"


def _brief_description(summary: str | None, max_len: int = 200, min_len: int = 20) -> str:
    """First sentence of yfinance's longBusinessSummary, verbatim, trimmed to
    a headline length. Never rewrites or paraphrases — just truncates.

    Splitting naively on ". " misfires on abbreviations like "Inc." or
    "Corp." right after the company name, so short leading fragments are
    merged into the next one until the result is long enough to actually be
    a sentence.
    """
    if not summary:
        return "N/A"
    parts = summary.split(". ")
    sentence = parts[0]
    i = 1
    while len(sentence) < min_len and i < len(parts):
        sentence += ". " + parts[i]
        i += 1
    sentence = sentence.strip()
    if not sentence.endswith("."):
        sentence += "."
    if len(sentence) > max_len:
        return sentence[: max_len - 1].rstrip() + "…"
    return sentence


def _entry_stop(candidate: ScoredCandidate) -> tuple[str, float]:
    t = candidate.technical
    entry_low = min(t.ema21, t.last_close)
    entry_high = max(t.ema21, t.last_close)
    entry_zone = f"${entry_low:.2f} - ${entry_high:.2f}"

    stop_level = round(min(t.recent_low_20d, t.ema50) * 0.98, 2)
    return entry_zone, stop_level


def build_result_row(candidate: ScoredCandidate) -> dict:
    entry_zone, stop_level = _entry_stop(candidate)
    f = candidate.fundamental.fundamentals
    return {
        "ticker": candidate.ticker,
        "company_name": _fmt_str(f.company_name),
        "industry": _fmt_str(f.industry),
        "description": _brief_description(f.business_summary),
        "conviction_score": candidate.conviction_score,
        "setup_summary": candidate.why,
        "key_technical_trigger": candidate.technical.trigger_summary,
        "technical_signal_count": candidate.technical.signal_count,
        "revenue_growth_yoy": _fmt_pct(f.revenue_growth_yoy),
        "earnings_growth_yoy": _fmt_pct(f.earnings_growth_yoy),
        "next_earnings_date": _fmt_date(f.next_earnings_date),
        "trading_days_to_earnings": f.trading_days_to_earnings,
        "entry_zone": entry_zone,
        "stop_level": stop_level,
        "last_close": round(candidate.technical.last_close, 2),
        "rsi14": round(candidate.technical.rsi14, 1),
        "volume_ratio": round(candidate.technical.volume_ratio, 2),
    }


def build_artifact(
    candidates: list[ScoredCandidate],
    *,
    run_timestamp: dt.datetime,
    sp500_snapshot_date: str,
    sp500_source: str,
    universe_size: int,
    technical_pass_count: int,
    fundamental_pass_count: int,
) -> dict:
    return {
        "run_timestamp_utc": run_timestamp.isoformat(),
        "sp500_snapshot_date": sp500_snapshot_date,
        "sp500_source": sp500_source,
        "universe_size": universe_size,
        "technical_pass_count": technical_pass_count,
        "fundamental_pass_count": fundamental_pass_count,
        "disclaimer": DISCLAIMER,
        "results": [build_result_row(c) for c in candidates],
    }


def write_json(artifact: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2))


def build_history_rows(artifact: dict) -> list[dict]:
    """One row per ticker that appeared in this run's ranked output, tagged
    with the run's date so it can be appended to the running history log."""
    run_date = artifact["run_timestamp_utc"][:10]
    rows = []
    for r in artifact["results"]:
        row = dict(r)
        row["run_date"] = run_date
        row["run_timestamp_utc"] = artifact["run_timestamp_utc"]
        rows.append(row)
    return rows


def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return loaded if isinstance(loaded, list) else []


def update_history(existing: list[dict], artifact: dict) -> list[dict]:
    """Append this run's rows to the history, replacing any rows already
    recorded for the same run_date (so re-running on the same day doesn't
    produce duplicate entries)."""
    run_date = artifact["run_timestamp_utc"][:10]
    kept = [row for row in existing if row.get("run_date") != run_date]
    updated = kept + build_history_rows(artifact)
    updated.sort(key=lambda row: (row.get("run_date", ""), row.get("conviction_score", 0)), reverse=True)
    return updated


def write_history(history: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2))


def _md_cell(value) -> str:
    """Escape a value for embedding in a Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_markdown(artifact: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Daily Swing Trade Scanner",
        "",
        f"Run: {artifact['run_timestamp_utc']} UTC  ",
        f"S&P 500 snapshot: {artifact['sp500_snapshot_date']} (source: {artifact['sp500_source']})  ",
        f"Universe: {artifact['universe_size']} tickers | "
        f"Technical pass: {artifact['technical_pass_count']} | "
        f"Fundamental pass: {artifact['fundamental_pass_count']}",
        "",
        f"> {artifact['disclaimer']}",
        "",
        "| Ticker | Company | Industry | Description | Score | Setup Summary | Key Trigger | "
        "Rev Growth YoY | Next Earnings | Entry Zone | Stop |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in artifact["results"]:
        lines.append(
            f"| {_md_cell(r['ticker'])} | {_md_cell(r['company_name'])} | {_md_cell(r['industry'])} | "
            f"{_md_cell(r['description'])} | {r['conviction_score']} | {_md_cell(r['setup_summary'])} | "
            f"{_md_cell(r['key_technical_trigger'])} | {r['revenue_growth_yoy']} | "
            f"{r['next_earnings_date']} | {r['entry_zone']} | ${r['stop_level']:.2f} |"
        )
    path.write_text("\n".join(lines) + "\n")
