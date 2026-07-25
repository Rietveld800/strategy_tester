# build_equity_html.py
#
# Generate the standalone interactive reports:
#
#   output/equity_<strategy>.html   one page per strategy (the interactive report)
#   output/report.html              a PRINT report carrying every strategy, used for PDF
#
# Both are built from the same pieces: one stylesheet, one per-strategy section of markup,
# and one script whose renderer is a FACTORY (`mountReport(root, DATA)`), so a page can mount
# one strategy or several. That is what makes the multi-strategy PDF possible without a
# second renderer to keep in step.
#
#   python build_equity_html.py            # every registered strategy + report.html
#   python build_equity_html.py slowfix    # just one page (report.html still gets all)
#
# PDF: the pages do NOT bundle a JavaScript PDF library. The browser's own print-to-PDF
# produces selectable vector text at a fraction of the size, where an html2canvas-style
# library rasterises everything and would add hundreds of KB to every page. So "Export PDF"
# opens report.html for the chosen strategies and calls window.print(); the user picks
# "Save as PDF" in the print dialog.

import json
import sys

import engine as eng
import strategies

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

CSS = r"""<style>
:root{
  --bg:#F6F8F5; --surface:#FFFFFF; --ink:#16201C; --ink2:#4A5852; --ink3:#7C8A84;
  --grid:rgba(20,32,28,.09); --border:rgba(20,32,28,.11);
  --accent:#0F7B57; --accent-soft:rgba(15,123,87,.13); --accent-line:#0F7B57;
  --neg:#C0503A; --neg-soft:rgba(192,80,58,.14); --ref:rgba(20,32,28,.30);
  --bars:#5C7D8A; --pos:#0F7B57;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#0D1512; --surface:#121C18; --ink:#E9EFEB; --ink2:#9BAAA3; --ink3:#66756E;
    --grid:rgba(233,239,235,.08); --border:rgba(233,239,235,.11);
    --accent:#2FB488; --accent-soft:rgba(47,180,136,.15); --accent-line:#3CC796;
    --neg:#E0715A; --neg-soft:rgba(224,113,90,.15); --ref:rgba(233,239,235,.26);
    --bars:#79A0B2; --pos:#3CC796;
  }
}
:root[data-theme="light"]{
  --bg:#F6F8F5; --surface:#FFFFFF; --ink:#16201C; --ink2:#4A5852; --ink3:#7C8A84;
  --grid:rgba(20,32,28,.09); --border:rgba(20,32,28,.11);
  --accent:#0F7B57; --accent-soft:rgba(15,123,87,.13); --accent-line:#0F7B57;
  --neg:#C0503A; --neg-soft:rgba(192,80,58,.14); --ref:rgba(20,32,28,.30);
  --bars:#5C7D8A; --pos:#0F7B57;
}
:root[data-theme="dark"]{
  --bg:#0D1512; --surface:#121C18; --ink:#E9EFEB; --ink2:#9BAAA3; --ink3:#66756E;
  --grid:rgba(233,239,235,.08); --border:rgba(233,239,235,.11);
  --accent:#2FB488; --accent-soft:rgba(47,180,136,.15); --accent-line:#3CC796;
  --neg:#E0715A; --neg-soft:rgba(224,113,90,.15); --ref:rgba(233,239,235,.26);
  --bars:#79A0B2; --pos:#3CC796;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"Segoe UI",-apple-system,BlinkMacSystemFont,Roboto,Helvetica,Arial,sans-serif;
  line-height:1.5;-webkit-font-smoothing:antialiased;}
.mono{font-family:"SF Mono","JetBrains Mono","Cascadia Code",Consolas,"Roboto Mono",ui-monospace,monospace;
  font-variant-numeric:tabular-nums;}
.wrap{max-width:1080px;margin:0 auto;padding:clamp(20px,4vw,44px) clamp(16px,4vw,32px) 56px;}
/* strategy switcher: one button per strategy, current one filled */
.nav{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:26px;
  padding-bottom:18px;border-bottom:1px solid var(--border);}
.nav .lbl{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink3);
  font-weight:600;margin-right:4px;}
.nav a{display:inline-flex;flex-direction:column;gap:1px;padding:7px 14px;border-radius:9px;
  border:1px solid var(--border);background:var(--surface);color:var(--ink2);
  text-decoration:none;font-size:13px;font-weight:600;transition:border-color .12s,color .12s;}
.nav a .sub{font-size:10.5px;font-weight:500;color:var(--ink3);letter-spacing:0;}
.nav a:hover{border-color:var(--accent);color:var(--ink);}
.nav a.on{background:var(--accent);border-color:var(--accent);color:#fff;}
.nav a.on .sub{color:rgba(255,255,255,.82);}
.pdfbtn{margin-left:auto;padding:8px 14px;border-radius:9px;border:1px solid var(--border);
  background:var(--surface);color:var(--ink2);font-size:13px;font-weight:600;cursor:pointer;
  font-family:inherit;}
.pdfbtn:hover{border-color:var(--accent);color:var(--ink);}
header{margin-bottom:26px;}
.eyebrow{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);
  font-weight:600;margin-bottom:12px;}
h1{font-size:clamp(26px,4.4vw,40px);line-height:1.08;margin:0 0 12px;letter-spacing:-.02em;
  text-wrap:balance;font-weight:650;}
.lede{max-width:66ch;color:var(--ink2);font-size:15px;margin:0;}
/* the four rules, so a first-time reader can follow the report */
.rules{margin:24px 0 0;border:1px solid var(--border);border-radius:12px;
  background:var(--surface);overflow:hidden;}
.rules .rhead{padding:12px 16px 10px;border-bottom:1px solid var(--border);}
.rules .rhead .t{font-weight:650;font-size:14px;letter-spacing:-.01em;}
.rules .rhead .s{font-size:12px;color:var(--ink3);margin-top:2px;}
.rulegrid{display:grid;grid-template-columns:repeat(2,1fr);gap:1px;background:var(--border);}
@media(max-width:720px){.rulegrid{grid-template-columns:1fr}}
.rule{background:var(--surface);padding:12px 16px 14px;display:flex;gap:11px;}
.rule .n{flex:0 0 auto;width:22px;height:22px;border-radius:50%;background:var(--accent-soft);
  color:var(--accent);font-size:11.5px;font-weight:700;display:flex;align-items:center;
  justify-content:center;margin-top:1px;}
.rule .rn{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink3);
  font-weight:600;margin-bottom:3px;}
.rule .rt{font-size:13px;color:var(--ink2);line-height:1.5;}
.rule b{color:var(--ink);font-weight:600;}
.rulefoot{padding:12px 16px;border-top:1px solid var(--border);font-size:13px;
  color:var(--ink2);line-height:1.5;}
.rulefoot b{color:var(--ink);font-weight:600;}
.rulefoot + .rulefoot{border-top:1px dashed var(--border);}
/* risk control: re-runs the shared-account simulation in the browser */
.riskbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:22px 0 0;
  padding:12px 16px;background:var(--surface);border:1px solid var(--border);
  border-radius:12px;}
.riskbar .lbl{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);font-weight:600;}
.riskbar input[type=number]{width:92px;padding:5px 7px;font-size:14px;font-weight:600;
  color:var(--ink);background:var(--bg);border:1px solid var(--border);border-radius:7px;
  font-variant-numeric:tabular-nums;}
/* The up/down buttons ARE the control here, so they must always be visible. Chrome renders
   the spinners only while the field is hovered or focused; forcing the appearance and
   opacity keeps them on permanently. */
.riskbar input[type=number]::-webkit-outer-spin-button,
.riskbar input[type=number]::-webkit-inner-spin-button{
  -webkit-appearance:inner-spin-button;opacity:1;margin:0;height:26px;}
.riskbar .unit{font-size:13px;color:var(--ink2);margin-left:-6px;}
.riskbar .warn{flex-basis:100%;font-size:11.5px;color:var(--neg);}
.riskbar .warn:empty{display:none}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1px;
  background:var(--border);
  border:1px solid var(--border);border-radius:12px;overflow:hidden;margin:22px 0 22px;}
.kpi{background:var(--surface);padding:14px 16px 15px;display:flex;flex-direction:column;gap:5px;}
.kpi .k{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink3);font-weight:600;}
.kpi .v{font-size:clamp(17px,2.2vw,21px);font-weight:600;letter-spacing:-.01em;}
.kpi .v.pos{color:var(--pos)}.kpi .v.neg{color:var(--neg)}
.kpi .sub{font-size:11px;color:var(--ink3);}
@media(max-width:460px){.kpis{grid-template-columns:repeat(2,1fr)}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;
  padding:16px clamp(10px,2vw,18px) 10px;}
.charthead{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:2px 6px 10px;}
.charthead .t{font-weight:600;font-size:14px;letter-spacing:-.01em;}
.charthead .s{font-size:12px;color:var(--ink3);}
.plot{position:relative;width:100%;touch-action:none;}
.plot svg{display:block;width:100%;height:auto;}
text{font-family:"SF Mono",Consolas,ui-monospace,monospace;}
.tip{position:absolute;pointer-events:none;opacity:0;transition:opacity .12s;background:var(--surface);
  border:1px solid var(--border);border-radius:10px;padding:9px 11px;font-size:12px;min-width:180px;
  max-width:260px;box-shadow:0 8px 26px rgba(0,0,0,.18);z-index:5;}
.tip .d{font-weight:600;margin-bottom:6px;letter-spacing:-.01em;}
.tip .row{display:flex;justify-content:space-between;gap:14px;color:var(--ink2);margin:2px 0;}
.tip .row b{color:var(--ink);font-weight:600;}
.tip .ev{margin-top:7px;padding-top:7px;border-top:1px solid var(--border);font-size:11px;color:var(--ink2);}
.tip .ev .in{color:var(--pos)}.tip .ev .out{color:var(--neg)}
.tip .mk{margin-top:6px;font-size:11px;color:var(--ink3);line-height:1.35;}
.note{max-width:72ch;margin:22px 2px 0;padding:14px 16px;background:var(--accent-soft);
  border-left:3px solid var(--accent);border-radius:0 8px 8px 0;font-size:13.5px;color:var(--ink2);}
.note b{color:var(--ink);font-weight:600;}
details{margin-top:22px;border:1px solid var(--border);border-radius:12px;overflow:hidden;background:var(--surface);}
summary{cursor:pointer;padding:13px 16px;font-weight:600;font-size:13px;list-style:none;color:var(--ink2);}
summary::-webkit-details-marker{display:none}
summary::before{content:"\25B8  ";color:var(--accent);}
details[open] summary::before{content:"\25BE  ";}
.tscroll{max-height:340px;overflow:auto;border-top:1px solid var(--border);}
table{border-collapse:collapse;width:100%;font-size:12px;}
th,td{padding:6px 12px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--border);}
th{position:sticky;top:0;background:var(--surface);color:var(--ink3);font-weight:600;text-align:right;
  font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;}
th:first-child,td:first-child{text-align:left;}
tbody tr:hover{background:var(--accent-soft);}
td.neg{color:var(--neg)}td.pos{color:var(--pos)}
.section-h{font-size:16px;font-weight:650;letter-spacing:-.01em;margin:34px 2px 12px;}
.stats4{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--border);
  border:1px solid var(--border);border-radius:12px;overflow:hidden;}
@media(max-width:640px){.stats4{grid-template-columns:repeat(2,1fr)}}
.tradecard{margin-top:14px;border:1px solid var(--border);border-radius:12px;overflow:hidden;background:var(--surface);}
.tradescroll{max-height:470px;overflow-y:auto;overflow-x:hidden;}
table.trades{border-collapse:separate;border-spacing:0;width:100%;font-size:12px;table-layout:fixed;}
table.trades th,table.trades td{padding:6px 7px;}
table.trades th{position:sticky;top:0;background:var(--surface);cursor:pointer;user-select:none;z-index:1;}
table.trades th:hover{color:var(--ink);}
table.trades th.sorted{color:var(--accent);}
table.trades .ar{font-size:9px;margin-left:2px;}
table.trades td.l,table.trades th.l{text-align:left;}
/* the two text columns (market, reason) wrap; the rest stay one line */
table.trades td:first-child,table.trades th:first-child,
table.trades td:last-child,table.trades th:last-child{white-space:normal;word-break:break-word;}
.tag{display:inline-block;margin-left:6px;padding:1px 6px;border-radius:20px;
  background:var(--grid);color:var(--ink3);font-size:9.5px;letter-spacing:.04em;
  text-transform:uppercase;font-weight:600;vertical-align:1px;}
.dbar{position:relative;height:5px;margin-top:4px;border-radius:3px;background:var(--grid);}
.dbar i{position:absolute;top:0;height:100%;border-radius:3px;}
.dbar .z{position:absolute;left:50%;top:-1px;bottom:-1px;width:1px;background:var(--border);}
footer{margin-top:30px;font-size:12px;color:var(--ink3);}
/* modal: strategy picker for the PDF export */
.mask{position:fixed;inset:0;background:rgba(0,0,0,.34);z-index:40;display:flex;
  align-items:center;justify-content:center;padding:20px;}
.dlg{background:var(--surface);border:1px solid var(--border);border-radius:14px;
  padding:18px 20px 16px;max-width:460px;width:100%;box-shadow:0 18px 50px rgba(0,0,0,.3);}
.dlg h4{margin:0 0 4px;font-size:15px;font-weight:650;letter-spacing:-.01em;}
.dlg p{margin:0 0 12px;font-size:12.5px;color:var(--ink3);}
.dlglist{border:1px solid var(--border);border-radius:10px;overflow:hidden;}
.dlgrow{display:flex;align-items:center;gap:10px;padding:9px 12px;cursor:pointer;}
.dlgrow + .dlgrow{border-top:1px solid var(--border);}
.dlgrow:hover{background:var(--accent-soft);}
.dlgrow input{margin:0;cursor:pointer;accent-color:var(--accent);}
.dlgrow .nm{font-size:13.5px;font-weight:600;}
.dlgrow .sb{display:block;font-size:11px;color:var(--ink3);font-weight:400;margin-top:1px;}
.dlgbtns{display:flex;gap:8px;justify-content:flex-end;margin-top:14px;}
.dlgbtns button{padding:7px 14px;font-size:13px;font-weight:600;border-radius:8px;
  border:1px solid var(--border);background:var(--bg);color:var(--ink2);cursor:pointer;
  font-family:inherit;}
.dlgbtns button.pri{background:var(--accent);border-color:var(--accent);color:#fff;}
.dlgbtns button:hover{border-color:var(--accent);}
.rep + .rep{margin-top:48px;padding-top:8px;}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

/* ---- print / PDF -------------------------------------------------------------
   Forced to the LIGHT palette: the dark theme would print as a solid ink-heavy
   background. print-color-adjust keeps the greens, reds and tints that carry meaning. */
@media print{
  :root, :root[data-theme="dark"]{
    --bg:#FFFFFF; --surface:#FFFFFF; --ink:#16201C; --ink2:#3F4C47; --ink3:#6B7A74;
    --grid:rgba(20,32,28,.10); --border:rgba(20,32,28,.22);
    --accent:#0F7B57; --accent-soft:rgba(15,123,87,.10); --accent-line:#0F7B57;
    --neg:#B4402A; --neg-soft:rgba(180,64,42,.12); --ref:rgba(20,32,28,.35);
    --bars:#5C7D8A; --pos:#0F7B57;
  }
  @page{size:A4 portrait;margin:13mm 11mm;}
  html,body{background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact;}
  .noprint{display:none!important;}
  .wrap{max-width:none;padding:0;}
  /* scroll boxes must open up: a PDF cannot be scrolled */
  .tradescroll,.tscroll{max-height:none!important;overflow:visible!important;}
  table.trades th,table th{position:static;}
  /* one strategy per page, and never split a block across the fold */
  .rep{break-before:page;}
  .rep:first-of-type{break-before:auto;}
  .card,.kpis,.stats4,.rules,.note,.tradecard{break-inside:avoid;}
  .section-h{break-after:avoid;}
  tr{break-inside:avoid;}
  a{text-decoration:none;color:inherit;}
}
</style>"""

