# build_1m_rcut_report.py
#
# The R-CUT report (Lode, 2026-08-10): quickfix1m1dc restricted to a BAND of
# ladder geometry - keep only entries whose level-to-stop distance (1R in
# price) falls between a lower and an upper fraction of the market's trailing
# 24-hour high-low range. Pick the two cuts in the page, see that band's
# equity curve and its metrics.
#
# WHY EVERY BAND NEEDS ITS OWN ENGINE RUN, and therefore why this script is
# slow (~24s per combination, ~55 min for the 0.10-step grid): a refused entry
# does NOT spend the session-lockout allowance, so a band does not merely
# DROP trades from the baseline - a later minute can trigger instead, and the
# band takes trades the baseline never reached. The 0.10-step bands sum to 337
# trades against the baseline's 137, which is the proof: they are not slices
# of one run and cannot be produced by filtering a blotter.
#
# EVERY CELL IS LEVERED TO THE SAME 6% MAX DRAWDOWN (Lode asked for this the
# moment he saw the flat-1% sweep, and he was right): comparing bands at one
# bet size flatters whichever band was allowed to dig the deepest hole, since
# a shallower curve can simply be bet bigger. Method is solve_risk.py's -
# drawdown rises monotonically with risk, so bisect - applied to
# run_1m.portfolio_replay, this project's own account. The 1% figures are kept
# beside it because the R-space metrics are what the sample can actually
# support.
#
# HOW TO READ IT, and the cautions are not decoration (audit s.15):
# - A narrow band holds 9-41 trades. Its win rate is noisy and its DRAWDOWN is
#   barely an estimate, so the 6%-levered money divides by a number this
#   sample cannot support. The leverage column is an illustration, not advice.
# - Leverage to a MEASURED drawdown rewards having FEWER observations: it bets
#   biggest exactly where the evidence is thinnest.
# - Check `top market %` before believing any band: the 0.10-0.20 band is 45%
#   one market (wheat, holding the sample's biggest winner).
#
# Usage:  python build_1m_rcut_report.py                # full 0.10-step grid
#         python build_1m_rcut_report.py --step 0.5     # coarse, for testing
#         python build_1m_rcut_report.py --max 1.0      # cap the upper edge

import json
import sys
import time
from pathlib import Path

import run_1m
import run_1m_matrix as mx

HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "output" / "quickfix1m1dcRcut.json"
OUT_HTML = HERE / "output" / "quickfix1m1dcRcut.html"

TARGET_DD = 6.0
RISK_TOLERANCE = 0.0005
BASE = dict(tighten=False, allow_pre_activation=False, confirm=False,
            stop_mode="ladder", max_entries_per_session=1)


def solve_risk(trades, target=TARGET_DD):
    """The risk % putting this trade list at `target` max drawdown, or None
    when its curve never digs that deep at any sane bet size."""
    if not trades:
        return None
    def dd(risk):
        return run_1m.portfolio_replay(trades, risk_pct=risk)[1]
    lo, hi = 0.0, 8.0
    while dd(hi) < target:
        hi *= 2
        if hi > 64:
            return None
    while hi - lo > RISK_TOLERANCE:
        mid = (lo + hi) / 2
        if dd(mid) < target:
            lo = mid
        else:
            hi = mid
    return lo


def measure(trades):
    """Metrics for one band, at 1% and levered to TARGET_DD."""
    n = len(trades)
    if not n:
        return None
    wins = sum(1 for t in trades if t["net_r"] > 0)
    netr = sum(t["net_r"] for t in trades)
    final1, dd1, curve1 = run_1m.portfolio_replay(trades, risk_pct=1.0)
    streak, dd_r = mx.entry_order_metrics(trades)
    risk6 = solve_risk(trades)
    if risk6:
        final6, dd6, curve6 = run_1m.portfolio_replay(trades, risk_pct=risk6)
    else:
        final6, dd6, curve6 = final1, dd1, curve1
    per_market = {}
    for t in trades:
        per_market[t["market"]] = per_market.get(t["market"], 0.0) + t["net_r"]
    top_mkt, top_r = (max(per_market.items(), key=lambda kv: kv[1])
                      if per_market else ("-", 0.0))
    mix = {r: sum(1 for t in trades if t["reason"] == r)
           for r in ("stop", "close1", "no_confirm", "data_end")}
    return dict(
        trades=n, wins=wins, win_rate=round(100 * wins / n, 1),
        net_r=round(netr, 2), avg_r=round(netr / n, 3),
        longest_losing_streak=streak, max_dd_r=dd_r,
        max_dd_pct=round(dd1, 2), final_1pct=round(final1, 2),
        risk_6pct=round(risk6, 3) if risk6 else None,
        final_6pct=round(final6, 2),
        markets=len(per_market), top_market=top_mkt,
        top_market_share=round(100 * top_r / netr, 0) if netr > 0 else None,
        exit_mix=mix,
        # The curve shown in the page is the LEVERED one: equal pain is the
        # comparison Lode asked for. Falls back to 1% when the band never
        # reaches the target drawdown.
        curve=curve6,
        levered=bool(risk6),
    )


