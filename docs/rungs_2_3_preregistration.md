# Pre-registration: rungs 2 and 3 of the ladder for the reversal signal of quickfix1m1dc (variant 4)

Written 2026-09-19 15:40 Belgian, before any number is computed, at Lode's instruction
("Could we run the 2 rungs now? Then let's do it."). Nothing below has been run. The
readings, when they exist, are appended as RECORD ONLY sections with sections 2 to 8
unchanged, as `exit_timing_preregistration.md` does.

## 1. Why this exists - the record so far

`live_engine/strategies/PREREGISTERED_LADDER.md` records that rungs 2 (Detection) and 3
(Direction) were pre-registered in the reasoning-layer sessions of 2026-06-07/08, that the
reversal-record quarantine landed before any reversal-family detection test executed, and
that the lineage finding of 2026-08-20 (`STEP6_VARIANT05_DOSSIER.md` section 2, the extractor
fix `charter@afe4167`) unblocked them: "pre-registered, open, unblocked", running them being
`strategy_tester` work, "the two that cost least and kill most".

**What the record fixes about the June design, in its entirety** (the ladder file, lines
64-68): *"surrogate nulls, B=10,000 time-shuffles with a 5,000 in-sample fallback only, the
null restricted to defined-close trading days, equal-weight independent-per-level as the
reversal baseline, with class-conditioning and Major/Minor stratification explicitly deferred
to later pre-registered hypotheses"*, and the rung questions themselves: rung 2, *does the
defined signal fire in the historical record significantly above a surrogate null - e.g. a
time-shuffle preserving the value distribution?*; rung 3, *conditional on firing, does
subsequent movement carry directional content beyond the null?*

**What the record does not fix**, searched on 2026-09-19 across live_engine, strategy_tester,
data_center, charter, trading_system and hyperliquid_bot: the exact shuffle, the statistic,
the population's window, the horizons for rung 3, the thresholds, and the reading rules. No
repository file carries them; the reasoning-layer conversations are not in the record. This
document fixes them now, marking each as **[June]** where the June sentence fixes it and
**[Lode to rule]** where it is a choice made here. Under the ladder's discipline a choice
made after looking is a result, not a decision, so nothing in sections 2 to 8 changes once a
number exists.

## 2. The signal, as rung 1 defined it

The reversal signal is the one `engine_1m.py` and `strategies/quickfix1m1dc.py` trade: on a
session, the ACTIVE levels file (the Socrates daily array whose second column is that
session) carries a ladder of reversal levels per side; a **level prints** when a 1-minute bar
of that session has `low <= level <= high`. The strategy's own trigger is the print of the
ladder's FIRST reversal (the lowest bullish reversal above the file's `prev_close` for the
short side, mirrored for the long side) under rules 1 and 2. Two events are therefore
defined:

- **E_any**: a published reversal level prints during the session its file is active for.
  This is the **equal-weight independent-per-level baseline** [June]: every level counts
  once, tested on its own, no weighting by class, ladder position or side.
- **E_first**: the ladder's first reversal prints, the strategy's trigger.

Rung 2 is graded on **E_any** (the June baseline) with E_first reported beside it. Rung 3 is
graded on E_first, the trigger the strategy acts on, with E_any reported beside it.
**[Lode to rule]**: that rung 2 grades on E_any and rung 3 on E_first.

## 3. The null - a time shuffle that preserves the value distribution

**[June]**: a surrogate null by time shuffle preserving the value distribution, B = 10,000,
with 5,000 only as an in-sample fallback, restricted to defined-close trading days.

**The shuffle as fixed here [Lode to rule]**: per market, every session's levels file is
reduced to its set of **offsets**, level minus the file's own `prev_close`, per side. The null
pairs each session's bars with the offset set of a **random other session of the same
market** (a permutation of files across sessions, without replacement), and rebuilds levels
as that session's `prev_close` plus the borrowed offsets. The distribution of offsets, and
of ladder shapes, is thereby preserved exactly; the alignment of a file with its own session
is destroyed. B = 10,000 permutations, seed 20260607, the fallback to 5,000 only if a full B
exceeds two hours on this machine, in which case the fallback is recorded as such.

Why offsets and not raw values: a raw-value shuffle borrows levels from days whose prices sat
elsewhere; those levels rarely print for that reason alone, and a null that is trivially
easy to beat is not a null. The offset shuffle keeps every borrowed ladder at the same
distance from the session's reference price as a real one, so what is tested is the
ALIGNMENT of Socrates' levels with the session's path, which is the claim.

**Defined-close trading days** [June]: a session counts when data_center holds it under
section 7's rule (`live_engine/commissioning/sessions.py`, the same rule as
`run_1m.futures_days`): the roll calendar covers the date, the calendar's contract holds
1-minute bars on it, and, where a statistics table exists, a settlement (`stat_type` 3, the
2026-09-18 correction) is keyed into it. Sessions with no levels file are excluded from both
the observed and the null.

## 4. Population [Lode to rule]

- **Markets**: the fifteen of `MARKET_SELECTION.md` (6E, 6J, CL, DX, ES, GC, HG, LE, NG, NQ,
  PA, PL, SI, YM, ZW), each on its roll calendar's contract for the date.
