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

THREE strategies are built and documented — **quickfix**, **slowfix** and **quickfixpro**.
They share every rule except Rule 4, so they take exactly the same setups and differ only in
the exit.

**Rule 4 has TWO SHAPES**, and the distinction runs through the whole pipeline:

1. **The cap family.** "Ride to the first opposite reversal beyond entry, but never past
   `cap`R." One number in it. quickfix is that family at cap **2.5R** (was 5R until
   2026-07-27), slowfix at cap None. So quickfix uncapped IS slowfix and slowfix at 2.5R IS
   quickfix, trade for trade; they are one strategy at the two settings the research is
   about. Say that plainly rather than describing them as two methods.
2. **The entry bar** — **quickfixpro** (2026-07-27, user's spec). Take profit **one tick
   beyond the entry bar's own opposite extreme**, fixed at entry and never moving: a short
   exits one tick below the entry bar's low. Stop and target are the two sides of the entry
   bar, so the bet is that the low breaks before the high — the initial energy of the move.
   NO reversal level and NO R ceiling, so it is **not a cap setting**: its page has **no cap
   dial and no cap-sweep section**. Exit reason `target_bar`. Rule 3's 3.5R filter still
   applies unchanged (it is Rule 3, not Rule 4), which is what keeps the setups identical to
   the other two; it just no longer describes the target. A winner is worth whatever the bar
   measured — +3.02R average, up to 9.52R on this data. Both-in-range days are `unknown_pl`
   at −1R, which was already the engine's rule and is what the user asked for.

A **`Rule4`** in `strategies.py` is ONE setting: policy + variant token + `in_grid` + prose.
A `Strategy` is a key, a title and a default `Rule4`. `in_grid` is the flag that makes the
pages drop the cap dial and the cap sweep automatically, and the policy signature now returns
its own exit reason (the engine only resolves `"reversal"` into a side).

**GAP FILLS** (user, 2026-07-27). A bar that JUMPS OVER the stop or the target fills at
**that bar's OPEN**, not at the level — the open is the day's first price, so it is the one
case where a daily bar reveals the intraday order. Applies to ALL strategies (the stop is
shared machinery, and two fill models would make the comparison unfair). A gapped stop
therefore loses MORE than 1R (worst on this data: −11.68R, slowfix).

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

AUDITED when the user asked why quickfix and quickfixpro disagree on an engulfing bar (see
README "Why two strategies can split on the same bar"): `check_exit` IS shared and both give
the doubt to the stop (quickfix 5 of 9 such days -> `unknown_pl`, quickfixpro 6 of 7). The
wins are the GAP rule firing first. They split on exactly one date, EURO_Futures 2026-05-08,
where the open fell between the two strategies' targets (1.6 ticks apart). Do NOT "fix" this
as an inconsistency -- it is one rule against two target prices. The one thing genuinely open:
`open <= target` counts an open sitting EXACTLY on the target as a gap (once today,
USD_EUR_Cross_Rate 2026-03-09 quickfixpro +0.27R); requiring a strict one-tick gap was offered
and not taken.

**RISK PER TRADE IS PER STRATEGY** (user, 2026-07-27): each strategy's default is the risk
that puts THAT strategy at `engine.TARGET_DD` (6%) max drawdown — quickfix **1.175%**,
quickfixpro **0.8%**, slowfix **0.396%**. They are MEASURED constants in `strategies.py`
(`Strategy.risk_pct`), derived by **`solve_risk.py`** — re-run it and paste the numbers back
after any change to the rules, the fill model or the archive, or the reports quietly go
stale. So **1R = the strategy's own percentage**; any text saying "1R = 1%" or "1R = 1.573%"
is stale (the rules block generates it via `strategies.entry_mechanics(risk_pct)`, a function
for exactly this reason). Every page therefore opens at the same PAIN, not the same bet size,
which is what makes the three directly comparable. `engine.RISK_PCT` is a DIFFERENT thing —
the REFERENCE risk the shared variant grid is priced at and the pages self-check against; it
tracks quickfix's number but nothing depends on them being equal. `run_portfolio.at_risk()`
is the context manager that sets the money management's risk for one run and restores it.

At their own 6% risks on 2026-07-27 data: **quickfix $290,446 / 31.7x / 58.3% wr; quickfixpro
$281,067 / 30.2x / 65.9% wr; slowfix $158,195 / 9.7x / 27.6% wr.** Quickfix and quickfixpro
are effectively TIED (1.5 points of ret/DD on 84 trades is not a result); quickfixpro gets
there on 45% time in market against 52%. This table was rewritten TWICE in one day by changes
to the FILL MODEL alone, strategies untouched — treat the fill assumptions as the biggest
open risk and never present the ordering as settled. See `README.md` for the full rules, money-management/slippage model, outputs and the
charter hand-off.

The cap is a **DIAL on the reports** (2R–10R in quarter-R steps, plus no cap): each setting
is a real backtest, precomputed into `output/_variants.json`, because changing the cap
changes the trades themselves (every exit moves, and an earlier exit frees that market for a
signal a longer hold blocked). Do NOT confuse it with the risk dial, which replays live in
the browser precisely because trades are capital-independent. One cap dial PER CAP-FAMILY
STRATEGY (Rule 4 is what tells them apart), NONE on a strategy outside the family; one risk
dial PER STRATEGY too (since 2026-07-27 — the defaults are three different numbers, so one
box cannot show them). Files on disk are always written at the strategy's default cap and
default risk. Levered to equal drawdown the sweet spot is the **2R–3R band**; the top POINT
inside it was 2.5R (hence quickfix's default) and is **2R since gap fills went in** — the
default was deliberately left at 2.5R, because on 76–88 trades the point moves and the band
does not. Do not read any of this as an optimisation, and do not move the default unless the
BAND moves. Critically, ret/DD at a FIXED risk is NOT risk-invariant: the same fixed-risk
sweep has ranked 5R, 7R/8.5R and 2R top at different reference risks, with nothing about the
strategies changing in between. Only the levered chart compares caps honestly — never rank
caps off the fixed-risk sweep.

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

**Choosing the profit cap** is the LAST section of every CAP-FAMILY page (after By market /
Daily data, before the footer; quickfixpro has neither it nor the dial): one chart, *Final capital by profit cap levered to a constant 6%
drawdown*, four stacked panels — capital, RISK EACH CAP ALLOWS, return/DD, win rate — and
five short passages under it whose every number is READ OUT OF THE GRID at render time, not
typed, so the prose cannot go stale. Risk is solved per cap by bisection (`TARGET_DD`) so the
caps are compared at equal PAIN, not equal bet size; it deliberately does NOT follow the risk
dial, so it is computed once and cached (the cap marker still moves). This INVERTS the
ranking: at equal drawdown the sweet spot is 2R-3R and the uncapped run is the WORST of the
family, since it must be sized down to 0.396% per trade. Note the chart's own bisection is
the SAME method `solve_risk.py` uses for the strategies' default risks, at the same
`TARGET_DD` -- so quickfix's page marker sits at exactly the risk the page opens at. A second chart showing the same grid
at the dial's risk was built and then removed on request — at one risk the comparison is the
misleading one. Uncapped is a dashed reference line, never a point ("no cap" is not 10.25R).
It calls the SAME `simulate()` with a `lite` flag, NEVER a second copy of the money
management, and warns if the bisection missed the target. Drawn SYNCHRONOUSLY at mount —
deferring it to a rAF silently skipped it on any page whose cap was `none`, including in the
printed PDF.

**Inside the hotspot** is a SECOND chart section under it (2026-07-27, user's ask), the same
calculation zoomed: `FINE_GRID` = **0R-3R at 0.1R**, because the wide chart's quarter-R axis
resolves the 2R-3R band at five points and STARTS at 2R, so the band's left side was never
drawn. TWO grids on purpose -- `CAP_GRID` (2R-10R, 0.25R) stays the dial's and the wide
sweep's axis; `CAP_CHOICES` is their union (62 settings). `_variants.json` carries `caps`,
`fine` and `extra` over one `v` table. Solved risks are cached PER TOKEN (`leveredAt`) so the
2R/2.5R/3R overlap is bisected once and both charts show the identical number. Cost measured
before building: <1s backtest, ~+160 KB per page (451 KB, report 471 KB). NOT exported to
charter (user: "for now we don't need it on our charts yet") -- `CHARTER_CAPS` unchanged.

FINDING: **the plateau starts at 1.3R.** Allowed risk climbs 0.19% at 0R -> 1.39% at 1.3R,
holds to 2R, falls to 1.18% at 2.1R. Below 1.3R the cap is too tight for the winners to pay
for the losers and capital falls away to $94k at 0R (1% win rate -- the target sits ON the
entry). Flat allowed risk does NOT mean a flat result: across 1.3R-2R capital still climbs
($203k -> $306k, upper half +28.6% over lower), because every cap there bets the same but a
wider one lets winners run further. Best point 1.9R, +6.5% over its neighbours = noise. The
page computes all of this from the grid, including the drift, so it cannot go stale.

The 1R version of this chart is what FOUND the already-through gap bug: it reported its own
left edge was still on the plateau, extending to 0R put a degenerate 0R cap at the top of the
grid, and that was the tell. Keep 0R in the grid -- it is the sanity anchor.

Variant rows travel PACKED (positional arrays against shared market/date/reason tables):
`VAR_COLS` in `run_portfolio.py` and `unpackCap` in `build_equity_html.py` are two halves of
one format — change one and you must change the other. The whole grid shares one day
calendar so the equity curve's x-axis does not shift as the dial moves. `_variants.json`
holds `caps` (the dial's axis and the wide sweep's), `fine` (the zoom's, 1R-3R) and `extra`
(settings that are not caps, e.g. quickfixpro's `bar`) in one `v` table: same packing, same
replay, three different questions asked of it.

Obsolete markets (last daily bar > `OBSOLETE_AFTER_DAYS` behind the newest across all
markets) have stopped being collected, so a position open on their last bar can never
resolve. Those are flattened at that bar's CLOSE with exit reason `data_end`
(`CLOSE_OBSOLETE_AT_END` in `engine.py`); only ACTIVE markets still report `open_at_end`.
Obsolescence is cross-market, so `run_markets` loads every market before backtesting any.

Trades are handed to charter **per OVERLAY** as `output/charter_trades_<key>.json`, chosen by
two lists in `export_charter_trades.py`:
- `CHARTER_CAPS` — **2R, 2.25R, 2.5R, 5R**, filenames zero-padded (`cap02_25`) so filename
  order IS cap order. It MUST contain quickfix's default cap, or the charts draw every cap
  except the one the strategy runs at. Per CAP, not per strategy, since 2026-07-27;
  **slowfix is not exported at all** (user) — it stays a full strategy everywhere else.
- `CHARTER_STRATEGIES` — **quickfixpro**, exported whole and named by its key (which sorts
  after every `cap…`). It earns an overlay by being a different Rule 4 SHAPE, not another
  setting: its exits stop inside the entry bar instead of fanning out along the cap axis.

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
