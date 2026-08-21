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
`hybrid1m` -> `levels1m` ->
`charts`, ~8-17 min on a normal day (2026-08-21; the measured record is
`../trading_system/refresh_runtime_plan.md`). The old
`strategy` step (`run_pipeline.py`) is GONE with the daily registry. Measured
2026-08-21: run_1m ~110s, matrix ~4-12 min depending on how many markets'
files moved (per-market cache + tail splice, cached/spliced counts and a
TIMING line in its output; under a minute when nothing new landed), hybrid
stop 1s (it reads the matrix JSON), the level study ~55s, charts ~70s. The
matrix became the full factorial on 2026-08-13 (27 cells; 30 briefly, until
the extras went on 2026-08-18), quietly grew to ~30 min once the
geometry-ratio pane's series dominated, and came back down on 2026-08-21
with the ratio rewrite and the cache; `hybrid1m` builds `variant 5`,
and `levels1m` builds the baseline study. A VARIANT WITH A REPORT
BELONGS IN THE CHAIN -- a page built once ages out of date beside the
grid it came from, which is exactly what happened to the hybrid stop
before it joined the matrix. THE CHAIN LOST THREE STEPS on 2026-08-18
(`band1m28`, `band1m29`, `levels1mnl`): Lode removed cells 28-30 and the
`variant 20` level study, so nothing builds those pages any more and the
files are deleted rather than left to rot.

