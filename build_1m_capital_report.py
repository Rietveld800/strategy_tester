"""The capital ladder: one deployment report across five account sizes.

Lode, 2026-09-01: the published baseline traded in INTEGER CONTRACTS
under the refusal policy at $100k, $250k, $500k, $1M and $2M starting
capital, each section in the variant-report format -- equity, drawdown
and open-positions panes, the refused orders, and the full blotter with
the contracts taken, the ACTUAL risk each position realized and the
detailed execution cost per trade. The page opens with the contract
arsenal (every market's front contract and every verified micro, with
contract size and the min_account_1pct_stop yardstick, whole dollars)
and the MISSED-TRADE TREND across the ladder: 27 missed at $100k
thinning to ONE at $2M -- and that one is a finding, not a rounding
error. GC 2026-02-02 needs $19,910 for one contract, the account had
dipped below $1.991M in January, and the order missed BY $28: the
refusal gate reads LIVE equity, not starting capital, exactly as it
would at the broker.

THE UNIVERSE IS THE LIVE 22 FUTURES (Lode, same day: "ETF's can't be
traded with our strategy ... We only trade the 22 markets"). The
blotter's ETF and non-updated markets' trades are dropped before any
replay through research_1m_sizing.live_trades -- exact, since the
engine runs markets independently.

Money model per section: research_1m_sizing's refusal policy (floor
sizing, refuse at n=0, release as equity grows) with execution costs
per side from execution_costs.py (sourced; taxes excluded). The R of a
taken trade never moves across sections -- only which trades fit and
what they pay. Rebuilds from quickfix1m1dc_all.json and data_center's
contract_specs.json alone; no engine passes, seconds.

Output: output/quickfix1m1dc_capitals.html. Refresh step `capitals1m`.
"""

import json
from pathlib import Path

import pandas as pd

import run_1m
import run_1m_matrix
import research_1m_sizing as sizing
from build_equity_html import CSS
from build_1m_report import (
    LIB_PATH, STUDY_BASE, REASON_TEXT, cls, daily_series, esc, held,
    money, price, replay, replay_contracts, signed, signed_money, stamp)

HERE = Path(__file__).resolve().parent
OUT_HTML = HERE / "output" / "quickfix1m1dc_capitals.html"
IN_JSON = HERE / "output" / "quickfix1m1dc_all.json"
SPECS_JSON = HERE / ".." / "data_center" / "metadata" / \
    "contract_specs.json"

CAPITALS = [100_000, 250_000, 500_000, 1_000_000, 2_000_000]
RISK_PCT = 1.0


def cap_label(c):
    return f"${c / 1000:,.0f}k" if c < 1_000_000 else f"${c / 1e6:g}M"


# ------------------------------------------------------------- the arsenal