# One strategy's whole report. Mounted by the script below; __RISKBAR__ and __DAILY__ are
# filled on the interactive page and left empty on the print report (which carries a single
# risk control for all strategies, and no 179-row daily table per strategy).
SECTION_HTML = r"""<section class="rep" data-root>
  <header>
    <div class="eyebrow">__EYEBROW__</div>
    <h1>__H1__</h1>
    <p class="lede">__LEDE__</p>
  </header>

  <div class="rules">
    <div class="rhead">
      <div class="t">How a trade is found</div>
      <div class="s">Described for a short; the long side is the exact mirror &mdash; bearish
        levels for the entry, bullish for the target.</div>
    </div>
    <div class="rulegrid">__RULES__</div>
    <div class="rulefoot">__MECHANICS__</div>
    <div class="rulefoot">__PRICEONLY__</div>
  </div>
__RISKBAR__
  <section class="kpis" data-el="kpis"></section>

  <section class="card">
    <div class="charthead">
      <span class="t">Capital, drawdown &amp; positions open</span>
      <span class="s">net of slippage &middot; hover for any day</span>
    </div>
    <div class="plot" data-el="plot">
      <svg data-el="svg" role="img" aria-label="Portfolio equity, drawdown and open positions over time"></svg>
      <div class="tip" data-el="tip"></div>
    </div>
  </section>

  <p class="note">__NOTE__</p>

  <h2 class="section-h">Per-trade statistics</h2>
  <section class="stats4" data-el="tradestats"></section>

  <div class="tradecard">
    <div class="charthead" style="padding:12px 14px 10px">
      <span class="t">All trades</span>
      <span class="s"><span data-el="tcount"></span> &middot; <span class="noprint">click a column to sort</span></span>
    </div>
    <div class="tradescroll">
      <table class="trades" data-el="ttbl"><thead data-el="thead"></thead><tbody data-el="ttbody"></tbody></table>
    </div>
  </div>

  <h2 class="section-h">By market</h2>
  <div class="tradecard">
    <div class="charthead" style="padding:12px 14px 10px">
      <span class="t">Per-market performance</span>
      <span class="s"><span data-el="mcount"></span> &middot; <span class="noprint">click a column to sort</span></span>
    </div>
    <div class="tradescroll">
      <table class="trades" data-el="mtbl"><thead data-el="mhead"></thead><tbody data-el="mbody"></tbody></table>
    </div>
  </div>
__DAILY__
  <footer class="mono">__FOOTER__</footer>
</section>"""

