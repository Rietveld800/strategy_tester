"""The audit's 2x2 rerun: quickfix1m1dc v2 under {tighten on/off} x
{overnight-window entries allowed/blocked}. One pass over the data (each
market's days/files load once), four engine runs per market.

Metrics per variant, portfolio level (Lode's priority order): longest
losing streak (entry order, net R), max shared-account drawdown, net R,
win rate, trade count, final cash at 1% risk. Output:
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

VARIANTS = [
    ("tighten+window", dict(tighten=True, allow_pre_activation=True)),
    ("tighten+blocked", dict(tighten=True, allow_pre_activation=False)),
    ("frozen+window", dict(tighten=False, allow_pre_activation=True)),
    ("frozen+blocked", dict(tighten=False, allow_pre_activation=False)),
]
COLORS = {"tighten+window": "#1a63c9", "tighten+blocked": "#1B9E4B",
          "frozen+window": "#D64545", "frozen+blocked": "#8e44ad"}


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


def main():
    keys = sys.argv[1:] or (run_1m.ELIGIBLE_FUTURES + run_1m.ETFS
                            + list(run_1m.BINANCE))
    results = {name: {"trades": [], "rows": []} for name, _ in VARIANTS}
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
        for name, dials in VARIANTS:
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
    for name, dials in VARIANTS:
        trades = sorted(results[name]["trades"],
                        key=lambda t: t["entry_ts"])
        final, max_dd, curve = run_1m.portfolio_replay(trades)
        streak, max_dd_r = entry_order_metrics(trades)
        wins = sum(1 for t in trades if t["net_r"] > 0)
        report[name] = dict(
            dials=dials,
            trades=len(trades),
            win_rate=round(100 * wins / len(trades), 1) if trades else None,
            net_r=round(sum(t["net_r"] for t in trades), 2),
            longest_losing_streak=streak,
            max_dd_r=max_dd_r,
            final_cash=round(final, 2),
            max_dd_pct=round(max_dd, 2),
            curve=curve,
        )
        print(f"\n{name}: {report[name]['trades']} trades, "
              f"wr {report[name]['win_rate']}%, "
              f"net {report[name]['net_r']}R, "
              f"longest losing streak {streak}, "
              f"max DD {report[name]['max_dd_pct']}% "
              f"(${report[name]['final_cash']:,.0f})", flush=True)

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
        per_market={n: results[n]["rows"] for n, _ in VARIANTS},
        trades={n: results[n]["trades"] for n, _ in VARIANTS},
        excluded=skipped), indent=1) + "\n", encoding="utf-8")

    lib = run_1m.LIB_PATH.read_text(encoding="utf-8")
    head = "".join(
        f"<tr><td>{n}</td><td>{r['trades']}</td><td>{r['win_rate']}</td>"
        f"<td>{r['net_r']}</td><td><b>{r['longest_losing_streak']}</b></td>"
        f"<td>{r['max_dd_r']}</td><td>{r['max_dd_pct']}%</td>"
        f"<td>${r['final_cash']:,.0f}</td>"
        f"<td><i style='background:{COLORS[n]}'></i></td></tr>"
        for n, r in report.items())
    series = "\n".join(
        f"chart.addLineSeries({{color:'{COLORS[n]}', lineWidth:2, "
        f"priceLineVisible:false, lastValueVisible:false}})"
        f".setData({json.dumps([{'time': t, 'value': v} for t, v in report[n]['curve']])});"
        for n, _ in VARIANTS)
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>quickfix1m1dc v2 - dial matrix</title><style>
body {{ background:#fff; color:#222; font:13px -apple-system,Segoe UI,
sans-serif; margin:0; padding:14px; }}
#chart {{ height:430px; }} table {{ border-collapse:collapse;
margin-top:14px; }}
td, th {{ padding:4px 10px; border-bottom:1px solid #ddd;
text-align:right; }}
td:first-child, th:first-child {{ text-align:left; }}
td i {{ display:inline-block; width:22px; height:10px; }}
</style></head><body>
<b>quickfix1m1dc v2 - tighten x overnight-window matrix</b>
<span style="color:#666"> market-order entries, 4 ticks slippage, ladder
stop (5th else 4th reversal), 1% risk on the level-to-stop distance</span>
<div id="chart"></div>
<table><tr><th>variant</th><th>trades</th><th>wr%</th><th>netR</th>
<th>longest losing streak</th><th>max DD (R)</th><th>max DD %</th>
<th>final</th><th></th></tr>{head}</table>
<script>{lib}</script><script>
const chart = LightweightCharts.createChart(
  document.getElementById('chart'),
  {{ layout: {{ background: {{ color: '#ffffff' }}, textColor: '#333',
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
