# Pre-registration: exit timing of quickfix1m1dc — is the edge bound to the level's validity window?

Status: PRE-REGISTERED 2026-08-28 (Lode + Claude). No research code exists
yet and none may be written until this file is agreed. Everything below is
fixed BEFORE any forward-return profile is computed; a choice made after
looking at the curve is a result, not a decision (ladder discipline,
`../../live_engine/strategies/PREREGISTERED_LADDER.md`).

Rung addressed: **3 (Direction)**, at multiple horizons. This is not an
exit-rule sweep and it does not produce an optimal exit time. See section 8.

## 1. Why this exists — the record so far

"Exiting on time beats exiting on price" is a working belief of this project.
What has actually been measured:

- **Daily product (retired 2026-08-12, proxy fills).** The Rule 4 cap dial,
  0R-10R in tenth-R steps (75 settings, each a real backtest), against the
  bar-exit family (close0, open1, close1, open2, and the bar 3-20 hold sweep
  of 2026-08-01). Levered to a constant 6% drawdown: close1 $910k, open1
  $850k, the 1.9R cap $346k, uncapped $158k; every hold past bar 2 landed in
  $115-190k with no second peak. Win rate fell monotonically with the cap
  (62% at 2R to 28% uncapped). All of it on daily bars with the daily-proxy
  fill model, and with trade counts that fall as the hold lengthens (one
  position per market), so part of every comparison is which setups each
  exit was free to take. README, "Where it stands" and "What the cap sweep
  shows".
- **1-minute engine.** No price target has ever been run. The only exits are
  time exits (`close1` at the next settlement; `no_confirm`, retired with the
  confirmation clause; `stop`). Findings that bear on the question, all from
  `quickfix1m1dc_audit.md`: survival to the next settlement wins ~80% at
  ~+2.3R while stops cost -1.19R (s.8); mechanical exit-before-stop (abort at
  -X R, breakeven stops) is negative in every cell because the winners chop
  deep first (s.14); late entries keep the win rate and lose two thirds of
  the R (s.14); the fixed time exit is what makes the geometry band
  derivable, since a ladder wider than a day's travel has a capped payoff
  (s.15b); rule 3 was removed as target-era logic (s.9). The s.14 per-minute
  path analysis (MAE/MFE, time to each) was a scratch run and is not in any
  persisted artifact.

So the belief rests on a daily-proxy comparison plus an arithmetic argument.
At 1-minute resolution the SHAPE of the edge over holding time has never been
measured. That shape is what this pre-registration measures.

## 2. The hypothesis

**H1 — the edge is bound to the level's validity window.** After a
qualifying trigger, the expected favourable excursion accrues mostly inside
the entry session, saturates by the next Socrates activation (the next levels
file, normally d+1 07:35 UTC), and does not grow further by the next
settlement. Beyond that, the position carries variance without drift.

**Mechanism.** A Socrates reversal level is information about where flow
reverses UNTIL Socrates redraws it. The third test plus the snap-back (rule
1 = 3, whose measured edge is timing on shared sessions rather than extra
trades — `research_1m_rule1.py`, 2026-08-27) is the market absorbing the
level: the probe through it fails, the participants who pushed through are
wrong-footed, and their unwind is the move. Once the unwind has run the
level's information is spent, and the next morning's update replaces the
ladder anyway, so the trade's premise expires at the next activation. The
next settlement is the last structural moment on the spent premise. Hence a
TIME exit at a STRUCTURAL moment rather than a price target — which, under a
fixed horizon, truncates the right tail and holds the losers.

**Rival hypotheses, stated so they can win.**

- **H2 — continuation.** The snap-back is the start of a larger move; the
  excursion keeps rising past the next settlement. Then a longer hold or a
  trailing exit is right and H1 is false.
- **H3 — no shape.** The profile is flat from the first hour: the edge is in
  the fill and the stop, not in the hold. Then the exit moment is a cost and
  execution question only.

## 3. Predictions (fixed now, in order of severity)