RISKBAR_HTML = r"""
  <section class="riskbar noprint">
    <span class="lbl">Risk per trade</span>
    <input data-el="riskin" type="number" min="0" max="100" step="0.1" value="1"
           aria-label="Risk per trade, percent of liquid capital">
    <span class="unit">% of liquid capital</span>
    <span class="warn" data-el="riskwarn"></span>
  </section>
"""

DAILY_HTML = r"""
  <details class="noprint">
    <summary>Daily data</summary>
    <div class="tscroll"><table><thead><tr>
      <th>Date</th><th>Capital</th><th>Drawdown</th><th>Open</th><th>Activity</th>
    </tr></thead><tbody data-el="tbody"></tbody></table></div>
  </details>
"""

SCRIPT = r"""<script>
const DATASETS = __DATASETS__;
const STRATS = __STRATS__;
const RISK_DEFAULT = __RISKDEF__;
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const fmtUSD = v => (v<0?"−$":"$") + Math.abs(Math.round(v)).toLocaleString("en-US");
const fmtK = v => (v<0?"−$":"$") + Math.abs(v/1000).toFixed(0) + "k";
const pct = v => (v>=0?"+":"") + v.toFixed(1) + "%";
const fmtPrice = v => { if(v==null) return "—"; const a=Math.abs(v);
  const dp = a>=100?1:a>=1?2:a>=0.01?4:6;
  return v.toLocaleString("en-US",{minimumFractionDigits:dp,maximumFractionDigits:dp}); };
const signFix = (v,d) => v==null?"—":(v>=0?"+":"−")+Math.abs(v).toFixed(d);
const signUSD = v => v==null?"—":(v>=0?"+$":"−$")+Math.abs(v).toLocaleString("en-US",{maximumFractionDigits:0});
const prettyReason = r => ({target_5r:"5R target",stop:"stop",unknown_pl:"unknown P/L",
  bullish_reversal:"bull reversal",bearish_reversal:"bear reversal",
  data_end:"data ended",open_at_end:"open at end"})[r]||r;

// ---- one strategy's report, mounted into `root` ----------------------------------
// A factory rather than top-level code: the print report mounts SEVERAL of these on one
// page, so nothing may address elements by a document-unique id.
function mountReport(root, DATA){
  const $ = k => root.querySelector('[data-el="'+k+'"]');
  const START = DATA.start;
  const DAYS = DATA.points.map(p => p.date);
  const RAW = DATA.trades;

  // ---- shared-account money management, replayed in the browser ------------------
  // A direct port of run_portfolio.py's loop. It is only possible because the trades are
  // CAPITAL-INDEPENDENT: which trades fire, their R multiples, and their slippage cost in R
  // are all fixed by price and reversals, so changing the risk % changes the dollar sizing
  // and nothing else. Rules mirrored exactly, and in this order:
  //   1) a new trade risks `risk`% of LIQUID capital = cash - risk tied up in open trades;
  //   2) cash moves ONLY when a trade closes; open trades are never marked to market;
  //   3) within a day ALL entries are sized first, THEN the exits book P&L;
  //   4) same-day entries are sized in market-name order, each off the base the earlier ones
  //      left. Plain < > comparison, not localeCompare, to match Python's sort.
  // The gross curve is replayed alongside on its own cash/committed pair -- costs change the
  // sizing base as the run compounds, so it cannot be derived from the net one afterwards.
  function simulate(risk){
    const ent = {}, exi = {};
    RAW.forEach((t,i) => {
      (ent[t.din] || (ent[t.din] = [])).push(i);
      (exi[t.xd] || (exi[t.xd] = [])).push(i);
    });
    const tr = RAW.map(t => Object.assign({}, t, {base:0, riskD:0, pnl:0, pnlpct:0}));
    let cash = START, committed = 0, peak = START, maxdd = 0;
    let gcash = START, gcommitted = 0;
    const open = {}, gopen = {}, pts = [];
    let maxOpen = 0, totalCost = 0, daysIn = 0;

    for (const day of DAYS){
      const es = (ent[day] || []).slice().sort((a,b) =>
        RAW[a].market < RAW[b].market ? -1 : RAW[a].market > RAW[b].market ? 1 : 0);
      const enotes = [];
      for (const i of es){
        const base = Math.max(cash - committed, 0), riskD = base * risk / 100;
        tr[i].base = base; tr[i].riskD = riskD;
        open[i] = riskD; committed += riskD;
        const gbase = Math.max(gcash - gcommitted, 0);
        gopen[i] = gbase * risk / 100; gcommitted += gopen[i];
        enotes.push(RAW[i].market + " " + RAW[i].side + " (risk " +
                    Math.round(riskD).toLocaleString("en-US") + ")");
      }
      const xnotes = [];
      for (const i of (exi[day] || [])){
        const riskD = open[i]; delete open[i]; committed -= riskD;
        const pnl = tr[i].r * riskD;
        cash += pnl; totalCost += tr[i].cr * riskD;
        tr[i].pnl = pnl;
        tr[i].pnlpct = tr[i].base ? pnl / tr[i].base * 100 : 0;
        const griskD = gopen[i]; delete gopen[i]; gcommitted -= griskD;
        gcash += tr[i].gr * griskD;
        xnotes.push(RAW[i].market + " " + RAW[i].reason + " (" +
          (RAW[i].reason === "open_at_end" ? "open->closed 0"
            : (pnl >= 0 ? "+" : "−") + Math.abs(Math.round(pnl)).toLocaleString("en-US")) + ")");
      }
      const nOpen = Object.keys(open).length;
      if (cash > peak) peak = cash;
      const dd = peak > 0 ? (cash - peak) / peak * 100 : 0;
      if (-dd > maxdd) maxdd = -dd;
      if (nOpen > maxOpen) maxOpen = nOpen;
      if (nOpen > 0) daysIn++;
      pts.push({date:day, cash:cash, open:nOpen, dd:dd,
                markets:Object.keys(open).map(i => RAW[i].market).sort().join(", "),
                entries:enotes.join("; "), exits:xnotes.join("; ")});
    }

    // Closed trades only, in EXIT order -- the streaks are "as they were lived".
    const closed = tr.filter(t => t.reason !== "open_at_end");
    const seq = closed.slice().sort((a,b) =>
      a.xd < b.xd ? -1 : a.xd > b.xd ? 1 :
      a.din < b.din ? -1 : a.din > b.din ? 1 :
      a.market < b.market ? -1 : a.market > b.market ? 1 : 0);
    let lw=0, ll=0, cw=0, cl=0;
    for (const t of seq){
      if (t.pnl > 0){ cw++; cl=0; } else if (t.pnl < 0){ cl++; cw=0; } else { cw=0; cl=0; }
      if (cw > lw) lw = cw;
      if (cl > ll) ll = cl;
    }
    const wins = closed.filter(t => t.pnl > 0), loss = closed.filter(t => t.pnl < 0);
    const mean = (xs,f) => xs.length ? xs.reduce((s,x) => s+f(x), 0)/xs.length : 0;
    // Win rate keys off R, not dollars, so it stays meaningful at risk = 0 (where every
    // position is sized to nothing and no trade can book a dollar of profit or loss).
    const rWins = closed.filter(t => t.r > 0).length;

    return {points:pts, trades:tr, stats:{
      final:cash, ret:(cash/START-1)*100, maxdd:-maxdd,
      rdd: maxdd > 0 ? ((cash/START-1)*100)/maxdd : null,
      gross_final:gcash, gross_ret:(gcash/START-1)*100, total_cost:totalCost,
      n_trades:closed.length,
      win_rate: closed.length ? 100*rWins/closed.length : 0,
      max_open:maxOpen,
      time_in_market: DAYS.length ? 100*daysIn/DAYS.length : 0,
      long_win:lw, long_loss:ll,
      avg_win:mean(wins,t=>t.pnl), avg_loss:mean(loss,t=>t.pnl),
      avg_win_pct:mean(wins,t=>t.pnlpct), avg_loss_pct:mean(loss,t=>t.pnlpct)
    }};
  }

  let SIM = simulate(RISK_DEFAULT);
  let P = SIM.points, N = P.length, T = SIM.trades, ST = SIM.stats;
  // Self-check: at the default risk the replay MUST reproduce the server's own figure. If it
  // ever does not, the JS port has drifted from run_portfolio.py -- say so in the console
  // rather than quietly showing different numbers from the workbook.
  if (Math.abs(ST.final - DATA.final) > 0.5){
    console.warn(DATA.strategy + ": risk replay mismatch at " + RISK_DEFAULT + "%: page " +
      ST.final.toFixed(2) + " vs server " + DATA.final.toFixed(2) +
      " -- build_equity_html.py is out of step with run_portfolio.py");
  } else {
    console.log(DATA.strategy + ": risk replay verified against run_portfolio.py");
  }

  function renderKpis(){
    const kpis = [
      ["Final capital", fmtUSD(ST.final), "", "net, from "+fmtK(START)],
      ["Total return", pct(ST.ret), ST.ret>=0?"pos":"neg", "gross "+pct(ST.gross_ret)],
      ["Max drawdown", ST.maxdd.toFixed(2)+"%", "neg", "peak to trough"],
      ["Return / DD", ST.rdd==null?"—":ST.rdd.toFixed(1)+"x", (ST.rdd!=null&&ST.rdd>=0)?"pos":"",
       "return per point of drawdown"],
      ["Time in market", ST.time_in_market.toFixed(0)+"%", "", "of trading days"],
      ["Win rate", ST.win_rate.toFixed(1)+"%", "", ST.n_trades+" trades"],
      ["Max concurrent", String(ST.max_open), "", "positions open"],
    ];
    $("kpis").innerHTML = kpis.map(k =>
      `<div class="kpi"><span class="k">${k[0]}</span><span class="v ${k[2]} mono">${k[1]}</span>`+
      `<span class="sub">${k[3]}</span></div>`).join("");
  }

  function renderDaily(){
    const el = $("tbody");
    if (!el) return;                       // the print report omits the daily table
    el.innerHTML = P.map(p => {
      const act = [p.entries?`<span style="color:var(--pos)">${p.entries}</span>`:"",
                   p.exits?`<span style="color:var(--neg)">${p.exits}</span>`:""].filter(Boolean).join(" &nbsp; ");
      return `<tr><td class="mono">${p.date}</td><td class="mono">${fmtUSD(p.cash)}</td>`+
        `<td class="mono ${p.dd<0?'neg':''}">${p.dd.toFixed(2)}%</td>`+
        `<td class="mono">${p.open}</td><td style="text-align:left;white-space:normal;font-size:11px">${act||"&mdash;"}</td></tr>`;
    }).join("");
  }

  function renderTradeStats(){
    const TS = [
      ["Average win", fmtUSD(ST.avg_win), "pos", "+"+ST.avg_win_pct.toFixed(2)+"% per win"],
      ["Average loss", fmtUSD(ST.avg_loss), "neg", ST.avg_loss_pct.toFixed(2)+"% per loss"],
      ["Average winner", (DATA.avg_win_r>=0?"+":"")+DATA.avg_win_r.toFixed(2)+"R", "pos",
       "best "+(DATA.best_r>=0?"+":"")+DATA.best_r.toFixed(2)+"R"],
      ["Average hold", DATA.avg_bars.toFixed(1)+"d", "", "bars per closed trade"],
      ["Longest win streak", String(ST.long_win), "pos", "consecutive wins"],
      ["Longest loss streak", String(ST.long_loss), "neg", "consecutive losses"],
    ];
    $("tradestats").innerHTML = TS.map(k =>
      `<div class="kpi"><span class="k">${k[0]}</span><span class="v ${k[2]} mono">${k[1]}</span>`+
      `<span class="sub">${k[3]}</span></div>`).join("");
  }

  const COLS = [
    {k:"market",l:"Market",t:"s",w:15},{k:"side",l:"Side",t:"s",w:6},
    {k:"din",l:"In",t:"d",w:8.5},{k:"dout",l:"Out",t:"d",w:8.5},{k:"bars",l:"Bars",t:"n",w:5},
    {k:"pin",l:"In",t:"n",f:fmtPrice,w:8},{k:"pout",l:"Out",t:"n",f:fmtPrice,w:8},
    {k:"sl",l:"Stop",t:"n",f:fmtPrice,w:8},{k:"r",l:"R",t:"n",f:v=>signFix(v,2),color:1,w:6.5},
    {k:"pnl",l:"P&L $",t:"n",f:signUSD,color:1,w:8},
    {k:"pnlpct",l:"P&L %",t:"n",f:v=>signFix(v,2)+"%",color:1,w:8},
    {k:"reason",l:"Reason",t:"s",f:prettyReason,w:10.5},
  ];
  $("ttbl").insertAdjacentHTML("afterbegin",
    "<colgroup>"+COLS.map(c=>`<col style="width:${c.w}%">`).join("")+"</colgroup>");
  let sortKey="din", sortDir=1;
  function renderHead(){
    $("thead").innerHTML = "<tr>"+COLS.map(c=>{
      const on=c.k===sortKey, ar=on?`<span class="ar">${sortDir>0?"▲":"▼"}</span>`:"";
      return `<th data-k="${c.k}" class="${c.t!=='n'?'l':''}${on?' sorted':''}">${c.l}${ar}</th>`;
    }).join("")+"</tr>";
    root.querySelectorAll('[data-el="thead"] th').forEach(th => th.onclick = () => {
      const k = th.dataset.k;
      if (k===sortKey) sortDir=-sortDir; else { sortKey=k; sortDir=(COLS.find(c=>c.k===k).t==="n")?-1:1; }
      renderHead(); renderRows();
    });
  }
  function renderRows(){
    const col = COLS.find(c=>c.k===sortKey);
    const rows = [...T].sort((a,b)=>{
      let x=a[sortKey], y=b[sortKey];
      if(x==null&&y==null)return 0; if(x==null)return 1; if(y==null)return -1;
      return (col.t==="n" ? (x-y) : String(x).localeCompare(String(y)))*sortDir;
    });
    $("ttbody").innerHTML = rows.map(t=>"<tr>"+COLS.map(c=>{
      const v=t[c.k], disp=c.f?c.f(v):(v==null?"—":v);
      let cls=(c.t==="n")?"mono":"l";
      if(c.color&&v!=null) cls+=v>0?" pos":v<0?" neg":"";
      return `<td class="${cls}">${disp}</td>`;
    }).join("")+"</tr>").join("");
  }

  // ---- per-market analysis (aggregated from the trades, excluding open-at-end) -----
  // Rebuilt on every risk change: the R columns are risk-independent but the P&L column and
  // its bar are not, so the table has to be re-aggregated rather than just re-sorted.
  let MK=[], maxAbsPnl=1;
  function mBuild(){
    const byM={};
    // Seed EVERY market that was backtested, so the ones the rules never fired on appear as
    // zeros instead of vanishing. "No trade here" is a result, and a table listing only the
    // markets that traded reads as though the others were never researched.
    const blank = m => ({market:m, obs:false, n:0, wins:0, pnl:0, totalr:0, best:null, worst:null});
    (DATA.markets_all || []).forEach(u => { byM[u.m] = Object.assign(blank(u.m), {obs:!!u.obs}); });
    for(const t of T){ if(t.reason==="open_at_end") continue;
      const m = byM[t.market] || (byM[t.market] = blank(t.market));
      m.n++; if(t.pnl>0)m.wins++; m.pnl+=t.pnl; m.totalr+=t.r;
      m.best = m.best==null ? t.r : Math.max(m.best,t.r);
      m.worst = m.worst==null ? t.r : Math.min(m.worst,t.r);
    }
    // Sums stay 0 for an untraded market (truthfully nothing); ratios and extremes are
    // UNDEFINED there, so they are null and print as an em dash rather than a fake 0%.
    MK=Object.values(byM).map(m=>Object.assign(m,{
      winrate: m.n ? 100*m.wins/m.n : null,
      avgr: m.n ? m.totalr/m.n : null}));
    maxAbsPnl=Math.max(1,...MK.map(m=>Math.abs(m.pnl)));
    const traded = MK.filter(m => m.n > 0).length;
    $("mcount").textContent = MK.length+" markets · "+traded+" with trades";
  }
  const MCOLS = [
    // An obsolete market stopped being collected, which is usually WHY it has no trades --
    // worth saying on the row rather than leaving the reader to wonder.
    {k:"market",l:"Market",t:"s",w:22,
     rowf:m => m.market + (m.obs ? '<span class="tag">obsolete</span>' : '')},
    {k:"n",l:"Trades",t:"n",w:9},
    {k:"winrate",l:"Win %",t:"n",f:v=>v==null?"—":v.toFixed(0)+"%",w:10},
    {k:"pnl",l:"P&L $",t:"n",f:signUSD,bar:1,w:22},
    {k:"totalr",l:"Total R",t:"n",f:v=>signFix(v,2),color:1,w:11},
    {k:"avgr",l:"Avg R",t:"n",f:v=>signFix(v,2),color:1,w:10},
    {k:"best",l:"Best R",t:"n",f:v=>signFix(v,2),w:8},{k:"worst",l:"Worst R",t:"n",f:v=>signFix(v,2),w:8},
  ];
  $("mtbl").insertAdjacentHTML("afterbegin",
    "<colgroup>"+MCOLS.map(c=>`<col style="width:${c.w}%">`).join("")+"</colgroup>");
  function pnlBar(v){ const frac=Math.min(Math.abs(v)/maxAbsPnl,1)*50, pos=v>=0;
    return `<div class="${v>0?'pos':v<0?'neg':''}">${signUSD(v)}</div>`+
      `<div class="dbar"><span class="z"></span><i style="left:${(pos?50:50-frac).toFixed(1)}%;`+
      `width:${frac.toFixed(1)}%;background:${pos?'var(--pos)':'var(--neg)'}"></i></div>`; }
  let mKey="pnl", mDir=-1;
  function mHead(){
    $("mhead").innerHTML = "<tr>"+MCOLS.map(c=>{
      const on=c.k===mKey, ar=on?`<span class="ar">${mDir>0?"▲":"▼"}</span>`:"";
      return `<th data-k="${c.k}" class="${c.t!=='n'?'l':''}${on?' sorted':''}">${c.l}${ar}</th>`;
    }).join("")+"</tr>";
    root.querySelectorAll('[data-el="mhead"] th').forEach(th => th.onclick = () => {
      const k = th.dataset.k;
      if (k===mKey) mDir=-mDir; else { mKey=k; mDir=(MCOLS.find(c=>c.k===k).t==="n")?-1:1; }
      mHead(); mRows();
    });
  }
  function mRows(){
    const col = MCOLS.find(c=>c.k===mKey);
    // Untraded markets carry nulls in the ratio columns; they sort LAST whichever way the
    // column is pointed, so they never push the real rows off the top.
    const rows = [...MK].sort((a,b)=>{ const x=a[mKey],y=b[mKey];
      if(x==null&&y==null)return 0; if(x==null)return 1; if(y==null)return -1;
      return (col.t==="n"?(x-y):String(x).localeCompare(String(y)))*mDir; });
    $("mbody").innerHTML = rows.map(m=>"<tr>"+MCOLS.map(c=>{
      const v=m[c.k];
      const disp = c.bar ? pnlBar(v) : (c.rowf ? c.rowf(m) : (c.f ? c.f(v) : v));
      let cls=(c.t==="n")?"mono":"l"; if(c.color&&v!=null) cls+=v>0?" pos":v<0?" neg":"";
      return `<td class="${cls}">${disp}</td>`;
    }).join("")+"</tr>").join("");
  }

  function niceTicks(min,max,n){
    const raw=(max-min)/n, mag=Math.pow(10,Math.floor(Math.log10(raw))), norm=raw/mag;
    let step = norm<1.5?1:norm<3?2:norm<7?5:10; step*=mag;
    const out=[]; for(let v=Math.ceil(min/step)*step; v<=max+1e-6; v+=step) out.push(v);
    return out;
  }

  const svg=$("svg"), plot=$("plot"), tip=$("tip");
  const NS="http://www.w3.org/2000/svg";
  const mk=(t,a)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
  let geom=null, firstDraw=true;

  function txt(x,y,s,anchor,size,fill,ls){
    const t=mk("text",{x:x,y:y,"font-size":size,fill:fill});
    if(anchor)t.setAttribute("text-anchor",anchor); if(ls)t.setAttribute("letter-spacing",ls);
    t.textContent=s; return t;
  }

  function render(){
    const W=plot.clientWidth||880;
    const padT=14, mainH=262, gap=16, ddH=60, posH=60, xAxisH=22;
    const mainBot=padT+mainH, ddTop=mainBot+gap, ddBot=ddTop+ddH;
    const posTop=ddBot+gap, posBot=posTop+posH, H=posBot+xAxisH;
    const mL=58, mR=18, plotW=W-mL-mR;
    svg.setAttribute("viewBox",`0 0 ${W} ${H}`); svg.setAttribute("height",H);
    while(svg.firstChild) svg.removeChild(svg.firstChild);

    const cash=P.map(p=>p.cash);
    const lo=Math.min(...cash,START), hi=Math.max(...cash);
    // At risk = 0 nothing moves, so the range collapses and every y would divide by zero.
    const span=(hi-lo) || Math.max(1, Math.abs(hi)*0.02);
    const yMin=lo-span*0.06, yMax=hi+span*0.10;
    const x=i=> mL + (N<=1?0:i/(N-1))*plotW;
    const y=v=> padT + mainH - (v-yMin)/(yMax-yMin)*mainH;
    const ddLo=Math.min(...P.map(p=>p.dd),-0.5), yd=v=> ddTop + (-v)/(-ddLo)*ddH;
    const maxOpen=Math.max(ST.max_open,1), yp=v=> posBot - (v/maxOpen)*posH;

    niceTicks(yMin,yMax,5).forEach(v=>{ if(v<yMin||v>yMax)return;
      svg.appendChild(mk("line",{x1:mL,x2:W-mR,y1:y(v),y2:y(v),stroke:"var(--grid)","stroke-width":1}));
      const t=mk("text",{x:mL-9,y:y(v)+3.5,"text-anchor":"end","font-size":11,fill:"var(--ink3)"});
      t.textContent=fmtK(v); svg.appendChild(t);
    });
    // starting-capital reference
    svg.appendChild(mk("line",{x1:mL,x2:W-mR,y1:y(START),y2:y(START),stroke:"var(--ref)",
      "stroke-width":1.2,"stroke-dasharray":"3 4"}));
    const rl=mk("text",{x:mL+4,y:y(START)-5,"font-size":10,fill:"var(--ink3)"});
    rl.textContent=fmtK(START)+" start"; svg.appendChild(rl);

    let lastM=-1;
    P.forEach((p,i)=>{const m=+p.date.slice(5,7)-1;
      if(m!==lastM){lastM=m;
        if(i>1) svg.appendChild(mk("line",{x1:x(i),x2:x(i),y1:padT,y2:posBot,stroke:"var(--grid)","stroke-width":1}));
        const t=mk("text",{x:x(i),y:H-6,"text-anchor":"middle","font-size":11,fill:"var(--ink3)"});
        t.textContent=MONTHS[m]+(m===0?" '26":""); svg.appendChild(t);
      }});

    const lp=P.map((p,i)=>`${x(i).toFixed(1)},${y(p.cash).toFixed(1)}`);
    svg.appendChild(mk("path",{d:`M${x(0)},${y(yMin)} L`+lp.join(" L")+` L${x(N-1)},${y(yMin)} Z`,fill:"var(--accent-soft)"}));
    const line=mk("path",{d:"M"+lp.join(" L"),fill:"none",stroke:"var(--accent-line)","stroke-width":2,
      "stroke-linejoin":"round","stroke-linecap":"round"});
    svg.appendChild(line);

    svg.appendChild(mk("line",{x1:mL,x2:W-mR,y1:yd(0),y2:yd(0),stroke:"var(--grid)","stroke-width":1}));
    const ddp=P.map((p,i)=>`${x(i).toFixed(1)},${yd(p.dd).toFixed(1)}`);
    svg.appendChild(mk("path",{d:`M${x(0)},${yd(0)} L`+ddp.join(" L")+` L${x(N-1)},${yd(0)} Z`,fill:"var(--neg-soft)"}));
    svg.appendChild(mk("path",{d:"M"+ddp.join(" L"),fill:"none",stroke:"var(--neg)","stroke-width":1.4}));
    svg.appendChild(txt(mL-9,yd(ddLo)+3.5,ddLo.toFixed(0)+"%","end",10,"var(--ink3)"));
    svg.appendChild(txt(mL+4,ddTop-5,"DRAWDOWN","start",10.5,"var(--ink3)",".04em"));

    svg.appendChild(mk("line",{x1:mL,x2:W-mR,y1:posBot,y2:posBot,stroke:"var(--grid)","stroke-width":1}));
    const barW=Math.max(1.6,Math.min(7,plotW/N*0.72));
    P.forEach((p,i)=>{ if(p.open>0){ const by=yp(p.open);
      svg.appendChild(mk("rect",{x:(x(i)-barW/2).toFixed(1),y:by.toFixed(1),width:barW.toFixed(1),
        height:(posBot-by).toFixed(1),fill:"var(--bars)",rx:1,opacity:.85})); }});
    svg.appendChild(txt(mL-9,yp(maxOpen)+3.5,String(maxOpen),"end",10,"var(--ink3)"));
    svg.appendChild(txt(mL-9,posBot+3.5,"0","end",10,"var(--ink3)"));
    svg.appendChild(txt(mL+4,posTop-5,"POSITIONS OPEN","start",10.5,"var(--ink3)",".04em"));

    const ex=x(N-1), ey=y(cash[N-1]);
    svg.appendChild(mk("circle",{cx:ex,cy:ey,r:4,fill:"var(--accent-line)",stroke:"var(--surface)","stroke-width":2}));
    const el=txt(ex-8,ey-9,fmtUSD(cash[N-1]),"end",12.5,"var(--ink)"); el.setAttribute("font-weight",600);
    svg.appendChild(el);

    const cross=mk("line",{x1:0,x2:0,y1:padT,y2:posBot,stroke:"var(--ink2)","stroke-width":1,"stroke-dasharray":"2 3",opacity:0});
    const dot=mk("circle",{r:4.5,fill:"var(--accent-line)",stroke:"var(--surface)","stroke-width":2,opacity:0});
    const ddot=mk("circle",{r:3.5,fill:"var(--neg)",stroke:"var(--surface)","stroke-width":1.5,opacity:0});
    svg.appendChild(cross);svg.appendChild(dot);svg.appendChild(ddot);

    // Draw-on animation only on the FIRST paint. Re-running it on every risk keystroke would
    // make the curve flicker instead of letting you watch the shape change.
    if(firstDraw && !matchMedia("(prefers-reduced-motion:reduce)").matches){
      const len=line.getTotalLength(); line.style.strokeDasharray=len; line.style.strokeDashoffset=len;
      line.animate([{strokeDashoffset:len},{strokeDashoffset:0}],{duration:900,easing:"cubic-bezier(.4,0,.1,1)",fill:"forwards"});
    }
    firstDraw=false;
    geom={W,mL,plotW,x,y,yd,ex,ey,cross,dot,ddot};
  }

  function move(ev){
    if(!geom)return;
    const r=plot.getBoundingClientRect(), scale=geom.W/r.width;
    let i=Math.round(((ev.clientX-r.left)*scale-geom.mL)/geom.plotW*(N-1));
    i=Math.max(0,Math.min(N-1,i));
    const p=P[i], cx=geom.x(i), cy=geom.y(p.cash);
    geom.cross.setAttribute("x1",cx);geom.cross.setAttribute("x2",cx);geom.cross.setAttribute("opacity",1);
    geom.dot.setAttribute("cx",cx);geom.dot.setAttribute("cy",cy);geom.dot.setAttribute("opacity",1);
    geom.ddot.setAttribute("cx",cx);geom.ddot.setAttribute("cy",geom.yd(p.dd));geom.ddot.setAttribute("opacity",1);
    let ev2="";
    if(p.entries) ev2+=`<div class="in">&#9650; ${p.entries}</div>`;
    if(p.exits) ev2+=`<div class="out">&#9660; ${p.exits}</div>`;
    const mkline = p.open>0 && p.markets ? `<div class="mk">in: ${p.markets}</div>` : "";
    tip.innerHTML=`<div class="d">${p.date}</div>`+
      `<div class="row"><span>Capital</span><b class="mono">${fmtUSD(p.cash)}</b></div>`+
      `<div class="row"><span>Drawdown</span><b class="mono">${p.dd.toFixed(2)}%</b></div>`+
      `<div class="row"><span>Positions open</span><b class="mono">${p.open}</b></div>`+
      mkline + (ev2?`<div class="ev">${ev2}</div>`:"");
    tip.style.opacity=1;
    const tw=tip.offsetWidth, th=tip.offsetHeight;
    let lx=(cx/scale)+14; if(lx+tw>r.width) lx=(cx/scale)-tw-14;
    let ly=(cy/scale)-th-6; if(ly<0) ly=(cy/scale)+14;
    tip.style.left=lx+"px"; tip.style.top=ly+"px";
  }
  function leave(){ if(!geom)return;
    geom.cross.setAttribute("opacity",0);geom.dot.setAttribute("opacity",0);geom.ddot.setAttribute("opacity",0);
    tip.style.opacity=0;
  }
  plot.addEventListener("pointermove",move);
  plot.addEventListener("pointerleave",leave);

  function renderAll(){
    renderKpis(); renderDaily(); renderTradeStats();
    $("tcount").textContent = T.length+" trades";
    renderHead(); renderRows(); mBuild(); mHead(); mRows(); render();
  }
  function setRisk(r){
    SIM = simulate(r); P = SIM.points; N = P.length; T = SIM.trades; ST = SIM.stats;
    renderAll();
  }
  new ResizeObserver(render).observe(plot);
  renderAll();
  return {setRisk:setRisk, render:render, stats:()=>ST};
}

// ---- mount every section on this page --------------------------------------------
const ROOTS = Array.prototype.slice.call(document.querySelectorAll("[data-root]"));
const INST = ROOTS.map((el,i) => mountReport(el, DATASETS[i]));

// ---- risk control (one per page, drives every mounted strategy) -------------------
const riskIn = document.querySelector('[data-el="riskin"]');
const riskWarn = document.querySelector('[data-el="riskwarn"]');
function applyRisk(v, typed){
  let r = Number(v);
  if (!isFinite(r)) r = RISK_DEFAULT;
  r = Math.min(100, Math.max(0, r));
  // Do not rewrite the field while it is being typed into -- that would fight the caret.
  if (riskIn && !typed) riskIn.value = String(r);
  INST.forEach(inst => inst.setRisk(r));
  document.querySelectorAll(".riskecho").forEach(e => { e.textContent = r + "%"; });
  if (riskWarn){
    // Above a few percent the sizing model stops describing anything tradeable: it assumes
    // any position size fills at these prices, and it has no margin, no liquidity limit and
    // no ruin -- a losing streak just shrinks the base forever instead of ending the account.
    const worst = Math.max.apply(null, INST.map(i => i.stats().long_loss));
    riskWarn.textContent = r > 5
      ? "At " + r + "% per trade the model ignores margin, liquidity and ruin: 1R = " + r +
        "% of the account, and the " + worst + "-trade losing streak below is survived only " +
        "because positions shrink with the balance. Read as arithmetic, not a plan."
      : "";
  }
}
if (riskIn){
  // An empty field mid-edit (select-all then retype) is left alone rather than treated as 0 --
  // otherwise the whole page would flash to a flat curve between keystrokes.
  riskIn.addEventListener("input", () => { if (riskIn.value !== "") applyRisk(riskIn.value, true); });
}
applyRisk(RISK_DEFAULT);

// Re-measure before printing: the print layout is a different width from the screen, and the
// SVG viewBox is computed from the live element width.
window.addEventListener("beforeprint", () => INST.forEach(i => i.render()));
__BOOT__
</script>"""

