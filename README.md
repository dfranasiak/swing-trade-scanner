# Swing Trade Scanner

A daily S&P 500 swing-trade screener. Every trading morning it recomputes,
from scratch, a ranked watchlist of names showing bullish technical setups
backed by decent fundamentals — no cached conclusions carried over between
runs.

**This is a screening tool, not investment advice.** Output is descriptive
(setup summaries, technical triggers, entry/stop levels derived from price
structure) — never a buy/sell directive.

## How it works

1. **Universe** — pulls the current S&P 500 constituent list live from
   Wikipedia (falls back to a secondary live mirror if that's unreachable).
   Never uses a static/cached roster.
2. **Step 1 — Technical screen** (`scanner/technical_screen.py`): for each
   ticker, pulls ~100 trading days of daily OHLCV via `yfinance` and checks
   5 bullish signals — EMA8/21 cross with EMA21>EMA50 trend alignment,
   RSI(14) in the 40–60 reset zone (or bullish divergence off oversold),
   MACD(12,26,9) bullish cross or histogram turning positive, volume ≥1.3x
   the 20-day average, and a pullback to rising 20/50-day support (not a
   breakdown). A ticker needs **3 of 5** to pass.
3. **Step 2 — Fundamental screen** (`scanner/fundamental_screen.py`): for
   technical passers, pulls revenue growth, earnings growth, margin trend,
   and debt-to-equity from `yfinance`. Positive revenue growth (>8% YoY) is
   mandatory; at least 2 of the remaining 3 checks must be neutral-or-better.
   Anything reporting earnings within the next 5 trading days is excluded
   outright to avoid earnings-gap risk on a swing entry.
4. **Step 3 — Conviction score** (`scanner/scoring.py`): 0–100, weighted 60%
   technical alignment strength / 40% fundamental quality.
5. **Step 4 — Output** (`scanner/report.py`): top 15–20 names ranked by
   score, written to `data/scan-latest.json` (consumed by the
   dashboard) and `data/scan-latest.md` / `reports/scan-YYYY-MM-DD.md`
   (human-readable, archived per day). Each run also appends its rows to
   `data/history.json` — a running log of every ticker ever surfaced,
   tagged with the date it was recommended (a same-day re-run replaces
   that day's rows rather than duplicating them).

Each result includes the company name, industry, and a one-sentence
description (`longName`/`industry`/`longBusinessSummary` from `yfinance`,
truncated to the first sentence — never rewritten or paraphrased).

Any field a data source doesn't provide (e.g. no recent revenue figure) is
marked `"N/A"` — the scanner never estimates or fabricates a value.

## Running locally

```bash
pip install -r requirements.txt
python -m scanner.run                 # full S&P 500 scan
python -m scanner.run --limit 25      # quick smoke test on a subset
```

Outputs land in `data/scan-latest.json` and `reports/`.

Run tests with:

```bash
pip install pytest
pytest -q
```

## Dashboard

`index.html` is a static, dependency-free page with two tabs:

- **Latest Scan** — fetches `data/scan-latest.json` and renders the ranked
  table (ticker, company, industry, brief description, score, setup
  summary, key technical trigger, revenue growth, next earnings date,
  suggested entry zone, suggested stop level).
- **History** — fetches `data/history.json` and renders every ticker ever
  recommended, newest first, with a text filter (ticker or company name).

It's designed to be served straight from GitHub Pages (Settings → Pages →
"Deploy from a branch" → the default branch → `/ (root)`) — no build step
required. Until the first scan has run, each tab shows a "no data yet"
message rather than fabricating a demo table.

The page also has a **"Run scan now"** button that triggers
`daily-scan.yml` on demand via GitHub's `workflow_dispatch` API. Since
this is a public static page, it can't embed a secret, so on first click
it asks for a GitHub *fine-grained* personal access token scoped only to
this repo with `Actions: Read and write` permission
(github.com/settings/personal-access-tokens/new). The token is written to
that browser's `localStorage` and sent directly from the browser to
`api.github.com` — it never passes through any server of ours, and a
"forget saved token" link clears it. A rejected token (401/403) is
cleared automatically. If the repo is ever renamed or moved, or the
default branch changes, update the `GH_OWNER` / `GH_REPO` / `GH_REF`
constants near the top of `index.html`'s `<script>`.

## Scheduling

`.github/workflows/daily-scan.yml` runs the scanner on a cron schedule
(`30 11 * * 1-5` UTC — pre-market before the 9:30am ET open in both EST and
EDT) and, if the output changed, commits the updated JSON/Markdown back to
the repo. It can also be triggered manually from the Actions tab
(`workflow_dispatch`).

`.github/workflows/tests.yml` runs the unit test suite on every push and
pull request.

## Data source & limitations

- All price and fundamentals data comes from Yahoo Finance via the free
  `yfinance` library. It has no official SLA, fundamentals coverage is
  inconsistent across tickers (especially quarterly YoY figures), and it
  can rate-limit or block on the free tier under heavy or repeated request
  volume. If a field is missing, it's reported as `N/A`, not guessed.
- Historical margin-trend and debt checks are computed from whatever
  `yfinance` exposes for quarterly financials; coverage is best-effort.
- The GitHub Actions runner needs unrestricted outbound HTTPS to Yahoo
  Finance endpoints. If you're running this in a network-restricted
  environment (e.g. a sandboxed dev container), the scanner will fail to
  fetch data — that's an environment/egress-policy issue, not a bug in the
  scanner itself.

## Project layout

```
scanner/
  universe.py             # live S&P 500 roster fetch
  data.py                 # yfinance OHLCV + fundamentals fetch
  indicators.py            # EMA / RSI / MACD / SMA
  technical_screen.py      # Step 1
  fundamental_screen.py    # Step 2
  scoring.py                # Step 3
  report.py                 # Step 4 (JSON + Markdown output)
  run.py                     # CLI orchestration
index.html                  # static dashboard (Latest Scan + History tabs)
data/
  scan-latest.json          # latest run's artifact (dashboard reads this)
  history.json               # running log of every ticker ever recommended
reports/
  scan-YYYY-MM-DD.md        # archived daily reports
tests/                       # unit tests (indicators, screens, scoring)
.github/workflows/
  daily-scan.yml             # scheduled pre-market run
  tests.yml                   # CI test suite
```
