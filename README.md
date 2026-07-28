# strategy_tester — strategies, backtest, risk management

Strategy department of the trading system (see `../trading_system/README.md` for the
umbrella contracts). Turns the Socrates "time and price meet" method into explicit,
testable rules, backtests them on the array files, applies risk management, and hands the
resulting trades to `charter` for display.

**Scope (firm): strategy_tester produces trade results. It never scrapes data and never
renders charts.** It reads the array (meta) xlsx files from `hyperliquid_bot` (via
`charter`'s parser) and writes trades + equity as JSON / xlsx / standalone HTML reports.

One strategy is built today: **quickfix**, the cap family at **1.9R** with **1.39%** risk
per trade. Those are the levered-optimal settings, not a guess: 1.9R tops the
constant-6%-drawdown chart and 1.39% is the risk that puts it there.

Rule 4 is the **cap family**: ride to the first opposite reversal beyond entry, never past
`cap`R. One policy with one number in it, and that number is a **dial on the reports**,
**0R to 10R** (tenth-R steps to 5.5R, quarter-R above) plus no cap at all. Every setting is a
real backtest. See [The Rule 4 cap dial](#the-rule-4-cap-dial-on-the-reports).

Two sibling strategies were retired on 2026-07-28 and neither should be reinstated without
being asked. **slowfix** was the family at no cap, i.e. a dial position rather than a method.
**quickfixpro** took profit one tick beyond the entry bar's own extreme, fixed at entry, a
genuinely different Rule 4 *shape* rather than another cap; it is gone from the report and
from charter. The machinery for a second shape stays (`Rule4`, `in_grid`) and
`strategies.py`'s header says how to add one.

---

## The strategy family (daily timeframe)

A "quick", selective reversal method: trade when price probes a cluster of reversal levels
and snaps back. It works long and short; the short is described first, the long is the exact
mirror. All rules are evaluated per daily bar.

**Reversal ladders.** For each day, bullish reversals (`bull_major` + `bull_minor`) and
bearish reversals (`bear_major` + `bear_minor`) are each pooled into one sorted ladder.
Majors and minors count equally.

**Look-ahead rule (critical).** The array file dated D already reflects day D's own
intraday extremes and re-draws any levels that D elected. So a bar is always evaluated
against the reversal levels **known at its start = the previous file's levels**, never its
own file's. The reference "previous close" comes from that same previous file. This holds
for entry detection and for target recomputation alike.

### Short setup

1. **Signal (Rule 1).** At least **3 bullish reversals** lie in `(prev_close, high]` — price
   rose from the previous close and tested them. The **first reversal** is the lowest of
   these; the **second** is the next lowest.
2. **Clean-setup filter (Rule 2).** Refuse if the bar's `open >= second reversal`. An open
   below the first, or between the first and second, is acceptable.
3. **Entry trigger.** The bar **closes below the first reversal**. Entry fills at the first
   reversal price. (Close at or above it → no trade — no proof price snapped back.)
4. **Stop.** One tick above the entry bar's high. `risk = stop - entry`. Position is sized
   so that risk is exactly the strategy's own `risk_pct` of equity, so **1R = that
   percentage** (1.39% today, see [Risk per trade](#risk-per-trade-one-number-per-strategy)).
   A gapped stop can lose more than 1R; see the daily-proxy assumptions.
5. **Reward filter (Rule 3).** The nearest bearish reversal below entry must be at least
   **3.5R** below entry, else refuse (not enough room).
6. **Target (Rule 4).** Take profit at `cap`R, or at an opposite reversal nearer than that.
   It is evaluated on **every** bar from the levels known at that bar's start, so the target
   moves in when a nearer level is drawn and falls away when one is elected. Only
   **opposite-side** reversals ever close a trade early (bearish for a short, bullish for a
   long), never a same-side one.

### Long setup (mirror)

Bearish ladder for entry, bullish for targets. Tested bearish reversals in
`[low, prev_close)`, ≥3; **first = highest** tested bearish level, second the next highest.
Rule 2: refuse if `open <= second`. Trigger: **close above the first**. Stop = one tick
below the entry bar's low. Rule 3: nearest bullish reversal above entry ≥ 3.5R up.

### Rule 4 — two shapes

| Strategy | Rule 4 | Character |
|---|---|---|
| **quickfix** | The cap family at **cap = 1.9R**: take profit at 1.9R, or at an opposite reversal that sits **closer** than 1.9R (then that reversal is the target). | Takes profit fast. 1.9R is a hard ceiling on every winner. |

#### The cap family — one policy, one number

The cap family is a single policy with a **profit cap in R** as its only parameter:

> ride to the **first opposite reversal beyond entry**, but never past **`cap`R**.

Writing it as one family makes the cap a **dial** the reports can move, and makes the
consequence explicit: **a cap-family "strategy" is just a dial position.** There used to be a
second registered entry, *slowfix*, for the uncapped end; it was retired on 2026-07-28 once
the dial reached every setting, because it was never a separate method and a whole page for
one dial position earned nothing. Nothing is lost — "no cap" is still a setting, still the
dashed reference line on both charts, and still the worst point of the family at equal
drawdown ($158,195 at 0.396% risk), which is the finding that made showing it in full
redundant.

Uncapped corner case: if **no** opposite reversal exists beyond entry (they were all
elected), no target is in force and the trade simply **waits, holding**, until one appears.
The stop stays in place throughout, so a position can never be stranded forever. That is the
only behaviour a capped run cannot produce — a ceiling is always somewhere.

Note that identical Rule 4 *setups* do not mean identical *trades*: an earlier exit frees
that market sooner, and one position per market at a time means a later signal can be taken
that a longer hold would have blocked. Changing the cap changes the trade list, which is why
each setting is a real backtest rather than something the page could recompute.

#### A second Rule 4 shape

**Quickfixpro** was one, from 2026-07-27 to 2026-07-28: take profit **one tick beyond the
entry bar's own extreme**, fixed at entry and never moving, so stop and target were the two
sides of the entry bar and the bet was simply that its low breaks before its high. No
reversal level and no R ceiling, so it was not a cap setting: `in_grid=False`, and its page
carried neither the cap dial nor the cap charts. It was retired on the user's instruction and
its policy deleted rather than left unreachable; it is in git.

The machinery for a second shape stays. To add one: write the policy factory beside
`target_policy`, build a `Rule4` with `in_grid=False` and its own prose, register a
`Strategy` on it, and run `solve_risk.py` for its risk. A new exit reason must be added to
`VAR_REASONS`, `prettyReason` **and** charter's `TRADE_COLORS`.

### Daily-proxy assumptions

We only have daily bars, not intraday ticks (that arrives later with IBKR data). So:

- **Entry is confirmed on the close**, filled at the first-reversal price.
- **The target can never be hit on the entry bar.** Management (stop and target) starts the
  **day after** entry. The entry bar's high/low are already spent by the time its close
  confirms the trade, and by construction the stop sits one tick beyond that bar's own
  extreme, so it cannot trigger there either.
- **A gap is filled at the OPEN** (user, 2026-07-27). If a later bar **jumps over** the stop
  or the target, the trade fills at **that bar's open**, not at the level. The open is the day's first price, so a level the bar opened past
  was taken at the open and nothing can have traded before it — the gap is the one case where
  a daily bar does tell us the intraday order. On the stop that is worse than the stop price
  (a gapped stop loses **more than 1R** — the worst on this data is −11.68R, on an uncapped
  run); on
  the target it is better than the target. Both are the real fill. A short gaps its stop when
  `open ≥ stop` and its target when `open ≤ target`; the long is the mirror. The two cannot
  both be true, since a short's target is below its entry and its stop above it, but the stop
  is tested first anyway, keeping the same doubt-goes-to-the-loss convention as below.
- **A gap is measured against the PREVIOUS CLOSE, not the open alone** (fixed 2026-07-27,
  same day it was introduced). A gap means price *jumped over* the level, so a short gaps its
  target when `open <= target < prev_close`. Testing the open by itself was a real bug: a
  short's entry bar closes **below** its entry by definition, so any target above that close
  was already in the money before management started, every next open counted as a "gap", and
  the trade was paid out at that open instead of at its target. It hit **9 of quickfix's 84
  trades for about +24R of free profit**, and made a **0R cap the best setting on the whole
  grid** — 78 of 88 trades paying an average +1.94R on a target sitting *on* the entry price.
  An already-through target is not a gap: a resting limit there fills at the limit. The stop
  needs no such guard, since it sits one tick beyond the entry bar's own extreme and no close
  can be through it while the trade is open.
- On each later bar, once gaps are resolved: **only the target in range → win; only the stop
  in range → loss; BOTH in range on one bar → `unknown_pl`**, booked as a **loss (−1R)** —
  without intraday data we cannot know which was hit first, so the doubt goes to the stop.
  Gap handling shrank this case to what is genuinely unknowable — the bar that opened
  *between* the two levels and then traded through both. On quickfix it fell from 9 trades to
  5, and several of those became wins rather than −1R losses, which is most of why quickfix's
  win rate and average winner both rose when gap fills went in.
- Slippage is unchanged and still charges the full 3-tick stop rate on a gapped stop. That is
  mildly conservative — the gap is already in the fill price — and is left alone deliberately:
  it is an order-type cost, not a re-pricing of the fill.

**Why two strategies can split on the same bar** (audited 2026-07-27, after the question came
up from reading the charter overlays side by side). `check_exit` is shared, so every strategy
resolves an engulfing day the same way — but the gap test is against *each strategy's own
target*, and those sit at different prices. Across the whole archive:

| | days where BOTH stop and target were in the exit bar's range | booked `unknown_pl` (−1R) | booked a win | booked a stop |
|---|---|---|---|---|
| quickfix 2.5R | 9 | **5** | 3 (all gapped past the target) | 1 (−3.05R, gapped past the stop) |
| quickfixpro | 7 | **6** | 1 (+0.27R, gapped) | 0 |

Both strategies do give the doubt to the stop; the wins are the gap rule firing *first*,
because the bar opened past the target and the limit was already filled before price ran back
through the stop. The one date where the two split is **EURO_Futures, short, exit 2026-05-08**:

```
entry bar 2026-05-07, low 1.17425
  quickfix 2.5R target   1.17440   <- computed: entry - 2.5 x risk
  quickfixpro target     1.17424   <- entry bar low - 1 tick
  exit bar 2026-05-08    O 1.17435  H 1.18085  L 1.17405  C 1.17985
```

The open landed **between the two targets** — 5 ticks past quickfix's, 11 ticks short of
quickfixpro's — so quickfix gapped into profit at the open (+2.53R) while quickfixpro did not
gap, traded through both levels, and booked −1R. One rule, two target prices 1.6 ticks apart.

Structural point worth keeping: quickfix's target is a **computed** price
(`entry − cap × risk`, landing wherever the arithmetic puts it) while quickfixpro's is a
**real chart price** (entry bar low − 1 tick), so a computed target lands near the open by
chance more often and wins these coin-flips somewhat more.

**Open question, deliberately not changed.** The gap test is `open <= target` (short), so an
open sitting *exactly on* the target counts as a gap. That happens once today —
`USD_EUR_Cross_Rate` 2026-03-09, quickfixpro, open 0.8602 against a 0.8602 target, booked
+0.27R. Defensible (a resting limit fills when the market trades there) but it is not a gap.
Requiring a **strict gap of at least one tick** would send that trade through to
`unknown_pl` instead; it is a one-line change in `check_exit` and would need the risks
re-solved.
- A position still open on the last bar is resolved by whether that market is still being
  collected:
  - **active market → `open_at_end`** (unrealized, no P&L). The trade is genuinely still
    running; tomorrow's file will resolve it.
  - **obsolete market → `data_end`**: flattened at that last bar's **close**, with a real
    P&L. Collection has stopped for good, so the trade could never reach its target or its
    stop — leaving it open would park an unresolvable position in the ledger forever and tie
    up risk in the portfolio for an outcome that can never arrive. The last price the data
    gives us is that close, so that is where we get out. Governed by
    `CLOSE_OBSOLETE_AT_END` in `engine.py`; obsolete is the same relative rule charter uses
    (`OBSOLETE_AFTER_DAYS`, default 30 — see the data window below).

  **Known bias in `data_end`, accepted deliberately (user, 2026-07-25).** When the trade's
  entry bar *is* the market's last bar, it is flattened the same day it opened, and that is
  **always a winner**: the entry trigger requires the close to be beyond the entry level (a
  long only fires when the close is above the first reversal, which is the entry price), so
  marking out at that same close cannot lose. It is not a bug and should not be "fixed"
  silently — it follows from the entry-fill assumption the model already makes (filled at the
  reversal price intrabar), and that close is the only price the data offers. The effect is
  bounded by the reversal-to-close distance and affects one trade today
  (`USD_EUR_Cross_Rate`, +0.94R). Trades entered earlier and still open on the last bar carry
  no such bias — their close can land either side of entry. The alternatives considered and
  rejected were dropping the trade entirely (it never had a management day) and booking it
  flat at entry.

**One position per market at a time.** A new signal while in a trade in that market is
ignored — which is why a wider cap, holding longer, ends up with slightly **fewer** closed
trades than a tight one despite identical entry rules. Across markets, positions run
concurrently (see the portfolio model below).

### Data window

Per market, trading starts the day after the market's reversals are **first reported**
(older array files carry no reversal block at all, so they produce no signals). Windows
therefore differ per market (gold from 2025-12-15, several obsolete markets end 2026-04-17,
etc.). Gold futures on the COMEX is the reference market.

A market is **obsolete** when its newest daily bar lags the newest daily bar across *all*
markets by more than `OBSOLETE_AFTER_DAYS` (30) — charter's rule, relative rather than a
hardcoded date so it stays correct as the data moves on. Obsolete markets are still
backtested and still reported; the only difference is that a position open on their last bar
is flattened there (`data_end`) instead of left unresolved. Because obsolescence is measured
across markets, `engine.run_markets` loads every market first and only then runs the
backtests.

---

## Files

| File | What it does |
|---|---|
| `engine.py` | The engine, shared by every strategy: `load_bars`, `infer_tick`, `market_dirs`, signal detection, the stop, exit resolution, `backtest(bars, tick, dp, policy)` and `run_markets` (all markets, **every cap in the grid**, one pass). Run directly for a single-market (gold) JSON ledger. |
| `strategies.py` | The **registry** and Rule 4 itself: `target_policy(cap)` (the cap family), `CAP_CHOICES` (the grid the reports dial across), and the text every output labels itself with. A `Rule4` bundles one setting — its policy, the token its backtest is filed under, `in_grid`, and its prose; a `Strategy` is a key, a title, a **default `Rule4`** and its own `risk_pct`. `QUICKFIX`, `REGISTRY`. |
| `run_all.py` | Runs every market independently (each a fresh $100k) → `<strategy>_all_markets_daily.xlsx` (per-market summary + all trades). |
| `run_portfolio.py` | Merges every market's trades into ONE shared account, applies the money-management + slippage model → the portfolio xlsx + `_equity_<strategy>.json`. Also writes `_variants.json`: the same shared account replayed at **every cap in the grid, plus every registered Rule 4 that is not a cap**, packed for the pages. |
| `build_equity_html.py` | Renders `_equity_<strategy>.json` + the shared `_variants.json` into `output/equity_<strategy>.html`, plus `report.html` and `conclusions.html`. Refuses to build if the variant grid disagrees with a strategy's workbook. |
| `export_charter_trades.py` | Hand-off to charter: `output/charter_trades_<key>.json` — one file per **cap** in `CHARTER_CAPS` (1.9R, 2R, 2.25R, 2.5R, 5R; the strategy's own default MUST be in there). `CHARTER_STRATEGIES` is empty since quickfixpro was retired. Prunes hand-off files it no longer owns. |
| `strategies.py` (grid) | `CAP_GRID` = 0R&ndash;10R, tenth-R steps to `CAP_FINE_TO` (5.5R) and quarter-R above. One axis for the dial and both charts; `CAP_CHOICES` adds the uncapped run and is what gets backtested (75 settings). |
| `solve_risk.py` | Solves each strategy's default risk: the one that puts it at `engine.TARGET_DD` (6%) maximum drawdown. Prints its own solve **and** what the registered number actually produces. Not part of the pipeline; it is how the constants in `strategies.py` are derived. |
| `run_pipeline.py` | Every writer in one pass over the array archive (and it backtests whatever `CHARTER_CAPS` names on top of the dial grid, since the two lists are independent) (the fast way to regenerate everything): per-market xlsx, portfolio, the cap grid, the charter hand-off, then the pages. |

Parsing is imported from `../charter/scripts/charting_core.py` (`parse_array`); do not
rewrite it here.

### Adding a strategy

If the new strategy is the cap family at a different cap, it is one line:

1. `Strategy(key=..., title=..., rule4=cap_rule4(3.0), risk_pct=1.0)` in `strategies.py`,
   appended to `REGISTRY`. Any `risk_pct` will do to start with.
2. `venv\Scripts\python.exe solve_risk.py` &mdash; it prints the risk that puts the new
   strategy at 6% drawdown and says the registry is stale. Paste that number back.
3. `venv\Scripts\python.exe run_pipeline.py`.

Its Rule 4 text, lede, caveat, footers and navigation buttons are all generated from the
cap, and a cap already in `CAP_CHOICES` costs no extra backtest — it is already in the grid.

If Rule 4 needs a genuinely different *shape* (a trailing stop, a time exit, a target that
is not priced off a reversal or an R multiple), it is a new `Rule4` beside `ENTRY_BAR`:

1. Write the policy factory beside `target_policy` / `entry_bar_policy`. It gets `pos` (side,
   entry, stop, risk, and the entry bar's own high/low/tick), the bullish levels and the
   bearish levels known at the bar's start, and returns `(price_or_None, reason)`.
2. If it invents a new exit reason, add it to `VAR_REASONS` (`run_portfolio.py`),
   `prettyReason` (`build_equity_html.py`) and `TRADE_COLORS` (charter's builder).
3. Build a `Rule4(token=..., label=..., policy=..., texts=...)` with `in_grid` left `False` —
   it is not a point on the cap dial — and give it `rule4` / `rule4_text` / `lede` / `caveat`
   text, which for a one-off setting is written rather than generated.
4. `Strategy(key=..., title=..., rule4=<that>, risk_pct=...)`, appended to `REGISTRY`, then
   `solve_risk.py` for the real `risk_pct` as above.
5. Add the key to `CHARTER_STRATEGIES` if it should be drawn on the charts.

Everything else — the runners, the workbooks, the variant grid, the pages, the strategy
switcher, the PDF picker — follows from the registry. The pages leave the cap dial and the
*Choosing the profit cap* section out automatically when `in_grid` is `False`.

## Portfolio money management (`run_portfolio.py`)

One shared account, starting $100,000, processed chronologically by date, run separately per
strategy. A market's trades (which trades, their entries/exits, their R) are
capital-independent, so they are reused verbatim and only the money management is re-run on
the shared account.

- **The strategy's own `risk_pct` on liquid capital.** A new trade risks that share of
  `cash − risk already tied up in open trades`. Each open trade ties up its own risk
  until it closes. The percentage differs per strategy &mdash; see
  [Risk per trade](#risk-per-trade-one-number-per-strategy).
- **Cash changes only when a trade closes** (realized P&L added). Open trades are never
  marked to market.
- **No cap** on concurrent positions.
- **Same-day order: all entries first, then exits.** A new trade is sized while that day's
  closing trades still tie up their risk (smaller base → smaller risk); the exits then book
  P&L and grow the balance. Multiple same-day entries are sized in market-name order.

**Slippage** is charged as tick slippage — `SLIP_ENTRY_TICKS` (1) on entry, `SLIP_TARGET_TICKS`
(1) on a limit take-profit, `SLIP_STOP_TICKS` (3) on a stop — converted to R through each
trade's own risk distance. In dollars this equals ticks × tick × position size, the true
slippage. Constants live at the top of `run_portfolio.py`. Fees/commission are omitted
(negligible for liquid futures relative to slippage).

### Risk per trade: one number per strategy

**Every strategy is published at its own risk: the one that puts *that* strategy at a 6%
maximum drawdown** (`engine.TARGET_DD`). So all three pages open at the same **pain**, and
the only thing left to compare is what each one earns for it.

| | risk per trade | 1R = |
|---|---|---|
| quickfix (1.9R) | **1.39%** | 1.39% of liquid capital |

These are **measured constants**, not choices: `solve_risk.py` bisects for them (max drawdown
rises monotonically with risk) and prints both its own solve and what the *registered* number
actually produces.

It calls the registry **stale only when the registered risk misses the target**, not when it
differs from the solve in the third decimal. The registry deliberately carries round numbers
(1.39 against a solved 1.391) and an exact-match test would have left the tool complaining
forever about a difference that moves the drawdown by nothing. The tolerance is 0.05, the same
one the report's own chart uses on its bisection. Re-run it after any change to the rules, the fill model or the
archive — they all moved when gap fills went in on 2026-07-27. They live in `strategies.py`
rather than being solved on every run so that the workbooks, the ledgers and the pages all
quote one published figure and the reports do not shift under the reader.

Opening every page at one bet size was the old behaviour, and it was wrong in a specific way:
it showed three different depths of hole and invited ranking them on return alone, which
flatters whichever strategy was allowed to dig deepest, and it meant a strategy's page could
quote another strategy's number (user, 2026-07-27).

`engine.RISK_PCT` is a different thing — the **reference** risk the shared cap grid in
`_variants.json` is priced at, and the only risk at which a page's replay is pinned to a
server figure. It tracks quickfix's number because quickfix is the reference strategy;
nothing depends on them being equal.

### Where it stands (2026-07-28 data, 28 markets with trades, at 1.9R / 1.39%)

| | quickfix (1.9R) |
|---|---|
| Risk per trade | 1.39% |
| Net return | **+206.16%** |
| Gross return | +221.40% |
| Max drawdown | 6.00% |
| **Return / drawdown** | **34.4x** |
| Closed trades | 88 |
| Win rate | 63.6% |
| Average winner | +2.19R |
| Average hold | 1.2 bars |
| Max concurrent | 5 |
| Time in market | 48% |
| Longest losing run | 4 |

The drawdown is 6.00% by construction: 1.39% is the risk solved to put 1.9R exactly there.
Both numbers come off the cap chart at the bottom of the report, which is the whole point of
that section.

The uncapped end of the family is far behind: $158,195 at 0.396% risk, 9.7x. It wins barely a
quarter of the time with winners nearly three times the size, and that combination produces
long losing runs (13 straight against 4), which is a deep hole; held to the same 6% it must
be sized right down, and that gives away far more than the big winners bring back. That is
visible on the cap chart rather than as a strategy of its own.

**Return / drawdown is the ranking metric**, not total return. Risk per trade is a dial, so a
shallower edge can be levered up to meet a given drawdown, while the reverse conversion does
not exist — a bigger total return bought with a deeper hole is not automatically the better
strategy.

**Do not read this as a verdict.** It is ~7 months and 84–85 trades, and max drawdown — the
thing both of these risks are solved against — is the most sample-dependent statistic in the
project. This table was rewritten twice in one day by changes to the **fill model alone**,
with the strategies untouched. Read the fill assumptions as the biggest open risk here.

Caveat on every drawdown figure here: ~7 months and 76–85 trades. Max drawdown is a single
worst-path observation and the most sample-dependent statistic in the project. The structural
reasons above will hold; the specific 6.00% will not — expect it to deepen as the sample
grows, which is a reason to treat every risk in the table above as a ceiling rather than a
target.

#### What the cap sweep shows (same data, at the reference risk)

All at the reference risk, 1.39%:

| cap | 2R | **2.5R** | 3.5R | 4.5R | 5R | 6R | 7R | 8.5R | 10R | none |
|---|---|---|---|---|---|---|---|---|---|---|
| return | +199% | +249% | +231% | +308% | +309% | +314% | +424% | +425% | +294% | +266% |
| max DD | 6.00% | 7.09% | 6.92% | 7.99% | 7.97% | 12.61% | 11.88% | 11.86% | 19.48% | 19.48% |
| ret/DD | 33.1x | 35.1x | 33.4x | 38.6x | 38.8x | 24.9x | 35.7x | 35.9x | 15.1x | 13.7x |
| trades | 88 | 84 | 80 | 79 | 79 | 79 | 79 | 77 | 76 | 76 |
| win rate | 61% | 58% | 48% | 44% | 42% | 38% | 38% | 35% | 32% | 28% |

**Do not rank the caps off this table.** It compares them at one bet size, and at one bet
size a wider cap is being handed a deeper drawdown for free — part of its bigger return is
just the bigger hole it was allowed to dig. Worse, the ranking *moves with the risk*: return
compounds exponentially with risk while drawdown is bounded near 100%, so an earlier reading
of this same sweep put 5R on top at 1% and 7R/8.5R on top at 1.573%. Nothing about the
strategies changed between those readings — only the dial did.

The comparison that survives is the **levered one**: solve for the risk that holds every cap
to the same drawdown, and the caps are being asked the same question. That chart lives at the
bottom of every cap-family report page and it puts **2.5R first**, which is why it is
quickfix's default.
See [Choosing the profit cap](#choosing-the-profit-cap--the-section-at-the-bottom-of-the-page).

What this table *is* good for is the shape: **drawdown moves in plateaus** (5.1% → 6.8% →
10.1% → 16.7%), because on ~80 trades the worst path is dominated by a handful of trades and
only jumps when the cap crosses one of their exits. Win rate falls monotonically as the cap
widens, from 61% at 2R to 28% uncapped. Both of those are structural and will hold; the
specific peaks will not.

---

## Outputs (`output/`)

Per strategy, `<strategy>` being `quickfix` today.

- **`<strategy>_gold_daily.json`** — single-market ledger: `meta`, `trades` (entry/exit,
  bars, R, pnl%, equity), `equity_curve`.
- **`<strategy>_all_markets_daily.xlsx`** — `summary` (per-market: window, trades, win rate,
  return, obsolete flag, and the `data_end` / `open_at_end` counts) + `trades` (all markets).
- **`<strategy>_portfolio_daily.xlsx`** — `summary` (net/gross return, drawdown, streaks,
  averages, hold time, time in market, slippage), `equity_curve` (daily, with a chart),
  `trades` (gross/cost/net R, prices, P&L, running balance).
- **`equity_<strategy>.html`** — standalone interactive report: the **four rules** (1–3
  shared, 4 this strategy's), the **Rule 4 cap dial**, equity + drawdown + open-positions
  panels, KPI + per-trade stat tiles, a sortable trade blotter, a per-market breakdown, the
  **daily calendar**, and
  **Choosing the profit cap** at the bottom (the 0R–10R grid twice over: at a constant 1%
  risk, then levered to a constant 6% drawdown, each with its own generated reading). The cap dial and that last section are **left out for a
  strategy outside the cap family**, since there would be no number in its Rule 4 to dial and
  it would not be a point on the cap axis. Everything else, including the risk dial, is the
  same on every page. **Every page opens with
  the strategy switcher** — one button per registered strategy, current one filled, so you
  click straight from one to the next. The buttons are generated from the registry,
  so a new strategy appears on every page as soon as the pages are rebuilt. It also carries
  the **risk dial** and the **Export PDF** button (both below).
- **`report.html`** — the print/PDF report, carrying **every** strategy (below).
- **`conclusions.html`** — two free-text fields that print at the end of the exported PDF
  (below).

### The daily calendar

Every trading day, in order: date, **total capital**, drawdown, positions open, and the
entries and exits booked that day (entries green, exits red, an em dash where nothing
happened). It scrolls inside its own box on screen and the print stylesheet opens it out, so
it runs to several pages of the PDF.

**It is on both page types and it prints** (user, 2026-07-28). It used to be a collapsed
`<details class="noprint">` on the interactive page only and was left out of `report.html`
altogether, on the reasoning that a 180-row table per strategy would bloat the PDF; the
effect was that the calendar simply was not there when it was wanted. One markup block,
`DAILY_HTML`, now serves both.

### The market universe on the reports

**Every market that was backtested appears under *By market*, including the ones that never
produced a trade** — they show `0` trades and are tagged **obsolete** where that is why.
Listing only the markets that traded made the research look far narrower than it was: 41
markets are tested, the rules fire on 28, and "no setup ever qualified here" is itself a
result worth seeing. The lede and footer now say both numbers.

For an untraded row the sums are genuinely `0` (P&L, total R) while the ratios and extremes
are **undefined**, so win rate, average R, best and worst print an em dash rather than a
misleading `0%`. Those nulls always sort last, whichever way the column is pointed, so they
never push the real rows off the top. The full list travels in
`_equity_<strategy>.json` as `markets_all` (name + obsolete flag), written by
`run_portfolio.py` from the backtest results.

### The rules block

Each page states the strategy in full before any figure: the four numbered rules as cards
(1–3 identical everywhere, 4 the strategy's own), then how the trade is actually placed
(entry fill, stop, 1R = the risk per trade), then an explicit note that **entries use the
reversal levels
only — no timing, cycle or aggregate signal is involved**. That last line exists because the
page used to describe "time-and-price reversal signals", which misled a first-time reader:
the umbrella method is "time and price meet", but these strategies are the price half alone.

The text lives in `strategies.py` (`SHARED_RULES`, `entry_mechanics(risk_pct)`,
`PRICE_ONLY_NOTE`, and `rule4_text(cap)`), so a new strategy writes nothing at all — its Rule
4 wording follows from its cap. All of it is phrased for the short side, with the long stated
as the exact mirror. Two of those are **functions, not constants**, because they quote numbers
that are dials: `entry_mechanics` states 1R as a percentage of capital (it said a hardcoded
"1R = 1%" until the risk moved off 1%), and `rule4_text` states the cap.

### PDF export

The **Export PDF** button opens a picker (checkbox per strategy, current one pre-ticked,
plus **Select all**) and opens `report.html` for the chosen ones — one strategy per printed
page, at the risk currently set — which calls the browser's print dialog. Choose "Save as
PDF" there.

**No PDF library is bundled, deliberately.** The browser's own print-to-PDF produces
selectable, searchable vector text and small files; an `html2canvas`/`jsPDF` approach
rasterises the page into images, adds hundreds of KB to every page, and would make the trade
tables unsearchable.

**Pick the right destination in the print dialog: "Save as PDF", not "Microsoft Print to
PDF".** The Windows printer rasterises every page — a report came out 5.9 MB across 19
pages, as 498 JPEGs with zero embedded fonts and no selectable text (measured 2026-07-25).
Chrome's own "Save as PDF" keeps it vector. The report page says this above the print button.

**Bug that produced a flat equity curve (fixed 2026-07-25).** `Number(null)` is `0`, not
`NaN`, so reading the risk straight out of the query string —
`const rp = Number(params.get("risk"))` — made a report opened **without** `?risk=` re-run
the simulation at 0%: every position sized to nothing, no trade booking a cent, and an
equity curve flat at exactly the starting capital. The Conclusions page's "Open report" link
did exactly that. The parameter is now only applied when actually supplied, and everything
that needs the live value reads `CURRENT_RISK` (the applied number) rather than the input's
raw `.value`, which reads `""` mid-edit and would hit the same trap.

### Conclusions

The **Conclusions** button (immediately left of Export PDF) opens `conclusions.html`: two
large fields, **General conclusions** and **Final conclusions of the author**, whose text is
printed at the **end of the exported PDF**, after the last strategy. Both are optional — an
empty one is left out of the report entirely rather than printing a bare heading.

The text is saved in the browser as you type (`localStorage`, key `strategy_conclusions`);
it is never written to a file and never leaves the machine. **Export PDF also passes it to
the report in the URL hash**, because two `file://` documents do not reliably share storage
in every browser and the text has to survive the hop either way; a hash is read by the page
itself and sent nowhere. The report prefers the hash and falls back to storage, so opening
`report.html` directly still picks up whatever is saved.

Since the conclusions are report-level rather than per-strategy, there is one pair of fields
regardless of how many strategies are selected.

`report.html` embeds every strategy and filters client-side from its query string —
`report.html?s=quickfix&risk=1.5&auto=1` (`auto=1` opens the print dialog on load).
It is always built with **all** strategies even during a partial rebuild, so a
`build_equity_html.py <one-key>` run cannot silently shrink it. It carries one risk control
driving every strategy on the page, so a multi-strategy PDF is always a like-for-like
comparison. The print stylesheet forces the light palette (the dark theme would print as a
solid ink-heavy background), opens the scrolling tables so nothing is cut off, keeps cards
and rows from splitting across the fold, and drops the navigation and the two dials. The
**daily calendar prints** (see below).

Both page types are generated from one stylesheet, one per-strategy markup section and one
script whose renderer is a **factory** (`mountReport(root, DATA)`), so the report can mount
several strategies on one page without a second renderer to keep in step.

### The risk input on the equity pages

Each strategy section has a **risk per trade** number box (0–100%, stepped 0.1 by its own
up/down buttons, which are forced permanently visible rather than appearing on hover) that
re-runs the entire shared-account simulation **in the browser** and redraws everything:
equity curve, drawdown, KPIs, per-trade stats, the blotter's P&L columns and the per-market
table.

**One box PER STRATEGY, like the cap dial** (since 2026-07-27). It was page-level while every
strategy shared one risk; now each opens at its own 6%-drawdown risk, and one box cannot show
three numbers. The old reasoning for sharing was that a multi-strategy PDF should be
like-for-like — but equal **drawdown** is the like-for-like this project ranks on, which is
exactly what the per-strategy defaults give. Typing a number still lets you compare them at
one bet size; the box then says it has been changed and names the default it came from.

This works because **the trades are capital-independent**. Which trades fire, their entry
and exit prices, their R multiples and even their slippage cost *in R* are fixed by price
and reversals — risk changes the dollar sizing and nothing else. So the page can replay
`run_portfolio.py`'s loop over the trade list it already carries, with no rebuild and no
Python round-trip. The replay mirrors that loop exactly, including the same-day
entries-before-exits ordering and the market-name sizing order.

- Nothing is persisted: a section always opens at that strategy's own documented default
  (`Strategy.risk_pct`) so it agrees with the workbook. Reload to get back to it.
- Risk-**independent** figures stay put as you move the dial — trade count, **win rate**, R
  multiples, average hold, time in market, max concurrent. Only the money moves: final
  capital, P&L, and max drawdown (deeper in percent as a bigger bet compounds harder), and
  therefore return/drawdown.
  **Win rate not moving is the point, not a bug.** Risk changes the dollar size of a
  position; it cannot change whether that position was a winner. Win rate is counted off the
  R multiples, which are fixed by price and reversals. The **cap** is the dial that changes
  which trades win, because it moves the exits — which is exactly why the cap grid has to be
  precomputed while risk can be replayed.
- The page self-checks on load: **at the reference risk** (`engine.RISK_PCT`) the replay
  must reproduce `run_portfolio.py`'s own final capital for the cap in force, and it logs a
  console warning if it ever does not. That is the guard against the JS port drifting from
  the Python. It re-simulates at the reference rather than checking the live figures, because
  a page no longer opens there — testing "if the dial happens to sit on the reference" would
  silently never fire on two of the three strategies.
- `charter_trades_*.json` is unaffected — the risk dial is a display-side exploration, it
  never changes the trades or any file on disk.

Two things to read carefully at high risk. **Above ~5% the model stops describing anything
tradeable** (the page says so in red): it assumes any position size fills at these prices,
and it has no margin, no liquidity limit and no ruin — a losing run just shrinks the base
forever instead of ending the account. And **return/drawdown is only comparable at equal
risk**: return compounds exponentially with risk while drawdown is bounded near 100%, so the
ratio inflates absurdly. Compare strategies at the *same* setting, not across settings —
which is why the published defaults are solved to put every strategy at the same **drawdown**
instead.

Why `xd`, `gr` and `cr` are in `_variants.json` at 6 decimals: the replay needs the
risk-release day, the gross R and the cost R, and it compounds them across ~80 trades.
Rounding R to 3 decimals put the page $13.56 away from the server's figure (measured
2026-07-25); at 6 it agrees to the cent.

### The Rule 4 cap dial on the reports

Beside Rule 4's card, a **cap-family** page carries a **profit cap** number box (0R–10R,
tenth-R steps to 5.5R and quarter-R above, plus a **no cap** tick) that switches the entire report to that setting:
equity curve, drawdown, KPIs, per-trade stats, the blotter, the per-market table — and the
prose. The Rule 4 card, the lede, the honesty note and the footer are all regenerated from
the cap (their text comes from `strategies.py`, shipped per cap), so a page showing 4.25R
never still claims a 2.5R ceiling.

**A strategy outside the family would have no dial.** The section is built without one
rather than shown disabled: there would be no number in its Rule 4, so a control would have
nothing to move. `IN_FAMILY` in the page script also refuses the `?cap=key:tok` URL route for
such a strategy, which would otherwise print its section holding a cap run's trades.

**Precomputed, not replayed — the opposite of the risk dial.** Risk works in the browser
because the trades are capital-independent: risk changes the dollar sizing and nothing else.
The cap changes the trades. Every exit moves, and because only one position per market runs
at a time, an earlier exit frees that market for a signal a longer hold would have missed —
so the trade list itself differs and there is nothing to replay from. `run_portfolio.py`
therefore backtests **all 75 settings** and writes them to `_variants.json`; the page just
swaps trade lists and re-runs the money management on top. Parsing the array archive is the
slow part and is unchanged, so the grid rides along on the same pass.

- **One dial per strategy, not per page.** Rule 4 is exactly what tells the strategies
  apart, so a single shared dial would collapse every cap-family strategy on a report onto
  the same numbers. Risk stays shared (one account, one money-management model);
  the cap is per section, on both the interactive pages and `report.html`.
- **The whole grid shares one day calendar**, so moving the dial does not shift the equity
  curve's x-axis: 4R and 8R are drawn over exactly the same period.
- **Nothing on disk changes.** The workbooks, the JSON ledgers and the charter hand-off are
  always written at the strategy's **default** cap (quickfix 2.5R), and the
  page says so under the dial. The dial is display-side exploration, exactly like risk.
  (The charter hand-off is a separate chosen set of caps and need not contain the default —
  the dial's note is careful not to claim otherwise.)
- **The page self-checks at every cap.** At the default risk its replay must reproduce
  `run_portfolio.py`'s own final capital for the cap in force; it logs a console warning if
  it ever does not. `build_equity_html.py` additionally refuses to build if the grid's figure
  for a strategy's default cap disagrees with that strategy's workbook.

#### Choosing the profit cap — the section at the bottom of the page

The dial answers "what happens at 1.7R". The last section of every cap-family page answers
"what happens at all of them", which is the question one setting cannot. **Two charts over
the same 0R–10R grid**, stacked, read top to bottom:

1. **At a constant 1% risk per trade** — the real result. Five panes: final capital, **max
   drawdown**, the risk (a flat line, on the chart precisely to show that it never moves),
   return/drawdown, win rate. This is what each cap actually did on the same bet.
2. **Levered to a constant 6% drawdown** — the ranking. Three panes: final capital, **the
   risk each cap is allowed**, win rate. The risk is solved per cap by bisection (max
   drawdown rises monotonically with risk) so every cap bottoms out in the same hole.

**Why both, in that order.** The first is honest about what happened but cannot rank
anything: with the bet fixed, the drawdown fans out from 4.3% to 28.0% across the grid, so a
wider cap's bigger return is partly just the deeper hole it was allowed to dig. Seeing that
fan is what makes the second chart's point land. The second asks the question the ranking
metric implies — for the same pain, which cap ends up with the most money? — and it is the
one to rank on. The first chart's own caption says so, generated from its own numbers.

Return/drawdown appears on the **first** chart only. On the levered one the drawdown is
pinned at 6% by construction, so return/DD is just return ÷ 6 and the pane would redraw the
capital line in different units.

(This replaced a pair of sections — a 2R–10R sweep and a separate 0R–3R zoom — on
2026-07-28. They existed only because the dial could not reach below 2R; once one grid
covered everything at tenth-R resolution there was nothing left to zoom into.)

**It reorders the family, and it flattens it.** Levered to equal drawdown the top of the grid
is **1.9R ($306,421, 1.391% risk, 34.4x)** — which is quickfix's default, so the strategy now
sits on the point its own chart picks — then **2R ($299,000, 1.391%)**, **3.7R ($291,206,
1.211%)**, **2.5R ($290,519, 1.175%)** and **5R ($289,469, 1.027%)**. Five settings inside 6%
of each other, which is nothing on this sample. What the chart says clearly is the *bottom*:
the uncapped run is the **worst of the whole family** at $158,195, because it must be sized
down to 0.396% per trade to hold 6%.

**The plateau starts at 1.3R.** Allowed risk climbs from 0.19% at 0R to **1.39% at 1.3R**,
holds there to 2R, then falls to 1.18% at 2.1R. Below 1.3R the cap is too tight for the
winners to pay for the losers and the account cannot carry a full bet — capital falls away to
**$94k at 0R**, where the target sits on the entry price and the win rate is 1%. 0R is kept
in the grid deliberately as that sanity anchor: it is what exposed the already-through gap
bug on 2026-07-27, by coming out best on the whole grid, which is impossible on its face.

**The default follows this chart, but the chart's peak is not to be chased.** That top point
has read 2.5R, then 2R, then 3.75R, and now 1.9R across successive changes to the **fill
model** and to the grid's resolution — never to the strategies themselves. 3.75R is not even
a setting any more: tenth-R steps do not include it. So take the **band** as the finding, and
treat a default sitting on the current peak as a coincidence worth re-checking rather than a
result.

**Both charts explain themselves, from themselves.** Every number in the prose under them is
**read out of the grid at render time**, not typed, so it cannot go stale, including which
stretch of caps shares the same allowed risk and where that falls off a cliff. The levered
chart's reading was cut from five passages to three on 2026-07-28.

The first of those three, *Where it pays*, is generated end to end, and it is where the
**best point is highlighted in yellow** — that is the finding the whole report exists to
make, so it is marked as such rather than left to be picked out of a sentence.

The other two, *Why* and *How much to trust it*, are the **author's own words**, supplied
verbatim (user, 2026-07-28). Their numbers are still read out: the cap named as the sweet
spot is `best.cap` off the levered grid, not a literal, so the passage follows the data if
the peak moves. Everything else in them is fixed prose and has to be revisited by hand — that
is the trade for saying it in the author's voice, and it is the one place in the report where
a claim could age.

Mechanics:

- **Neither follows the risk dial** — that is the point of them — so each is computed once
  per page and cached. Both cap markers still move with the dial, and a dial setting off the
  axis is labelled rather than silently unmarked.
- Solved risks are cached **per cap token**, so a cap appearing on both charts is bisected
  once and the two can never disagree.
- **One `simulate()`.** Both charts call the same function the page runs on itself, with a
  `lite` flag that skips the daily narrative. A second stripped-down copy of the money
  management would be free to drift, and the charts would quietly lie. The levered one also
  checks that the bisection converged: every point within 0.05 of the target, or it warns.
- The **uncapped** run is a dashed reference line on both, never a point — "no cap" is not
  10.25R and does not belong on that axis. An uncapped page marks no point and says so.
- They **print**; only the dial is `noprint`. They are results, not controls.
- Drawn **synchronously at mount**. Deferring to an animation frame silently skipped them on
  any page whose cap was `none`, including in the printed PDF.
- `TARGET_DD` and `FIXED_RISK` in the chart code are the two constants to change.

Rows travel packed — positional arrays indexed against shared market/date/reason tables
(`VAR_COLS` in `run_portfolio.py`, unpacked by `unpackCap` in `build_equity_html.py`; change
one side and you must change the other). 75 settings of named JSON fields would add several
megabytes of repeated key names to every page; packed, `_variants.json` is 425 KB and the
pages 516 KB.

- **`_variants.json`** — the variant grid, shared by every page (intermediate). `caps` is the
  single cap axis — the dial's and both charts'; `extra` lists the settings that are *not*
  caps; empty today, since quickfixpro was the only one), packed and replayed identically but
  not points on that axis.
- **`_equity_<strategy>.json`** — that strategy's headline numbers at its default Rule 4 and
  its own `risk_pct` (intermediate). Its `r4` field is the variant token the page opens at —
  a cap token for the family, something else for a strategy outside it, which is why it is
  not called `cap`. It also carries `ref_final`: the same account replayed at the **reference**
  risk, which exists only so `build_equity_html.py` can check the shared grid against this
  workbook without the risk difference tripping the guard.
- **`charter_trades_<key>.json`** — the charter hand-off, one file per exported **cap** or
  **strategy** (below).

Ledger note: the per-trade `target` field records **the Rule 4 level in force at entry**
(it can move later). It replaced an old quickfix-only `target_5r` column, which could only
ever describe one strategy — and now could not even describe one, since the cap is a dial.

### Charter hand-off schema (`charter_trades_<key>.json`)

```
{
  "meta": { "strategy": "cap02_25", "title": "2.25R", "cap": "2.25", "rule4": "...",
            "timeframe": "daily", "n_markets": N, "n_trades": M, ... },
  "markets": {
    "Gold_Futures_COMEX": {
      "tick": 0.1, "price_decimals": 1,
      "trades": [
        { "side": "short"|"long",
          "entry_date": "YYYY-MM-DD", "entry": <price>,
          "exit_date": "YYYY-MM-DD"|null, "exit": <price>|null,
          "stop": <price>, "target": <price>,
          "reason": "target_r"|"target_bar"|"stop"|"bullish_reversal"|"bearish_reversal"
                    |"unknown_pl"|"data_end"|"open_at_end",
          "r": <gross R multiple>|null, "bars": <int>|null }
      ]
    }, ...
  }
}
```

**One file per OVERLAY, all in the same schema** — charter globs `charter_trades_*.json` and
picks up a new one on its next build with no code change. Cap names are **zero-padded**
(`cap02_00`, `cap02_25`, `cap05_00`) so sorting the filenames sorts the caps: charter lists
the boxes in filename order, and `cap10` would otherwise land before `cap2`. A strategy
exported whole is named by its key, which sorts after every `cap…` name, so the caps stay
together in cap order and the strategies follow them.

Two lists at the top of `export_charter_trades.py` choose the set, because Rule 4 has two
shapes:

- `CHARTER_CAPS` — today **1.9R, 2R, 2.25R, 2.5R and 5R**. **1.9R is quickfix's own default
  and MUST be here**, or the charts draw every cap except the one the strategy actually runs
  at; it was added on 2026-07-28 when the default moved there, and it has to move again if
  the default does. The rest bracket it: 2R–2.5R is the levered band, 5R a wider comparison.
- `CHARTER_STRATEGIES` — **empty** since quickfixpro was retired. Kept because the export
  writes a whole strategy and a cap through the same code path, so re-adding one is a single
  key.

`export_charter_trades.py` also **prunes** any `charter_trades_*.json` it no longer owns,
because charter globs the directory and a file left over from an earlier set would go on
being drawn.

**Why not the whole grid.** Bytes are not the obstacle (no extra backtest either — the
pipeline already computes every setting). Legibility is. Rules 1–3 do not involve the cap, so **every cap takes the same setups**: all their entry
triangles land on the same bar at the same price, and 34 overlays would stack 34 markers on
one point and fan 34 exit lines from it. Charter also has one line style for these overlays
and colour already means the outcome, so they cannot be told apart on the chart at all — they
are read one tick at a time.

**Caps, not every strategy** (2026-07-27). This used to be one file per registered strategy
(`charter_trades_quickfix.json`, `…_slowfix.json`). Once a cap-family strategy turned out to
be just a dial position, the useful comparison on a price chart became a few caps. The
uncapped setting is not exported at all — its trades are the least interesting on the chart.
Nothing outside the cap family is exported today.

The set is **independent of the reports' cap grid** and need not sit on it: 2.25R is exported
and is on no grid the reports draw, since the grid moved to tenth-R steps. `run_pipeline.py`
backtests whatever `CHARTER_CAPS` names, on top of the grid, so the two can diverge freely. This is
only about what charter draws; the workbooks, JSON ledgers and HTML reports are unchanged.

`reason` was **`target_5r`** until the cap became a dial; it is now **`target_r`** — the exit
means "the R cap was hit", and 5 is only one setting of it. **`target_bar`** was quickfixpro's
target, the entry bar's own extreme; nothing emits it now, but charter still colours it.
charter colours all three green, the same as any other target, so files exported before the rename still draw correctly and so colour never starts
meaning "which strategy" instead of "what happened".

Trade geometry only — the entry plots at the first-reversal price on the entry bar, the exit
at the fill level on the exit bar. `unknown_pl` exits at the stop; `data_end` exits at the
last bar's close (drawn grey — it is not a rule exit); `open_at_end` has null exit. charter reads this at build time and overlays the trades on each market's **daily**
price pane behind a toggle. To refresh the overlay end to end:

1. Here: `venv\Scripts\python.exe export_charter_trades.py` (regenerate after a rule change).
2. In `../charter`: `venv\Scripts\python.exe scripts\chart_all_markets_reference.py`
   (append a market substring, e.g. `... gold`, for a fast single-market rebuild).
3. In `../charter`: `venv\Scripts\python.exe serve.py`, open the site, and click the **T**
   button (green/red triangles) on the right rail. It opens the **Strategy trades box** —
   one checkbox per exported overlay (1.9R, 2R, 2.25R, 2.5R, 5R), each labelled with
   its own Rule 4 and its trade count — so you can show any combination or none. Long entry =
   up-triangle, short = down-triangle, exit = a marker on the exit bar; the entry→exit line
   is green for a win, red for a stop, amber for an ambiguous (`unknown_pl`) outcome, blue
   for a still-open trade. Daily timeframe only; markets with no trades show nothing.

**Colour is the outcome**, and every overlay is drawn **identically** — one dotted line, one
round exit marker for all of them. There is nothing to tell them apart on the chart, on
purpose: they all share Rules 1–3, so their entry triangles sit on exactly the same bar and
price, and a different dash per overlay would only decorate lines that start from the same
point. **Read them one tick at a time**; the exits and the lines are what differ. (The old
four-style set — dot/dash/long-dash/dash-dot — is in git if a genuine
need to tell overlays apart at a glance ever returns.)

---

## Running

```
venv\Scripts\python.exe run_pipeline.py             # everything, every strategy (one pass)

venv\Scripts\python.exe engine.py                   # gold single-market ledger + summary
venv\Scripts\python.exe run_all.py                  # per-market xlsx
venv\Scripts\python.exe run_portfolio.py            # shared-account xlsx + _equity_<s>.json
venv\Scripts\python.exe build_equity_html.py        # -> output/equity_<s>.html
venv\Scripts\python.exe export_charter_trades.py    # -> output/charter_trades_<key>.json

venv\Scripts\python.exe solve_risk.py               # each strategy's 6%-drawdown risk
```

Every script takes optional strategy keys; with none it runs all of them. Reading the array
archive is the slow part, so prefer `run_pipeline.py` for a full refresh — it parses the
archive once and feeds all four writers, then rebuilds `report.html` and `conclusions.html`.

Two things follow from the cap grid. `run_portfolio.py` backtests **all 75 settings** (that is
what `_variants.json` is) while `run_all.py` and `export_charter_trades.py` ask for the
strategies' own caps only, since their outputs are written at the default. And
`build_equity_html.py` needs `_variants.json` to exist — run `run_portfolio.py` first, or
just use `run_pipeline.py`.

Requirements: `pandas`, `openpyxl` (see `requirements.txt`).

## Working agreements

- Commit straight to main. English only in code/comments/strings. No emoji.
- Simulation inputs (starting capital, risk per trade, slippage) live here; data and charts do not.
- When the user supplies text verbatim, use it verbatim.