# The PDF picker, only on the interactive pages.
PDF_SCRIPT = r"""
// ---- Export PDF: pick strategies, open the print report ---------------------------
// No PDF library is bundled. The browser's own print-to-PDF gives selectable vector text at
// a fraction of the size that an html2canvas-style rasteriser would produce, so the button
// opens report.html for the chosen strategies and lets it call window.print().
const pdfBtn = document.querySelector('[data-el="pdfopen"]');
if (pdfBtn) pdfBtn.addEventListener("click", () => {
  const here = document.body.dataset.strategy;
  const picked = {};
  STRATS.forEach(s => { picked[s.key] = (s.key === here); });   // current one pre-ticked
  const mask = document.createElement("div");
  mask.className = "mask";
  mask.innerHTML =
    '<div class="dlg"><h4>Export PDF</h4>' +
    '<p>Choose the strategies to include. They print one per page, in this order, at the ' +
    'risk currently set on the page.</p><div class="dlglist">' +
    STRATS.map(s => '<label class="dlgrow"><input type="checkbox" data-s="' + s.key + '">' +
      '<span class="nm">' + s.title + '<span class="sb">' + s.rule4 + '</span></span></label>').join("") +
    '</div><div class="dlgbtns"><button data-a="all">Select all</button>' +
    '<button data-a="cancel">Cancel</button>' +
    '<button class="pri" data-a="ok">Open PDF</button></div></div>';
  const boxes = () => Array.prototype.slice.call(mask.querySelectorAll("input[data-s]"));
  boxes().forEach(cb => {
    cb.checked = !!picked[cb.dataset.s];
    cb.addEventListener("change", () => { picked[cb.dataset.s] = cb.checked; });
  });
  function close(){ document.removeEventListener("keydown", onKey, true); mask.remove(); }
  function ok(){
    const keys = STRATS.map(s => s.key).filter(k => picked[k]);
    if (!keys.length) return;                       // nothing ticked: refuse rather than open a blank report
    const risk = riskIn ? Number(riskIn.value) : RISK_DEFAULT;
    close();
    window.open("report.html?s=" + keys.join(",") + "&risk=" + risk + "&auto=1", "_blank");
  }
  function onKey(e){
    if (e.key === "Escape"){ e.stopPropagation(); close(); }
    else if (e.key === "Enter"){ e.stopPropagation(); ok(); }
  }
  mask.querySelector('[data-a="all"]').addEventListener("click", () => {
    STRATS.forEach(s => { picked[s.key] = true; });
    boxes().forEach(cb => { cb.checked = true; });
  });
  mask.querySelector('[data-a="ok"]').addEventListener("click", ok);
  mask.querySelector('[data-a="cancel"]').addEventListener("click", close);
  mask.addEventListener("mousedown", e => { if (e.target === mask) close(); });
  document.addEventListener("keydown", onKey, true);
  document.body.appendChild(mask);
});
"""

