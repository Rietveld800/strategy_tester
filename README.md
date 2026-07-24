# strategy_tester — quickfix strategy, backtest, risk management

Strategy department of the trading system (see `../trading_system/README.md` for the
umbrella contracts). Turns the Socrates "time and price meet" method into explicit,
testable rules, backtests them on the array files, applies risk management, and hands the
resulting trades to `charter` for display.

**Scope (firm): strategy_tester produces trade results. It never scrapes data and never
renders charts.** It reads the array (meta) xlsx files from `hyperliquid_bot` (via
`charter`'s parser) and writes trades + equity as JSON / xlsx / a standalone HTML report.

---

## The quickfix strategy (daily timeframe)

A "quick", selective reversal strategy: trade when price probes a cluster of reversal
levels and snaps back. It works long and short; the short is described first, the long is
the exact mirror. All rules are evaluated per daily bar.

**Reversal ladders.** For each day, bullish reversals (`bull_major` + `bull_minor`) and
bearish reversals (`bear_major` + `bear_minor`) are each pooled into one sorted ladder.
Majors and minors count equally.

**Look-ahead rule (critical).** The array file dated D already reflects day D's own
intraday extremes and re-draws any levels that D elected. So a bar is always evaluated
against the reversal levels **known at its start = the previous file's levels**, never its
own file's. The reference "previous close" comes from that same previous file.

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
6. **Target (Rule 4).** 5R. But if a bearish reversal sits closer than 5R below entry, exit
   when price hits it instead. Recomputed each bar from that bar's levels, so a newly
   appearing nearer bearish reversal moves the target up; a reversal that is elected
   (breached) is the exit itself. Only bearish reversals close a short early, never bullish.

### Long setup (mirror)

Bearish ladder for entry, bullish for targets. Tested bearish reversals in
`[low, prev_close)`, ≥3; **first = highest** tested bearish level, second the next highest.
Rule 2: refuse if `open <= second`. Trigger: **close above the first**. Stop = one tick
below the entry bar's low. Rule 3: nearest bullish reversal above entry ≥ 3.5R up. Target:
nearest bullish reversal above entry if nearer than 5R, else `entry + 5R`.

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
ignored. Across markets, positions run concurrently (see the portfolio model below).

### Data window

Per market, trading starts the day after the market's reversals are **first reported**
(older array files carry no reversal block at all, so they produce no signals). Windows
therefore differ per market (gold from 2025-12-15, several obsolete markets end 2026-04-17,
etc.). Gold futures on the COMEX is the reference market.

---

## Files

| File | What it does |
|---|---|
| `quickfix.py` | The engine. `load_bars`, `infer_tick`, signal detection, trade management, and `backtest(bars, tick, dp)`. Run directly for a single-market (gold) JSON ledger. |
| `quickfix_all.py` | Runs every market independently (each a fresh $100k) and writes `quickfix_all_markets_daily.xlsx` (per-market summary + all trades). |
| `quickfix_portfolio.py` | Merges every market's trades into ONE shared account, applies the money-management + slippage model, and writes the portfolio xlsx + `_equity_data.json`. |
| `build_equity_html.py` | Renders `_equity_data.json` into the standalone interactive report `output/equity_curve.html`. |
| `export_charter_trades.py` | Hand-off to charter: writes `output/charter_trades.json` (trade geometry keyed by market). |

Parsing is imported from `../charter/scripts/charting_core.py` (`parse_array`); do not
rewrite it here.

## Portfolio money management (`quickfix_portfolio.py`)

One shared account, starting $100,000, processed chronologically by date. A market's trades
(which trades, their entries/exits, their R) are capital-independent, so they are reused
verbatim and only the money management is re-run on the shared account.

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
slippage. Constants live at the top of `quickfix_portfolio.py`. Fees/commission are omitted
(negligible for liquid futures relative to slippage).

---

## Outputs (`output/`)

- **`quickfix_gold_daily.json`** — single-market ledger: `meta`, `trades` (entry/exit,
  bars, R, pnl%, equity), `equity_curve`.
- **`quickfix_all_markets_daily.xlsx`** — `summary` (per-market: window, trades, win rate,
  return, obsolete flag) + `trades` (all markets).
- **`quickfix_portfolio_daily.xlsx`** — `summary` (net/gross return, drawdown, streaks,
  averages, time in market, slippage), `equity_curve` (daily, with a chart), `trades`
  (gross/cost/net R, prices, P&L, running balance).
- **`equity_curve.html`** — standalone interactive report: equity + drawdown + open-positions
  panels, KPI + per-trade stat tiles, a sortable trade blotter, and a per-market breakdown.
- **`charter_trades.json`** — the charter hand-off (below).

### Charter hand-off schema (`charter_trades.json`)

```
{
  "meta": { "strategy": "quickfix", "timeframe": "daily", "n_markets": N, "n_trades": M, ... },
  "markets": {
    "Gold_Futures_COMEX": {
      "tick": 0.1, "price_decimals": 1,
      "trades": [
        { "side": "short"|"long",
          "entry_date": "YYYY-MM-DD", "entry": <price>,
          "exit_date": "YYYY-MM-DD"|null, "exit": <price>|null,
          "stop": <price>, "target": <price>,
          "reason": "target_5r"|"stop"|"bullish_reversal"|"bearish_reversal"|"unknown_pl"|"open_at_end",
          "r": <net_of_nothing R multiple>|null, "bars": <int>|null }
      ]
    }, ...
  }
}
```

Trade geometry only — the entry plots at the first-reversal price on the entry bar, the exit
at the fill level on the exit bar. `unknown_pl` exits at the stop; `open_at_end` has null
exit. charter reads this at build time and overlays the trades on each market's **daily**
price pane behind a toggle. To refresh the overlay end to end:

1. Here: `venv\Scripts\python.exe export_charter_trades.py` (regenerate after a rule change).
2. In `../charter`: `venv\Scripts\python.exe scripts\chart_all_markets_reference.py`
   (append a market substring, e.g. `... gold`, for a fast single-market rebuild).
3. In `../charter`: `venv\Scripts\python.exe serve.py`, open the site, and click the **T**
   button (green/red triangles) on the right rail to show/hide trades. Long entry =
   up-triangle, short = down-triangle, exit = dot; the dotted entry→exit line is green for a
   win, red for a stop, amber for an ambiguous (`unknown_pl`) outcome, blue for a still-open
   trade. Daily timeframe only; markets with no trades show nothing.

---

## Running

```
venv\Scripts\python.exe quickfix.py            # gold single-market ledger + summary
venv\Scripts\python.exe quickfix_all.py        # per-market xlsx
venv\Scripts\python.exe quickfix_portfolio.py  # shared-account xlsx + _equity_data.json
venv\Scripts\python.exe build_equity_html.py   # -> output/equity_curve.html
venv\Scripts\python.exe export_charter_trades.py  # -> output/charter_trades.json
```

Requirements: `pandas`, `openpyxl` (see `requirements.txt`).

## Working agreements

- Commit straight to main. English only in code/comments/strings. No emoji.
- Simulation inputs (starting capital, 1% risk, slippage) live here; data and charts do not.
- When the user supplies text verbatim, use it verbatim.
