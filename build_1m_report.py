"""Build the quickfix1m1dc REPORT from the saved trades JSON.

The 1-minute workstream's answer to the daily project's
`equity_<strategy>.html`: the model and its dials, the KPI row, the three
synced panes (equity, drawdown on daily closes, open positions), per-trade
statistics, the
exit-class anatomy, the full trade blotter, the per-market table and the
daily calendar. Regenerates from output/quickfix1m1dc_all.json without
re-running the backtest.

It borrows `build_equity_html.CSS` rather than carrying a second
stylesheet, so this page ages with the daily reports instead of drifting
away from them. What it does NOT borrow is `mountReport`: that renderer is
bound to the registry and the shared variant grid, and quickfix1m1dc is
deliberately outside both. The tables here are therefore rendered in
Python, and the only script on the page is the three charts plus a table
sorter.

Every blotter row LINKS INTO charter's 1-minute trade study at that exact
trade (`trades.html?m=<Market>&t=<n>`), which is the workflow the page
exists for: read a row, jump to the picture. The link needs charter's
serve.py running, since the study is served over HTTP.

Money: the portfolio replay is `run_1m.portfolio_replay` mirrored so the
blotter can show each trade's dollar risk, P&L and running balance. The
trades' own `pnl_usd` / `cash_after` fields are PER MARKET (each market a
fresh $100k) and would be a different account entirely, so they are not
used here. The build checks its final capital and drawdown against the
figures run_1m wrote and warns on drift.

`--contracts` (2026-09-01, Lode: "trade it with the contracts and not
with the one percent risk") builds the INTEGER-CONTRACT pages beside
the fractional ones: the same trade list, the same page, but the money
layer sizes every entry in whole contracts off data_center's validated
contract spec table, at the $250,000 deployment account. The sizing
arithmetic is imported from research_1m_sizing (ONE code path), the R
columns are untouched by construction, and the page states its own
delta against the fractional ideal at the same account.

THE CONTRACTS PAGES TRADE THE MICRO STACK SINCE 2026-09-03 (Lode: the
pages were still refusing orders as if only full contracts existed,
"yet we did the whole study of micro-contracts already"). The money
layer is now `replay_micro` -- full contracts first, the routed micro
(research_1m_micro.py's gates JSON) topping the position up toward
the 1% budget, the measured entry drift priced per trade, the micro
stop rounded away on its own grid -- the SAME function the capital
ladder's $250k rung runs, so the two agree to the cent by
construction. The full-contracts-only replay stays on the page as the
thin gray reference curve and a comparison tile, exactly as on the
ladder pages; without the gates JSON the page falls back to full-only
and says so. The blotter shows each position's STACK (n full + k
micro), the risk it ACTUALLY took as a percentage of equity at entry,
and its execution cost split per leg.

THE CONTRACTS PAGES CARRY TWO ACCOUNTS SINCE 2026-09-03 (Lode: "another
equity curve, above the equity curve we currently see ... the same
strategy result WITHOUT stoploss. So the exit will always be at the same
moment in time; settlement ... the curve without stop is as important
as the curve with stop"). The page renders the SAME account section
twice - KPI row, statistics, the three panes, the exit classes, the
refused orders, the open positions, the blotter, the per-market table
and the daily calendar - first for the NO-STOP run and then for the
stopped run, at the same account, the same sizing, the same costs and
the same universe. The no-stop trade list is the engine's own pass
with `stop_live` off (run_1m_matrix.py's companion of the cell, read
from the matrix JSON's `nostop` block), never the stopped blotter
re-priced: a position that is no longer stopped is still open the next
session, so the two lists differ in entries as well as exits. Its
blotter rows link into charter's study through the STOPPED trade that
shares the entry minute, since that is the list charter holds.

THE `_without_mf` PAGES (Lode, 2026-09-03 evening: "a lot of markets are
excluded from trading because of the human market filter ... additional
reports where we say the human market filter gives its release for all
markets"): the same two pages built from the matrix's `no-mf` and
`no-mf no-stop` companions of the cell - the cell's dials run on every
eligible future, so ZC, ZN, ZB, SB, FGBL and BTC join the account (SR3
has no 1-minute bars yet and cannot); the ETFs and JGB stay outside the
traded universe by decision. The contract arsenal derives its statuses
from what the engine ran, so those six read Traded / In arsenal on
these pages; the rules block and the money layer are unchanged.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

import engine_1m
import execution_costs
import research_1m_sizing as sizing
import run_1m
import run_1m_matrix
from build_equity_html import CSS

HERE = Path(__file__).resolve().parent
IN_JSON = HERE / "output" / "quickfix1m1dc_all.json"
MATRIX_JSON = HERE / "output" / "quickfix1m1dc_matrix.json"
# THE BASELINE REPORT IS NAMED FOR ITS CELL (Lode, 2026-08-18): it is
# `variant 2`'s report and was called `quickfix1m1dc_report.html`, which
# said nothing about which dials it ran. DERIVED, not typed - the stem
# and the slug both come from run_1m_matrix, so the filename cannot drift
# from whichever cell is the published baseline.
REPORT_STEM = "quickfix1m1dc_report"
OUT_HTML = HERE / "output" / (
    f"{REPORT_STEM}_"
    f"{run_1m_matrix.variant_slug(run_1m_matrix.BASELINE_NAME)}.html")
LIB_PATH = (HERE / ".." / "data_center" / "scripts"
            / "lightweight-charts.4.2.3.standalone.js")

# The ENGINE BASE: run_1m and the matrix publish their figures at this
# start, and the page's self-check replays against it. Fractional
# percentages are start-invariant, so the check holds whatever the
# page renders at.
START_CAPITAL = 100_000.0
# What the PAGES RENDER AT (Lode, 2026-09-02): both the fractional
# variant reports and the integer-contract pages open the account at
# $250,000.
PAGE_START = 250_000.0
RISK_PCT = 1.0
# The deployment scenario: $250,000 (Lode, 2026-09-02; was $150k), and
# an order whose single contract risks more than the budget is REFUSED
# at placement -- never forced -- and released the moment grown capital
# affords it. research_1m_sizing owns the sizing rule.
SIZING_ACCOUNT = 250_000.0
CONTRACTS_STEM = "quickfix1m1dc_contracts"
# charter serves site/ over HTTP (serve.py, port 8000 by default and the
# next free one after that). A file:// link cannot reach the study, so the
# page says what has to be running.
STUDY_BASE = "http://localhost:8000/1m/trades.html"

REASON_TEXT = {
    "stop": "Stop",
    "close1": "Day-2 settlement",
    "no_confirm": "No confirmation",
    "data_end": "Data end",
}
REASON_NOTE = {
    "stop": "the ladder stop traded",
    "close1": "held to the settlement of the day after entry, the rule exit",
    "no_confirm": "the entry day did not settle beyond the first reversal, "
                  "so the trade was aborted at that settlement",
    "data_end": "collection stopped while the position was open",
}


# ---------------------------------------------------------------- formatting

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def money(v):
    return f"${v:,.0f}" if abs(v) >= 1000 else f"${v:,.2f}"


def signed_money(v):
    return ("+" if v >= 0 else "-") + money(abs(v))


def signed(v, n=2):
    return f"{v:+.{n}f}"


def price(v):
    if v is None:
        return "&mdash;"
    return f"{v:,.4f}".rstrip("0").rstrip(".") if abs(v) < 100 else f"{v:,.2f}"


def cls(v):
    return "pos" if v > 0 else "neg" if v < 0 else ""


def stamp(ts):
    return pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M")


def held(minutes):
    if minutes < 90:
        return f"{minutes:.0f}m"
    if minutes < 60 * 48:
        return f"{minutes / 60:.1f}h"
    return f"{minutes / 1440:.1f}d"


# ------------------------------------------------------------------- numbers

def replay(trades, risk_pct=RISK_PCT, start=START_CAPITAL):
    """run_1m.portfolio_replay, keeping each trade's own money.

    Same event order (exits before entries at an equal timestamp) and the
    same sizing rule (risk_pct of equity at entry), so at the default the
    final capital is the figure run_1m published.
    """
    events = []
    for i, t in enumerate(trades):
        events.append((pd.Timestamp(t["entry_ts"]), 1, i))
        events.append((pd.Timestamp(t["exit_ts"]), 0, i))
    events.sort(key=lambda e: (e[0], e[1]))

    equity, peak, max_dd = start, start, 0.0
    open_risk, money_of, eod = {}, {}, {}
    for ts, kind, i in events:
        if kind == 1:
            open_risk[i] = equity * risk_pct / 100.0
        else:
            risk = open_risk.pop(i, equity * risk_pct / 100.0)
            pnl = trades[i]["net_r"] * risk
            equity += pnl
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
            money_of[i] = dict(risk_usd=risk, pnl_usd=pnl, balance=equity)
            # Three numbers per day, not one. The balance at the bell is what
            # the equity line plots, but the deepest hole of a session can be
            # filled again before that bell, and the running peak can be set
            # by a trade that is not the day's last. Carrying only the closing
            # balance hid 11.20% behind an 8.96% pane (Lode, 2026-08-08).
            worst = max(eod.get(ts.date(), (0.0, 0.0, 0.0))[2],
                        (peak - equity) / peak * 100.0)
            eod[ts.date()] = (equity, peak, worst)
    return money_of, eod, equity, max_dd


def replay_contracts(trades, risk_pct=RISK_PCT, start=SIZING_ACCOUNT):
    """replay() in INTEGER position sizes -- the deployability rendering
    of the same trade list. Each entry takes what its budget affords in
    whole contracts off data_center's validated contract spec table;
    an entry whose SINGLE contract busts the budget is REFUSED at
    placement and booked nowhere (research_1m_sizing.contract_size, ONE
    code path with the research reading; refusal policy Lode
    2026-09-01, superseding force-1; margin out of scope). ETFs are
    sized in whole shares, which pay FULL notional -- each row records
    what it locked. Returns (money_of, eod, final, max_dd, refused):
    money_of covers the TAKEN trades only, refused maps the skipped
    trade index to its sizing facts. The R columns of a taken trade
    cannot move: only the money differs from replay().
    """
    specs, _ = sizing.load_specs()
    events = []
    for i, t in enumerate(trades):
        events.append((pd.Timestamp(t["entry_ts"]), 1, i))
        events.append((pd.Timestamp(t["exit_ts"]), 0, i))
    events.sort(key=lambda e: (e[0], e[1]))

    equity, peak, max_dd = start, start, 0.0
    open_pos, money_of, eod, refused = {}, {}, {}, {}
    for ts, kind, i in events:
        t = trades[i]
        if kind == 1:
            spec = specs[t["market"]]
            is_etf = spec["type"] == "etf"
            per_unit = t["rpu"] * sizing.usd_point_value(spec)
            n, refuse = sizing.contract_size(equity, risk_pct, per_unit)
            if refuse:
                refused[i] = dict(per_unit=per_unit, equity=equity,
                                  budget=equity * risk_pct / 100.0)
                continue
            # Execution costs, per side (execution_costs.py: IBKR
            # commission + exchange + NFA, sourced; taxes excluded by
            # decision). The entry side is paid the moment the order
            # fills; slippage stays in R where the engine put it.
            side = execution_costs.cost_per_side(
                t["market"], n, is_etf=is_etf, eurusd=sizing.EURUSD)
            equity -= side
            m = dict(n=n, per_unit=per_unit,
                     risk_usd=n * per_unit,
                     risk_pct=n * per_unit / (equity + side) * 100.0,
                     cost_rt=2.0 * side, etf=is_etf)
            if is_etf:
                m["locked_usd"] = n * t["entry"]
                m["locked_pct"] = m["locked_usd"] / (equity + side) * 100.0
            open_pos[i] = m
        else:
            m = open_pos.pop(i, None)
            if m is None:
                continue  # the entry was refused
            # The row's P&L carries the FULL round turn's cost so the
            # blotter attributes the bill to the trade that rang it up;
            # the equity path paid half at entry already.
            pnl = t["net_r"] * m["risk_usd"] - m["cost_rt"]
            equity += t["net_r"] * m["risk_usd"] - m["cost_rt"] / 2.0
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
            money_of[i] = dict(m, pnl_usd=pnl, balance=equity)
            worst = max(eod.get(ts.date(), (0.0, 0.0, 0.0))[2],
                        (peak - equity) / peak * 100.0)
            eod[ts.date()] = (equity, peak, worst)
    return money_of, eod, equity, max_dd, refused


# --------------------------------------------------------- the micro stack

GATES_JSON = HERE / "output" / "quickfix1m1dc_micro_gates.json"


# A micro top-up never takes more than this share of the entry
# minute's printed volume -- drift pricing answers fidelity, this
# answers liquidity, trade by trade.
PARTICIPATION_CAP = 0.5


def micro_route():
    """market -> routed micro leg spec plus the per-entry drift map,
    from the measured study (research_1m_micro.py). Since the
    drift-pricing revision (Lode, 2026-09-02) every sourced candidate
    routes; the measured drift is PRICED per trade instead of gating
    the market, and a trade with no per-entry record gets no micro
    leg."""
    gates = json.loads(GATES_JSON.read_text(encoding="utf-8"))
    route = {}
    for key, root in gates["routing"].items():
        if root is None:
            continue
        cand = next(c for c in gates["candidates"][key]
                    if c["root"] == root)
        route[key] = dict(root=root, fraction=cand["fraction"],
                          tick=cand["tick"])
    return route, gates


def rounded_micro_stop(entry, stop, tick):
    """The parent-space stop price on the MICRO's tick grid, rounded
    AWAY from entry -- a micro stop may only be equal or wider, never
    tighter, than the parent's (Lode: the stop placement on the micro
    is the critical piece; conservatism is the rule).

    Rounded on the EXCHANGE'S ABSOLUTE PRICE GRID (multiples of the
    micro tick), never on an entry-anchored offset grid: the slipped
    entry fill can sit off-grid, and an order book only accepts grid
    prices. The epsilon absorbs float dust so a stop already on the
    grid stays exactly where it is."""
    import math as _m
    steps = stop / tick
    eps = 1e-9 * max(1.0, abs(steps))
    if stop > entry:      # short: the stop sits above, round UP
        return _m.ceil(steps - eps) * tick
    return _m.floor(steps + eps) * tick


def replay_micro(trades, risk_pct, start, route, specs, per_entry):
    """The mixed-stack replay: full contracts first, then the routed
    micro tops the remainder up toward the budget. Refused only when
    even one micro does not fit (or the market has no routed micro and
    one full contract does not fit).

    Booking, precise by construction: the micro leg's RISK uses its
    own rounded stop distance (>= the parent's); a STOP exit books the
    micro leg at that wider distance (net_r scaled on its own risk
    base), any other exit books the identical per-unit price move the
    parent leg made (net_r x parent rpu x micro point value). Costs
    are charged per leg per side from the sourced table and reported
    split.

    THE DRIFT IS PRICED, NOT GATED (Lode, 2026-09-02): the measured
    signed basis of the micro's print against the parent's at THIS
    trade's entry minute is booked into the curve at entry --
    side_sign x basis x point value x contracts, a COST when the micro
    sat on the wrong side of the parent for our direction and a CREDIT
    when it sat on the right one. Per-trade liquidity rules: no micro
    bar at the entry minute means no micro leg for that trade, and the
    top-up never exceeds PARTICIPATION_CAP of the minute's printed
    volume. Exits at settlement are treated as aligned (exchange
    micro settlements track the parent's); stop exits book the micro
    leg at its own grid-rounded stop distance."""
    events = []
    for i, t in enumerate(trades):
        events.append((pd.Timestamp(t["entry_ts"]), 1, i))
        events.append((pd.Timestamp(t["exit_ts"]), 0, i))
    events.sort(key=lambda e: (e[0], e[1]))

    equity, peak, max_dd = start, start, 0.0
    open_pos, money_of, eod, refused = {}, {}, {}, {}
    for ts, kind, i in events:
        t = trades[i]
        if kind == 1:
            spec = specs[t["market"]]
            pv_full = sizing.usd_point_value(spec)
            full_risk = t["rpu"] * pv_full
            budget = equity * risk_pct / 100.0
            n = int(budget // full_risk)
            r = route.get(t["market"])
            rec = per_entry.get(
                f"{t['market']}|{t['contract']}|{t['entry_ts']}")
            k, rpu_m, pv_m, root, basis = 0, None, None, None, 0.0
            if r is not None and rec is not None and rec["volume"] > 0:
                root = r["root"]
                basis = rec["basis"]
                # The SAME risk anchor as the parent's R: level to
                # stop (entry_first), never the slipped fill -- the
                # two legs must denominate one distance, the micro's
                # merely rounded to its own grid.
                anchor = t.get("entry_first") or t["entry"]
                stop_m = rounded_micro_stop(anchor, t["stop"],
                                            r["tick"])
                rpu_m = abs(anchor - stop_m)
                pv_m = pv_full * r["fraction"]
                micro_risk = rpu_m * pv_m
                k = min(int((budget - n * full_risk) // micro_risk),
                        int(rec["volume"] * PARTICIPATION_CAP))
                k = max(k, 0)
            if n == 0 and k == 0:
                refused[i] = dict(per_unit=full_risk, equity=equity,
                                  budget=budget)
                continue
            side = execution_costs.cost_per_side(
                t["market"], n, eurusd=sizing.EURUSD) if n else 0.0
            side_m = execution_costs.cost_per_side(
                root, k, eurusd=sizing.EURUSD) if k else 0.0
            # the measured entry drift, signed against our side: a
            # long pays a micro printing above the parent, a short is
            # paid by it
            side_sign = 1.0 if t["side"] == "long" else -1.0
            drift = (side_sign * basis * pv_m * k) if k else 0.0
            equity -= side + side_m + drift
            risk_usd = n * full_risk + (k * rpu_m * pv_m if k else 0.0)
            m = dict(n=n, k=k, root=root, rpu_m=rpu_m, pv_m=pv_m,
                     full_risk=full_risk, risk_usd=risk_usd,
                     risk_pct=risk_usd
                     / (equity + side + side_m + drift) * 100.0,
                     cost_full_rt=2.0 * side, cost_micro_rt=2.0 * side_m,
                     drift_usd=drift)
            open_pos[i] = m
        else:
            m = open_pos.pop(i, None)
            if m is None:
                continue
            pnl_full = t["net_r"] * m["n"] * m["full_risk"]
            if m["k"]:
                if t["reason"] == "stop":
                    # the micro leg is stopped at ITS OWN rounded stop:
                    # the loss per unit is its wider distance
                    pnl_micro = t["net_r"] * m["k"] * m["rpu_m"] * m["pv_m"]
                else:
                    # any other exit fills both legs at the same price,
                    # so the per-unit move is the parent's
                    pnl_micro = t["net_r"] * t["rpu"] * m["pv_m"] * m["k"]
            else:
                pnl_micro = 0.0
            pnl = (pnl_full + pnl_micro
                   - m["cost_full_rt"] / 2.0 - m["cost_micro_rt"] / 2.0)
            equity += pnl
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
            money_of[i] = dict(
                m, pnl_usd=pnl_full + pnl_micro
                - m["cost_full_rt"] - m["cost_micro_rt"]
                - m["drift_usd"],
                balance=equity)
            worst = max(eod.get(ts.date(), (0.0, 0.0, 0.0))[2],
                        (peak - equity) / peak * 100.0)
            eod[ts.date()] = (equity, peak, worst)
    return money_of, eod, equity, max_dd, refused



def solve_risk_pct(trades, target_dd):
    """The risk per trade that puts the replay at target_dd worst-reached.

    solve_risk.py's bisection, on THIS module's replay rather than a
    second copy of the money management, for the same reason it insists
    on run_portfolio's own account(): a drifted copy would hand back a
    risk that does not actually produce the target.
    """
    def dd(r):
        return replay(trades, r)[3]

    lo, hi = 0.0, 8.0
    while dd(hi) < target_dd:
        hi *= 2
        if hi > 100:
            return None
    while hi - lo > 0.0005:
        mid = (lo + hi) / 2
        if dd(mid) < target_dd:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 3)


def daily_series(trades, eod, calendar, start=START_CAPITAL,
                 first_entry=None):
    """The three panes' data, one point per MARKET DAY (see run_1m).

    `first_entry` pins the grid's start when two accounts share one page
    (the no-stop and the stopped account, 2026-09-03): both must be
    drawn on the same days, so the earlier first entry of the two is
    passed to both.

    The grid runs from a market day before the first entry to the LAST
    MARKET DAY in the calendar, not to the last exit: the account is as
    up to date as the data is, and a fortnight with no trade in it is a
    fortnight of flat line rather than the page simply stopping.

    A day's figures are placed with run_1m.place, not by their own date:
    an exit can print at 23:30 UTC on a Sunday whose TRADING date is the
    Monday, and dropping it would take the headline drawdown off the pane
    it is supposed to be the bottom of. Two days landing on one grid day
    merge - the later balance and peak, the deeper hole.
    """
    spans = [(pd.Timestamp(t["entry_ts"]).date(),
              pd.Timestamp(t["exit_ts"]).date()) for t in trades]
    grid = run_1m.market_day_grid(
        calendar, first_entry or min(a for a, _ in spans))
    on_grid = {}
    for d in sorted(eod):
        i = run_1m.place(d, grid)
        prev = on_grid.get(i)
        value, peak, worst = eod[d]
        on_grid[i] = (value, peak,
                      max(worst, prev[2]) if prev else worst)
    days, eq, dd, ddc, openpos = [], [], [], [], []
    value, peak = start, start
    # A second, gentler curve next to the worst-reached one: drawdown on the
    # CLOSING balances only, peak and trough both read at the bell. A day
    # that digs and refills before the close does not appear in it.
    peak_close = start
    for i, d in enumerate(grid):
        if i in on_grid:
            value, peak, worst = on_grid[i]
        else:
            # Nothing closed, so neither the balance nor the peak moved and
            # the drawdown simply persists.
            worst = (peak - value) / peak * 100.0
        peak_close = max(peak_close, value)
        days.append(str(d))
        eq.append(round(value, 2))
        dd.append(round(worst, 3))
        ddc.append(round((peak_close - value) / peak_close * 100.0, 3))
        openpos.append(sum(1 for a, b in spans if a <= d < b))
    return days, eq, dd, ddc, openpos


def streaks(trades, outcome=None):
    """Longest winning and losing run, in ENTRY order and off net R.

    The project's rule (user, 2026-07-29): the blotter is sorted by entry,
    so a reader counting losing rows counts entry order, and keying off R
    keeps the figure independent of the bet size. `outcome(i)` swaps the
    figure a trade wins or loses by (the contracts pages count in the
    account's own dollars, 2026-09-03 evening).
    """
    best_w = best_l = cur_w = cur_l = 0
    order = sorted(range(len(trades)), key=lambda i: trades[i]["entry_ts"])
    for i in order:
        t = trades[i]
        v = outcome(i) if outcome else t["net_r"]
        if v > 0:
            cur_w, cur_l = cur_w + 1, 0
        else:
            cur_l, cur_w = cur_l + 1, 0
        best_w, best_l = max(best_w, cur_w), max(best_l, cur_l)
    return best_w, best_l


# The settlement class split by outcome (user, 2026-08-09): the edge lives
# in the day-2 survivors, so the table separates the settlements that paid
# from the ones that did not instead of averaging them into one row.
CLASS_DEFS = [
    ("Day 2 win",
     lambda t: t["reason"] == "close1" and t["net_r"] > 0,
     "held to the settlement of the day after entry, the rule exit, and "
     "settled in profit"),
    ("Day 2 loss",
     lambda t: t["reason"] == "close1" and t["net_r"] <= 0,
     "held to the same rule exit, which settled against the position"),
    ("Stop loss",
     lambda t: t["reason"] == "stop",
     "the ladder stop traded"),
    ("No confirmation",
     lambda t: t["reason"] == "no_confirm",
     REASON_NOTE["no_confirm"]),
    ("Data end",
     lambda t: t["reason"] == "data_end",
     REASON_NOTE["data_end"]),
]


def class_rows_html(trades, money_of=None):
    """`money_of` switches the two figure columns from R to the account's
    dollars (the contracts pages, 2026-09-03 evening)."""
    rows = []
    for label, pick, note in CLASS_DEFS:
        idx = [i for i, t in enumerate(trades) if pick(t)]
        if not idx:
            continue
        if money_of is not None:
            r = sum(money_of[i]["pnl_usd"] for i in idx)
            fmt = signed_money
        else:
            r = sum(trades[i]["net_r"] for i in idx)
            fmt = signed
        avg = r / len(idx)
        # The % column is this class's share of ALL trades, not a win rate
        # within the class (user, 2026-08-09), tinted by which side of the
        # ledger the class sits on.
        rows.append(
            f'<tr><td class="l">{label}</td>'
            f'<td class="mono">{len(idx)}</td>'
            f'<td class="mono {cls(r)}">'
            f'{100 * len(idx) / len(trades):.1f}%</td>'
            f'<td class="mono {cls(r)}">{fmt(r)}</td>'
            f'<td class="mono {cls(avg)}">{fmt(avg)}</td>'
            f'<td class="l wrap">{note}</td></tr>')
    return "".join(rows)


def markets_money_html(trades, money_of, links):
    """The per-market table of a CONTRACTS account, from the trades it
    took and the money they booked (2026-09-03 evening, Lode: these
    pages are about the position in contracts and never a flat 1%).
    The engine's per-market rows - each market a fresh $100k at 1% -
    stay on the fractional pages."""
    by = {}
    for i, t in enumerate(trades):
        by.setdefault(t["market"], []).append(i)
    cols = [("Market", "l", 20), ("Trades", "", 9), ("Win %", "", 9),
            ("Net P&amp;L $", "", 14), ("Net R", "", 10), ("Stops", "", 9),
            ("Settlement", "", 12), ("Costs $", "", 17)]
    head = "".join(
        f'<th class="{c} sortable" data-i="{i}" style="width:{w}%">{lab}'
        f'<span class="ar"></span></th>'
        for i, (lab, c, w) in enumerate(cols))
    body = []
    for key in sorted(by):
        idx = by[key]
        pnl = sum(money_of[i]["pnl_usd"] for i in idx)
        wins = sum(1 for i in idx if money_of[i]["pnl_usd"] > 0)
        wr = 100.0 * wins / len(idx)
        r = sum(trades[i]["net_r"] for i in idx)
        stops = sum(1 for i in idx if trades[i]["reason"] == "stop")
        settle = sum(1 for i in idx if trades[i]["reason"] == "close1")
        costs = sum(money_of[i].get("cost_full_rt", money_of[i].get("cost_rt", 0.0))
                    + money_of[i].get("cost_micro_rt", 0.0)
                    + money_of[i].get("drift_usd", 0.0) for i in idx)
        link = links.get(key)
        name = (f'<a href="{link[0]}" target="_blank" '
                f'title="{esc(link[2])} in the 1m study">{esc(key)}</a>'
                if link else esc(key))
        body.append(
            f'<tr><td class="l" data-s="{esc(key)}">{name}</td>'
            f'<td class="mono" data-s="{len(idx)}">{len(idx)}</td>'
            f'<td class="mono" data-s="{wr:.1f}">{wr:.0f}%</td>'
            f'<td class="mono {cls(pnl)}" data-s="{pnl:.2f}">'
            f'{signed_money(pnl)}</td>'
            f'<td class="mono {cls(r)}" data-s="{r:.4f}">{signed(r)}</td>'
            f'<td class="mono" data-s="{stops}">{stops}</td>'
            f'<td class="mono" data-s="{settle}">{settle}</td>'
            f'<td class="mono" data-s="{costs:.2f}">{money(costs)}</td>'
            f'</tr>')
    return (f'<div class="tradecard"><div class="tradescroll">'
            f'<table class="trades" data-sort="3" data-dir="-1">'
            f'<thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div></div>')


def exit_classes(trades):
    out = {}
    for t in trades:
        c = out.setdefault(t["reason"], dict(n=0, wins=0, r=0.0))
        c["n"] += 1
        c["wins"] += 1 if t["net_r"] > 0 else 0
        c["r"] += t["net_r"]
    for c in out.values():
        c["avg"] = c["r"] / c["n"]
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["n"]))


# --------------------------------------------------------------------- parts

def kpi(label, value, sub="", tone=""):
    tone = f" {tone}" if tone else ""
    return (f'<div class="kpi"><div class="k">{label}</div>'
            f'<div class="v{tone}">{value}</div>'
            f'<div class="sub">{sub}</div></div>')


STOP_TEXT = {
    "ladder": "one tick beyond the <b>5th reversal</b> of the active ladder, "
              "the 4th when only four exist",
    "ladder_or_extreme": "one tick beyond whichever is further away, the "
                         "<b>5th reversal</b> of the active ladder or the "
                         "<b>session's running extreme at entry</b>",
    "extreme": "one tick beyond the <b>session's running extreme at "
               "entry</b>, ignoring the ladder",
}


def geometry_foot(p):
    """The geometry-cut paragraph, generated from the payload's own dials so
    a variant page states its own model rather than the baseline's."""
    lo = p.get("min_rpu_range_ratio")
    hi = p.get("max_rpu_range_ratio")
    if lo is None and hi is None:
        return ('<div class="rulefoot"><b>The geometry cut</b> is <b>off</b> '
                'on this page: every setup is taken whatever its '
                'level-to-stop distance measures against the trailing '
                'previous trading day&rsquo;s range. The published baseline carries the band at '
                '0.20 / 0.50 (adopted, audit s.15e and s.17).</div>')
    band = (f"{lo:.2f} to {hi:.2f}" if lo and hi is not None
            else f"at most {hi:.2f}" if hi is not None
            else f"at least {lo:.2f}")
    return (
        '<div class="rulefoot"><b>The geometry cut</b> (adopted, audit '
        's.15e and s.17): an entry is refused unless its <b>level-to-stop '
        f'distance</b> is <b>{band}</b> of the market\'s PREVIOUS TRADING DAY\'s '
        'high-low range. Under the fixed settlement exit a wider ladder has '
        'a mathematically capped payoff against a full -1R downside, so '
        'the upper cut follows from the exit rule and sits on a measured '
        'plateau (0.40-0.55); the lower cut declines the compact ladders '
        'that spend the session lockout before a better-proportioned setup '
        'appears. A refused entry does not spend the session-lockout '
        'allowance, so a later minute may trigger instead. With fewer than '
        f'{engine_1m.MIN_RANGE_BARS} bars of trailing window the cut '
        'abstains rather than refuses.'
        + ('' if (lo or 0) > 0 else ' This page runs <b>no lower cut</b>; '
           'the published baseline carries 0.20 (s.17).')
        + '</div>')


def rules_html(p):
    slip = (f'{engine_1m.ENTRY_SLIP_TICKS} ticks on entry, '
            f'{engine_1m.SLIP_STOP_TICKS} on a stop, '
            f'{engine_1m.SLIP_SCHEDULED_TICKS} on a settlement exit')
    confirm = p.get("confirm", True)
    exit_card = (
        "The <b>settlement of the day after entry</b>, with the stop live "
        "throughout. Nothing else closes the trade."
        if not confirm else
        "The <b>settlement of the day after entry</b>. If the entry day does "
        "not settle at least one tick beyond the active first reversal, the "
        "trade is aborted at that settlement instead "
        "(<b>no confirmation</b>). The stop is live throughout.")
    cards = [
        ("1", "Signal",
         f"At least <b>{p['min_tested']} reversals</b> of the active file's "
         "ladder are tested beyond the previous close, measured on the "
         "session's <b>running extremes</b>, minute by minute. The ladder "
         f"itself must carry <b>{p['min_ladder']} levels</b>, since the stop "
         "is anchored in it."),
        ("2", "Clean setup",
         "Refused if the <b>day's open</b> is already at or beyond the second "
         "reversal. The verdict is taken once per ladder against that same "
         "day open, and it governs while that ladder is active."),
        ("3", "Entry",
         "A <b>market order</b> the moment the first reversal price prints "
         f"(or the bar gaps past it, filling from the open), at "
         f"<b>{engine_1m.ENTRY_SLIP_TICKS} ticks</b> of adverse slippage. "
         "Risk is denominated on the <b>first reversal to the stop</b>, never "
         "on the slipped fill."),
        ("4", "Exit", exit_card),
    ]
    grid = "".join(
        f'<div class="rule"><div class="n">{n}</div><div>'
        f'<div class="rn">Rule {n} &middot; {t}</div>'
        f'<div class="rt">{body}</div></div></div>'
        for n, t, body in cards)
    return f"""<div class="rules">
  <div class="rhead"><div class="t">quickfix1m1dc, the v2 model</div>
  <div class="s">Rules 1 and 2 are the daily project's, evaluated INTRADAY on
  1-minute bars. Rule 3, the 3.5R room requirement, was removed on 2026-08-06
  as target-era logic: this strategy exits at a settlement regardless, so it
  guarded nothing, and its existence clause blocked the one-sided files that
  mark the strongest trends.{"" if confirm else " The confirmation clause went"
  " the same day, and for the opposite reason: it was measured, and cutting"
  " unconfirmed trades at the entry-day close cost net R, win rate AND"
  " drawdown against simply carrying them."}</div></div>
  <div class="rulegrid">{grid}</div>
  <div class="rulefoot"><b>The stop</b> is
  {STOP_TEXT.get(p.get('stop_mode', 'ladder'), p.get('stop_mode'))}. It
  is structural, not a multiple of the move, and it is what makes 1R a
  distance the chart can show. <b>1R = {p['risk_pct']}%</b> of equity at
  entry.</div>
  <div class="rulefoot"><b>The session lockout</b>: at most
  <b>{p.get('max_entries_per_session') or 'any number of'}</b> entries per
  market per session, expiring at the session boundary. It is not one of the
  rules above, it is a fact about our own previous trade, in the same family
  as one position per market at a time. It counts ENTRIES, so a position
  carried in from the previous session and stopped intraday does not spend
  the allowance. Measured before it was built: the 1st trade of a market-day
  won 39.4% for +42.51R, the 2nd won 21.4% for -10.39R.</div>
  {geometry_foot(p)}
  <div class="rulefoot"><b>Dials</b>, at the setting this page is built at:
  the <b>confirmation clause</b> is
  <b>{'on' if confirm else 'off'}</b>, stop tightening at the entry-day
  settlement is <b>{'on' if p['tighten'] else 'off'}</b>, entries before the
  day's own update is active are
  <b>{'allowed' if p['allow_pre_activation'] else 'blocked'}</b>, and levels
  activate at <b>{p.get('activation_utc', '07:35')} UTC</b>. Every one of
  those was chosen by a measured matrix, see the audit.</div>
  <div class="rulefoot"><b>Slippage</b>: {slip}. The entry is charged in the
  PRICE, the exits in R. The settlement rate is an order-type argument, the
  time is known in advance so the order can be worked, and not a liquidity
  claim: the day's volume peaks are the open and the session close, and
  settlement is neither.</div>
</div>"""


def refused_html(all_trades, refused_map, links_full, route=None):
    """The orders the sizing policy refused (Lode, 2026-09-01: never
    force a trade above the 1% budget; the same setup is released the
    moment grown capital affords one contract). They are rendered as
    their own table rather than dimmed blotter rows because they are
    not trades: nothing was entered, nothing is booked, no statistic
    above counts them. The R column shows what the blotter's trade went
    on to do -- the release analysis a growing account wants to read.

    With `route` (the micro stack in force) a refusal means even ONE
    MICRO did not fit -- or the market has no routed micro, or no
    micro bar printed at that entry minute -- and the table says
    which."""
    if not refused_map:
        return ""
    head = '<div class="section-h">Refused at order placement</div>'
    if route is None:
        note = (
            '<p class="chartnote">Entries whose <b>single contract</b> '
            'risked more than the 1% budget at that moment. The order is '
            'refused, never forced, and nothing is booked; as the account '
            'grows, the same market&rsquo;s later setups clear the bar on '
            'their own. <b>R (not taken)</b> is what the blotter&rsquo;s '
            'trade did &mdash; information about the release, not booked '
            'money.</p>')
    else:
        note = (
            '<p class="chartnote">Entries where <b>one full contract</b> '
            'risked more than the 1% budget at that moment <b>and no '
            'micro contract could stand in</b>: the market has no routed '
            'micro (<b>Micro</b> shows a dash), no micro bar printed at '
            'that entry minute, or even one micro risked more than the '
            'budget. The order is refused, never forced, and nothing is '
            'booked; as the account grows, the same market&rsquo;s later '
            'setups clear the bar on their own. <b>R (not taken)</b> is '
            'what the blotter&rsquo;s trade did &mdash; information about '
            'the release, not booked money.</p>')
    cols = [("Market", "l", 11), ("Side", "l", 7), ("In (UTC)", "l", 15),
            ("1 contract $", "", 13), ("Budget $", "", 12),
            ("Equity $", "", 13), ("R (not taken)", "", 12),
            ("Reason", "l", 17)]
    if route is not None:
        cols = [("Market", "l", 10), ("Side", "l", 6), ("In (UTC)", "l", 14),
                ("1 contract $", "", 12), ("Micro", "l", 8),
                ("Budget $", "", 11), ("Equity $", "", 12),
                ("R (not taken)", "", 11), ("Reason", "l", 16)]
    heads = "".join(f'<th class="{c}" style="width:{w}%">{lab}</th>'
                    for lab, c, w in cols)
    rows = []
    for i in sorted(refused_map, key=lambda i: all_trades[i]["entry_ts"]):
        t, r = all_trades[i], refused_map[i]
        link = links_full.get(t["market"])
        name = esc(t["market"])
        if link:
            name = (f'<a href="{link[0]}{study_t(link, i)}" '
                    f'target="_blank">{name}</a>')
        micro_cell = ""
        if route is not None:
            m = route.get(t["market"])
            micro_cell = (f'<td class="l mono">'
                          f'{esc(m["root"]) if m else "&mdash;"}</td>')
        rows.append(
            f'<tr>'
            f'<td class="l">{name}</td>'
            f'<td class="l">{t["side"]}</td>'
            f'<td class="l mono">{stamp(t["entry_ts"])}</td>'
            f'<td class="mono neg">{money(r["per_unit"])}</td>'
            f'{micro_cell}'
            f'<td class="mono">{money(r["budget"])}</td>'
            f'<td class="mono">{money(r["equity"])}</td>'
            f'<td class="mono {cls(t["net_r"])}">{signed(t["net_r"])}</td>'
            f'<td class="l">{REASON_TEXT.get(t["reason"], t["reason"])}'
            f'</td></tr>')
    return (f'{head}{note}<div class="tradecard"><table class="trades">'
            f'<thead><tr>{heads}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def open_html(open_positions, stopped=True):
    """The positions entered but not yet closed (Lode, 2026-08-29): a
    window-end entry waiting for the settlement of its market's next
    trading day, carried by run_1m.py as `open_positions` beside the
    blotter. None means the payload does not track them at all - a matrix
    cell, or a JSON from before the key existed - and the section is
    omitted; an empty LIST is a positive statement and prints as one.
    Not to be confused with the "Open positions" chart pane, which counts
    concurrently open CLOSED-by-now trades over time."""
    if open_positions is None:
        return ""
    head = '<div class="section-h">Currently open</div>'
    if not open_positions:
        return (head + '<p class="chartnote">No open positions at the end '
                'of the data: every entry in the window has met its '
                'exit.</p>')
    note = (
        '<p class="chartnote">Entered but not yet closed: each of these '
        'exits at the settlement of its market&#39;s next trading day, so '
        'a position entered before a weekend or holiday waits here until '
        'that settlement prints. <b>R so far</b> is marked at the last '
        'settlement in the data and nothing is booked &mdash; every '
        'figure above counts closed trades only. A market whose data '
        'stopped entirely never parks here: a position stranded by a '
        'data stop is force-closed in the blotter as <b>Data end</b>.'
        + ('' if stopped else ' <b>Stop</b> here is the sizing anchor '
           'only: no stop order rests in this account.')
        + '</p>')
    cols = [("Market", "l", 12), ("Side", "l", 7), ("In (UTC)", "l", 15),
            ("In", "", 11), ("Stop", "", 11), ("R/24h", "", 9),
            ("R so far", "", 11), ("Marked at (UTC)", "l", 24)]
    heads = "".join(f'<th class="{c}" style="width:{w}%">{lab}</th>'
                    for lab, c, w in cols)
    rows = []
    for o in sorted(open_positions, key=lambda o: o["entry_ts"]):
        ratio = o.get("rpu_range_ratio")
        rows.append(
            f'<tr>'
            f'<td class="l">{esc(o["market"])}</td>'
            f'<td class="l">{o["side"]}</td>'
            f'<td class="l mono">{stamp(o["entry_ts"])}</td>'
            f'<td class="mono">{price(o["entry"])}</td>'
            f'<td class="mono">{price(o["stop"])}</td>'
            f'<td class="mono">'
            f'{f"{ratio:.2f}" if ratio is not None else "&mdash;"}</td>'
            f'<td class="mono {cls(o["unrealized_r"])}">'
            f'{signed(o["unrealized_r"])}</td>'
            f'<td class="l mono">{stamp(o["mark_ts"])}</td>'
            f'</tr>')
    return (f'{head}{note}<div class="tradecard"><table class="trades">'
            f'<thead><tr>{heads}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def study_t(link, i):
    """The `&t=` part of a study link for trade i, or nothing when the
    study holds no row for it (a no-stop trade whose entry the stopped
    list never took): the link then opens the market's study on its
    first trade rather than a wrong one."""
    n = link[1].get(i)
    return f"&amp;t={n}" if n else ""


def study_title(link, i):
    n = link[1].get(i)
    if n is None:
        return "no row in the 1m study for this entry (the stopped list " \
               "never took it); opens the market"
    return f"trade {n} in the 1m study" + (
        " (numbered through the list charter holds)" if link[3] else "")


def study_links(all_trades, vslug, numbering=None):
    """key -> (study url, {trade index: n in the study}, market folder,
    by_proxy). charter sorts each market's trades by entry and numbers
    them 1-based, so the link lands on the row.

    THE URL MUST NAME THIS PAGE'S VARIANT (2026-08-13, Lode found it).
    charter's study holds one trade list per matrix cell now, and `?v=`
    picks which. Without it the study fell back to the PUBLISHED blotter
    and indexed THAT: a variant page's row drew the baseline's ladder
    stop, and wherever the two trade lists diverge the link opened a
    different trade entirely (31 of variant 5's 66 rows). The index is
    only meaningful inside the list it was counted in.

    `numbering` is the list charter actually holds when it is not
    `all_trades` itself: the NO-STOP account's rows (2026-09-03) are
    numbered through the STOPPED trade sharing their (market, entry
    minute), because that is the list in the study; an entry the stopped
    run never took gets no number and links to the market alone.
    """
    numbering = all_trades if numbering is None else numbering
    by_proxy = numbering is not all_trades
    by_market_num = {}
    for i, t in enumerate(numbering):
        by_market_num.setdefault(t["market"], []).append(i)
    n_of = {}
    for key, idxs in by_market_num.items():
        order = sorted(idxs, key=lambda i: numbering[i]["entry_ts"])
        for n, i in enumerate(order):
            n_of[(key, numbering[i]["entry_ts"])] = n + 1
    out = {}
    for key in sorted({t["market"] for t in all_trades}):
        try:
            folder = run_1m.market_info(key)["array_dir"]
        except (KeyError, StopIteration):
            continue
        url = f"{STUDY_BASE}?m={folder}"
        if vslug:
            url += f"&amp;v={vslug}"      # the url goes straight into an href
        nums = {i: n_of[(key, t["entry_ts"])]
                for i, t in enumerate(all_trades)
                if t["market"] == key and (key, t["entry_ts"]) in n_of}
        out[key] = (url, nums, folder, by_proxy)
    return out


def mf_cell(market):
    """The MF column: did the market pass the human market filter."""
    if market in run_1m.HUMAN_APPROVED:
        return '<td class="l pos" data-s="passed">passed</td>'
    return '<td class="l neg" data-s="no pass">no pass</td>'


def blotter_html(trades, money_of, links, contracts=False, micro=False,
                 mf=False):
    """`contracts` adds the position-size column; `micro` (the combined
    full+micro stack) renders it as the STACK with the risk the position
    actually took and its costs, the columns Lode asked the contracts
    pages to carry (2026-09-03). `mf` adds the MARKET FILTER column
    (same evening): `passed` for a market of the human filter's
    universe, `no pass` for one trading only because the filter is
    lifted on that page."""
    if contracts and micro and mf:
        # Sixteen columns; the timestamps keep their width (they are the
        # widest strings), the rest give up a little; sums to 100.
        cols = [("Market", "l", 7), ("Side", "l", 4.5),
                ("In (UTC)", "l", 10.5), ("Out (UTC)", "l", 10.5),
                ("Held", "", 4), ("In", "", 6), ("Out", "", 6),
                ("Stop", "", 6), ("R/24h", "", 4.5), ("Stack", "l", 7),
                ("Risk %", "", 5), ("R", "", 4.5), ("Costs $", "", 5),
                ("P&amp;L $", "", 5.5), ("Reason", "l", 8), ("MF", "l", 5.5)]
    elif contracts and micro:
        # Stack, actual risk % and costs are the subject of the page, so
        # the price columns each give up a little width; sums to 100.
        cols = [("Market", "l", 8), ("Side", "l", 4.5),
                ("In (UTC)", "l", 10.5), ("Out (UTC)", "l", 10.5),
                ("Held", "", 4.5), ("In", "", 6.5), ("Out", "", 6.5),
                ("Stop", "", 6.5), ("R/24h", "", 5), ("Stack", "l", 8),
                ("Risk %", "", 5), ("R", "", 5), ("Costs $", "", 5.5),
                ("P&amp;L $", "", 6), ("Reason", "l", 8)]
    elif contracts:
        # The extra column is the whole point of a contracts page, so the
        # others each give up a little width; still sums to 100.
        cols = [("Market", "l", 9), ("Side", "l", 5), ("In (UTC)", "l", 12),
                ("Out (UTC)", "l", 12), ("Held", "", 5.5), ("In", "", 7.5),
                ("Out", "", 7.5), ("Stop", "", 7.5), ("R/24h", "", 6),
                ("Ctr", "", 5), ("R", "", 5.5), ("P&amp;L $", "", 7.5),
                ("Reason", "l", 10)]
    else:
        cols = [("Market", "l", 10), ("Side", "l", 5),
                ("In (UTC)", "l", 12.5), ("Out (UTC)", "l", 12.5),
                ("Held", "", 5.5), ("In", "", 8), ("Out", "", 8),
                ("Stop", "", 8), ("R/24h", "", 6), ("R", "", 5.5),
                ("P&amp;L $", "", 7.5), ("Reason", "l", 11.5)]
    head = "".join(
        f'<th class="{c} sortable" data-i="{i}" style="width:{w}%">{lab}'
        f'<span class="ar"></span></th>'
        for i, (lab, c, w) in enumerate(cols))
    # THE DENSE CONTRACTS BLOTTER WRAPS ITS TEXT CELLS (Lode, 2026-09-03
    # evening: "view in the browser whether the spacing works out"): at
    # fifteen or sixteen fixed-layout columns a timestamp no longer fits
    # its column on one line and ran into its neighbour, and "Day-2
    # settlement" ran into the MF cell. The stylesheet's cells default
    # to nowrap and OVERFLOW rather than wrap; `wrap` opts a cell back
    # in, so the date sits over its time and the reason takes two lines
    # where it must. The fractional blotter (twelve columns) fits as is.
    wrap = " wrap" if contracts else ""
    rows = []
    for t in sorted(range(len(trades)), key=lambda k: trades[k]["entry_ts"]):
        tr = trades[t]
        m = money_of[t]
        mins = ((pd.Timestamp(tr["exit_ts"]) - pd.Timestamp(tr["entry_ts"]))
                .total_seconds() / 60.0)
        link = links.get(tr["market"])
        name = esc(tr["market"])
        # The geometry ratio the adopted cut decides on; a trade whose 24h
        # window was too short to judge has none and sorts below the rest.
        ratio = tr.get("rpu_range_ratio")
        ratio_txt = f"{ratio:.2f}" if ratio is not None else "&mdash;"
        cell = (f'<a href="{link[0]}{study_t(link, t)}" target="_blank" '
                f'title="{esc(link[2])}, {study_title(link, t)}">'
                f'{name}</a>') if link else name
        if contracts and micro:
            # The STACK (n full + k micro), the risk the whole stack
            # actually took of equity at entry, and the costs it rang up
            # (both legs' round turns plus the measured entry drift,
            # split in the tooltip). A refused order is not here at all.
            stack = " + ".join(
                ([f'{m["n"]} {tr["market"]}'] if m["n"] else [])
                + ([f'{m["k"]} {m["root"]}'] if m["k"] else []))
            drift = m.get("drift_usd", 0.0)
            costs = m["cost_full_rt"] + m["cost_micro_rt"] + drift
            stack_tip = (
                f'risk ${m["risk_usd"]:,.0f} = {m["risk_pct"]:.2f}% of '
                f'equity at entry; ${m["full_risk"]:,.0f} per full contract'
                + (f'; micro stop rounded to {m["root"]}\'s grid: '
                   f'{m["rpu_m"]:g}/unit against the parent\'s '
                   f'{tr["rpu"]:g}' if m["k"] else '; no micro leg'))
            cost_tip = (
                f'full leg round turn ${m["cost_full_rt"]:,.2f}; micro leg '
                f'round turn ${m["cost_micro_rt"]:,.2f}; measured entry '
                f'drift '
                + (f'{"paid" if drift > 0 else "received"} '
                   f'${abs(drift):,.2f}' if drift else 'none'))
            ctr_cell = (
                f'<td class="l mono" data-s="{m["n"] * 1000 + m["k"]}" '
                f'title="{stack_tip}">{esc(stack)}</td>'
                f'<td class="mono" data-s="{m["risk_pct"]:.3f}">'
                f'{m["risk_pct"]:.2f}%</td>')
            # A received drift larger than the fees is a net CREDIT and
            # prints green with its sign, never "$-9.05" in red.
            cost_cell = (f'<td class="mono {cls(-costs)}" '
                         f'data-s="{costs:.2f}" title="{cost_tip}">'
                         f'{signed_money(-costs) if costs < 0 else money(costs)}'
                         f'</td>')
        elif contracts:
            # The cell says how many; the tooltip carries the money behind
            # it, plus the ETF's locked notional -- the number the
            # futures-only decision reads. (An entry the budget could not
            # size is not here at all: refused orders have their own
            # table.)
            tip = (f'risk ${m["risk_usd"]:,.0f} = {m["risk_pct"]:.2f}% '
                   f'(${m["per_unit"]:,.0f}/contract); round-turn cost '
                   f'${m["cost_rt"]:,.2f}')
            if m.get("etf"):
                tip += (f'; {m["n"]:,} shares locking '
                        f'${m["locked_usd"]:,.0f} = {m["locked_pct"]:.0f}% '
                        f'of the account')
            ctr_cell = (f'<td class="mono" data-s="{m["n"]}" '
                        f'title="{tip}">{m["n"]:,}</td>')
            cost_cell = ""
        else:
            ctr_cell = cost_cell = ""
        rows.append(
            f'<tr>'
            f'<td class="l" data-s="{name}">{cell}</td>'
            f'<td class="l" data-s="{tr["side"]}">{tr["side"]}</td>'
            f'<td class="l mono{wrap}" data-s="{tr["entry_ts"]}">'
            f'{stamp(tr["entry_ts"])}</td>'
            f'<td class="l mono{wrap}" data-s="{tr["exit_ts"]}">'
            f'{stamp(tr["exit_ts"])}</td>'
            f'<td class="mono" data-s="{mins:.0f}">{held(mins)}</td>'
            f'<td class="mono" data-s="{tr["entry"]}">{price(tr["entry"])}</td>'
            f'<td class="mono" data-s="{tr["exit"]}">{price(tr["exit"])}</td>'
            f'<td class="mono" data-s="{tr["stop"]}">{price(tr["stop"])}</td>'
            f'<td class="mono" data-s="{ratio if ratio is not None else -1}">'
            f'{ratio_txt}</td>'
            f'{ctr_cell}'
            f'<td class="mono {cls(tr["net_r"])}" data-s="{tr["net_r"]}">'
            f'{signed(tr["net_r"])}</td>'
            f'{cost_cell}'
            f'<td class="mono {cls(m["pnl_usd"])}" data-s="{m["pnl_usd"]:.2f}">'
            f'{signed_money(m["pnl_usd"])}</td>'
            f'<td class="l{wrap}" data-s="{tr["reason"]}">'
            f'{REASON_TEXT.get(tr["reason"], tr["reason"])}</td>'
            + (mf_cell(tr["market"]) if mf else "")
            + f'</tr>')
    return (f'<div class="tradecard"><div class="tradescroll">'
            f'<table class="trades" data-sort="2" data-dir="1">'
            f'<thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></div>')


# The MIC codes the definitions carry, in the venue-family form Lode
# asked the arsenal to show (2026-09-02). CME's four exchanges all
# trade on Globex, hence one family. Shared with the capital ladder.
EXCHANGE_LABEL = {"XCME": "CME/GLBX", "XCEC": "COMEX/GLBX",
                  "XNYM": "NYMEX/GLBX", "XCBT": "CBOT/GLBX",
                  "IFUS": "ICE/IFUS", "XEUR": "Eurex",
                  "ARCA/NYSE": "NYSE Arca"}


def open_cost(key):
    """USD cost of OPENING one contract (one side), from the sourced
    execution-cost table; None where the row has no source."""
    try:
        return execution_costs.cost_per_side(key, 1, eurusd=sizing.EURUSD)
    except (KeyError, ValueError):
        return None


def tick_cell(v):
    # plain decimals, never scientific: MJY's 0.000001 must not print
    # as 1e-06
    if v is None:
        return "&mdash;"
    return f"{v:.7f}".rstrip("0").rstrip(".") if v < 0.001 else f"{v:g}"


def arsenal_status_html(taken_by_market, refused_by_market, tested,
                        route, count_note=""):
    """THE CONTRACT ARSENAL ON THE CONTRACTS PAGES (Lode, 2026-09-03):
    all 25 Socrates markets in subscription order, each with its front
    contract and a STATUS -- traded on this page, in the arsenal but no
    trade in the window, not backtested (and why), not tradable (and
    why) -- plus which micro the page routes to and why not where it
    does not. It replaces the "Not tested" list under By market, which
    only confused once the universe had two definitions: the engine's
    human filter and the live universe the account trades. Every
    reason is DERIVED from the lists in code (run_1m.HUMAN_APPROVED,
    run_1m.ELIGIBLE_FUTURES, research_1m_sizing.LIVE_UNIVERSE, the
    spec table, the fee table), never typed per market."""
    payload = json.loads(
        (HERE / ".." / "data_center" / "metadata" / "contract_specs.json")
        .read_text(encoding="utf-8"))
    specs = payload["markets"]
    fronts = {r["key"]: r for r in payload["sizing"]}
    micros_of = {}
    for m in payload["micros"]:
        micros_of.setdefault(m["parent"], []).append(m)

    def whole(v):
        return f"{v:,.0f}" if v else "&mdash;"

    def cost_cell(v):
        return f"{v:,.2f}" if v is not None else "&mdash;"

    def micro_cell(key):
        r = (route or {}).get(key)
        if r:
            return (f'<b>{esc(r["root"])}</b> (1/{round(1 / r["fraction"])})',
                    "")
        verified = [m for m in micros_of.get(key, [])
                    if m.get("listed") == "VERIFIED"]
        if not verified:
            yields = [m for m in micros_of.get(key, [])
                      if m.get("listed") == "YES"]
            if yields:
                return ("&mdash;", "yield-quoted micro only, a different "
                        "product (not comparable)")
            return ("&mdash;", "no micro exists")
        sourced = [m for m in verified
                   if open_cost(m["symbol"]) is not None]
        if sourced:
            return ("&mdash;", f'{esc(", ".join(m["symbol"] for m in sourced))}'
                    f' verified and priced, not routed: no entry minute'
                    f' measured in the micro study')
        return ("&mdash;", f'{esc(", ".join(m["symbol"] for m in verified))}'
                f' verified but its fee row has no source; refused to'
                f' price')

    rows, n_traded, n_arsenal = [], 0, 0
    for m in run_1m.MAPPING["markets"]:
        key = m.get("key") or "JGB"
        s = specs.get(key, {})
        f = fronts.get(key)
        name = s.get("market") or m.get("socrates_name", key)
        exch = EXCHANGE_LABEL.get(s.get("exchange"), s.get("exchange"))
        size = (f'{s["unit_qty"]:,.0f} {s["unit"]}'
                if s.get("unit_qty") else "&mdash;")
        micro, micro_why = micro_cell(key)
        n_taken = taken_by_market.get(key, 0)
        n_ref = refused_by_market.get(key, 0)
        if key not in sizing.LIVE_UNIVERSE:
            live = False
            if s.get("type") == "etf":
                status, why = ("Not tradable",
                               "ETF: a share position pays full notional "
                               "with no leverage, so risking 1% locks the "
                               "account (over 100% on 5 of 12 historical "
                               "ETF trades, at any account size)")
            else:
                status, why = ("Not tradable",
                               "outside our data: no Databento OSE coverage "
                               "(the known gap; IBKR backfill later)")
            micro, micro_why = "&mdash;", ""
        else:
            live = True
            n_arsenal += 1
            if key in tested:
                if n_taken:
                    n_traded += 1
                    status = f"<b>Traded</b>, {n_taken} trade" + (
                        "s" if n_taken != 1 else "")
                    why = ("" if not n_ref else
                           f"{n_ref} more refused at placement")
                else:
                    status = "In arsenal, no trade"
                    why = ("no setup qualified in the window" if not n_ref
                           else f"{n_ref} refused at placement, none "
                                f"taken")
            elif key not in run_1m.ELIGIBLE_FUTURES:
                status, why = ("Not backtested",
                               "no 1-minute bars in data_center yet")
            elif key not in run_1m.HUMAN_APPROVED:
                status, why = ("Not backtested",
                               "failed the human market filter (audit "
                               "s.16); lifting it is a strategy-level "
                               "decision")
            else:
                status, why = "Not backtested", "not in this run"
        tone = ("pos" if n_taken else "" if live else "neg")
        rows.append(
            f'<tr class="{"arsenal-out" if not live else ""}">'
            f'<td class="l"><b>{esc(key)}</b></td>'
            f'<td class="l wrap">{esc(name)}</td>'
            f'<td class="l">{esc(exch) if exch else "&mdash;"}</td>'
            f'<td class="l mono wrap">{esc(f["front"]) if f else "&mdash;"}'
            f'</td>'
            f'<td class="l">{size}</td>'
            f'<td class="mono">{tick_cell(s.get("tick"))}</td>'
            f'<td class="mono">{cost_cell(open_cost(key)) if live else "&mdash;"}'
            f'</td>'
            f'<td class="l" title="{micro_why}">{micro}</td>'
            f'<td class="l {tone}">{status}</td>'
            f'<td class="l wrap">{why or micro_why}</td>'
            f'</tr>')
    head = ('<tr><th class="l" style="width:4.5%">Key</th>'
            '<th class="l" style="width:19%">Market</th>'
            '<th class="l" style="width:8.5%">Exchange</th>'
            '<th class="l" style="width:7%">Contract</th>'
            '<th class="l" style="width:9.5%">Size</th>'
            '<th style="width:5.5%">Tick</th>'
            '<th style="width:6.5%">Open 1 ctr $</th>'
            '<th class="l" style="width:8%">Micro</th>'
            '<th class="l" style="width:10.5%">Status</th>'
            '<th class="l" style="width:21%">Why</th></tr>')
    routed = ", ".join(f"{k}&rarr;{r['root']}"
                       for k, r in sorted((route or {}).items()))
    return (
        '<div class="section-h">The contract arsenal</div>'
        f'<p class="chartnote">All <b>{len(rows)} Socrates markets</b> we '
        f'subscribe to, in subscription order. <b>{n_arsenal}</b> are the '
        f'arsenal, the live universe the account trades; <b class="pos">'
        f'{n_traded} traded on this page</b> (green status), the rest of '
        f'the arsenal either had no qualifying setup in the window or was '
        f'never backtested, and the greyed rows cannot be traded with '
        f'this strategy at all. <b>Micro</b> is the contract this page '
        f'tops positions up with'
        + (f' ({routed})' if routed else '')
        + '; a dash carries its reason in the Why column or on hover. '
        '<b>Open 1 ctr $</b> is one side&rsquo;s commission + exchange + '
        'NFA from execution_costs.py. Every status is derived from the '
        'lists in code (the human market filter, the engine&rsquo;s bar '
        'coverage, the live universe, the spec and fee tables), never '
        'typed per market.' + count_note + '</p>'
        f'<div class="tradecard"><table class="trades"><thead>{head}'
        f'</thead><tbody>{"".join(rows)}</tbody></table></div>')


def markets_html(rows, excluded, links):
    cols = [("Market", "l", 26), ("Trades", "", 9), ("Win %", "", 9),
            ("Net R", "", 10), ("Stops", "", 9), ("Aborts", "", 9),
            ("Settlement", "", 12), ("Return %", "", 16)]
    head = "".join(
        f'<th class="{c} sortable" data-i="{i}" style="width:{w}%">{lab}'
        f'<span class="ar"></span></th>'
        for i, (lab, c, w) in enumerate(cols))
    body = []
    for r in rows:
        key = r["market"]
        link = links.get(key)
        name = (f'<a href="{link[0]}" target="_blank" '
                f'title="{esc(link[2])} in the 1m study">{esc(key)}</a>'
                if link else esc(key))
        note = r.get("note", "")
        # The note is a DATA provenance line ("futures, frozen calendar" is
        # data_center's roll calendar, not an obsolete market), so it belongs
        # in the tooltip. The tag says only what the instrument is.
        tag = '<span class="tag">ETF</span>' if note.startswith("ETF") else ""
        wr = r["win_rate"]
        body.append(
            f'<tr>'
            f'<td class="l" data-s="{esc(key)}" title="{esc(note)}">'
            f'{name}{tag}</td>'
            f'<td class="mono" data-s="{r["trades"]}">{r["trades"]}</td>'
            f'<td class="mono" data-s="{wr if wr is not None else -1}">'
            f'{f"{wr:.0f}%" if wr is not None else "&mdash;"}</td>'
            f'<td class="mono {cls(r["net_r_total"])}" '
            f'data-s="{r["net_r_total"]}">{signed(r["net_r_total"])}</td>'
            f'<td class="mono" data-s="{r["reasons"]["stop"]}">'
            f'{r["reasons"]["stop"]}</td>'
            f'<td class="mono" data-s="{r["reasons"]["no_confirm"]}">'
            f'{r["reasons"]["no_confirm"]}</td>'
            f'<td class="mono" data-s="{r["reasons"]["close1"]}">'
            f'{r["reasons"]["close1"]}</td>'
            f'<td class="mono {cls(r["return_pct"])}" '
            f'data-s="{r["return_pct"]}">{signed(r["return_pct"])}%</td>'
            f'</tr>')
    out = (f'<div class="tradecard"><div class="tradescroll">'
           f'<table class="trades" data-sort="3" data-dir="-1">'
           f'<thead><tr>{head}</tr></thead>'
           f'<tbody>{"".join(body)}</tbody></table></div></div>')
    if excluded:
        items = "".join(
            f'<tr><td class="l">{esc(e["market"])}</td>'
            f'<td class="l wrap">{esc(e.get("reason", ""))}</td></tr>'
            for e in excluded)
        out += (f'<div class="tradecard"><table class="trades">'
                f'<thead><tr><th class="l" style="width:20%">Not tested</th>'
                f'<th class="l" style="width:80%">Why</th></tr></thead>'
                f'<tbody>{items}</tbody></table></div>')
    return out


def calendar_html(days, eq, dd, openpos, trades, money_of):
    """One row per MARKET DAY that did something (see daily_series).

    Activity is filed under the same grid day the money is, through
    run_1m.place - keying it on the trade's own date instead would hide a
    Sunday-night stop whose P&L is nevertheless in Monday's capital
    column, and this table is read against that column.
    """
    grid = [date.fromisoformat(d) for d in days]
    ins, outs = {}, {}
    for i, t in enumerate(trades):
        ins.setdefault(
            run_1m.place(pd.Timestamp(t["entry_ts"]).date(), grid),
            []).append(i)
        outs.setdefault(
            run_1m.place(pd.Timestamp(t["exit_ts"]).date(), grid),
            []).append(i)
    rows = []
    for gi, (d, e, drop, op) in enumerate(zip(days, eq, dd, openpos)):
        if gi not in ins and gi not in outs and op == 0:
            continue
        acts = []
        for i in ins.get(gi, []):
            acts.append(f'<span style="color:var(--opened)">opened '
                        f'{esc(trades[i]["market"])} {trades[i]["side"]}'
                        f'</span>')
        for i in outs.get(gi, []):
            t = trades[i]
            acts.append(f'<span style="color:var(--closed)">closed '
                        f'{esc(t["market"])} {signed(t["net_r"])}R '
                        f'{signed_money(money_of[i]["pnl_usd"])}</span>')
        rows.append(
            f'<tr><td class="l mono">{d}</td>'
            f'<td class="mono">{money(e)}</td>'
            f'<td class="mono">{drop:.2f}%</td>'
            f'<td class="mono">{op}</td>'
            f'<td class="l act">{" &middot; ".join(acts) or "&mdash;"}</td>'
            f'</tr>')
    return (f'<div class="tradecard"><div class="tradescroll">'
            f'<table class="trades"><thead><tr>'
            f'<th class="l" style="width:11%">Date</th>'
            f'<th style="width:12%">Capital</th>'
            f'<th style="width:9%">Drawdown</th>'
            f'<th style="width:7%">Open</th>'
            f'<th class="l" style="width:61%">Activity</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div></div>')


PAGE_JS = r"""<script>
// Two small things only: the three panes, and a table sorter. Everything
// else on this page is rendered server-side, because quickfix1m1dc is
// outside the registry and there is no variant grid to replay.
(function () {
  function cssv(n) {
    return getComputedStyle(document.documentElement)
      .getPropertyValue(n).trim();
  }
  function opts() {
    return {
      layout: { background: { color: cssv('--surface') },
                textColor: cssv('--ink2'), attributionLogo: false },
      grid: { vertLines: { color: cssv('--grid') },
              horzLines: { color: cssv('--grid') } },
      rightPriceScale: { borderColor: cssv('--border') },
      timeScale: { borderColor: cssv('--border') },
    };
  }
  function pct(v) { return v.toFixed(2) + '%'; }
  var panes = [];
  function mk(id, data, addSeries) {
    var el = document.getElementById(id);
    // Height minus slack: the time-axis label row clips when the canvas
    // fills the container exactly (seen in Chrome, headless and normal).
    var c = LightweightCharts.createChart(el, Object.assign(
      { width: el.clientWidth, height: el.clientHeight - 18 }, opts()));
    var s = addSeries(c);
    s.setData(data);
    var by = {};
    data.forEach(function (d) { by[d.time] = d.value; });
    panes.push({ el: el, chart: c, series: s, by: by });
  }
  // STEP LINES, not joined dots (Lode, 2026-08-18). The balance stands
  // still until a trade closes and then jumps, so it is held flat from one
  // market day to the next and the whole move is the vertical there. A
  // sloped line between two exits eleven days apart draws eleven days of
  // gain that nothing booked.
  var STEP = LightweightCharts.LineType.WithSteps;
  // One entry per ACCOUNT on the page (the contracts pages carry two
  // since 2026-09-03: no-stop above, stopped below; every other page
  // one). All panes of all accounts share one time axis and one
  // crosshair, since they are drawn on the same market days. The
  // contracts pages also carry a second sizing (full contracts only)
  // as a thin gray reference behind the combined stack, like the
  // capital ladder; those series are empty on every other page.
  var SECTIONS = __SECTIONS__;
  SECTIONS.forEach(function (s) {
    mk('eq' + s.sfx, s.eq, function (c) {
      if (s.eqf.length) {
        c.addLineSeries({ color: cssv('--ink3'), lineWidth: 1,
          lineType: STEP, priceLineVisible: false,
          lastValueVisible: false }).setData(s.eqf);
      }
      return c.addLineSeries({ color: cssv('--accent-line'), lineWidth: 2,
        lineType: STEP });
    });
    mk('ddc' + s.sfx, s.ddc, function (c) {
      if (s.ddf.length) {
        c.addLineSeries({ color: cssv('--ink3'), lineWidth: 1,
          lineType: STEP, priceLineVisible: false,
          lastValueVisible: false,
          priceFormat: { type: 'custom', formatter: pct } }).setData(s.ddf);
      }
      return c.addLineSeries({ color: cssv('--neg'), lineWidth: 1,
        lineType: STEP,
        priceFormat: { type: 'custom', formatter: pct } });
    });
    mk('op' + s.sfx, s.op, function (c) {
      // Positions are counted, in or out: the scale steps in INTEGERS
      // (minMove 1), so the thin gray gridlines land on whole numbers
      // and never on a 2.50 nobody can hold (Lode, 2026-09-02).
      return c.addHistogramSeries({ color: cssv('--bars'),
        priceFormat: { type: 'price', precision: 0, minMove: 1 } });
    });
  });
  // One label column for all panes: force every price scale to the widest
  // one, so the time axes, and with them the month ticks, sit exactly
  // under each other instead of shifting with each pane's own labels.
  function alignAxes() {
    var w = 0;
    panes.forEach(function (p) {
      w = Math.max(w, p.chart.priceScale('right').width());
    });
    panes.forEach(function (p) {
      p.chart.applyOptions({ rightPriceScale: { minimumWidth: w } });
    });
  }
  function resize() {
    panes.forEach(function (p) {
      p.chart.resize(p.el.clientWidth, p.el.clientHeight - 18);
    });
    alignAxes();
  }
  window.addEventListener('resize', resize);
  panes.forEach(function (p) {
    p.chart.timeScale().subscribeVisibleLogicalRangeChange(function (r) {
      if (!r) return;
      panes.forEach(function (q) {
        if (q !== p) q.chart.timeScale().setVisibleLogicalRange(r);
      });
    });
    p.chart.timeScale().fitContent();
  });
  // One cursor over all panes: moving it in any pane places the
  // crosshair on the same day in the others, each labelling its own
  // value on its own axis. Programmatic placement does not re-fire
  // crosshairMove, so this cannot loop.
  function tkey(t) {
    if (typeof t === 'string') return t;
    if (t && t.year !== undefined) {
      return t.year + '-' + ('0' + t.month).slice(-2)
        + '-' + ('0' + t.day).slice(-2);
    }
    return String(t);
  }
  panes.forEach(function (p) {
    p.chart.subscribeCrosshairMove(function (param) {
      panes.forEach(function (q) {
        if (q === p) return;
        var v = param.time === undefined ? undefined : q.by[tkey(param.time)];
        if (v === undefined) q.chart.clearCrosshairPosition();
        else q.chart.setCrosshairPosition(v, param.time, q.series);
      });
    });
  });
  requestAnimationFrame(alignAxes);
  // The canvas keeps whatever colours it was built with, so the print
  // stylesheet's forced light palette would not reach it. Re-read the
  // variables on both events; print resolves them against the print CSS.
  function retheme() { panes.forEach(function (p) { p.chart.applyOptions(opts()); }); }
  window.addEventListener('beforeprint', retheme);
  window.addEventListener('afterprint', retheme);
  if (window.matchMedia) {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    if (mq.addEventListener) mq.addEventListener('change', retheme);
  }

  // Sorter: every cell carries data-s, so a column sorts on its own value
  // rather than on the formatted text (dates, R, dollars all differ).
  document.querySelectorAll('table.trades').forEach(function (tbl) {
    var body = tbl.tBodies[0];
    if (!body) return;
    var key = Number(tbl.dataset.sort), dir = Number(tbl.dataset.dir) || 1;
    function val(row, i) {
      var td = row.cells[i];
      var s = td ? (td.dataset.s !== undefined ? td.dataset.s
                    : td.textContent) : '';
      var n = parseFloat(s);
      return (s !== '' && !isNaN(n) && /^[-+0-9.eE]+$/.test(s)) ? n : s;
    }
    function apply() {
      var rows = Array.prototype.slice.call(body.rows);
      rows.sort(function (a, b) {
        var x = val(a, key), y = val(b, key);
        if (x === y) return 0;
        return (x > y ? 1 : -1) * dir;
      });
      rows.forEach(function (r) { body.appendChild(r); });
      tbl.querySelectorAll('th').forEach(function (th) {
        th.classList.remove('sorted');
        var ar = th.querySelector('.ar');
        if (ar) ar.textContent = '';
      });
      var th = tbl.querySelector('th[data-i="' + key + '"]');
      if (th) {
        th.classList.add('sorted');
        var ar = th.querySelector('.ar');
        if (ar) ar.textContent = dir > 0 ? '▲' : '▼';
      }
    }
    tbl.querySelectorAll('th.sortable').forEach(function (th) {
      th.addEventListener('click', function () {
        var i = Number(th.dataset.i);
        if (i === key) { dir = -dir; } else { key = i; dir = 1; }
        apply();
      });
    });
    if (!isNaN(key)) apply();
  });
})();
</script>"""


# One ACCOUNT block: everything a trade list's shared account renders.
# The fractional pages render it once; the contracts pages render it
# twice (no-stop first, then stopped), which is why the pane ids carry
# a suffix and the heading is optional.
ACCOUNT = r"""<div class="acct" id="acct__SFX__">
__HEAD__
<div class="kpis">__KPIS__</div>
<div class="stats4">__STATS__</div>
<div class="card">
  <div class="charthead"><div class="t">__CARDT__</div>
  <div class="s">__CHARTSUB__</div></div>
  <div class="panelbl">__PANE_EQ__</div><div id="eq__SFX__" class="pane-eq"></div>
  <div class="panelbl">__PANE_DD__</div>
  <div id="ddc__SFX__" class="pane-dd"></div>
  <div class="panelbl">Open positions</div><div id="op__SFX__" class="pane-op"></div>
</div>
<div class="note">__NOTE__</div>
<div class="section-h">Where the trades end</div>
<div class="tradecard"><table class="trades"><thead><tr>
  <th class="l" style="width:20%">Exit class</th>
  <th style="width:9%">Trades</th>
  <th style="width:9%">%</th><th style="width:11%">__CLASS_NET__</th>
  <th style="width:9%">__CLASS_AVG__</th>
  <th class="l wrap" style="width:42%">What it means</th>
</tr></thead><tbody>__CLASSES__</tbody></table></div>
__REFUSED__
__OPEN__
<div class="section-h">All trades</div>
<p class="chartnote">__BLOTNOTE__</p>
__BLOTTER__
<div class="section-h">By market</div>
<p class="chartnote">__MKTNOTE__</p>
__MARKETS__
<div class="section-h">Daily calendar</div>
<p class="chartnote">Every <b>market day</b> that opened, closed or carried a
position.
<b style="color:var(--opened)">Purple</b> is a position opened,
<b style="color:var(--closed)">blue</b> one closed. Capital is the shared
account at the end of that day; drawdown is the worst it reached at any
trade close during it, which is why a day can close higher than it
dug.</p>
__CALENDAR__
</div>"""


PAGE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NAME__ &mdash; 1-minute report</title>
__CSS__
<style>
/* the three panes; the daily reports draw their own SVG, this page uses
   lightweight-charts, so the containers need explicit heights */
.pane-eq{height:330px}.pane-dd{height:150px}.pane-op{height:130px}
.pane-eq,.pane-dd,.pane-op{margin-bottom:4px}
/* Two accounts on one page (2026-09-03): each opens with a ruled
   heading so the reader always knows which one a table belongs to. */
.acct-h{font-size:19px;margin:40px 2px 6px;padding-top:22px;
  border-top:3px solid var(--border)}
.acct-h .tag{font-size:11px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);font-weight:600;margin-left:10px;vertical-align:middle}
.panelbl{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);font-weight:600;margin:10px 2px 4px}
table.trades td a{color:var(--accent);text-decoration:none;font-weight:600}
table.trades td a:hover{text-decoration:underline}
/* The shared stylesheet caps .chartnote at 78ch, which reads as cut
   off beside full-width tables (Lode, 2026-09-02): on these pages the
   notes run the full column like the lede does. */
.chartnote{max-width:none}
/* The shared .kpis is an auto-fit GRID, which leaves gray cells
   whenever the tile count does not fill the last row. Flex with
   stretching tiles fills every row whatever the count (same Lode
   note: no empty gray fields). */
.kpis{display:flex;flex-wrap:wrap}
.kpis .kpi{flex:1 1 150px}
/* Twelve stat tiles as 3 rows x 4 columns (Lode, 2026-09-02), the
   winner/loser and best/worst pairs sharing one row; the shared
   stylesheet's narrow-screen 2-column rule stays in force below
   641px. */
@media(min-width:641px){.stats4{grid-template-columns:repeat(4,1fr)}}
/* the contract arsenal: markets outside the trading universe are
   greyed so the traded rows stand out (Lode, 2026-09-03) */
tr.arsenal-out td{color:var(--ink3)}
table.trades td.pos b{color:var(--pos)}
@media print{.pane-eq{height:300px}.pane-dd,.pane-op{height:120px}
  .acct-h{break-before:page}}
</style></head><body>
<div class="wrap">
<header>
  <div class="eyebrow">1-minute workstream</div>
  <h1>__NAME__</h1>
  <p class="lede">__LEDE__</p>
</header>
__RULES__
__ARSENAL__
__ACCOUNTS__
<footer>__FOOTER__</footer>
</div>
<script>__LIB__</script>
__JS__
</body></html>"""


def build_baseline():
    """The published baseline page, sized to a drawdown budget (Lode,
    2026-08-11, audit s.17): risk per trade is SOLVED by bisection so the
    worst drawdown reached at any trade close is 6%, the TARGET_DD the daily
    project publishes at. Re-solved on every build; the page states the
    number. The trade list itself is untouched - risk moves only the
    money columns, never the R columns."""
    data = json.loads(IN_JSON.read_text(encoding="utf-8"))
    risk = solve_risk_pct(data["trades"], 6.0)
    _, _, final, max_dd = replay(data["trades"], risk)
    data["risk_pct"] = risk
    data["params"] = dict(data["params"], risk_pct=risk)
    data["portfolio"].update(final=round(final, 2),
                             max_dd_pct=round(max_dd, 2))
    data["universe_note"] = (
        " <b>This baseline trades the human market filter</b>: the "
        "markets that passed the chart-structure inspection (audit s.16); "
        "the rejected ones are under Not tested with that reason. <b>And "
        "it is sized to a drawdown budget</b>: risk per trade is solved "
        f"to <b>{risk:g}%</b> so the worst drawdown reached at any "
        "trade close is 6%, the daily project's target.")
    build(data=data)


def build_baseline_contracts():
    """The published baseline's trade list in integer contracts. The raw
    blotter at the 1% budget, NOT the fractional page's solved 6%
    sizing: the contracts layer defines its own money and solving a
    drawdown on top of it would conflate two questions. Its no-stop
    account is the matrix's companion of the baseline cell, crosschecked
    against this blotter so the two accounts cannot come from different
    data windows."""
    data = json.loads(IN_JSON.read_text(encoding="utf-8"))
    data["universe_note"] = (
        " <b>The engine behind this page ran the human market "
        "filter</b>: the markets that passed the chart-structure "
        "inspection (audit s.16); the contract arsenal below names the "
        "live-universe markets that filter left out.")
    build(data=data, contracts=True,
          nostop=companion_payload(run_1m_matrix.BASELINE_NAME, "no-stop",
                                   check_against=data["trades"]))


def variant_payload(name):
    """A blotter-shaped payload for one cell of run_1m_matrix.py.

    The matrix already ran every dial combination over one data load, so a
    variant report costs no backtest: its trades, per-market rows and
    exclusions are all in the matrix JSON. Only the published baseline
    goes through run_1m.py, because that run is also what charter's trade
    study reads.
    """
    m = json.loads(MATRIX_JSON.read_text(encoding="utf-8"))
    if name not in m["variants"]:
        raise SystemExit(f"{name} is not in the matrix "
                         f"({', '.join(m['variants'])})")
    v = m["variants"][name]
    trades = sorted(m["trades"][name], key=lambda t: t["entry_ts"])
    return dict(
        strategy=f"quickfix1m1dc [{name}]",
        # charter's study keys its variant trade lists on this slug, and
        # every blotter link on the page carries it in ?v=.
        slug=v.get("slug") or run_1m_matrix.variant_slug(name),
        params=dict(m["params"], activation_utc="07:35",
                    stop="see stop_mode", **v["dials"]),
        portfolio=dict(final=v["final_cash"], max_dd_pct=v["max_dd_pct"],
                       trades=v["trades"], win_rate=v["win_rate"],
                       net_r=v["net_r"]),
        markets=m["per_market"][name], excluded=m.get("excluded", []),
        # The matrix ran every market, so its calendar is the same one the
        # baseline page is drawn on - a variant page and the published one
        # end on the same market day even when their last trades differ.
        calendar=m.get("calendar"),
        # One open-position list per cell since 2026-08-30; a matrix JSON
        # from before then has no key, and .get(name) then omits the
        # section rather than printing a false "none open".
        open_positions=m.get("open_positions", {}).get(name),
        trades=trades)


COMPANION_TAGS = ("no-stop", "no-mf", "no-mf no-stop")


def companion_payload(name, tag, check_against=None):
    """A COMPANION of a cell, blotter-shaped, from the matrix JSON's
    `companions` block (run_1m_matrix.COMPANIONS, 2026-09-03): the cell's
    dials with `stop_live` off (`no-stop`), on the unfiltered universe
    (`no-mf`), or both (`no-mf no-stop`), run in the matrix pass beside
    the cell. None - with a printed NOTE, never a silent empty section -
    when the matrix JSON predates the companions.

    `check_against` is the STOPPED trade list this page renders (the
    published blotter on the baseline page); it is crosschecked against
    the matrix's own cell trade for trade, so the two accounts on one
    page can never quietly come from different data windows or dials.
    """
    m = json.loads(MATRIX_JSON.read_text(encoding="utf-8"))
    block = m.get("companions", {}).get(name, {}).get(tag)
    if block is None:
        print(f"NOTE: {MATRIX_JSON.name} carries no `{tag}` companion for "
              f"{name} -- rebuild the matrix (run_1m_matrix.py) for it")
        return None
    if check_against is not None:
        mine = [run_1m_matrix.comparable(t) for t in
                sorted(check_against, key=lambda t: t["entry_ts"])]
        theirs = [run_1m_matrix.comparable(t) for t in
                  sorted(m["trades"][name], key=lambda t: t["entry_ts"])]
        if mine == theirs:
            print(f"crosscheck: the blotter == matrix {name}, "
                  f"{len(mine)} trades")
        else:
            print(f"WARNING: the blotter and matrix {name} disagree "
                  f"({len(mine)} vs {len(theirs)} trades) -- the no-stop "
                  f"account may come from a different data window; rerun "
                  f"run_1m.py and run_1m_matrix.py together")
    v = m["variants"][name]
    label = {"no-stop": "no stop order",
             "no-mf": "without market filter",
             "no-mf no-stop": "without market filter, no stop order"}[tag]
    return dict(
        strategy=f"quickfix1m1dc [{name}, {label}]",
        # THE COMPANION'S OWN SLUG (2026-09-03 evening, Lode: the rows
        # must link to the 1-minute chart): charter's study ships every
        # companion list beside the cells, keyed by this slug, so a row
        # here opens ITS OWN trade - including on the markets the cells
        # never traded. (Until then a companion's rows went through the
        # cell's trade sharing the entry minute, which had nothing to
        # point at on those markets.)
        slug=block.get("slug") or (run_1m_matrix.variant_slug(name)
                                   + "_" + tag.replace("-", "_")
                                   .replace(" ", "_")),
        filter_lifted="no-mf" in tag,
        params=dict(m["params"], activation_utc="07:35",
                    stop="see stop_mode", **block["dials"]),
        portfolio=dict(final=block["final_cash"],
                       max_dd_pct=block["max_dd_pct"],
                       trades=block["trades_n"], win_rate=block["win_rate"],
                       net_r=block["net_r"]),
        markets=block["per_market"], excluded=m.get("excluded", []),
        calendar=m.get("calendar"),
        open_positions=block.get("open_positions"),
        trades=sorted(block["trades"], key=lambda t: t["entry_ts"]))


def entry_keys(trades):
    return {(t["market"], t["entry_ts"]) for t in trades}


def build(data=None, out=None, variant=None, contracts=False, nostop=None,
          without_mf=False):
    """The published baseline by default; one matrix cell when `variant`
    names one, written beside it under its own filename. `contracts`
    swaps the money layer for integer sizing at the test account and the
    page lands under the contracts stem instead - and carries the
    NO-STOP account above the stopped one (`nostop`, a payload from
    companion_payload; looked up for a variant when not given).
    `without_mf` (contracts pages only) builds the cell's `_without_mf`
    page from its no-market-filter companions instead of the cell."""
    if variant:
        if without_mf:
            if not contracts:
                raise SystemExit("without_mf is a contracts-page build")
            data = companion_payload(variant, "no-mf")
            if data is None:
                raise SystemExit(f"no `no-mf` companion for {variant}")
            nostop = companion_payload(variant, "no-mf no-stop")
        else:
            data = variant_payload(variant)
            if contracts and nostop is None:
                nostop = companion_payload(variant, "no-stop")
        # The matrix names its own cells, so it owns the filename form too
        # ("variant 5" -> quickfix1m1dc_report_variant_05.html). A page
        # built here can then never land under a name the matrix does not
        # use.
        # REPORT_STEM, never OUT_HTML.stem: the baseline's own name now
        # carries a slug, so stem-chaining would spell
        # `..._variant_02_variant_05.html`.
        stem = CONTRACTS_STEM if contracts else REPORT_STEM
        out = OUT_HTML.with_name(
            f"{stem}_{run_1m_matrix.variant_slug(variant)}"
            f"{'_without_mf' if without_mf else ''}.html")
    data = data or json.loads(IN_JSON.read_text(encoding="utf-8"))
    if out is None and contracts:
        out = OUT_HTML.with_name(
            f"{CONTRACTS_STEM}_"
            f"{run_1m_matrix.variant_slug(run_1m_matrix.BASELINE_NAME)}.html")
    out = out or OUT_HTML
    if not contracts:
        nostop = None
    p = data["params"]
    published = data["portfolio"]
    vslug = data.get("slug")
    filter_lifted = bool(data.get("filter_lifted"))
    calendar = data.get("calendar")
    if not calendar:
        calendar = run_1m.calendar_fallback(data["trades"])
        print("WARNING: this JSON predates the market-day calendar. The "
              "panes are drawn on calendar days and stop at the last exit; "
              "re-run the runner that wrote it for the real grid.")

    if contracts:
        start = SIZING_ACCOUNT
        risk = RISK_PCT  # the budget; what each trade REALIZES is below it
        # THE MICRO STACK (Lode, 2026-09-03): full contracts first, the
        # routed micro topping up toward the budget -- the capital
        # ladder's own replay, at the ladder's $250k rung, so the two
        # pages cannot disagree. Full-contracts-only stays on the page
        # as the gray reference; without the gates JSON it is all
        # there is, and the page says so.
        micro = GATES_JSON.exists()
        if micro:
            route, gates = micro_route()
            specs, _ = sizing.load_specs()
        else:
            print("NOTE: no micro gates JSON -- building full-contracts-"
                  "only (run research_1m_micro.py for the micro stack)")
            route = gates = specs = None
    else:
        start = PAGE_START
        risk = data.get("risk_pct", RISK_PCT)
        micro, route, gates, specs = False, None, None, None

    def live(payload):
        """THE LIVE UNIVERSE ONLY (Lode, 2026-09-01: "we only trade the
        22 markets"). ETF and non-updated markets' trades are dropped
        before the replay -- exact, since the engine runs markets
        independently. Their rows also leave the per-market table,
        moving to the excluded list with the reason."""
        if not contracts:
            return payload
        dropped = sorted({t["market"] for t in payload["trades"]
                          if t["market"] not in sizing.LIVE_UNIVERSE})
        return dict(
            payload,
            trades=sizing.live_trades(payload["trades"]),
            markets=[r for r in payload["markets"]
                     if r["market"] in sizing.LIVE_UNIVERSE],
            excluded=list(payload.get("excluded", [])) + [
                dict(market=m,
                     reason="outside the live trading universe (ETF or "
                            "not currently updated); not traded, dropped "
                            "before the replay")
                for m in dropped],
            open_positions=(
                None if payload.get("open_positions") is None else
                [o for o in payload["open_positions"]
                 if o["market"] in sizing.LIVE_UNIVERSE]))

    data = live(data)
    nostop = live(nostop) if nostop else None
    # Both accounts draw on ONE grid: from the earlier first entry of the
    # two (they normally share it - nothing can block a first trade).
    first_entry = min(pd.Timestamp(t["entry_ts"]).date()
                      for pl in (data, nostop) if pl
                      for t in pl["trades"])
    stopped_keys = entry_keys(data["trades"])
    nostop_keys = entry_keys(nostop["trades"]) if nostop else set()

    # The MF column rides on the lifted-filter contracts pages, where a
    # row can be either; on the published pages every row would read
    # `passed`, so the column stays off there.
    mf_col = contracts and micro and filter_lifted

    def account(payload, stopped, sfx, links_full):
        """Everything one trade list's shared account renders: the
        replay, the panes' series, and the ACCOUNT block's html. Returns
        (html, series, info) - `info` carries the figures the lede, the
        arsenal and the footer quote."""
        all_trades = trades = payload["trades"]
        refused_map = {}
        if contracts:
            if micro:
                money_of, eod, final, max_dd, refused_map = replay_micro(
                    trades, risk, start, route, specs, gates["per_entry"])
                r_full = replay_contracts(trades, risk, start)
            else:
                money_of, eod, final, max_dd, refused_map = \
                    replay_contracts(trades, risk, start)
                r_full = None
            # The fractional replay at the SAME account is this page's
            # yardstick: the published figures live on the fractional
            # pages and are a different bet size, so comparing to them
            # would only measure the account, not the quantization and
            # the refusals.
            _, _, ideal_final, ideal_dd = replay(trades, risk, start)
            # Every statistic, pane and table below counts the TAKEN
            # trades only -- a refused order is not a trade. The refused
            # entries get their own table, with charter links numbered
            # against the FULL blotter (which is the list charter holds).
            orig_idx = [i for i in range(len(all_trades))
                        if i not in refused_map]
            if not orig_idx:
                raise SystemExit(
                    f"every trade was refused at ${start:,.0f} / {risk:g}%"
                    f" -- no page to build at this account")
            trades = [all_trades[i] for i in orig_idx]
            money_of = {n: money_of[o] for n, o in enumerate(orig_idx)}
        else:
            money_of, eod, final, max_dd = replay(trades, risk, start)
            ideal_final = ideal_dd = None
            orig_idx = list(range(len(trades)))
            r_full = None
        days, eq, dd, ddc, openpos = daily_series(trades, eod, calendar,
                                                  start, first_entry)
        # The full-contracts-only reference curves (equity and drawdown
        # on closes), drawn thin gray behind the combined stack like the
        # ladder pages do; empty when there is nothing to compare against.
        eq_f, ddc_f = [], []
        if r_full is not None:
            taken_f = [all_trades[i] for i in sorted(r_full[0])]
            days_f, eq_f, _, ddc_f, _ = daily_series(
                taken_f, r_full[1], calendar, start, first_entry)
            assert days_f == days
        if not contracts:
            # The self-check replays at the ENGINE BASE, because that is
            # the start run_1m published its figures at; the page itself
            # renders at PAGE_START, and fractional drawdown percentages
            # are start-invariant so max_dd checks directly.
            _, _, check_final, _ = replay(trades, risk, START_CAPITAL)
            if abs(check_final - published["final"]) > 0.01:
                print(f"WARNING: replay final ${check_final:,.2f} at the "
                      f"${START_CAPITAL:,.0f} base against run_1m's "
                      f"${published['final']:,.2f}")
            if abs(max_dd - published["max_dd_pct"]) > 0.01:
                print(f"WARNING: replay drawdown {max_dd:.2f}% against "
                      f"run_1m's {published['max_dd_pct']:.2f}%")
        # The headline and the calendar's drawdown column are two
        # renderings of one curve, so the deepest point of the series has
        # to BE the headline. It was not, for as long as it carried
        # closing balances only.
        if abs(max(dd) - max_dd) > 0.01:
            print(f"WARNING: daily worst series bottoms at {max(dd):.2f}% "
                  f"against the headline {max_dd:.2f}%")

        # THE OUTCOME EVERY STATISTIC COUNTS (Lode, 2026-09-03 evening:
        # "102.6R won against 95.7R lost while the return is -5.35%"). A
        # contracts page books each trade in whole contracts, so its win
        # rate, expectancy, profit factor, average winner and loser, best
        # and worst and the streaks are counted in the DOLLARS this
        # account booked, after costs - never one flat R per trade. R
        # stays a column of the blotter, where it belongs to the trade.
        # The fractional pages count in R as they always have.
        if contracts:
            def outcome(i):
                return money_of[i]["pnl_usd"]
            def fmt(v):
                return signed_money(v)
            unit_note = "in this account's dollars, after costs"
        else:
            def outcome(i):
                return trades[i]["net_r"]
            def fmt(v):
                return signed(v) + "R"
            unit_note = "in R"
        vals = [outcome(i) for i in range(len(trades))]
        wins = [v for v in vals if v > 0]
        losses = [v for v in vals if v <= 0]
        net_r = sum(t["net_r"] for t in trades)
        net_out = sum(vals)
        wr = 100 * len(wins) / len(trades)
        avg_w = (sum(wins) / len(wins)) if wins else 0.0
        avg_l = (sum(losses) / len(losses)) if losses else 0.0
        gross_win = sum(wins)
        gross_loss = -sum(losses)
        pf = gross_win / gross_loss if gross_loss else None
        best = max(vals)
        worst = min(vals)
        run_w, run_l = streaks(trades, outcome)
        holds = [(pd.Timestamp(t["exit_ts"]) - pd.Timestamp(t["entry_ts"])
                  ).total_seconds() / 60.0 for t in trades]
        avg_hold = sum(holds) / len(holds)
        max_open = max(openpos)
        in_market = 100 * sum(1 for o in openpos if o) / len(openpos)
        classes = exit_classes(trades)
        links = {key: (url, {n: nums[o] for n, o in enumerate(orig_idx)
                             if o in nums}, folder, proxy)
                 for key, (url, nums, folder, proxy) in links_full.items()}

        traded = sum(1 for r in payload["markets"] if r["trades"])
        kpis = "".join([
            kpi("Closed trades", f"{len(trades)}",
                (f"taken of {len(all_trades)} in the "
                 f"{'blotter' if stopped else 'no-stop list'};"
                 f" {len(refused_map)} refused by sizing" if contracts else
                 f"{traded} markets traded of {len(payload['markets'])} "
                 f"tested")),
            kpi("Win rate", f"{wr:.1f}%",
                f"{len(wins)} won, {len(losses)} lost, {unit_note}"),
            (kpi("Net P&amp;L", signed_money(net_out),
                 "booked by this account, after costs", cls(net_out))
             if contracts else
             kpi("Net R", signed(net_r, 2), "after slippage")),
            kpi("Final capital", money(final),
                f"from {money(start)}", cls(final - start)),
            kpi("Return", signed(100 * (final / start - 1), 2) + "%",
                ("1% risk budget, integer contracts" if contracts
                 else f"at {risk}% risk per trade"),
                cls(final - start)),
            # "At any trade close", not "intraday" (Lode, 2026-09-03):
            # equity books only when a trade closes, so this can exceed
            # the closes figure only on multi-exit days; open positions
            # are NOT marked to market.
            kpi("Max drawdown", f"{max_dd:.2f}%",
                "worst reached at any trade close; open positions are not"
                " marked to market"),
            kpi("Max drawdown on closes", f"{max(ddc):.2f}%",
                "daily closing balances"),
        ])
        fees = drift = k_total = k_trades = 0
        if contracts:
            risks_pct = sorted(m["risk_pct"] for m in money_of.values())
            med_risk = risks_pct[len(risks_pct) // 2] if risks_pct else 0.0
            delta = 100 * (final / ideal_final - 1)
            # No "R at a flat 1%" tile here (Lode, 2026-09-03 evening: the
            # contracts pages are about scaling the position in contracts
            # and should never refer to a flat 1%; the blotter's Risk %
            # column is where each trade's realized size is read). The
            # reconciliation is in the commit history: with won and lost
            # R nearly balanced, cheap contracts filling the budget and
            # expensive ones floored below it can flip the money's sign.
            if micro:
                fees = sum(m["cost_full_rt"] + m["cost_micro_rt"]
                           for m in money_of.values())
                drift = sum(m.get("drift_usd", 0.0)
                            for m in money_of.values())
                k_total = sum(m["k"] for m in money_of.values())
                k_trades = sum(1 for m in money_of.values() if m["k"])
            else:
                fees = sum(m["cost_rt"] for m in money_of.values())
            kpis += "".join([
                kpi("Against the fractional ideal",
                    signed(delta, 2) + "%",
                    f"ideal {money(ideal_final)} at {ideal_dd:.2f}% DD, same"
                    f" account, all {len(all_trades)} trades", cls(delta)),
                kpi("Realized risk (median)", f"{med_risk:.2f}%",
                    f"of the {risk:g}% budget; what the stack actually"
                    f" risked of equity at entry, never above it"
                    if micro else
                    f"of the {risk:g}% budget; floor sizing never exceeds"
                    f" it"),
                kpi("Refused at placement", f"{len(refused_map)}",
                    "one full contract risked more than the budget and no"
                    " micro could stand in; never forced, released as"
                    " capital grows" if micro else
                    "one contract risked more than the budget; never"
                    " forced, released as capital grows",
                    "neg" if refused_map else ""),
                (kpi("Micro top-ups", f"{k_total:,} ctr",
                     f"on {k_trades} of {len(trades)} taken trades; routed"
                     f" {', '.join(f'{k}->{r['root']}' for k, r in sorted(route.items()))}")
                 if micro else ""),
                kpi("Execution costs", money(fees),
                    "commission + exchange + NFA, both legs, both sides, in"
                    " the curve (sourced in execution_costs.py; taxes"
                    " excluded)" if micro else
                    "commission + exchange + NFA, both sides, in the curve"
                    " (sourced in execution_costs.py; taxes excluded)",
                    "neg"),
                (kpi("Micro drift, net", signed_money(-drift),
                     "measured micro-vs-parent entry prints, signed against"
                     " the side; in the curve", cls(-drift))
                 if micro else ""),
                (kpi("Full contracts only", money(r_full[2]),
                     f"{r_full[3]:.2f}% DD, {len(r_full[0])} taken /"
                     f" {len(r_full[4])} refused -- the gray curve",
                     cls(r_full[2] - start))
                 if micro else ""),
            ])

        # Twelve tiles in three rows of four (Lode, 2026-09-02): the
        # winner/loser pair and the best/worst pair share the middle row.
        stats = "".join([
            kpi("Expectancy", fmt(net_out / len(trades)),
                f"per trade, {unit_note}", cls(net_out)),
            kpi("Profit factor", f"{pf:.2f}" if pf else "&mdash;",
                f"{fmt(gross_win)[1:] if not contracts else money(gross_win)}"
                f" won against "
                f"{fmt(gross_loss)[1:] if not contracts else money(gross_loss)}"
                f" lost, {unit_note}"),
            kpi("Longest winning run", f"{run_w}",
                "positions, in entry order"),
            kpi("Longest losing run", f"{run_l}",
                "positions, in entry order"),
            kpi("Average winner", fmt(avg_w), f"{len(wins)} trades",
                "pos"),
            kpi("Average loser", fmt(avg_l),
                f"{len(losses)} trades", "neg"),
            kpi("Best trade", fmt(best),
                "gross of nothing, net of all"),
            kpi("Worst trade", fmt(worst),
                ("a gapped or slipped stop can cost more than 1R" if stopped
                 else "no stop rests: a loss is the whole move to the"
                      " settlement") + (", in this account's dollars"
                                        if contracts else "")),
            kpi("Average hold", held(avg_hold), "entry to exit"),
            kpi("Max concurrent", f"{max_open}", "positions open at once"),
            # Currently-open count from the payload's open_positions --
            # the same list the "Currently open" table renders; a JSON
            # without the key shows a dash, never a false zero.
            kpi("Currently open",
                f"{len(payload['open_positions'])}"
                if payload.get("open_positions") is not None else "&mdash;",
                "entered, waiting for the next settlement"),
            kpi("Time in market", f"{in_market:.0f}%",
                "of market days with a position open"),
        ])

        survivors = classes.get("close1", dict(n=0, wins=0, avg=0.0))
        if contracts:
            surv_idx = [i for i, t in enumerate(trades)
                        if t["reason"] == "close1"]
            surv_vals = [money_of[i]["pnl_usd"] for i in surv_idx]
            survivors = dict(
                n=len(surv_idx),
                wins=sum(1 for v in surv_vals if v > 0),
                avg=(sum(surv_vals) / len(surv_vals)) if surv_vals else 0.0)
        if stopped:
            note = (
                "<b>Read the execution assumptions before reading the "
                "result.</b> Entries are market orders charged "
                f"{engine_1m.ENTRY_SLIP_TICKS} ticks and stops another two, "
                "and moving those two ticks was worth about 12R across the "
                "sample, so professional execution is a first-order part of "
                "this edge rather than a detail. The win rate lives in one "
                "place: a trade that survives to the day-2 settlement wins "
                f"{100 * survivors['wins'] / survivors['n']:.0f}% of the "
                f"time at {fmt(survivors['avg'])} average, while the "
                "stop class bleeds. See docs/quickfix1m1dc_audit.md, "
                "sections 8 and 9.")
        else:
            blocked = len(stopped_keys - nostop_keys)
            freed = len(nostop_keys - stopped_keys)
            note = (
                "<b>No stop order rests in this account.</b> Every position "
                "is entered exactly as in the stopped account below - the "
                "same minute, the same size, because the stop PRICE still "
                "denominates 1R and feeds the geometry band - and is then "
                "carried to the settlement of the day after entry whatever "
                "the path did. A loss is the whole settlement-to-settlement "
                "move and is not capped near -1R; a trade the stop would "
                "have taken out on a spike that reversed is a winner here. "
                "This is the engine's own run with the stop off, not the "
                "stopped blotter re-priced: a position no longer stopped is "
                "still open the next session, so an entry the stopped run "
                "took there is blocked by one position per market "
                f"(<b>{blocked}</b> such entr{'y' if blocked == 1 else 'ies'}"
                " on this window), and a market the stopped run still held "
                "can be free here "
                f"(<b>{freed}</b> entr{'y' if freed == 1 else 'ies'} only "
                "this account took). Entries are market orders charged "
                f"{engine_1m.ENTRY_SLIP_TICKS} ticks; the settlement exit "
                f"{engine_1m.SLIP_SCHEDULED_TICKS}. The stopped account is "
                "the published model; this one is its equal on the page, "
                "not a variant of it.")
        if contracts:
            etf_rows = [m for m in money_of.values() if m.get("etf")]
            note += (
                " <b>And the sizing assumptions</b> (2026-08-21, refusal "
                "policy, execution costs and the live universe "
                "2026-09-01): margin is out of scope, an order whose "
                "single contract risks more than the budget is refused at "
                "placement rather than forced, <b>every side of every "
                "position pays commission + exchange + NFA fees</b> into "
                "the equity curve (per-market rates, sources and "
                "confidence flags in <b>execution_costs.py</b>; where two "
                "sources disagreed the higher figure was adopted; taxes "
                "excluded at all times, slippage separately charged in R "
                "by the engine). ETFs are not traded at all: an ETF "
                "position would pay its full notional with no leverage, "
                "and the measured lock (over 100% of the account on 5 of "
                "12 historical ETF trades, at any account size) is part "
                "of why the universe is futures-only."
                + ("" if not etf_rows else " (ETF rows unexpectedly"
                   " present -- check the universe filter.)"))
        blotnote = (
            "Sorted by entry, newest sort on any column. <b>The market name "
            "is a link</b>: it opens charter's 1-minute trade study centred "
            "on that trade, which needs charter's <b>serve.py</b> running "
            f"({STUDY_BASE.rsplit('/1m/', 1)[0]}). R is <b>net</b> of "
            "slippage; P&amp;L is this trade's share of the shared account."
            + ("" if stopped else
               " The study holds this account&rsquo;s own list, so a row "
               "opens this trade as it was booked here, without a stop.")
            + (" <b>MF</b> says whether the market passed the human market "
               "filter (audit s.16): <b>passed</b> markets are the "
               "published universe, <b>no pass</b> markets trade on this "
               "page only because the filter is lifted."
               if mf_col else "")
            + (" <b>Stack</b> is the open position&rsquo;s composition, full "
               "contracts of the parent plus the routed micro&rsquo;s "
               "top-up (hover it for the dollar risk and the micro "
               "leg&rsquo;s rounded stop distance); <b>Risk %</b> is what "
               "the whole stack ACTUALLY risked of equity at entry, never "
               "above the 1% budget; <b>Costs $</b> is both legs&rsquo; "
               "round turn of commission + exchange + NFA plus the measured "
               "entry drift (hover for the split), already inside "
               "P&amp;L. Entries the sizing policy refused are not rows "
               "here -- see <b>Refused at order placement</b> above."
               if contracts and micro else
               " <b>Ctr</b> is the position in whole contracts; hover it "
               "for the dollar risk it realized. Entries the sizing policy "
               "refused are not rows here -- see <b>Refused at order "
               "placement</b> above."
               if contracts else ""))
        if contracts:
            mktnote = (
                "Each market's share of THIS account: the trades it took "
                "here, the dollars they booked after costs (they add up to "
                "the headline), their net R, and the exits. Win % counts "
                "the dollar outcome. <b>Costs $</b> is the market's "
                "commission + exchange + NFA plus micro drift. Only the "
                "markets that traded on this page are listed; the contract "
                "arsenal above accounts for every other Socrates market.")
        else:
            mktnote = (
                "Each market's own figures at "
                + ("the same 1% risk" if risk == RISK_PCT else
                   "the engine's 1% risk, not this page's solved risk")
                + f", on a fresh {money(START_CAPITAL)} rather than the "
                "shared account, so the returns do not add up to the "
                "headline. <b>Aborts</b> are the no-confirmation exits, "
                "<b>settlement</b> the day-2 rule exits.")
        last_exit = max(t["exit_ts"] for t in trades)[:10]
        chartsub = (
            f"{len(trades)} trades, {days[0]} to {days[-1]}, "
            + (f"a {risk:g}% risk budget in integer contracts, the "
               f"combined full + micro stack in the accent colour "
               f"against full contracts only in gray"
               if contracts and micro else
               f"a {risk:g}% risk budget in integer contracts"
               if contracts else f"{risk}% risk per trade")
            + ". One point per <b>market day</b> - "
            f"a day some market in the universe was open - and the line "
            f"<b>steps</b>: the balance is held flat until a trade "
            f"closes, and the whole move is the vertical there. It runs "
            f"to the last market day in the data"
            + (f", so the flat tail after {last_exit} is a real "
               f"{sum(1 for d in days if d > last_exit)} days with "
               f"nothing booked." if days[-1] > last_exit else "."))
        pane_eq = ("Equity &middot; <span style=\"color:var(--accent-line)\">"
                   "combined full + micro</span> against <span style=\"color:"
                   "var(--ink3)\">full contracts only</span>"
                   if micro else "Equity")
        pane_dd = ("Drawdown &middot; on daily closes, both sizings"
                   if micro else "Drawdown &middot; on daily closes")
        if contracts and nostop is not None:
            if stopped:
                head = (
                    '<h2 class="section-h acct-h">With the stop order'
                    '<span class="tag">account 2 of 2 &middot; the '
                    'published model</span></h2>'
                    '<p class="chartnote">The ladder stop rests in the '
                    'market from the entry minute: a position is closed '
                    'at its stop or at the settlement of the day after '
                    'entry, whichever comes first. Same account, same '
                    'sizing, same costs and same universe as the no-stop '
                    'account above; the two differ only in the stop '
                    'order, and in the entries a still-open position '
                    'blocked or freed.</p>')
                cardt = "One shared account, ladder stop live"
            else:
                head = (
                    '<h2 class="section-h acct-h">Without the stop order'
                    '<span class="tag">account 1 of 2</span></h2>'
                    '<p class="chartnote">The same entries with <b>no stop '
                    'order resting</b>: every position is carried to the '
                    'settlement of the day after entry, whatever the path '
                    'did in between. Sized exactly as the stopped account '
                    'below (the stop price still denominates 1R and feeds '
                    'the geometry band), the same integer-contract stack, '
                    'the same execution costs, the same universe. It is '
                    'the engine&rsquo;s own pass with the stop off, '
                    'rebuilt on every refresh beside the stopped one.</p>')
                cardt = "One shared account, no stop order"
        else:
            head = ""
            cardt = ("One shared account, ladder stop live"
                     if contracts else "One shared account")
        html = (ACCOUNT
                .replace("__SFX__", sfx)
                .replace("__HEAD__", head)
                .replace("__KPIS__", kpis)
                .replace("__STATS__", stats)
                .replace("__CARDT__", cardt)
                .replace("__CHARTSUB__", chartsub)
                .replace("__PANE_EQ__", pane_eq)
                .replace("__PANE_DD__", pane_dd)
                .replace("__NOTE__", note)
                .replace("__CLASS_NET__", "Net P&amp;L $" if contracts
                         else "Net R")
                .replace("__CLASS_AVG__", "Avg $" if contracts else "Avg R")
                .replace("__CLASSES__", class_rows_html(
                    trades, money_of if contracts else None))
                .replace("__REFUSED__", refused_html(all_trades, refused_map,
                                                     links_full, route))
                .replace("__OPEN__", open_html(payload.get("open_positions"),
                                               stopped))
                .replace("__BLOTNOTE__", blotnote)
                .replace("__BLOTTER__", blotter_html(trades, money_of, links,
                                                     contracts, micro,
                                                     mf_col))
                .replace("__MKTNOTE__", mktnote)
                # The "Not tested" list is the arsenal's job on a
                # contracts page (Lode, 2026-09-03: confusing beside the
                # arsenal).
                .replace("__MARKETS__", markets_money_html(
                    trades, money_of, links) if contracts else markets_html(
                    payload["markets"], payload.get("excluded", []), links))
                .replace("__CALENDAR__", calendar_html(
                    days, eq, dd, openpos, trades, money_of)))
        series = dict(sfx=sfx,
                      eq=[{"time": d, "value": v} for d, v in zip(days, eq)],
                      # Drawdown reads DOWNWARD from zero, like the R-cut
                      # pages: percent below the peak, negated (Lode,
                      # 2026-09-03: that is the correct visualisation of
                      # a drawdown).
                      ddc=[{"time": d, "value": -v}
                           for d, v in zip(days, ddc)],
                      eqf=[{"time": d, "value": v}
                           for d, v in zip(days, eq_f)],
                      ddf=[{"time": d, "value": -v}
                           for d, v in zip(days, ddc_f)],
                      op=[{"time": d, "value": v}
                          for d, v in zip(days, openpos)])
        taken_by_market, refused_by_market = {}, {}
        for t in trades:
            taken_by_market[t["market"]] = \
                taken_by_market.get(t["market"], 0) + 1
        for i in refused_map:
            k = all_trades[i]["market"]
            refused_by_market[k] = refused_by_market.get(k, 0) + 1
        info = dict(trades=trades, all_trades=all_trades, days=days,
                    final=final, max_dd=max_dd, refused=refused_map,
                    r_full=r_full, traded=traded,
                    taken_by_market=taken_by_market,
                    refused_by_market=refused_by_market)
        return html, series, info

    # The stopped account (the published list) numbers charter's study;
    # the no-stop rows link through the stopped trade sharing their entry.
    # Every account links through ITS OWN list and slug: charter's study
    # holds the cells and every companion (2026-09-03 evening), so a
    # no-stop row opens the no-stop trade, drawn without the stop it does
    # not have, and a lifted-filter row opens its trade on a market the
    # cells never entered.
    links_stopped = study_links(data["trades"], vslug)
    html_s, series_s, s_info = account(data, True, "", links_stopped)
    blocks, sections = [html_s], [series_s]
    n_info = None
    if nostop:
        links_ns = study_links(nostop["trades"], nostop.get("slug") or vslug)
        html_n, series_n, n_info = account(nostop, False, "ns", links_ns)
        # The no-stop account FIRST (Lode: "above the equity curve we
        # currently see"), the stopped one under it.
        blocks, sections = [html_n, html_s], [series_n, series_s]
    days = s_info["days"]
    trades = s_info["trades"]
    all_trades = s_info["all_trades"]

    if contracts and micro:
        sizing_lede = (
            f" <b>Money on this page is the MICRO STACK in INTEGER "
            f"CONTRACTS on the LIVE 22-futures universe</b>: ETFs and "
            f"non-updated markets are not traded and their blotter "
            f"trades are dropped before the replay (exact &mdash; the "
            f"engine runs markets independently). Each entry takes what "
            f"a {risk:g}% budget affords in <b>full contracts</b> first "
            f"and tops the position up toward the budget with the "
            f"routed <b>micro</b> ("
            + esc(", ".join(f"{k}->{r['root']}"
                            for k, r in sorted(route.items())))
            + f"), priced off data_center&rsquo;s validated contract "
            f"spec table; the micro leg&rsquo;s stop is the parent "
            f"stop rounded away on the micro&rsquo;s own tick grid, "
            f"the measured micro-vs-parent entry drift is priced into "
            f"the curve per trade, a trade with no micro bar at its "
            f"entry minute gets no micro leg, and a top-up never "
            f"exceeds half the minute&rsquo;s printed volume. <b>An "
            f"order that cannot fit even one micro inside the budget "
            f"is refused at placement</b> &mdash; never forced &mdash; "
            f"and released the moment grown capital affords it; "
            f"refused entries have their own table below. The "
            f"full-contracts-only sizing is the thin gray curve and "
            f"its own tile, for comparison. A taken trade&rsquo;s R is "
            f"identical to the fractional page by construction; the "
            f"blotter&rsquo;s <b>Stack</b> and <b>Risk %</b> columns "
            f"say what each position was and what it actually risked.")
    elif contracts:
        sizing_lede = (
            f" <b>Money on this page is INTEGER CONTRACTS on the LIVE "
            f"22-futures universe</b>: ETFs and non-updated markets are "
            f"not traded and their blotter trades are dropped before the "
            f"replay (exact &mdash; the engine runs markets "
            f"independently). Each entry takes what a {risk:g}% budget "
            f"affords in whole contracts (floor sizing), priced off "
            f"data_center&rsquo;s validated contract spec table. <b>An "
            f"order whose single contract risks more than the budget is "
            f"refused at placement</b> &mdash; never forced &mdash; and "
            f"released the moment grown capital affords it; refused "
            f"entries have their own table below. A taken trade&rsquo;s R "
            f"is identical to the fractional page by construction. "
            f"<b>No micro gates JSON was found</b>, so this build is "
            f"full contracts only; run research_1m_micro.py for the "
            f"micro stack.")
    else:
        sizing_lede = ""
    if contracts:
        if n_info:
            accounts_lede = (
                f" <b>Two accounts of the same entries, as equals</b>: "
                f"first <b>without a stop order</b> (every position "
                f"carried to the next settlement, {len(n_info['trades'])} "
                f"trades taken, {money(n_info['final'])} at "
                f"{n_info['max_dd']:.2f}% drawdown), then <b>with the "
                f"ladder stop</b>, the published model "
                f"({len(trades)} trades taken, {money(s_info['final'])} at "
                f"{s_info['max_dd']:.2f}% drawdown). Same account, same "
                f"sizing, same costs, same universe; the no-stop list is "
                f"the engine&rsquo;s own pass with the stop off, rebuilt "
                f"on every refresh.")
        else:
            accounts_lede = (
                " <b>The no-stop account is missing from this build</b>: "
                "the matrix JSON carries no companion for this cell yet. "
                "Rebuild the matrix (run_1m_matrix.py) and this page.")
        tested = {r["market"] for r in data["markets"]}
        arsenal = arsenal_status_html(
            s_info["taken_by_market"], s_info["refused_by_market"], tested,
            route,
            count_note=(" Counts are the <b>stopped</b> account&rsquo;s, "
                        "the published model; the no-stop account takes "
                        "the same entries less those a still-open "
                        "position blocked." if n_info else "")
            + (" <b>The human market filter is lifted on this page</b>: "
               "every live-universe market with 1-minute bars was "
               "backtested, so the six the filter rejects (ZC, ZN, ZB, "
               "SB, FGBL, BTC) read as traded or in arsenal here; SR3 "
               "still has no bars, and the ETFs and JGB stay outside the "
               "traded universe by decision." if filter_lifted else ""))
        universe_lede = (
            f"on the {len(sizing.LIVE_UNIVERSE)}-market live universe, "
            f"{len(s_info['taken_by_market'])} of which traded on this "
            f"page (the contract arsenal below says which, and why the "
            f"others did not), ")
    else:
        arsenal = ""
        accounts_lede = ""
        universe_lede = (f"across {len(data['markets'])} tested markets, "
                         f"{s_info['traded']} of which traded, ")
    lede = (
        f"One shared account of {money(start)} "
        + universe_lede +
        f"{days[0]} to {days[-1]}, at "
        f"{risk}% risk per trade. Rules 1 and 2 are the daily project's, "
        f"evaluated minute by minute; the trade is entered with a market "
        f"order and marked out at the settlement of the day after entry. "
        f"This page is the blotter: every one of the {len(trades)} trades is "
        f"listed, and each row opens that trade in charter's 1-minute study."
        + accounts_lede + sizing_lede
        + (" <b>The human market filter is LIFTED on this page</b> "
           "(Lode, 2026-09-03): the engine ran the published dials on "
           "every live-universe market with 1-minute bars, so ZC, ZN, "
           "ZB, SB, FGBL and BTC trade here beside the filter's own "
           "markets; SR3 has no bars yet, and the ETFs and JGB remain "
           "outside the traded universe. The published pages keep the "
           "filter; this page measures what it costs or saves."
           if filter_lifted else data.get("universe_note", "")))
    footer = (
        f"quickfix1m1dc, built from output/{IN_JSON.name} at the published "
        f"baseline (tighten "
        f"{'on' if p['tighten'] else 'off'}, overnight window "
        f"{'open' if p['allow_pre_activation'] else 'blocked'}). Rules, "
        f"decisions and the experiment history: docs/quickfix1m1dc_audit.md. "
        f"All times UTC. This strategy is deliberately outside the daily "
        f"registry, so it has no cap dial, no risk dial and no variant grid."
        + (f" Money on this page: integer contracts at the {money(start)} "
           f"deployment account with refusal at the {risk:g}% budget "
           f"(Lode, 2026-09-01)"
           + (", full contracts topped up with the routed micros (the "
              "micro stack, Lode 2026-09-03; the same replay as the "
              "capital ladder's $250k rung)" if micro else "")
           + f", specs from data_center/"
           f"metadata/contract_specs.json; the fractional pages remain the "
           f"research currency." if contracts else "")
        + (f" The no-stop account is the matrix's companion pass of "
           f"{esc(nostop['strategy'].split('[')[1].split(',')[0])} "
           f"(run_1m_matrix.py, the `nostop` block of "
           f"{MATRIX_JSON.name}; engine dial stop_live off, Lode "
           f"2026-09-03)." if n_info else ""))

    name = esc(data.get("strategy", "quickfix1m1dc"))
    if contracts:
        name += (" &mdash; integer contracts, full + micro stack" if micro
                 else " &mdash; integer contracts")
        if n_info:
            name += ", without and with the stop"
        if filter_lifted:
            name += ", market filter lifted"
    html = (PAGE
            .replace("__NAME__", name)
            .replace("__CSS__", CSS)
            .replace("__LEDE__", lede)
            .replace("__RULES__", rules_html(p))
            .replace("__ARSENAL__", arsenal)
            .replace("__ACCOUNTS__", "\n".join(blocks))
            .replace("__FOOTER__", footer)
            .replace("__LIB__", LIB_PATH.read_text(encoding="utf-8"))
            .replace("__JS__", PAGE_JS.replace(
                "__SECTIONS__", json.dumps(sections,
                                           separators=(",", ":")))))
    out.write_text(html, encoding="utf-8")
    r_full = s_info["r_full"]
    print(f"report: {len(trades)} trades, final ${s_info['final']:,.2f}, "
          f"max drawdown {s_info['max_dd']:.2f}%, {len(days)} days -> "
          f"{out.name} ({len(html) / 1024:.0f} KB)"
          + (f"; micro stack: {len(s_info['refused'])} refused, full-only"
             f" ${r_full[2]:,.2f} / {r_full[3]:.2f}% DD /"
             f" {len(r_full[4])} refused" if micro else "")
          + (f"; NO-STOP account: {len(n_info['trades'])} trades, final"
             f" ${n_info['final']:,.2f}, max drawdown "
             f"{n_info['max_dd']:.2f}%, {len(n_info['refused'])} refused"
             if n_info else ""))


if __name__ == "__main__":
    # python build_1m_report.py                     the published baseline
    #                                               (at the solved 6% risk)
    # python build_1m_report.py --variant "variant 5"    one matrix cell
    #
    # There were two more builds until 2026-08-12, --active25 and
    # --active25-6pct: the baseline restricted to the 25 numbered Socrates
    # markets, plain and sized to the 6% budget. Both were retired with
    # their pages (user); the human market filter is what the baseline
    # publishes now, so an active-list cut was a second answer to a
    # question the baseline already answers.
    # python build_1m_report.py --contracts     BOTH integer-contract pages
    #                                           (baseline + variant 5),
    #                                           which is what the refresh
    #                                           chain's contracts1m step runs
    # python build_1m_report.py --contracts --variant "variant N"   one cell
    # python build_1m_report.py --contracts --without-mf --variant "variant N"
    #                                           that cell's _without_mf page
    args = sys.argv[1:]
    contracts = "--contracts" in args
    without_mf = "--without-mf" in args
    args = [a for a in args if a not in ("--contracts", "--without-mf")]
    if args and args[0] == "--variant":
        build(variant=args[1], contracts=contracts, without_mf=without_mf)
    elif contracts:
        build_baseline_contracts()
        build(variant="variant 4", contracts=True)
        # The market filter lifted (Lode, 2026-09-03): the same two pages
        # on every eligible future, from the matrix's no-mf companions.
        for cell in (run_1m_matrix.BASELINE_NAME, "variant 4"):
            build(variant=cell, contracts=True, without_mf=True)
    else:
        build_baseline()
