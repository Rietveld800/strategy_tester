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

## Status (2026-08-13)

**ONE STRATEGY: `quickfix1m1dc`.** It is the 1-minute engine, it is what the
reports publish, it is the only charter overlay, and it is the whole of the
1-minute workstream section below. Everything about it is there; read that.

**THE DAILY REGISTRY IS EMPTY** (user, 2026-08-12). `strategies.REGISTRY == []`.
Twenty-five daily strategies that morning, five by the afternoon, none by the
evening -- quickfix1m1dc replaced them. The retirements, all in git, none to be
reinstated without being asked:

| when | what | why |
|---|---|---|
| 2026-07-28 | `slowfix` | the cap family at no cap: a dial position, never a method |
| 2026-08-12 | `quickfixwick`, `quickfixclose2` .. `quickfixclose20` | the hold sweep had measured its curve and the answer did not move: one bar is where the exit pays |
| 2026-08-12 | `quickfix`, `quickfixclose0`, `quickfixopen1`, `quickfixclose1`, `quickfixopen2` | the 1-minute engine became the published strategy |

**THE DAILY CODE IS INTACT AND UNUSED, and that is deliberate.** `engine.py`,
`strategies.py` (the cap family, the bar exits, the grid, the prose
generators, `Rule4`, `Strategy`), `run_all.py`, `run_portfolio.py`,
`build_equity_html.py`, `export_charter_trades.py`, `solve_risk.py` and
`run_pipeline.py` are all still correct; there is simply nothing registered for
them to run. Registering one `Strategy` brings the entire daily side back with
its pages, its variant grid and its cap dial. Do NOT delete them to tidy up,
and do NOT delete `build_equity_html.py` in particular -- `build_1m_report.py`
and `research_1m_levels.py` import its `CSS`, so the 1m pages would lose their
stylesheet.

**TWO GUARDS EXIST BECAUSE THE EMPTY REGISTRY IS DANGEROUS, not because it is
untidy.** `export_charter_trades.prune()` deletes every `charter_trades_*.json`
it does not own; with nothing owned it owned nothing, so it wiped
`charter_trades_quickfix1m1dc.json` -- the only overlay charter has left. Found
by running it. So:
- `run_pipeline.py` raises on an empty registry instead of spending an archive
  pass, writing a `_variants.json` and an empty `report.html` nobody reads, and
  pruning the charter directory to nothing.
- `export_charter_trades.py` refuses in `main()` AND `prune()` refuses on an
  empty item list. The guard is in `prune()` and not only in `main()` because
  `run_pipeline` calls `export()`/`prune()` directly. **A prune that owns
  nothing is not a prune, it is a wipe.**

**THE CHARTER HAND-OFF IS `export_charter_trades_1m.py`** (2026-08-12), and it
is the only owner of `output/charter_trades_*.json` now. It reads the published
blotter alone (no backtest), maps the engine's contract key to charter's market
FOLDER through `run_1m.market_info()`, and writes one file,
`charter_trades_quickfix1m1dc.json`, in charter's EXISTING schema -- so charter
needed exactly one line for it (see below). `run_1m.py` calls it, which is why
the overlay can never be a refresh behind the report beside it. It prunes.

**INTRADAY TRADES ON A DAILY PANE.** A quickfix1m1dc trade enters at a minute
inside the session and exits at the next day's settlement or at its stop, so on
charter's daily overlay the entry marker lands on the entry session's bar and
the exit marker on the exit session's bar. The minute is LOST, deliberately: the
daily pane cannot show it and charter's own 1m trade study is where the intraday
path is read. A trade stopped in its own session draws a VERTICAL line on one
bar -- correct, and the same thing quickfixclose0 used to do.

**CHARTER COST ONE LINE**: `close1` added to `TRADE_BY_R` in
`chart_all_markets_reference.py`. The exit reason names a MOMENT (the next
settlement), so it covers a win and a loss alike and its colour must be read off
the trade's own R, exactly like the retired `exit_close` / `exit_open`. Colour
is the outcome, always. `load_strategies()` globs, so the T box followed from 29
overlays to 1 with no other edit; its copy was rewritten because it described
profit caps and "every overlay shares rules 1 to 3", which is now false.

