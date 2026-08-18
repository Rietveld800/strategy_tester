# strategy_tester — strategies, backtest, risk management

Strategy department of the trading system (see `../trading_system/README.md` for the
umbrella contracts). Turns the Socrates "time and price meet" method into explicit,
testable rules, backtests them on the array files, applies risk management, and hands the
resulting trades to `charter` for display.

**Scope (firm): strategy_tester produces trade results. It never scrapes data and never
renders charts.** It reads the array (meta) xlsx files from `hyperliquid_bot` (via `charter`'s
parser) and, for the 1-minute engine, the bars/settlements/roll calendars from `../data_center`;
it writes trades + equity as JSON / xlsx / standalone HTML reports.

**One strategy is published today: `quickfix1m1dc`**, the 1-minute engine. The daily
registry is **empty** — see [The pivot](#the-pivot-2026-08-12) below. Everything from
*The strategy family* down to *Charter hand-off* documents the **daily** product, whose code
is intact and unused; the 1-minute strategy is documented in
[`CLAUDE.md`](CLAUDE.md#1-minute-workstream-2026-08-03--the-published-strategy-since-2026-08-12)
and in `../data_center/docs/backtest_1m_design.md`.

## The pivot (2026-08-12)

`strategies.REGISTRY == []`. Twenty-five daily strategies that morning, five by the
afternoon, none by the evening — **quickfix1m1dc replaced them**, it did not join them. The
daily model's biggest open risk was always its fill assumptions, one daily bar standing in for
an intraday path it cannot see; the 1-minute engine answers that with real 1-minute bars
rather than with a proxy, so publishing both would be publishing the question beside the
answer.

| when | retired | why |
|---|---|---|
| 2026-07-28 | `slowfix` | the cap family at no cap: a dial position, never a method |
| 2026-08-12 | `quickfixwick`, `quickfixclose2` … `quickfixclose20` | the hold sweep had measured its curve and it did not move: one bar is where the exit pays |
| 2026-08-12 | `quickfix`, `quickfixclose0`, `quickfixopen1`, `quickfixclose1`, `quickfixopen2` | the 1-minute engine became the published strategy |

**The daily code stays and is not to be tidied away.** `engine.py`, `strategies.py`,
`run_all.py`, `run_portfolio.py`, `build_equity_html.py`, `export_charter_trades.py`,
`solve_risk.py` and `run_pipeline.py` are all still correct — there is nothing registered for
them to run. Registering one `Strategy` brings the whole daily side back: pages, variant grid,
cap dial, charter overlays. `build_equity_html.py` in particular can never go, since
`build_1m_report.py` and `research_1m_levels.py` import its `CSS`.

**Two guards, because an empty registry is dangerous rather than merely idle.**
`export_charter_trades.prune()` deletes every `charter_trades_*.json` it does not own, and
owning nothing it wiped `charter_trades_quickfix1m1dc.json` — the only overlay left. Found by
running it. So `run_pipeline.py` now raises on an empty registry instead of spending an
archive pass on a grid nobody reads, and the prune refuses on an empty set. The guard sits in
`prune()` and not only in `main()` because `run_pipeline` calls `export()`/`prune()` directly.
**A prune that owns nothing is not a prune, it is a wipe.**

**The charter hand-off is `export_charter_trades_1m.py`**, the only owner of
`output/charter_trades_*.json` now. It reads the published blotter (no backtest), maps the
engine's contract key to charter's market **folder** through `run_1m.market_info()`, and
writes one file in charter's **existing** schema — which is why charter needed exactly one
line for it: `close1` added to `TRADE_BY_R`, because that reason names a *moment* (the next
settlement) and so covers a win and a loss alike, and its colour must come off the trade's own
R. Colour is the outcome, always. `run_1m.py` calls the exporter, so the overlay cannot be a
refresh behind the report beside it.

A 1-minute trade enters at a minute inside the session and exits at the next settlement or at
its stop, so on charter's **daily** pane the entry marker sits on the entry session's bar and
the exit marker on the exit session's bar. The minute is lost deliberately — the daily pane
cannot show it, and charter's 1m trade study is where the intraday path is read. A trade
stopped in its own session draws a **vertical** line on one bar.

### What the Update button builds

`../trading_system/refresh.py`, which is what charter's rail **Update** button runs:
`data` → `bars` → `strategy1m` → `matrix1m` → `hybrid1m` → `levels1m` →
`charts`, about **12 minutes**. Measured 2026-08-12: `run_1m.py` 111 s, `run_1m_matrix.py`
240 s, the hybrid-stop variant 1 s (it reads the matrix JSON), each level study 54 s, the
chart build ~4 min. The old `strategy` step (`run_pipeline.py`) went with the daily registry.

**`rcut1m` and `rcut1mhybrid` are reachable but deliberately not in a full run** (user,
2026-08-12). Each R-cut band grid is ~231 engine passes, about **90 minutes**, which is not a
thing to hang off a button pressed to see this morning's bars. `refresh.EXTRA_STEPS` holds
them: `step_for()` searches it, `run_all()` never does, so `python refresh.py rcut1m` and
`/api/refresh` reach them and a plain `python refresh.py` cannot. **Each page carries its own
update button** (`quickfix1m1dcRcut4th5th.html` posts `rcut1m`,
`quickfix1m1dcRcutHybrid.html` posts `rcut1mhybrid`, both read from the payload's
`refresh_step`, so a page can only rebuild itself), which posts that step key to charter's
`/api/refresh` — the same runner, driven from the page that shows the result, so there is no
second way to build anything. The page finds
the server by probing `127.0.0.1:8000..8019` (it is usually opened straight off disk, so it
has no origin to infer a port from), posts `text/plain` so a `null` origin never triggers a
CORS preflight, streams the log, and reloads itself when the run finishes. `serve.py` echoes
`Access-Control-Allow-Origin` for `null` and loopback origins only.

**THERE IS ONE GRID PER STOP ANCHOR** (Lode, 2026-08-16). The page used to be the 4th/5th
reversal stop alone and said so nowhere, which reads as a fact about the strategy rather than
about that stop. The band cuts the ratio whose numerator is **1R in price, level to stop**, so
widening the stop to the session extreme moves every cell of the grid (audit s.19: PA
2026-08-07 is 0.226 on the ladder stop and 0.557 on the hybrid one, straight through the upper
cut) — a band's evidence does not carry across stop modes, and the only honest comparison is
the whole grid on each. `build_1m_rcut_report.py --stop {4th5th|hybrid}`; the anchor's label
and dial come from `run_1m_matrix.STOPS`, so these pages and the matrix cannot disagree about
what `hybrid` means. Outputs and trade caches are per anchor
(`quickfix1m1dcRcut4th5th.*`, `quickfix1m1dcRcutHybrid.*`), each page names its anchor in the
title and the first sentence, and each links to the other. The published band (0.20 / 0.50)
was read off the **4th/5th** grid; the hybrid page opens on it for comparability only and says
so.

**That grid's cache is keyed on the data, not just the band.** It reused every cell from
whatever window it was first built on, so a rebuild after new bars landed finished in three
seconds and republished a stale grid beside a fresh baseline — measured, not hypothetical.
`data_fingerprint()` hashes size and mtime of every bars parquet (~90 files, ~2 ms) and any
change throws the whole cache away. It errs the safe way on purpose: a wrong cache **hit**
costs correctness, a wrong **miss** costs time. The payload carries `built`, `data` and
`n_cells`, and the page prints the build time, so a stale grid is visible rather than assumed
fresh.

---

# The daily product (retired 2026-08-12, code intact)

Everything below documents the daily backtest as it stood when its registry was emptied. It is
kept because the code is kept: register a `Strategy` and all of it is live again, exactly as
described. Nothing below runs today.

**Five strategies were built at the end** (seven until 2026-08-01, twenty-five until
2026-08-12). They shared rules 1–3 exactly, so they took the same setups on the same
bars, and the only thing the daily project ever compared is **where the profit is taken**.

| | Rule 4 | risk per trade | on the cap dial |
|---|---|---|---|
| **quickfix** | the **cap family** at **1.9R**: the first opposite reversal beyond entry, never past 1.9R | **1.39%**, solved | yes |
| **quickfixclose0** | the close of **bar 0**, the entry bar itself: flat the same day | 1.0%, chosen | no |
| **quickfixopen1** | the open of **bar 1**, held through one night | 1.0%, chosen | no |
| **quickfixclose1** | the close of **bar 1**, one night and the next full day | 1.0%, chosen | no |
| **quickfixopen2** | the open of **bar 2**, two nights and the day between | 1.0%, chosen | no |

**Bars are numbered from the entry bar, which is bar 0** (user, 2026-07-31). Four of
the five are one family — a **bar exit** — parameterised by which bar the trade is
marked out on, and their keys say which. `quickfixopen1` was plain `quickfixopen` until bar
2's open was registered beside it; `quickfixclose0` keeps its bare name, by the user's choice,
and is bar 0.

quickfix's settings are the levered-optimal point of its family, not a guess: 1.9R tops the
constant-6%-drawdown chart and 1.39% is the risk that puts it there. Its cap is a **dial on
the reports**, **0R to 10R** (tenth-R steps to 5.5R, quarter-R above) plus no cap at all, and
every setting is a real backtest — see
[The Rule 4 cap dial](#the-rule-4-cap-dial-on-the-reports). The other four have no
number in their Rule 4 to dial, so their pages carry neither the dial nor the cap charts.

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
   percentage** (see [Risk per trade](#risk-per-trade-one-number-per-strategy)).
   A gapped stop can lose more than 1R; see the daily-proxy assumptions. The stop is **not
   Rule 4** and is live on every strategy here; on two of the five it simply never gets
   the chance to trade — see [Rule 4 — the shapes](#rule-4--the-shapes).
5. **Reward filter (Rule 3).** The nearest bearish reversal below entry must be at least
   **3.5R** below entry, else refuse (not enough room).
6. **Exit (Rule 4).** The one rule that differs, and the whole subject of this project. One
   of the five watches a **price level** (recomputed on every bar from the levels known at
   that bar's start, so a target moves in when a nearer level is drawn and falls away when one
   is elected; only **opposite-side** reversals ever close a trade early). The other
   four exit on a **bar event** — bar *k*'s open or close — and watch no level at all.

### Long setup (mirror)

Bearish ladder for entry, bullish for targets. Tested bearish reversals in
`[low, prev_close)`, ≥3; **first = highest** tested bearish level, second the next highest.
Rule 2: refuse if `open <= second`. Trigger: **close above the first**. Stop = one tick
below the entry bar's low. Rule 3: nearest bullish reversal above entry ≥ 3.5R up.

### Rule 4 — the shapes

| Strategy | Rule 4 | Character |
|---|---|---|
| **quickfix** | The cap family at **cap = 1.9R**: take profit at 1.9R, or at an opposite reversal that sits **closer** than 1.9R (then that reversal is the target). | Takes profit fast. 1.9R is a hard ceiling on every winner. |
| **quickfixclose0** | The close of **bar 0** — the entry bar itself. Opened and shut on the same day. | Never carries overnight. Cannot lose on gross terms. |
| **quickfixopen1** | The open of **bar 1**, the bar that follows the entry bar, unconditionally. | Holds through one nightly session and no further. What it earns is what the night did. |
| **quickfixclose1** | The close of **bar 1**. | Gives the move one whole session to work, with a live stop under it for that session. |
| **quickfixopen2** | The open of **bar 2**. | quickfixopen1 with one more day of room, and a real floor under that day. |

#### Two mechanisms, and why

quickfix watches a **price level**, so it goes through `check_exit`'s shared resolution:
stop first, then gaps, then ambiguity. Its Rule 4 is a **target policy**,
`policy(pos, bull, bear) -> (price, reason)`, called on every bar.

The other four do not. "Out at bar 1's close" and "out at bar 2's open" are **moments**, not
levels: there is no target the market could have filled and nothing to be ambiguous about, so
there is nothing for that half of the machinery to resolve. Their Rule 4 is a **bar exit**,
`bar_exit(pos, bar, k) -> (price, reason) | None`, where `k` is bars since entry and is the
family's only parameter. `k = 0` is the entry bar, and a bar exit is **the only thing in this
engine allowed to close a trade there** — which is what makes quickfixclose0 expressible at
all. `engine.backtest` calls it once at `k = 0` immediately after booking the entry; a target
policy is never called there, and management for it starts the next bar as it always has.

A `Rule4` carries exactly one of the two and refuses to be built with both or neither. A bar
exit also carries `bar_exit_at` (`"open"` or `"close"`), and that is required rather than
decorative — see below.

#### The stop is not Rule 4

**A bar exit that holds past its entry bar keeps its stop** (user, 2026-07-31: only Rule 4
changes, and the stop belongs to the entry mechanics). On every bar between the entry and the
exit bar the stop is resolved exactly as it is for a target strategy — the gap rules, the
worse-than-1R gapped stop, all of it — through the same `check_exit`, handed a policy
(`engine.no_target`) that simply never has a target. There is no second stop test to drift.

On the **exit bar** the order between the two is not a guess:

| | resolves | why |
|---|---|---|
| an **open** exit | **before** the stop | the open is the bar's first price, so nothing can have traded ahead of it. (If that open gapped past the stop, both give the same fill anyway.) |
| a **close** exit | **after** the stop | a stop triggers the moment price touches it; a market-on-close waits for the bell. A stop inside the bar's range was hit first. |

`Rule4.bar_exit_at` is which of the two, and the class refuses a bar exit without it.

**The stop never trades on quickfixclose0 or quickfixopen1** — but that is a *consequence*,
not a rule, and it does not survive a longer hold. quickfixclose0 is shut on the bar that
opened it, and the stop sits one tick beyond that bar's own already-spent extreme;
quickfixopen1 is shut at the *first price* of the next bar, so nothing can trade ahead of it.
On those two the stop still **sizes** the position — 1R is the stop distance, and Rule 3 still
applies unchanged — but **it is not a floor under the loss**. An adverse overnight gap takes
quickfixopen1 out for well over 1R, which is the same arithmetic as a gapped stop everywhere
else here, except that on quickfixopen1 *every* exit is at an open, so it is not a rare case.

On **quickfixclose1 and quickfixopen2** the stop is a floor again, and the figures say so
plainly: at a flat 1% quickfixclose1 wins 66% against quickfixclose0's 97%, and holds 4.62% of
drawdown against 0.06%. That is not the same strategy held longer, it is a different
question — and it is why the longer holds book **fewer** trades (96 at bar 2's open against
117 at bar 0), since a market still held is a market not available for the next signal.

**quickfixclose0 cannot lose on gross terms**, and that follows from the entry rule rather
than from a flattering assumption: the trigger requires the bar to close **beyond** the entry
price (a short only fires when the close is below the first reversal, which is where it
filled), so marking out at that same close is always on the right side of entry. Its losers
are the trades whose move was smaller than the two ticks of slippage charged to get in and
out. On the current data that means a **96.6% win rate and a 0.06% maximum drawdown**, and no
6%-drawdown risk at any bet size at all. It is a real result and it is also the loudest thing
this project has to say about the daily-proxy fill model; read it that way and not as a free
lunch.

Two figures on its page look broken and are not: **max concurrent 0** and **time in market
0%**. Entries and exits both land inside one day, so nothing is ever held when a day is
counted. The KPI subtitles say so. Note that this is quickfixclose0 alone: quickfixclose1 is
held overnight like anything else and reports 4 and 42%.

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
each setting is a real backtest rather than something the page could recompute. The same
mechanism is why the five strategies do not have identical trade counts either — on the
current data quickfixclose0 books **117**, quickfixclose1 and quickfixopen1 book 100, and
quickfix and quickfixopen2 book **96**, purely because of how long each one keeps the market
to itself. Whenever two holds are read against each other, part of the difference is *which
setups each was free to take*, not only what it made of them. That was the single most
important caveat on the bar 3 to bar 20 sweep, where the trade count fell monotonically with
*k*.

#### Adding another bar, or another shape

Another **bar exit** is one `Rule4(bar_exit=close_exit(3), bar_exit_at="close", ...)` with its
own prose plus a `Strategy` on it. Nothing else changes: `close_exit(k)` and `open_exit(k)` are
already parameterised, and the two exit *reasons* name the order type (`exit_close` = a
market-on-close, `exit_open` = a market-on-open), not the bar, so every bar exit shares them
and a fifth would too. `CHARTER_STRATEGIES` is derived from the registry, so it reaches
charter with no second edit. (Until 2026-08-12 bars 3 to 20 were generated from a
`close_texts(k)` / `close_strategy(k)` pair; both went with the sweep, and a new bar writes its
own paragraph like the four that remain.)

A genuinely different **shape** is a new factory beside `target_policy`
(a target) or beside `close_exit` / `open_exit` (a bar event), a `Rule4` with `in_grid=False`
and its own prose, a registered `Strategy`, and a decision on whether its risk is solved or
chosen. Only *that* can need a new exit reason, which must be added to `VAR_REASONS`,
`prettyReason` **and** charter's `TRADE_COLORS` — or to charter's `TRADE_BY_R` instead, if the
reason can cover a win *or* a loss, as both bar-exit reasons can.

`open_exit(0)` raises: bar 0's open comes *before* the entry trigger (that bar's close) has
confirmed anything.

### Daily-proxy assumptions

We only have daily bars, not intraday ticks (that arrives later with IBKR data). So:

- **Entry is confirmed on the close**, filled at the first-reversal price.
- **A price target can never be hit on the entry bar.** Management (stop and target) starts
  the **day after** entry. The entry bar's high/low are already spent by the time its close
  confirms the trade, and by construction the stop sits one tick beyond that bar's own
  extreme, so it cannot trigger there either. The one exception is a **bar exit**, and only
  because it watches no level: quickfixclose0 is marked out at that same bar's close, which is
  a price the bar has already printed rather than one whose path we would have to guess.
- Everything below about **targets** governs quickfix alone. A bar exit
  names a price, so there is no target gap test, no target in-range test and no ambiguity for
  it. Everything below about the **stop** governs every bar exit held past its entry bar too,
  since their stop is live on every bar they are carried through. What all of them inherit is
  the same honesty problem in a different place — quickfixclose0 assumes one daily bar can give
  us both a fill at the reversal intraday and a fill at that day's close, quickfixopen1 and
  quickfixopen2 assume an open is fillable, and quickfixclose1 assumes a stop inside bar 1's
  range was hit before that bar's close. That last assumption is made **once per bar held**,
  which is what made the retired long holds lean on it hardest.
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
- The **bar exits** are charged the **limit rate** (1 tick), not the stop rate: a
  market-on-close and a market-on-open are orders whose **time is known in advance**, so they
  can be worked, rather than a stop fired into a move nobody chose the timing of. **That is an
  order-type argument, not a liquidity one** (corrected 2026-08-06, Lode): the day's volume
  peaks are the **open** and the **session close**, and the "close" these strategies exit on is
  the **settlement**, which is neither. So the open exits do land on a real volume peak, while
  on the settlement side the 1 tick rests on the order type alone and is, if anything,
  optimistic. The rate is unchanged; only the reason for it was wrong. Same
  reasoning already applied to `data_end`. It matters more here than anywhere else — at two
  ticks round trip it is the difference between a winner and a loser on quickfixclose0's
  smallest trades, and those trades are the *only* way it loses at all. A bar-exit trade that
  is **stopped out** is charged the stop rate like any other stop; only the scheduled exit
  gets the limit rate.

**Why two strategies can split on the same bar** (audited 2026-07-27, after the question came
up from reading the charter overlays side by side). `check_exit` is shared, so every strategy
resolves an engulfing day the same way — but the gap test is against *each strategy's own
target*, and those sit at different prices. The audit is kept as written, against the data of
the day: quickfixwick was retired on 2026-08-12 and quickfix is the only target strategy left,
so nothing here can split against anything today, but the *mechanism* is unchanged and is what
the section is for. Across the archive as it stood:

| | days where BOTH stop and target were in the exit bar's range | booked `unknown_pl` (−1R) | booked a win | booked a stop |
|---|---|---|---|---|
| quickfix 2.5R | 9 | **5** | 3 (all gapped past the target) | 1 (−3.05R, gapped past the stop) |
| quickfixwick | 7 | **6** | 1 (+0.27R, gapped) | 0 |

Both strategies do give the doubt to the stop; the wins are the gap rule firing *first*,
because the bar opened past the target and the limit was already filled before price ran back
through the stop. The one date where the two split is **EURO_Futures, short, exit 2026-05-08**:

```
entry bar 2026-05-07, low 1.17425
  quickfix 2.5R target   1.17440   <- computed: entry - 2.5 x risk
  quickfixwick target    1.17424   <- entry bar low - 1 tick
  exit bar 2026-05-08    O 1.17435  H 1.18085  L 1.17405  C 1.17985
```

The open landed **between the two targets** — 5 ticks past quickfix's, 11 ticks short of
quickfixwick's — so quickfix gapped into profit at the open (+2.53R) while quickfixwick did not
gap, traded through both levels, and booked −1R. One rule, two target prices 1.6 ticks apart.

Structural point worth keeping: quickfix's target is a **computed** price
(`entry − cap × risk`, landing wherever the arithmetic puts it) while quickfixwick's is a
**real chart price** (entry bar low − 1 tick), so a computed target lands near the open by
chance more often and wins these coin-flips somewhat more.

**Open question, deliberately not changed.** The gap test is `open <= target` (short), so an
open sitting *exactly on* the target counts as a gap. It hit once in the audit above —
`USD_EUR_Cross_Rate` 2026-03-09, quickfixwick, open 0.8602 against a 0.8602 target, booked
+0.27R. Defensible (a resting limit fills when the market trades there) but it is not a gap.
Requiring a **strict gap of at least one tick** would send such a trade through to
`unknown_pl` instead; it is a one-line change in `check_exit` and would need the risks
re-solved. It applies to quickfix, the only target strategy left.
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
| `engine.py` | The engine, shared by every strategy: `load_bars`, `infer_tick`, `market_dirs`, signal detection, the stop, exit resolution, `backtest(bars, tick, dp, rule4)` (it takes the whole `Rule4`, since that may carry a target policy **or** a bar exit) and `run_markets` (all markets, **every cap in the grid** plus every registered non-cap Rule 4, one pass). Run directly for a single-market (gold) JSON ledger. |
| `strategies.py` | The **registry** and Rule 4 itself: `target_policy(cap)` (the cap family), `close_exit(k)` / `open_exit(k)` (the bar-exit family), `CAP_CHOICES` (the grid the reports dial across), and the text every output labels itself with. A `Rule4` bundles one setting — its policy **or** its bar exit (plus `bar_exit_at`), the token its backtest is filed under, `in_grid`, and its prose; a `Strategy` is a key, a title, a **default `Rule4`**, its own `risk_pct` and whether that risk was solved. `QUICKFIX`, `CLOSE_0`, `OPEN_1`, `CLOSE_1`, `OPEN_2`, `REGISTRY`. |
| `run_all.py` | Runs every market independently (each a fresh $100k) → `<strategy>_all_markets_daily.xlsx` (per-market summary + all trades). |
| `run_portfolio.py` | Merges every market's trades into ONE shared account, applies the money-management + slippage model → the portfolio xlsx + `_equity_<strategy>.json`. Also writes `_variants.json`: the same shared account replayed at **every cap in the grid, plus every registered Rule 4 that is not a cap**, packed for the pages. |
| `build_equity_html.py` | Renders `_equity_<strategy>.json` + the shared `_variants.json` into `output/equity_<strategy>.html`, plus `report.html`. Refuses to build if the variant grid disagrees with a strategy's workbook. (It also wrote `comparison.html` and `conclusions.html` until both were retired on 2026-08-12.) |
| `export_charter_trades.py` | Hand-off to charter: `output/charter_trades_<key>.json` — one file per **cap** in `CHARTER_CAPS` (1.9R, 2R, 2.25R, 2.5R, 5R; quickfix's own default MUST be in there) plus one per **key** in `CHARTER_STRATEGIES`, which is **derived from the registry**: every strategy that is not on the cap axis, 4 of them. Prunes hand-off files it no longer owns. |
| `strategies.py` (grid) | `CAP_GRID` = 0R&ndash;10R, tenth-R steps to `CAP_FINE_TO` (5.5R) and quarter-R above. One axis for the dial and both charts; `CAP_CHOICES` adds the uncapped run and is what gets backtested (75 settings). |
| `solve_risk.py` | Solves each strategy's 6%-drawdown risk. Prints its own solve **and** what the registered number actually produces, but only calls a **solved** risk stale — the four chosen 1% risks are reported and left alone. Not part of the pipeline; it is how quickfix's constant in `strategies.py` is derived. |
| `run_pipeline.py` | Every writer in one pass over the array archive (and it backtests whatever `CHARTER_CAPS` names on top of the dial grid, since the two lists are independent) (the fast way to regenerate everything): per-market xlsx, portfolio, the cap grid, the charter hand-off, then the pages. |

Parsing is imported from `../charter/scripts/charting_core.py` (`parse_array`); do not
rewrite it here.

### The 1-minute side — the published strategy

| File | What it does |
|---|---|
| `engine_1m.py` | The 1-minute engine: rules 1–2 intraday, market-order entry on the first reversal print, ladder-anchored stop, exit at the next settlement. `tests/test_engine_1m.py` covers it. |
| `run_1m.py` | The backtest and the published baseline: `output/quickfix1m1dc_all.json`, then the report and the charter hand-off. Everything else on this side reads what it writes — including the **market-day calendar** and the grid helpers every curve here is drawn on (below). |
| `build_1m_report.py` | `output/quickfix1m1dc_report_variant_02.html` (named for its cell) from the blotter alone (no backtest), and `--variant "<cell>"` for any matrix cell under its own filename. Imports `build_equity_html.CSS` so the look cannot drift. |
| `run_1m_matrix.py` | The dial matrix, one pass over the data: the full lockout x stop x band cross on the filtered universe (`variant 1` .. `variant 27`) plus three appended extras — since 2026-08-16 `variant 28` (4th/5th, band 0.15-0.20) and `variant 29` (hybrid, band 0.25-0.65), the winning band from each stop anchor's R-cut grid, and `variant 30`, the market filter's off-state (lockout 1 / hybrid / 000-050 over all 31 markets, pairing with `variant 4`). Curves **levered to a constant 6% max drawdown** with the risk solved per cell (the table carries both bases). |
| `research_1m_levels.py` | The level/entry study, baseline and `--variant "<cell>"`. |
| `build_1m_rcut_report.py` | The R-cut band grid, **one per stop anchor**: `--stop 4th5th` (default) and `--stop hybrid`, each ~231 engine passes, ~90 min, **not** in a full refresh — each page has its own update button. Its trade cache is per anchor and keyed on the dials **and** on `data_fingerprint()`, so it can never republish cells computed on an older window or under the other stop. |
| `export_charter_trades_1m.py` | The charter hand-off: `output/charter_trades_quickfix1m1dc.json`, in charter's existing schema. The only owner of that directory now, and it prunes. |

#### Every curve is a step function on the market days (2026-08-18)

`portfolio_replay` books P&L at exits, so its curve carries **one point per exit** — and a
chart that joins two of them draws the account climbing smoothly across eleven days on which
nothing was booked. The balance did not do that: it stood still and then jumped. Lode,
2026-08-18: *"not the correct way of visualising it, although it's also not completely
wrong"*. So every page here now plots the same two things, from helpers in `run_1m.py`:

- `lineType: WithSteps` — today's balance held flat until tomorrow, the whole move taken as
  the vertical there. The drawdown pane is the same curve read against its peak, so it steps
  too.
- one point per **market day**, out to the **last** one rather than to that curve's own last
  exit. A quiet fortnight is a flat fortnight, and the page is as up to date as the data.

**A market day is the union**: a date on which *any* market in the run was open. The account
can move on any of them, and the published universe holds 22 calendars — GC trades ~23h a
day, LE ~4.6h, the softs are frozen at Apr 17 — so no single market's calendar is the
account's. On the current window that is **158 market days, 2026-01-02 to 2026-08-14**,
against GC's own 155.

Only the runners can build it, since only they hold the bars, so `run_1m.py` and
`run_1m_matrix.py` write it into their JSON as `calendar` and every page builder reads it
from there — rebuilding it in a page would cost ~100 s of bar loading to draw a line. A JSON
written before it existed falls back to calendar days with a printed warning rather than
breaking the refresh chain. `calendar_union` / `market_day_grid` / `place` / `carry_forward`
are pinned by `tests/test_equity_grid.py`.

What it makes visible: on the matrix every cell now starts and ends on the same x, where a
cell that stopped trading early used to be a **shorter line** and read as a shorter history
(`variant 28`: 18 trades, last exit 2026-07-29, two weeks short of the rest). The report's
daily calendar and its **time in market** are on market days as well, so weekends no longer
dilute that percentage.

### Adding a strategy

If the new strategy is the cap family at a different cap, it is one line:

1. `Strategy(key=..., title=..., rule4=cap_rule4(3.0), risk_pct=1.0)` in `strategies.py`,
   appended to `REGISTRY`. Any `risk_pct` will do to start with.
2. `venv\Scripts\python.exe solve_risk.py` &mdash; it prints the risk that puts the new
   strategy at 6% drawdown and says the registry is stale. Paste that number back.
3. `venv\Scripts\python.exe run_pipeline.py`.

Its Rule 4 text, lede, caveat, footers and navigation buttons are all generated from the
cap, and a cap already in `CAP_CHOICES` costs no extra backtest — it is already in the grid.

If it is another **bar exit** — bar 2's close, say, or bar 3's open — it is two short steps:

1. `CLOSE_2 = Rule4(token="close2", label="bar 2 close", bar_exit=close_exit(2),
   bar_exit_at="close", texts=dict(...))` beside the others, with its own prose.
2. `Strategy(key="quickfixclose2", title="Quickfixclose2", rule4=CLOSE_2, risk_pct=1.0,
   risk_solved=False)` appended to `REGISTRY`, then
   `venv\Scripts\python.exe run_pipeline.py`.

`close_exit(k)` and `open_exit(k)` are already parameterised and `CHARTER_STRATEGIES` is
derived from the registry, so charter picks it up as well. No new exit reason is needed:
`exit_close` and `exit_open` name the **order type**, not the bar, so the whole family shares
them. (Bars 3 to 20 were *generated* from a `close_texts(k)` / `close_strategy(k)` pair until
2026-08-12; with the sweep retired, a new bar writes its own paragraph like the four that
remain.)

If Rule 4 needs a genuinely different *shape*, it is a new `Rule4` beside the written bar
exits:

1. Write the factory. Which kind depends on what the exit watches:
   - a **price level** → beside `target_policy`. It gets `pos` (side,
     entry, stop, risk, and the entry bar's own high/low/tick), the bullish levels and the
     bearish levels known at the bar's start, and returns `(price_or_None, reason)`.
   - a **bar event** → beside `close_exit` / `open_exit`. It gets `pos`, the `bar`, and `k`
     bars since entry, and returns `(price, reason)` or `None`. `k = 0` is the entry bar,
     which only a bar exit may close on.
2. If it invents a new exit reason, add it to `VAR_REASONS` (`run_portfolio.py`),
   `prettyReason` (`build_equity_html.py`) and `TRADE_COLORS` (charter's builder) — or to
   charter's `TRADE_BY_R` instead, if the reason can be a win *or* a loss.
3. Build a `Rule4(token=..., label=..., texts=..., policy=...)` **or**
   `Rule4(..., bar_exit=..., bar_exit_at=...)` — exactly one of the two mechanisms, and a bar
   exit always with its `bar_exit_at`; it raises otherwise. Leave `in_grid` `False`, since it
   is not a point on the cap dial, and give it `rule4` / `rule4_text` / `lede` / `caveat`
   text, written rather than generated for a setting outside the cap family.
4. `Strategy(key=..., title=..., rule4=<that>, risk_pct=..., risk_solved=...)`, appended to
   `REGISTRY`. Run `solve_risk.py` if the risk is meant to be the solved one. It reaches
   charter automatically, since `CHARTER_STRATEGIES` is every non-cap strategy in the
   registry.

Either way, **delete the retired key's old outputs by hand** when you rename or retire one.
The charter hand-off prunes itself; the workbooks, the JSON ledgers and `equity_<key>.html` do
not, so a renamed strategy leaves a full set of files behind under its old name (that is what
happened to both `quickfixopen` and `quickfixclose` on 2026-07-31, and it is the 105 files that
had to be deleted by hand when the wick and the long holds were retired on 2026-08-12).

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

**Each strategy is published at its own risk**, and `Strategy.risk_solved` records where that
number came from:

| | risk per trade | 1R = | where it comes from |
|---|---|---|---|
| quickfix (1.9R) | **1.39%** | 1.39% of liquid capital | **solved**: the risk that puts it at a 6% max drawdown (`engine.TARGET_DD`) |
| quickfixclose0 | 1.0% | 1.0% | **chosen** (user, 2026-07-28) |
| quickfixopen1 | 1.0% | 1.0% | **chosen** |
| quickfixclose1 | 1.0% | 1.0% | **chosen** |
| quickfixopen2 | 1.0% | 1.0% | **chosen** |

Publishing at the *solved* risk is what makes two strategies comparable at equal **pain**
rather than equal bet size, and it is still how quickfix is published. The four bar exits
are deliberately not: their exits are fast enough that the R scale stops meaning much, and
quickfixclose0 barely draws down at all, so a 6%-drawdown solve either does not converge or
hands back a bet nobody would take. To read them at equal drawdown, run `solve_risk.py`: it
prints what 6% would cost each of them without changing what any page publishes. (The
comparison page did that in the browser, across every strategy at once, until it was retired
on 2026-08-12.)

`solve_risk.py` still prints the solve for every strategy — "what would 6% cost this one" is
worth knowing even when it is not the setting — but it only calls a **solved** risk stale.
Do not paste its numbers into the registry for the other four.

For quickfix, that number is a **measured constant**, not a choice: `solve_risk.py` bisects
for it (max drawdown rises monotonically with risk) and prints both its own solve and what
the *registered* number actually produces.

It calls the registry **stale only when a solved risk misses the target**, not when it
differs from the solve in the third decimal. The registry deliberately carries round numbers
(1.39 against a solved 1.391) and an exact-match test would have left the tool complaining
forever about a difference that moves the drawdown by nothing. The tolerance is 0.05, the same
one the report's own chart uses on its bisection. Re-run it after any change to the rules, the fill model or the
archive — they all moved when gap fills went in on 2026-07-27. They live in `strategies.py`
rather than being solved on every run so that the workbooks, the ledgers and the pages all
quote one published figure and the reports do not shift under the reader.

Opening every page at one bet size was the old behaviour, and it was wrong in a specific way:
it showed several different depths of hole and invited ranking them on return alone, which
flatters whichever strategy was allowed to dig deepest, and it meant a strategy's page could
quote another strategy's number (user, 2026-07-27).

`engine.RISK_PCT` is a different thing — the **reference** risk the shared cap grid in
`_variants.json` is priced at, and the only risk at which a page's replay is pinned to a
server figure. It tracks quickfix's number because quickfix is the reference strategy;
nothing depends on them being equal.

### Where it stands (2026-08-12 data, 41 markets tested, 28 with trades)

**A DATED SNAPSHOT, NOT A SPECIFICATION.** Every figure in this section moves with each new
array day, so it is stale by definition the morning after it is written, and **it is not
meant to be updated per bar** — doing that would be a daily chore with no reader on the other
end. `output/report.html` is regenerated on every run and is
the live answer; this table is here so the README means something to somebody who has not
opened them. Refresh it when a number is quoted in a decision, or when the rules or the fill
model change. What must stay current is the *structure* — the rules, the defaults, the
invariants below — none of which a new bar touches.

Each at its own **published default** risk, which is why the drawdown row is not constant:

| | quickfix (1.9R) | quickfixclose0 | quickfixopen1 | quickfixclose1 | quickfixopen2 |
|---|---|---|---|---|---|
| Risk per trade | 1.39% | 1.0% | 1.0% | 1.0% | 1.0% |
| Net return | +245.78% | **+463.48%** | +358.51% | +462.71% | +334.44% |
| Gross return | +265.05% | +482.55% | +371.38% | +484.53% | +349.17% |
| Max drawdown | 6.00% | 0.06% | 4.21% | 4.62% | 11.71% |
| **Return / drawdown** | 41.0x | (undefined) | 85.2x | **100.2x** | 28.6x |
| Closed trades | 96 | 117 | 100 | 100 | 96 |
| Win rate | 64.6% | 96.6% | 88.0% | 66.0% | 63.5% |
| Average winner | +2.14R | +1.57R | +1.89R | +3.32R | +3.42R |
| Average hold | 1.2 bars | 0.0 bars | 1.0 bars | 1.0 bars | 1.7 bars |
| Max concurrent | 5 | 0 | 4 | 4 | 6 |
| Time in market | 49% | 0% | 42% | 42% | 55% |
| Longest losing run | 4 | 1 | 2 | 4 | 6 |
| Longest winning run | 9 | 58 | 26 | 14 | 11 |

quickfix's drawdown is 6.00% by construction: 1.39% is the risk solved to put 1.9R exactly
there, off the cap chart at the bottom of its page. The other four are at a flat 1%, so
their drawdowns are whatever they are — which is exactly why this table cannot rank them.

**Levered to a constant 6% drawdown**, which can. Straight off `solve_risk.py`, same run:

| | risk allowed | final capital | return / drawdown |
|---|---|---|---|
| **quickfixclose1** | **1.300%** | **$910,201** | 135.1x |
| quickfixopen1 | 1.428% | $849,666 | 125.0x |
| quickfix (1.9R) | 1.391% | $346,075 | 41.0x |
| quickfixopen2 | 0.512% | $219,559 | 19.9x |
| quickfixclose0 † | 1.000% (its own) | $563,483, at a 0.06% drawdown | (undefined) |

† **exempt**: it never reaches 6% at any bet size, so it keeps its published 1% and is not in
this ranking. Its capital is not comparable to the rows above it.

The two **one-bar** holds are far ahead, and the mechanism is visible in the table above:
they hold 4.2–4.6% of drawdown at a 1% bet where the two-bar hold holds 11.7%, so they are the
ones that can be levered hardest. Note that they get there differently — quickfixopen1 wins 88%
of the time for small amounts, quickfixclose1 wins 66% of the time for +3.32R a winner — and
end up within 8% of each other, which is nothing on this sample.

**Holding past one bar costs more than it pays here.** quickfixopen2 books bigger winners than
either one-bar hold (+3.42R) and still finishes far behind them: its drawdown roughly triples,
its losing run gets longer (6), and it ties up a market for a third day, which costs it 4
trades outright (96 against 100). The bar 3 to bar 20 sweep, run 2026-08-01 and retired
2026-08-12, did not reverse that anywhere: every one of those holds landed in a $115k–$190k
band levered, against $846k at bar 1 on that day's data, with no second peak. That is the
measured curve the sweep was built to produce, and it is why the axis is not maintained any
more.

**Read the fill assumptions before reading any of this as a result.** quickfixclose0's 96.6%
and near-zero drawdown are the entry rule and the daily-proxy model showing through, not an
edge to trade; quickfixopen1 has no stop that can trade, so its tail is an overnight gap; and
quickfixclose1 rests on a stop inside a daily bar's range having been hit before that bar's
close. All of it is stated in full in the daily-proxy section above.

Within quickfix's own family, the uncapped end is far behind: $158,195 at 0.396% risk, 9.7x.
It wins barely a quarter of the time (28%) with winners four times the size, and that
combination produces long losing runs (13 straight against 4), which is a deep hole; held to
the same 6% it must be sized right down, and that gives away far more than the big winners
bring back. That is visible on the cap chart rather than as a strategy of its own.

**Return / drawdown is the ranking metric**, not total return. Risk per trade is a dial, so a
shallower edge can be levered up to meet a given drawdown, while the reverse conversion does
not exist — a bigger total return bought with a deeper hole is not automatically the better
strategy.

**Do not read this as a verdict.** It is ~8 months and 96–117 trades, and max drawdown — the
thing both of these risks are solved against — is the most sample-dependent statistic in the
project. This table was rewritten twice in one day by changes to the **fill model alone**,
with the strategies untouched. Read the fill assumptions as the biggest open risk here.

Caveat on every drawdown figure here: max drawdown is a single worst-path observation and the
most sample-dependent statistic in the project. The structural reasons above will hold; the
specific 6.00% will not — expect it to deepen as the sample grows, which is a reason to treat
every risk in the table above as a ceiling rather than a target.

#### What the cap sweep shows (2026-08-01 data, at the reference risk)

All at the reference risk, 1.39%. Dated like the table above and just as stale by
construction; the live version is the cap chart at the bottom of quickfix's page:

| cap | 2R | 2.5R | 3.5R | 4.5R | 5R | 6R | 7R | 8.5R | 10R | none |
|---|---|---|---|---|---|---|---|---|---|---|
| return | +215% | +273% | +263% | +333% | +337% | +348% | +475% | +486% | +294% | +266% |
| max DD | 6.00% | 7.09% | 6.92% | 7.99% | 7.97% | 12.61% | 11.88% | 11.86% | 19.48% | 19.48% |
| ret/DD | 35.9x | 38.5x | 38.0x | 41.7x | 42.3x | 27.6x | 40.0x | 41.0x | 15.1x | 13.7x |
| trades | 90 | 86 | 82 | 80 | 80 | 80 | 80 | 78 | 76 | 76 |
| win rate | 62% | 59% | 49% | 45% | 42% | 39% | 39% | 36% | 32% | 28% |

**Do not rank the caps off this table.** It compares them at one bet size, and at one bet
size a wider cap is being handed a deeper drawdown for free — part of its bigger return is
just the bigger hole it was allowed to dig. Worse, the ranking *moves with the risk*: return
compounds exponentially with risk while drawdown is bounded near 100%, so an earlier reading
of this same sweep put 5R on top at 1% and 7R/8.5R on top at 1.573%. Nothing about the
strategies changed between those readings — only the dial did.

The comparison that survives is the **levered one**: solve for the risk that holds every cap
to the same drawdown, and the caps are being asked the same question. That chart lives at the
bottom of every cap-family report page and it puts **1.9R first**, which is why it is
quickfix's default.
See [Choosing the profit cap](#choosing-the-profit-cap--the-section-at-the-bottom-of-the-page).

What this table *is* good for is the shape: **drawdown moves in plateaus** (~6% → 8% → 12% →
19.5%), because on ~80 trades the worst path is dominated by a handful of trades and
only jumps when the cap crosses one of their exits. Win rate falls monotonically as the cap
widens, from 62% at 2R to 28% uncapped. Both of those are structural and will hold; the
specific peaks will not.

---

## Outputs (`output/`)

Per strategy, `<strategy>` being one of `quickfix`, `quickfixclose0`, `quickfixopen1`,
`quickfixclose1` or `quickfixopen2`. That is 5 of each, so a full run writes 5 pages of
~580 KB and 10 workbooks; the pages are large because each carries the whole shared variant
grid.

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

Two more pages were written here until 2026-08-12, both retired by the user with their
builders: **`comparison.html`** (every strategy against the others, at a constant 1% risk and
then levered to a constant 6% drawdown) and **`conclusions.html`** (two free-text fields that
printed at the end of the exported PDF). Both are in git. The **Compare** and **Conclusions**
buttons went with them, so **Export PDF** is the only button left in the nav's button row.

### The daily calendar

Every trading day, in order: date, **total capital**, drawdown, positions open, and the
entries and exits booked that day. **Purple = a position opened, blue = a position closed**
(an em dash where nothing happened). Deliberately not the green/red used everywhere else on
the page: there green and red mean *won* and *lost*, and an entry has no outcome yet, so
colouring it green said something untrue. It scrolls inside its own box on screen and the print stylesheet opens it out, so
it runs to several pages of the PDF.

**It is on both page types and it prints** (user, 2026-07-28). Its `Activity` column carries
61% of the width, because it is the column with something to say; date, capital, drawdown and
open share the rest. It used to be a collapsed
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

### Streaks are counted in ENTRY order

**Longest winning / losing run counts positions in the order they were TAKEN**, not the
order they closed (user, 2026-07-29). It ran in exit order until then, on the reasoning that
the balance moves as trades close — which was wrong for the reader, because the blotter is
sorted by **entry**, so anybody counting losing rows down the page counts entry order and the
report was quoting a different sequence.

It surfaced on quickfixwick (retired 2026-08-12). Three losing positions were opened on
**2026-01-29**, and one of them (`S_P_500_Index`) did not close until **2026-02-03**, after an
unrelated winner had closed on 02-02. In exit order that winner splits the run, giving 4; in
entry order the run is the 5 consecutive losers the blotter plainly shows.

The question this figure answers is "how many positions in a row lost", which is about the
order they were taken. The **drawdown** — which is about the order they closed — is a
separate figure and is still measured in exit order by `account()`.

It also keys off **net R** rather than dollars, like the win rate, so it does not move with
the risk dial: whether a position won is not a function of how big it was. That also keeps it
meaningful at risk = 0, where every dollar P&L is 0 and the old test scored every trade as
neither a win nor a loss.

### "optimized" in the page title

**Only quickfix's page says "equity curve optimized".** Its cap *and* its risk are both
solved — 1.9R tops the levered cap chart, 1.39% is the risk that puts it there — so the word
is a claim the page can back. The other four are a fixed Rule 4 shape at a chosen 1%:
nothing about them has been optimized, and the title said so anyway until 2026-07-29.
`page_title()` keys off `risk_solved and in_grid`, which is exactly the pair of properties
that makes the claim true, rather than off the strategy key.

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

### Table widths in the PDF

`table.trades` is `table-layout: fixed`, so **column widths come from the header row and
nowhere else**. `COLS` and `MCOLS` have carried a `w` percentage from the start and it was
never emitted into the markup, so every column silently got an equal share: in the printed
blotter the market names wrapped onto two lines while `Side` and `Bars` sat half empty (found
by reading an exported PDF, 2026-07-28). The widths are now written onto each `<th>`, and the
daily table carries its own in `DAILY_HTML`. They sum to 100 — keep it that way.

Widths alone were not enough. The blotter is **twelve columns** and does not fit 188 mm of A4
portrait at screen type size: measured at the real print width a quarter of the market names
still wrapped and the date, R and P&L columns overflowed their cells. The print stylesheet
therefore drops `table.trades` to 9px with 3–4px cell padding. That fits everything with only
the single longest market name (`Chicago_SRW_Wheat_Futures_CBOT`, 30 characters) taking two
lines, on 6 of 90 rows. Shrinking the type is the right lever here; starving one column to
feed another only moves the problem.

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
did exactly that, and that page is gone but the trap is not. The parameter is now only applied
when actually supplied, and everything
that needs the live value reads `CURRENT_RISK` (the applied number) rather than the input's
raw `.value`, which reads `""` mid-edit and would hit the same trap.

### The print report

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
strategy shared one risk; now each opens at its own published default and one box cannot show
two different numbers. The old reasoning for sharing was that a multi-strategy PDF should be
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
  multiples, average hold, time in market, max concurrent, and the **win/loss streaks**.
  Only the money moves: final
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
  silently never fire on four of the five strategies.
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
  always written at the strategy's **default** cap (quickfix 1.9R), and the
  page says so under the dial. The dial is display-side exploration, exactly like risk.
  (The charter hand-off is a separate chosen set of caps and need not contain the default —
  the dial's note is careful not to claim otherwise.)
- **The page self-checks at every cap.** At the default risk its replay must reproduce
  `run_portfolio.py`'s own final capital for the cap in force; it logs a console warning if
  it ever does not. `build_equity_html.py` additionally refuses to build if the grid's figure
  for a strategy's default cap disagrees with that strategy's workbook.

#### Choosing the profit cap — the section at the bottom of the page

The dial answers "what happens at 1.7R". This section answers "what happens at all of them",
which is the question one setting cannot. It sits **directly above the trade blotter**
(2026-07-28): it is the finding the report exists to make, so it is read before the raw trade
list rather than after everything else.

Pane heights matter and are set deliberately. Every pane auto-scales its y range to its own
data, so the pixel height **is** how much of the variation a reader can see: a 50px pane
flattens a curve that a 90px one resolves. The main capital pane is 250px and the readout
panes 90px, raised from 150/50 on 2026-07-28 for exactly that reason. The constant-risk pane
is deliberately shorter (52px): it is a flat line by construction and has nothing to resolve,
it is there to show that it does not move. **Two charts over
the same 0R–10R grid**, stacked, read top to bottom:

1. **At a constant 1% risk per trade** — the real result. Five panes: final capital, **max
   drawdown**, the risk (a flat line, on the chart precisely to show that it never moves),
   return/drawdown, win rate. This is what each cap actually did on the same bet.
2. **Levered to a constant 6% drawdown** — the ranking. Three panes: final capital, **the
   risk each cap is allowed**, win rate. The risk is solved per cap by bisection (max
   drawdown rises monotonically with risk) so every cap bottoms out in the same hole.

**Why both, in that order.** The first is honest about what happened but cannot rank
anything: with the bet fixed, the drawdown fans out from 6.0% to 36.7% across the grid, so a
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
is **1.9R ($322,267, 1.391% risk, 37.0x)** — which is quickfix's default, so the strategy now
sits on the point its own chart picks — then **3.7R ($316,945, 1.211%)**, **2R ($315,290,
1.391%)**, **3.5R ($308,848, 1.205%)** and **2.5R ($307,283, 1.175%)**. Five settings inside 5%
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
stretch of caps shares the same allowed risk and where that falls off a cliff. The best
setting is labelled **Optimal point** and highlighted in yellow. The levered
chart's reading was cut from five passages to three on 2026-07-28.

The first of those three, *Where it pays*, is generated end to end, and it is where the
**Optimal point is highlighted in yellow** — that is the finding the whole report exists to
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
megabytes of repeated key names to every page; packed, `_variants.json` is ~480 KB and the
pages ~580 KB.

- **`_variants.json`** — the variant grid, shared by every page (intermediate). `caps` is the
  single cap axis — the dial's and both charts'; `extra` lists the settings that are *not*
  caps (`close0`, `open1`, `close1`, `open2`), packed and replayed identically but not points
  on that axis. It is **derived from the registry**, never typed, so retiring a strategy takes
  its token out with it.
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
                    |"unknown_pl"|"data_end"|"open_at_end"|"exit_close"|"exit_open",
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
- `CHARTER_STRATEGIES` — **every non-cap strategy**, 4 of them today, exported by key because
  there is no cap number to name the file after. **Derived from the registry**
  (`[s.key for s in REGISTRY if not s.r4.in_grid]`) rather than typed: deriving it means a new
  bar exit reaches charter with no second edit, and a retired one cannot linger — which is
  what carried the list from six names to twenty-four on 2026-08-01 and back to four on
  2026-08-12, both times with no edit here. The caps above stay a *chosen*
  handful, because there the registry is the wrong source — the cap grid has 75 points and
  charter wants five. Unlike the caps, these are worth drawing *together*: their exits land on
  genuinely different **bars**, not just different prices on one bar, so on the price pane they
  fan out across the days after the entry instead of off a single point. Read against a cap
  overlay they show the whole spread of what "take the profit" can mean on one setup.

`export_charter_trades.py` also **prunes** any `charter_trades_*.json` it no longer owns,
because charter globs the directory and a file left over from an earlier set would go on
being drawn.

**Why not the whole grid.** Bytes are not the obstacle (no extra backtest either — the
pipeline already computes every setting). Legibility is. Rules 1–3 do not involve the cap, so **every cap takes the same setups**: all their entry
triangles land on the same bar at the same price, and 34 overlays would stack 34 markers on
one point and fan 34 exit lines from it. Charter also has one line style for these overlays
and colour already means the outcome, so they cannot be told apart on the chart at all — they
are read one tick at a time.

**A few caps, and every non-cap strategy.** Caps went from one-file-per-strategy to
one-file-per-cap on 2026-07-27, once a cap-family strategy turned out to be just a dial
position: the useful comparison on a price chart is then a handful of caps, not all 75, and
the uncapped setting is not exported at all since its trades are the least interesting on the
chart. The **non-cap** strategies are a different case and are all exported: their exits land
on genuinely different bars and prices instead of fanning off one point, which is exactly what
makes them worth seeing together.

**Nine overlay boxes** today — eleven before 2026-08-01, twenty-nine between then and
2026-08-12, when the wick and every hold past bar 2's open were retired. At twenty-nine that
was a lot of checkboxes and worth being honest about; it was still not the same problem as
exporting the cap grid, and the difference is the whole argument for the rule this section
states. Seventy-five caps would stack seventy-five identical entry markers on one point and
fan their exits off it; a bar exit fans out **across the days after the entry**, one per bar,
so each box shows something the others cannot. Show a few at a time.

The set is **independent of the reports' cap grid** and need not sit on it: 2.25R is exported
and is on no grid the reports draw, since the grid moved to tenth-R steps. `run_pipeline.py`
backtests whatever `CHARTER_CAPS` names, on top of the grid, so the two can diverge freely. This is
only about what charter draws; the workbooks, JSON ledgers and HTML reports are unchanged.

`reason` was **`target_5r`** until the cap became a dial; it is now **`target_r`** — the exit
means "the R cap was hit", and 5 is only one setting of it. **`target_bar`** was quickfixwick's
target, one tick past the entry bar's own wick, and nothing books it since that strategy was
retired. charter colours all three green, the same as
any other target, so files exported before either change still draw correctly and so colour
never starts meaning "which strategy" instead of "what happened".

The two **bar-exit reasons** are the one case that cannot name its own colour. **`exit_close`**
and **`exit_open`** are *moments*, not levels, so the same reason covers a win and a loss and
painting either green would draw a losing trade as a target reached. charter lists them in
`TRADE_BY_R` and `trade_color()` reads their colour off the trade's own `r` instead — which
is what "colour is the outcome" actually asks for.

They name the **order type**, not the bar (a market-on-close, a market-on-open), so every
bar-exit strategy shares them and adding a fifth would need no change in
charter at all. That is what made the bar 3 to bar 20 sweep cost charter nothing to add and
nothing to remove. Every hold past the entry bar also produces ordinary **`stop`** exits,
drawn red like any other stop, because their stop is live on every bar the trade is carried
through; only quickfixclose0 and quickfixopen1 never show one.

Trade geometry only — the entry plots at the first-reversal price on the entry bar, the exit
at the fill level on the exit bar. `unknown_pl` exits at the stop; `data_end` exits at the
last bar's close (drawn grey — it is not a rule exit); `open_at_end` has null exit. A
**quickfixclose0** trade exits on its *own* entry bar, so its line is vertical and both its
markers sit on one bar — correct, and the only overlay that does it. charter reads this at
build time and overlays the trades on each market's **daily** price pane behind a toggle.

Note that `r` here is the **gross** R multiple: slippage is a portfolio-level cost applied in
`run_portfolio.py`, so a trade that was green on the chart can still be a small net loser in
the ledger. That has always been true of every overlay and is not specific to the bar exits.

To refresh **everything** — new data included — there is one command,
`python ../trading_system/refresh.py`, or the **Update** button at the top of charter's
icon rail, which runs it and streams the output into the page. That is the umbrella's
convenience runner: it calls each project's own entry point (`hyperliquid_bot`'s
`sync_arrays.py` — the array sync alone, since nothing here reads the rest of that
pipeline — then this project's `run_pipeline.py`, then charter's builder) in data-flow
order and stops at the first failure. It changes nothing here; the steps below are what it runs.

To refresh the overlay alone, end to end:

1. Here: `venv\Scripts\python.exe export_charter_trades.py` (regenerate after a rule change).
2. In `../charter`: `venv\Scripts\python.exe scripts\chart_all_markets_reference.py`
   (append a market substring, e.g. `... gold`, for a fast single-market rebuild).
3. In `../charter`: `venv\Scripts\python.exe serve.py`, open the site, and click the **T**
   button (green/red triangles) on the right rail. It opens the **Strategy trades box** —
   one checkbox per exported overlay, 9 of them today (1.9R, 2R, 2.25R, 2.5R, 5R, then the
   4 non-cap strategies in filename order), each labelled with
   its own Rule 4 and its trade count — so you can show any combination or none. Long entry =
   up-triangle, short = down-triangle, exit = a marker on the exit bar; the entry→exit line
   is green for a win, red for a stop, amber for an ambiguous (`unknown_pl`) outcome, blue
   for a still-open trade. Daily timeframe only; markets with no trades show nothing.

**Colour is the outcome**, and every overlay is drawn **identically** — one dotted line, one
round exit marker for all of them. There is nothing to tell them apart on the chart, on
purpose: **all** of them share Rules 1–3, caps and non-caps alike, so their entry triangles
sit on exactly the same bar and price and a different dash per overlay would only decorate
lines that start from the same point. **Read them one tick at a time**; the exits and the
lines are what differ, and with the bar exits on the chart that is the whole point:
they are the overlays whose exit *bars* fan out across the days after the entry rather
than sitting on one. (That fan ran to twenty bars between 2026-08-01 and 2026-08-12; today it
reaches bar 2's open.) (The old
four-style set — dot/dash/long-dash/dash-dot — is in git if a genuine
need to tell overlays apart at a glance ever returns.)

---

## Running

**The published strategy** — this is what the Update button runs, in this order:

```
venv\Scripts\python.exe run_1m.py                            # backtest -> blotter, report, charter hand-off
venv\Scripts\python.exe run_1m_matrix.py                     # dial matrix, curves levered to 6% DD
venv\Scripts\python.exe build_1m_report.py --variant "variant 5"   # any matrix cell, by number
venv\Scripts\python.exe research_1m_levels.py                # level study, baseline
venv\Scripts\python.exe research_1m_levels.py --variant "no lockout"

venv\Scripts\python.exe export_charter_trades_1m.py          # hand-off alone, no backtest
venv\Scripts\python.exe build_1m_report.py                   # report alone, no backtest
venv\Scripts\python.exe -m pytest tests -q                   # the 1m engine's tests
```

or all of it plus the data and the charts with
`python ../trading_system/refresh.py`, which is what charter's **Update** button runs
(~12 min). `run_1m.py` must go first: everything else reads what it writes.

**Not in a full run**, ~90 minutes each, and each has its own button on its own page:

```
venv\Scripts\python.exe build_1m_rcut_report.py              # R-cut grid, 4th/5th stop
venv\Scripts\python.exe build_1m_rcut_report.py --stop hybrid   # R-cut grid, hybrid stop
venv\Scripts\python.exe build_1m_rcut_report.py --no-reuse   # ignore the cache outright
```

**The daily product** — nothing to run today, since the registry is empty; each of these
refuses or does nothing until a `Strategy` is registered again:

```
venv\Scripts\python.exe run_pipeline.py             # everything, every strategy (one pass)

venv\Scripts\python.exe engine.py                   # gold single-market ledger + summary
venv\Scripts\python.exe run_all.py                  # per-market xlsx
venv\Scripts\python.exe run_portfolio.py            # shared-account xlsx + _equity_<s>.json
venv\Scripts\python.exe build_equity_html.py        # -> output/equity_<s>.html
venv\Scripts\python.exe export_charter_trades.py    # -> output/charter_trades_<key>.json

venv\Scripts\python.exe solve_risk.py               # each strategy's 6%-drawdown risk
```

Every daily script takes optional strategy keys; with none it runs all of them. Reading the
array archive is the slow part, so `run_pipeline.py` is the way to refresh that side: it
parses the archive once and feeds every writer. `build_equity_html.py` needs `_variants.json`,
so `run_portfolio.py` has to run first. **What a full daily run cost**, measured 2026-08-12 at
five strategies: ~25 seconds and ~6 MB of output; at twenty-five, ~30 seconds and ~18 MB. The
archive parse dominates the clock, so what a registry really costs is bytes on disk and in
git, because every strategy page ships the whole shared variant grid.

Requirements: `pandas`, `openpyxl`, `pyarrow`, `pytest` (see `requirements.txt`).

## Working agreements

- Commit straight to main. English only in code/comments/strings. No emoji.
- Simulation inputs (starting capital, risk per trade, slippage) live here; data and charts do not.
- When the user supplies text verbatim, use it verbatim.
