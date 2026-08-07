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

## Status (2026-08-01)

**TWENTY-FIVE strategies.** They share rules 1-3 exactly, so they take the same setups on the
same bars and the only thing being compared anywhere in this project is where the profit is taken.

| key | Rule 4 | risk | in_grid |
|---|---|---|---|
| **quickfix** | the CAP FAMILY at **1.9R** | **1.39%**, SOLVED | yes |
| **quickfixwick** | one tick past the entry bar's own **wick** | 1.0%, chosen | no |
| **quickfixclose0** | the close of **bar 0**, the entry bar: flat the same day | 1.0%, chosen | no |
| **quickfixopen1** | the open of **bar 1**, through one night | 1.0%, chosen | no |
| **quickfixclose1** | the close of **bar 1** | 1.0%, chosen | no |
| **quickfixopen2** | the open of **bar 2** | 1.0%, chosen | no |
| **quickfixclose2** | the close of **bar 2** | 1.0%, chosen | no |
| **quickfixclose3** .. **quickfixclose20** | the close of **bar 3** .. **bar 20**, the HOLD SWEEP | 1.0%, chosen | no |

**BARS ARE NUMBERED FROM THE ENTRY BAR, WHICH IS BAR 0** (user, 2026-07-31). Twenty-three of
the twenty-five are ONE FAMILY, a bar exit parameterised by `k` = which bar it closes on, and
their keys say which. `quickfixopen1` was plain `quickfixopen` until 2026-07-31 (same rule,
same trades, renamed the day bar 2's open joined it); **quickfixclose0 keeps its bare name by
the user's explicit choice** and is bar 0 -- do not "helpfully" rename it quickfixclose0.

**READ THE REGISTRY AS THREE THINGS, NOT TWENTY-FIVE**: the cap family's default, the entry-bar
wick, and a HOLDING-PERIOD AXIS from bar 0 to bar 20 with two market-on-open settings inside it.

**THE HOLD SWEEP IS GENERATED** (user, 2026-08-01: "quickfixclose3, close4, ... 20", in the
reports, the comparison and charter). `CLOSE_SWEEP_KS = range(3, 21)`, `close_strategy(k)`
builds the `Rule4` + `Strategy`, `close_texts(k)` writes all four pieces of prose. This is the
ONLY generated Rule 4 prose outside the cap family and the split is deliberate: bars 0, 1 and 2
each say something QUALITATIVELY different (bar 0 cannot lose gross and has no live stop, bar
1's open has no live stop either but is all overnight, bar 1's close is where a live stop and a
real losing side arrive), so they keep their WRITTEN paragraphs. From bar 3 up there are no
branches left, one sentence with one number in it, so a generator is the honest form. Do not
hand-write bars 3-20 back in, and do not "unify" bars 0-2 into the generator.

**WHAT THE SWEEP FOUND, and it is the point of it**: holding longer is monotonically worse.
Win rate 65% (bar 1) -> 22% (bar 20), drawdown 4.6% -> 21.8%, trades 92 -> 72. Levered to 6%
the collapse is total: **$846k at bar 1 against a $115k-$190k band for EVERY bar from 3 to 20**,
with no second peak. Raw capital does rise again past bar 10 ($150k at bar 10 -> $288k at bar
20) and that is NOT a second sweet spot -- it is a few very large winners on a strategy that is
now wrong three times in four, and at equal drawdown it buys nothing. "One bar is where it
pays" was an inference from three points before 2026-08-01; it is now a measured curve.
The trade count falls monotonically with `k` because one position per market at a time means a
long hold BLOCKS later signals, so part of every difference along that axis is which setups
each hold was free to take. Say so whenever the axis is read.

quickfix's 1.9R / 1.39% ARE THE DEFAULTS (user, 2026-07-28) and they are the levered-optimal
point of the cap family, not a guess: 1.9R tops the constant-6%-drawdown chart, and 1.39% is
the risk that puts it exactly there (verified: 6.00%). `engine.RISK_PCT`, the reference the
variant grid is priced at, tracks it. `CHARTER_CAPS` must contain 1.9R and does.

**quickfixwick carried a different key for one day** (added 2026-07-27, retired, brought back
under its present name on 2026-07-28 because the name says what it does: it takes profit a
tick past the entry bar's WICK). The RULE is unchanged. The user asked for the old key to be
removed from the docs entirely; it is in git, and it must not come back.

**slowfix stays retired** (2026-07-28) and should not be reinstated without being asked: it
was the cap family at no cap, i.e. a dial position, never a separate method. "No cap" is
still a dial setting and the dashed reference line on both cap charts, and still the worst
point of the family at equal drawdown.

**TWO MECHANISMS, not one** (`Rule4` carries exactly one of them, and raises if given both
or neither):
- a **target POLICY** `(pos, bull, bear) -> (price, reason)`, recomputed every bar and
  resolved by `check_exit`'s shared machinery: stop first, then gaps, then ambiguity. The cap
  family and quickfixwick.
- a **BAR EXIT** `(pos, bar, k) -> (price, reason) | None`, which reads a price off the bar
  instead of watching a level, so there is no TARGET path to guess at and nothing for
  `check_exit` to resolve on that side. The twenty-three bar exits. `k` is bars since entry and
  is the family's only parameter; **k=0 is the entry bar**: a bar exit is THE ONLY THING in this
  engine allowed to close a trade there, which is what makes quickfixclose0 expressible at all.
  `engine.backtest` calls it once at k=0 right after booking the entry. `close_exit(k)` and
  `open_exit(k)` are already parameterised, so another CLOSE is one number in `CLOSE_SWEEP_KS`
  and another OPEN is one `Rule4` plus a `Strategy`. `open_exit(0)` raises (bar 0's open
  precedes the entry trigger). Nothing bounds `k` upward.

`backtest` therefore takes the whole `Rule4` object, not a bare policy (`Strategy.target` is
gone; use `s.r4`).

**THE STOP IS NOT RULE 4, AND A BAR EXIT KEEPS IT** (user, 2026-07-31: only rule 4 changes).
On every bar between the entry and the exit bar, a bar-exit strategy's stop is resolved by the
SAME `check_exit`, handed `engine.no_target` -- a policy that never has a target. There is no
second stop test anywhere and there must not be. On the exit bar the order is decided by
`Rule4.bar_exit_at`, which is REQUIRED beside a `bar_exit` for exactly this reason:
- **"open"** -> the exit resolves BEFORE the stop. The open is the bar's first price, so
  nothing can trade ahead of it (and a stop the open gapped through fills at that same open).
- **"close"** -> the exit resolves AFTER the stop. A stop triggers the moment price touches
  it; a market-on-close waits for the bell.

**THE STOP NEVER TRADES on quickfixclose0 or quickfixopen1** -- but that is a CONSEQUENCE of
those two bars, not a rule, and it does NOT survive a longer hold. quickfixclose0 is shut on
the bar that opened it, and the stop sits one tick beyond that bar's own already-spent
extreme; quickfixopen1 is shut at the FIRST price of the next bar, so nothing can trade ahead
of it. On those two the stop still **sizes** the position (1R = the stop distance), which is
its important job, but **it is not a floor under the loss** -- an adverse overnight gap takes
quickfixopen1 out for well over 1R, same arithmetic as a gapped stop everywhere else here.
On EVERY OTHER hold, quickfixclose1 through quickfixclose20, the stop IS a floor, and the
numbers show it: quickfixclose1 wins 65.2% where quickfixclose0 wins 97.1%. On the long end the
stop is what actually closes most trades -- quickfixclose20's average hold is 6.4 bars against
a 20-bar rule, so the bar exit is the exception there and not the norm.

**quickfixclose0 cannot lose on GROSS terms**, and that is the entry rule, not a flattering
assumption: the trigger requires the bar to close BEYOND the entry price, so marking out at
that same close is always on the right side of entry. Its losers are the trades whose move
was smaller than the 2 ticks of slippage. Hence 97.1% win rate, 0.06% max drawdown, and no
6%-drawdown risk at any bet size. That is a REAL result and also the loudest warning on the
whole project about the daily-proxy fill model, which is exactly how the comparison page
frames it. Do not "fix" it.

**Its `max_open` and `time_in_market` are 0 and that is correct** -- entries and exits both
land inside one day, so nothing is ever held when a day is counted. The KPI subtitles say so
("every trade shut the same day") rather than leaving a 0 that looks broken beside 105 trades.
QUICKFIXCLOSE0 ALONE: quickfixclose1 is held overnight and reads 4 and 42%.

**RISK IS 1.0% FOR THE TWENTY-FOUR QUICK EXITS** (user, 2026-07-28: "we don't need the scale of
R for these strategies but keep risk as a variable, default 1.0%"; the three added on
2026-07-31 and the eighteen added on 2026-08-01 follow it). `Strategy.risk_solved` records
whether a risk is the MEASURED 6%-drawdown one (quickfix) or a CHOSEN number (the other
twenty-four), and `solve_risk.py` prints the solve for all of them but only calls the solved
ones stale. Do not "helpfully" paste the solved numbers into the registry for the other
twenty-four.

**GAP FILLS** (user, 2026-07-27). A bar that JUMPS OVER the stop or the target fills at
**that bar's OPEN**, not at the level — the open is the day's first price, so it is the one
case where a daily bar reveals the intraday order. Applies to every strategy that watches a
LEVEL (the stop is shared machinery, and two fill models would make the comparison unfair),
and since 2026-07-31 that includes the STOP on a bar-exit strategy held past its entry bar.
What a bar exit never reaches is the TARGET half: it names a price rather than waiting for
one. A gapped stop therefore loses MORE than 1R (worst on this data: −11.68R, on an
uncapped run).

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

AUDITED when the user asked why quickfix and quickfixwick disagreed on an engulfing bar (see
README "Why two strategies can split on the same bar"): `check_exit` IS shared and both give
the doubt to the stop (quickfix 5 of 9 such days -> `unknown_pl`, quickfixwick 6 of 7). The
wins are the GAP rule firing first. They split on exactly one date, EURO_Futures 2026-05-08,
where the open fell between the two strategies' targets (1.6 ticks apart). Do NOT "fix" this
as an inconsistency -- it is one rule against two target prices. The one thing genuinely open:
`open <= target` counts an open sitting EXACTLY on the target as a gap (once today,
USD_EUR_Cross_Rate 2026-03-09 quickfixwick +0.27R); requiring a strict one-tick gap was offered
and not taken.

**RISK PER TRADE IS PER STRATEGY** (user, 2026-07-27). For quickfix that means the risk which
puts it at `engine.TARGET_DD` (6%) max drawdown: **1.39%**, a MEASURED constant in
`strategies.py` (`Strategy.risk_pct`), derived by **`solve_risk.py`**, which calls the
registry stale only when a SOLVED risk MISSES the 6% target by more than 0.05, not when it
differs from its own 3-dp solve (1.39 against a solved 1.391 would otherwise nag forever).
Re-run it and paste the numbers back after any change to the rules, the fill model or the
archive, or the reports quietly go stale. The other three carry a chosen 1.0% and are never
called stale (see `risk_solved` above). So **1R = the strategy's own percentage**; any text
saying "1R = 1%" for quickfix or "1R = 1.573%" is stale (the rules block generates it via
`strategies.entry_mechanics(risk_pct)`, a function for exactly this reason).
`engine.RISK_PCT` is a DIFFERENT thing — the REFERENCE risk the shared variant grid is priced
at and the pages self-check against; it tracks quickfix's number but nothing depends on them
being equal. `run_portfolio.at_risk()` is the context manager that sets the money
management's risk for one run and restores it.

**STREAKS ARE COUNTED IN ENTRY ORDER** (user, 2026-07-29), off **net R**, not in exit order
off dollars. The blotter is sorted by entry, so a reader counting losing rows counts entry
order; quoting the exit sequence made the report disagree with what is plainly on the page.
Found on quickfixwick: three losers opened 2026-01-29, one not closing until 2026-02-03 after
an unrelated winner closed on 02-02, so exit order split a visible run of 5 into 4. The
drawdown is still measured in exit order by `account()` -- that one IS about the order trades
closed. Keying off R rather than dollars also makes streaks risk-dial-independent, like win
rate. Both `_streaks_and_avgs` and the JS `simulate` were changed; they must stay mirrors.

**"optimized" IS QUICKFIX-ONLY in the page title** (user, 2026-07-29). Its cap and its risk
are both solved, so the word is a claim the page can back; the other twenty-four are a fixed
shape at a chosen 1%. `page_title()` keys off `risk_solved and in_grid`, not off the key.

On 2026-08-01 data, each at its published default:
**quickfix 1.9R/1.39% $338,471, 6.00% DD, 92 trades, 65.2% wr.**
**quickfixwick 1% $424,800, 7.47% DD, 89 trades, 67.4%.**
**quickfixclose0 1% $504,201, 0.06% DD, 105 trades, 97.1%.**
**quickfixopen1 1% $429,768, 4.21% DD, 92 trades, 88.0%.**
**quickfixclose1 1% $531,971, 4.62% DD, 92 trades, 65.2%.**
**quickfixopen2 1% $422,419, 11.71% DD, 88 trades, 64.8%.**
**quickfixclose2 1% $404,992, 11.89% DD, 88 trades, 55.7%.**
The sweep, same basis: **close3 $364k/12.9%/84tr/42.9%**, **close5 $289k/16.5%/82tr/37.8%**,
**close10 $151k/20.6%/77tr/24.7%**, **close15 $247k/21.7%/76tr/23.7%**,
**close20 $288k/21.8%/72tr/22.2%**.
Levered to 6% drawdown the order is **quickfixclose1 $846k (1.300%)**, quickfixopen1 $775k
(1.428%), quickfix $339k (1.391%), quickfixwick $322k (0.800%), quickfixopen2 $216k (0.512%),
quickfixclose2 $210k (0.504%), then the sweep descending from close3 $188k (0.455%) into a
$115k-$143k band for bars 6 to 20; quickfixclose0 is EXEMPT and stays at its own 1% ($504k at a
0.06% drawdown), not unrankable-and-hidden as it was before 2026-07-31. The finding of the
2026-07-31 batch was that ONE bar is where it pays and the second buys bigger winners at
roughly triple the drawdown; the 2026-08-01 sweep CONFIRMED it out to bar 20 and found no
second peak anywhere.
**THOSE LINES ARE A DATED SNAPSHOT AND ARE NOT MAINTAINED PER BAR** (user, 2026-07-28): every
one of those numbers moves with each new array day, so they are stale the next morning by
construction, and chasing it daily would be a chore with no reader. `output/report.html` is
rebuilt on every run and is the live answer. Refresh this line when a figure is quoted in a
decision, or when the rules or the fill model change; what has to stay correct here is the
STRUCTURE (the rules, the defaults, the invariants), which no new bar touches. The 1.39% risk
and the 6.00% drawdown it targets are NOT part of the daily drift — check them with
`solve_risk.py` when the sample has grown meaningfully, not every day.
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
1.39% at 1.3R, flat to 2R, 1.18% at 2.1R) and the top five settings sit within 5% of each
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
and `run_pipeline.py` (all of them in one pass over the array archive — reading it is the slow
part — then `report.html` + `comparison.html` + `conclusions.html`). `solve_risk.py` is NOT
in the pipeline: it derives the registry's solved `risk_pct` and is run by hand when it needs
refreshing.
Adding a strategy at a new cap is ONE line in `strategies.py` (`rule4=cap_rule4(3.0)`) plus
a `solve_risk.py` run for its risk; another CLOSE bar is ONE NUMBER in `CLOSE_SWEEP_KS` (the
`Rule4`, the `Strategy` and all four pieces of prose are generated, and `CHARTER_STRATEGIES` is
derived, so charter picks it up too); another OPEN bar is one `Rule4(bar_exit=open_exit(3),
bar_exit_at="open", ...)` plus a `Strategy` and NO new exit reason; a genuinely different
Rule 4 shape is a new policy factory OR bar-exit factory plus a `Rule4` with `in_grid=False`
— see README "Adding a strategy", and remember a new exit reason has to be added to
`VAR_REASONS`, `prettyReason` AND charter's `TRADE_COLORS` (or to charter's `TRADE_BY_R` if
the reason can be a win OR a loss, as the two bar-exit reasons can).
RENAMING a strategy leaves its OLD outputs on disk: only the charter hand-off prunes itself,
so `<key>_*.xlsx`, `_equity_<key>.json`, `<key>_gold_daily.json` and `equity_<key>.html` have
to be deleted by hand (done for `quickfixopen` and `quickfixclose` on 2026-07-31).
`build_equity_html.py` needs `_variants.json`, so `run_portfolio.py` must run first. `venv\`
has pandas + openpyxl (`requirements.txt`). Reference market: gold futures.
COST OF A FULL RUN, measured 2026-08-01 at 25 strategies: **~30 seconds** and ~18 MB of output
(25 pages at ~685 KB, report.html ~900 KB, 50 workbooks, 29 charter hand-offs). The archive
parse still dominates the clock, so the 18 extra backtests were nearly free; what grew is BYTES
ON DISK AND IN GIT, mostly because every strategy page ships the whole shared variant grid.
Weigh that, not runtime, before adding another block of strategies.

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

**`output/comparison.html`** (2026-07-28, user) answers the question no strategy page can and
the cap section cannot either: the cap charts sweep ONE Rule 4 shape across its own
parameter, and twenty-four of the twenty-five have no such parameter. Same two-chart argument
one level
up, across STRATEGIES instead of caps: first the real result at a constant 1% risk (panes:
capital, max drawdown, return/drawdown, win rate), then the same set levered to a constant
6% drawdown (panes: capital, risk per trade allowed, win rate). Plus one Rule 4 card per
strategy, a numbers table and a generated `Where it pays` with the yellow **Optimal point**
highlight.
- **IT SHOWS 22 OF THE 25** (user, 2026-08-02). `COMPARISON_SKIP` names the three that come
  off it and `comparison_strategies()` is what the whole page is built from, `STRATS` included
  (the page ships the trimmed list, so it has nothing to filter client-side). NOT a grab bag:
  the page compares HOLDING PERIODS and none of the three is a point on that axis — **quickfix**
  and **quickfixwick** are price targets with no bar number (quickfix has the cap dial and the
  cap charts instead, which is the sweep that fits it), and **quickfixclose0** is the one bar
  that cannot be levered to TARGET_DD at any bet size, i.e. the page's only EXEMPT bar, which
  answers a different question from every bar beside it. All three keep their own page, their
  charter overlay and their row everywhere else. The strategy SWITCHER stays complete — it is
  how you leave this page. The exemption and outlier machinery STAYS (general, and neither
  fires today); the note explaining the dagger is written by `renderExemptNote()` only when
  there IS one, so the page does not describe a marker nobody can see.
- **EVERY COUNT IS GENERATED** from the SHOWN list — the h1, both chart titles, the findings
  prose — and the bar widths and label sizes scale with it. Going from four strategies to
  seven on 2026-07-31 and to twenty-five on 2026-08-01 needed no wording change. Do not type a
  number into this page.
- **BARS, not lines** — the x axis is a list of names, not a number line, so joining them
  would imply an ordering and a rate of change between neighbours that do not exist. That
  holds even for the bar exits, which DO have a natural order: a sequence of settings is
  not a measured axis, and a line would draw bar 2 -> bar 3 (one trading day) and
  quickfixwick -> quickfixclose0 (not a distance at all) as the same step. Zero baseline
  always: a bar's length IS its value. Colour says WHICH MEASURE (capital green, drawdown
  red, risk red, ret/DD slate, win rate ink, exactly the cap charts' pane colours), never
  which strategy — the strategies are named on the axis and every bar is direct-labelled, so
  twenty-five hues would buy nothing.
- **AT TWENTY-TWO BARS EVERY LABEL IS TURNED ON ITS SIDE** (2026-08-01), names and values
  alike, and the x-axis band grows to fit them. The switch is MEASURED, not a count: it fires
  when the longest name would not fit its slot, so at seven the chart is unchanged. Dropping
  labels and scrolling the chart sideways were both rejected — a direct label on EVERY bar is
  what makes these charts work in the printed PDF, and a chart that scrolls prints clipped.
  A standing label needs its own WIDTH as vertical headroom, so when they stand up the readout
  panes grow 30px and reserve more of themselves (`head`), and a BROKEN outlier bar (already
  full height, so no headroom at all) hangs its label DOWNWARD INSIDE itself in the surface
  colour. Without both, the drawdown pane's labels were overprinted.
- **The outlier rule.** One value orders of magnitude above the rest (quickfixclose0's
  return/drawdown is ~7000x, because its drawdown is a rounding error) would flatten every
  other bar to a stub. Such a bar is scaled to the REST and drawn BROKEN at the top with its
  true value labelled and a `▲`. General, not special-cased to that pane.
- **THE EXEMPTION** (user, 2026-07-31). A strategy that cannot be made to lose TARGET_DD at
  ANY bet size is priced at its OWN published risk on the levered chart and flagged `exempt`,
  rather than drawing no bar. quickfixclose0 is the only one and always will be while its
  drawdown is ~0.06%: keep it at 1%, lever everything else. Its bars are drawn HOLLOW and
  DASHED with a **dagger** on the axis name, it is excluded from `nw` (so it can never win
  "Optimal point", which would compare two different questions), and the chartnote, the
  tooltip, the table cells and the generated prose all say why. A zero-height bar is still
  never drawn; the `n/a` branch survives for a pane with genuinely no value.
- The Rule 4 column in the numbers table carries **`class="l wrap"`**: `td` is `nowrap` by
  default and `table.trades` is `table-layout:fixed`, so a long middle column OVERFLOWS
  rather than wrapping. It was printing over the Trades figures until 2026-07-31.
- It carries a **TRIMMED** variant grid (the 22 tokens it prices, not all 99), so it is
  ~215 KB against the strategy pages' ~685 KB. It has no dial to reach the rest with.
- Reached from a **Compare** button, first in the nav's button row on every strategy page and
  on `conclusions.html`. It is NOT folded into `report.html`; keep it a page of its own.

Each strategy gets its own page `output/equity_<strategy>.html`, plus `output/report.html`
(every strategy, print/PDF). Pages carry a strategy-switcher row generated from the registry,
the **four rules** (1-3 shared text in `strategies.py`, 4 from the strategy's `Rule4`), the
**Rule 4 cap dial** under the rule cards (cap-family strategies only, so quickfix alone
today; rewrites the rule card, lede, caveat and footer from `strategies.py`'s per-cap text),
a **risk per trade**
number box (0-100%, spinners forced always-visible) that re-runs the whole shared-account
simulation client-side, and **Export PDF** (picker -> `report.html?s=...&cap=...&auto=1` -> the
browser's own print-to-PDF; no PDF library is bundled, on purpose). A **Compare** button
opens `comparison.html` (above) and a **Conclusions** button opens `conclusions.html` (two free-text fields kept in localStorage, also passed in
the URL hash because file:// documents may not share storage) whose text prints at the END of
the exported PDF. Both page types come from
one stylesheet + one markup section + one renderer FACTORY (`mountReport(root, DATA)`), so
the report mounts several strategies without a second renderer.

**ONE MONEY-MANAGEMENT REPLAY, page-wide.** `simulate()`, `statsAt`, `riskForDrawdown` and
the per-token `LEVERED` cache were hoisted out of `mountReport` into **`CORE_JS`** on
2026-07-28 so `comparison.html` could call the same code instead of carrying a second port of
`run_portfolio.py`'s loop. `mountReport` binds it to its own section with
`sim = (risk, rows, lite) => simulate(risk, rows || RAW, lite, START)`. Do not let a second
copy appear; that is the same rule the cap charts' `lite` flag exists for. Note that top-level
`const` is shared across `<script>` blocks, so a name declared in `CORE_JS` must not be
re-declared in `REPORT_JS` or the page dies at load. Entries use reversal levels
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
   drawdown fans 6.0% to 36.7%, so a wider cap's bigger return is partly the deeper hole it
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
are not caps: `wick`, `close0`, `open1`, `close1`, `open2`, `close2`, then `close3` .. `close20`
-- 24 today, DERIVED from the registry's non-grid Rule 4s, never typed) in one `v` table: same
packing, same replay. Two bar-exit reasons live in `VAR_REASONS`, appended: **`exit_close`**
and **`exit_open`**. They name the ORDER TYPE, not the bar, so ALL 23 bar-exit strategies
share them and a 24th would need no new reason -- that is deliberate, the reason is what the
ledger says HAPPENED and "sold at the close" is the same event on bar 0 or bar 2. Both are
charged the LIMIT slippage rate in `cost_in_r`, not the stop rate, because a
market-on-close and a market-on-open are orders whose TIME IS KNOWN IN ADVANCE and can be
worked, unlike a stop fired into a move nobody chose the timing of. **THAT IS AN ORDER-TYPE
ARGUMENT, NOT A LIQUIDITY ONE** (corrected 2026-08-06, Lode: the day's volume peaks are the
OPEN and the SESSION CLOSE, and the "close" these strategies exit on is the SETTLEMENT, which
is neither -- so on that side the 1 tick is if anything optimistic; the open exits do land on
a genuine volume peak). The RATE did not change, only the reason for it. At 2 ticks round
trip that choice is the difference between a winner and a loser on
quickfixclose0's smallest trades, so it is a real assumption, not a detail. A bar-exit trade
that is STOPPED out is charged the stop rate like any other stop.

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
- `CHARTER_STRATEGIES` — EVERY non-cap strategy, 24 today, **DERIVED from the registry**
  (`[s.key for s in REGISTRY if not s.r4.in_grid]`) since 2026-08-01 rather than typed: a new
  bar exit reaches charter with no second edit and a retired one cannot linger. The CAPS above
  stay a CHOSEN handful, because there the registry is the wrong source (75 points, charter
  wants five). Unlike the caps these are worth drawing TOGETHER: their exits land on genuinely
  different BARS, not just different prices on one bar, so they fan out across the days after
  the entry instead of off one point. Charter lists boxes in FILENAME order, so they come out
  alphabetically (quickfixclose10 next to quickfixclose1), not in hold order.

The exporter PRUNES hand-off files it no longer owns, because charter globs the directory and
a leftover file keeps being drawn.

Charter globs them, draws each as `trades_<key>`, and its **T** rail button opens a box with
a checkbox per overlay (labelled with its Rule 4 + trade count) — **29 today**, up from 11 on
2026-08-01. All are drawn
IDENTICALLY — one dotted line, one round exit marker (`TRADE_STYLE`, was `TRADE_STYLES[i%4]`)
— because ALL of them share Rules 1-3 and therefore enter on exactly the same bars, caps and
non-caps alike; read them one tick at a time. The BAR EXITS are the overlays whose
exit BARS fan out across the days after the entry rather than sitting on one, and that fan now
runs to twenty bars, which is what makes reading them together worth 29 boxes. 29 is a lot of
checkboxes and is NOT the same problem as exporting the cap grid: each bar exit shows something
the others cannot, where 75 caps would stack 75 identical markers on one point. Show a few at a
time. Colour is always the OUTCOME, never which
strategy, so `target_bar` is the same green as `target_r` in charter's `TRADE_COLORS`. The
two BAR-EXIT reasons are the one case that cannot name its own colour — `exit_close` and
`exit_open` cover a win and a loss alike — so charter lists them in **`TRADE_BY_R`** and
`trade_color()` reads their colour off the trade's own `r`. That is the faithful reading of
"colour is the outcome", not an exception to it. Every hold past the entry bar also draws
ordinary red `stop` exits, because their stop is live -- and on the long end most exits ARE
stops (quickfixclose20 averages 6.4 bars against a 20-bar rule). A **quickfixclose0** trade
enters and exits on
the SAME bar, so its line is vertical and both markers sit on one bar: correct, and the only
overlay that does it. Do NOT export the whole cap grid: it is affordable in bytes but
illegible, since 75 overlays stack 75 identical entry markers on one point.

Not yet done: intraday price data (IBKR) to replace the daily-proxy fill assumptions.

## 1-minute workstream (2026-08-03, standalone — NOT in the registry)

`engine_1m.py` + `run_1m.py` + `tests/test_engine_1m.py` implement
**quickfix1m1dc v2**: rules 1-2 evaluated INTRADAY on 1-minute bars
(rule 3 REMOVED 2026-08-06 - target-era logic), market-order entry when
the first reversal prints (2 ticks slippage), ladder-anchored stop (one
tick beyond the 5th reversal, 4th when only four; ladder must carry 4),
R denominated level-to-stop, exit at next-day settlement. Baseline dials
(run_1m.BASELINE): no tightening, no pre-activation entries, **no
confirmation clause**, ladder stop, **session lockout at 1**.
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
no data_end exits), and the live baseline is **134 trades, 41.0% wr, +53.22R,
11.20% max DD, $162,415**. Figures quoted from
before that date are pre-correction; the shape of the arguments survived, the
numbers did not.
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
else. Deliberately NOT integrated into the 25-strategy registry, pages,
variant grid or charter hand-off until the results earn it. venv gained
pyarrow and pytest for this (requirements.txt updated). Run the tests
with `venv\Scripts\python.exe -m pytest tests -q`.

**THE REPORT IS `build_1m_report.py` -> `output/quickfix1m1dc_report.html`**
(2026-08-06, Lode: "so I can look up the different trades", in the format of
the daily reports). It rebuilds from `quickfix1m1dc_all.json` alone, no
backtest, and carries the v2 rule block and dials, the KPI row, the three
lightweight-charts panes, per-trade statistics, the EXIT-CLASS anatomy, the
full 153-row blotter, the per-market table and the daily calendar. It
**imports `build_equity_html.CSS`** so the look cannot drift from the daily
pages, but NOT `mountReport`: that renderer is bound to the registry and the
variant grid, and this strategy is outside both, so the tables are rendered
in Python and the only script is the panes plus a table sorter. Its money is
`run_1m.portfolio_replay` MIRRORED (the trades' own `pnl_usd` / `cash_after`
are PER MARKET, a different account) and the build warns if its final capital
or drawdown drifts from what `run_1m` published. **Every blotter row links
into charter's 1m study at that trade** (`trades.html?m=<Market>&t=<n>`,
1-based, charter sorts each market's trades by entry exactly as the report
does); the link needs charter's `serve.py` running. The old dark
`quickfix1m1dc_equity.html` and `run_1m.build_html` are GONE (2026-08-06) --
the report says everything they said.
`build_1m_report.py --variant hold+hybrid` builds a report for ANY cell of
`run_1m_matrix.py` straight from the matrix trades, with no extra backtest
(the matrix already ran every dial over one data load) and under its own
filename. Only the published baseline goes through `run_1m.py`, because that
run is also what charter's trade study reads. The rules block and the stop
sentence are GENERATED from the payload's dials, so a variant page states its
own model rather than the baseline's.

## Working agreements (carried over from charter)

- Commit straight to main.
- English only in code, variable names, comments, strings. No emoji.
- When the user supplies text verbatim, use it verbatim.