| # | Prediction | Which hypothesis it separates |
|---|---|---|
| P1 | Mean excursion m(h) rises with h through the entry session and is statistically flat between h = next activation and h = next settlement — *flat clause retired by amendment A1 (section 6); verdict = first reading, section 12* | H1 vs H2 |
| P2 | Per-trade Sharpe S(h) = m(h)/s(h) peaks at or before the next settlement and declines at +2 and +3 settlements — *under A1: at or before settle1, and lower at every later horizon* | H1 vs H2 (variance grows, drift does not) |
| P3 | Losers are decided early: among stopped trades, the stop prints inside the entry session in the majority of cases | H1 mechanism (the premise fails fast when it fails) |
| P4 | Conditioning on the rule 1 count: r3 trades show a steeper early rise of m(h) than the r1/r2-only trades of the rule 1 sweep | the link to the third-reversal finding |
| P5 | The result holds on both stop anchors (4th/5th, hybrid) and is not carried by one market | robustness, not a separate hypothesis |

**Falsifiers.** m(h) still rising at +2 settlements with S(h) not declining
falsifies H1 in favour of H2. No horizon distinguishable from the null (s.6)
supports H3. P3 failing (stops mostly after the entry session) means the
early loss anatomy of s.8 is an exit artefact, not a property of the signal.

## 4. Population

**Taken trades only** (Lode, 2026-08-28). Refused triggers are unfilled
hypotheticals; their excursion profile is a separate, later question.

- **Primary sample:** the published blotter, `output/quickfix1m1dc_all.json`
  (`variant 2`: 4th/5th stop, lockout 1, band 0.00-0.60, trading-day window,
  the 22-market human filter), every trade with a recorded exit.
- **Secondary sample:** `variant 5` (hybrid stop, band 0.20-0.60) from
  `output/quickfix1m1dc_matrix.json`. Reported beside the primary, never
  pooled with it — the two lists differ in both directions.
- **For P4 only:** the r1 and r2 cells of `output/quickfix1m1dcRule1.json`,
  restricted to trades NOT in the r3 list of the same anchor (the marginal
  trades the lower counts add).
- Trades whose exit reason is `data_end` are excluded.
- **Discontinued markets stay in the primary sample (decided 2026-08-28).**
  CC, KC, UDOW, UNG, USO (collection stopped ~2026-04-17; 14 of 79 variant
  5 trades, +10.97R, all in the first half of the window) are real, filled
  trades on markets that passed the human filter, and this study asks about
  the shape of the signal, not about forward performance. Excluding them
  would drop the sample by 18% and would itself be a selection made after
  knowing their results. Every table is ALSO printed on the surviving
  17-market universe of `MARKET_SELECTION.md`, and a verdict is "not
  rejected" only if it holds on BOTH (reading rule 6). A disagreement
  between the two is a finding to write up — the likely cause is the ETF
  session structure (a 6.5-hour RTH session with no overnight bars behaves
  differently at the clock horizons) — never resolved by choosing the
  friendlier universe.

## 5. Quantities — defined without reference to any exit rule

All bars are on-book 1-minute bars through `expand_process.load_bars()`;
prices are the trade's own contract's bars only, never across a splice.

- **Reference price:** `entry_first`, the first-reversal price the trade
  armed on — not the slipped fill. Slippage is a cost, not part of the
  signal's path.
- **Excursion at horizon h:** signed in the trade's favour,
  `x(h) = (entry_first - close(h))` for a short and the mirror for a long,
  where `close(h)` is the close of the last on-book bar at or before the
  horizon instant on the trade's contract.
- **MFE(h) / MAE(h):** the running best / worst excursion over all bars
  from the entry bar (inclusive) to the horizon instant, using bar highs and
  lows.
- **Two paths, both reported, with the roles fixed now** (wording settled
  by Lode 2026-08-28; the earlier labels "unconstrained" / "stop-truncated"
  survive only as field names in the code and JSON):
  - **signal path (no stop)** (primary for P1, P2): the path as if no stop
    existed — the market after a qualifying trigger. It is the quantity a
    hypothesis about edge shape is about.
  - **trade path (stop as booked)** (primary for P3, secondary for P1,
    P2): the same path frozen at the trade's OWN stop — the one the blotter
    recorded at entry (`stop`), i.e. each sample's anchor: the 4th/5th
    ladder stop for variant 2, the hybrid stop for variant 5, named in
    every heading — from the first bar whose high/low prints it. There is
    no scheduled exit on this path, so a point on it is the position,
    still open with its stop, marked at that moment. It is NOT a
    simulation of any new exit rule.
