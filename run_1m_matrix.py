"""The dial matrix for quickfix1m1dc v2: one pass over the data (each
market's days/files load once), every variant run on the same inputs.

FULL FACTORIAL SINCE 2026-08-13 (Lode). The grid used to be one axis
(the session lockout) with four cells riding along beside it, and every
cell was NAMED for the one dial it moved - "hybrid stop", "no lockout",
"band 0.00-0.50". That naming only works while each cell is one step
from the baseline, and it hid the combinations: the table could not say
what the hybrid stop is worth WITHOUT the lockout, or whether the 0.20
lower cut still earns its place under a wick stop. So the cells are now
numbered - `variant 1` .. `variant 28` - and the four PROPERTIES are
columns on the page instead of prose in a name:

  lockout : 1 / 2 / none        (max_entries_per_session)
  stop    : 4th/5th / hybrid / wick   (stop_mode: ladder /
            ladder_or_extreme / extreme - "wick" is one tick beyond the
            session's running extreme AT ENTRY, above the high for a
            short and below the low for a long)
  band    : 000-050 / 020-050 / full  (the geometry cut; `full` = dial
            off)
  markets : 22 (the human market filter, s.16) / 31 (the whole universe)

27 cells are the full cross of lockout x stop x band on the FILTERED
universe. The 28th is the market filter's off-state, and Lode set it
deliberately at lockout 1 / hybrid / 000-050 rather than at the
published dials, so it pairs with variant 4 - same lockout, same stop,
same band, only the filter differs. The published baseline is
`variant 2` (lockout 1, 4th/5th, 020-050, 22 markets) and it is an
ordinary row here: it can be switched off on the chart like any other.

Everything not on those four axes stays at the published baseline: no
tightening, overnight window blocked, no confirmation clause. Read the
LOSING STREAK and the drawdown first.

Earlier grids, all in git and written up in the audit: {tighten} x
{window} picked the baseline (sections 6 and 7), {confirm} x {stop
anchor} removed the confirmation clause and kept the ladder stop
(section 10), and the lockout axis (2026-08-07 to 2026-08-13) measured
what a market that has already traded today is worth - the 1st trade of
a market-day at 39.4% and +42.51R against the 2nd at 21.4% and -10.39R,
which is the measurement the lockout rule follows from.

EVERY ROW CARRIES A CHECKBOX (default on, plus all-on / all-off), which
is what makes 28 curves readable at all: the colours run in families -
hue by stop anchor, shade by band, lightness by lockout - so a family
can be read together, and anything else is switched off.

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

import colorsys
import json
import re
import sys
from pathlib import Path

import run_1m

HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "output" / "quickfix1m1dc_matrix.json"
OUT_HTML = HERE / "output" / "quickfix1m1dc_matrix.html"

# Everything off the four axes sits at the published baseline and never
# moves: no tightening, overnight window blocked, no confirmation clause.
BASE = dict(tighten=False, allow_pre_activation=False, confirm=False)
HUMAN_APPROVED = run_1m.HUMAN_APPROVED

# The four axes. Each entry is (label, dials it sets); the label is what
# the page prints in that property's column, and the JSON carries both.
LOCKOUTS = [("1", dict(max_entries_per_session=1)),
            ("2", dict(max_entries_per_session=2)),
            ("none", dict(max_entries_per_session=None))]
# "wick" IS the engine's `extreme` mode (confirmed by Lode, 2026-08-13):
# one tick beyond the session's running extreme AT ENTRY - above the high
# for a short, below the low for a long. At entry is the only extreme that
# exists; the rest of the day is not knowable there, and the stop does not
# trail afterwards.
STOPS = [("4th/5th", dict(stop_mode="ladder")),
         ("hybrid", dict(stop_mode="ladder_or_extreme")),
         ("wick", dict(stop_mode="extreme"))]
BANDS = [("000-050", dict(min_rpu_range_ratio=0.00,
                          max_rpu_range_ratio=0.50)),
         ("020-050", dict(min_rpu_range_ratio=0.20,
                          max_rpu_range_ratio=0.50)),
         ("full", dict(min_rpu_range_ratio=None,
                       max_rpu_range_ratio=None))]

# Colour families, so 28 curves can still be read as a picture: HUE is
# the stop anchor, a hue SHIFT is the band, LIGHTNESS is the lockout.
# Two cells of the same family sit next to each other in colour, which is
# the comparison the eye is usually making.
STOP_HUE = {"4th/5th": 145, "hybrid": 215, "wick": 25}
BAND_SHIFT = {"000-050": -20, "020-050": 0, "full": 20}
LOCK_LIGHT = {"1": 32, "2": 46, "none": 61}
UNFILTERED_HSL = (300, 0.65, 0.45)        # the one cell off the 22-market grid


def color_for(props):
    """The curve colour for a cell, from its properties (see above).

    Emitted as HEX. The families are picked in HSL because that is the
    space the scheme is defined in, but lightweight-charts is handed
    `#rrggbb` - every other page in this project feeds it hex, and a
    colour string it cannot parse fails inside the paint loop where no
    console error and no test would show it.
    """
    if props["markets"] != "22":
        h, s, li = UNFILTERED_HSL
    else:
        h = (STOP_HUE[props["stop"]] + BAND_SHIFT[props["band"]]) % 360
        s, li = 0.68, LOCK_LIGHT[props["lockout"]] / 100
    r, g, b = colorsys.hls_to_rgb(h / 360, li, s)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255),
                                        round(b * 255))


def variant_slug(name):
    """Filename form of a variant name: `variant 5` -> `variant_05`.

    The number is zero-padded so the files of a 28-cell grid sort the way
    the grid reads. Owned here because the matrix names the cells; the
    JSON carries the result per variant as `slug`, and build_1m_report.py
    and research_1m_levels.py import this function so a variant page can
    never land under a name the matrix does not use.
    """
    m = re.match(r"^(.*?)\s*(\d+)$", name.strip())
    head = re.sub(r"[^a-z0-9]+", "_",
                  (m.group(1) if m else name).lower()).strip("_")
    return f"{head}_{int(m.group(2)):02d}" if m else head


def build_grid():
    """The 28 cells: the full lockout x stop x band cross on the filtered
    universe, then the market filter's off-state.

    Returns (name, dials, markets, props) tuples in the numbered order.
    The 28th cell is at lockout 1 / hybrid / 000-050 BY CHOICE (Lode,
    2026-08-13), not at the published dials, so it pairs with variant 4:
    same lockout, same stop, same band, only the filter differs.
    """
    out = []
    for lock_lab, lock in LOCKOUTS:
        for stop_lab, stop in STOPS:
            for band_lab, band in BANDS:
                props = dict(lockout=lock_lab, stop=stop_lab,
                             band=band_lab, markets="22")
                out.append((f"variant {len(out) + 1}",
                            dict(BASE, **lock, **stop, **band),
                            HUMAN_APPROVED, props))
    out.append((f"variant {len(out) + 1}",
                dict(BASE, max_entries_per_session=1,
                     stop_mode="ladder_or_extreme",
                     min_rpu_range_ratio=0.00, max_rpu_range_ratio=0.50),
                None, dict(lockout="1", stop="hybrid", band="000-050",
                           markets="31")))
    return out


VARIANTS = build_grid()
# The published run (lockout 1, 4th/5th, 020-050, 22 markets). It is an
# ORDINARY row on the page - it carries a checkbox like every other cell
# and can be switched off (Lode, 2026-08-13) - and this constant only
# marks it in the table and the JSON.
BASELINE_NAME = "variant 2"
COLORS = {name: color_for(props) for name, _, _, props in VARIANTS}


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
    results = {name: {"trades": [], "rows": []} for name, _, _, _ in VARIANTS}
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
        # The progress line quotes the BASELINE cell and counts the rest:
        # 28 cells x "name Nt R" is a line nobody reads, and the full
        # per-market figures are in the JSON for every cell anyway.
        ran = 0
        base_line = "-"
        for name, dials, markets, _props in VARIANTS:
            if markets is not None and key not in markets:
                continue
            trades, summary = run_1m.engine_1m.run_market(
                days, files, tick, **dials)
            for t in trades:
                t["market"] = key
            summary.update(market=key, note=note, tick=tick)
            results[name]["trades"].extend(trades)
            results[name]["rows"].append(summary)
            ran += 1
            if name == BASELINE_NAME:
                base_line = (f"{summary['trades']}t "
                             f"{summary['net_r_total']}R")
        print(f"{key}: {BASELINE_NAME} {base_line}  |  {ran} cells",
              flush=True)

    report = {}
    for name, dials, markets, props in VARIANTS:
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
            props=props,
            slug=variant_slug(name),
            baseline=(name == BASELINE_NAME),
            color=COLORS[name],
            dials=dials,
            markets=sorted(markets) if markets is not None else None,
            markets_run=len(results[name]["rows"]),
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
        print(f"\n{name} [lockout {props['lockout']}, {props['stop']}, "
              f"{props['band']}, {props['markets']} markets]: "
              f"{report[name]['trades']} trades, "
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
        per_market={n: results[n]["rows"] for n, _, _, _ in VARIANTS},
        trades={n: results[n]["trades"] for n, _, _, _ in VARIANTS},
        excluded=skipped), indent=1) + "\n", encoding="utf-8")

    write_page(report)
    print(f"\nwrote {OUT_JSON.name} and {OUT_HTML.name}")


def rebuild_page():
    """Redraw the page from the matrix JSON, with NO backtest.

    The grid is ~9 minutes and the page is the part that gets edited, so
    a layout or colour change must not cost a data pass. The curves are
    the only thing the JSON does not carry, and they come back from the
    stored trades in seconds (`portfolio_replay` + the same 6% solve).
    Colours are recomputed from the properties rather than read back, so
    a palette edit lands here too. Usage: `python run_1m_matrix.py
    --page`.
    """
    m = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    report = {}
    for name, v in m["variants"].items():
        trades = sorted(m["trades"][name], key=lambda t: t["entry_ts"])
        risk6 = solve_risk(trades)
        _final, _dd, curve = run_1m.portfolio_replay(
            trades, risk_pct=risk6) if risk6 else run_1m.portfolio_replay(
            trades)
        report[name] = dict(v, color=color_for(v["props"]), curve=curve)
    write_page(report)
    print(f"redrew {OUT_HTML.name} from {OUT_JSON.name} "
          f"({len(report)} cells, no backtest)")


def write_page(report):
    """The matrix page: one chart, one table, a checkbox per row."""
    lib = run_1m.LIB_PATH.read_text(encoding="utf-8")
    # The row order IS the variant order, and so is the series order: the
    # checkbox carries its row's index and toggles series[i], so nothing
    # here may be sorted or filtered on its way to the page.
    head = "".join(
        f"<tr data-i='{i}'{' class=base' if r['baseline'] else ''}>"
        f"<td><input type='checkbox' class='v' data-i='{i}' checked></td>"
        f"<td>{n}{' *' if r['baseline'] else ''}</td>"
        f"<td>{r['props']['lockout']}</td><td>{r['props']['stop']}</td>"
        f"<td>{r['props']['band']}</td><td>{r['markets_run']}</td>"
        f"<td>{r['trades']}</td><td>{r['win_rate']}</td>"
        f"<td>{r['net_r']}</td><td><b>{r['longest_losing_streak']}</b></td>"
        f"<td>{r['max_dd_r']}</td><td>{r['max_dd_pct']}%</td>"
        f"<td>{r['max_dd_close_pct']}%</td>"
        f"<td>${r['final_cash']:,.0f}</td>"
        # A cell whose drawdown never reaches 6% at any bet size has no
        # solve: it is drawn at 1% and says so rather than printing a
        # None. Only reachable on a thin sample (a debug run over one
        # market), never on the published universe.
        f"<td>{str(r['risk_6pct']) + '%' if r['risk_6pct'] else '- (1%)'}</td>"
        f"<td><b>${r['final_6pct']:,.0f}</b></td>"
        f"<td>{r['exit_mix']['close1']['wins']} / "
        f"{r['exit_mix']['close1']['n'] - r['exit_mix']['close1']['wins']} / "
        f"{r['exit_mix']['stop']['n']} / "
        f"{r['exit_mix']['no_confirm']['n']}</td>"
        f"<td>{(str(r['geometry']['refused_wide'] + r['geometry']['refused_tight'])
                + ' / ' + str(r['geometry']['range_unjudged']))
               if (r['geometry']['refused_wide'] + r['geometry']['refused_tight'])
               else ''}</td>"
        f"<td><i style='background:{r['color']}'></i></td></tr>"
        for i, (n, r) in enumerate(report.items()))
    series = "\n".join(
        f"series.push(chart.addLineSeries({{color:'{r['color']}', "
        f"lineWidth:2, priceLineVisible:false, lastValueVisible:false}})"
        f");\nseries[series.length-1].setData("
        f"{json.dumps([{'time': t, 'value': v} for t, v in r['curve']])});"
        for r in report.values())
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
#tbl td:nth-child(2), #tbl th:nth-child(2),
#tbl td:nth-child(3), #tbl th:nth-child(3),
#tbl td:nth-child(4), #tbl th:nth-child(4),
#tbl td:nth-child(5), #tbl th:nth-child(5) {{ text-align:left; }}
/* The four PROPERTY columns are what turns a numbered cell back into a
   model, so they are boxed off from the metrics beside them. */
#tbl td:nth-child(6), #tbl th:nth-child(6) {{ border-right:2px solid #bbb; }}
#tbl td i {{ display:inline-block; width:22px; height:10px; }}
#tbl tr.off td {{ opacity:.35; }}
#tbl tr.base td:nth-child(2) {{ font-weight:600; }}
#ctl {{ margin-top:10px; }}
#ctl button {{ font:inherit; padding:2px 10px; margin-right:6px; }}
</style></head><body>
<b>quickfix1m1dc v2 - the dial matrix</b>
<span style="color:#666"> market-order entries,
{run_1m.engine_1m.ENTRY_SLIP_TICKS} ticks entry slippage,
{run_1m.engine_1m.SLIP_STOP_TICKS} on a stop and
{run_1m.engine_1m.SLIP_SCHEDULED_TICKS} on a settlement exit, 1% risk on
the level-to-stop distance, no tightening, overnight window blocked, no
confirmation clause.
Every combination of the four properties is its own engine run, and the
properties are COLUMNS rather than a name, so the table can be read
across as well as down.
<b>lockout</b> = at most N ENTRIES per market per session, expiring at
the session boundary (a position carried in from the previous session
and stopped intraday does not spend the allowance).
<b>stop</b>: <b>4th/5th</b> one tick beyond the 5th reversal (4th when
only four), <b>hybrid</b> whichever of that and the session's running
extreme at entry is further away, <b>wick</b> the running extreme alone -
a tick above the entry day's high for a short, below its low for a long.
<b>band</b> = the geometry cut: refuse an entry whose level-to-stop
distance is outside that fraction of the trailing 24h high-low range
(<b>full</b> = no cut).
<b>markets</b>: {len(HUMAN_APPROVED)} = the chart-structure inspection's
universe (audit s.16, never a judgment on a market's backtest result),
31 = every market that produced a run.
The published baseline is <b>{BASELINE_NAME}</b> (marked *), and it is an
ordinary row here.
Read the losing streak and the drawdown first.</span>
<div style="color:#666; margin-top:8px"><b style="color:#222">The curves
are drawn at a constant 6% max drawdown</b> - risk per trade solved per
cell by bisection (the table's <b>risk @6% DD</b> column), because at one
shared bet size the tallest curve is partly just the deepest hole that
cell was allowed to dig. The 1% figures stay in the table beside the
solved ones. <b style="color:#222">Colour reads as a family</b>: hue is
the stop anchor (green 4th/5th, blue hybrid, orange wick), the shade
within a hue is the band, and the lighter the line the looser the
lockout. The one 31-market cell is magenta.</div>
<div id="chart"></div>
<div id="ctl"><button id="allon">all on</button>
<button id="alloff">all off</button>
<span style="color:#666">- untick a row to drop its curve; the baseline
too.</span></div>
<table id="tbl"><tr><th></th><th>variant</th>
<th>lockout</th><th>stop</th><th>band</th>
<th title="markets that produced a run in this cell">markets</th>
<th>trades</th><th>wr%</th><th>netR</th>
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
const series = [];
{series}
chart.timeScale().fitContent();
// series[i] IS the row with data-i="i" - both are written in variant
// order and neither list is ever sorted, which is the whole contract
// between the table and the chart.
const boxes = [...document.querySelectorAll('#tbl input.v')];
function apply(cb) {{
  const i = +cb.dataset.i;
  series[i].applyOptions({{visible: cb.checked}});
  cb.closest('tr').classList.toggle('off', !cb.checked);
}}
boxes.forEach(cb => cb.addEventListener('change', () => apply(cb)));
function setAll(on) {{
  boxes.forEach(cb => {{ cb.checked = on; apply(cb); }});
}}
document.getElementById('allon').onclick = () => setAll(true);
document.getElementById('alloff').onclick = () => setAll(false);
</script></body></html>"""
    OUT_HTML.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    if "--page" in sys.argv[1:]:
        rebuild_page()
    else:
        main()
