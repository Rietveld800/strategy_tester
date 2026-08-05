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