- **Definitional refinements before the first run (2026-08-28, recorded
  so the agreement check of section 10 can be exact rather than
  approximate).** (a) A SETTLEMENT horizon takes the day's settlement
  PRICE — the price the engine books `close1` at and the close Socrates
  shows — not the close of a bar; its MFE/MAE run over the bars strictly
  before the settlement instant. (b) On the trade path (stop as booked) the
  engine's precedence is copied exactly: a stop printing on the entry bar
  never counts (the engine tests `bts > entry_ts`), and on a settlement
  bar the settlement is booked first, so a stop counts for a settlement
  horizon only if its bar is strictly before that `settle_ts`. (c) A clock
  horizon that falls after its session's last bar reads that last bar and
  is flagged "session ended"; the flag count is printed per horizon.
  (d) A horizon past a contract splice is recorded as "splice" (the core
  function raises; the runner records), one past the data as "data end".
  (e, amendment A1) An OPEN horizon takes the first bar's open; its
  MFE/MAE run over the bars strictly before that bar plus the open print
  itself, and on the trade path a stop on the open bar counts
  only from the next horizon on. A CLOSE horizon takes the last bar's
  close; a stop on that bar counts.
- **Denominators, both reported:** R, using the trade's `rpu` (first
  reversal to stop, the engine's own definition); and the trailing
  trading-day range at entry, `rpu / rpu_range_ratio` where the ratio is
  recorded (the eight unjudged trades of s.19a are reported in R only).
  The range denominator exists so that a reading does not depend on the
  stop choice, which s.19 showed moves every ratio.

## 6. Horizons, statistics, null

**Horizons — fixed list (AMENDED TWICE, A1 and A2 below).**

The list as first registered (2026-08-28, first reading in section 12):
30m, 1h, 2h, 4h; entry settlement; next activation; next settlement; +2,
+3 settlements.

**Amendment A1 (Lode, 2026-08-28, after the first reading).** The list is
replaced by fifteen horizons; the entry day is day 0:

| horizon | definition |
|---|---|
| 30m, 1h, 2h, 4h | clock offsets from `entry_ts`; the last bar at or before the instant; a horizon that falls after that session's last bar is flagged "session ended" and reads that last bar |
| settle0 .. settle3 (A2: .. settle7) | the settlement of session N (`settle_ts` / `settle_price` of the Nth trading day after the entry day in the market's `days` list); settle1 is the engine's `close1` exit moment |
| close0 .. close3 (A2: .. close7) | the session's LAST print: the close of the last on-book bar of session N |
| open1 .. open3 (A2: .. open7) | the session's FIRST print: the open of the first on-book bar of session N. Bars strictly before it carry the excursions; a stop printing on the open bar itself prints after the open and does not count at openN |

Reason for the amendment, in Lode's terms: the activation horizon does not
sit at a comparable point of the session across markets — the update lands
9h35 into a CME session, 7h35 into the grains, five minutes into Sugar and
before the ETF open (charter's `site/1m/timing.html`) — so a profile point
at "activation" mixes fifteen different session phases into one number.
The open / settlement / close of each session are the same structural
moments on every market, and three sessions of them make the shape of the
edge, and its end, legible rather than inferred from two points.

Naming caution: in the blotter `close1` is the exit REASON (the settlement
of day 1); in this list `close1` is session 1's last print and `settle1` is
that exit moment. A horizon crossing a contract splice reads "splice", one
past the data "data end".

Consequences for the predictions, recorded rather than silently absorbed:

- **P1's flat clause is RETIRED with its horizon.** Its verdict is the
  first reading's (section 12: the activation-to-settlement stretch was a
  rise, H1's saturation clause is false in that direction). The rise clause
  (settle0 − 30m) is still read. Two DESCRIPTIVE deltas are printed beside
  it and are not pre-registered tests: the day-1 session (settle1 − settle0)
  and the overnight gap (open1 − close0).
- **P2 is read on the full list and is STRICTER than before:** the Sharpe
  peak must sit at or before settle1 AND every later horizon (close1,
  open2, settle2, close2, open3, settle3, close3) must be lower than
  settle1's. A peak after settle1 rejects it towards H2.
- **Reading rule 2's deciding horizons are settle0 and settle1** (were: next
  activation and next settlement).
- P3, P4, P5, the population, the quantities, the null and the bootstrap
  are unchanged.

**Amendment A2 (Lode, 2026-08-30, after the A1 reading).** The day
horizons run to day 7 instead of day 3: open4 .. close7 are appended,
twenty-seven horizons in all. The clock horizons, the deciding horizons
(settle0, settle1), P1-P5 and every reading rule are as under A1; P2's
"every later horizon" now spans to close7. Recorded consequences:
later horizons lose trades to "data end" (each further day drops the
window's newest entries) and to "splice" (a longer window crosses more
contract changes), so their n decays and rule 1 dims them sooner; the
null is placed on the same twenty-seven horizons. This is an extension
of the window, asked for to see where the edge ends, not a horizon added
because the curve suggested it (section 8) - no exit rule is read off
days 4-7 any more than off days 1-3.

**Statistics per horizon:** n, m(h), s(h), hit-rate (x(h) > 0), S(h),
median x(h), MFE(h) and MAE(h) means, the e-ratio MFE(h)/MAE(h), the ZW
share of the summed excursion, and the top-market share.

**Uncertainty:** the paired day-cluster bootstrap of `sharpe_stats.py`
(clusters = entry days, reps 10,000, the fixed seed), for m(h) and for the
difference m(h2) - m(h1) between adjacent horizons.

**"Statistically flat" in P1 (decided 2026-08-28):** two conditions, both
required, on `delta = x(next settlement) - x(next activation)` in R:

1. the 95% bootstrap interval of mean(delta) contains zero — the sample
   cannot tell the drift from zero; and
2. the point estimate of mean(delta) is under **0.25R** — roughly one
   round trip of the measured slippage (s.7), the smallest drift that could
   pay for staying in the trade at all.

Condition 1 alone rewards a small sample (an interval of +-0.3-0.4R on ~80
trades would call a material +0.3R/trade drift "flat"); condition 2 alone
ignores the noise. An interval covering zero with a point estimate above
0.25R reads "the sample cannot decide", never "flat". A relative threshold
(a fraction of m(next settlement)) was considered and rejected: it moves
with the quantity under test. Note the meaning: "flat" here is "flat
enough that the added variance is not paid for", not "no drift exists" —
a true slow drift of +0.2R per day passes this rule and is acceptable for
the exit decision H1 feeds, and the reading must say so if the point
estimate sits between 0.10R and 0.25R.

**Null (rung 2/3 machinery, pre-registered 2026-06-07/08, adapted to a
taken-trade population):** each trade's geometry — side, contract, `rpu`,
stop distance — is placed at B random on-book minutes of the SAME market,
the same session time-of-day (within 30 minutes) and a different trading
day inside the window, restricted to days with a defined settlement, and
the identical profile is computed. B = 10,000 placements in total (5,000
in-sample fallback if runtime forces it). The observed m(h) is reported
with its percentile in the null distribution at every horizon. This
answers: does a qualifying trigger carry directional content beyond "a
random minute in this market at this time of the session".

## 7. Reading rules (committed before the numbers)

1. A horizon with n < 30 trades gets no verdict; it is printed dimmed.
2. A prediction is "not rejected" only if it holds on the primary sample
   AND is not carried by one market (top-market share of the excursion sum
   under 35% at the horizons that decide it). It is never "confirmed" on
   this sample size — ~80 trades over eight months.
3. P1 and P2 are read on the signal path (no stop) first. If the trade
   path disagrees, the disagreement is reported as a finding about the
   stop, not resolved by picking the friendlier of the two.
4. Both denominators must agree on the direction of every verdict; if they
   do not, the verdict is "indeterminate" and the reason is written up.
5. The rule 1 comparison (P4) is read as a difference of profiles with the
   paired bootstrap, no selection deflation (r3 is the pre-existing rule).
   **P4 is run on this window and expected to be unpowered (decided
   2026-08-28):** the marginal r1/r2-only trades are ~20-30 per anchor, so
   most horizons will print dimmed under rule 1. It is run anyway because
   it costs nothing (the rule 1 payload exists and the profile code is the
   same), because the first reading is then on record and the forward
   window adds to it without a new pre-registration, and because it is the
   one prediction that ties this hypothesis to the third-reversal finding.
   The reading must state that it is unpowered; a suggestive dimmed curve
   is not a result. P4 is diagnostic of the MECHANISM only — H1 can hold
   with P4 failing — so its sample size never delays the verdict on P1-P3.
6. A verdict on P1-P3 requires agreement between the full primary sample
   and the surviving 17-market subset (section 4). Disagreement is written
   up as a finding, and the prediction is "indeterminate".

## 8. What this pre-registration does NOT do

- It does not sweep exit rules and does not compute an optimal exit time.
  On ~80 trades the argmax of m(h) is noise — the same trap as the 0.45-0.55
  band cell (s.19k). No horizon is added because the curve suggests it.
- It does not introduce a dial into `engine_1m.py`. Nothing in the engine
  changes as a result of this document.
- It does not test refused triggers, price targets or trailing exits.
  Those are follow-ups whose shape depends on which of H1/H2/H3 survives.

## 9. What happens next, by outcome (decided now)

- **H1 not rejected.** The exit stays a time exit at a structural moment.
  The choice between "next activation" and "next settlement" is then a
  COST and EXECUTION decision argued from the order type (a settlement
  order can be worked; 07:35 UTC is not a session event on most markets)
  and from the flat stretch P1 reports — not read off m(h). A candidate
  earlier exit (entry-day settlement) is only considered if P1 shows the
  rise complete by then, and it would be its own pre-registration.
- **H2 not rejected.** The question becomes "which structural event ends a
  continuation", and price-level exits (the next opposite reversal, an R
  cap) re-enter honestly as candidates — as a new pre-registration against
  the daily cap-dial record, not by reviving the daily code.