# report.html: honour ?s=<keys>&risk=<n>&auto=1, then offer the print dialog.
REPORT_SCRIPT = r"""
// ---- report page: show only the requested strategies, then print ------------------
const params = new URLSearchParams(location.search);
const want = (params.get("s") || "").split(",").filter(Boolean);
if (want.length){
  ROOTS.forEach((el, i) => {
    if (want.indexOf(DATASETS[i].strategy) < 0) el.remove();
  });
}
const rp = Number(params.get("risk"));
if (isFinite(rp) && rp >= 0){
  if (riskIn) riskIn.value = String(rp);
  applyRisk(rp);
}
document.querySelectorAll(".repcount").forEach(e => {
  const n = document.querySelectorAll("[data-root]").length;
  e.textContent = n + (n === 1 ? " strategy" : " strategies");
});
const printBtn = document.querySelector('[data-el="printnow"]');
if (printBtn) printBtn.addEventListener("click", () => window.print());
// Auto-open the print dialog when arrived at from the Export PDF button. Deferred a frame so
// the charts have laid out at their printed width first.
if (params.get("auto") === "1"){
  window.addEventListener("load", () => setTimeout(() => window.print(), 350));
}
"""


def page_path(strategy):
    return eng.OUT_DIR / f"equity_{strategy.key}.html"


