# quickfix1m1dc - trade-review audit

Status: FOR DISCUSSION (Lode + Claude), 2026-08-05. No engine change happens
before the discussion. Evidence: manual review of 21 of the 137 trades (GC 9,
BTC 2, ZW 10) on the corrected 1m trade study; every claim below was
re-verified against exchange bars, engine code, or the array files - nothing
rests on a chart impression alone. Agreed process: discuss this audit ->
implement chosen variants -> rerun -> report -> re-inspect ALL trades from
scratch on the new baseline.

Framing (Lode): gold is not representative - it wins for every strategy. The
problem to solve is EQUITY-CURVE DRAWDOWN FROM LONG LOSING STREAKS, so losers
weigh more than winners in every judgment below, and losing-streak length is a
first-class metric in the reports.

## 1. Verified findings

### 1.1 Fill model - the biggest number-mover

Current model (v1, documented as the "fill honesty" open item): rules arm, a
1-minute bar CLOSING beyond the first reversal triggers, and the fill books AT
the reversal price on that same trigger bar. That demands confirmation that is
only knowable at the bar's close while booking a price only a limit resting
BEFORE the bar could have gotten. The honest model: confirmation first, then a
resting limit at the level, filled only if a later bar trades back to it.

Bar-verified classes across the 21 reviewed trades:

| Class | Cases | Consequence |
|---|---|---|
| Honest, delayed fill | GC1 (+3min), BTC1 (+18min), BTC2 (+10min), GC7 (+1h33) | same price, later timestamp - survives honest model |
| PHANTOM (never refilled) | GC3 (+5.04R booked), GC9 (+1.01R), ZW6 (+1.80R) | trade does not exist live; ~+8R of booked profit is fiction in just 21 trades |
| Suspect thin fill | ZW8 | single-print touch; fill uncertain |
| Update-switch fill far from market | GC3 (booked 70 points below market at the 07:35 switch) | worst subclass: level-price fill when price is arbitrarily far past the new level |

Phantoms can only FLATTER the backtest: a phantom books exactly when price ran
away from the level - the winning direction. The honest curve is strictly more
loser-heavy than the published one.

Missed-winner ledger (Lode): never-filled honest limits are kept as their own
list, not just dropped - they become immediate winners the day a faster entry
path exists (e.g. intra-minute updates, ~4 data batches/second).

### 1.2 Stops

Current: intraday stop = entry +- 1.5x (entry-to-running-session-extreme),
min 1 tick; at entry-day settlement a confirmed trade's stop tightens to the
day extreme +- 1 tick. R stays denominated in the entry stop distance.

Evidence rows from the review:

- GC1: 1.5x stop died at 07:12 in level-zone chop; ladder-anchored stop
  (beyond 5th reversal) turns it into a winner.
- GC4: killed by the TIGHTENED stop at 22:46; overnight peak 4783 vs 5th
  reversal ~4788 - the ladder stop survives by ~5 points into a winner.
  The tightening, an anti-overnight-risk feature, killed a trade the
  structural stop would have saved.
- GC6: loses under every stop variant (honest counterweight; keep such cases).
- GC7: the ladder stop is TIGHTER than 1.5x and still holds - this is not a
  "wider stops" proposal, it is structure-anchored invalidation.
- BTC2: Lode's instinct = stop one tick above the ladder-test high = exactly
  stop_mult 1.0 + tick, the tight end the GC pilot sweep already favoured.
- ZW7: cluster-anchored stop (below 4th, wide 4->5 gap) loses; 5th-reversal
  stop wins big. The cluster idea needs its gap definition tested, not assumed.
- Cascade: GC2, GC5, ZW8 exist only because their predecessors stopped out.
  Any stop change changes the TRADE LIST -> all comparisons are equity-curve
  vs equity-curve at equal risk, never per-trade.

### 1.3 Rule 2 - verified working, one open question

ZW Apr 24: all 921 tradeable minutes refused by Rule 2 on both ladders
(day_open 622.0 >= second 617.125 overnight; >= 621.0 after activation - a
4-tick near-miss). Correct per the shared daily rules; the refused short would
have won. Open question (deeper cut - touches shared rules 1-3): is the 00:00
session open the right anchor for a ladder that only activates at 07:35, or
should the verdict for a fresh ladder use the price at its activation?

### 1.4 Timing model - verified clean end to end

- Array files are NAMED for their DATA date d: the file stamped Apr 27 carries
  Apr 27's completed session bar tick-exact, so it was scraped the morning of
  d+1. Levels activate d+1 07:35 UTC. run_1m always assumed this - correct.
- STANDING DATA CONTRACT (Lode, flagged BEFORE the 1m build and bypassed once -
  never again): the reversals belong to the date in the file's SECOND COLUMN,
  not the filename date. Robustness improvement: parse that column directly
  instead of deriving stamp+1.
- The daily engine pairs each bar with the PREVIOUS file's levels - no
  look-ahead in either engine.