**`rcut1m` IS REACHABLE BUT NOT IN A FULL RUN** (user, 2026-08-12: "we're not
updating quickfix1m1dcRcut.html after clicking button. quickfix1m1dcRcut.html
will get his own update button inside the html page"). A FULL grid is ~232
engine passes, about 93 minutes; since 2026-08-19 a click usually costs far
less (exact hit in seconds, spliced tail ~20 min - see the cache block
below). `refresh.EXTRA_STEPS` holds it: `step_for()` searches it,
`run_all()` never does, so `refresh.py rcut1m` and `/api/refresh` reach it and
a plain `refresh.py` cannot. The page's own button posts that key to charter's
`/api/refresh` -- the SAME runner, driven from the page that shows the result,
so there is no second way to build anything.
**THERE ARE TWO OF THEM SINCE 2026-08-16, ONE PER STOP ANCHOR** (Lode:
"I thought the calculations happened with the 4th/5th reversal stop and
not the hybrid stop"). They were right - `BASE` carried
`stop_mode="ladder"` and the page said so nowhere, so its band read as a
fact about the strategy rather than about that stop. THE BAND READS THE
STOP ANCHOR'S OUTPUT: the ratio's numerator is level-to-stop, so
widening the stop moves every cell (audit s.19, PA 2026-08-07 0.226 ->
0.557), and a band measured on one anchor is not evidence about the
other. Same script, `--stop 4th5th` (default) / `--stop hybrid`, with the
label and dial taken from `run_1m_matrix.STOPS` so these pages and the
matrix cannot disagree about what `hybrid` means. Per anchor: its own
outputs (`quickfix1m1dcRcut4th5th.*`, `quickfix1m1dcRcutHybrid.*`), its
own trade cache, its own refresh key (`rcut1m` / `rcut1mhybrid`) carried
in the payload as `refresh_step` so A PAGE CAN ONLY REBUILD ITSELF, and
its anchor named in the title, in the first sentence and in the
definition of 1R. The 0.20/0.50 band was adopted on the 4th/5th grid; the
hybrid page opens on it for comparability only and says so. The 4th/5th
page was NOT recomputed in the split - the 231 cells, the `built` stamp
and the trade cache are the ones that were already there, restamped and
redrawn. It finds the server by probing
127.0.0.1:8000..8019 (the page is usually opened straight off disk, so it has no
origin to infer a port from), posts `text/plain` so a null origin never needs a
CORS preflight, streams the log, and reloads itself when the run finishes.
`serve.py` echoes `Access-Control-Allow-Origin` for `null` and loopback origins
only -- that is not a security control and does not pretend to be one, it just
does not hand the reply to the open internet.

**THE R-CUT CACHE IS KEYED ON THE DATA** (2026-08-12) **AND SPLICES A TAIL
SINCE 2026-08-19** rather than starting over. It was once reusing every cell
from whatever window it was first built on, so a rebuild after new bars landed
finished in three seconds and republished a stale grid beside a fresh baseline
-- measured, not hypothetical; the first cure threw the whole cache away on any
data change. Current form: `bars_manifest()` stamps every bars parquet per file
(size:mtime); unchanged = exact hit in seconds, grown-only = splice candidate
(`rebuild_tail` reruns each cell from PRIME_DAYS before the cut and
`verify_overlap` demands the recomputed overlap reproduce the cache trade for
trade -- any disagreement rebuilds the grid whole), anything else = full
rebuild. Two boundary rules added 2026-08-21 after real phantoms: the old
window's LAST day is never compared (its entries_allowed flag flips when the
roll calendar extends -- it cost a 93-min rebuild over zero changed bars), and
the cache carries `market_days` so a growth the UNION calendar hides (a second
refresh in one day filling the newest date in per market) still places its cut
via `market_gains`. Tests: `tests/test_rcut_incremental.py` (fast oracle +
RCUT_SLOW=1 real bars) and `tests/test_rcut_market_days.py`. It errs the safe
way on purpose: a wrong cache HIT costs correctness, a wrong MISS costs time,
and every refusal names its reason. The payload carries `built`, `data` and
`n_cells`, and the page prints the build time, so a stale grid is visible
rather than assumed fresh.

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
three EXTRA cells appended after them. **`wick`
IS the engine's existing `extreme` mode** (confirmed by Lode) -- one
tick beyond the session's running extreme AT ENTRY, which is the only
extreme that exists at entry -- so this cost NO engine change. Cells are
`variant 1` .. `variant 27`, the published baseline is **`variant 2`**
and it is an ordinary row: every row carries a checkbox (default on,
plus all-on / all-off) and the baseline can be switched off like any
other. Colour is a FAMILY, not an identity: hue is the stop anchor,
the shade within a hue is the band, lightness is the lockout, the two
extra BAND cells take the outermost shade of their own anchor's hue,
and the one 31-market cell is magenta -- outside every family, because
what makes it different is not one of those three dials.
**THE GRID IS THE FACTORIAL AND NOTHING ELSE** (Lode, 2026-08-18). The
three extras are gone -- `variant 28` (015-020), `variant 29` (025-065)
and `variant 30` (the market filter's off-state) -- with their reports
deleted and their refresh steps removed. Numbering below 28 did not move
and never may: variants 1..27 are read by number in the audit, in
charter's `?v=` links and in every report filename.
**THE BAND AXIS IS NESTED UNDER THE STOP ANCHOR** (same day). It was one
shared ladder, which cannot express what the re-swept grids say: each
anchor wants its own cuts, and `variant 2` and `variant 5` sit in the
SAME slot, so a shared axis would force one band on both. Each anchor now
keeps `000-050` and `full` as fixed comparison points and carries its own
chosen band in the middle slot -- **4th/5th `000-060`, hybrid `020-060`,
wick `020-050`** -- so the cross is still 3x3x3. Chosen BROAD on purpose:
the sweep's best hybrid cell was 0.45-0.55 on 36 trades with 48% of them
one market (Lode: "too narrow ... we're probably just price-fitting"),
and 0.65 was left alone for sitting on the edge of the measured region.
`run_1m.BASELINE` follows `variant 2`, so the published band is
**0.00-0.60**.


**THE GEOMETRY RATIO IS NOW READABLE AT EVERY MINUTE, NOT ONLY AT THE
TRADES THAT SURVIVED IT** (Lode, 2026-08-15, audit s.19). A refused entry
leaves NO trade, so the blotter could not say why a setup did not take,
and PA 2026-08-07 triggered 28 times between 11:25 and 16:17 and was
turned away 28 times at 0.557 with nothing on the chart to show it.
`engine_1m.ratio_series()` walks the same bars and computes the same
number at every armed minute; `run_1m_matrix.py` writes it per market to
`output/ratio/<KEY>.json` and charter draws it as a pane. Three series
cover all 30 cells because **the stop anchor is the only dial the number
depends on** - the lockout and the band decide what to DO with it, never
what it is - and they are keyed by the page's STOP LABEL (`4th/5th`,
`hybrid`, `wick`) so charter looks one up straight from `props.stop`.
**THE WINDOW HAS BEEN HALF-WIDTH ON A FIFTH OF ALL SESSIONS** (Lode,
2026-08-17, audit s.19j). A flat 24h of clock holds exactly ONE SESSION
for every market - GC 23h, LE 4.6h, measured 0.90x-1.00x across all 22 -
which is why it has worked. But where the CALENDAR has a hole it holds
only 0.42x-0.55x of a session, and a narrower range is a LARGER ratio, so
~20% of sessions were judged against half a denominator and pushed toward
the upper cut. `range_mode` is the dial: `clock` (default, unchanged) or
`trading_day`, which looks back to the same clock time on the market's
OWN previous trading date - taken from its `days` list, so nothing
defines a weekend, a timezone or a DST rule anywhere. On a normal day the
two are BIT-IDENTICAL (170,523 GC minutes, 0 different, pinned by test);
after a gap the window goes 0.50x -> 1.00x. A fixed BAR COUNT was the
wrong idea and is written up: 1440 bars is 1.04x sessions for GC and
5.24x for LE, because Databento emits a bar only for minutes that traded.
`variant 31` measures it against `variant 2` on every refresh. NOT
ADOPTED - and if it is, the band wants a re-sweep, since 0.20/0.50 was
fitted with Mondays at half width.
**RULE 2 STOPS THE TRADE, NOT THE MEASUREMENT** (Lode, 2026-08-16, audit
s.19h). A third line per side, `rule2`, carries the ratio exactly where
rule 2 shut that ladder for the session, and charter draws it PURPLE - a
real number nobody could have acted on. It is the only gap reason with a
number behind it; the rest genuinely have none. The window is judged
BEFORE rule 2 now (no usable range means nothing to draw in any colour),
so in the overlap the label moves from `rule2` to `short-window` - both
untradable, no figure moves.
**IT RETURNS `main`, `prev` AND `rule2` PER SIDE** (Lode, 2026-08-16,
audit s.19d): a session opens the evening before its own Socrates update
activates, so in that window two answers exist and the pane shows both.
`main` is the session's OWN update applied across the WHOLE session
(green/red, hindsight in that window on purpose - it is only computable
once the update lands); `prev` is the levels actually live at that
minute, emitted only until the update activates (blue, behind, NO band
colour and NO rule 2, because `allow_pre_activation=False` sets
`f = None` before the entry scan's side loop, so no trade is reachable
there on ANY levels). Where blue runs alone IS the window; where
green/red takes over IS the update. Mondays have no blue - that update
lands Saturday. Agreement is untouched: an entry needs the day's own
update live, and there `f_live is f_day`.
**TWO THINGS ARE DELIBERATELY NOT `run_market`'s** (audit s.19c, "we
like to see the line without gaps"). Rule 1 is NOT applied - `first`
is `ladder[0]` whether
or not price has tested anything, so the ratio before a ladder arms IS
the ratio the trigger gets; requiring three tested reversals cost 80% of
the line and bought nothing. Rule 1 now only breaks the TIE of which
ladder is in play (armed side first, else the SMALLER rpu), resolved
BEFORE rule 2 - resolving it after would answer 2026-08-11 with a bear
ladder 130 points from price, in green. THE TIE-BREAK MUST BE
CONTINUOUS AT THE HANDOVER (audit s.19e): picking the NEAREST first
reversal was not, and PA 2026-05-04 square-waved between 1.273 and
3.764 as price wandered across the midpoint of two far-away ladders,
swapping the whole numerator each time. The lower envelope cannot step,
and needs no threshold tuned. Coverage 8.8% -> ~88%.
Everything else MUST mirror `run_market` exactly or the pane and the
blotter disagree, which is worse than no pane: the window is pruned
BEFORE the bar joins the running extremes and appended only AFTER, and
it clears at a splice.
The binding test is agreement - `tests/test_engine_1m.py` asserts the
series' value at a trade's entry minute EQUALS that trade's recorded
`rpu_range_ratio`. It is written from the MATRIX pass and not `run_1m.py`
because that is the pass holding every market's bars already AND the pass
that ships the trades the pane sits under; a pane built from a different
run than the trades beside it would be a quiet lie.
**THREE ANSWERS, ALL DIFFERENT, TO "WHY DIDN'T IT TRADE"** (audit s.19,
worth knowing before diagnosing the next one): PA 7 and 12 Aug were the
geometry cut too WIDE; PA 11 Aug 05:27 was neither the band nor the
lockout but the pre-activation window (no active file until 07:35) and
then rule 2. And the 7/12 Aug refusals are the HYBRID STOP's doing, not
the band's - the ratio's numerator is level-to-stop, so widening the stop
to the session extreme pushes it through the upper cut (0.226 -> 0.557
on 7 Aug). **The band reads the stop anchor's output**, so a band's
evidence does not carry across stop modes unchanged. Variant 2 took both
and lost both. Related open item, NOT decided: 8 trades in the window
entered at a weekend/holiday open where the trailing window was too short
to judge, so the band never voted on them (audit s.19a).
**EVERY CELL IS VISIBLE IN CHARTER TOO** (2026-08-13): charter's 1m study
reads the matrix JSON directly and ships all 30 trade lists inside each
market's `__trades.json`, its `?v=<slug>` picks which are drawn (several at
once, told apart by dash since colour is the outcome), and the Strategy
trades box gained a `1-minute variants` section with a checkbox per cell.
Nothing new is exported from here for it -- charter reads
`quickfix1m1dc_matrix.json` the same way it already read
`quickfix1m1dc_all.json`, so the matrix run IS the hand-off.
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

