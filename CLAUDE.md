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

ONE strategy is built and documented: **quickfix**, the cap family at a **1.9R** profit cap
with **1.39%** risk per trade. THOSE ARE THE DEFAULTS (user, 2026-07-28) and they are the
levered-optimal point, not a guess: 1.9R tops the constant-6%-drawdown chart, and 1.39% is
the risk that puts it exactly there (verified: 6.00%). `engine.RISK_PCT`, the reference the
variant grid is priced at, tracks it. `CHARTER_CAPS` must contain 1.9R and does.

**BOTH SIBLING STRATEGIES HAVE BEEN RETIRED.** Do not reinstate either without being asked.
- **slowfix** (2026-07-28) was the cap family at no cap, i.e. a dial position, never a
  separate method. "No cap" is still a dial setting and the dashed reference line on both
  charts, and still the worst point of the family at equal drawdown ($158,195 at 0.396%).
- **quickfixpro** (2026-07-28, user: "it has no longer value") took profit one tick beyond
  the entry bar's own extreme, fixed at entry: a genuinely different Rule 4 SHAPE, not a cap,
  so `in_grid=False` and its page carried neither the cap dial nor the cap charts. Removed
  from the report AND from charter (`CHARTER_STRATEGIES` is now empty). Its policy was
  deleted rather than left as unreachable code; it is in git, and `strategies.py`'s header
  says how to add a second shape back.

So a "strategy" here is now just a dial position. The `Rule4` / `in_grid` machinery stays,
because it is what makes the pages drop the cap dial and cap charts for a non-cap shape.

**GAP FILLS** (user, 2026-07-27). A bar that JUMPS OVER the stop or the target fills at
**that bar's OPEN**, not at the level — the open is the day's first price, so it is the one
case where a daily bar reveals the intraday order. Applies to ALL strategies (the stop is
shared machinery, and two fill models would make the comparison unfair). A gapped stop
therefore loses MORE than 1R (worst on this data: −11.68R, on an uncapped run).