def main():
    argv = sys.argv[1:]
    step = 0.10
    top = 1.50
    if "--step" in argv:
        step = float(argv[argv.index("--step") + 1])
    if "--max" in argv:
        top = float(argv[argv.index("--max") + 1])
    n_edges = int(round(top / step)) + 1
    edges = [round(i * step, 2) for i in range(n_edges)]

    t0 = time.time()
    loaded = []
    for key in run_1m.ELIGIBLE_FUTURES + run_1m.ETFS:
        try:
            inputs, excluded = run_1m.market_inputs(key)
        except Exception as exc:
            print(f"{key}: ERROR {type(exc).__name__}: {exc}", flush=True)
            continue
        if inputs is not None:
            loaded.append((key, inputs))
    print(f"loaded {len(loaded)} markets in {time.time() - t0:.0f}s", flush=True)

    def run(lo, hi):
        dials = dict(BASE, min_rpu_range_ratio=lo, max_rpu_range_ratio=hi)
        trades = []
        for key, (days, files, tick, note) in loaded:
            tr, _ = run_1m.engine_1m.run_market(days, files, tick, **dials)
            for t in tr:
                t["market"] = key
            trades.extend(tr)
        trades.sort(key=lambda t: t["entry_ts"])
        return trades

    # Every (lower, upper) pair with lower < upper, plus an uncapped upper for
    # each lower. `None` on a side means unbounded there.
    combos = [(lo, hi) for i, lo in enumerate(edges) for hi in edges[i + 1:]]
    combos += [(lo, None) for lo in edges]
    print(f"{len(combos)} combinations at {step} steps up to {top}; "
          f"~{len(combos) * 24 / 60:.0f} min", flush=True)

    cells = {}
    baseline = measure(run(None, None))
    print(f"baseline: {baseline['trades']}t {baseline['net_r']}R "
          f"DD {baseline['max_dd_pct']}% -> ${baseline['final_6pct']:,.0f} "
          f"at {baseline['risk_6pct']}%", flush=True)
    for i, (lo, hi) in enumerate(combos, 1):
        m = measure(run(lo, hi))
        key = f"{lo:.2f}|{'inf' if hi is None else f'{hi:.2f}'}"
        cells[key] = m
        el = time.time() - t0
        left = el / i * (len(combos) - i)
        print(f"[{i}/{len(combos)}] {key}: "
              + (f"{m['trades']}t {m['net_r']:+.2f}R "
                 f"avg {m['avg_r']:+.2f} DD {m['max_dd_pct']}% "
                 f"-> ${m['final_6pct']:,.0f}" if m else "no trades")
              + f"   (~{left / 60:.0f} min left)", flush=True)

    OUT_JSON.parent.mkdir(exist_ok=True)
    payload = dict(
        strategy="quickfix1m1dc - ladder-geometry band (R cut)",
        audit_doc="docs/quickfix1m1dc_audit.md (s.15)",
        target_dd=TARGET_DD, step=step, edges=edges,
        dials=BASE, baseline=baseline, cells=cells)
    OUT_JSON.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    OUT_HTML.write_text(page(payload), encoding="utf-8")
    print(f"\nwrote {OUT_JSON.name} and {OUT_HTML.name} "
          f"in {(time.time() - t0) / 60:.0f} min")


def page(p):
    lib = run_1m.LIB_PATH.read_text(encoding="utf-8")
    data = json.dumps(p)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>quickfix1m1dc - R cut</title><style>