- **H3 not rejected.** Exit as early as execution allows; the research
  moves to entry quality and cost, where s.14 already pointed.
- **Indeterminate.** Written up as a clean negative for this sample size,
  with the forward window as the next sample. No rule changes.

## 10. Implementation notes (for the session that builds it)

- Script: `research_1m_exit_profile.py`, a READING like
  `research_1m_rule1.py` — no engine passes; it loads the blotter(s) and
  `run_1m.market_inputs(key)` (bars, `days` with `settle_ts`, `files` with
  `activation_ts`) per market. Minutes of runtime at most.
- Output: `output/quickfix1m1dc_exit_profile.txt` (the reading, in the
  style of the rule 1 research text) and `.json` (every trade's profile at
  every horizon, so a later page can draw it). Not in the refresh chain;
  not in charter's overlays or variant list.
- **Existing output files are never touched** (Lode, 2026-08-28). Nothing
  this study produces may overwrite, rename or rebuild any file already in
  `output/` (the blotter, the matrix, the R-cut and rule 1 pages and their
  PDFs). If a page is wanted, it is an ADDITIONAL file under its own name
  (`quickfix1m1dc_exit_profile.html`, and a PDF only via the browser's own
  print), built read-only from the study's JSON.
- Tests: the excursion and horizon definitions of section 5 and 6 pinned
  on a synthetic market with hand-computed values (session-end horizon,
  Friday-to-Saturday activation, stop truncation on the entry bar, a
  splice inside the horizon window must raise). Real-data checks: every
  trade's `x(next settlement)` on the trade path (stop as booked), in R, must
  equal `gross_r + (fill - level) / rpu` in the trade's favour — the entry
  slippage (`ENTRY_SLIP_TICKS * tick / rpu`) on a touch fill, the
  gap-through distance plus slippage on a fill from the open — for
  `close1` AND for `stop` exits (a stop is -1R on the path), and a stop
  trade's truncation bar must be the blotter's exit bar. The run refuses
  to write when any trade disagrees. Same agreement discipline as the
  ratio pane against the blotter. FOUND BY THE FIRST RUN (2026-08-28): the
  check was first written as slippage only and refused two trades (PA
  2026-05-21, PL 2026-08-17) whose touch bar never printed the level — the
  engine fills those from the bar's open (`gap_beyond`). The profile still
  measures from the LEVEL, as section 5 says; only the check translates.
- BUILT 2026-08-28: `research_1m_exit_profile.py`,
  `tests/test_exit_profile.py` (16 synthetic tests plus the real-blotter
  agreement check behind `EXIT_SLOW=1`). The engine's own defaults still
  carry v1's `tighten=True`; the study refuses any trade with a tightened
  stop and every cell it reads runs `tighten=False`.