A gap is measured against the **PREVIOUS CLOSE**, not the open alone: a short gaps its target
when `open <= target < prev_close`. Testing the open by itself was a REAL BUG, introduced and
fixed the same day — a short's entry bar closes below its entry by definition, so any target
above that close was already in the money before management started, every next open counted
as a "gap", and the trade was paid out at that open instead of at its target. Cost: ~24R of
free profit on quickfix, and it made a **0R cap the best setting on the whole grid** ($633k,
88% wr) which is what exposed it. An already-through target is NOT a gap; a resting limit
there fills at the limit. The STOP needs no such guard (it sits one tick beyond the entry
bar's own extreme, so no close can be through it while the trade is open). Do not "simplify"
`target_gap` back to a one-sided test.
`unknown_pl` at −1R survives only for the bar that opened BETWEEN the two and then traded
through both. This changed every published number and every solved risk; slippage still
charges the full 3-tick stop rate on a gapped stop, deliberately.

AUDITED when the user asked why quickfix and the retired quickfixpro disagreed on an engulfing bar (see
README "Why two strategies can split on the same bar"): `check_exit` IS shared and both give
the doubt to the stop (quickfix 5 of 9 such days -> `unknown_pl`, quickfixpro 6 of 7). The
wins are the GAP rule firing first. They split on exactly one date, EURO_Futures 2026-05-08,
where the open fell between the two strategies' targets (1.6 ticks apart). Do NOT "fix" this
as an inconsistency -- it is one rule against two target prices. The one thing genuinely open:
`open <= target` counts an open sitting EXACTLY on the target as a gap (once today,
USD_EUR_Cross_Rate 2026-03-09 quickfixpro +0.27R); requiring a strict one-tick gap was offered
and not taken.

**RISK PER TRADE IS PER STRATEGY** (user, 2026-07-27): each strategy's default is the risk
that puts THAT strategy at `engine.TARGET_DD` (6%) max drawdown — quickfix **1.39%**.
It is a MEASURED constant in `strategies.py`
(`Strategy.risk_pct`), derived by **`solve_risk.py`**, which calls the registry stale only
when the registered risk MISSES the 6% target by more than 0.05, not when it differs from
its own 3-dp solve (1.39 against a solved 1.391 would otherwise nag forever). Re-run it
and paste the numbers back
after any change to the rules, the fill model or the archive, or the reports quietly go
stale. So **1R = the strategy's own percentage**; any text saying "1R = 1%" or "1R = 1.573%"
is stale (the rules block generates it via `strategies.entry_mechanics(risk_pct)`, a function
for exactly this reason). Every page therefore opens at the same PAIN, not the same bet size,
which is what makes the three directly comparable. `engine.RISK_PCT` is a DIFFERENT thing —
the REFERENCE risk the shared variant grid is priced at and the pages self-check against; it
tracks quickfix's number but nothing depends on them being equal. `run_portfolio.at_risk()`
is the context manager that sets the money management's risk for one run and restores it.

At 1.9R / 1.39% on 2026-07-28 data: **$306,160, +206.16%, 6.00% DD, 34.4x, 84 trades.**
Published figures were rewritten repeatedly in two days by changes to the FILL MODEL alone,
strategies untouched -- treat the fill assumptions as the biggest open risk and never present
any of it as settled. See `README.md` for the full rules, money-management/slippage model,
outputs and the charter hand-off.

The cap is a **DIAL on the reports** — **0R to 10R**, tenth-R steps to 5.5R (`CAP_FINE_TO`)
and quarter-R above, plus no cap. ONE grid (2026-07-28): it is the dial's axis and both
charts'; the old split into a 2R-10R dial grid plus a 0R-3R detail grid existed only because
the dial could not reach below 2R. 75 settings, each a REAL backtest precomputed into
`output/_variants.json`, because changing the cap changes the trades themselves (every exit
moves, and an earlier exit frees that market for a signal a longer hold blocked). Do NOT
confuse it with the risk dial, which replays live in the browser precisely because trades are
capital-independent. One cap dial PER CAP-FAMILY STRATEGY, NONE on a strategy outside the
family; one risk dial PER STRATEGY too (the defaults are different numbers, so one box could
not show them). Files on disk are always written at the strategy's default cap and risk.

0R stays in the grid deliberately as the SANITY ANCHOR — it is what exposed the
already-through gap bug, by coming out best on the whole grid, which is impossible on its
face. Levered to equal drawdown the plateau starts at **1.3R** (allowed risk 0.19% at 0R ->
1.39% at 1.3R, flat to 2R, 1.18% at 2.1R) and the top four settings sit within 6% of each
other. Critically, ret/DD at a FIXED risk is NOT risk-invariant, and the levered top point has
read 2.5R, 2R, 3.75R and now 1.9R across successive changes to the FILL MODEL and to the
grid's resolution, never to the strategies. 3.75R is not even a setting any more (tenth-R
steps skip it). The default currently SITS on the peak (1.9R), which is a coincidence to
re-check after any change, not a result. Read the band, never rank caps off the fixed-risk
chart, and do not chase the peak.