REPORT_PATH = eng.OUT_DIR / "report.html"


def month_year(iso):
    """2025-12-15 -> Dec 2025."""
    y, m, _ = iso.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def nav_html(current):
    """The strategy switcher: one button per registered strategy, current one filled."""
    out = []
    for s in strategies.REGISTRY:
        cls = " class=\"on\"" if s.key == current.key else ""
        out.append(f'<a href="{page_path(s).name}"{cls}>{s.title}'
                   f'<span class="sub">{s.rule4}</span></a>')
    return "".join(out)


def rules_html(strategy):
    """The four rule cards -- 1-3 shared, 4 this strategy's."""
    return "".join(
        f'<div class="rule"><span class="n">{n}</span><div>'
        f'<div class="rn">Rule {n} &middot; {name}</div>'
        f'<div class="rt">{text}</div></div></div>'
        for n, name, text in strategy.rules())


def load_data(strategy):
    src = eng.OUT_DIR / f"_equity_{strategy.key}.json"
    if not src.exists():
        raise SystemExit(f"missing {src} -- run: python run_portfolio.py {strategy.key}")
    return json.loads(src.read_text())


def section_html(strategy, data, riskbar, daily):
    slip = data.get("slippage", {})
    eyebrow = (f"{strategy.title} strategy &middot; daily &middot; "
               f"shared ${eng.STARTING_CAPITAL / 1000:.0f}k account")
    # NOTE: no "time and price" here. These strategies read the reversal levels only; the
    # aggregate/timing side of the Socrates method is not involved, and saying otherwise
    # misled a first-time reader (user, 2026-07-25).
    # n_markets_all is the RESEARCHED universe; n_markets is how many produced a trade. The
    # page used to print only the latter, which read as though the rest were never tested.
    n_all = data.get("n_markets_all", data["n_markets"])
    lede = (f"{strategy.lede} One shared account trading Socrates <b>reversal levels</b>. "
            f"All <b>{n_all} markets</b> in the archive were tested, "
            f"{month_year(data['first'])} &ndash; {month_year(data['last'])}; the rules "
            f"fired on <b>{data['n_markets']}</b> of them, and the rest are listed with zero "
            f"trades under <em>By market</em>. Capital moves only when a trade closes; each "
            f"new trade risks <span class=\"riskecho\">{eng.RISK_PCT:g}%</span> of liquid "
            f"capital. Figures are net of realistic slippage.")
    note = (f"<b>Backtest, net of slippage.</b> Costs are charged as tick slippage "
            f"&mdash; {slip.get('entry', 1)} tick on entry, {slip.get('target', 1)} on a "
            f"limit take-profit, {slip.get('stop', 3)} on a stop &mdash; converted to R "
            f"through each trade's own risk distance. Still optimistic on the rest: the "
            f"entry-day intraday path is assumed favorable, {strategy.caveat}, and there "
            f"is no commission or funding. Read it as evidence of an edge, not a return "
            f"forecast.")
    footer = (f"source: {strategy.key}_portfolio_daily.xlsx &middot; "
              f"{n_all} markets tested, {data['n_markets']} traded &middot; "
              f"rule 4: {strategy.rule4} &middot; "
              f"per-market one-position-at-a-time, portfolio-level concurrency")
    return (SECTION_HTML
            .replace("__EYEBROW__", eyebrow)
            .replace("__H1__", f"{strategy.title} &mdash; portfolio equity curve")
            .replace("__LEDE__", lede)
            .replace("__RULES__", rules_html(strategy))
            .replace("__MECHANICS__", strategies.ENTRY_MECHANICS)
            .replace("__PRICEONLY__", strategies.PRICE_ONLY_NOTE)
            .replace("__RISKBAR__", riskbar)
            .replace("__NOTE__", note)
            .replace("__DAILY__", daily)
            .replace("__FOOTER__", footer))


