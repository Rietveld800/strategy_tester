# strategy_tester

Strategy department of a four-part trading system. Read `README.md` and
`../trading_system/README.md` (umbrella contracts) before doing anything.

## Context

- The system implements the Socrates "time and price meet" method (Erwin
  Pletsch): trade when a time signal (aggregate turning point) coincides with a
  price signal (a reversal level).
- Sibling projects: `../hyperliquid_bot` produces the array (meta) xlsx files on
  a VPS; `../charter` renders HTML charts. This project turns strategy rules
  into a backtest with risk management.
- Data flows one direction: hyperliquid_bot -> array files -> strategy_tester ->
  trades/equity JSON -> charter. Never scrape data here, never render charts
  here, never patch data gaps (report them to hyperliquid_bot).

## Inputs

- Array files (read-only):
  `../hyperliquid_bot/data/array/<Market>/<Year>/<tf>/<Market>_YYMMDD<sfx>_array.xlsx`.
- Battle-tested parsers live in `../charter/scripts/charting_core.py`
  (OVERVIEW DATA = OHLC, REVERSALS DATA, timing rows). Import them from there
  for now; do not rewrite them. Extract a shared package only when importing
  across projects starts to hurt.

## Outputs

- Trade ledger (entries, exits, per-trade percentage, R:R) + equity curve as
  JSON. Charter renders these; the exact schema is defined together with the
  first backtest.
- Simulation inputs live here: position sizing, risk per trade, fees, starting
  capital.

## Status (2026-07-25)

TWO strategies are built and documented — **quickfix** (strategy 1) and **slowfix**
(strategy 2). They share every rule except Rule 4, so they take exactly the same trades and
differ only in the exit: quickfix caps a winner at 5R (or an opposite reversal nearer than
5R); slowfix has no cap and rides to the first opposite reversal beyond entry, whatever the
distance. See `README.md` for the full rules, money-management/slippage model, outputs and
the charter hand-off.

Layout: one shared `engine.py`, and strategies are DATA in `strategies.py` (a registry;
each strategy is its Rule 4 target policy plus its display text). Runners are
strategy-parameterized and take optional strategy keys, defaulting to all: `run_all.py`,
`run_portfolio.py`, `build_equity_html.py`, `export_charter_trades.py`, and
`run_pipeline.py` (all four in one pass over the array archive — reading it is the slow
part). Adding strategy 3 means one entry in `strategies.py`; nothing else. `venv\` has
pandas + openpyxl (`requirements.txt`). Reference market: gold futures.

Each strategy gets its own page `output/equity_<strategy>.html`, plus `output/report.html`
(every strategy, print/PDF). Pages carry a strategy-switcher row generated from the registry,
the **four rules** (1-3 shared text in `strategies.py`, 4 per strategy), a **risk per trade**
number box (0-100%, spinners forced always-visible) that re-runs the whole shared-account
simulation client-side, and **Export PDF** (picker -> `report.html?s=...&auto=1` -> the
browser's own print-to-PDF; no PDF library is bundled, on purpose). Both page types come from
one stylesheet + one markup section + one renderer FACTORY (`mountReport(root, DATA)`), so
the report mounts several strategies without a second renderer. Entries use reversal levels
ONLY -- never describe these strategies as using a time/cycle signal. That is possible because the trades are capital-independent: risk changes the dollar
sizing only, never the R multiples, so the page replays `run_portfolio.py`'s loop over the
trade list it already has. It self-checks against the server's figure at the default risk
(console warning on drift) — if you change the money management in `run_portfolio.py`, change
`simulate()` in `build_equity_html.py` to match. Nothing is persisted and no file changes.

Obsolete markets (last daily bar > `OBSOLETE_AFTER_DAYS` behind the newest across all
markets) have stopped being collected, so a position open on their last bar can never
resolve. Those are flattened at that bar's CLOSE with exit reason `data_end`
(`CLOSE_OBSOLETE_AT_END` in `engine.py`); only ACTIVE markets still report `open_at_end`.
Obsolescence is cross-market, so `run_markets` loads every market before backtesting any.

Trades are handed to charter as `output/charter_trades_<strategy>.json`, one file per
strategy in the same schema (this replaced the single `charter_trades.json`). Charter globs
them, draws each as `trades_<key>`, and its **T** rail button opens a box with a checkbox per
strategy — any combination can be shown at once. Colour still means the OUTCOME, so charter
separates strategies by line dash + exit marker. A new strategy needs no charter change:
export the file and rebuild the site.

Not yet done: intraday price data (IBKR) to replace the daily-proxy fill assumptions.

## Working agreements (carried over from charter)

- Commit straight to main.
- English only in code, variable names, comments, strings. No emoji.
- When the user supplies text verbatim, use it verbatim.
