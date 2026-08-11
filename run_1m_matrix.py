"""The dial matrix for quickfix1m1dc v2: one pass over the data (each
market's days/files load once), every variant run on the same inputs.

GRID IN FORCE (Lode, 2026-08-07; geometry band 0.20/0.50 and the human
market filter adopted into the base 2026-08-11, audit s.17): the SESSION
LOCKOUT at 1, 2 and off, everything else at the published baseline (no
tightening, overnight window blocked, no confirmation clause, ladder
stop, geometry band 0.20/0.50, human-approved markets only). It asks
what a market that has already traded today is worth:
research_1m_levels.py measured the 1st trade of a market-day at 39.4%
and +42.51R against the 2nd at 21.4% and -10.39R, and the lockout is the
rule that follows from it. Read the LOSING STREAK and the drawdown first
here.

Four cells ride along, off that axis: the HYBRID STOP at the published
lockout (the dial left open when the confirmation clause went, section
10), and one OFF/PREVIOUS state per adopted rule, so each adoption's
case is re-measured on every pass instead of resting on the sample it
was adopted on - NO GEOMETRY CUT (s.15e), BAND 0.00-0.50 (the lower cut
published until 2026-08-11; the 0.20 edge is a one-step ridge, s.15c),
and NO MARKET FILTER (the whole universe, s.16 - the inspection judged
price-bar and reversal structure and dimensions, never a market's
backtest result).

Earlier grids, all in git and written up in the audit: {tighten} x
{window} picked the baseline (sections 6 and 7), {confirm} x {stop
anchor} removed the confirmation clause and kept the ladder stop
(section 10).

Metrics per variant, portfolio level (Lode's priority order): longest
losing streak (entry order, net R), max shared-account drawdown (worst
reached, and on daily closes beside it, the same pair the main report
shows), net R, win rate, trade count, final cash at 1% risk, and the 6%
solve (risk per trade + final). THE PLOTTED CURVES ARE THE LEVERED ONES
(Lode, 2026-08-11): every cell at a constant 6% max drawdown, risk
solved per cell by bisection, because at one bet size the tallest curve
is partly just the deepest hole that cell was allowed to dig. Output:
output/quickfix1m1dc_matrix.json + output/quickfix1m1dc_matrix.html.

Usage: python run_1m_matrix.py [KEY ...] (default: all eligible).
"""

import json
import sys
from pathlib import Path

import run_1m

HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "output" / "quickfix1m1dc_matrix.json"
OUT_HTML = HERE / "output" / "quickfix1m1dc_matrix.html"

# Everything sits on the published baseline; only the dial under test moves.
# Since 2026-08-11 (audit s.17) the baseline is the ADOPTED geometry band
# 0.20 / 0.50 on the HUMAN MARKET FILTER's universe (run_1m.HUMAN_APPROVED,
# the markets that passed Lode's chart-structure inspection, s.16), so every
# cell here inherits both and each cell is still a one-dial deviation from
# what is actually published.
BASE = dict(tighten=False, allow_pre_activation=False, confirm=False,
            stop_mode="ladder",
            min_rpu_range_ratio=0.20, max_rpu_range_ratio=0.50)
HUMAN_APPROVED = run_1m.HUMAN_APPROVED

# (name, dials, markets) - markets None = the whole universe, else only
# keys in the set are run for that cell.
VARIANTS = [
    ("lockout 1", dict(BASE, max_entries_per_session=1), HUMAN_APPROVED),
    ("lockout 2", dict(BASE, max_entries_per_session=2), HUMAN_APPROVED),
    ("no lockout", dict(BASE, max_entries_per_session=None),
     HUMAN_APPROVED),
    # Not part of the lockout axis. The hybrid stop stayed an open dial
    # when the confirmation clause was removed (section 10), so it is
    # carried here against the published baseline rather than left in a
    # report nobody re-runs (Lode, 2026-08-08).
    ("hybrid stop", dict(BASE, stop_mode="ladder_or_extreme",
                         max_entries_per_session=1), HUMAN_APPROVED),
    # The OFF state of the adopted geometry cut (s.15e), so its case is
    # re-measured on every pass instead of resting on the sample it was
    # adopted on.
    ("no geometry cut", dict(BASE, max_entries_per_session=1,
                             min_rpu_range_ratio=None,
                             max_rpu_range_ratio=None), HUMAN_APPROVED),
    # The PREVIOUS lower cut (baseline until 2026-08-11). The 0.20 edge is
    # a one-step ridge carried by five trades (s.15c), so the cell watches
    # what adopting it is worth as the window grows.
    ("band 0.00-0.50", dict(BASE, max_entries_per_session=1,
                            min_rpu_range_ratio=0.00,
                            max_rpu_range_ratio=0.50), HUMAN_APPROVED),
    # The OFF state of the adopted market filter (s.16): the published
    # dials on the whole universe, so the filter's case is re-measured on
    # every pass too.
    ("no market filter", dict(BASE, max_entries_per_session=1), None),
]
BASELINE_NAME = "lockout 1"               # the published run, for reference
COLORS = {"lockout 1": "#1B9E4B", "lockout 2": "#E8A33D",
          "no lockout": "#D64545", "hybrid stop": "#3D7FE8",
          "no geometry cut": "#8E44AD", "band 0.00-0.50": "#C2185B",
          "no market filter": "#0D9488"}