def strat_meta():
    return json.dumps([{"key": s.key, "title": s.title, "rule4": s.rule4}
                       for s in strategies.REGISTRY], separators=(",", ":"))


def script_html(datasets, boot):
    return (SCRIPT
            .replace("__DATASETS__", json.dumps(datasets, separators=(",", ":")))
            .replace("__STRATS__", strat_meta())
            .replace("__RISKDEF__", f"{eng.RISK_PCT:g}")
            .replace("__BOOT__", boot))


def build(strategy):
    """One interactive page for `strategy`."""
    data = load_data(strategy)
    body = (f'<div class="wrap">\n<nav class="nav noprint"><span class="lbl">Strategy</span>'
            f'{nav_html(strategy)}'
            f'<button class="pdfbtn" data-el="pdfopen" type="button">Export PDF</button></nav>\n'
            + section_html(strategy, data, RISKBAR_HTML, DAILY_HTML) + "\n</div>")
    html = (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>{strategy.title} &mdash; portfolio equity curve</title>\n{CSS}\n</head>\n'
            f'<body data-strategy="{strategy.key}">\n{body}\n'
            f'{script_html([data], PDF_SCRIPT)}\n</body>\n</html>\n')
    path = page_path(strategy)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    print(f"wrote {path.name}  {len(html):,} bytes")