- The 1m chart drew every level one day early (keyed by file date); fixed
  2026-08-05, charter commit adde5d8. Review impressions made before that fix
  about "outdated window" entries need re-reading; ZW 1-3 were on the freshest
  available file (Monday has NO update - Saturday's file already carries
  Friday's data; the next fresh file lands Tuesday ~06:23).

### 1.5 Chart/data items (fix with the implementation batch, no debate needed)

- ZW/ZC (eighths) and ZN (64ths) levels are drawn on the 1m chart in raw
  Socrates notation (e.g. 620.5 drawn where the true price is 620.625; ZN up
  to ~0.35 off). Decode with the same PRICE_CODEC as run_1m in chart_1min.py.
- DECISION FOR LODE: the daily site draws file d's levels on day d's bar (the
  day they were computed FROM, not the day they applied to). Display
  convention - keep or shift by one day like the 1m pages.

## 2. Experiment matrix (after discussion)

All variants are full engine reruns (slot-blocking makes post-processing
invalid). Judged at 1% risk on: net R, max equity drawdown, LONGEST LOSING
STREAK, win rate, trade count, final cash; secondary: solve_risk-style
leverage to 6% drawdown. Portfolio level first, per-market table beside it.

- E1 FILL DIAL: level-price (current) vs resting-limit-after-trigger.
  Switch-fills flagged as their own class. Report adds: phantom count,
  delayed-fill stats, missed-winner ledger.
- E2 LIMIT LIFETIME (only under resting-limit): until next activation /
  until trigger-day settlement / N minutes. Cancel means THIS trigger's
  order; a persisting level may re-arm on a fresh trigger.
- E3 STOP MATRIX: {mult sweep 1.0-3.0} | {ladder-last: 1 tick beyond the
  LAST reversal of the active ladder, 4 or 5} | {cluster: 1 tick beyond the
  reversal cluster, gap-detected} x tightening {on | off}. Cluster gap
  candidates (hindsight-free, k swept): k x median ladder spacing, k x
  entry-to-extreme distance, fixed fraction of price. Also decide: does
  settlement-tightening still apply on top of structural stops, or only
  when tighter?
- E4 OVERNIGHT-WINDOW DIAL: entries allowed before the day's activation
  (current) vs blocked until activation. Note: blocking kills ALL Monday
  entries until Tuesday (no Monday update exists).
- E5 RULE-2 ANCHOR (run only if Lode wants it - touches shared rules):
  day open (current) vs price at ladder activation.

Staged execution so results stay attributable:
1. E1 alone -> the honest baseline (expected: fewer trades, lower net R,
   truer drawdown).
2. E3 on top of the honest baseline (stop family x tightening).
3. E4 and E2 on the winner of stage 2.
4. E5 only after explicit approval.

## 3. Report (after reruns)

One comparison page: overlaid equity curves per variant; a table with the
metrics above; the fill-class table; the missed-winner ledger; per-market
deltas vs the current published run. Then discussion round two, pick the new
baseline, and restart the full manual inspection of every trade on the trade
study.

## 4. Decisions wanted from Lode

1. Approve the staged order (or reorder).
2. Cluster "gap" definitions to include in E3.
3. Tightening semantics on structural stops (off / only-if-tighter / always).
4. E5 (Rule-2 anchor): include or park.
5. Limit-lifetime candidates for E2.
6. Daily-site level-day convention (1.5).

## 5. DECISIONS (Lode, 2026-08-06) - the v2 model

- E1/E2 CLOSED by a model change: entry is a MARKET ORDER the moment the
  first-reversal price trades - no limit orders, no fill uncertainty, no
  phantoms, no missed winners, no limit lifetime. Flat 4 ticks adverse
  slippage on every entry (an average; the roadmap replaces it with IB
  streaming, ~4 value batches/second - the 1m chart is a visual
  validator, we model acting in real time).
- RISK stays denominated on the FIRST-REVERSAL price to the stop, never
  on the slipped entry.
- STOP: always one tick beyond the 5th reversal; beyond the 4th when only
  four exist. A setup requires at least 4 reversals. No cluster/gap logic
  (parked). Stop-above-daily-high remains only as the TIGHTENING dial.
- E3 reduced to {tighten | frozen}; E4 stays {window | blocked}. 2x2.
- E5 RESOLVED, no experiment: the DAY OPEN stays the anchor; each new
  ladder is judged against the same day open when it activates (current
  engine behavior). A new ladder invalidates old-ladder setups; entries
  fire only off the ACTIVE file's first reversal (also current behavior).
- Daily-site level drawing stays AS-IS (deliberate visual: a reversal
  starts on the previous day's bar because the daily bar cannot show that
  the level was alive during the morning half of its own day). Both
  charts are now correct in their own terms.
- Monday clarification (Lode): the Saturday-landing file IS Monday's
  update (its second-column date is Monday). Blocking the overnight
  window must NOT block Mondays - encoded as: entries require the active
  file's publish (data) date >= previous trading date.

Implementation assumptions to confirm (constants, trivial to flip):
- MIN_REVERSALS (tested) stays 3; MIN_LADDER = 4 is the new requirement.
- "5th reversal" = 5th level of the eligible ladder (file levels beyond
  prev_close), counted from the first.

## 6. v2 implemented and the 2x2 rerun (2026-08-06)

engine_1m v2: touch-trigger (level must PRINT in the bar, or the bar
gaps past it - fill from the open), 4-tick slipped market entries,
ladder stop, tighten/window dials; 15 synthetic tests green. Two bugs
the first matrix run exposed, both fixed: ICE sentinel prices leaked
through a low/high-only filter into bar OPENS (CC booked a 9.2e9 entry;
all four OHLC fields now sanitized in run_1m), and the first
touch-trigger fired when price was merely BEYOND the level rather than
the level printing (CC longs 600+ points past the reversal).

Portfolio results (1% risk, shared-account replay):

| variant | trades | wr% | netR | longest losing streak | max DD | final |
|---|---|---|---|---|---|---|
| tighten+window | 141 | 29.1 | +17.39 | 9 | 24.08% | $114,188 |
| tighten+blocked | 132 | 28.8 | +18.35 | 8 | 24.27% | $115,248 |
| frozen+window | 137 | 30.7 | +17.67 | 9 | 23.13% | $114,554 |
| frozen+blocked | 130 | 30.8 | +19.25 | 7 | 23.32% | $116,336 |

frozen+blocked leads on every priority metric (fewest trades, highest
wr, most net R, shortest losing streak). Exit mix (frozen+blocked): 63
stops, 50 close1, 17 no_confirm. Stars: ZW +18.97R, DX +16.55R;
worst: ZB -7.02R, ZC -5.85R, FGBL -4.98R, ES -4.72R. Full details:
output/quickfix1m1dc_matrix.{json,html} (run_1m_matrix.py).

The per-trade REPORT for the inspection round is
output/quickfix1m1dc_report.html (build_1m_report.py, 2026-08-06): the
rules and dials, the KPIs, the exit-class anatomy, the full blotter, the
per-market table and the daily calendar, with every blotter row linking
into the trade study at that trade. output/quickfix1m1dc_matrix.html
stays the variant comparison this section asked for.

Superseded: the trade study fed off the v1 blotter when this was written.
It now carries the current baseline - charter's `site/1m/*__trades.json`
and `output/quickfix1m1dc_all.json` agree at 153 trades (post-rule-3,
section 9), so the full manual re-inspection can start on it.

## 7. Slippage revision (Lode, 2026-08-06): 2 ticks entry, 2 ticks stop

Entry slippage 4 -> 2 ticks, stop-exit slippage 3 -> 2 ticks (settlement
exits stay 1 tick). Same trades, same dials; only costs moved. The full
model, per exit class:

| class | entry | exit | round trip |
|---|---|---|---|
| stop | 2 ticks | 2 (`SLIP_STOP_TICKS`) | 4 |
| close1 (day-2 settlement) | 2 ticks | 1 (`SLIP_SCHEDULED_TICKS`) | 3 |
| no_confirm (entry-day settlement) | 2 ticks | 1 | 3 |

Entry slippage is charged in the PRICE (the fill is moved 2 ticks adverse);
the exits are charged in R as a cost. R stays denominated on the
first-reversal-to-stop distance, never on the slipped entry.

WHY 1 TICK ON A SETTLEMENT EXIT, stated correctly (Lode, 2026-08-06): it is
an ORDER-TYPE argument. The time is known in advance, so the order can be
worked, unlike a stop fired into a move nobody chose the timing of. It is
NOT the liquidity claim the daily engine's docs used to make - the day's
volume peaks are the OPEN and the SESSION CLOSE, and settlement (~13:30 ET
on GC) is neither. So the 1 tick is if anything optimistic here, which puts
it on the same list as everything else in section 8: execution is a
first-order part of this edge, and the settlement exit is the side of it we
have not yet measured against real fills. Rate unchanged, reason fixed;
same correction applied to `run_portfolio.py`, README and CLAUDE.

The 2x2 at the new costs:

| variant | trades | wr% | netR | longest losing streak | max DD | final |
|---|---|---|---|---|---|---|
| tighten+window | 141 | 30.5 | +30.31 | 8 | 18.57% | $129,760 |
| tighten+blocked | 132 | 28.8 | +30.81 | 8 | 18.84% | $130,371 |
| frozen+window | 137 | 32.1 | +30.41 | 7 | 17.67% | $129,948 |
| frozen+blocked (baseline) | 130 | 30.8 | +31.54 | 7 | 17.95% | $131,386 |

The two ticks of slippage were worth ~12R across 130 trades - the
strategy is highly slippage-sensitive, which is exactly why the IB
streaming entry path matters on the roadmap.

## 8. Where this stands (Lode's assessment, 2026-08-06)

The strategy is PROBABLY WINNING, and the slippage experiment proved that
PROFESSIONAL EXECUTION of entries and exits is a first-order component of
the edge, not a detail: two ticks per side moved net R by ~12R, final
cash by ~$15k and max drawdown by 5+ points on identical trades. The
equity curve shows signs of hope, but the drawdown (~18%) is still too
explicit for practical use, and the win rate (~31%) must improve for
this to become a valuable strategy.

What the baseline's anatomy says about WHERE the win rate lives:

| exit class | trades | wins | net R | avg R |
|---|---|---|---|---|
| stop | 63 | 0 | -75.06 | -1.19 |
| no_confirm | 17 | 0 | -8.71 | -0.51 |
| close1 (survived to day-2 settlement) | 50 | 40 | +115.31 | +2.31 |

A trade that SURVIVES to the next-day settlement wins 80% of the time at
+2.31R average. The whole win-rate problem is the 63 stop-outs (48% of
all trades) bleeding -1.19R each - slippage makes a full ladder-stop
loss cost MORE than 1R. The no_confirm class already works as a cheap
abort (half-R average). So "better win rate" concretely means: fewer
entries that reach the ladder stop - entry-quality filters, invalidation
research (the parked cluster/gap study), or exit-before-stop logic -
NOT squeezing more out of the winners.

Candidate directions for the next research round (open, no decisions):
- Entry-quality filters that predict the stop class (e.g. room between
  first reversal and the ladder top relative to recent range).
- The parked cluster/gap invalidation, aimed specifically at cutting the
  -1.19R average of the stop class.
- Execution: every tick of real-world slippage saved goes straight into
  the stop class's worst losses - the IB streaming entry path
  (ib_live_session_notes.md) is part of the strategy, not plumbing.

## 15. The wide-cluster cell, measured (2026-08-10)

Lode asked for the variant s.14 describes, in his own words "really a gamble
... basically for the fun, and yet we're going to learn something", expecting
the drawdown to get WORSE. It got better, and the sweep says something more
useful than the single cell did.

Built as an ENGINE DIAL (`max_rpu_range_ratio` / `min_rpu_range_ratio`,
engine_1m), not a blotter filter, because a refused entry does not spend the
session-lockout allowance and a later minute may trigger instead. It rides in
run_1m_matrix.py as the cell `no wide clusters` so it is re-measured on every
pass rather than ageing in a page of its own (the s.10 lesson). Mechanics and
their justifications are in the engine docstring: trailing 24h wall-clock
window of bars strictly before the candidate minute, reset at a contract
splice, abstaining below MIN_RANGE_BARS (60) rather than refusing on a short
window.

| | baseline | no wide clusters (> 0.50) |
|---|---|---|
| trades | 137 | **89** |
| win rate | 40.9% | 41.6% |
| net R | +52.31 | **+60.61** |
| longest losing streak | 7 | 7 |
| max DD | 11.20% | **8.21%** |
| final | $160,979 | **$174,938** |

Checks that the project's own standards demand, all three passed or reported:

- **NOT one market.** Deltas spread across the book - ZB +3.43R, NG +2.13R,
  SI +2.00R, HG +1.90R, GC +1.38R - with real losses beside them (LE -2.63R,
  ZW -2.20R). Unlike the lockout, whose entire gain traced to wheat.
- **Almost no cascade.** Only 2 new trades appear (+2.83R); 50 are removed,
  netting -5.47R, and **20 of those 50 were winners**. So the mechanism is
  s.14's, exactly: not removing losers, removing a class whose winners are
  too small to pay for its losers.
- **`refused_wide` counts TRIGGER EVENTS, not trades** (1098 of them): the
  same level re-prints many times in a session. The trade-count effect is the
  48 net. `range_unjudged` was 7 in the whole sample, so the abstain path is
  rare.

**THE THRESHOLD SWEEP IS THE REAL RESULT.** 0.50 was read off a table of
outcomes, so some improvement was guaranteed by construction; the question is
whether the effect is smooth or a knife-edge at the chosen number:

| cut | trades | wr% | netR | streak | maxDD% | final |
|---|---|---|---|---|---|---|
| off | 137 | 40.9 | +52.31 | 7 | 11.20 | $160,979 |
| 1.50 | 136 | 40.4 | +52.30 | 7 | 11.20 | $160,966 |
| 1.00 | 125 | 40.8 | +53.98 | 7 | 10.28 | $163,602 |
| 0.75 | 115 | 40.9 | +57.43 | 7 | 10.88 | $168,885 |
| **0.60** | 103 | **41.7** | +60.46 | 7 | 8.93 | $174,136 |
| **0.50** | 89 | 41.6 | **+60.61** | 7 | 8.21 | $174,938 |
| 0.40 | 72 | 37.5 | +48.38 | 5 | 6.22 | $155,240 |
| 0.35 | 65 | 33.8 | +38.16 | 5 | 6.22 | $141,176 |
| 0.30 | 55 | 32.7 | +36.00 | 5 | 5.89 | $138,441 |

A PLATEAU, not a spike: monotone improvement from 1.50 down to 0.50-0.60,
graceful decay upward toward "off", and a hard collapse below 0.40 - which is
s.14's 15-50% band defending itself, since cutting into it destroys the edge.
The plateau is what a real property looks like; the exact peak is still
sample-chosen and 0.60 keeps 14 more trades for the same net R.

**THE SAME SWEEP AT A CONSTANT 6% DRAWDOWN** (Lode asked for it immediately,
and he was right to: comparing at a flat 1% flatters whichever variant was
allowed to dig the deepest hole, because a shallower curve can simply be bet
bigger. solve_risk.py's argument and its method - DD rises monotonically with
risk, so bisect - applied to run_1m.portfolio_replay.)

| cut | trades | wr% | netR | streak | DD@1% | final@1% | risk for 6% | final@6%DD |
|---|---|---|---|---|---|---|---|---|
| off | 137 | 40.9 | +52.31 | 7 | 11.20% | $160,979 | 0.535% | **$130,445** |
| 1.50 | 136 | 40.4 | +52.30 | 7 | 11.20% | $160,966 | 0.535% | $130,437 |
| 1.00 | 125 | 40.8 | +53.98 | 7 | 10.28% | $163,602 | 0.585% | $134,850 |
| 0.75 | 115 | 40.9 | +57.43 | 7 | 10.88% | $168,885 | 0.551% | $135,095 |
| 0.60 | 103 | 41.7 | +60.46 | 7 | 8.93% | $174,136 | 0.676% | $146,994 |
| 0.50 | 89 | 41.6 | +60.61 | 7 | 8.21% | $174,938 | 0.725% | $151,300 |
| **0.40** | 72 | **37.5** | +48.38 | **5** | 6.22% | $155,240 | 0.964% | **$153,040** |
| 0.35 | 65 | 33.8 | +38.16 | 5 | 6.22% | $139,616 | 0.964% | $139,616 |
| 0.30 | 55 | 32.7 | +36.00 | 5 | 5.89% | $138,441 | 1.020% | $139,234 |

**THE RANKING FLIPS.** 0.40 looked like a failure at flat 1% (+48.38R against
+52.31R) and wins at equal pain, because a 6.22% drawdown can be bet nearly
twice as large as an 11.20% one. The whole 0.40-0.60 region lands at
$147-153k against the baseline's $130k - about 15% more money for the same
drawdown.

**FOUR CAUTIONS, and they matter more than the ranking.**

1. **It does not fix the win rate, and the equal-pain winner makes it
   WORSE.** No cut anywhere beats 41.7% at 1% risk, and 0.40 - the best cell
   at 6% - runs 37.5% against the baseline's 40.9%. This dial trades win rate
   for curve smoothness, which is a different bargain from the one s.8 asked
   for.
2. **THE EQUAL-PAIN METHOD REWARDS HAVING FEWER OBSERVATIONS.** Levering to a
   MEASURED drawdown bets bigger precisely where the estimate is thinnest:
   0.30's 5.89% comes from 55 trades against the baseline's 11.20% from 137,
   and the method answers by roughly doubling the stake on the weaker
   evidence. The daily project's own caveat - max drawdown is "the most
   sample-dependent statistic in the project" - applies here with a leverage
   multiplier sitting on top of it. The $153,040 is honest arithmetic on this
   sample and is the first number that would break out of sample.
3. **The spread inside 0.40-0.60 is not resolvable.** $147k to $153k is ~4%
   on 137 trades over seven months. A broad region beats the baseline at
   equal pain; where the optimum sits inside it, this sample cannot say.
4. **Correction to an earlier claim in this section:** the losing streak does
   NOT stay at 7 everywhere. It holds across the 0.50-0.75 plateau and drops
   to **5** at 0.40 and below - so the deeper cuts do shorten the streak,
   which is the drawdown mechanism Lode actually cares about. That is the
   strongest thing in favour of the deep end, and it arrives together with
   the worst win rates.

### 15a. What was actually found: profit factor, not win rate (Lode, 2026-08-10)

Lode's reading, and it is the right one: *"We were looking to increase the win
rate in order to get a softer DD. But what we stumbled on is that we have
possibly solved the problem in one go. We do have the softer DD, and it's not
with getting the win rate up but with filtering the too wide R's out. And it
makes perfect sense; when the R is too wide in $ then there's simply not
enough projected $ profit to make it worth the trade. So we're probably
looking at a higher profit factor."*

Measured, and the hypothesis holds:

| variant | n | wr% | gross win R | gross loss R | profit factor | avg win | avg loss | expectancy |
|---|---|---|---|---|---|---|---|---|
| baseline | 137 | 40.9 | 131.84 | 79.53 | **1.66** | +2.35 | -0.98 | +0.382 |
| no wide clusters | 89 | 41.6 | 117.34 | 56.74 | **2.07** | **+3.17** | -1.09 | **+0.681** |
| hybrid stop | 133 | 43.6 | 109.82 | 71.48 | 1.54 | +1.89 | -0.95 | +0.288 |
| no lockout | 156 | 37.8 | 144.92 | 100.46 | 1.44 | +2.46 | -1.04 | +0.285 |

Profit factor 1.66 -> 2.07 and expectancy per trade nearly DOUBLES, 0.382R ->
0.681R, while the win rate moves 0.7 of a point. The whole gain is average
WINNER SIZE (2.35R -> 3.17R); the average loss even worsens slightly.

**THIS CORRECTS SECTION 8.** That section concluded "so 'better win rate'
concretely means: fewer entries that reach the ladder stop ... NOT squeezing
more out of the winners". The available lever turned out to be the winners
after all - not by squeezing them, but by declining trades that STRUCTURALLY
CANNOT produce a fat one. The softer drawdown followed from that, without the
win rate ever rising. Note also the hybrid-stop cell in the same table: the
best win rate in the grid (43.6%) and the WORST profit factor of the three
lockout-1 cells, which is the same lesson from the other side.

### 15b. The first-principles version, which is what could make it a RULE

The measured threshold still comes from an outcome table. But Lode's economic
argument has a form that does NOT: **this strategy has a FIXED TIME EXIT** (the
next day's settlement), so the R-multiple it can possibly earn is bounded by
how far price travels in the holding window divided by R. That is arithmetic,
available before any P&L:

| 1R as a fraction of a day's travel | a full day's move is worth |
|---|---|
| 0.20 | 5R |
| 0.33 | 3R |
| 0.50 | 2R |
| 1.00 | 1R, before slippage |
| 1.50 | 0.67R - 1R is UNREACHABLE on a perfect day |

So a wide ladder does not have a lower PROBABILITY of paying; it has a
mathematically CAPPED payoff under this exit rule, while its downside stays a
full -1R. That is exactly the asymmetry the numbers show: wide trades keep a
normal win rate, because the far stop is rarely hit, and produce tiny winners
(band avg R 0.2-0.4 above 0.60 against 1.0-1.2 below 0.30, s.14).

Stated as a requirement it reads: **the ladder must leave at least N R of room
inside one day's normal travel.** Demanding 2R lands on 0.50, 3R on 0.33, 1.5R
on 0.67 - so the arithmetic supplies a REASON for a threshold in that region
without proving any particular number. That is the footing rule 3 never had,
and it is derived from the strategy's own exit rather than from its results.
Choosing N is the open decision; it should be argued from the exit rule and
the traded range, never fitted to the curve.

### 15c. The R-cut report, and why the LOWER cut matters (2026-08-10)

`build_1m_rcut_report.py` -> `output/quickfix1m1dcRcut.{json,html}`: pick a
lower and an upper cut in 0.10 steps, see that band's equity curve and metrics
against all trades. 136 combinations, one engine pass each (56 min; a band is
its own run, see the top of s.15), every cell levered to 6%.

**Every one of the ten best cells has a LOWER cut of 0.20**, which no
one-sided sweep could have shown. The neighbourhood, final at 6% DD:

| lower \ upper | 0.30 | 0.40 | 0.50 | 0.60 | 0.70 | 0.80 | none |
|---|---|---|---|---|---|---|---|
| 0.00 | 139k | 153k | 151k | 147k | 140k | 135k | **130k** |
| 0.10 | 139k | 153k | 151k | 147k | 140k | 135k | 130k |
| **0.20** | 174k | **193k** | **195k** | 169k | 166k | 155k | 156k |
| 0.30 | thin | 106k | 119k | 118k | 117k | 115k | 110k |
| 0.40 | thin | thin | 139k | 128k | 125k | 118k | 113k |

The leading cell **0.20-0.50**: 75 trades, **48.0% win rate** (baseline 40.9),
+66.23R, avg +0.88R, DD 5.65%, streak 5, $194,633 at equal 6% pain - and the
top market falls to **DX at 21%** against the baseline's **ZW at 49%**. The
whole 0.20 row shows that dilution (21-25%), which is the most encouraging
statistic in the exercise: the edge stops being one market's.

**The win rate finally moves here.** No one-sided cut beat 41.7%; the band
reaches 48.0%, and 0.40-0.50 reaches 54.5% on 33 trades. So the original target
IS reachable - through both cuts together, not either alone.

**WHY the lower cut works, verified rather than assumed - and it is NOT that
those trades lose.** Comparing 0.00-0.50 against 0.20-0.50 trade by trade: the
19 removed sub-0.20 trades made **+22.49R**, and their removal unlocked **5 new
trades worth +28.11R** (DX +10.07, USO +7.97, YM +5.98, ZW +5.18, one -1.09
stop). Five trades out-earned nineteen. The sub-0.20 setups were not bad
trades - **they were spending the one-entry-per-session allowance before a
better-proportioned setup appeared in the same session.** Lode's defence of the
compact clusters was right; the reason to decline them is not quality but
OPPORTUNITY COST.

That makes the lower cut a SLOT-ALLOCATION policy, not a quality filter, and it
completes a coherent two-sided story in which both ends follow from the rules
rather than the curve:
- **below ~0.20**: the payoff ceiling is high (a day's travel is worth >5R) but
  the stop sits inside ordinary noise, so the ceiling is rarely reached - and
  under the lockout the attempt costs the session's only entry.
- **~0.20 to ~0.50**: ceiling 2-5R AND a stop outside routine noise.
- **above ~0.50**: the stop is safe but the payoff is capped under 2R by the
  fixed exit (s.15b).

**AND THE HONEST LIMITS, which are heavier here than anywhere above.**
1. **The lower cut is a RIDGE, not an optimum.** Rows 0.00 and 0.10 are
   IDENTICAL on every metric (the sub-0.10 trades never win a slot anyway), and
   row 0.30 COLLAPSES to 106-119k. The result depends on the 0.20-0.30 band
   being included and the 0.10-0.20 band excluded - a one-step discontinuity,
   not a smooth region.
2. **Five trades carry the mechanism.** +28.11R rests on four winners, one
   trade per market. The MECHANISM (slot pre-emption) is logic and is durable;
   the MAGNITUDE is noise.
3. **Two fitted parameters now, not one.** Picking both cuts off this grid
   doubles the rule-3 exposure of s.15's single threshold.
4. **The lower cut exists only BECAUSE of the session lockout.** Remove
   `max_entries_per_session=1` and slot scarcity disappears with it, so these
   two rules interact - neither can be judged alone.

### 15d. The refined grid, and what is parked for next time (2026-08-10)

The R-cut report was refined to 0.05 steps where the grid turns (lower
0.10-0.30, upper 0.40-0.70): 21 edges, 231 combinations, every cell levered to
6%. `build_1m_rcut_report.py` -> `output/quickfix1m1dcRcut.{json,html}`.

Best cells, minimum 30 trades, at equal 6% pain:

| band | n | wr% | netR | PF | W/L streak | max pos | top market | final@6% |
|---|---|---|---|---|---|---|---|---|
| **0.20-0.55** | 80 | 47.5 | +66.54 | 2.50 | 5W/5L | 4 | DX 20% | **$194,769** |
| 0.20-0.50 | 75 | 48.0 | +66.23 | 2.58 | 5W/5L | 3 | DX 21% | $194,633 |
| 0.20-0.40 | 58 | 44.8 | +54.00 | 2.51 | 3W/4L | 3 | DX 25% | $193,039 |
| 0.20-0.45 | 73 | 46.6 | +62.85 | 2.50 | 4W/5L | 3 | DX 22% | $187,908 |
| all trades | 137 | 40.9 | +52.31 | 1.66 | 6W/7L | 5 | ZW 49% | $130,445 |

The half-steps earned their runtime by showing that **the upper cut is a
PLATEAU, not a point**: 0.40 through 0.55 all land within a few thousand
dollars, so nothing hangs on the exact value. The lower cut at 0.20 stays the
sharp RIDGE of s.15c. Concurrent exposure also falls from 5 positions to 3-4,
so the better cells put less on the table at once - something the equity curve
alone never showed.

**PARKED FOR NEXT TIME (Lode, 2026-08-10): the lower cut's 0.00-0.15 region,
with a slightly WIDER STOP.** Those are the compact ladders whose stop sits
inside ordinary noise (s.14) and which spend the session's only entry before a
better setup appears (s.15c) - but they carry the highest payoff ceiling in the
book, since a day's travel is worth more than 5R there (s.15b). A wider stop
would buy survivability at the cost of R per move, which is exactly the trade
the hybrid-stop cell lost on in s.10 - but that was measured across ALL
geometries, never on this class alone. Worth its own run: `stop_mode` or a
stop multiplier, applied only where the geometry ratio is below ~0.15.

Status at the time of 15d: MEASURED, NOT ADOPTED, but the case has changed
shape. The measurement
is still a 137-trade sample whose net R is 49% one market (ZW - visible on
every cell of the R-cut report), the equal-pain view rewards variants with
fewer observations (caution 2 above), and 15b is an argument, not yet a
definition with an N behind it. s.14's parked order stands - the trade review
builds the vocabulary - but the geometry ratio has gone from "a filter read off
a table" to "a candidate with a derivation", which is a different thing.
SUPERSEDED the same day by 15e below: the UPPER cut is adopted, the lower is
not.

### 15e. ADOPTED: lower 0.00, upper 0.50 (Lode, 2026-08-10)

The geometry cut moves from measured to ADOPTED, into the published baseline
(`run_1m.BASELINE`: `min_rpu_range_ratio=0.00, max_rpu_range_ratio=0.50`).
Lode's reading of the R-cut grid, and the decision that follows from it:

- **The upper cut is capped on hard evidence.** When 1R is too large a
  fraction of the 24h range there is not enough potential profit left inside
  the fixed settlement exit to be worth the risk, so the setup is skipped
  entirely and the session screens for the next one. That is s.15b's
  derivation (payoff capped below 2R above 0.50, downside a full -1R), and
  the sweep agrees from the other side: shifting the band toward high
  lower/upper values finds no profit, decay is monotone above the plateau,
  and the plateau itself (0.40-0.55, s.15d) means nothing hangs on the exact
  number.
- **Very low values are also costly** - the 0.20 row of the grid beats the
  0.00 row on every metric, and s.15c showed why (slot pre-emption under the
  session lockout, not trade quality). The optimal band on this sample is
  0.20-0.50.
- **The lower cut stays 0.00 anyway.** The 0.20 ridge is a one-step
  discontinuity carried by five trades (s.15c honest limits 1-2), and the
  sub-0.20 class carries the highest payoff ceiling in the book. That region
  deserves its own investigation - the parked wider-stop run of s.15d -
  before any lower cut is adopted. Adopting only the defensible half keeps
  the fitted-parameter count at one.

What adoption changes, everywhere at once: the published baseline
(`quickfix1m1dc_all.json`), the report the baseline builds, charter's 1m
trade study (fewer trades, renumbered blotter links), and the dial matrix,
whose cells all sit on the new baseline - with two watch-cells riding along,
`no geometry cut` (the pre-adoption engine, so the case for the cut is
re-measured on every pass instead of resting on the sample it was adopted
on) and `band 0.20-0.50` (the researched optimum, under investigation, not
adopted). The R-cut report stays the research record; its header carries the
adopt decision and it opens on the adopted cell.

## 14. Path analysis of the baseline, and the two quality filters (2026-08-09)

An observational round over the 137-trade baseline (40.9% wr, +52.31R): every
trade's minute-by-minute path recomputed from the on-book bars - MAE/MFE in R,
time to each, entry-hour, and risk distance against the prior 24h range.
**Everything here is a per-trade estimate, not an engine rerun**; an earlier
exit frees a market slot and the lockout counts entries, so only a rerun can
price any of it. The estimates are for choosing which reruns are worth doing.

**Exit-before-stop is a NEGATIVE result, and it closes that branch.** Section
8 named "exit-before-stop logic" as a candidate; the paths say no mechanical
form of it pays:

- Abort at -X R: at every X in 0.3-0.8 the killed winners cost more than the
  saved stops (best case ~-15R). The survivors chop deep before winning: 33
  of 72 close1 trades went >= 0.5R adverse first and netted +65R together;
  even the >= 0.9R-MAE band (a hair from the stop) is net positive (9 trades,
  5 wins, +5.4R).
- Breakeven stop once the trade reaches +Y R: negative in every cell of
  {Y: 0.5-1.5} x {stop at 0 / -0.25 / -0.5R}; best cell still -6.2R, because
  20 close1 winners also revisit entry after being +1R up and then win.

Chop through the entry zone is intrinsic to entering at a reversal that gets
retested. Same verdict as section 10 reached for stop anchors, now from the
trade paths: the win rate has to come from ENTRY SELECTION.

**The give-back class, quantified:** 19 of 65 stops were up >= +1R before
dying (ZC 04-30 short: +3.25R, stopped 32h later; ZW 07-23: +2.15R in 24
minutes). A third of the stop class is formerly-winning trades, worth eyes
during the manual review - but per the above, the mechanical protections
measurably fail; anything that ever addresses this class must be structural.

**Ladder geometry against recent range: BOTH TAILS ARE BAD, FOR OPPOSITE
REASONS.** The measure is `rpu / prior-24h range`: the price distance of 1R
(first reversal to ladder stop) over the high-low of the 24 wall-clock hours
before entry. Dimensionless, knowable at entry, no look-ahead.

| rpu / prior-24h range | n | wr | avg winner | best win | avg loser | net R | slippage as % of R |
|---|---|---|---|---|---|---|---|
| < 0.15 | 7 | **0%** | - | - | -1.28 | -8.96 | **13.96%** |
| 0.15-0.30 | 36 | 33.3% | **+4.94R** | +13.41R | -1.04 | +34.33 | 4.47% |
| 0.30-0.50 | 38 | 52.6% | +2.24R | +5.75R | -1.08 | +25.29 | 5.63% |
| > 0.50 | 55 | 41.8% | **+1.10R** | +5.14R | -0.82 | -0.82 | 2.05% |

The seven sub-0.15 trades, all shorts, all stopped: USO 03-04 (8.4%), YM
05-06 (10.2%), 6J 05-01 (10.5%), ZW 07-23 (11.9%), USO 03-31 (13.3%), ZC
07-23 (14.1%), ZB 02-13 (14.9%). SIX OF THE SEVEN WERE UP >= +1.4R FIRST, so
the mechanism is not "wrong from the start, chopped at the entry" - the
trades worked, and a normal pullback of the winning move reached a stop
sitting only 8-15% of a day's travel away.

**LODE'S VERDICT (2026-08-09), and the data backs it: do NOT filter the
compact end.** Reviewing YM 1, 6J 2, ZW 9 and USO 7 on the trade study he
would eliminate none of them - they are correct setups, and USO 7 is the
archetype: an unlucky stop on a trade whose upside was large. The economics
say the same thing. A small $R is exactly what makes a win lucrative:
average winner +4.94R at 15-30% against +1.10R above 50%, and 29% of the
sub-15% trades reached +2R at some point against 9% of the wide ones. The
wide end is the real profitability problem - it wins 41.8% of the time,
about the portfolio average, and earns nothing, because a fat R denominator
books few R per move (the hybrid-stop lesson of section 10, arrived at from
the other direction). So the class is not "bad setups": it is HIGH-VARIANCE,
HIGH-PAYOFF, EXECUTION-CRITICAL setups on which we hold 0 for 7 - at that
sample size, near-zero information. **The filter dial proposed here on
2026-08-09 is withdrawn.**

**TRANSACTION COSTS: LODE WAS RIGHT, AND THE FIRST ANSWER HERE WAS THE WRONG
DENOMINATOR.** This section first reported slippage as a share of 1R - 14% in
the sub-0.15 class against 2% above 0.50 - and concluded that costs pressed
hardest on the compact trades. Lode: the slippage is paid either way, so what
matters is its share of the PROFIT the class actually produces; at a huge $R,
a $1 round trip against a $1 win is 100% of the profit. That is the right
denominator, and it inverts the conclusion. Full cost per trade = entry slip
(charged in the price, so buried inside gross R: `|entry - entry_first| /
rpu`) plus `cost_r` (the exit slip, charged in R):

| rpu / prior-24h range | n | cost/trade | total cost | gross R | net R | cost as % of GROSS |
|---|---|---|---|---|---|---|
| < 0.15 | 7 | 0.279R | 1.95R | -7.00 | -8.96 | n/a (no gross edge) |
| 0.15-0.30 | 36 | 0.110R | 3.95R | +38.29 | +34.33 | **10%** |
| 0.30-0.50 | 38 | 0.132R | 5.00R | +30.29 | +25.29 | **17%** |
| > 0.50 | 55 | 0.050R | 2.74R | +1.92 | -0.82 | **143%** |

Both measures are true and they answer different questions: cost per unit of
RISK is worst in the compact class (0.279R/trade, the biggest per-trade drag
in the book), cost per unit of PROFIT PRODUCED is fatal in the wide class,
where 2.74R of costs consume a 1.92R gross edge. On winners alone the share
is 2.7-3.5% in every bucket, which is why the effect is invisible per trade
and only appears at class level - and why the "% of net" instinct found it
where "% of R" did not.

The refinement that matters for the argument: the wide class's gross edge is
only **+1.92R over 55 trades** (+0.035R/trade BEFORE costs). So execution did
not ruin a good class - the class has almost no gross edge to begin with, and
costs then push it under. That is a stronger case against wide clusters than
the net figure alone, and unlike the net figure it does not depend on the
slippage assumptions being exactly right.

**What cannot be unseen, and what it is not:** on this series the money sits
between 15% and 50% (74 trades, +59.6R) and both tails are dead. Coincidence
or not, it is in the record. It is NOT yet a rule: the buckets were drawn
after seeing the outcomes, and 7 and 55 trades of a seven-month sample decide
the two edges. Reading a band off that table is precisely the curve-fitting
this project removed rule 3 for. A geometry requirement has to be DEFINED
first - from the rules and from looking at charts - and only then measured.
If the definition needs the outcome table to justify it, it is not a
definition.

**THE AGREED DIRECTION (Lode, 2026-08-09): two quality filters, both parked
until the trade review is complete.**

1. **Reversal quality** - what makes a ladder a good setup, as a property of
   the levels themselves. Geometry against recent range is ONE slice of it,
   and the open question is which way it points: compact clusters carry the
   payoff, wide ones carry the survivability, and "it could even be the WIDE
   clusters we are after" is explicitly still on the table. Vocabulary not
   yet built: spacing regularity, ladder depth, whether the cluster has been
   tested and held before, where price sits inside the ladder at entry.
2. **Instrument quality** - price-data quality per market, bar density being
   one component. Lode: some markets in the report are visibly not tradeable
   the moment their 1m chart is opened. Expected low-hanging fruit, and
   independent of (1); the two share nothing but their purpose.

Both wait for the full manual review, because the review is what builds the
vocabulary for defining them without leaning on the backtest outcome.

**A MEASUREMENT ERROR TO NOT REPEAT (2026-08-09).** A first pass at instrument
quality counted the 1-minute bars falling inside each trade's 24h lookback and
read the low numbers as thin data. It was wrong, caught by Lode against the
charts. That count measures SESSION LENGTH and WEEKEND OVERLAP far more than
liquidity: URA's "21 bars" was a Monday 13:51 entry whose previous 24 hours
were Sunday plus 21 minutes of Monday - URA trades a normal 389 bars/day; LE's
"275" IS its ~4.5h session, identical on all nine of its trades. Measured
correctly as median bars per TRADING day, only two markets are genuinely thin:
**WEAT at 120** (of a ~390-minute session, 31% coverage) and **BTC at 180**
(of ~1380, 13%). Any instrument-quality metric must normalise by the market's
own session, and must never be computed from a window that can straddle a
weekend.

**Late entries do not lower the win rate - they shrink the winners.** First
6h after activation: 64 trades, 40.6% wr, +44.2R. Later: 61 trades, 41.0%
wr, +6.6R. Same wr, a third of the R - so not a wr lever and not a filter
candidate under this project's framing, but the edge concentrates in the
fresh window, which weighs on the IB streaming path's priority.

**Portfolio note:** the worst days are now -2 to -3R pairs (the lockout
capped the intraday tail; streak 7 accumulates ACROSS days). On 06-22 the
pair was DX short + 6E short - near-mirror instruments, one macro bet in two
slots.

## 13. The window reaches 2026-08-06 (2026-08-08)

The data had been standing still without anyone noticing. data_center's
`WINDOW_END` was frozen at the pilot's PURCHASE window (2026-08-02), which
capped the whole live chain: the fingerprint could not see an array day past
it, so `refresh_1m` never extended a roll calendar, so it never bought a
1-minute tail. The daily charts kept moving while the 1-minute series stopped
at 2026-07-31. Fixed upstream (data_center `1fce946`, `WINDOW_END =
date.today()`), calendars extended and re-fingerprinted, and 20 markets now
carry 1-minute bars through 2026-08-05/06.

Checked BEFORE republishing, because a longer window is only worth having if
it is correct: bars, settlements and array files all reach 2026-08-06 (SB, DX
and FGBL to 08-05, and those three have no statistics by design); the
calendar's `last_date` excludes the partial Aug 7 evening session rather than
half-counting it; and entries stay blocked on each segment's last day.

The rerun is **purely additive - 6 trades added, 0 removed, and not one
pre-existing trade's R moved**, which is the strongest evidence that the
extension is an extension and not a reshuffle. Five are new August sessions
(PA, PL, PA, NQ, ES). The sixth is **6J short 2026-07-31 17:45**, which was
previously refused because Jul 31 was a segment's LAST day; with the calendar
running to Aug 6 that day is mid-segment and the entry stands. There are no
`data_end` exits at all, so the window-end forced-exit bias did not bite.

| | through 2026-07-31 | through 2026-08-06 |
|---|---|---|
| trades | 128 | **134** |
| win rate | 41.4% | 41.0% |
| net R | +55.34 | +53.22 |
| longest losing streak | 7 | 7 |
| max drawdown | 11.20% | **11.20%** |
| final | $165,921 | $162,415 |

The six new trades are -2.12R together, which is the entire difference. The
lockout matrix moves with it and its ranking does not: lockout 1 134 trades /
41.0% / +53.22R / streak 7 / 11.20% / $162,415, lockout 2 146 / 39.0% /
+42.91R / 16.66%, no lockout 153 / 37.9% / +45.36R / streak 8 / 14.99%. The
repeat class is unchanged to the decimal (2nd trade of a market-day still 12
trades at 16.7% for -10.30R), because the new sessions produced no
same-session repeats.

The daily refresh has since carried the window to **2026-08-07**, two trades
further, and the shape held again: baseline 136 trades, 41.2% wr, +53.32R,
streak 7, 11.20% DD, $162,579. Section 10's hybrid cell was added to the same
pass. Figures dated earlier than this in the tables above are the record of
the measurement on the day it was made, not a claim about today's window.

Inherited unchanged and still open: the CC/KC/SB/DX roll calendars were frozen
on volume that counted off-book blocks, and FGBL's volume flip sits one day
before its 06-05 boundary. See section 12's closing note.

## 12. Off-book prints were in the bars (2026-08-07)

Lode: "some markets don't show the 1m chart properly, for example FGBL."
The chart was the symptom; the cause was in data_center. XEUR and IFUS
publish each minute TWICE, on-book and off-book (`*.XOFF` block trades
reported off-exchange), and every parquet writer selected columns without
`publisher_id`, so the two became indistinguishable duplicate minutes.
charter's charts broke on it (lightweight-charts needs strictly ascending
unique times) and THE BACKTEST TRADED ON IT: 25 trades came from the five
affected markets and 12 had an off-book print on their entry or exit
minute. 14,613 FGBL off-book minutes either widen the bar's range or trade
when the book did not, so a level touch or a stop could be triggered by a
price nobody could have hit.

Fixed in data_center (`BAR_COLUMNS`, `load_bars()`,
`rebuild_publisher_bars.py` re-deriving from the raw DBN already on disk -
no repurchase, no row lost). Both consumers now read through `load_bars`.

**The ground for the fix is UNTRADEABILITY, and that is the whole of it for
this project**: a block negotiated away from the book is not a price our
orders could have hit, so the engine and the charts must not see it.
A second argument was offered here on 2026-08-06 and was WRONG AS STATED -
"Socrates itself excludes off-book prints" holds for **XEUR only**. It came
from FGBL (session H/L matching its daily bar 97.2%/98.6% on-book-only
against 88.7%/83.1%, which does retire the old "vendor clips the extremes"
caveat) and does not generalize: on IFUS the Socrates OPEN matches the
OFF-BOOK row, verified over the sessions carrying both rows at CC 52 of 67
against 4 on-book, SB 27 of 30 against 14, KC 46 of 67 against 45. That is
why data_center's `trade_session_bars()` deliberately reads the RAW frame -
the fingerprint reproduces what the vendor DISPLAYED, while we trade what
the book offered. Nothing in this project reads those session bars, and
every bar the 1m engine sees is on-book only, so the correction changes no
number here. See data_center's CLAUDE.md.

**Every published figure moved, and all of them for the better** - which is
what you would expect when phantom triggers and phantom stop-outs come out:

Both columns are measured on the SAME window (to 2026-07-31), which is the
point of the comparison; the live baseline has since extended to 2026-08-06
and 134 trades, see section 13.

| | contaminated | corrected |
|---|---|---|
| trades | 132 | 128 |
| win rate | 39.4% | **41.4%** |
| net R | +42.51 | **+55.34** |
| longest losing streak | 6 | 7 |
| max drawdown | 14.55% | **11.20%** |
| final | $146,382 | **$165,921** |

The lockout matrix was rerun on the corrected bars and the decision holds,
now with the drawdown improvement it did NOT have before: lockout 1
11.20% against no lockout 14.99%, where on the contaminated series the two
were 14.55% and 14.70%. Section 11's honest limits were written on the
contaminated run; the shape of its argument survives, the specific figures
in it do not.

## 11a. WHY the lockout exists (Lode, 2026-08-07) - read this before 11b

The measured improvement is not the reason for the rule, and the rule does
not stand or fall with it. Lode, in his own terms:

> The lockout is not just a rule we came up with to improve the overall
> metrics of the backtest. The most important thing is that this rule will
> PROTECT THE PORTFOLIO FROM THE WHIPSAW EFFECT DURING A SINGLE SESSION.
> What we saw with wheat, the 5 consecutive losses on one day, contributes
> to a deeper drawdown. The other markets didn't even have a chance to
> soften the drawdown with a winning trade, because the 5 losses all
> happened intraday. And when a market does that 5 times in a day, it could
> also do it 10 times in a day. It's simply not yet in our source data
> series. With the lockout we prevent all of that. Yes, we're throwing away
> winners in return. But we're not creating rules that fit the better
> outcome. We make rules only because they make sense.

Three things follow, and they are why this rule is different in kind from
the cap or the stop dials:

1. **It bounds a tail the sample has not shown us.** Five same-session
   stop-outs on one level is not a limit the strategy respects, it is the
   worst case that happened to occur in seven months. Nothing in the rules
   stopped it at five. The lockout makes the per-market, per-session loss
   bounded BY CONSTRUCTION at one R, which is a property of the rule rather
   than an observation about the data.
2. **Intraday clustering is the drawdown mechanism, not trade count.** Losses
   spread across markets and days get interleaved with winners that soften
   the curve; five losses inside one session in one market arrive with
   nothing in between. That is why the same R can dig a deeper hole
   depending on WHEN it arrives, and why the equity curve is the right thing
   to judge it on.
3. **The cost is accepted with eyes open.** It throws winners away (USO's
   repeats were +8.78R) and section 11b shows the sample's whole net-R gain
   is one market. That is not the argument. A rule that caps a tail is worth
   paying a known price for; a rule that only shows up as a better backtest
   number is curve-fitting, and this project has removed rules for exactly
   that reason before (rule 3, section 9).

So: keep the lockout even if a later sample shows its measured edge shrink
toward zero. The thing to watch is whether the CAP still binds, not whether
the R total still flatters it.

## 11b. Verdict on corrected bars (Lode, 2026-08-07)

Lode, once section 12's data fix landed: "we can eventually see that the
theory was indeed right. Lockout 1 did make a significant improvement in
drawdown, and it improved significantly on all metrics. I knew that when
getting the win rate higher that everything would fit in eventually."

That is the right read of the headline, and the clean bars make the pattern
SHARPER than the run the rule was decided on. Which trade of the market-day
it is, no lockout, corrected bars:

| | trades | win rate | net R | avg R |
|---|---|---|---|---|
| 1st | 134 | **41.0%** | +53.22 | +0.40 |
| 2nd | 12 | **16.7%** | -10.30 | -0.86 |
| 3rd | 5 | 20.0% | +5.39 | +1.08 |
| 4th+ | 2 | 0% | -2.94 | -1.47 |

The 2nd trade's win rate was 21.4% on contaminated bars and is 16.7% on
clean ones. And the lockout now beats no-lockout on every metric at once:
134 v 153 trades, 41.0% v 37.9%, +53.22R v +45.36R, streak 7 v 8, **11.20%
v 14.99% drawdown**, $162,415 v $149,347. The win-rate-first thesis is what
carried it: the rule does nothing but delete a class that wins 16.7% of the
time, and everything else follows.

**WHAT THE SAMPLE STILL WILL NOT SAY, and it is the same limit as before.**
Leave wheat's six repeats out by hand and take everything else:

| | trades | wr | net R | streak | max DD | final |
|---|---|---|---|---|---|---|
| no lockout | 153 | 37.9% | +45.36 | 8 | 14.99% | $149,347 |
| minus WHEAT's repeats only | 147 | 39.5% | +53.83 | 7 | **9.77%** | $162,783 |
| minus all repeats (the rule) | 134 | 41.0% | +53.22 | 7 | 11.20% | $162,415 |

Removing one market's one session gets a BETTER drawdown than the rule
does. The other 13 repeats are +0.62R together and their removal costs 1.4
points of drawdown, because USO's repeat winners were cushioning it. So the
honest statement is: the theory named the right class and the prescription
is sound, the class is genuinely bad wherever it appears (16.7% over 12
trades), and on THIS sample the whole measured gain still traces to
2026-04-27 in wheat. That is an argument for keeping the rule and watching
it, not for believing the +7.86R. Prospective trades are what settle it.

## 11. The session lockout (Lode, 2026-08-07)

Lode, reading wheat trades 1-5 on the trade study - five stop-outs in one
session on one level: "when a market oscillates like this between the exact
same reversals it's the worst possible outcome for us", with the hypothesis
that a cluster tested many times is less likely to produce the immediate
move. Understand it before changing anything, so `research_1m_levels.py`
measured the published baseline first (page:
output/quickfix1m1dc_levels.html). It groups every trade by market, side,
first reversal price and LEVEL RUN (the consecutive files carrying that
level), and counts both ATTEMPTS (another trade) and TESTS (another touch,
traded or not; a maximal run of minutes containing the level).

**The hypothesis as stated did not survive, and something sharper did.**

- Trading a level AGAIN is not itself bad: 1st attempts 37% wr for +9.29R,
  repeats 35% for +25.27R. Banning re-entry on a level after a loss would
  have removed +12.60R of profit.
- The TEST count predicts nothing: 13+ prior tests is flat (+0.74R over 68
  trades), 7-12 is the best bucket (+22.69R), and within a session 4+ tests
  before entry is the best of all (+37.31R over 101).
- The leak is the SAME SESSION. 1st trade of a market-day: 132 trades,
  39.4%, +42.51R. 2nd: 14 trades, 21.4%, -10.39R. 3rd: 5 trades, 20%. 4th
  and 5th: 2 trades, 0%. Every same-session repeat in the sample was a
  re-attack of the SAME level, so both framings collapse into one.

THE RULE: **`max_entries_per_session`, default 1** - at most one ENTRY per
market per session, expiring at the session boundary. Deliberately NOT part
of rules 1-3 (those describe what the chart must show; this is a fact about
our own previous trade, the family of one-position-per-market), and
deliberately counting ENTRIES rather than exits.

**That entry/exit distinction is worth 19R.** A position carried in from the
previous session and stopped intraday does NOT spend today's allowance: nine
trades sit in that case, +19.10R with 6 winners, including the sample's
biggest (ZW +13.41R, entered 12 minutes after the previous day's position
was stopped). Locking a session on any intraday exit would delete all nine.
Being stopped out of yesterday's trade after a fresh session and a fresh
update is not the same event as re-attacking a level that just chopped you.

| variant | trades | wr% | netR | streak | max DD | final |
|---|---|---|---|---|---|---|
| **lockout 1 (NEW BASELINE)** | 132 | **39.4** | **+42.51** | **6** | **14.55%** | **$146,382** |
| lockout 2 | 146 | 37.7 | +32.12 | 6 | 19.53% | $131,798 |
| no lockout | 153 | 36.6 | +34.56 | 8 | 14.70% | $134,426 |

The engine rerun reproduced the blotter-level estimate to the decimal, which
is itself a finding: this rule has NO cascades. It only removes trades that
follow a first entry in the same market-day, and the lockout then keeps that
market shut, so the trade list under the rule IS the first-of-day subset.

RERUN ON CORRECTED BARS (section 12) AND THE EXTENDED WINDOW (section 13):
lockout 1 134 trades / 41.0% / +53.22R / streak 7 / **11.20%** DD /
$162,415; lockout 2 146 / 39.0% / +42.91R / 16.66%; off 153 / 37.9% /
+45.36R / streak 8 / 14.99%. The ranking is unchanged and the drawdown case is
STRONGER than it was here - on the contaminated series the lockout barely
moved drawdown (14.55 against 14.70), on clean bars it takes 3.8 points off.

**HONEST LIMITS, and they matter more than the table.** The net-R gain is
one market, and this survives the data correction: of the 19 removed trades
(21 before it) wheat is 6 and **-8.47R**, more than the whole -7.86R.
Without wheat the other 13 are **+0.62R**, a wash. USO's repeats made
+8.78R on their own. So the case for the rule is the SHAPE of the equity
curve, not the total. What DID change with clean bars is the drawdown: it
was 14.70% -> 14.55%, "does not fix the motivation", and it is now
14.99% -> 11.20%. Nineteen trades still decide it; treat it as provisional
and re-check as the sample grows.

Left open, both from the research: the grouping keys on the FIRST REVERSAL
price while Lode's language was about the CLUSTER, so a re-attack that fires
off a neighbouring level currently counts as a fresh episode; and the level
runs say nothing yet about WHY a cluster stops repelling price.

Note on reading the page later: every figure above was measured on the
PRE-LOCKOUT baseline, which is the evidence the rule was decided on. The
page rebuilds from whatever blotter is current, so on the live baseline its
same-session cuts are empty BY CONSTRUCTION - the rule deleted the thing
the page exists to show.

**THE NO-LOCKOUT PAGE IS THEREFORE KEPT AS A PAGE OF ITS OWN** (Lode,
2026-08-07): `research_1m_levels.py --variant "no lockout"` builds the same
measurement off that cell of the matrix and writes
`output/quickfix1m1dc_levels_no_lockout.{json,html}` beside the baseline's,
labelled as a dial setting that is NOT what runs. On corrected bars it has
147 trades and **19 episodes that traded more than once**, wheat's
`LLLLL` at 620.625 among them. Any matrix cell works the same way. The
pre-lockout page in git at commit 1761f5a is the CONTAMINATED-bar version
and is superseded by this one for every purpose except reading the history.

## 10. The confirmation clause is gone, the ladder stop stays (2026-08-06)

Two questions from reading USO 2026-03-13 (a no_confirm abort at -0.96R,
four cents short of its stop, on a day whose session high had passed the
stop 29 minutes BEFORE the entry existed):

1. should the stop sit beyond the session's running extreme rather than
   only beyond the ladder?
2. does the confirmation clause make sense at all?

The clause had NEVER been measured: it arrived with the v1 design, sat in
no experiment (E1-E5 covered fill, limit lifetime, stops, window, rule-2
anchor), and had two behaviour tests and no economics. Both questions
became dials (`confirm`, `stop_mode`) and the matrix was rerun as
{confirm, hold} x {ladder, hybrid, extreme}, everything else at the
baseline.

| variant | trades | wr% | netR | streak | max DD | final | stop/abort/day-2 |
|---|---|---|---|---|---|---|---|
| confirm+ladder (old baseline) | 153 | 30.7 | +26.63 | 8 | 17.78% | $124,827 | 70/23/60 |
| **hold+ladder (NEW BASELINE)** | 153 | **36.6** | **+34.56** | 8 | **14.70%** | **$134,426** | 82/0/71 |
| confirm+hybrid | 144 | 32.6 | +16.92 | 8 | 19.21% | $115,454 | 58/25/61 |
| hold+hybrid | 143 | 39.9 | +24.84 | **6** | 16.78% | $124,415 | 69/0/74 |
| confirm+extreme | 172 | 26.2 | +8.49 | 11 | 29.14% | $104,238 | 97/23/52 |
| hold+extreme | 169 | 30.8 | +17.52 | 10 | 24.11% | $113,519 | 107/0/62 |

Levered to a 6% drawdown, the same order: hold+ladder $113,556 at 0.391%
risk, confirm+ladder $108,549 (0.327%), hold+hybrid $108,533 (0.344%),
down to confirm+extreme $101,401.

**THE CLAUSE COSTS MONEY, on an IDENTICAL set of 153 entries** - neither
dial changes which trades are taken here, so this is a rare like-for-like
comparison with no cascade distortion. Dropping it improves net R, win
rate AND drawdown at once. Mechanism: the 23 aborted trades, carried
instead, cost -2.70R rather than -10.64R (12 stopped, 11 reached the
day-2 settlement, and enough of those won to pay for the 12).

The decision is the MIRROR of rule 3's. Rule 3 was unprincipled and
profitable and went anyway; the clause was PRINCIPLED (the intraday
stand-in for the daily engine's close-beyond-the-level entry proof, which
is what kept quickfixclose1 a fair baseline) and unprofitable, and goes
because "simplify, and even come out on top with better metrics" (Lode).
Consequence to state plainly: quickfix1m1dc is now a pure touch-entry
strategy that carries every position overnight with the stop live, and it
no longer asks the daily engine's question at all.

**GAP RISK WAS THE CLAUSE'S ORIGINAL PURPOSE** (Lode's recollection:
stop a losing trade being gapped through its stop the next morning) and
it barely exists in this sample. Measured on the new baseline: 6 of 80
stop exits opened beyond their stop, understating the loss by +0.52R in
TOTAL, only 2 of them overnight, and NONE of them trades the clause used
to abort. Related known modelling gap, worth its own fix: engine_1m books
a stop AT the stop price whatever the bar did, where the daily engine
fills a gapped stop at the open. Cost of that optimism, measured: ~0.5R
across the sample.

**THE STOP STAYS LADDER-ANCHORED, and the hybrid is not retired** (Lode:
"something to keep an eye on"). The hybrid does exactly what it was
predicted to do - fewer trades (143 v 153), better win rate (39.9 v 36.6)
and the SHORTEST losing streak in the grid (6) - but the wider stop is a
bigger R denominator, so the same price move books fewer R: about -9.7R
either way, and the drawdown goes UP rather than down. (Claude predicted
-15R to -25R from a per-trade diagnostic; Lode called that too high, and
was right.) `extreme` (tighter than the ladder) is far worse still, which
is what it was in the grid to establish: the ladder anchor earns its
place in BOTH directions, and moving the stop at all is the wrong lever.
The hybrid keeps a report of its own,
`output/quickfix1m1dc_report_hybrid_stop.html`, built from the matrix
trades with no extra backtest.

Kept honest since (2026-08-08): that report had aged into a page nobody
re-ran - it still carried the 143-trade, pre-lockout grid above while the
baseline had moved on. The hybrid is now a standing cell in the matrix
itself (`hybrid stop`: the published baseline with `stop_mode`
`ladder_or_extreme`), so it is re-measured on every pass. On the current
window it reads **132 trades, 43.9% wr, +39.35R, streak 7, 11.92% DD,
$143,907** against the baseline's 136, 41.2%, +53.32R, streak 7, 11.20%,
$162,579. The verdict of this section is unchanged and the reason is the
same one: the better win rate is real and it does not pay, because the
wider stop books fewer R per move. The drawdown is now level rather than
worse, which is the one thing that moved.

Diagnostics behind the discussion, kept because they shape the next
round: the wider stop would have moved the stop on 60 of 153 trades
(median 0.47R further, so a third less size), and of the 26 entry-day
stop-outs it touches only 6 survive the rest of the day. And the trades
it touches are the GOOD ones: entries taken after the session had already
traded through the ladder top are 60 trades at +21.36R (25% wr, winners
+3.99R average) against 93 clean entries at +5.27R (34% wr, +1.22R). Same
shape as the rule 3 finding - the structurally ugliest setups are the
strong-trend ones - and it is why an entry FILTER on that condition would
be the wrong move too.

## 9. Rule 3 removed (Lode, 2026-08-06)

Rule 3 (>= 3.5x room to the nearest opposite-side reversal, including its
existence clause: no opposite reversals -> no trade) was target-era logic.
quickfix1m1dc exits at the next day's settlement regardless, so the
requirement guarded nothing - and the existence clause blocked exactly the
one-sided files that mark the strongest trends. The motivating case now
trades: GC 2026-02-02 06:55 long 4517.2 (a file with a five-level bear
ladder and zero bulls) -> 4935.0 at next-day settlement, +2.10R.

Measured cost, honestly stated - the removal is a PRINCIPLED change, not a
performance win. Baseline (frozen+blocked, 2-tick slippage):

| | with rule 3 | without |
|---|---|---|
| trades | 130 | 153 |
| win rate | 30.8% | 30.7% |
| net R | +31.54 | +26.63 |
| longest losing streak | 7 | 8 |
| max DD | 17.95% | 17.78% |
| final | $131,386 | $124,827 |

The 23 recovered trades split: 7 new stop-outs (-8.1R), 6 no_confirm
aborts (-1.9R), 10 survived to close1 (7 winners, +5.2R) - net -4.9R.
Rule 3 HAD been acting as an accidental entry-quality filter, mediocre
but positive. Keeping a rule for accidental benefit is curve-fitting;
the honest path is the one taken: remove the unprincipled rule, and let
the entry-quality research (section 8) earn those 7 stop-outs back with
a filter that has a reason to exist. Anatomy without rule 3: stop 70x
-1.19R avg, no_confirm 23x -0.46R, close1 60 trades / 47 wins / +2.01R
avg - survival-to-settlement still wins 78%.