**THE REPORT IS `build_1m_report.py` -> `output/quickfix1m1dc_report_variant_02.html`**
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
11.20% headline until 2026-08-08. The equity line still plots the close.
**EVERY CURVE IN THIS PROJECT IS A STEP FUNCTION ON THE MARKET DAYS**
(Lode, 2026-08-18). The balance stands still until a trade closes and
then jumps, so a line joining consecutive exit balances draws eleven days
of gain that nothing booked -- "not the correct way of visualising it,
although also not completely wrong". Two changes, both in
`run_1m.py` and shared by the report, the matrix and both R-cut pages:
`lineType: WithSteps` (today's balance held flat to tomorrow, the whole
move the vertical there), and one point per MARKET DAY out to the LAST
one instead of stopping at the last exit. **A MARKET DAY IS THE UNION**
(Lode's choice): a date ANY market in the run was open, because the
account can move on any of them and the universe holds 22 calendars --
158 days, 2026-01-02 to 2026-08-14, against GC's own 155. The drawdown
pane steps for the same reason; the daily calendar and `time in market`
are on market days too, so weekends no longer dilute the percentage.
`calendar_union` / `market_day_grid` / `place` / `carry_forward` are
pinned by `tests/test_equity_grid.py`. **ONLY THE RUNNERS CAN BUILD THE
CALENDAR**, since only they hold the bars, so `run_1m.py` and
`run_1m_matrix.py` write it into their JSON as `calendar` and the page
builders read it from there -- rebuilding it in a page would cost ~100s
of bar loading to draw a line. A JSON without it falls back to calendar
days with a printed WARNING rather than failing the refresh chain. What
this makes visible: a cell that stopped trading early used to be a
SHORTER line and read as a shorter history (`variant 28`, 18 trades, last
exit 2026-07-29, ended two weeks before every other cell), and the
published page ended at the last exit while the data ran on -- now every
curve on the matrix starts and ends on the same x and the flat tail is
counted in the chart's subtitle. **Every blotter row links
into charter's 1m study at that trade** (`trades.html?m=<Market>&t=<n>`,
1-based, charter sorts each market's trades by entry exactly as the report
does); the link needs charter's `serve.py` running. **A VARIANT PAGE'S LINKS
CARRY `&v=<slug>`** (2026-08-13, Lode found it on the hybrid-stop page): charter's
study holds one trade list per matrix cell now, and without `v` it falls back to
the PUBLISHED blotter *and indexes that* -- the chart drew the ladder stop where
the report said hybrid, and wherever the two lists diverge the link opened a
different trade (31 of variant 5's 66 rows). An index is only meaningful inside
the list it was counted in. `variant_payload()` therefore carries the cell's
`slug` and `build()` puts it in every row's href. The old dark
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