- Any change to sections 3-7 after the first run is recorded here with a
  date and a reason, and the run before it is kept as the first reading.

## 11. Decisions taken before code (Lode, 2026-08-28)

1. "Statistically flat" = 95% interval covers zero AND point estimate under
   0.25R (section 6).
2. Discontinued markets stay in the primary sample; every table also on the
   17-market subset; a verdict needs both (sections 4 and 7).
3. P4 runs on this window, printed dimmed where unpowered, re-read on the
   forward sample (section 7).
4. No existing output file is modified; the study only adds files
   (section 10).

Nothing in sections 3-7 is open. The next step is the script and its tests.

## 12. First reading (2026-08-28) — RECORD ONLY, sections 3-7 unchanged

Run of `research_1m_exit_profile.py` on the blotters of 2026-08-27
(variant 2: 100 trades; variant 5: 85), 22 markets loaded, null B = 10,000,
bootstrap reps 10,000, seed 20260828. Agreement check passed on every
trade (after the gapped-fill correction of section 10, which the first
attempt refused on). Full text: `output/quickfix1m1dc_exit_profile.txt`;
page: `output/quickfix1m1dc_exit_profile.html`.

Variant 2, all 100 trades, signal path (no stop), R units:

| horizon | mean R | sd | hit | Sharpe | null percentile |
|---|---|---|---|---|---|
| 30m | +0.01 | 0.69 | 0.53 | 0.02 | 72 |
| 1h | +0.04 | 0.74 | 0.56 | 0.05 | 75 |
| 2h | -0.01 | 1.22 | 0.50 | -0.01 | 58 |
| 4h | +0.20 | 1.71 | 0.54 | 0.12 | 95 |
| entry settle | +0.31 | 1.98 | 0.60 | 0.16 | 96 |
| next activation | +0.34 | 2.31 | 0.59 | 0.15 | 97 |
| **next settle** | **+0.77** | 3.98 | 0.62 | **0.19** | **99** |
| +2 settle | +0.11 | 6.07 | 0.61 | 0.02 | 82 |
| +3 settle | +0.22 | 6.22 | 0.55 | 0.04 | 89 |

Verdicts as the pre-committed rules produce them (both samples, both
universes, both denominators unless stated):

- **P1 — indeterminate, and wrong in a specific direction.** The stretch
  next activation -> next settlement is not flat: +0.42R (95% CI
  [-0.04, +0.89], "cannot decide" in R units; "rising" in range units and
  on the 17-market subset, CI clear of zero). The excursion does NOT
  saturate when the levels file is replaced; more than half of it accrues
  in the day-2 session and it stops at the next settlement. The rise
  through the entry session (entry settle - 30m, +0.30R) has its CI just
  covering zero on the full sample and clear of it on the 17.
- **P2 — not rejected, 8 of 8 readings.** Per-trade Sharpe peaks at the
  next settlement and declines at +2 and +3 in every sample, universe and
  denominator. Past close1 the signal path's mean collapses (+0.77 ->
  +0.11) and the sd doubles: variance without drift. H2 (continuation) has
  no support.
- **P3 — not rejected:** stops print inside the entry session on 68% (v2)
  and 61-68% (v5) of stop trades.
- **Reading rule 2 bites.** DX carries 35.3% of the summed excursion at
  the next-activation horizon (limit 35%); ZW 26.6% at the next
  settlement. By the rule as written, NO prediction may read "not
  rejected" on this sample. Recorded, not waived.
- **The first two hours are indistinguishable from the null** (percentiles
  58-75). The edge is not front-loaded in clock time; it appears from ~4h
  and is sharpest at the structural moment.
- **P4 — unpowered as expected:** r3 leads the marginal r1/r2-only trades
  by +0.3 to +0.4R at every settlement horizon on both anchors, P(<=0)
  0.07-0.12. Not a result; re-read on the forward sample.

What this says about H1's MECHANISM, stated after the fact and therefore
not a change to section 2: the premise does not expire with the levels
file. It plays out over two sessions and ends at the second settlement.
The current `close1` exit sits on the Sharpe peak; an earlier structural
exit (entry settlement, next activation) would give up roughly half the
drift, a later one buys variance. Any re-statement of H1 is a new
pre-registration against the forward window, not an edit here.