def arsenal_html(payload):
    """The contract arsenal: every market's front contract, then every
    verified micro/mini, each with its size and the whole-dollar
    min_account_1pct_stop yardstick (the account at which ONE contract
    with a 1%-of-price stop risks exactly 1% of equity)."""
    markets = payload["markets"]
    by_key = {r["key"]: r for r in payload["sizing"]}
    def whole(v):
        return f"{v:,.0f}" if v else "&mdash;"

    rows = []
    for key in sorted(sizing.LIVE_UNIVERSE,
                      key=list(markets).index):
        s = markets[key]
        r = by_key.get(key)
        size = f"{s['unit_qty']:g} {s['unit']}"
        rows.append(
            f'<tr><td class="l">{esc(key)}</td>'
            f'<td class="l">{esc(s["market"])}</td>'
            f'<td class="l mono">{esc(r["front"]) if r else "&mdash;"}</td>'
            f'<td class="l">{size}</td>'
            f'<td class="mono">'
            f'{whole(r["min_account_1pct_stop"]) if r else "&mdash;"}</td>'
            f'<td class="l"></td>'
            f'</tr>')
    micro_rows = []
    for m in payload["micros"]:
        if m.get("listed") != "VERIFIED":
            continue
        micro_rows.append(
            f'<tr><td class="l">{esc(m["parent"])}</td>'
            f'<td class="l">{esc(m["name"])}</td>'
            f'<td class="l mono">{esc(m["symbol"])}</td>'
            f'<td class="l">{esc(m["contract_unit"])}'
            f' ({esc(m["size_vs_parent"])})</td>'
            f'<td class="mono">{whole(m.get("min_account_1pct_stop"))}'
            f'</td>'
            f'<td class="l"></td></tr>')
    head = ('<tr><th class="l" style="width:7%">Key</th>'
            '<th class="l" style="width:34%">Market</th>'
            '<th class="l" style="width:14%">Contract</th>'
            '<th class="l" style="width:22%">Size</th>'
            '<th style="width:13%">Min acct, 1% stop $</th>'
            '<th class="l" style="width:10%"></th></tr>')
    return (
        '<div class="section-h">The contract arsenal</div>'
        '<p class="chartnote"><b>The 22 markets we trade</b> &mdash; '
        'the live universe: the 19 currently-updated GLBX futures, '
        'FGBL (kept despite its EUR denomination) and the two IFUS '
        'markets. ETFs and non-updated markets are not traded and '
        'appear nowhere on this page. Each row: the <b>front '
        'contract</b>; below them, every <b>verified micro/mini</b> '
        'in the arsenal (definitions bought and validated 2026-09-01). '
        '<b>Min acct, 1% stop</b> is the yardstick from '
        'data_center&rsquo;s spec table: the account at which one '
        'contract with a 1%-of-price stop risks exactly 1% of equity '
        '&mdash; whole dollars, front close of the sizing build. The '
        'real gate in the sections below is the trade&rsquo;s own stop, '
        'not this yardstick.</p>'
        f'<div class="tradecard"><table class="trades"><thead>{head}'
        f'</thead><tbody>{"".join(rows)}</tbody></table></div>'
        '<p class="chartnote"><b>Micros and minis in arsenal</b> &mdash; '
        'verified from GLBX definitions; none are routed to by any '
        'replay yet, the micro study decides that.</p>'
        f'<div class="tradecard"><table class="trades"><thead>{head}'
        f'</thead><tbody>{"".join(micro_rows)}</tbody></table></div>')


# ------------------------------------------------------------- the sections

def run_ladder(all_trades):
    """One refusal-policy replay per capital."""
    out = []
    for cap in CAPITALS:
        money_of, eod, final, max_dd, refused = replay_contracts(
            all_trades, RISK_PCT, float(cap))
        _, _, ideal_final, ideal_dd = replay(all_trades, RISK_PCT,
                                             float(cap))
        out.append(dict(cap=cap, money_of=money_of, eod=eod, final=final,
                        max_dd=max_dd, refused=refused,
                        ideal_final=ideal_final, ideal_dd=ideal_dd))
    return out