def entry_order_metrics(trades):
    """Longest losing streak and max cumulative-R drawdown, ENTRY order."""
    seq = sorted(trades, key=lambda t: t["entry_ts"])
    streak = longest = 0
    cum = peak = 0.0
    max_dd_r = 0.0
    for t in seq:
        if t["net_r"] < 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
        cum += t["net_r"]
        peak = max(peak, cum)
        max_dd_r = max(max_dd_r, peak - cum)
    return longest, round(max_dd_r, 2)


def solve_risk(trades, target=6.0, tol=0.0005):
    """The risk % that puts this trade list at `target` max drawdown -
    the same bisection the report and the R-cut page use (drawdown rises
    monotonically with risk). Here so the CHART can draw every cell at
    equal pain: at one bet size the tallest curve is partly just the
    deepest hole that cell was allowed to dig (Lode, 2026-08-11)."""
    if not trades:
        return None
    def dd(risk):
        return run_1m.portfolio_replay(trades, risk_pct=risk)[1]
    lo, hi = 0.0, 8.0
    while dd(hi) < target:
        hi *= 2
        if hi > 64:
            return None
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if dd(mid) < target:
            lo = mid
        else:
            hi = mid
    return lo


def close_dd_pct(curve, start_capital=100_000.0):
    """Max drawdown on daily CLOSING balances, peak and trough both read
    at the bell: the gentler figure the main report shows next to the
    worst-reached one. The curve is per-exit, so the last point of each
    UTC day is that day's close."""
    eod = {}
    for ts, v in curve:
        eod[ts // 86400] = v
    peak, worst = start_capital, 0.0
    for day in sorted(eod):
        peak = max(peak, eod[day])
        worst = max(worst, (peak - eod[day]) / peak * 100.0)
    return round(worst, 2)


def main():
    keys = sys.argv[1:] or (run_1m.ELIGIBLE_FUTURES + run_1m.ETFS
                            + list(run_1m.BINANCE))
    results = {name: {"trades": [], "rows": []} for name, _, _ in VARIANTS}
    skipped = []
    for key in keys:
        try:
            inputs, excluded = run_1m.market_inputs(key)
        except Exception as exc:
            skipped.append({"market": key,
                            "reason": f"{type(exc).__name__}: {exc}"})
            print(f"{key}: ERROR {type(exc).__name__}: {exc}", flush=True)
            continue
        if inputs is None:
            skipped.append(excluded)
            print(f"{key}: EXCLUDED - {excluded['reason']}", flush=True)
            continue
        days, files, tick, note = inputs
        line = [key]
        for name, dials, markets in VARIANTS:
            if markets is not None and key not in markets:
                line.append(f"{name} -")
                continue
            trades, summary = run_1m.engine_1m.run_market(
                days, files, tick, **dials)
            for t in trades:
                t["market"] = key
            summary.update(market=key, note=note, tick=tick)
            results[name]["trades"].extend(trades)
            results[name]["rows"].append(summary)
            line.append(f"{name} {summary['trades']}t "
                        f"{summary['net_r_total']}R")
        print("  |  ".join(line), flush=True)

    report = {}
    for name, dials, markets in VARIANTS:
        trades = sorted(results[name]["trades"],
                        key=lambda t: t["entry_ts"])
        final, max_dd, curve = run_1m.portfolio_replay(trades)
        # The plotted curve is the LEVERED one - every cell at the same 6%
        # max drawdown, risk solved per cell - so the chart compares equal
        # pain instead of handing the deepest hole the tallest line. The
        # table keeps the 1% figures beside the solved ones.
        risk6 = solve_risk(trades)
        if risk6:
            final6, _, curve6 = run_1m.portfolio_replay(trades,
                                                        risk_pct=risk6)
        else:
            final6, curve6 = final, curve
        streak, max_dd_r = entry_order_metrics(trades)
        wins = sum(1 for t in trades if t["net_r"] > 0)
        # The exit mix is what this grid is actually about: the clause
        # moves trades between no_confirm and the other two, the stop
        # anchor moves them between stop and the settlement exits.
        mix = {}
        for r in ("stop", "no_confirm", "close1", "data_end"):
            sub = [t for t in trades if t["reason"] == r]
            mix[r] = dict(n=len(sub),
                          wins=sum(1 for t in sub if t["net_r"] > 0),
                          net_r=round(sum(t["net_r"] for t in sub), 2))
        # Geometry-dial bookkeeping, summed over markets: how many entries
        # the dial refused and how often it had to abstain for want of a
        # window. Zero on every cell that leaves the dial off.
        geom = {k: sum(r.get(k, 0) for r in results[name]["rows"])
                for k in ("refused_wide", "refused_tight", "range_unjudged")}
        report[name] = dict(
            dials=dials,
            markets=sorted(markets) if markets is not None else None,
            geometry=geom,
            trades=len(trades),
            win_rate=round(100 * wins / len(trades), 1) if trades else None,
            net_r=round(sum(t["net_r"] for t in trades), 2),
            longest_losing_streak=streak,
            max_dd_r=max_dd_r,
            final_cash=round(final, 2),
            max_dd_pct=round(max_dd, 2),
            max_dd_close_pct=close_dd_pct(curve),
            risk_6pct=round(risk6, 3) if risk6 else None,
            final_6pct=round(final6, 2),
            exit_mix=mix,
            curve=curve6,
        )
        print(f"\n{name}: {report[name]['trades']} trades, "
              f"wr {report[name]['win_rate']}%, "
              f"net {report[name]['net_r']}R, "
              f"longest losing streak {streak}, "
              f"max DD {report[name]['max_dd_pct']}% "
              f"(closes {report[name]['max_dd_close_pct']}%, "
              f"${report[name]['final_cash']:,.0f}) "
              f"-> at 6% DD: {report[name]['risk_6pct']}% risk, "
              f"${report[name]['final_6pct']:,.0f}", flush=True)

    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(dict(
        strategy="quickfix1m1dc v2 (audit decisions 2026-08-06)",
        audit_doc="docs/quickfix1m1dc_audit.md",
        params=dict(risk_pct=run_1m.engine_1m.RISK_PCT,
                    entry_slip_ticks=run_1m.engine_1m.ENTRY_SLIP_TICKS,
                    min_ladder=run_1m.engine_1m.MIN_LADDER,
                    min_tested=run_1m.engine_1m.MIN_REVERSALS),
        variants={n: {k: v for k, v in r.items() if k != "curve"}
                  for n, r in report.items()},
        per_market={n: results[n]["rows"] for n, _, _ in VARIANTS},
        trades={n: results[n]["trades"] for n, _, _ in VARIANTS},
        excluded=skipped), indent=1) + "\n", encoding="utf-8")

    lib = run_1m.LIB_PATH.read_text(encoding="utf-8")
    head = "".join(
        f"<tr><td>{n}</td><td>{r['trades']}</td><td>{r['win_rate']}</td>"
        f"<td>{r['net_r']}</td><td><b>{r['longest_losing_streak']}</b></td>"
        f"<td>{r['max_dd_r']}</td><td>{r['max_dd_pct']}%</td>"
        f"<td>{r['max_dd_close_pct']}%</td>"
        f"<td>${r['final_cash']:,.0f}</td>"
        f"<td>{r['risk_6pct']}%</td>"
        f"<td><b>${r['final_6pct']:,.0f}</b></td>"
        f"<td>{r['exit_mix']['close1']['wins']} / "
        f"{r['exit_mix']['close1']['n'] - r['exit_mix']['close1']['wins']} / "
        f"{r['exit_mix']['stop']['n']} / "
        f"{r['exit_mix']['no_confirm']['n']}</td>"
        f"<td>{(str(r['geometry']['refused_wide'] + r['geometry']['refused_tight'])
                + ' / ' + str(r['geometry']['range_unjudged']))
               if (r['geometry']['refused_wide'] + r['geometry']['refused_tight'])
               else ''}</td>"
        f"<td><i style='background:{COLORS[n]}'></i></td></tr>"
        for n, r in report.items())
    series = "\n".join(
        f"chart.addLineSeries({{color:'{COLORS[n]}', lineWidth:2, "
        f"priceLineVisible:false, lastValueVisible:false}})"
        f".setData({json.dumps([{'time': t, 'value': v} for t, v in report[n]['curve']])});"
        for n, _, _ in VARIANTS)
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>quickfix1m1dc v2 - dial matrix</title><style>
body {{ background:#fff; color:#222; font:13px -apple-system,Segoe UI,
sans-serif; margin:0; padding:14px; }}
/* Fill the window's height with the chart (Lode, 2026-08-11: a taller
   plot spreads the y axis, so the lines separate and the scale reads).
   autoSize on the chart tracks this through window resizes. */