## 13. Second reading (2026-08-28, under amendment A1) — RECORD ONLY

Same blotters, same null and bootstrap settings, fifteen horizons.
Agreement check passed on every trade. Files: the `.txt`, `.json` and
`.html` under `output/quickfix1m1dc_exit_profile.*` (overwritten by this
study's own re-run; nothing else touched).

Variant 2, all 100 trades, R units — signal path (no stop) and trade path
(stop as booked, here the 4th/5th ladder stop):

| horizon | mean R (signal) | Sharpe (signal) | mean R (trade) | Sharpe (trade) |
|---|---|---|---|---|
| 30m / 1h / 2h | +0.01 / +0.04 / -0.00 | ~0 | +0.02 / +0.04 / -0.02 | ~0 |
| 4h | +0.22 | 0.13 | +0.21 | 0.14 |
| settle0 | +0.31 | 0.16 | +0.33 | 0.21 |
| close0 | +0.29 | 0.14 | +0.33 | 0.20 |
| open1 | +0.31 | 0.13 | +0.33 | 0.20 |
| settle1 | +0.76 | 0.19 | +0.74 | 0.28 |
| close1 | +0.80 | **0.20** | +0.76 | 0.28 |
| open2 | +0.19 | 0.04 | +0.80 | **0.29** |
| settle2 / close2 | +0.11 / +0.17 | 0.02 / 0.03 | +0.73 / +0.74 | 0.21 / 0.22 |
| open3 | -0.17 | -0.02 | +0.64 | 0.19 |
| settle3 / close3 | +0.21 / +0.31 | 0.03 / 0.05 | +0.82 / +0.81 | 0.21 / 0.21 |

Verdicts as the amended rules produce them:

- **P2 — REJECTED towards H2 by the letter of A1, on every reading (8 of
  8), and the letter should be read with its magnitude.** The signal's
  Sharpe peak sits at close1 (0.200) rather than settle1 (0.194): one
  horizon later, 3.5 hours into the same session, by 0.006. The stricter
  wording asked that every later horizon be lower than settle1, and the
  session's own last print is not. Everything after close1 IS lower, and
  by a lot: open2 0.04, settle2 0.02. So the rejection is a statement about
  where inside session 1 the peak sits, not a vote for holding longer.
  Recorded as rejected; the interpretation is in the closing paragraph.
- **P3 — not rejected** (68% / 61-68%), unchanged.
- **P1 — retired** (A1); the rise clause reads +0.30R settle0 − 30m
  (CI just covering zero on the full sample, clear of it on the 17).
- **Reading rule 2 bites harder** on the new deciding horizons: ZW carries
  55.5% of the summed excursion at settle0 (26.6% at settle1). Nothing may
  read "not rejected" on this sample.
- **Descriptive deltas.** The day-0 overnight (open1 − close0) is
  **+0.02R, CI [-0.18, +0.24]** — the night after entry adds nothing. The
  day-1 session (settle1 − settle0) is **+0.45R, CI [-0.08, +0.98]**,
  P(<=0) 0.05 (clear of zero in range units and on the 17). The excursion
  is earned in two SESSIONS, not across the night between them.
- **P4** unchanged in character: unpowered, r3 ahead at the settlement
  horizons on both anchors.

What the fifteen horizons add, stated after the fact: the edge ends with
session 1. Between settle1 and close1 the signal is flat (+0.04R,
Sharpe 0.194 vs 0.200 — indistinguishable); across the following night
it collapses (close1 +0.80 -> open2 +0.19, sd 4.0 -> 5.3) and never
recovers. On the trade path (stop as booked) the stop preserves most of the
Sharpe through day 3 (0.19-0.29), but adds no drift after close1 — a held
trade past session 1 is variance the stop happens to cap. The current
`close1` exit (settle1) sits on the plateau, 3.5 hours before its edge;
whether settlement or the session's last print is the better structural
moment is a cost and execution question (a settlement order can be
worked; the last print cannot), not one this sample can separate. Any
new prediction from this — "the edge ends at the close of session 1" —
is a new pre-registration against the forward window.