**WHAT THE UPDATE BUTTON BUILDS** (`../trading_system/refresh.py`, and charter's
rail button runs that file): `data` -> `bars` -> `strategy1m` -> `matrix1m` ->
`hybrid1m` -> `levels1m` -> `levels1mnl` -> `charts`, ~17 min. The old
`strategy` step (`run_pipeline.py`) is GONE with the daily registry. Measured
2026-08-12: run_1m 111s, matrix 240s, hybrid stop 1s (it reads the matrix JSON),
each level study 54s. The matrix became the full factorial on 2026-08-13
(28 cells, 625 engine passes against 163) and now costs ~9 min, which is
where the chain's ~12 -> ~17 min came from; `hybrid1m` builds `variant 5`
and `levels1mnl` builds `variant 20`.

**`rcut1m` IS REACHABLE BUT NOT IN A FULL RUN** (user, 2026-08-12: "we're not
updating quickfix1m1dcRcut.html after clicking button. quickfix1m1dcRcut.html
will get his own update button inside the html page"). It is ~231 engine passes,
about 90 minutes. `refresh.EXTRA_STEPS` holds it: `step_for()` searches it,
`run_all()` never does, so `refresh.py rcut1m` and `/api/refresh` reach it and
a plain `refresh.py` cannot. The page's own button posts that key to charter's
`/api/refresh` -- the SAME runner, driven from the page that shows the result,
so there is no second way to build anything. It finds the server by probing
127.0.0.1:8000..8019 (the page is usually opened straight off disk, so it has no
origin to infer a port from), posts `text/plain` so a null origin never needs a
CORS preflight, streams the log, and reloads itself when the run finishes.
`serve.py` echoes `Access-Control-Allow-Origin` for `null` and loopback origins
only -- that is not a security control and does not pretend to be one, it just
does not hand the reply to the open internet.

**THE R-CUT CACHE IS KEYED ON THE DATA NOW** (2026-08-12), not only on the band
and the dials. It was reusing every cell from whatever window it was first built
on, so a rebuild after new bars landed finished in three seconds and republished
a stale grid beside a fresh baseline -- measured, not hypothetical.
`data_fingerprint()` hashes size+mtime of every bars parquet (~90 files, ~2 ms)
and any change throws the whole cache away. It errs the safe way on purpose: a
wrong cache HIT costs correctness, a wrong MISS costs time. The payload carries
`built`, `data` and `n_cells`, and the page prints the build time, so a stale
grid is visible rather than assumed fresh.

## 1-minute workstream (2026-08-03) — THE published strategy since 2026-08-12

`engine_1m.py` + `run_1m.py` + `tests/test_engine_1m.py` implement
**quickfix1m1dc v2**: rules 1-2 evaluated INTRADAY on 1-minute bars
(rule 3 REMOVED 2026-08-06 - target-era logic), market-order entry when
the first reversal prints (2 ticks slippage), ladder-anchored stop (one
tick beyond the 5th reversal, 4th when only four; ladder must carry 4),
R denominated level-to-stop, exit at next-day settlement. Baseline dials
(run_1m.BASELINE): no tightening, no pre-activation entries, **no
confirmation clause**, ladder stop, **session lockout at 1**, and the
**GEOMETRY BAND at 0.20 / 0.50** (upper adopted 2026-08-10 s.15e, lower
raised from 0.00 on 2026-08-11 s.17): an entry is refused when its
level-to-stop distance is above 0.50 or below 0.20 of the trailing 24h
high-low range. The upper cut has a derivation (payoff capped under the
fixed exit, s.15b, plateau 0.40-0.55); the lower cut is the researched
band's edge, adopted WITH the s.15c caution on record (a one-step ridge
carried by five trades; the sub-0.20 wider-stop investigation stays
PARKED, s.15d). The published universe is the **HUMAN MARKET FILTER**
(`run_1m.HUMAN_APPROVED`, 22 markets, s.16): Lode's eye inspection of
chart structure, never a market's backtest result; explicit CLI keys
bypass it for debug runs. The published report page is **sized to the 6%
drawdown budget** (s.17): `build_baseline()` solves risk per trade by
bisection to a 6.0% worst-reached drawdown and states the number - the
JSON and matrix stay at 1%, since R is risk-independent. A refused entry
does not spend the lockout allowance, so a band SHIFTS the trade list
rather than slicing it; that is why every band in
`build_1m_rcut_report.py` is its own engine run (that grid stays
whole-universe, no cuts - the research record). The matrix chart draws
every cell's curve LEVERED to a constant 6% drawdown (risk solved per
cell, table carries both bases) on a window-height plot - comparing
curves at one bet size hands the deepest hole the tallest line (Lode,
2026-08-11).
**THE MATRIX IS A FULL FACTORIAL AND ITS CELLS ARE NUMBERED**
(2026-08-13, Lode). It used to be one axis (the lockout) with four
one-dial cells beside it, each NAMED for the dial it moved -- `hybrid
stop`, `no lockout`, `band 0.00-0.50`, `no market filter`. That naming
only works while every cell is one step from the baseline, and it hid
the combinations: the table could not say what the hybrid stop is worth
WITHOUT the lockout. So `run_1m_matrix.build_grid()` crosses four
PROPERTIES and the page prints them as COLUMNS instead of a name --
lockout (1 / 2 / none) x stop (4th/5th / hybrid / wick) x band
(000-050 / 020-050 / full) = 27 cells on the filtered universe, plus
one 31-market cell that Lode set at lockout 1 / hybrid / 000-050 so it
pairs with `variant 4` rather than with the published dials. **`wick`
IS the engine's existing `extreme` mode** (confirmed by Lode) -- one
tick beyond the session's running extreme AT ENTRY, which is the only
extreme that exists at entry -- so this cost NO engine change. Cells are
`variant 1` .. `variant 28`, the published baseline is **`variant 2`**
and it is an ordinary row: every row carries a checkbox (default on,
plus all-on / all-off) and the baseline can be switched off like any
other. Colour is a FAMILY, not an identity: hue is the stop anchor,
the shade within a hue is the band, lightness is the lockout, and the
31-market cell is magenta. `run_1m_matrix.variant_slug()` owns the
filename form (`variant 5` -> `_variant_05`) and both consumers import
it, so a variant page can never land under a name the matrix does not
use. 625 engine passes against 163: the step went from ~4 to ~9 min and
the refresh chain from ~12 to ~17 (accepted by Lode in advance). Every
former watch-cell is still in the grid, now by number: `no geometry cut`
= `variant 3`, `band 0.00-0.50` = `variant 1`, `hybrid stop` =
`variant 5`, `no lockout` = `variant 20`. **`run_1m_matrix.py --page`
redraws the page from the JSON with NO backtest** (the curves come back
from the stored trades in seconds, colours are recomputed from the
properties): nine minutes is too much to spend on a layout edit. The
whole grid is written up in audit s.18.
**THE SESSION LOCKOUT** (`max_entries_per_session`, default 1, Lode
2026-08-07, audit section 11): at most one ENTRY per market per session,
expiring at the session boundary. NOT part of rules 1-3 by explicit choice --
those say what the chart must show, this is a fact about our own previous
trade, the family of one-position-per-market. It counts ENTRIES, NOT EXITS,
and that is worth 19R: a position carried in from the previous session and
stopped intraday does not spend today's allowance (9 trades, +19.10R, 6
winners, including the sample's biggest at +13.41R). Measured first by
`research_1m_levels.py`. The rerun matched the blotter estimate to the
decimal, so this rule has NO cascades.
**ON CORRECTED BARS THE PATTERN IS SHARPER AND THE RULE WINS ON EVERY
METRIC** (audit 11b, figures on the CURRENT window to 2026-08-06): 1st trade
of a market-day 41.0% wr / +53.22R, 2nd **16.7%** / -10.30R (was 21.4% on
contaminated bars), and lockout 1 beats no lockout 134v153 trades,
41.0%v37.9%, +53.22Rv+45.36R, streak 7v8,
**11.20%v14.99% DD**, $162,415v$149,347. Lode's read, recorded: the
win-rate-first thesis is what carried it. STILL TRUE THOUGH: the measured
gain is one market's one session -- removing WHEAT's six repeats BY HAND
gives a better drawdown (9.77%) than the rule itself, and the other 13
repeats are +0.62R. Keep the rule and watch it; do not believe the +7.86R.
**OFF-BOOK PRINTS WERE IN THE BARS UNTIL 2026-08-07** (audit section 12,
found from "FGBL's 1m chart doesn't show properly"): XEUR and IFUS publish
each minute twice, on-book and off-book, data_center's writers dropped
`publisher_id`, and both the charts and the ENGINE ate the duplicates. Fixed
upstream (`expand_process.load_bars`); every consumer reads through it now,
with ONE deliberate exception that is not ours: data_center's own
`trade_session_bars()` reads the RAW frame, because the FINGERPRINT asks which
contract SOCRATES DISPLAYED rather than what we could have traded, and on IFUS
the Socrates open matches the OFF-BOOK row (qualified 2026-08-07; filtering
there costs SB 0.836 -> 0.767, DX 0.934 -> 0.908, CC 0.479 -> 0.096, KC 0.452
-> 0.164). Nothing in THIS project reads those session bars, and every bar the
1m engine sees is still on-book only. See data_center's CLAUDE.md; do not
"fix" that function.
Every published 1m figure moved and all for the better -- 128 trades, 41.4%
wr, +55.34R, 11.20% max DD, $165,921 at the baseline, against 132 / 39.4% /
+42.51R / 14.55% / $146,382 on the contaminated bars, both to 2026-07-31.
**THE WINDOW THEN REACHED 2026-08-06** (audit section 13): data_center's
WINDOW_END had been frozen at the pilot's purchase window, silently capping
the chain, and with it fixed 20 markets carry 1m bars six days further. The
rerun is PURELY ADDITIVE (6 trades added, 0 removed, no pre-existing R moved,
no data_end exits). The daily refresh has carried the window on to
2026-08-07, and since the 2026-08-11 ADOPTIONS (market filter + band
0.20/0.50 + 6% sizing, s.17) the live baseline is **59 trades, 49.2% wr,
+57.88R, streak 4, 4.68% max DD, $173,846 at 1%**; the published page shows
the 6%-solved sizing (**1.289% risk per trade, $202,126, 6.00% DD** on this
window). The whole-universe and previous-band states stay visible as the
matrix's `no market filter`, `band 0.00-0.50` and `no geometry cut` cells.
Figures quoted from before 2026-08-07 are pre-correction; the shape of the
arguments survived, the numbers did not. Expect the live line to move with
every refresh: the dated tables in the audit are records, not current
claims.
**THE CONFIRMATION CLAUSE WENT ON 2026-08-06** (Lode), and it is the
MIRROR of rule 3: rule 3 was unprincipled and profitable and went anyway;
the clause was PRINCIPLED (the intraday stand-in for the daily engine's
close-beyond-the-level entry proof) and cost money. Measured on an
IDENTICAL 153 entries, dropping it improved net R (+26.63 -> +34.56), win
rate (30.7 -> 36.6%) and drawdown (17.78 -> 14.70%) at once; the 23
aborted trades carried instead cost -2.70R against -10.64R. So the model
is now a pure touch-entry strategy carrying every position overnight with
the stop live, and it no longer asks the daily engine's question. The
gap risk the clause was FOR barely exists here: 6 of 80 stops opened
through their stop, 0.52R in total, none of them former aborts. Related
open item: engine_1m books a stop AT the stop price where the daily
engine fills a gapped stop at the OPEN, worth ~0.5R of optimism.
**TWO DIALS carry this**: `confirm` and `stop_mode` (`ladder` /
`ladder_or_extreme` / `extreme`). The hybrid stop is NOT retired (Lode:
"keep an eye on") - it wins on win rate (39.9%) and has the shortest
losing streak in the grid (6), but a wider stop is a bigger R denominator
so it books ~9.7R less; `extreme` is far worse, which is how we know the
ladder anchor earns its place in both directions. See audit section 10. The full rule set, every decision and the first results live
in `../data_center/docs/backtest_1m_design.md` — READ THAT before touching
any of it. The 2026-08-05 trade-review audit (fill-model phantoms, stop
variants, overnight-window dial, verified timing model) is
`docs/quickfix1m1dc_audit.md` — the agreed improvement plan, staged and
awaiting Lode's decisions; no engine change before that discussion. Data comes from `../data_center` (GC pilot: bars parquet, roll
calendar, settlements); levels via charter's parse_array as everywhere
else. It was deliberately kept OUT of the daily registry, pages, variant grid
and charter hand-off "until the results earn it" (2026-08-03); on 2026-08-12 it
did not join them, it REPLACED them -- the daily registry is empty and this is
the only strategy left, with its own report, its own charter overlay
(`export_charter_trades_1m.py`) and no variant grid at all. venv gained
pyarrow and pytest for this (requirements.txt updated). Run the tests
with `venv\Scripts\python.exe -m pytest tests -q`.

