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
"""

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

import engine_1m
import run_1m
from build_equity_html import CSS

HERE = Path(__file__).resolve().parent
IN_JSON = HERE / "output" / "quickfix1m1dc_all.json"
MATRIX_JSON = HERE / "output" / "quickfix1m1dc_matrix.json"
OUT_HTML = HERE / "output" / "quickfix1m1dc_report.html"
LIB_PATH = (HERE / ".." / "data_center" / "scripts"
            / "lightweight-charts.4.2.3.standalone.js")

START_CAPITAL = 100_000.0
RISK_PCT = 1.0
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

def replay(trades, risk_pct=RISK_PCT):
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

    equity, peak, max_dd = START_CAPITAL, START_CAPITAL, 0.0
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


def daily_series(trades, eod):
    spans = [(pd.Timestamp(t["entry_ts"]).date(),
              pd.Timestamp(t["exit_ts"]).date()) for t in trades]
    first = min(a for a, _ in spans)
    last = max(b for _, b in spans)
    days, eq, dd, ddc, openpos = [], [], [], [], []
    value, peak = START_CAPITAL, START_CAPITAL
    # A second, gentler curve next to the worst-reached one: drawdown on the
    # CLOSING balances only, peak and trough both read at the bell. A day
    # that digs and refills before the close does not appear in it.
    peak_close = START_CAPITAL
    d = date(first.year, first.month, 1)
    while d <= last:
        if d in eod:
            value, peak, worst = eod[d]
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
        d += timedelta(days=1)
    return days, eq, dd, ddc, openpos


def streaks(trades):
    """Longest winning and losing run, in ENTRY order and off net R.

    The project's rule (user, 2026-07-29): the blotter is sorted by entry,
    so a reader counting losing rows counts entry order, and keying off R
    keeps the figure independent of the bet size.
    """
    best_w = best_l = cur_w = cur_l = 0
    for t in sorted(trades, key=lambda x: x["entry_ts"]):
        if t["net_r"] > 0:
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


def class_rows_html(trades):
    rows = []
    for label, pick, note in CLASS_DEFS:
        sel = [t for t in trades if pick(t)]
        if not sel:
            continue
        r = sum(t["net_r"] for t in sel)
        avg = r / len(sel)
        # The % column is this class's share of ALL trades, not a win rate
        # within the class (user, 2026-08-09), tinted by which side of the
        # ledger the class sits on.
        rows.append(
            f'<tr><td class="l">{label}</td>'
            f'<td class="mono">{len(sel)}</td>'
            f'<td class="mono {cls(r)}">'
            f'{100 * len(sel) / len(trades):.1f}%</td>'
            f'<td class="mono {cls(r)}">{signed(r)}</td>'
            f'<td class="mono {cls(avg)}">{signed(avg)}</td>'
            f'<td class="l wrap">{note}</td></tr>')
    return "".join(rows)


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
                '24-hour range. The published baseline carries the band at '
                '0.20 / 0.50 (adopted, audit s.15e and s.17).</div>')
    band = (f"{lo:.2f} to {hi:.2f}" if lo and hi is not None
            else f"at most {hi:.2f}" if hi is not None
            else f"at least {lo:.2f}")
    return (
        '<div class="rulefoot"><b>The geometry cut</b> (adopted, audit '
        's.15e and s.17): an entry is refused unless its <b>level-to-stop '
        f'distance</b> is <b>{band}</b> of the market\'s trailing 24-hour '
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


def blotter_html(trades, money_of, links):
    cols = [("Market", "l", 10), ("Side", "l", 5), ("In (UTC)", "l", 12.5),
            ("Out (UTC)", "l", 12.5), ("Held", "", 5.5), ("In", "", 8),
            ("Out", "", 8), ("Stop", "", 8), ("R/24h", "", 6),
            ("R", "", 5.5), ("P&amp;L $", "", 7.5), ("Reason", "l", 11.5)]
    head = "".join(
        f'<th class="{c} sortable" data-i="{i}" style="width:{w}%">{lab}'
        f'<span class="ar"></span></th>'
        for i, (lab, c, w) in enumerate(cols))
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
        cell = (f'<a href="{link[0]}&amp;t={link[1][t]}" target="_blank" '
                f'title="{esc(link[2])}, trade {link[1][t]} in the 1m study">'
                f'{name}</a>') if link else name
        rows.append(
            f'<tr>'
            f'<td class="l" data-s="{name}">{cell}</td>'
            f'<td class="l" data-s="{tr["side"]}">{tr["side"]}</td>'
            f'<td class="l mono" data-s="{tr["entry_ts"]}">'
            f'{stamp(tr["entry_ts"])}</td>'
            f'<td class="l mono" data-s="{tr["exit_ts"]}">'
            f'{stamp(tr["exit_ts"])}</td>'
            f'<td class="mono" data-s="{mins:.0f}">{held(mins)}</td>'
            f'<td class="mono" data-s="{tr["entry"]}">{price(tr["entry"])}</td>'
            f'<td class="mono" data-s="{tr["exit"]}">{price(tr["exit"])}</td>'
            f'<td class="mono" data-s="{tr["stop"]}">{price(tr["stop"])}</td>'
            f'<td class="mono" data-s="{ratio if ratio is not None else -1}">'
            f'{ratio_txt}</td>'
            f'<td class="mono {cls(tr["net_r"])}" data-s="{tr["net_r"]}">'
            f'{signed(tr["net_r"])}</td>'
            f'<td class="mono {cls(m["pnl_usd"])}" data-s="{m["pnl_usd"]:.2f}">'
            f'{signed_money(m["pnl_usd"])}</td>'
            f'<td class="l" data-s="{tr["reason"]}">'
            f'{REASON_TEXT.get(tr["reason"], tr["reason"])}</td>'
            f'</tr>')
    return (f'<div class="tradecard"><div class="tradescroll">'
            f'<table class="trades" data-sort="2" data-dir="1">'
            f'<thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></div>')


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
    ins, outs = {}, {}
    for i, t in enumerate(trades):
        ins.setdefault(pd.Timestamp(t["entry_ts"]).date(), []).append(i)
        outs.setdefault(pd.Timestamp(t["exit_ts"]).date(), []).append(i)
    rows = []
    for d, e, drop, op in zip(days, eq, dd, openpos):
        day = date.fromisoformat(d)
        if day not in ins and day not in outs and op == 0:
            continue
        acts = []
        for i in ins.get(day, []):
            acts.append(f'<span style="color:var(--opened)">opened '
                        f'{esc(trades[i]["market"])} {trades[i]["side"]}'
                        f'</span>')
        for i in outs.get(day, []):
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
  mk('eq', __EQ__, function (c) {
    return c.addLineSeries({ color: cssv('--accent-line'), lineWidth: 2 });
  });
  mk('ddc', __DDC__, function (c) {
    return c.addLineSeries({ color: cssv('--neg'), lineWidth: 1,
      priceFormat: { type: 'custom', formatter: pct } });
  });
  mk('op', __OP__, function (c) {
    return c.addHistogramSeries({ color: cssv('--bars') });
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
  // One cursor over all three panes: moving it in any pane places the
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


PAGE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NAME__ &mdash; 1-minute report</title>
__CSS__
<style>
/* the three panes; the daily reports draw their own SVG, this page uses
   lightweight-charts, so the containers need explicit heights */
#eq{height:330px}#ddc{height:150px}#op{height:130px}
#eq,#ddc,#op{margin-bottom:4px}
.panelbl{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);font-weight:600;margin:10px 2px 4px}
table.trades td a{color:var(--accent);text-decoration:none;font-weight:600}
table.trades td a:hover{text-decoration:underline}
@media print{#eq{height:300px}#ddc,#op{height:120px}}
</style></head><body>
<div class="wrap">
<header>
  <div class="eyebrow">1-minute workstream</div>
  <h1>__NAME__</h1>
  <p class="lede">__LEDE__</p>
</header>
__RULES__
<div class="kpis">__KPIS__</div>
<div class="card">
  <div class="charthead"><div class="t">One shared account</div>
  <div class="s">__CHARTSUB__</div></div>
  <div class="panelbl">Equity</div><div id="eq"></div>
  <div class="panelbl">Drawdown &middot; on daily closes</div>
  <div id="ddc"></div>
  <div class="panelbl">Open positions</div><div id="op"></div>
</div>
<div class="note">__NOTE__</div>
<div class="section-h">Per-trade statistics</div>
<div class="stats4">__STATS__</div>
<div class="section-h">Where the trades end</div>
<div class="tradecard"><table class="trades"><thead><tr>
  <th class="l" style="width:20%">Exit class</th>
  <th style="width:9%">Trades</th>
  <th style="width:9%">%</th><th style="width:11%">Net R</th>
  <th style="width:9%">Avg R</th>
  <th class="l wrap" style="width:42%">What it means</th>
</tr></thead><tbody>__CLASSES__</tbody></table></div>
<div class="section-h">All trades</div>
<p class="chartnote">__BLOTNOTE__</p>
__BLOTTER__
<div class="section-h">By market</div>
<p class="chartnote">__MKTNOTE__</p>
__MARKETS__
<div class="section-h">Daily calendar</div>
<p class="chartnote">Every day that opened, closed or carried a position.
<b style="color:var(--opened)">Purple</b> is a position opened,
<b style="color:var(--closed)">blue</b> one closed. Capital is the shared
account at the end of that day; drawdown is the worst it reached at any
point during it, which is why a day can close higher than it dug.</p>
__CALENDAR__
<footer>__FOOTER__</footer>
</div>
<script>__LIB__</script>
__JS__
</body></html>"""


