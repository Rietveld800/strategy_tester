"""Build the quickfix1m1dc portfolio report from the saved trades JSON.

Three synced panes in the style of the daily reports: equity curve, max
drawdown, open positions — DAILY series from the window start to the last
data day, so the time axis is honest (flat segments are days without
exits) and strictly ascending by construction. Regenerates from
output/quickfix1m1dc_all.json without re-running the backtest.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
IN_JSON = HERE / "output" / "quickfix1m1dc_all.json"
OUT_HTML = HERE / "output" / "quickfix1m1dc_equity.html"
LIB_PATH = (HERE / ".." / "data_center" / "scripts"
            / "lightweight-charts.4.2.3.standalone.js")

WINDOW_START = date(2026, 1, 1)
WINDOW_END = date(2026, 7, 31)
START_CAPITAL = 100_000.0
RISK_PCT = 1.0


def daily_series(trades):
    events = []
    for t in trades:
        entry = pd.Timestamp(t["entry_ts"])
        exit_ = pd.Timestamp(t["exit_ts"])
        events.append((entry, "entry", id(t), t))
        events.append((exit_, "exit", id(t), t))
    events.sort(key=lambda e: (e[0], 0 if e[1] == "exit" else 1))

    equity = START_CAPITAL
    open_risk = {}
    eod_equity = {}
    for ts, kind, tid, t in events:
        if kind == "entry":
            open_risk[tid] = equity * RISK_PCT / 100.0
        else:
            equity += t["net_r"] * open_risk.pop(tid, equity / 100.0)
            eod_equity[ts.date()] = equity

    spans = [(pd.Timestamp(t["entry_ts"]).date(),
              pd.Timestamp(t["exit_ts"]).date()) for t in trades]

    days, eq, dd, openpos = [], [], [], []
    value, peak = START_CAPITAL, START_CAPITAL
    d = WINDOW_START
    while d <= WINDOW_END:
        if d in eod_equity:
            value = eod_equity[d]
        peak = max(peak, value)
        days.append(str(d))
        eq.append(round(value, 2))
        dd.append(round((peak - value) / peak * 100.0, 3))
        openpos.append(sum(1 for a, b in spans if a <= d < b))
        d += timedelta(days=1)
    return days, eq, dd, openpos, value, max(dd)


def build():
    data = json.loads(IN_JSON.read_text(encoding="utf-8"))
    trades = data["trades"]
    rows = data["markets"]
    days, eq, dd, openpos, final, max_dd = daily_series(trades)
    wins = sum(1 for t in trades if t["net_r"] > 0)
    wr = round(100 * wins / len(trades), 1) if trades else 0

    def series(values):
        return json.dumps([{"time": d, "value": v}
                           for d, v in zip(days, values)])

    table = "".join(
        f"<tr><td>{r['market']}</td><td>{r['trades']}</td>"
        f"<td>{r['win_rate'] if r['win_rate'] is not None else '-'}</td>"
        f"<td>{r['net_r_total']}</td><td>{r['reasons']['stop']}</td>"
        f"<td>{r['reasons']['no_confirm']}</td>"
        f"<td>{r['reasons']['close1']}</td></tr>"
        for r in rows)

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>quickfix1m1dc — portfolio report</title><style>
body {{ background:#131722; color:#d1d4dc;
font:13px -apple-system,Segoe UI,sans-serif; margin:0; padding:16px; }}
h1 {{ font-size:16px; margin:0 0 2px; }}
.sub {{ color:#787b86; margin-bottom:12px; }}
.lbl {{ color:#787b86; font-size:11px; text-transform:uppercase;
letter-spacing:.5px; margin:12px 0 4px; }}
#eq {{ height:340px; }} #dd, #op {{ height:150px; }}
#eq, #dd, #op {{ margin-bottom:6px; }}
/* Scoped to the results table ONLY: unscoped td/th rules leak into
   lightweight-charts' internal table layout and push its time-axis
   canvas down, clipping the labels (found 2026-08-03). */
table.results {{ border-collapse:collapse; margin-top:16px; }}
table.results td, table.results th {{ padding:4px 12px;
border-bottom:1px solid #2a2e39; text-align:right; }}
table.results td:first-child, table.results th:first-child {{
text-align:left; }}
table.results th {{ color:#787b86; font-weight:normal; }}
</style></head><body>
<h1>quickfix1m1dc — {len(rows)} markets, {days[0]} to {days[-1]}</h1>
<div class="sub">{len(trades)} trades, win rate {wr}%, final
${final:,.2f} ({(final / START_CAPITAL - 1) * 100:+.2f}%), max drawdown
{max_dd:.2f}%, risk {RISK_PCT}% of equity per trade</div>
<div class="lbl">Equity</div><div id="eq"></div>
<div class="lbl">Drawdown %</div><div id="dd"></div>
<div class="lbl">Open positions</div><div id="op"></div>
<table class="results"><tr><th>market</th><th>trades</th><th>wr%</th>
<th>netR</th><th>stops</th><th>no-confirm</th><th>close1</th></tr>
{table}</table>
<script>{LIB_PATH.read_text(encoding="utf-8")}</script><script>
function mk(id) {{
  const el = document.getElementById(id);
  // Height minus slack: the time-axis label row clips when the canvas
  // fills the container exactly (seen in Chrome, headless and normal).
  return LightweightCharts.createChart(el, {{
    width: el.clientWidth, height: el.clientHeight - 18,
    layout: {{ background: {{ color: '#131722' }},
               textColor: '#d1d4dc' }},
    grid: {{ vertLines: {{ color: '#1e222d' }},
             horzLines: {{ color: '#1e222d' }} }},
    rightPriceScale: {{ borderColor: '#2a2e39' }},
    timeScale: {{ borderColor: '#2a2e39' }},
  }});
}}
const ceq = mk('eq');
ceq.addLineSeries({{ color: '#26a69a', lineWidth: 2 }})
  .setData({series(eq)});
const cdd = mk('dd');
cdd.addLineSeries({{ color: '#ef5350', lineWidth: 1,
  priceFormat: {{ type: 'custom',
    formatter: v => v.toFixed(2) + '%' }} }})
  .setData({series(dd)});
const cop = mk('op');
cop.addHistogramSeries({{ color: '#5b6b8c' }})
  .setData({series(openpos)});
const charts = [ceq, cdd, cop];
window.addEventListener('resize', () => {{
  for (const [id, c] of [['eq', ceq], ['dd', cdd], ['op', cop]]) {{
    const el = document.getElementById(id);
    c.resize(el.clientWidth, el.clientHeight - 18);
  }}
}});
for (const a of charts) {{
  a.timeScale().subscribeVisibleLogicalRangeChange(r => {{
    if (r) for (const b of charts) if (b !== a)
      b.timeScale().setVisibleLogicalRange(r);
  }});
}}
for (const c of charts) c.timeScale().fitContent();
</script></body></html>"""
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"report: final ${final:,.2f}, max drawdown {max_dd:.2f}%, "
          f"{len(days)} days -> {OUT_HTML.name}")


if __name__ == "__main__":
    build()