**THE REPORT IS `build_1m_report.py` -> `output/quickfix1m1dc_report.html`**
(2026-08-06, Lode: "so I can look up the different trades", in the format of
the daily reports). It rebuilds from `quickfix1m1dc_all.json` alone, no
backtest, and carries the v2 rule block and dials, the KPI row, the three
lightweight-charts panes, per-trade statistics, the EXIT-CLASS anatomy, the
full 153-row blotter, the per-market table and the daily calendar. It
**imports `build_equity_html.CSS`** so the look cannot drift from the daily
pages, but NOT `mountReport`: that renderer is bound to the daily registry and
its variant grid, and this strategy is outside both, so the tables are rendered
in Python and the only script is the panes plus a table sorter. Its money is
`run_1m.portfolio_replay` MIRRORED (the trades' own `pnl_usd` / `cash_after`
are PER MARKET, a different account) and the build warns if its final capital
or drawdown drifts from what `run_1m` published. **The drawdown pane plots
the worst drawdown REACHED each day, not the one standing at the bell**, and
the build warns if the bottom of the pane is not the headline: this is a 1m
engine resampled to a daily axis, so a session can dig a hole and fill it
before the close. Carrying only closing balances showed 8.96% under an
11.20% headline until 2026-08-08. The equity line still plots the close. **Every blotter row links
into charter's 1m study at that trade** (`trades.html?m=<Market>&t=<n>`,
1-based, charter sorts each market's trades by entry exactly as the report
does); the link needs charter's `serve.py` running. The old dark
`quickfix1m1dc_equity.html` and `run_1m.build_html` are GONE (2026-08-06) --
the report says everything they said.
`build_1m_report.py --variant "variant 5"` builds a report for ANY cell of
`run_1m_matrix.py` straight from the matrix trades, with no extra backtest
(the matrix already ran every dial over one data load) and under its own
filename (`run_1m_matrix.variant_slug()`, so
`output/quickfix1m1dc_report_variant_05.html`). A variant worth keeping a report for
belongs IN the matrix rather than in a page built once: the hybrid stop was
left outside it and quietly aged a full grid out of date before anyone
looked (2026-08-08). Only the published baseline goes through `run_1m.py`, because that
run is also what charter's trade study reads. The rules block and the stop
sentence are GENERATED from the payload's dials, so a variant page states its
own model rather than the baseline's.

## Working agreements (carried over from charter)

- Commit straight to main.
- English only in code, variable names, comments, strings. No emoji.
- When the user supplies text verbatim, use it verbatim.