- **Window**: from the first session data_center holds in 2026 to **2026-09-08 inclusive**,
  the day before rung 6's forward window opened (2026-09-09). The forward window is rung 6's
  evidence and is not read here; rungs 2 and 3 are graded in sample by construction, which
  the ladder's ordering intends.
- **Levels**: both sides, Major and Minor pooled [June: stratification deferred], every
  reversal level the post-fix extractor (`charter/scripts/charting_core.py::parse_array`)
  returns for the file, exactly as `run_1m.py` reads them at backtest time.
- **Bars**: `expand_process.load_bars`, on-book only, as the engine reads them.

## 5. Quantities and statistics - defined without reference to any outcome

**Rung 2, detection.**
- `T2_any` = the number of (session, level) pairs in which the level prints, divided by the
  number of pairs, pooled over the fifteen markets with equal weight per pair; `T2_first`
  the same over first reversals only.
- Null distribution: `T2` recomputed under each of the B permutations.
- `p2` = (1 + #{b : T2_null_b >= T2_obs}) / (B + 1). One-sided: the claim is that levels
  print MORE often than aligned-by-chance ladders would.
- Per-market `T2` and `p2` are reported beside the pooled figures, descriptive only.

**Rung 3, direction.**
- For each E_first print, the **signed excursion** toward the strategy's side: for a short
  at a bullish reversal, (level - price_H) / tick; for a long, (price_H - level) / tick,
  where price_H is the market's price at horizon H.
- Horizons: **H2 = the next session's settlement** (the strategy's `close1` exit) as the
  PRIMARY horizon; **H1 = the same session's settlement** (the confirmation moment) as the
  secondary. Prices from the statistics table's settlement rows where they exist and from
  the session's last bar for the trade-close markets, exactly as `run_1m` books them.
- `T3_H` = the mean signed excursion in ticks over all E_first prints, pooled with equal
  weight per print; the median reported beside it.
- Null: the same permutations; under each, the E_first prints of the borrowed ladders and
  their excursions. `p3_H` = (1 + #{b : T3_null_b >= T3_obs}) / (B + 1), one-sided toward
  the strategy's direction.
- Reported beside it, not a test: the unconditional mean signed move over the same horizons
  after every bar of the population, so the reader sees drift.

## 6. Predictions and reading rules - fixed now [Lode to rule on the thresholds]

- **Rung 2 passes** when `p2` on `T2_any`, pooled, is **below 0.01**. It **fails** when `p2`
  is 0.05 or above. Between, it is **inconclusive**, reported and not passed. `T2_first` is
  reported and does not grade.
- **Rung 3 passes** when `p3_H2`, pooled, is below 0.01 with `T3_H2` positive. It **fails**
  when `p3_H2` is 0.05 or above, or `T3_H2` is not positive. Between, inconclusive. `H1` is
  reported and does not grade.
- A rung that is inconclusive is neither climbed nor killed; the record says so and the
  next step is Lode's.
- Per-market figures never override the pooled grade; a pooled pass with several markets
  at chance is reported as such and the composition question belongs to rung 7.
- A clean fail is a first-class finding. The ladder's rule applies as written: passing rungs
  do not average out a failed one, and a hypothesis that fails rung 2 or 3 has failed a
  cheaper rung after being promoted past it; rung 6's forward window, already open, keeps
  running as its own pre-registration says, and what a rung-2 or rung-3 kill means for
  variant 4's candidacy is Lode's to rule, recorded here when ruled.

## 7. What this pre-registration does NOT do

No parameter is searched or tuned; no variant is changed; nothing about frictions or fills;
no class conditioning or Major/Minor split (deferred, June); one run, once, with the numbers
appended below as record. It does not read the forward window. It does not grade rung 6.

## 8. What happens next, by outcome (decided now)

- Both pass: the ladder file's grading table is amended to "2 pass, 3 pass" with the p-values
  and this document as the evidence; nothing else changes.
- Either inconclusive: recorded; whether to widen the population or accept the reading is
  Lode's; no re-run with changed rules under this document.
- Either fails: recorded as the ladder's first clean kill on this hypothesis; the ladder file
  amended; the consequence for variant 4 is Lode's ruling, written here when given.

## 9. Implementation notes (for the session that builds it)

`strategy_tester/research_1m_detection.py`: levels via `parse_array` per file as `run_1m.py`
does; sessions via `run_1m.futures_days`; bars via `expand_process.load_bars`; settlement
prices via `run_1m.load_settlements`; the offset shuffle by permuting file indices per market
with numpy under the fixed seed; `T2` and `T3` vectorised per session; B = 10,000; outputs
`output/quickfix1m1dc_rungs_2_3.json` and `.txt` with every figure of section 5, the
permutation seed, the B actually used, the population counts, and the runtime. A `--dry-run`
prints the population counts and the runtime estimate for one permutation and computes no
statistic.

## 10. Decisions asked of Lode before code

1. Rung 2 on E_any, rung 3 on E_first (section 2).
2. The offset shuffle as the time shuffle (section 3).
3. The population window ending 2026-09-08, the fifteen traded markets, both sides pooled
   (section 4).
4. H2 primary, H1 secondary (section 5).
5. The thresholds 0.01 and 0.05 and the inconclusive band (section 6).
6. The consequence of a fail for variant 4's candidacy, or that it is ruled after the fact
   (section 6).

Until these are ruled, nothing is built and nothing is run.
