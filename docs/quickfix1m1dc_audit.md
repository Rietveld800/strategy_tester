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
The direction was confirmed independently: Socrates itself excludes
off-book prints (FGBL session H/L matches its daily bar 97.2%/98.6%
on-book-only against 88.7%/83.1% with off-book in), which also retires the
old "vendor clips the extremes" caveat.

**Every published figure moved, and all of them for the better** - which is
what you would expect when phantom triggers and phantom stop-outs come out:

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
| 1st | 128 | **41.4%** | +55.34 | +0.43 |
| 2nd | 12 | **16.7%** | -10.30 | -0.86 |
| 3rd | 5 | 20.0% | +5.39 | +1.08 |
| 4th+ | 2 | 0% | -2.94 | -1.47 |

The 2nd trade's win rate was 21.4% on contaminated bars and is 16.7% on
clean ones. And the lockout now beats no-lockout on every metric at once:
128 v 147 trades, 41.4% v 38.1%, +55.34R v +47.48R, streak 7 v 8, **11.20%
v 14.99% drawdown**, $165,921 v $152,571. The win-rate-first thesis is what
carried it: the rule does nothing but delete a class that wins 16.7% of the
time, and everything else follows.

**WHAT THE SAMPLE STILL WILL NOT SAY, and it is the same limit as before.**
Leave wheat's six repeats out by hand and take everything else:

| | trades | wr | net R | streak | max DD | final |
|---|---|---|---|---|---|---|
| no lockout | 147 | 38.1% | +47.48 | 8 | 14.99% | $152,571 |
| minus WHEAT's repeats only | 141 | 39.7% | +55.96 | 7 | **9.77%** | $166,297 |
| minus all repeats (the rule) | 128 | 41.4% | +55.34 | 7 | 11.20% | $165,921 |

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

RERUN ON CORRECTED BARS (section 12, off-book prints removed): lockout 1
128 trades / 41.4% / +55.34R / streak 7 / **11.20%** DD / $165,921;
lockout 2 140 / 39.3% / +45.04R / 16.66%; off 147 / 38.1% / +47.48R /
streak 8 / 14.99%. The ranking is unchanged and the drawdown case is
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
hold+hybrid keeps a report of its own,
`output/quickfix1m1dc_report_hold_hybrid.html`, built from the matrix
trades with no extra backtest.

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
