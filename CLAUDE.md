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

## Status (2026-07-27)

TWO strategies are built and documented — **quickfix** (strategy 1) and **slowfix**
(strategy 2). They share every rule except Rule 4, so they take exactly the same setups and
differ only in the exit.

**Rule 4 is ONE family with one number in it — the profit cap in R.** "Ride to the first
opposite reversal beyond entry, but never past `cap`R." quickfix is that family at cap 5R,
slowfix at cap None. So quickfix uncapped IS slowfix and slowfix at 5R IS quickfix, trade
for trade; they are one strategy at the two settings the research is about. Say that
plainly rather than describing them as two methods. See `README.md` for the full rules,
money-management/slippage model, outputs and the charter hand-off.

The cap is a **DIAL on the reports** (2R–10R in quarter-R steps, plus no cap): each setting
is a real backtest, precomputed into `output/_variants.json`, because changing the cap
changes the trades themselves (every exit moves, and an earlier exit frees that market for a
signal a longer hold blocked). Do NOT confuse it with the risk dial, which replays live in
the browser precisely because trades are capital-independent. One cap dial PER STRATEGY
(Rule 4 is what tells them apart); one risk dial per PAGE (one account). Files on disk are
always written at the strategy's default cap. On this data 5R is the best return/drawdown
setting on the grid, but drawdown moves in plateaus on a 79-trade sample — do not read the
sweep as an optimisation.

Layout: one shared `engine.py`, and strategies are DATA in `strategies.py` (a registry; each
strategy is a key, a title and a default cap — every line of Rule 4 text is generated from
the cap). Runners are strategy-parameterized and take optional strategy keys, defaulting to
all: `run_all.py`, `run_portfolio.py`, `build_equity_html.py`, `export_charter_trades.py`,
and `run_pipeline.py` (all four in one pass over the array archive — reading it is the slow
part — then `report.html` + `conclusions.html`). Adding a strategy at a new cap is ONE line
in `strategies.py`; a genuinely different Rule 4 shape means a second policy factory.
`build_equity_html.py` needs `_variants.json`, so `run_portfolio.py` must run first. `venv\`
has pandas + openpyxl (`requirements.txt`). Reference market: gold futures.

Each strategy gets its own page `output/equity_<strategy>.html`, plus `output/report.html`
(every strategy, print/PDF). Pages carry a strategy-switcher row generated from the registry,
the **four rules** (1-3 shared text in `strategies.py`, 4 generated from the cap), the
**Rule 4 cap dial** under the rule cards (per strategy; rewrites the rule card, lede,
caveat and footer from `strategies.py`'s per-cap text), a **risk per trade**
number box (0-100%, spinners forced always-visible) that re-runs the whole shared-account
simulation client-side, and **Export PDF** (picker -> `report.html?s=...&cap=...&auto=1` -> the
browser's own print-to-PDF; no PDF library is bundled, on purpose). A **Conclusions** button
beside it opens `conclusions.html` (two free-text fields kept in localStorage, also passed in
the URL hash because file:// documents may not share storage) whose text prints at the END of
the exported PDF. Both page types come from
one stylesheet + one markup section + one renderer FACTORY (`mountReport(root, DATA)`), so
the report mounts several strategies without a second renderer. Entries use reversal levels
ONLY -- never describe these strategies as using a time/cycle signal. The per-market table
lists EVERY tested market (41), not just the 28 that traded: a market with no setups is a
result, so it shows 0 trades with an obsolete tag where applicable, and undefined ratios
print an em dash rather than 0%. The risk dial is possible because the trades are
capital-independent: risk changes the dollar sizing only, never the R multiples, so the page
replays `run_portfolio.py`'s loop over the trade list it already has. Corollary the user has
already asked about once: **win rate does not move with risk and that is correct** — risk
cannot change whether a position won. Only capital, P&L, max drawdown and return/DD move.
The CAP is the dial that changes which trades win. It self-checks against
the server's figure at the default risk, at EVERY cap (console warning on drift), and
`build_equity_html.py` refuses to build if the grid disagrees with a strategy's workbook —
if you change the money management in `run_portfolio.py`, change `simulate()` in
`build_equity_html.py` to match. Nothing is persisted and no file changes.

**Choosing the profit cap** is the LAST section of every page (after By market / Daily data,
before the footer): one chart, *Final capital by profit cap levered to a constant 6%
drawdown*, four stacked panels — capital, RISK EACH CAP ALLOWS, return/DD, win rate — and
five short passages under it whose every number is READ OUT OF THE GRID at render time, not
typed, so the prose cannot go stale. Risk is solved per cap by bisection (`TARGET_DD`) so the
caps are compared at equal PAIN, not equal bet size; it deliberately does NOT follow the risk
dial, so it is computed once and cached (the cap marker still moves). This INVERTS the
ranking: at equal drawdown the sweet spot is 2R-3R and the uncapped run is the WORST of the
family, since it must be sized down to 0.46% per trade. A second chart showing the same grid
at the dial's risk was built and then removed on request — at one risk the comparison is the
misleading one. Uncapped is a dashed reference line, never a point ("no cap" is not 10.25R).
It calls the SAME `simulate()` with a `lite` flag, NEVER a second copy of the money
management, and warns if the bisection missed the target. Drawn SYNCHRONOUSLY at mount —
deferring it to a rAF silently skipped it on any page whose cap was `none`, including in the
printed PDF.

Variant rows travel PACKED (positional arrays against shared market/date/reason tables):
`VAR_COLS` in `run_portfolio.py` and `unpackCap` in `build_equity_html.py` are two halves of
one format — change one and you must change the other. The whole grid shares one day
calendar so the equity curve's x-axis does not shift as the dial moves.

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
