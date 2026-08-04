"""CLI entrypoint: orchestrates the full daily scan end-to-end.

    python -m scanner.run [--limit N] [--top-n N] [--max-workers N]

Recomputes everything from current data on every run — no cached
conclusions are carried over between days.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import data, fundamental_screen, report, scoring, technical_screen, universe

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("scanner.run")

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
REPORTS_DIR = REPO_ROOT / "reports"


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Daily swing trade scanner")
    p.add_argument("--limit", type=int, default=None, help="Limit universe size (testing)")
    p.add_argument("--top-n", type=int, default=20, help="Max names in final ranked output")
    p.add_argument(
        "--max-workers", type=int, default=8, help="Parallel workers for fundamentals fetch"
    )
    return p.parse_args(argv)


def fetch_fundamentals_concurrent(tickers: list[str], max_workers: int) -> dict[str, data.Fundamentals]:
    results: dict[str, data.Fundamentals] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(data.fetch_fundamentals, t): t for t in tickers}
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                results[ticker] = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s: fundamentals fetch failed (%s)", ticker, exc)
                results[ticker] = data.Fundamentals()
    return results


def main(argv=None) -> int:
    args = parse_args(argv)
    run_started = dt.datetime.now(dt.timezone.utc)

    logger.info("Fetching current S&P 500 universe...")
    uni = universe.get_sp500_universe()
    tickers = uni.tickers[: args.limit] if args.limit else uni.tickers
    logger.info(
        "Universe: %d tickers (source=%s, snapshot=%s)", len(tickers), uni.source, uni.snapshot_date
    )

    logger.info("Downloading price history...")
    price_data = data.fetch_price_history(tickers)

    logger.info("Running technical screen (Step 1)...")
    tech_results = technical_screen.run_technical_screen(price_data)
    tech_passers = [r for r in tech_results if r.passed]
    logger.info("Technical screen: %d/%d passed", len(tech_passers), len(tech_results))

    logger.info("Fetching fundamentals for technical passers...")
    fundamentals_map = fetch_fundamentals_concurrent(
        [r.ticker for r in tech_passers], args.max_workers
    )

    logger.info("Running fundamental screen (Step 2)...")
    candidates = []
    fundamental_pass_count = 0
    for tech in tech_passers:
        fund = fundamental_screen.evaluate_fundamentals(tech.ticker, fundamentals_map[tech.ticker])
        if fund.passed:
            fundamental_pass_count += 1
            candidates.append(scoring.score_candidate(tech, fund))

    logger.info("Fundamental screen: %d passed", fundamental_pass_count)

    logger.info("Scoring and ranking (Step 3)...")
    ranked = scoring.rank_candidates(candidates, top_n=args.top_n)

    logger.info("Building output artifacts (Step 4)...")
    artifact = report.build_artifact(
        ranked,
        run_timestamp=run_started,
        sp500_snapshot_date=uni.snapshot_date,
        sp500_source=uni.source,
        universe_size=len(tickers),
        technical_pass_count=len(tech_passers),
        fundamental_pass_count=fundamental_pass_count,
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    report.write_json(artifact, DATA_DIR / "scan-latest.json")
    report.write_markdown(artifact, DATA_DIR / "scan-latest.md")
    date_str = run_started.date().isoformat()
    report.write_markdown(artifact, REPORTS_DIR / f"scan-{date_str}.md")

    history_path = DATA_DIR / "history.json"
    history = report.load_history(history_path)
    history = report.update_history(history, artifact)
    report.write_history(history, history_path)

    elapsed = time.time() - run_started.timestamp()
    logger.info(
        "Done in %.1fs. %d names in final ranked output. Wrote %s",
        elapsed,
        len(ranked),
        DATA_DIR / "scan-latest.json",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