Layout: one shared `engine.py`, and strategies are DATA in `strategies.py` (a registry; each
strategy is a key, a title and a default `Rule4` — for the cap family every line of Rule 4
text is generated from the cap, for a one-off shape it is written on the `Rule4`). Runners
are strategy-parameterized and take optional strategy keys, defaulting to
all: `run_all.py`, `run_portfolio.py`, `build_equity_html.py`, `export_charter_trades.py`,
and `run_pipeline.py` (all four in one pass over the array archive — reading it is the slow
part — then `report.html` + `conclusions.html`). `solve_risk.py` is NOT in the pipeline: it
derives the registry's `risk_pct` constants and is run by hand when they need refreshing.
Adding a strategy at a new cap is ONE line in `strategies.py` (`rule4=cap_rule4(3.0)`) plus
a `solve_risk.py` run for its risk; a genuinely different Rule 4 shape is a new policy
factory plus a `Rule4` with `in_grid=False` — see README "Adding a strategy", and remember a
new exit reason has to be added to `VAR_REASONS`, `prettyReason` AND charter's
`TRADE_COLORS`.
`build_equity_html.py` needs `_variants.json`, so `run_portfolio.py` must run first. `venv\`
has pandas + openpyxl (`requirements.txt`). Reference market: gold futures.

**REFRESHING THE WHOLE SYSTEM** (2026-07-28): `python ../trading_system/refresh.py`, or the
**Update** button at the top of charter's icon rail, which runs that file and streams it into
the page. It runs `hyperliquid_bot`'s `src/orchestration/sync_arrays.py` (the ARRAY SYNC
ALONE, not its `main.py` — nothing downstream reads the rest of that pipeline), then this
project's
`run_pipeline.py`, then charter's builder, each with that project's own venv interpreter, and
STOPS AT THE FIRST FAILURE (every step reads what the one before it wrote). It lives in the
umbrella because the sequence belongs to no department: a runner inside any one project would
hand it knowledge of the other two. It is a convenience runner, not an orchestrator, and
nothing here depends on it — this project's scripts are unchanged and still run by hand.
`solve_risk.py` is NOT in it, same as it is not in `run_pipeline.py`. Note the Socrates update
for the day lands around 08:10 local; a run before that legitimately shows no new bar.

Each strategy gets its own page `output/equity_<strategy>.html`, plus `output/report.html`
(every strategy, print/PDF). Pages carry a strategy-switcher row generated from the registry,
the **four rules** (1-3 shared text in `strategies.py`, 4 from the strategy's `Rule4`), the
**Rule 4 cap dial** under the rule cards (cap-family strategies only; rewrites the rule
card, lede, caveat and footer from `strategies.py`'s per-cap text), a **risk per trade**
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

**Choosing the profit cap** sits DIRECTLY ABOVE the All trades blotter (moved there
2026-07-28, user: it is the finding the report exists to make, so it reads before the raw
trade list). Order: KPIs, equity chart, Per-trade statistics, THIS, All trades, By market,
Daily data, footer. A non-cap shape would carry neither it nor the dial. ONE section with TWO
charts over the same 0R-10R grid (merged 2026-07-28, user: "1 section, less explaining, more
to the point"):

1. TOP -- **at a constant 1% risk** (`FIXED_RISK`), the real result. Panes: capital, MAX
   DRAWDOWN, the risk (a FLAT line, there precisely to show it never moves), RETURN/DD, win
   rate. It CANNOT rank the caps and says so from its own numbers: with the bet fixed the
   drawdown fans 4.3% to 28.0%, so a wider cap's bigger return is partly the deeper hole it
   was allowed to dig. Seeing that fan is what makes the chart below land.
2. BOTTOM -- **levered to a constant 6% drawdown** (`TARGET_DD`), the ranking. Panes: capital,
   RISK PER TRADE ALLOWED (renamed from "needed", user), win rate. Risk solved per cap by
   bisection -- the SAME method `solve_risk.py` uses for the strategies' own risks, at the
   same TARGET_DD, so quickfix's marker sits at exactly the risk its page opens at.

RETURN/DD is on the TOP chart only: on the levered one drawdown is pinned by construction, so
return/DD is just return / 6 and the pane would redraw the capital line in different units.

Neither follows the risk dial (that is the point of them), so both are computed once and
cached; the cap markers still move, and a dial setting off the axis is LABELLED rather than
silently unmarked. Solved risks are cached PER TOKEN (`leveredAt`) so a cap on both charts is
bisected once and they cannot disagree. Both call the SAME `simulate()` with a `lite` flag,
NEVER a second copy of the money management, and the levered one warns if the bisection
missed. Uncapped is a dashed reference line on both, never a point ("no cap" is not 10.25R).
Drawn SYNCHRONOUSLY at mount -- deferring to a rAF silently skipped them on any page whose
cap was `none`, including in the printed PDF. The generated prose was cut from five passages
to three at the same time. The FIRST (`Where it pays`) is generated end to end and carries a
YELLOW HIGHLIGHT on the best point, labelled "Optimal point" -- that is the finding the report exists to make. The
other two (`Why`, `How much to trust it`) are the USER'S OWN WORDS, verbatim; their numbers
are still read out (the sweet-spot cap is `best.cap`, not a literal) but the rest is fixed
prose and must be revisited BY HAND if the data moves.

PANE HEIGHTS are deliberate: every pane auto-scales its y range to its own data, so pixel
height IS how much variation is visible. Main pane 250px, readout panes 90px (raised from
150/50 on 2026-07-28, user: "more height so the vertical movement is better visible"). The
constant-risk pane stays 52px -- a flat line by construction, there to show it does not move. It is the one place in the report
where a claim can age.

NO EM DASHES in report prose (user, 2026-07-28) -- use a comma. The only survivors are the
`&mdash;` used as the "no data" marker in table cells (a null glyph, not punctuation, and
explicitly fine) and `&ndash;` ranges like "Dec 2025 &ndash; Jul 2026".

The DAILY CALENDAR (`DAILY_HTML`: date, total capital, drawdown, positions open, that day's
entries and exits) is on BOTH page types and PRINTS. Activity is coloured PURPLE for opened
and BLUE for closed (`--opened` / `--closed`, user 2026-07-28) -- NOT the page's green/red,
which mean won and lost, and an entry has no outcome yet.

TABLE WIDTHS: `table.trades` is `table-layout:fixed`, so widths come from the header row and
nowhere else. `COLS`/`MCOLS` carried a `w` percentage that was NEVER EMITTED, so every column
got an equal share and the printed blotter wrapped market names while Side and Bars sat half
empty. Widths are now written onto each `<th>` and must sum to 100. On top of that the print
stylesheet drops `table.trades` to 9px / 3-4px padding, because twelve columns do not fit A4
portrait at screen size -- verified at the real print width. Shrink the type, do not starve a
column to feed another. It was a collapsed
`<details class="noprint">` on the interactive page only and absent from report.html, so the
PDF never carried it and the user went looking; do not put it back behind a disclosure.

Variant rows travel PACKED (positional arrays against shared market/date/reason tables):
`VAR_COLS` in `run_portfolio.py` and `unpackCap` in `build_equity_html.py` are two halves of
one format — change one and you must change the other. The whole grid shares one day
calendar so the equity curve's x-axis does not shift as the dial moves. `_variants.json`
holds `caps` (the single cap axis -- the dial's and both charts') and `extra` (settings that
are not caps; EMPTY today, since quickfixpro was the only one) in one `v` table: same
packing, same replay.

Obsolete markets (last daily bar > `OBSOLETE_AFTER_DAYS` behind the newest across all
markets) have stopped being collected, so a position open on their last bar can never
resolve. Those are flattened at that bar's CLOSE with exit reason `data_end`
(`CLOSE_OBSOLETE_AT_END` in `engine.py`); only ACTIVE markets still report `open_at_end`.
Obsolescence is cross-market, so `run_markets` loads every market before backtesting any.

Trades are handed to charter **per OVERLAY** as `output/charter_trades_<key>.json`, chosen by
two lists in `export_charter_trades.py`:
- `CHARTER_CAPS` — **1.9R, 2R, 2.25R, 2.5R, 5R**, filenames zero-padded (`cap02_25`) so
  filename order IS cap order. It MUST contain quickfix's default cap, or the charts draw
  every cap except the one the strategy runs at -- 1.9R was added on 2026-07-28 for exactly
  that reason when the default moved there. MOVE IT IF THE DEFAULT MOVES. Per CAP, not per strategy, since 2026-07-27;
  the uncapped setting is not exported at all. The list is INDEPENDENT of the reports' grid
  and need not sit on it: 2.25R is exported and is on no grid the reports draw, so
  `run_pipeline` backtests whatever `CHARTER_CAPS` names on top of the grid.
- `CHARTER_STRATEGIES` — **EMPTY** since quickfixpro was retired (2026-07-28). Kept because
  the export handles a whole strategy and a cap through the same code path, so re-adding one
  is a single key.

The exporter PRUNES hand-off files it no longer owns, because charter globs the directory and
a leftover file keeps being drawn.

Charter globs them, draws each as `trades_<key>`, and its **T** rail button opens a box with
a checkbox per overlay (labelled with its Rule 4 + trade count) — 5 today. All are drawn
IDENTICALLY — one dotted line, one round exit marker (`TRADE_STYLE`, was `TRADE_STYLES[i%4]`)
— because they share Rules 1-3 and therefore enter on exactly the same bars; read them one
tick at a time. Colour is always the OUTCOME, never which strategy, so `target_bar` is the
same green as `target_r` in charter's `TRADE_COLORS`. Do NOT export the whole 34-cap grid: it
is affordable in bytes (~1.1 MB on an 8.1 MB site) but illegible, since 34 overlays stack 34
identical entry markers on one point.

Not yet done: intraday price data (IBKR) to replace the daily-proxy fill assumptions.

## Working agreements (carried over from charter)

- Commit straight to main.
- English only in code, variable names, comments, strings. No emoji.
- When the user supplies text verbatim, use it verbatim.