def build_report(picked):
    """report.html -- every strategy in one document, filtered by ?s= and printed to PDF."""
    datasets = [load_data(s) for s in picked]
    sections = "\n".join(section_html(s, d, "", "") for s, d in zip(picked, datasets))
    head = (
        '<div class="wrap">\n'
        '<nav class="nav noprint"><span class="lbl">Report</span>'
        '<span style="font-size:13px;color:var(--ink2)">'
        '<span class="repcount"></span> &middot; print or save as PDF</span>'
        '<button class="pdfbtn" data-el="printnow" type="button">Print / Save as PDF</button>'
        '</nav>\n'
        + RISKBAR_HTML.replace('class="riskbar noprint"', 'class="riskbar noprint"') + "\n")
    html = (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>Strategy report</title>\n{CSS}\n</head>\n<body>\n'
            f'{head}{sections}\n</div>\n'
            f'{script_html(datasets, REPORT_SCRIPT)}\n</body>\n</html>\n')
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(html, encoding="utf-8")
    print(f"wrote {REPORT_PATH.name}  {len(html):,} bytes  "
          f"({', '.join(s.key for s in picked)})")


def main(argv):
    for s in strategies.selected(argv):
        build(s)
    # The report always carries EVERY strategy that has results, whichever pages were built:
    # the picker filters it client-side, so a partial rebuild must not shrink it.
    have = [s for s in strategies.REGISTRY
            if (eng.OUT_DIR / f"_equity_{s.key}.json").exists()]
    if have:
        build_report(have)


if __name__ == "__main__":
    main(sys.argv[1:])
