# strategy_tester — strategies, backtest, risk management

Strategy department of the trading system (see `../trading_system/README.md` for the
umbrella contracts). Turns the Socrates "time and price meet" method into explicit,
testable rules, backtests them on the array files, applies risk management, and hands the
resulting trades to `charter` for display.

**Scope (firm): strategy_tester produces trade results. It never scrapes data and never
renders charts.** It reads the array (meta) xlsx files from `hyperliquid_bot` (via
`charter`'s parser) and writes trades + equity as JSON / xlsx / standalone HTML reports.

Two strategies are built today — **quickfix** (strategy 1) and **slowfix** (strategy 2).
They share every rule except Rule 4, so they take **exactly the same trades** and differ
only in where those trades are closed.

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
   so that risk is exactly 1% of equity, so **1R = 1%**.
5. **Reward filter (Rule 3).** The nearest bearish reversal below entry must be at least
   **3.5R** below entry, else refuse (not enough room).
6. **Target (Rule 4).** **This is the only rule that differs per strategy** — see the table
   below. Whatever the rule, the target is recomputed on **every** bar from the levels known
   at that bar's start, so a newly appearing nearer reversal moves the target in and an
   elected one falls away. Only **opposite-side** reversals ever close a trade early
   (bearish for a short, bullish for a long), never a same-side one.

### Long setup (mirror)

Bearish ladder for entry, bullish for targets. Tested bearish reversals in
`[low, prev_close)`, ≥3; **first = highest** tested bearish level, second the next highest.
Rule 2: refuse if `open <= second`. Trigger: **close above the first**. Stop = one tick
below the entry bar's low. Rule 3: nearest bullish reversal above entry ≥ 3.5R up.

### Rule 4 — what separates the strategies

| Strategy | Rule 4 | Character |
|---|---|---|
| **quickfix** | Target = **5R**, or an opposite reversal that sits **closer** than 5R (then that reversal is the target). | Takes profit fast. 5R is a hard ceiling on every winner. |
| **slowfix** | Target = **the first opposite reversal beyond entry**, however far away. **No 5R cap.** | Rides the move. Rule 3 keeps that level ≥ 3.5R away at entry, so a winner is at least 3.5R unless a nearer reversal appears later; a level 8R away is ridden to 8R. |

slowfix corner case: if **no** opposite reversal exists beyond entry (they were all
elected), no target is in force and the trade simply **waits, holding**, until one appears.
The stop stays in place throughout, so a position can never be stranded forever.

### Daily-proxy assumptions

We only have daily bars, not intraday ticks (that arrives later with IBKR data). So:

- **Entry is confirmed on the close**, filled at the first-reversal price.
- **The target can never be hit on the entry bar.** Management (stop and target) starts the
  **day after** entry. The entry bar's high/low are already spent by the time its close
  confirms the trade, and by construction the stop sits one tick beyond that bar's own
  extreme, so it cannot trigger there either.
- On each later bar: **only the target in range → win; only the stop in range → loss; BOTH
  in range on one bar → `unknown_pl`**, booked as a **loss (−1R)** — without intraday data
  we cannot know which was hit first, so the doubt goes to the stop.
- A gap through the stop still fills at the stop price.
- A position still open when the market's data ends is reported as `open_at_end`
  (unrealized, no P&L).

**One position per market at a time.** A new signal while in a trade in that market is
ignored — which is why slowfix, holding longer, ends up with slightly **fewer** closed
trades than quickfix despite identical entry rules. Across markets, positions run
concurrently (see the portfolio model below).

### Data window

Per market, trading starts the day after the market's reversals are **first reported**
(older array files carry no reversal block at all, so they produce no signals). Windows
therefore differ per market (gold from 2025-12-15, several obsolete markets end 2026-04-17,
etc.). Gold futures on the COMEX is the reference market.

---

## Files

| File | What it does |
|---|---|
| `engine.py` | The engine, shared by every strategy: `load_bars`, `infer_tick`, `market_dirs`, signal detection, the stop, exit resolution, `backtest(bars, tick, dp, strategy)` and `run_markets` (all markets, all strategies, one pass). Run directly for a single-market (gold) JSON ledger. |
| `strategies.py` | The **registry**. Each strategy is its Rule 4 target policy plus the text its outputs label themselves with. `QUICKFIX`, `SLOWFIX`, `REGISTRY`. |
| `run_all.py` | Runs every market independently (each a fresh $100k) → `<strategy>_all_markets_daily.xlsx` (per-market summary + all trades). |
| `run_portfolio.py` | Merges every market's trades into ONE shared account, applies the money-management + slippage model → the portfolio xlsx + `_equity_<strategy>.json`. |
| `build_equity_html.py` | Renders `_equity_<strategy>.json` into the standalone interactive report `output/equity_<strategy>.html`, including the strategy-switcher buttons. |
| `export_charter_trades.py` | Hand-off to charter: `output/charter_trades_<strategy>.json` (trade geometry keyed by market). |
| `run_pipeline.py` | All four writers in one pass over the array archive (the fast way to regenerate everything). |

Parsing is imported from `../charter/scripts/charting_core.py` (`parse_array`); do not
rewrite it here.

### Adding a strategy

1. Write its Rule 4 target policy in `strategies.py` —
   `policy(pos, bull, bear) -> (price_or_None, "target_5r" | "reversal")`, called on every
   bar the trade is open.
2. Add a `Strategy(...)` with its key, title, one-line `rule4`, page `lede` and `caveat`.
3. Append it to `REGISTRY`.
4. `venv\Scripts\python.exe run_pipeline.py`.

Every runner, every output filename and the pages' navigation buttons follow from the
registry — there is nothing else to edit.

## Portfolio money management (`run_portfolio.py`)

One shared account, starting $100,000, processed chronologically by date, run separately per
strategy. A market's trades (which trades, their entries/exits, their R) are
capital-independent, so they are reused verbatim and only the money management is re-run on
the shared account.

- **1% risk on liquid capital.** A new trade risks 1% of `cash − risk already tied up in
  open trades`. Each open trade ties up its own 1% until it closes.
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

### Where they stand (2026-07-25 data, 28 markets with trades)

| | quickfix | slowfix |
|---|---|---|
| Net return | +168.67% | +203.54% |
| Gross return | +177.18% | +212.88% |
| Max drawdown | 5.85% | 12.66% |
| Closed trades | 78 | 75 |
| Win rate | 41.0% | 26.7% |
| Average hold | 2.3 bars | 3.9 bars |
| Max concurrent | 5 | 8 |
| Time in market | 74% | 87% |

Same entries, different exits: slowfix wins less often but its winners are far larger, and
it pays for that with a drawdown roughly twice as deep.

---

## Outputs (`output/`)

Per strategy, `<strategy>` being `quickfix`, `slowfix`, …

- **`<strategy>_gold_daily.json`** — single-market ledger: `meta`, `trades` (entry/exit,
  bars, R, pnl%, equity), `equity_curve`.
- **`<strategy>_all_markets_daily.xlsx`** — `summary` (per-market: window, trades, win rate,
  return, obsolete flag) + `trades` (all markets).
- **`<strategy>_portfolio_daily.xlsx`** — `summary` (net/gross return, drawdown, streaks,
  averages, hold time, time in market, slippage), `equity_curve` (daily, with a chart),
  `trades` (gross/cost/net R, prices, P&L, running balance).
- **`equity_<strategy>.html`** — standalone interactive report: equity + drawdown +
  open-positions panels, KPI + per-trade stat tiles, a sortable trade blotter, and a
  per-market breakdown. **Every page opens with the strategy switcher** — one button per
  registered strategy, current one filled, so you click straight from quickfix to slowfix.
  The buttons are generated from the registry, so a new strategy appears on every page as
  soon as the pages are rebuilt.
- **`_equity_<strategy>.json`** — the data behind that page (intermediate).
- **`charter_trades_<strategy>.json`** — the charter hand-off (below).

Ledger note: the per-trade `target` field records **the Rule 4 level in force at entry**
(it can move later). It replaced the old quickfix-only `target_5r` column, which could only
ever describe one strategy.

### Charter hand-off schema (`charter_trades_<strategy>.json`)

```
{
  "meta": { "strategy": "quickfix", "title": "Quickfix", "rule4": "...",
            "timeframe": "daily", "n_markets": N, "n_trades": M, ... },
  "markets": {
    "Gold_Futures_COMEX": {
      "tick": 0.1, "price_decimals": 1,
      "trades": [
        { "side": "short"|"long",
          "entry_date": "YYYY-MM-DD", "entry": <price>,
          "exit_date": "YYYY-MM-DD"|null, "exit": <price>|null,
          "stop": <price>, "target": <price>,
          "reason": "target_5r"|"stop"|"bullish_reversal"|"bearish_reversal"|"unknown_pl"|"open_at_end",
          "r": <gross R multiple>|null, "bars": <int>|null }
      ]
    }, ...
  }
}
```

**One file per strategy, all in the same schema** — charter globs
`charter_trades_*.json` and picks up a new strategy on its next build with no code change.
(This replaced the single `charter_trades.json` when slowfix was added.)

Trade geometry only — the entry plots at the first-reversal price on the entry bar, the exit
at the fill level on the exit bar. `unknown_pl` exits at the stop; `open_at_end` has null
exit. charter reads this at build time and overlays the trades on each market's **daily**
price pane behind a toggle. To refresh the overlay end to end:

1. Here: `venv\Scripts\python.exe export_charter_trades.py` (regenerate after a rule change).
2. In `../charter`: `venv\Scripts\python.exe scripts\chart_all_markets_reference.py`
   (append a market substring, e.g. `... gold`, for a fast single-market rebuild).
3. In `../charter`: `venv\Scripts\python.exe serve.py`, open the site, and click the **T**
   button (green/red triangles) on the right rail. It opens the **Strategy trades box** —
   one checkbox per strategy — so you can show quickfix, slowfix, both, or neither. Long
   entry = up-triangle, short = down-triangle, exit = a marker on the exit bar; the
   entry→exit line is green for a win, red for a stop, amber for an ambiguous (`unknown_pl`)
   outcome, blue for a still-open trade. Daily timeframe only; markets with no trades show
   nothing.

**Colour is the outcome, in every strategy**, so charter separates strategies by **line dash
and exit marker** (in file order: quickfix dotted/round, slowfix dashed/square). The box row
carries that hint — it is the only legend. Because both strategies share entry rules, their
entry triangles sit on exactly the same bar and price when both are shown; the exits and the
lines are what differ.

---

## Running

```
venv\Scripts\python.exe run_pipeline.py             # everything, every strategy (one pass)
venv\Scripts\python.exe run_pipeline.py slowfix     # everything, one strategy

venv\Scripts\python.exe engine.py                   # gold single-market ledger + summary
venv\Scripts\python.exe run_all.py                  # per-market xlsx
venv\Scripts\python.exe run_portfolio.py            # shared-account xlsx + _equity_<s>.json
venv\Scripts\python.exe build_equity_html.py        # -> output/equity_<s>.html
venv\Scripts\python.exe export_charter_trades.py    # -> output/charter_trades_<s>.json
```

Every script takes optional strategy keys; with none it runs all of them. Reading the array
archive is the slow part, so prefer `run_pipeline.py` for a full refresh — it parses the
archive once and feeds all four writers.

Requirements: `pandas`, `openpyxl` (see `requirements.txt`).

## Working agreements

- Commit straight to main. English only in code/comments/strings. No emoji.
- Simulation inputs (starting capital, 1% risk, slippage) live here; data and charts do not.
- When the user supplies text verbatim, use it verbatim.