#chart {{ height:calc(100vh - 330px); min-height:480px; }}
/* SCOPED TO #tbl. A bare `table` rule also hits the <table> that
   lightweight-charts builds inside the chart container, and a margin-top on
   it pushes the whole chart down so the time axis hangs out of its box and
   the date labels are cut in half (found on the R-cut page, 2026-08-10, and
   this page had it too). */
#tbl {{ border-collapse:collapse; margin-top:14px; }}
#tbl td, #tbl th {{ padding:4px 10px; border-bottom:1px solid #ddd;
text-align:right; }}
#tbl td:first-child, #tbl th:first-child {{ text-align:left; }}
#tbl td i {{ display:inline-block; width:22px; height:10px; }}
</style></head><body>
<b>quickfix1m1dc v2 - the session lockout</b>
<span style="color:#666"> market-order entries,
{run_1m.engine_1m.ENTRY_SLIP_TICKS} ticks entry slippage,
{run_1m.engine_1m.SLIP_STOP_TICKS} on a stop and
{run_1m.engine_1m.SLIP_SCHEDULED_TICKS} on a settlement exit, 1% risk on
the level-to-stop distance, no tightening, overnight window blocked, no
confirmation clause, ladder stop.
<b>lockout N</b> = at most N ENTRIES per market per session, expiring at
the session boundary; a position carried in from the previous session
and stopped intraday does not spend the allowance.
Every cell carries the ADOPTED baseline of 2026-08-11 (audit s.17): the
geometry band 0.20/0.50 (refuse an entry whose level-to-stop distance is
above 0.50 or below 0.20 of the trailing 24h range) on the
{len(HUMAN_APPROVED)} markets that passed Lode's chart-structure
inspection of the 1m study (s.16 - never a judgment on a market's
backtest result).
Each adopted rule keeps its off/previous state as a cell:
<b>no geometry cut</b> (dial off), <b>band 0.00-0.50</b> (the lower cut
published until 2026-08-11; the 0.20 edge is a one-step ridge, s.15c)
and <b>no market filter</b> (the whole universe).
Read the losing streak and the drawdown first.</span>
<div style="color:#666; margin-top:8px"><b style="color:#222">The curves
are drawn at a constant 6% max drawdown</b> - risk per trade solved per
cell by bisection (the table's <b>risk @6% DD</b> column), because at one
shared bet size the tallest curve is partly just the deepest hole that
cell was allowed to dig. The 1% figures stay in the table beside the
solved ones.</div>
<div id="chart"></div>
<table id="tbl"><tr><th>variant</th><th>trades</th><th>wr%</th><th>netR</th>
<th>longest losing streak</th><th>max DD (R)</th><th>max DD %</th>
<th>max DD close %</th><th>final @1%</th>
<th>risk @6% DD</th><th>final @6% DD</th>
<th>day-2 win / day-2 loss / stop / abort</th>
<th title="entries the geometry dial refused / times it abstained for want of a 24h window">geom refused / unjudged</th>
<th></th></tr>{head}</table>
<script>{lib}</script><script>
const chart = LightweightCharts.createChart(
  document.getElementById('chart'),
  {{ autoSize: true,
     layout: {{ background: {{ color: '#ffffff' }}, textColor: '#333',
     attributionLogo: false }},
     grid: {{ vertLines: {{ visible: false }},
              horzLines: {{ visible: false }} }},
     timeScale: {{ timeVisible: true }} }});
{series}
chart.timeScale().fitContent();
</script></body></html>"""
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"\nwrote {OUT_JSON.name} and {OUT_HTML.name}")


if __name__ == "__main__":
    main()