def trend_html(ladder, n_all):
    rows = []
    for r in ladder:
        taken = len(r["money_of"])
        missed = len(r["refused"])
        costs = sum(m["cost_rt"] for m in r["money_of"].values())
        rows.append(
            f'<tr><td class="l mono">{cap_label(r["cap"])}</td>'
            f'<td class="mono">{taken}</td>'
            f'<td class="mono {"neg" if missed else "pos"}">{missed}</td>'
            f'<td class="mono">{100 * missed / n_all:.0f}%</td>'
            f'<td class="mono">{money(r["final"])}</td>'
            f'<td class="mono {cls(r["final"] / r["cap"] - 1)}">'
            f'{signed(100 * (r["final"] / r["cap"] - 1), 1)}%</td>'
            f'<td class="mono">{r["max_dd"]:.2f}%</td>'
            f'<td class="mono">{money(costs)}</td>'
            f'<td class="mono">'
            f'{100 * (r["final"] / r["ideal_final"] - 1):+.2f}%</td>'
            f'</tr>')
    return (
        '<div class="section-h">The missed-trade trend</div>'
        '<p class="chartnote">The whole ladder in one table: how many of '
        f'the {n_all} blotter trades each starting capital could take '
        'inside the 1% threshold, and what the missed ones cost. A '
        'missed trade is an order REFUSED at placement because one '
        'contract risked more than 1% of equity <b>at that moment</b> '
        '&mdash; never forced &mdash; and the refusals thin out as '
        'capital grows. Even $2M misses ONE, and honestly so: GC '
        '2026-02-02 costs $19,910 a contract, the account had dipped '
        'below $1.991M in January, and the order missed by $28. The '
        'gate reads live equity, not starting capital, exactly as it '
        'would at the broker. '
        '<b>vs ideal</b> is the distance to the frictionless fractional '
        'replay at the same capital (quantization + refusals + '
        'execution costs together).</p>'
        '<div class="tradecard"><table class="trades"><thead><tr>'
        '<th class="l" style="width:11%">Start capital</th>'
        '<th style="width:10%">Taken</th>'
        '<th style="width:10%">Missed</th>'
        '<th style="width:10%">Missed %</th>'
        '<th style="width:14%">Final</th>'
        '<th style="width:11%">Return</th>'
        '<th style="width:11%">Max DD</th>'
        '<th style="width:12%">Exec costs</th>'
        '<th style="width:11%">vs ideal</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def refused_section_html(all_trades, refused, links_full):
    if not refused:
        return ('<p class="chartnote"><b>No trade missed at this '
                'capital.</b> Every blotter entry fit at least one '
                'contract inside the 1% budget.</p>')
    rows = []
    for i in sorted(refused, key=lambda i: all_trades[i]["entry_ts"]):
        t, r = all_trades[i], refused[i]
        link = links_full.get(t["market"])
        name = esc(t["market"])
        if link:
            name = (f'<a href="{link[0]}&amp;t={link[1][i]}" '
                    f'target="_blank">{name}</a>')
        rows.append(
            f'<tr><td class="l">{name}</td>'
            f'<td class="l">{t["side"]}</td>'
            f'<td class="l mono">{stamp(t["entry_ts"])}</td>'
            f'<td class="mono neg">{money(r["per_unit"])}</td>'
            f'<td class="mono">{money(r["budget"])}</td>'
            f'<td class="mono {cls(t["net_r"])}">{signed(t["net_r"])}'
            f'</td></tr>')
    return (
        f'<p class="chartnote"><b>{len(refused)} trades missed</b>: one '
        'contract risked more than the 1% budget at order time. '
        '<b>R (not taken)</b> is what the blotter&rsquo;s trade went on '
        'to do &mdash; release information, not booked money.</p>'
        '<div class="tradecard"><table class="trades"><thead><tr>'
        '<th class="l" style="width:14%">Market</th>'
        '<th class="l" style="width:9%">Side</th>'
        '<th class="l" style="width:20%">In (UTC)</th>'
        '<th style="width:19%">1 contract $</th>'
        '<th style="width:19%">Budget $</th>'
        '<th style="width:19%">R (not taken)</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def blotter_section_html(all_trades, money_of_full, links_full):
    """The taken trades of one capital: contracts, ACTUAL risk %, and
    the detailed execution cost, attributed per trade."""
    rows = []
    for i in sorted(money_of_full, key=lambda i: all_trades[i]["entry_ts"]):
        t, m = all_trades[i], money_of_full[i]
        mins = ((pd.Timestamp(t["exit_ts"]) - pd.Timestamp(t["entry_ts"]))
                .total_seconds() / 60.0)
        link = links_full.get(t["market"])
        name = esc(t["market"])
        if link:
            name = (f'<a href="{link[0]}&amp;t={link[1][i]}" '
                    f'target="_blank">{name}</a>')
        rows.append(
            f'<tr><td class="l" data-s="{esc(t["market"])}">{name}</td>'
            f'<td class="l" data-s="{t["side"]}">{t["side"]}</td>'
            f'<td class="l mono" data-s="{t["entry_ts"]}">'
            f'{stamp(t["entry_ts"])}</td>'
            f'<td class="mono" data-s="{mins:.0f}">{held(mins)}</td>'
            f'<td class="mono" data-s="{m["n"]}">{m["n"]:,}</td>'
            f'<td class="mono" data-s="{m["risk_usd"]:.0f}"'
            f' title="${m["per_unit"]:,.0f} per contract">'
            f'{money(m["risk_usd"])}</td>'
            f'<td class="mono" data-s="{m["risk_pct"]:.3f}">'
            f'{m["risk_pct"]:.2f}%</td>'
            f'<td class="mono {cls(t["net_r"])}" data-s="{t["net_r"]}">'
            f'{signed(t["net_r"])}</td>'
            f'<td class="mono neg" data-s="{m["cost_rt"]:.2f}">'
            f'{money(m["cost_rt"])}</td>'
            f'<td class="mono {cls(m["pnl_usd"])}"'
            f' data-s="{m["pnl_usd"]:.2f}">'
            f'{signed_money(m["pnl_usd"])}</td>'
            f'<td class="mono" data-s="{m["balance"]:.2f}">'
            f'{money(m["balance"])}</td>'
            f'<td class="l" data-s="{t["reason"]}">'
            f'{REASON_TEXT.get(t["reason"], t["reason"])}</td></tr>')
    cols = [("Market", "l", 9.5), ("Side", "l", 5), ("In (UTC)", "l", 12),
            ("Held", "", 5.5), ("Ctr", "", 5), ("Risk $", "", 8),
            ("Risk %", "", 6.5), ("R", "", 6), ("Costs $", "", 7),
            ("P&amp;L $", "", 9.5), ("Balance", "", 9.5),
            ("Reason", "l", 16.5)]
    head = "".join(f'<th class="{c}" style="width:{w}%">{lab}</th>'
                   for lab, c, w in cols)
    return (
        '<p class="chartnote">Every trade this capital took, in entry '
        'order. <b>Ctr</b> is whole contracts (shares for an ETF), '
        '<b>Risk %</b> the risk the opened position ACTUALLY took of '
        'equity at entry (floor sizing keeps it at or under 1%), '
        '<b>Costs $</b> the trade&rsquo;s full round turn of commission '
        '+ exchange + NFA fees (sourced in execution_costs.py; taxes '
        'excluded), already inside P&amp;L and Balance.</p>'
        '<div class="tradecard"><div class="tradescroll">'
        f'<table class="trades"><thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div></div>')


def section_html(idx, r, all_trades, calendar, links_full):
    cap = r["cap"]
    taken_idx = sorted(r["money_of"])
    taken = [all_trades[i] for i in taken_idx]
    days, eq, dd, ddc, openpos = daily_series(
        taken, r["eod"], calendar, float(cap))
    costs = sum(m["cost_rt"] for m in r["money_of"].values())
    wins = sum(1 for t in taken if t["net_r"] > 0)
    kpis = "".join([
        f'<div class="kpi"><div class="k">{k}</div>'
        f'<div class="v{" " + tone if tone else ""}">{v}</div>'
        f'<div class="sub">{s}</div></div>'
        for k, v, s, tone in [
            ("Start capital", money(cap), "this section's account", ""),
            ("Final capital", money(r["final"]),
             f"{signed(100 * (r['final'] / cap - 1), 1)}% return",
             cls(r["final"] - cap)),
            ("Max drawdown", f"{r['max_dd']:.2f}%",
             "worst reached intraday", ""),
            ("Taken / missed",
             f"{len(taken)} / {len(r['refused'])}",
             f"of {len(all_trades)} blotter trades;"
             f" {wins} of the taken won",
             "neg" if r["refused"] else "pos"),
            ("Execution costs", money(costs),
             "both sides, in the curve", "neg"),
            ("vs frictionless ideal",
             f"{100 * (r['final'] / r['ideal_final'] - 1):+.2f}%",
             f"ideal {money(r['ideal_final'])} at"
             f" {r['ideal_dd']:.2f}% DD",
             cls(r["final"] - r["ideal_final"])),
        ]])
    return (
        f'<div class="section-h" id="cap{idx}">'
        f'Starting capital {cap_label(cap)}</div>'
        f'<div class="kpis">{kpis}</div>'
        f'<div class="card">'
        f'<div class="charthead"><div class="t">One shared account, '
        f'{cap_label(cap)} start</div>'
        f'<div class="s">{len(taken)} trades taken, {days[0]} to '
        f'{days[-1]}, integer contracts at the 1% budget, refusal '
        f'policy, execution costs in the curve. Step lines on market '
        f'days, like every curve in this project.</div></div>'
        f'<div class="panelbl">Equity</div><div id="eq{idx}" class="pane-eq"></div>'
        f'<div class="panelbl">Drawdown &middot; on daily closes</div>'
        f'<div id="ddc{idx}" class="pane-ddc"></div>'
        f'<div class="panelbl">Open positions</div>'
        f'<div id="op{idx}" class="pane-op"></div>'
        f'</div>'
        + refused_section_html(all_trades, r["refused"], links_full)
        + blotter_section_html(all_trades, r["money_of"], links_full)
    ), days, eq, ddc, openpos


PAGE_JS = r"""<script>
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
  var STEP = LightweightCharts.LineType.WithSteps;
  var SECTIONS = __SECTIONS__;
  var allCharts = [];
  SECTIONS.forEach(function (sec, si) {
    var panes = [];
    function mk(id, data, add) {
      var el = document.getElementById(id + si);
      var c = LightweightCharts.createChart(el, Object.assign(
        { width: el.clientWidth, height: el.clientHeight - 18 }, opts()));
      var s = add(c);
      s.setData(data.map(function (p) {
        return { time: p[0], value: p[1] };
      }));
      panes.push({ el: el, chart: c });
      allCharts.push({ el: el, chart: c });
    }
    mk('eq', sec.eq, function (c) {
      return c.addLineSeries({ color: cssv('--accent-line'),
        lineWidth: 2, lineType: STEP });
    });
    mk('ddc', sec.ddc, function (c) {
      return c.addLineSeries({ color: cssv('--neg'), lineWidth: 1,
        lineType: STEP,
        priceFormat: { type: 'custom', formatter: pct } });
    });
    mk('op', sec.op, function (c) {
      return c.addHistogramSeries({ color: cssv('--bars') });
    });
    // One label column per SECTION so its three time axes align.
    var w = 0;
    panes.forEach(function (p) {
      w = Math.max(w, p.chart.priceScale('right').width());
    });
    panes.forEach(function (p) {
      p.chart.applyOptions({ rightPriceScale: { minimumWidth: w } });
      p.chart.timeScale().fitContent();
    });
    panes.forEach(function (p) {
      p.chart.timeScale().subscribeVisibleLogicalRangeChange(function (r) {
        if (!r) return;
        panes.forEach(function (q) {
          if (q !== p) q.chart.timeScale().setVisibleLogicalRange(r);
        });
      });
    });
  });
  function resize() {
    allCharts.forEach(function (p) {
      p.chart.resize(p.el.clientWidth, p.el.clientHeight - 18);
    });
  }
  window.addEventListener('resize', resize);
  function retheme() {
    allCharts.forEach(function (p) { p.chart.applyOptions(opts()); });
  }
  window.addEventListener('beforeprint', retheme);
  window.addEventListener('afterprint', retheme);
})();
</script>"""


PAGE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>quickfix1m1dc &mdash; the capital ladder</title>
__CSS__
<style>
.pane-eq{height:300px}.pane-ddc{height:130px}.pane-op{height:110px}
.pane-eq,.pane-ddc,.pane-op{margin-bottom:4px}
table.trades td a{color:var(--accent);text-decoration:none;font-weight:600}
table.trades td a:hover{text-decoration:underline}
@media print{.pane-eq{height:260px}.pane-ddc,.pane-op{height:110px}}
</style></head><body>
<div class="wrap">
<header>
  <div class="eyebrow">1-minute workstream &middot; deployment</div>
  <h1>quickfix1m1dc &mdash; the capital ladder</h1>
  <p class="lede">__LEDE__</p>
</header>
__ARSENAL__
__TREND__
__SECTIONS__
<footer>__FOOTER__</footer>
</div>
<script>__LIB__</script>
__JS__
</body></html>"""


def build():
    data = json.loads(IN_JSON.read_text(encoding="utf-8"))
    payload = json.loads(SPECS_JSON.read_text(encoding="utf-8"))
    # THE LIVE UNIVERSE ONLY (Lode, 2026-09-01): the blotter's ETF and
    # non-updated markets are not traded, so their trades leave before
    # any replay -- exact, the engine runs markets independently.
    all_trades = sizing.live_trades(data["trades"])
    calendar = data.get("calendar") or run_1m.calendar_fallback(all_trades)

    # Charter links numbered against the FULL blotter (the list the 1m
    # study holds), shared by every section.
    by_market = {}
    for i, t in enumerate(all_trades):
        by_market.setdefault(t["market"], []).append(i)
    links_full = {}
    for key, idxs in by_market.items():
        try:
            folder = run_1m.market_info(key)["array_dir"]
        except (KeyError, StopIteration):
            continue
        order = sorted(idxs, key=lambda i: all_trades[i]["entry_ts"])
        links_full[key] = (f"{STUDY_BASE}?m={folder}",
                           {i: n + 1 for n, i in enumerate(order)}, folder)

    ladder = run_ladder(all_trades)
    sections, series = [], []
    for idx, r in enumerate(ladder):
        html, days, eq, ddc, openpos = section_html(
            idx, r, all_trades, calendar, links_full)
        sections.append(html)
        series.append(dict(eq=[[d, v] for d, v in zip(days, eq)],
                           ddc=[[d, v] for d, v in zip(days, ddc)],
                           op=[[d, v] for d, v in zip(days, openpos)]))

    lede = (
        f"The published baseline&rsquo;s {len(all_trades)} live-universe "
        f"trades (the 22 futures we trade; ETF and non-updated markets "
        f"dropped before the replay), "
        f"deployed in integer contracts at five starting capitals "
        f"({', '.join(cap_label(c) for c in CAPITALS)}), all under the "
        f"refusal policy: an order whose single contract risks more "
        f"than 1% of equity at that moment is refused, never forced, "
        f"and released as the account grows. Execution costs "
        f"(commission + exchange + NFA, both sides; taxes excluded) are "
        f"in every curve. A taken trade&rsquo;s R never changes down "
        f"the ladder &mdash; only which trades fit, what they risked "
        f"and what they paid. Variant: "
        f"{esc(run_1m_matrix.BASELINE_NAME)}, the published baseline.")
    footer = (
        "quickfix1m1dc capital ladder, built from "
        "output/quickfix1m1dc_all.json and data_center's "
        "contract_specs.json by build_1m_capital_report.py; sizing "
        "policy and costs: research_1m_sizing.py / execution_costs.py "
        "(sourced 2026-09-01). All times UTC. Rebuilt by refresh step "
        "capitals1m.")

    html = (PAGE
            .replace("__CSS__", CSS)
            .replace("__LEDE__", lede)
            .replace("__ARSENAL__", arsenal_html(payload))
            .replace("__TREND__", trend_html(ladder, len(all_trades)))
            .replace("__SECTIONS__", "".join(sections))
            .replace("__FOOTER__", footer)
            .replace("__LIB__", LIB_PATH.read_text(encoding="utf-8"))
            .replace("__JS__", PAGE_JS.replace(
                "__SECTIONS__",
                json.dumps(series, separators=(",", ":")))))
    OUT_HTML.write_text(html, encoding="utf-8")
    for r in ladder:
        print(f"  {cap_label(r['cap']):>6}: {len(r['money_of'])} taken, "
              f"{len(r['refused'])} missed, final ${r['final']:,.0f}, "
              f"DD {r['max_dd']:.2f}%")
    print(f"capital ladder -> {OUT_HTML.name} "
          f"({OUT_HTML.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    build()