body {{ background:#fff; color:#222; font:13px -apple-system,Segoe UI,
sans-serif; margin:0; padding:14px; }}
/* The chart must have room for its own time axis: at 420px the date labels
   were cut in half (Lode, 2026-08-10). Height here plus autoSize, which is
   charter's rule for an lwc chart in a sized container - follow the
   container, never keep a load-time guess.
   The height is passed EXPLICITLY to createChart, not left to autoSize:
   autoSize gives the MAIN PANE the container's height and then puts the time
   axis BELOW it, so the axis hangs outside the box and is clipped (measured
   here: 9px over with a 420px box, 15px with 470px - it grows with the box,
   which is what gave the game away). With an explicit height lwc fits the
   axis INSIDE it. Resize is handled by hand for the same reason. */
#chart {{ height:470px; margin-top:10px; }}
/* SCOPED TO #tbl ON PURPOSE. A bare `table` rule also hits the <table>
   lightweight-charts builds INSIDE the chart container: a margin-top of 14px
   on it pushed the whole chart down by 14px, so the time axis hung outside
   the box and its date labels were cut in half (Lode saw it, 2026-08-10).
   Never style bare element selectors on a page that hosts a third-party
   widget. */
#tbl {{ border-collapse:collapse; margin-top:14px; }}
#tbl td, #tbl th {{ padding:4px 10px; border-bottom:1px solid #ddd;
text-align:right; }}
#tbl td:first-child, #tbl th:first-child {{ text-align:left; }}
select {{ font:13px inherit; padding:2px 4px; }}
#bar {{ display:flex; gap:18px; align-items:center; flex-wrap:wrap;
margin-top:10px; }}
.note {{ color:#666; line-height:1.45; }}
/* The header note is long: keep it to a readable measure instead of letting
   it run the full width of a wide window (max-width on an inline span does
   nothing, which is why it did). */
#head {{ max-width:1150px; }}
.warn {{ color:#B25000; }}
b.k {{ font-weight:600; }}
</style></head><body>
<div id="head"><b>quickfix1m1dc - ladder geometry band</b>
<span class="note"> Keep only entries whose <b class="k">1R in price
(level to ladder stop)</b> falls between the two cuts, as a fraction of that
market's trailing 24-hour high-low range. Every band is its OWN engine run -
a refused entry does not spend the session-lockout allowance, so a band takes
trades the baseline never reached and is not a slice of it. Each cell is
levered to a constant <b class="k">{p['target_dd']}% max drawdown</b>, because
comparing at one bet size flatters whichever band dug the deepest hole.</span>
</div>
<div id="bar">
  <label>lower cut <select id="lo"></select></label>
  <label>upper cut <select id="hi"></select></label>
  <span id="risk" class="note"></span>
</div>
<div id="chart"></div>
<table id="tbl"></table>
<p class="note warn"><b>Read the R columns, not the money.</b> A narrow band
holds a few dozen trades: its win rate is noisy and its drawdown is barely an
estimate, so levering to {p['target_dd']}% divides by a number this sample
cannot support - and leverage to a measured drawdown bets biggest exactly
where the evidence is thinnest. Check <b class="k">top market share</b> before
believing a band; the 0.10-0.20 band is 45% one market. Audit s.15.</p>
<script>{lib}</script><script>
const P = {data};
const CH = document.getElementById('chart');
const CHART_H = 470;
const chart = LightweightCharts.createChart(CH,
  {{ width: CH.clientWidth, height: CHART_H,
     layout: {{ background: {{ color:'#ffffff' }}, textColor:'#333',
       attributionLogo:false, fontSize: 11 }},
     grid: {{ vertLines:{{visible:false}}, horzLines:{{visible:false}} }},
     rightPriceScale: {{ scaleMargins: {{ top:0.08, bottom:0.12 }},
       borderVisible:true }},
     // Date-only labels: the curve spans seven months, so the HH:MM that
     // timeVisible adds made the axis dense and unreadable.
     timeScale: {{ timeVisible:false, secondsVisible:false,
       borderVisible:true, fixLeftEdge:true, fixRightEdge:true }} }});
window.addEventListener('resize',
  () => chart.resize(CH.clientWidth, CHART_H));
const sBand = chart.addLineSeries(
  {{ color:'#1B9E4B', lineWidth:2, priceLineVisible:false,
     lastValueVisible:false, title:'band' }});
const sBase = chart.addLineSeries(
  {{ color:'#BBBBBB', lineWidth:1, priceLineVisible:false,
     lastValueVisible:false, title:'all trades' }});
sBase.setData(P.baseline.curve.map(c => ({{time:c[0], value:c[1]}})));

const lo = document.getElementById('lo'), hi = document.getElementById('hi');
P.edges.forEach(e => lo.add(new Option(e.toFixed(2), e)));
P.edges.forEach(e => hi.add(new Option(e.toFixed(2), e)));
hi.add(new Option('no cap', 'inf'));

function fmtMoney(v) {{ return '$' + Math.round(v).toLocaleString('en-US'); }}

function rows(m, b) {{
  const R = [
    ['trades', m.trades, b.trades],
    ['wins', m.wins, b.wins],
    ['win rate %', m.win_rate, b.win_rate],
    ['net R', m.net_r, b.net_r],
    ['avg R per trade', m.avg_r, b.avg_r],
    ['longest losing streak', m.longest_losing_streak,
     b.longest_losing_streak],
    ['max DD (R)', m.max_dd_r, b.max_dd_r],
    ['max DD % at 1% risk', m.max_dd_pct + '%', b.max_dd_pct + '%'],
    ['final at 1% risk', fmtMoney(m.final_1pct), fmtMoney(b.final_1pct)],
    ['risk for ' + P.target_dd + '% DD',
     m.risk_6pct ? m.risk_6pct + '%' : 'never reaches it',
     b.risk_6pct + '%'],
    ['final at ' + P.target_dd + '% DD', fmtMoney(m.final_6pct),
     fmtMoney(b.final_6pct)],
    ['markets', m.markets, b.markets],
    ['top market', m.top_market + ' (' + (m.top_market_share ?? '-') + '%)',
     b.top_market + ' (' + (b.top_market_share ?? '-') + '%)'],
    ['stop / day-2 / abort',
     m.exit_mix.stop + ' / ' + m.exit_mix.close1 + ' / '
       + m.exit_mix.no_confirm,
     b.exit_mix.stop + ' / ' + b.exit_mix.close1 + ' / '
       + b.exit_mix.no_confirm],
  ];
  return '<tr><th>metric</th><th>band</th><th>all trades</th></tr>'
    + R.map(r => '<tr><td>' + r[0] + '</td><td><b>' + r[1]
        + '</b></td><td style="color:#888">' + r[2] + '</td></tr>').join('');
}}

function show() {{
  const a = parseFloat(lo.value);
  const bv = hi.value === 'inf' ? null : parseFloat(hi.value);
  const tbl = document.getElementById('tbl');
  const risk = document.getElementById('risk');
  if (bv !== null && bv <= a) {{
    tbl.innerHTML = '<tr><td>upper cut must be above the lower cut</td></tr>';
    sBand.setData([]); risk.textContent = ''; return;
  }}
  const key = a.toFixed(2) + '|' + (bv === null ? 'inf' : bv.toFixed(2));
  const m = P.cells[key];
  if (!m) {{
    tbl.innerHTML = '<tr><td>no trades in this band</td></tr>';
    sBand.setData([]); risk.textContent = ''; return;
  }}
  sBand.setData(m.curve.map(c => ({{time:c[0], value:c[1]}})));
  tbl.innerHTML = rows(m, P.baseline);
  risk.textContent = m.levered
    ? ('bet ' + m.risk_6pct + '% per trade for ' + P.target_dd + '% drawdown'
       + '  ->  ' + fmtMoney(m.final_6pct))
    : ('never reaches ' + P.target_dd + '% drawdown - curve shown at 1% risk');
}}
lo.onchange = hi.onchange = show;
// Defaults picked FROM THE EDGES that exist, never hardcoded: a coarse grid
// (--step 0.5) has no 0.10 option, and setting a missing value silently
// leaves the select empty, which opened the page on an error row.
function nearest(sel, want) {{
  let best = sel.options[0].value, d = Infinity;
  for (const o of sel.options) {{
    const v = parseFloat(o.value);
    if (!isNaN(v) && Math.abs(v - want) < d) {{ d = Math.abs(v - want); best = o.value; }}
  }}
  return best;
}}
lo.value = nearest(lo, 0.10);
hi.value = nearest(hi, 0.60);
if (parseFloat(hi.value) <= parseFloat(lo.value)) hi.value = 'inf';
show();
chart.timeScale().fitContent();
</script></body></html>"""


if __name__ == "__main__":
    main()