def build_baseline():
    """The published baseline page, sized to a drawdown budget (Lode,
    2026-08-11, audit s.17): risk per trade is SOLVED by bisection so the
    worst drawdown reached intraday is 6%, the same TARGET_DD the daily
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
        f"to <b>{risk:g}%</b> so the worst drawdown reached intraday is "
        "6%, the daily project's target.")
    build(data=data)


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
        params=dict(m["params"], activation_utc="07:35",
                    stop="see stop_mode", **v["dials"]),
        portfolio=dict(final=v["final_cash"], max_dd_pct=v["max_dd_pct"],
                       trades=v["trades"], win_rate=v["win_rate"],
                       net_r=v["net_r"]),
        markets=m["per_market"][name], excluded=m.get("excluded", []),
        trades=trades)


def build(data=None, out=None, variant=None):
    """The published baseline by default; one matrix cell when `variant`
    names one, written beside it under its own filename."""
    if variant:
        data = variant_payload(variant)
        # Variant names are prose ("hybrid stop", "lockout 1"), so slug the
        # lot rather than special-casing one separator into a filename.
        slug = re.sub(r"[^a-z0-9]+", "_", variant.lower()).strip("_")
        out = OUT_HTML.with_name(f"{OUT_HTML.stem}_{slug}.html")
    data = data or json.loads(IN_JSON.read_text(encoding="utf-8"))
    out = out or OUT_HTML
    trades = data["trades"]
    p = data["params"]
    published = data["portfolio"]

    risk = data.get("risk_pct", RISK_PCT)
    money_of, eod, final, max_dd = replay(trades, risk)
    days, eq, dd, ddc, openpos = daily_series(trades, eod)
    if abs(final - published["final"]) > 0.01:
        print(f"WARNING: replay final ${final:,.2f} against run_1m's "
              f"${published['final']:,.2f}")
    if abs(max_dd - published["max_dd_pct"]) > 0.01:
        print(f"WARNING: replay drawdown {max_dd:.2f}% against run_1m's "
              f"{published['max_dd_pct']:.2f}%")
    # The headline and the calendar's drawdown column are two renderings of
    # one curve, so the deepest point of the series has to BE the headline.
    # It was not, for as long as it carried closing balances only.
    if abs(max(dd) - max_dd) > 0.01:
        print(f"WARNING: daily worst series bottoms at {max(dd):.2f}% against "
              f"the headline {max_dd:.2f}%")

    wins = [t for t in trades if t["net_r"] > 0]
    losses = [t for t in trades if t["net_r"] <= 0]
    net_r = sum(t["net_r"] for t in trades)
    wr = 100 * len(wins) / len(trades)
    avg_w = sum(t["net_r"] for t in wins) / len(wins) if wins else 0.0
    avg_l = sum(t["net_r"] for t in losses) / len(losses) if losses else 0.0
    gross_win = sum(t["net_r"] for t in wins)
    gross_loss = -sum(t["net_r"] for t in losses)
    pf = gross_win / gross_loss if gross_loss else None
    best = max(t["net_r"] for t in trades)
    worst = min(t["net_r"] for t in trades)
    run_w, run_l = streaks(trades)
    holds = [(pd.Timestamp(t["exit_ts"]) - pd.Timestamp(t["entry_ts"])
              ).total_seconds() / 60.0 for t in trades]
    avg_hold = sum(holds) / len(holds)
    max_open = max(openpos)
    in_market = 100 * sum(1 for o in openpos if o) / len(openpos)
    classes = exit_classes(trades)

    # key -> (study url, {trade index in this build: n in the study},
    #         market folder). charter sorts each market's trades by entry,
    #         and its counter is 1-based, so the link lands on the row.
    by_market = {}
    for i, t in enumerate(trades):
        by_market.setdefault(t["market"], []).append(i)
    links = {}
    for key, idxs in by_market.items():
        try:
            folder = run_1m.market_info(key)["array_dir"]
        except (KeyError, StopIteration):
            continue
        order = sorted(idxs, key=lambda i: trades[i]["entry_ts"])
        links[key] = (f"{STUDY_BASE}?m={folder}",
                      {i: n + 1 for n, i in enumerate(order)}, folder)

    traded = sum(1 for r in data["markets"] if r["trades"])
    kpis = "".join([
        kpi("Closed trades", f"{len(trades)}",
            f"{traded} markets traded of {len(data['markets'])} tested"),
        kpi("Win rate", f"{wr:.1f}%", f"{len(wins)} won, {len(losses)} lost"),
        kpi("Net R", signed(net_r, 2), "after slippage"),
        kpi("Final capital", money(final),
            f"from {money(START_CAPITAL)}", cls(final - START_CAPITAL)),
        kpi("Return", signed(100 * (final / START_CAPITAL - 1), 2) + "%",
            f"at {risk}% risk per trade",
            cls(final - START_CAPITAL)),
        kpi("Max drawdown", f"{max_dd:.2f}%", "worst reached intraday"),
        kpi("Max drawdown on closes", f"{max(ddc):.2f}%",
            "daily closing balances"),
    ])

    stats = "".join([
        kpi("Average winner", signed(avg_w) + "R", f"{len(wins)} trades",
            "pos"),
        kpi("Average loser", signed(avg_l) + "R", f"{len(losses)} trades",
            "neg"),
        kpi("Expectancy", signed(net_r / len(trades)) + "R", "per trade",
            cls(net_r)),
        kpi("Profit factor", f"{pf:.2f}" if pf else "&mdash;",
            f"{gross_win:.1f}R won against {gross_loss:.1f}R lost"),
        kpi("Best trade", signed(best) + "R", "gross of nothing, net of all"),
        kpi("Worst trade", signed(worst) + "R",
            "a gapped or slipped stop can cost more than 1R"),
        kpi("Longest winning run", f"{run_w}", "positions, in entry order"),
        kpi("Longest losing run", f"{run_l}", "positions, in entry order"),
        kpi("Average hold", held(avg_hold), "entry to exit"),
        kpi("Max concurrent", f"{max_open}", "positions open at once"),
        kpi("Time in market", f"{in_market:.0f}%",
            "of days with a position open"),
    ])

    class_rows = class_rows_html(trades)

    def ser(values):
        return json.dumps([{"time": d, "value": v}
                           for d, v in zip(days, values)],
                          separators=(",", ":"))

    survivors = classes.get("close1", dict(n=0, wins=0, avg=0.0))
    lede = (
        f"One shared account of {money(START_CAPITAL)} across "
        f"{len(data['markets'])} tested markets, {traded} of which traded, "
        f"{days[0]} to {days[-1]}, at "
        f"{risk}% risk per trade. Rules 1 and 2 are the daily project's, "
        f"evaluated minute by minute; the trade is entered with a market "
        f"order and marked out at the settlement of the day after entry. "
        f"This page is the blotter: every one of the {len(trades)} trades is "
        f"listed, and each row opens that trade in charter's 1-minute study."
        + data.get("universe_note", ""))
    note = (
        "<b>Read the execution assumptions before reading the result.</b> "
        f"Entries are market orders charged {engine_1m.ENTRY_SLIP_TICKS} ticks "
        "and stops another two, and moving those two ticks was worth about 12R "
        "across the sample, so professional execution is a first-order part of "
        "this edge rather than a detail. The win rate lives in one place: a "
        f"trade that survives to the day-2 settlement wins "
        f"{100 * survivors['wins'] / survivors['n']:.0f}% of the time at "
        f"{signed(survivors['avg'])}R average, while the stop class bleeds. "
        "See docs/quickfix1m1dc_audit.md, sections 8 and 9.")
    blotnote = (
        "Sorted by entry, newest sort on any column. <b>The market name is a "
        "link</b>: it opens charter's 1-minute trade study centred on that "
        "trade, which needs charter's <b>serve.py</b> running "
        f"({STUDY_BASE.rsplit('/1m/', 1)[0]}). R is <b>net</b> of slippage; "
        "P&amp;L is this trade's share of the shared account.")
    mktnote = (
        "Each market's own figures at "
        + ("the same 1% risk" if risk == RISK_PCT else
           "the engine's 1% risk, not this page's solved risk")
        + f", on a fresh {money(START_CAPITAL)} rather than the shared "
        "account, so the returns do not add up to the headline. "
        "<b>Aborts</b> are the no-confirmation exits, <b>settlement</b> "
        "the day-2 rule exits.")
    chartsub = (f"{len(trades)} trades, {days[0]} to {days[-1]}, "
                f"{risk}% risk per trade")
    footer = (
        f"quickfix1m1dc, built from output/{IN_JSON.name} at the published "
        f"baseline (tighten "
        f"{'on' if p['tighten'] else 'off'}, overnight window "
        f"{'open' if p['allow_pre_activation'] else 'blocked'}). Rules, "
        f"decisions and the experiment history: docs/quickfix1m1dc_audit.md. "
        f"All times UTC. This strategy is deliberately outside the daily "
        f"registry, so it has no cap dial, no risk dial and no variant grid.")

    html = (PAGE
            .replace("__NAME__", esc(data.get("strategy", "quickfix1m1dc")))
            .replace("__CSS__", CSS)
            .replace("__LEDE__", lede)
            .replace("__RULES__", rules_html(p))
            .replace("__KPIS__", kpis)
            .replace("__CHARTSUB__", chartsub)
            .replace("__NOTE__", note)
            .replace("__STATS__", stats)
            .replace("__CLASSES__", class_rows)
            .replace("__BLOTNOTE__", blotnote)
            .replace("__BLOTTER__", blotter_html(trades, money_of, links))
            .replace("__MKTNOTE__", mktnote)
            .replace("__MARKETS__", markets_html(data["markets"],
                                                 data.get("excluded", []),
                                                 links))
            .replace("__CALENDAR__", calendar_html(days, eq, dd, openpos,
                                                   trades, money_of))
            .replace("__FOOTER__", footer)
            .replace("__LIB__", LIB_PATH.read_text(encoding="utf-8"))
            .replace("__JS__", PAGE_JS
                     .replace("__EQ__", ser(eq))
                     .replace("__DDC__", ser(ddc))
                     .replace("__OP__", ser(openpos))))
    out.write_text(html, encoding="utf-8")
    print(f"report: {len(trades)} trades, final ${final:,.2f}, max drawdown "
          f"{max_dd:.2f}%, {len(days)} days -> {out.name} "
          f"({len(html) / 1024:.0f} KB)")


if __name__ == "__main__":
    # python build_1m_report.py                     the published baseline
    #                                               (at the solved 6% risk)
    # python build_1m_report.py --variant "hybrid stop"   one matrix cell
    #
    # There were two more builds until 2026-08-12, --active25 and
    # --active25-6pct: the baseline restricted to the 25 numbered Socrates
    # markets, plain and sized to the 6% budget. Both were retired with
    # their pages (user); the human market filter is what the baseline
    # publishes now, so an active-list cut was a second answer to a
    # question the baseline already answers.
    args = sys.argv[1:]
    if args and args[0] == "--variant":
        build(variant=args[1])
    else:
        build_baseline()
