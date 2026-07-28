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
#   python build_equity_html.py quickfixpro   # just one page (report.html still gets all)
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
.navbtns{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap;}
.pdfbtn{padding:8px 14px;border-radius:9px;border:1px solid var(--border);
  background:var(--surface);color:var(--ink2);font-size:13px;font-weight:600;cursor:pointer;
  font-family:inherit;}
.pdfbtn:hover{border-color:var(--accent);color:var(--ink);}
/* conclusions editor */
.cfield{margin-top:22px;}
.cfield label{display:block;font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);font-weight:600;margin-bottom:7px;}
.cfield textarea{width:100%;min-height:230px;padding:14px 16px;font:15px/1.6 inherit;
  font-family:"Segoe UI",-apple-system,BlinkMacSystemFont,Roboto,Helvetica,Arial,sans-serif;
  color:var(--ink);background:var(--surface);border:1px solid var(--border);
  border-radius:12px;resize:vertical;}
.cfield textarea:focus{outline:none;border-color:var(--accent);}
.cbar{display:flex;align-items:center;gap:12px;margin-top:18px;}
.cbar .status{font-size:12px;color:var(--ink3);}
/* conclusions as printed at the end of the report */
.concl{margin-top:38px;padding-top:6px;}
.conclbody{white-space:pre-wrap;font-size:14px;color:var(--ink2);line-height:1.65;
  padding:14px 18px;background:var(--surface);border:1px solid var(--border);
  border-radius:12px;}
header{margin-bottom:26px;}
.eyebrow{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);
  font-weight:600;margin-bottom:12px;}
h1{font-size:clamp(26px,4.4vw,40px);line-height:1.08;margin:0 0 12px;letter-spacing:-.02em;
  text-wrap:balance;font-weight:650;}
/* No max-width: the lede and the honesty note run the full column so their left and right
   edges line up with the rule cards, KPI row and tables below them. */
.lede{color:var(--ink2);font-size:15px;margin:0;}
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
.riskbar .hint{font-size:11.5px;color:var(--ink3);}
.riskbar .hint:empty{display:none}
.riskbar .hint b{color:var(--ink2);font-weight:600;}
/* Rule 4's cap dial. Sits directly under the rule cards because it IS Rule 4, and unlike
   the risk control there is one PER STRATEGY -- Rule 4 is what tells the strategies apart,
   so a single shared dial would collapse them onto each other on the report. */
.capbar{margin-top:-1px;border-top-left-radius:0;border-top-right-radius:0;}
.capbar .nocap{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--ink2);
  cursor:pointer;user-select:none;}
.capbar .nocap input{width:14px;height:14px;accent-color:var(--accent);cursor:pointer;}
.capbar input[type=number]:disabled{opacity:.4;cursor:not-allowed;}
.capbar .hint{flex-basis:100%;font-size:11.5px;color:var(--ink3);}
.capbar .hint:empty{display:none}
.capbar .hint b{color:var(--ink2);font-weight:600;}
/* the rules block and its dial read as one object */
.rules:has(+ .capbar){border-bottom-left-radius:0;border-bottom-right-radius:0;}
/* the cap sweep sits right under the dial: it is what the dial does, across the whole grid */
.sweepcard{margin-top:14px;}
.sweepplot{min-height:210px;}
.chartnote{margin:0;padding:0 14px 4px;font-size:12px;color:var(--ink3);line-height:1.5;
  max-width:78ch;}
.chartnote b{color:var(--ink2);font-weight:600;}
/* the chart's own reading, generated from the chart so it cannot go stale */
.findings{padding:6px 14px 14px;max-width:86ch;}
.findings h4{margin:15px 0 3px;font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);font-weight:600;}
.findings p{margin:0;font-size:13px;color:var(--ink2);line-height:1.55;}
.findings b{color:var(--ink);font-weight:600;}
/* the one finding the whole report exists to make, marked as such (user, 2026-07-28).
   print-color-adjust:exact is already set on the page, so it survives the PDF. */
.hl{background:#FFE86B;color:#16201C;padding:1px 5px;border-radius:4px;font-weight:700;}
@media (prefers-color-scheme:dark){.hl{background:#F2D34A;color:#16201C;}}
:root[data-theme="dark"] .hl{background:#F2D34A;color:#16201C;}
:root[data-theme="light"] .hl{background:#FFE86B;color:#16201C;}
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
.note{margin:22px 0 0;padding:14px 18px;background:var(--accent-soft);
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
  /* the cap dial is one of those, and :has(+ .capbar) still matches a hidden sibling --
     give the rules block its bottom corners back rather than leaving them squared off */
  .rules{border-bottom-left-radius:12px!important;border-bottom-right-radius:12px!important;}
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

# One strategy's whole report. Mounted by the script below; __DAILY__ is filled on the
# interactive page and left empty on the print report (no 179-row daily table per strategy).
#
# The Rule 4 cap dial and the RISK dial are both part of the section on both page types,
# because both belong to the strategy rather than to the document. One shared cap dial would
# make every strategy on a report identical -- the cap IS what tells them apart -- and one
# shared risk box could not show three numbers, since each strategy's default risk is the one
# that puts THAT strategy at the 6% drawdown budget. (Risk was page-level until 2026-07-27,
# when the defaults stopped being the same number.)
SECTION_HTML = r"""<section class="rep" data-root>
  <header>
    <div class="eyebrow">__EYEBROW__</div>
    <h1>__H1__</h1>
    <p class="lede">__LEDE__</p>
  </header>

  <div class="rules">
    <div class="rhead">
      <div class="t">How a trade is found</div>
      <div class="s">Described for a short; the long side is the exact mirror, bearish
        levels for the entry, bullish for the target.</div>
    </div>
    <div class="rulegrid">__RULES__</div>
    <div class="rulefoot">__MECHANICS__</div>
    <div class="rulefoot">__PRICEONLY__</div>
  </div>
__CAPBAR__
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
__CAPCHART__
  <footer class="mono">__FOOTER__</footer>
</section>"""

# Rule 4's cap dial, and the section that sweeps the whole cap axis. Both are filled in only
# for a strategy whose Rule 4 IS the cap family. Quickfixpro's Rule 4 has no number in it, so
# a dial would have nothing to move and the sweep would be a chart of a different strategy --
# they are simply left out of its section rather than shown disabled.
CAPBAR_HTML = r"""
  <section class="riskbar capbar noprint">
    <span class="lbl">Rule 4 &middot; profit cap</span>
    <input data-el="capin" type="number" min="__CAPMIN__" max="__CAPMAX__"
           step="__CAPSTEP__" value="__CAPVAL__"
           aria-label="Rule 4 profit cap, in R">
    <span class="unit">R</span>
    <label class="nocap"><input data-el="capoff" type="checkbox"> no cap</label>
    <span class="hint" data-el="caphint"></span>
  </section>
"""

CAPCHART_HTML = r"""
  <h2 class="section-h">Choosing the profit cap</h2>
  <section class="card sweepcard">
    <div class="charthead">
      <span class="t">Every cap from 0R to 10R, at a constant 1% risk per trade</span>
      <span class="s">real result &middot; drawdown varies &middot; does not follow the risk dial</span>
    </div>
    <p class="chartnote">What each cap actually did on the same fixed bet. Every point is a
      full backtest; the risk is pinned so the <b>drawdown is free to move</b>, which is what
      makes the wider caps look good here, part of their return is the deeper hole
      they were allowed to dig. Rank them on the chart below, not this one.</p>
    <div class="plot sweepplot" data-el="fxplot">
      <svg data-el="fxsvg" role="img" aria-label="Final capital, max drawdown, risk, return over drawdown and win rate against the Rule 4 profit cap at a constant 1 percent risk"></svg>
      <div class="tip" data-el="fxtip"></div>
    </div>
    <div class="findings" data-el="fixedfindings"></div>
  </section>

  <section class="card sweepcard">
    <div class="charthead">
      <span class="t">The same caps levered to a constant 6% drawdown</span>
      <span class="s">risk solved per cap &middot; equal pain &middot; this is the ranking</span>
    </div>
    <p class="chartnote">Risk is a free variable, so the honest question is: held to the
      <b>same 6% maximum drawdown</b>, which cap ends up with the most money? The risk is
      solved per cap to make that true, and the second pane is what each one is then allowed
      to bet.</p>
    <div class="plot sweepplot" data-el="nwplot">
      <svg data-el="nwsvg" role="img" aria-label="Final capital, risk per trade allowed and win rate against the Rule 4 profit cap at a constant 6 percent drawdown"></svg>
      <div class="tip" data-el="nwtip"></div>
    </div>
    <div class="findings" data-el="capfindings"></div>
  </section>
"""

RISKBAR_HTML = r"""
  <section class="riskbar noprint">
    <span class="lbl">Risk per trade</span>
    <input data-el="riskin" type="number" min="0" max="100" step="0.1" value="__RISKVAL__"
           aria-label="Risk per trade, percent of liquid capital">
    <span class="unit">% of liquid capital</span>
    <span class="hint" data-el="riskhint"></span>
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
// The REFERENCE risk: what the shared variant grid in _variants.json is priced at, and the
// only risk at which the pages' own figures are pinned to a server figure. It is NOT what a
// page opens at -- each strategy opens at its own default (DATA.risk_pct), the risk that puts
// that strategy at the 6% drawdown budget.
const REF_RISK = __REFRISK__;
// Every Rule 4 setting, each a REAL backtest run by run_portfolio.py, shared by every
// strategy on the page: two strategies sitting on the same cap are one run, stored once. `caps` is the cap family -- the dial's axis and the sweep chart's x axis. `extra`
// holds the settings that are NOT caps (Quickfixpro's entry-bar target): same packed rows,
// same replay, but not a point on that axis, so a strategy sitting on one carries neither
// the dial nor the sweep.
//
// Why this is precomputed while the risk % is replayed live: risk changes only the DOLLAR
// SIZING of a fixed trade list, so the browser can redo the arithmetic. Rule 4 changes the
// trades. It moves every exit, and since only one position per market runs at a time, an
// earlier exit frees that market for a signal a longer hold would have missed -- the trade
// list itself is different, and there is nothing to replay it from.
const VARIANTS = __VARIANTS__;
const VCOL = {};
VARIANTS.cols.forEach((c, i) => { VCOL[c] = i; });

// Rows travel as positional arrays indexed against shared market / day / reason tables:
// 34 caps of named JSON fields would put most of a megabyte of repeated key names into
// every page. Net R is not stored -- it is gross minus cost, computed here.
function unpackCap(tok){
  const v = VARIANTS.v[tok];
  if (!v) return null;
  const M = VARIANTS.markets, D = VARIANTS.days, RS = VARIANTS.reasons;
  return v.rows.map(row => {
    const gr = row[VCOL.gr], cr = row[VCOL.cr], dout = row[VCOL.dout];
    return {market:M[row[VCOL.m]], side:row[VCOL.side] ? "long" : "short",
            din:D[row[VCOL.din]], dout:(dout == null ? null : D[dout]),
            xd:D[row[VCOL.xd]], gr:gr, cr:cr, r:gr - cr, bars:row[VCOL.bars],
            pin:row[VCOL.pin], pout:row[VCOL.pout], sl:row[VCOL.sl],
            reason:RS[row[VCOL.reason]]};
  });
}

// The numeric caps, for snapping whatever is typed into the box onto the grid that was
// actually backtested. String() matches Python's "%g" token for every value in the grid.
const CAP_NUMS = VARIANTS.caps.filter(c => c !== "none").map(Number).sort((a, b) => a - b);
function snapCap(x){
  let best = CAP_NUMS[0];
  for (const c of CAP_NUMS) if (Math.abs(c - x) < Math.abs(best - x)) best = c;
  return String(best);
}
// Where the Conclusions page keeps its text. Read back by the report when printing.
const CONCL_KEY = "strategy_conclusions";
function readConclusions(){
  try { return JSON.parse(localStorage.getItem(CONCL_KEY) || "null") || null; }
  catch(e){ return null; }
}
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const fmtUSD = v => (v<0?"−$":"$") + Math.abs(Math.round(v)).toLocaleString("en-US");
const fmtK = v => (v<0?"−$":"$") + Math.abs(v/1000).toFixed(0) + "k";
const pct = v => (v>=0?"+":"") + v.toFixed(1) + "%";
const fmtPrice = v => { if(v==null) return "—"; const a=Math.abs(v);
  const dp = a>=100?1:a>=1?2:a>=0.01?4:6;
  return v.toLocaleString("en-US",{minimumFractionDigits:dp,maximumFractionDigits:dp}); };
const signFix = (v,d) => v==null?"—":(v>=0?"+":"−")+Math.abs(v).toFixed(d);
const signUSD = v => v==null?"—":(v>=0?"+$":"−$")+Math.abs(v).toLocaleString("en-US",{maximumFractionDigits:0});
// 'target_r' = the R cap itself was hit, at whatever cap the run used. It is not named for
// a number any more: the cap is a dial, so "5R target" would be a lie at any other setting.
// 'target_bar' = Quickfixpro's target, the entry bar's own extreme.
const prettyReason = r => ({target_r:"R cap",stop:"stop",unknown_pl:"unknown P/L",
  bullish_reversal:"bull reversal",bearish_reversal:"bear reversal",
  data_end:"data ended",open_at_end:"open at end",target_bar:"bar target"})[r]||r;

// ---- one strategy's report, mounted into `root` ----------------------------------
// A factory rather than top-level code: the print report mounts SEVERAL of these on one
// page, so nothing may address elements by a document-unique id.
function mountReport(root, DATA){
  const $ = k => root.querySelector('[data-el="'+k+'"]');
  const START = DATA.start;
  // One calendar for the whole cap grid, so moving the dial does not shift the equity
  // curve's x-axis underneath the reader: 4R and 8R are drawn over exactly the same period.
  const DAYS = VARIANTS.days;
  // Both dials belong to the STRATEGY, so each mounted section keeps its own. CAP is its
  // Rule 4 setting (Rule 4 is what tells the strategies apart); RISK starts at the risk that
  // puts THIS strategy at the 6% drawdown budget, which differs per strategy -- that is the
  // whole point, the pages open at equal pain rather than equal bet size. A strategy whose
  // Rule 4 is not in the cap family has no cap dial to turn -- its section is built without
  // one, and IN_FAMILY says so for everything downstream.
  let CAP = DATA.r4, RISK = DATA.risk_pct;
  const IN_FAMILY = VARIANTS.caps.indexOf(CAP) >= 0;
  let RAW = unpackCap(CAP);

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
  // `rows` defaults to the cap in force; the sweep chart passes another cap's trades in.
  // `lite` skips the daily narrative (the per-day activity strings and the point series),
  // which is all the sweep needs and is where nearly all the cost is -- sorting the open
  // markets into a string on all 180 days, 34 times over, would be felt on every keystroke.
  // It is the SAME function either way on purpose: a second stripped-down copy of the money
  // management would be free to drift from this one, and the sweep would quietly lie.
  function simulate(risk, rows, lite){
    const R = rows || RAW;
    const ent = {}, exi = {};
    R.forEach((t,i) => {
      (ent[t.din] || (ent[t.din] = [])).push(i);
      (exi[t.xd] || (exi[t.xd] = [])).push(i);
    });
    const tr = R.map(t => Object.assign({}, t, {base:0, riskD:0, pnl:0, pnlpct:0}));
    let cash = START, committed = 0, peak = START, maxdd = 0;
    let gcash = START, gcommitted = 0;
    const open = {}, gopen = {}, pts = [];
    let maxOpen = 0, totalCost = 0, daysIn = 0;

    for (const day of DAYS){
      const es = (ent[day] || []).slice().sort((a,b) =>
        R[a].market < R[b].market ? -1 : R[a].market > R[b].market ? 1 : 0);
      const enotes = [];
      for (const i of es){
        const base = Math.max(cash - committed, 0), riskD = base * risk / 100;
        tr[i].base = base; tr[i].riskD = riskD;
        open[i] = riskD; committed += riskD;
        const gbase = Math.max(gcash - gcommitted, 0);
        gopen[i] = gbase * risk / 100; gcommitted += gopen[i];
        if (!lite) enotes.push(R[i].market + " " + R[i].side + " (risk " +
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
        if (!lite) xnotes.push(R[i].market + " " + R[i].reason + " (" +
          (R[i].reason === "open_at_end" ? "open->closed 0"
            : (pnl >= 0 ? "+" : "−") + Math.abs(Math.round(pnl)).toLocaleString("en-US")) + ")");
      }
      const nOpen = Object.keys(open).length;
      if (cash > peak) peak = cash;
      const dd = peak > 0 ? (cash - peak) / peak * 100 : 0;
      if (-dd > maxdd) maxdd = -dd;
      if (nOpen > maxOpen) maxOpen = nOpen;
      if (nOpen > 0) daysIn++;
      if (!lite) pts.push({date:day, cash:cash, open:nOpen, dd:dd,
                markets:Object.keys(open).map(i => R[i].market).sort().join(", "),
                entries:enotes.join("; "), exits:xnotes.join("; ")});
    }

    // Closed trades only, in EXIT order -- the streaks are "as they were lived".
    const closed = tr.filter(t => t.reason !== "open_at_end");
    const seq = lite ? [] : closed.slice().sort((a,b) =>
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

  let SIM = simulate(RISK), P = SIM.points, N = P.length, T = SIM.trades, ST = SIM.stats;

  // Self-check: at the REFERENCE risk the replay MUST reproduce the server's own figure for
  // the cap in force. If it ever does not, the JS port has drifted from run_portfolio.py --
  // say so in the console rather than quietly showing different numbers from the workbook.
  // Re-run on every cap change, so the whole grid is checked as it is browsed, not just the
  // one it opened on.
  //
  // It re-simulates at REF_RISK rather than checking the live figures, because the page no
  // longer opens at the reference: each strategy opens at its OWN risk, and only the grid's
  // reference price is pinned to a server number. Checking "if the dial happens to sit on the
  // reference" would silently never fire on two of the three strategies. One extra lite
  // simulate is cheap, and the guard now runs everywhere.
  function selfCheck(){
    const want = VARIANTS.v[CAP].final;
    const got = simulate(REF_RISK, null, true).stats.final;
    if (Math.abs(got - want) > 0.5){
      console.warn(DATA.strategy + " @ cap " + CAP + ": replay mismatch at " + REF_RISK +
        "%: page " + got.toFixed(2) + " vs server " + want.toFixed(2) +
        " -- build_equity_html.py is out of step with run_portfolio.py");
    } else {
      console.log(DATA.strategy + " @ cap " + CAP + ": replay verified against run_portfolio.py");
    }
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
    // R multiples and hold times belong to the CAP, not to the risk %, so they come from
    // the variant rather than from the risk replay.
    const V = VARIANTS.v[CAP];
    const TS = [
      ["Average win", fmtUSD(ST.avg_win), "pos", "+"+ST.avg_win_pct.toFixed(2)+"% per win"],
      ["Average loss", fmtUSD(ST.avg_loss), "neg", ST.avg_loss_pct.toFixed(2)+"% per loss"],
      ["Average winner", (V.avg_win_r>=0?"+":"")+V.avg_win_r.toFixed(2)+"R", "pos",
       "best "+(V.best_r>=0?"+":"")+V.best_r.toFixed(2)+"R"],
      ["Average hold", V.avg_bars.toFixed(1)+"d", "", "bars per closed trade"],
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
    // The lede and the footer quote this number too, and it moves with the cap: a shorter
    // hold frees markets for signals a longer one blocked, so a different set of markets
    // ends up trading. Keep all three in step from the one place that counts them.
    [$("ledemk"), $("footmk")].forEach(e => { if (e) e.textContent = String(traded); });
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

  // ---- the two cap charts ----------------------------------------------------------
  // The dial answers "what happens at 4R"; these answer "what happens at all of them",
  // which is the question one setting cannot. Every point is a separate backtest that
  // run_portfolio.py already ran -- the page only re-runs the money management on each.
  //
  //   1. AT THE RISK CURRENTLY SET. Moves with the risk dial, and is the same account the
  //      rest of the page describes.
  //   2. LEVERED TO A CONSTANT DRAWDOWN. Risk is solved per cap instead of taken from the
  //      dial, so the caps are compared at equal pain rather than at equal bet size. This
  //      one deliberately does NOT move with the risk dial.
  //
  // Both are drawn by one plotter over one x axis (the cap grid). Two near-identical
  // renderers would drift apart.
  const ROWCACHE={};
  const rowsFor = tok => ROWCACHE[tok] || (ROWCACHE[tok] = unpackCap(tok));
  const capOf = tok => tok === "none" ? null : Number(tok);
  function statsAt(risk, tok){
    const s = simulate(risk, rowsFor(tok), true).stats;
    return {tok:tok, cap:capOf(tok), risk:risk, final:s.final, ret:s.ret, dd:s.maxdd,
            rdd:s.rdd, n:s.n_trades, wr:s.win_rate};
  }

  // ---- shared plotter ---------------------------------------------------------------
  // `panels` stack down the card: the first is the tall one, the rest are compact rows.
  // Each is {k, h, label, fmt, kind, color, fill, ref, none, zero}.
  function capPlotter(plotEl, svgEl, tipEl, tipRows){
    let g=null;
    // `tickStep` spaces the x-axis labels: 1R suits the 2R-10R sweep, 0.5R the 1R-3R zoom
    // (whole-R ticks would give a detail chart three gridlines).
    function draw(pts, none, panels, markTok, tickStep){
      if(!pts.length) return;
      const W=plotEl.clientWidth||880, mL=62, mR=18, plotW=W-mL-mR, padT=16, xAxisH=26, gap=15;
      const tops=[]; let H=padT;
      panels.forEach(p=>{ tops.push(H); H+=p.h+gap; });
      H=H-gap+xAxisH;
      svgEl.setAttribute("viewBox",`0 0 ${W} ${H}`); svgEl.setAttribute("height",H);
      while(svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);

      const cLo=pts[0].cap, cHi=pts[pts.length-1].cap;
      const x=c=> mL+(cHi===cLo?0:(c-cLo)/(cHi-cLo))*plotW;
      const ys=[];

      panels.forEach((p,i)=>{
        const top=tops[i], vals=pts.map(q=>q[p.k]).filter(v=>v!=null);
        const extra=[];
        if(p.ref!=null) extra.push(p.ref);
        if(p.none && none && none[p.k]!=null) extra.push(none[p.k]);
        if(p.zero) extra.push(0);
        let lo=Math.min.apply(null,vals.concat(extra)), hi=Math.max.apply(null,vals.concat(extra));
        // A flat series (drawdown is constant by construction on the levered chart) would
        // divide by zero; give it a band around its own value instead.
        const span=(hi-lo)||Math.max(1,Math.abs(hi)*0.04)||1;
        const yLo=lo-span*0.12, yHi=hi+span*0.14;
        const y=v=> top+p.h-(v-yLo)/(yHi-yLo)*p.h;
        ys.push(y);

        (i===0?niceTicks(yLo,yHi,4):[lo,hi]).forEach(v=>{
          if(v<yLo||v>yHi) return;
          svgEl.appendChild(mk("line",{x1:mL,x2:W-mR,y1:y(v),y2:y(v),stroke:"var(--grid)","stroke-width":1}));
          svgEl.appendChild(txt(mL-9,y(v)+3.5,p.fmt(v),"end",10.5,"var(--ink3)"));
        });
        if(p.label) svgEl.appendChild(txt(mL+4,top-4,p.label,"start",10.5,"var(--ink3)",".04em"));

        if(p.ref!=null){
          svgEl.appendChild(mk("line",{x1:mL,x2:W-mR,y1:y(p.ref),y2:y(p.ref),stroke:"var(--ref)",
            "stroke-width":1.2,"stroke-dasharray":"3 4"}));
        }
        // The uncapped run is a reference LINE, never a point: "no cap" is not 10.25R and
        // does not belong anywhere on this axis. Labelled on the left, where the curves are
        // lowest, so the label does not land on top of them.
        if(p.none && none && none[p.k]!=null){
          svgEl.appendChild(mk("line",{x1:mL,x2:W-mR,y1:y(none[p.k]),y2:y(none[p.k]),
            stroke:"var(--bars)","stroke-width":1.3,"stroke-dasharray":"5 4",opacity:.9}));
          svgEl.appendChild(txt(mL+4,y(none[p.k])-6,"no cap  "+p.fmt(none[p.k]),"start",10.5,"var(--bars)"));
        }

        const seq=pts.filter(q=>q[p.k]!=null);
        const lp=seq.map(q=>`${x(q.cap).toFixed(1)},${y(q[p.k]).toFixed(1)}`);
        if(!lp.length) return;
        if(p.kind==="area"){
          const base=p.zero?y(Math.max(yLo,Math.min(0,yHi))):y(yLo);
          svgEl.appendChild(mk("path",{d:`M${x(seq[0].cap)},${base} L`+lp.join(" L")+
            ` L${x(seq[seq.length-1].cap)},${base} Z`,fill:p.fill||"var(--accent-soft)"}));
        }
        svgEl.appendChild(mk("path",{d:"M"+lp.join(" L"),fill:"none",stroke:p.color,
          "stroke-width":i===0?2:1.4,"stroke-linejoin":"round","stroke-linecap":"round"}));
        if(i===0) seq.forEach(q=>svgEl.appendChild(mk("circle",{cx:x(q.cap),cy:y(q[p.k]),r:2,
          fill:p.color,opacity:.55})));
      });

      const st=tickStep||1;
      for(let c=Math.ceil(cLo/st)*st; c<=cHi+1e-9; c+=st){
        const v=Math.round(c*100)/100;          // 1+0.5+0.5 is 2.0000000000000004 otherwise
        svgEl.appendChild(mk("line",{x1:x(v),x2:x(v),y1:padT,y2:H-xAxisH,stroke:"var(--grid)","stroke-width":1}));
        svgEl.appendChild(txt(x(v),H-8,v+"R","middle",11,"var(--ink3)"));
      }

      // where the dial is standing. An uncapped page has no point on this axis, so it says
      // so rather than parking the marker somewhere arbitrary.
      const cur=pts.filter(q=>q.tok===markTok)[0];
      if(cur && cur[panels[0].k]!=null){
        svgEl.appendChild(mk("line",{x1:x(cur.cap),x2:x(cur.cap),y1:padT,y2:H-xAxisH,
          stroke:"var(--accent-line)","stroke-width":1,"stroke-dasharray":"2 3",opacity:.7}));
        svgEl.appendChild(mk("circle",{cx:x(cur.cap),cy:ys[0](cur[panels[0].k]),r:4.5,
          fill:"var(--accent-line)",stroke:"var(--surface)","stroke-width":2}));
        const mf=panels[0].mfmt||panels[0].fmt;
        const s=VARIANTS.labels[markTok]+"  "+mf(cur[panels[0].k]);
        const cl=txt(x(cur.cap),ys[0](cur[panels[0].k])-11,s,"middle",12,"var(--ink)");
        cl.setAttribute("font-weight",600);
        const half=s.length*3.4;
        if(x(cur.cap)-half<mL){ cl.setAttribute("text-anchor","start"); cl.setAttribute("x",mL+2); }
        else if(x(cur.cap)+half>W-mR){ cl.setAttribute("text-anchor","end"); cl.setAttribute("x",W-mR-2); }
        svgEl.appendChild(cl);
      } else if(markTok==="none"){
        svgEl.appendChild(txt(mL+4,padT+12,
          "this page is uncapped — the dashed line is where it sits","start",11,"var(--ink3)"));
      } else {
        // The dial is on a cap this axis does not cover -- true on the zoomed chart whenever
        // the page is set above 3R. Say so; a chart with no marker and no explanation reads
        // as though the marker had been forgotten.
        svgEl.appendChild(txt(mL+4,padT+12,
          "the dial is at "+VARIANTS.labels[markTok]+", outside this range","start",11,
          "var(--ink3)"));
      }

      const cross=mk("line",{x1:0,x2:0,y1:padT,y2:H-xAxisH,stroke:"var(--ink2)","stroke-width":1,
        "stroke-dasharray":"2 3",opacity:0});
      const dot=mk("circle",{r:4.5,fill:"var(--accent-line)",stroke:"var(--surface)","stroke-width":2,opacity:0});
      svgEl.appendChild(cross); svgEl.appendChild(dot);
      g={W,mL,plotW,x,y0:ys[0],pts,cLo,cHi,cross,dot,k0:panels[0].k};
    }
    function move(ev){
      if(!g)return;
      const r=plotEl.getBoundingClientRect(), scale=g.W/r.width;
      const c=g.cLo+((ev.clientX-r.left)*scale-g.mL)/g.plotW*(g.cHi-g.cLo);
      let p=g.pts[0];
      for(const q of g.pts) if(Math.abs(q.cap-c)<Math.abs(p.cap-c)) p=q;
      const cx=g.x(p.cap), cy=g.y0(p[g.k0]);
      g.cross.setAttribute("x1",cx); g.cross.setAttribute("x2",cx); g.cross.setAttribute("opacity",1);
      g.dot.setAttribute("cx",cx); g.dot.setAttribute("cy",cy); g.dot.setAttribute("opacity",1);
      tipEl.innerHTML=tipRows(p);
      tipEl.style.opacity=1;
      const tw=tipEl.offsetWidth, th=tipEl.offsetHeight;
      let lx=(cx/scale)+14; if(lx+tw>r.width) lx=(cx/scale)-tw-14;
      let ly=(cy/scale)-th-6; if(ly<0) ly=(cy/scale)+14;
      tipEl.style.left=lx+"px"; tipEl.style.top=ly+"px";
    }
    function leave(){ if(!g)return;
      g.cross.setAttribute("opacity",0); g.dot.setAttribute("opacity",0); tipEl.style.opacity=0;
    }
    plotEl.addEventListener("pointermove",move);
    plotEl.addEventListener("pointerleave",leave);
    return draw;
  }

  const row=(k,v)=>`<div class="row"><span>${k}</span><b class="mono">${v}</b></div>`;
  const ddTxt = v => v==null?"—":v.toFixed(2)+"%";
  const rddTxt = v => v==null?"—":v.toFixed(1)+"x";

  // ---- the cap chart: levered to a constant drawdown ---------------------------------
  // Risk per trade is a free variable, so comparing caps at ONE risk compares them at
  // unequal pain: an uncapped run is twice as deep in drawdown as a 5R one, and its bigger
  // return is partly just a bigger bet. Solving for the risk that puts every cap at the same
  // drawdown removes that, and asks the question the ranking metric implies -- levered to
  // the same hole, which cap ends up with the most money?
  //
  // Drawdown rises monotonically with risk (a bigger bet swings the balance further), so a
  // plain bisection finds it. Solved ONCE per page and cached: this chart is independent of
  // the risk dial by construction, so it never needs redoing.
  const TARGET_DD = 6.0;               // percent; the one constant to change here
  function riskForDrawdown(tok){
    const dd = r => -simulate(r, rowsFor(tok), true).stats.maxdd;
    let lo=0, hi=8;
    if(dd(hi)<TARGET_DD){ hi=100; if(dd(hi)<TARGET_DD) return null; }   // unreachable
    for(let i=0;i<24 && hi-lo>1e-3;i++){
      const mid=(lo+hi)/2;
      if(dd(mid)<TARGET_DD) lo=mid; else hi=mid;
    }
    return (lo+hi)/2;
  }
  // Solved points, cached PER TOKEN rather than per chart: the wide grid and the zoomed one
  // overlap at 2R, 2.5R and 3R, and a bisection is ~24 lite simulates -- solving those three
  // twice would be pure waste, and worse, two caches could drift if either chart's inputs
  // ever changed independently.
  const LEVERED={};
  function leveredAt(tok){
    if(tok in LEVERED) return LEVERED[tok];
    const r = riskForDrawdown(tok);
    return LEVERED[tok] = (r==null
      ? {tok:tok, cap:capOf(tok), risk:null, final:null, ret:null, dd:null,
         rdd:null, n:null, wr:null}
      : statsAt(r, tok));
  }
  let NORM=null;
  function buildNorm(){ return NORM || (NORM = VARIANTS.caps.map(leveredAt)); }
  const drawNorm = !$("nwplot") ? function(){} :
    capPlotter($("nwplot"), $("nwsvg"), $("nwtip"), p =>
    `<div class="d">cap ${p.cap}R${p.tok===CAP?" &middot; current":""}</div>`+
    (p.risk==null ? row("Risk needed","cannot reach "+TARGET_DD+"%") :
      row("Risk per trade", p.risk.toFixed(2)+"%") + row("Final capital", fmtUSD(p.final)) +
      row("Return", pct(p.ret)) + row("Max drawdown", ddTxt(p.dd)) +
      row("Return / DD", rddTxt(p.rdd)) + row("Win rate", p.wr.toFixed(1)+"%") +
      row("Trades", p.n)));

  // No return/DD pane here, unlike the fixed-risk chart above: drawdown is pinned at
  // TARGET_DD by construction, so return/DD is just return divided by a constant and the
  // pane would redraw the capital line in different units. It earns its place on the chart
  // above, where the drawdown actually varies.
  const NORM_PANELS = () => [
    {k:"final", h:150, kind:"area", color:"var(--accent-line)", fmt:fmtK, mfmt:fmtUSD,
     ref:START, none:1},
    {k:"risk", h:50, kind:"line", color:"var(--neg)", none:1,
     label:"RISK PER TRADE ALLOWED", fmt:v=>v.toFixed(2)+"%"},
    {k:"wr",  h:50, kind:"line", color:"var(--ink2)", none:1,
     label:"WIN RATE", fmt:v=>v.toFixed(0)+"%"},
  ];

  // ---- what the chart says, written from the chart -----------------------------------
  // Every number in this prose is read out of the levered grid rather than typed in, so it
  // cannot go stale against the data the way a hand-written paragraph would. The claims are
  // deliberately about the BAND, not the single best quarter-R: on ~80 trades the exact peak
  // is noise, and the text says so.
  // The chart's own reading. Every number is read OUT OF THE GRID at render time rather than
  // typed, so it cannot go stale against the data -- that is the whole reason this is code
  // and not a paragraph in the HTML. Kept short on purpose (2026-07-28): it was five
  // passages, which buried the two things that matter -- where the plateau is, and that the
  // mechanism is the risk each cap is allowed to carry.
  function renderFindings(){
    const el=$("capfindings"); if(!el) return;
    const S=buildNorm();
    const g=S.filter(p=>p.cap!=null && p.final!=null).sort((a,b)=>a.cap-b.cap);
    const none=S.filter(p=>p.tok==="none")[0];
    if(!g.length){ el.innerHTML=""; return; }
    const usd=fmtUSD, r1=v=>v.toFixed(1), r2=v=>v.toFixed(2);
    const best=g.reduce((a,b)=>b.final>a.final?b:a);
    const ns=g.map(p=>p.n);
    const sample=Math.min.apply(null,ns)+"&ndash;"+Math.max.apply(null,ns)+" trades";
    // The plateau the best cap sits on: the run of caps allowed the same risk. That run, not
    // the single best point, is the finding -- inside it every cap bets the same.
    const near=(a,b)=>Math.abs(a-b)<0.02;
    let pa=g.indexOf(best), pb=pa;
    while(pa>0 && near(g[pa-1].risk,best.risk)) pa--;
    while(pb<g.length-1 && near(g[pb+1].risk,best.risk)) pb++;
    const plat=g.slice(pa,pb+1), cliff=g[pb+1];
    const rHi=g.reduce((a,b)=>b.risk>a.risk?b:a), rLo=g.reduce((a,b)=>b.risk<a.risk?b:a);
    const here=g.filter(p=>p.tok===CAP)[0];
    const h=(t,b)=>`<h4>${t}</h4><p>${b}</p>`;
    el.innerHTML =
      h("Where it pays",
        `<b>${plat[0].cap}R&ndash;${plat[plat.length-1].cap}R</b> is the band: every cap on it `+
        `is allowed the same <b>${r2(best.risk)}%</b> per trade`+
        (cliff?`, and at ${cliff.cap}R that falls to ${r2(cliff.risk)}%`:``)+
        `. <span class="hl">Best point ${best.cap}R</span> at <b>${usd(best.final)}</b>`+
        (none?`; uncapped is the worst of the family at ${usd(none.final)}, sized down to `+
              `${r2(none.risk)}%`:``)+`.`) +
      // Both passages below are the USER'S OWN WORDS (2026-07-28), pasted verbatim per the
      // project's working agreement -- so unlike the passage above they are static, not read
      // out of the grid. If the data moves, these have to be revisited by hand; that is the
      // trade being made for saying it in the author's voice.
      h("Why",
        `<b>Taking profit early prevents long loss streaks. And so the drawdown is naturally `+
        `lower at the same amount of risk taken. A lower drawdown allows for taking more `+
        `risk which results in the highest return for the same drawdown.</b>`) +
      h("How much to trust it",
        `The sample size is still small. Over time longer loss streaks are expected to `+
        `happen. But the signal is clear: Keeping the position as long till it hits the next `+
        `reversal or gets stopped out is the less profitable strategy of all. Taking profit `+
        `early but not too early seems to be the conclusion. The sweet spot is found at `+
        `1.9R for this dataseries. The longer the trade is kept after 1.9R, the lower the `+
        `profit for the same drawdown.`);
  }

  // ---- the fixed-risk chart: what each cap really did on the same bet ----------------
  // The companion to the levered chart, and the one that must be read SECOND. Risk is pinned
  // at FIXED_RISK, so the drawdown is free to move -- which is exactly why it cannot rank the
  // caps: a wider cap's bigger return is partly just the deeper hole it was allowed to dig.
  // It is here because it is the real result, and because seeing the drawdown fan out is what
  // makes the levered chart's point land.
  //
  // Deliberately NOT the risk dial's value, so it stays cacheable and so the two charts are
  // a fixed pair rather than one of them sliding around under the reader.
  const FIXED_RISK = 1.0;              // percent; the round reference the chart is titled with
  let FIXED=null;
  function buildFixed(){
    return FIXED || (FIXED = VARIANTS.caps.map(tok => statsAt(FIXED_RISK, tok)));
  }
  const drawFixed = !$("fxplot") ? function(){} :
    capPlotter($("fxplot"), $("fxsvg"), $("fxtip"), p =>
      `<div class="d">cap ${p.cap}R${p.tok===CAP?" &middot; current":""}</div>`+
      row("Final capital", fmtUSD(p.final)) + row("Return", pct(p.ret)) +
      row("Max drawdown", ddTxt(p.dd)) + row("Risk per trade", FIXED_RISK.toFixed(2)+"%") +
      row("Return / DD", rddTxt(p.rdd)) + row("Win rate", p.wr.toFixed(1)+"%") +
      row("Trades", p.n));

  // Panels: the real capital, then the drawdown that bought it, then the flat risk line that
  // says the bet never changed, then return/DD, then win rate. The risk pane is a constant by
  // construction -- it is on the chart precisely to show that it is, since that is the whole
  // difference from the chart below.
  const FIXED_PANELS = () => [
    {k:"final", h:150, kind:"area", color:"var(--accent-line)", fmt:fmtK, mfmt:fmtUSD,
     ref:START, none:1},
    {k:"dd", h:50, kind:"line", color:"var(--neg)", none:1,
     label:"MAX DRAWDOWN", fmt:v=>Math.abs(v).toFixed(0)+"%"},
    {k:"risk", h:36, kind:"line", color:"var(--ink3)", none:1,
     label:"RISK PER TRADE (CONSTANT)", fmt:v=>v.toFixed(2)+"%"},
    {k:"rdd", h:50, kind:"line", color:"var(--bars)", none:1,
     label:"RETURN / DRAWDOWN", fmt:v=>v.toFixed(0)+"x"},
    {k:"wr",  h:50, kind:"line", color:"var(--ink2)", none:1,
     label:"WIN RATE", fmt:v=>v.toFixed(0)+"%"},
  ];

  function renderFixedFindings(S){
    const el=$("fixedfindings"); if(!el) return;
    const g=S.filter(p=>p.cap!=null && p.final!=null).sort((a,b)=>a.cap-b.cap);
    if(!g.length){ el.innerHTML=""; return; }
    const best=g.reduce((a,b)=>b.final>a.final?b:a);
    const ddHi=g.reduce((a,b)=>Math.abs(b.dd)>Math.abs(a.dd)?b:a);
    const ddLo=g.reduce((a,b)=>Math.abs(b.dd)<Math.abs(a.dd)?b:a);
    const r1=v=>v.toFixed(1);
    el.innerHTML = `<h4>Why this one cannot rank them</h4><p>`+
      `Best here is <b>${best.cap}R</b> at <b>${fmtUSD(best.final)}</b>, but its `+
      `drawdown is <b>${r1(Math.abs(best.dd))}%</b>, against ${r1(Math.abs(ddLo.dd))}% at `+
      `${ddLo.cap}R. Across the grid the hole runs from ${r1(Math.abs(ddLo.dd))}% to `+
      `<b>${r1(Math.abs(ddHi.dd))}%</b> on the same bet, so these caps are not being asked `+
      `the same question. The chart below asks it.</p>`;
  }

  function renderFixed(){
    if(!$("fxplot")) return;
    const S=buildFixed();
    if(!S.length) return;
    drawFixed(S.filter(p=>p.cap!=null).sort((a,b)=>a.cap-b.cap),
              S.filter(p=>p.tok==="none")[0], FIXED_PANELS(), CAP);
    renderFixedFindings(S);
  }

  function renderNorm(){
    // Only a cap-family section carries this chart -- it is a sweep of the cap axis, and a
    // strategy that is not on that axis would be shown someone else's result.
    if(!$("nwplot")) return;
    const S=buildNorm();
    // The bisection has to have actually converged, or every figure on this chart is a
    // different drawdown pretending to be 6%.
    const off=S.filter(p=>p.dd!=null && Math.abs(Math.abs(p.dd)-TARGET_DD)>0.05);
    if(off.length) console.warn(DATA.strategy+": levered chart missed the "+TARGET_DD+
      "% target at cap "+off.map(p=>p.tok).join(", "));
    drawNorm(S.filter(p=>p.cap!=null).sort((a,b)=>a.cap-b.cap),
             S.filter(p=>p.tok==="none")[0], NORM_PANELS(), CAP);
    renderFindings();
  }

  function renderAll(){
    renderKpis(); renderDaily(); renderTradeStats();
    $("tcount").textContent = T.length+" trades";
    renderHead(); renderRows(); mBuild(); mHead(); mRows(); render();
    // NOT renderNorm(): the cap chart is risk-independent by construction, so it is
    // redrawn only when the cap marker moves or the card is resized.
  }
  function recompute(){
    SIM = simulate(RISK); P = SIM.points; N = P.length; T = SIM.trades; ST = SIM.stats;
    renderAll(); selfCheck();
  }
  // ---- the risk dial ---------------------------------------------------------------
  // PER STRATEGY, like the cap dial, and for the same kind of reason. Each strategy's
  // default is the risk that puts THAT strategy at the 6% drawdown budget, so the three
  // defaults are three different numbers and one shared box could not show them. Opening
  // every page at one bet size would instead show three different depths of hole and invite
  // ranking them on return alone, which flatters whichever was allowed to dig deepest.
  //
  // Everything that needs the live value reads RISK, never the input's raw .value -- an
  // empty or half-typed field reads as "" and Number("") is 0, which would silently mean
  // "size every position to nothing" rather than "unchanged".
  const riskIn = $("riskin"), riskWarn = $("riskwarn"), riskHint = $("riskhint");
  const DEFAULT_RISK = DATA.risk_pct;
  function setRisk(v, typed){
    let r = (v === "" || v === null || v === undefined) ? NaN : Number(v);
    if (!isFinite(r)) r = RISK;
    r = Math.min(100, Math.max(0, r));
    RISK = r;
    // Do not rewrite the field while it is being typed into -- that would fight the caret.
    if (riskIn && !typed) riskIn.value = String(r);
    root.querySelectorAll(".riskecho").forEach(e => { e.textContent = r + "%"; });
    recompute();
    if (riskHint){
      riskHint.innerHTML = Math.abs(r - DEFAULT_RISK) < 1e-9
        ? "This strategy's own default, the risk that holds it to a <b>" +
          TARGET_DD + "% maximum drawdown</b>, which is how the strategies are compared."
        : "Changed from <b>" + DEFAULT_RISK + "%</b>, this strategy's " + TARGET_DD +
          "%-drawdown risk. The workbooks on disk still hold " + DEFAULT_RISK + "%.";
    }
    if (riskWarn){
      // Above a few percent the sizing model stops describing anything tradeable: it assumes
      // any position size fills at these prices, and it has no margin, no liquidity limit and
      // no ruin -- a losing streak just shrinks the base forever instead of ending the account.
      riskWarn.textContent = r > 5
        ? "At " + r + "% per trade the model ignores margin, liquidity and ruin: 1R = " + r +
          "% of the account, and the " + ST.long_loss + "-trade losing streak below is " +
          "survived only because positions shrink with the balance. Read as arithmetic, " +
          "not a plan."
        : "";
    }
  }
  if (riskIn){
    // An empty field mid-edit (select-all then retype) is left alone rather than read as 0 --
    // otherwise the whole section would flash to a flat curve between keystrokes.
    riskIn.addEventListener("input", () => { if (riskIn.value !== "") setRisk(riskIn.value, true); });
    riskIn.addEventListener("change", () => setRisk(riskIn.value, false));
  }

  // ---- Rule 4's cap dial -----------------------------------------------------------
  // Per strategy, not per page: Rule 4 IS the difference between the strategies, so one
  // shared dial would collapse them onto each other in a multi-strategy report.
  const capIn = $("capin"), capOff = $("capoff"), capHint = $("caphint");
  const DEFAULT_CAP = DATA.r4;
  // What the number box shows while "no cap" is ticked, so unticking returns somewhere sane.
  // Taken from the box's own initial value rather than a magic number: for an uncapped page
  // that value is the registry's default cap, so unticking lands on the setting the OTHER
  // strategy uses instead of somewhere arbitrary. (It was hardcoded to 5, which stopped
  // agreeing with the box the moment quickfix's default moved off 5R.)
  let lastNum = (IN_FAMILY && DEFAULT_CAP !== "none") ? DEFAULT_CAP
              : (capIn && capIn.value !== "" ? snapCap(Number(capIn.value)) : snapCap(5));

  // Everything on the page that quotes the cap is rewritten from strategies.py's own text,
  // shipped per cap -- the wording is generated in ONE place, not written twice.
  function applyCapText(){
    const t = VARIANTS.texts[CAP];
    const put = (k, html) => { const e = $(k); if (e) e.innerHTML = html; };
    put("rule4text", t.rule4_text);
    put("lede4", t.lede);
    put("caveat", t.caveat);
    put("footrule4", t.rule4);
    if (!capHint) return;
    // Which other registered strategy this setting happens to BE. With the cap exposed the
    // strategies are one family at different settings, and saying so is more honest than
    // letting a reader think a re-dialled quickfix is still a separate method.
    const twin = STRATS.filter(s => s.key !== DATA.strategy &&
                                    VARIANTS.defaults[s.key] === CAP)[0];
    const same = "At this setting it is <b>" + (twin ? twin.title : "") + "</b>, trade for " +
                 "trade, with the cap exposed they are one family at two settings.";
    // Careful with what this claims: the workbooks and JSON ledgers really are written at
    // the default cap, but the charter hand-off is a SEPARATE chosen set of caps
    // (CHARTER_CAPS in export_charter_trades.py) which need not include this one.
    capHint.innerHTML = CAP === DEFAULT_CAP
      ? "This strategy's own Rule 4. The workbooks and JSON ledgers are written at this " +
        "setting."
      : "Changed from <b>" + VARIANTS.labels[DEFAULT_CAP] + "</b>. Every setting here is a " +
        "full backtest, so the trades themselves differ, not just their sizing. " +
        "The workbooks on disk still hold " + VARIANTS.labels[DEFAULT_CAP] + ". " +
        (twin ? same : "");
  }
  function syncCapControl(){
    if (capOff) capOff.checked = (CAP === "none");
    if (capIn){
      capIn.disabled = (CAP === "none");
      capIn.value = (CAP === "none" ? lastNum : CAP);
    }
  }
  function setCap(tok, typed){
    // IN_FAMILY guards the URL route as much as the control: report.html accepts a
    // "&cap=key:tok" pair, and letting one re-dial a strategy that is not on the cap axis
    // would print a Quickfixpro section showing a cap run's trades.
    if (!IN_FAMILY || !VARIANTS.v[tok] || tok === CAP) return;
    CAP = tok;
    if (tok !== "none") lastNum = tok;
    RAW = unpackCap(tok);
    applyCapText(); renderNorm(); renderFixed();     // both cap markers follow the dial
    // Same rule as the risk field: do not rewrite the box while it is being typed into,
    // that would fight the caret. `change` (blur, Enter, or a spinner click) syncs it to
    // the grid position actually in force.
    if (!typed) syncCapControl();
    recompute();
  }
  function capFromBox(typed){
    // An empty or half-typed field is left alone rather than read as a number: "" would
    // snap to the lowest cap and flash the whole page between keystrokes.
    if (!capIn || capIn.value === "") return;
    const x = Number(capIn.value);
    if (isFinite(x)) setCap(snapCap(x), typed);
  }
  if (capIn){
    // Live, like the risk dial: typing 4 shows 4R immediately. The value snaps to the grid
    // that was actually backtested -- there is no result for a cap in between.
    capIn.addEventListener("input", () => capFromBox(true));
    capIn.addEventListener("change", () => { capFromBox(false); syncCapControl(); });
  }
  if (capOff) capOff.addEventListener("change", () => setCap(capOff.checked ? "none" : lastNum));

  new ResizeObserver(render).observe(plot);
  // Drawn synchronously with everything else, NOT deferred to an animation frame. It was
  // deferred once, to keep its ~80 ms of bisection off first paint; on a page whose cap is
  // "none" the callback silently never ran and the chart was simply missing -- including
  // from the printed PDF, where nothing would have hinted at it. A chart that sometimes
  // does not exist is a far worse trade than 80 ms of load time.
  if ($("nwplot")) new ResizeObserver(renderNorm).observe($("nwplot"));
  if ($("fxplot")) new ResizeObserver(renderFixed).observe($("fxplot"));
  // setRisk seeds the box, the risk echoes and the hint, and recomputes + self-checks on
  // the way -- so it stands in for the old renderAll()/selfCheck() pair here.
  applyCapText(); syncCapControl(); setRisk(RISK); renderNorm(); renderFixed();
  return {setRisk:r => setRisk(r, false), setCap:setCap, cap:()=>CAP, key:DATA.strategy,
          risk:()=>RISK, defaultRisk:()=>DEFAULT_RISK,
          render:()=>{ render(); renderNorm(); renderFixed(); },
          norm:buildNorm, fixed:buildFixed, stats:()=>ST};
}

// ---- mount every section on this page --------------------------------------------
const ROOTS = Array.prototype.slice.call(document.querySelectorAll("[data-root]"));
const INST = ROOTS.map((el,i) => mountReport(el, DATASETS[i]));

// Each section owns its own risk box and seeds it at mount (see `setRisk` in mountReport),
// so there is nothing page-level left to wire up here.

// Re-measure before printing: the print layout is a different width from the screen, and the
// SVG viewBox is computed from the live element width.
window.addEventListener("beforeprint", () => INST.forEach(i => i.render()));
// The cap sweep prints too -- it is a result, not a control. Only the dial itself is noprint.
__BOOT__
</script>"""

# The PDF picker, only on the interactive pages.
PDF_SCRIPT = r"""
// ---- Export PDF: pick strategies, open the print report ---------------------------
// No PDF library is bundled. The browser's own print-to-PDF gives selectable vector text at
// a fraction of the size that an html2canvas-style rasteriser would produce, so the button
// opens report.html for the chosen strategies and lets it call window.print().
const conclBtn = document.querySelector('[data-el="concl"]');
if (conclBtn) conclBtn.addEventListener("click", () => { location.href = "conclusions.html"; });

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
    'risk currently set on the page. Anything written on the Conclusions page is printed ' +
    'at the end.</p><div class="dlglist">' +
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
    close();
    let url = "report.html?s=" + keys.join(",") + "&auto=1";
    // Any risk moved off its strategy's own default, as key:value pairs -- the same shape as
    // the cap parameter. A strategy not named keeps its own default, which since 2026-07-27
    // is its 6%-drawdown risk rather than one number shared by the page.
    const risks = INST.filter(i => Math.abs(i.risk() - i.defaultRisk()) > 1e-9)
                      .map(i => i.key + ":" + i.risk());
    if (risks.length) url += "&risk=" + risks.join(",");
    // Carry any Rule 4 cap that has been moved off its default, so the PDF prints what is
    // on screen. Only this page's own strategy can have been re-dialled here; the others
    // print at their own defaults, which is what the reader would expect from their names.
    const caps = INST.filter(i => i.cap() !== VARIANTS.defaults[i.key])
                     .map(i => i.key + ":" + i.cap());
    if (caps.length) url += "&cap=" + caps.join(",");
    // Carry the conclusions in the HASH as well as leaving them in localStorage. Opened from
    // a file:// path, browsers do not reliably share storage between two local documents,
    // and the text must survive the hop to the report either way. A hash is never sent
    // anywhere -- it is read by the report itself.
    const c = readConclusions();
    if (c && ((c.general || "").trim() || (c.final || "").trim())){
      url += "#c=" + encodeURIComponent(JSON.stringify(c));
    }
    window.open(url, "_blank");
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
// Rule 4 caps, as key:token pairs -- applied BEFORE the risk so the risk replay runs once,
// on the right trade list. A strategy not named here keeps its own default cap.
(params.get("cap") || "").split(",").filter(Boolean).forEach(pair => {
  const bits = pair.split(":");
  INST.filter(i => i.key === bits[0]).forEach(i => i.setCap(bits[1]));
});
// `risk` takes either key:value pairs (what Export PDF writes, now that each strategy has
// its own default) or a BARE NUMBER, which applies to every strategy on the page -- that is
// still the honest way to ask "compare them all at 2%", and it keeps older links working.
//
// Number(null) is 0, NOT NaN. Reading the parameter straight into Number() therefore made a
// report opened WITHOUT ?risk= (e.g. the Conclusions page's "Open report" link) re-run the
// whole simulation at 0% -- every position sized to nothing, so the equity curve came out
// flat at exactly the starting capital. Hence the empty-string guard before any Number().
const rpRaw = (params.get("risk") || "").trim();
if (rpRaw && rpRaw.indexOf(":") === -1){
  const rp = Number(rpRaw);
  if (isFinite(rp) && rp >= 0) INST.forEach(i => i.setRisk(rp));
} else if (rpRaw){
  rpRaw.split(",").filter(Boolean).forEach(pair => {
    const bits = pair.split(":"), r = Number(bits[1]);
    if (isFinite(r) && r >= 0) INST.filter(i => i.key === bits[0]).forEach(i => i.setRisk(r));
  });
}
document.querySelectorAll(".repcount").forEach(e => {
  const n = document.querySelectorAll("[data-root]").length;
  e.textContent = n + (n === 1 ? " strategy" : " strategies");
});
// Conclusions: the hash wins (that is how Export PDF hands them over, and it survives
// file:// documents not sharing storage); otherwise fall back to this browser's own copy.
function conclusionsForReport(){
  const m = (location.hash || "").match(/[#&]c=([^&]*)/);
  if (m){ try { return JSON.parse(decodeURIComponent(m[1])); } catch(e){} }
  return readConclusions();
}
(function renderConclusions(){
  const c = conclusionsForReport() || {};
  const g = (c.general || "").trim(), f = (c.final || "").trim();
  const box = document.querySelector('[data-el="conclusions"]');
  if (!box) return;
  if (!g && !f){ box.remove(); return; }            // nothing written: no empty headings
  const put = (key, text) => {
    const wrap = box.querySelector('[data-el="'+key+'wrap"]');
    if (!text){ wrap.remove(); return; }
    // textContent, not innerHTML: this is typed prose, and CSS white-space:pre-wrap keeps
    // the line breaks without needing any markup.
    box.querySelector('[data-el="'+key+'"]').textContent = text;
  };
  put("cgeneral", g);
  put("cfinal", f);
  box.hidden = false;
})();

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
    """The four rule cards -- 1-3 shared, 4 this strategy's.

    Rule 4's card is tagged so the cap dial can rewrite it: a page showing 4.25R must not
    still describe a 5R ceiling.
    """
    out = []
    for n, name, text in strategy.rules():
        el = ' data-el="rule4text"' if n == 4 else ""
        out.append(f'<div class="rule"><span class="n">{n}</span><div>'
                   f'<div class="rn">Rule {n} &middot; {name}</div>'
                   f'<div class="rt"{el}>{text}</div></div></div>')
    return "".join(out)


def load_data(strategy):
    src = eng.OUT_DIR / f"_equity_{strategy.key}.json"
    if not src.exists():
        raise SystemExit(f"missing {src} -- run: python run_portfolio.py {strategy.key}")
    return json.loads(src.read_text())


def load_variants():
    """The Rule 4 cap grid, shared by every page (one family, so one table)."""
    src = eng.OUT_DIR / "_variants.json"
    if not src.exists():
        raise SystemExit(f"missing {src} -- run: python run_portfolio.py")
    return json.loads(src.read_text())


def check_variants(strategy, data, variants):
    """The strategy's default Rule 4 must be in the grid, and must agree with its workbook.

    The grid runs every setting over ONE shared calendar while the workbook uses the
    strategy's own first trading day. Those coincide today (the first signal does not depend
    on Rule 4), and this is the guard that says so out loud if the data ever makes them
    diverge -- otherwise the page would quietly show a final capital the workbook does not
    have.
    """
    tok = data["r4"]
    if tok not in variants["v"]:
        raise SystemExit(f"{strategy.key}: Rule 4 {tok!r} is not in the grid -- "
                         f"rerun run_portfolio.py after changing strategies.py")
    # Both sides at the REFERENCE risk. The grid is shared by every page so it cannot be
    # priced per strategy, and the workbook is written at the strategy's own risk -- so the
    # workbook also carries `ref_final`, the same account replayed at the reference, purely
    # so this guard compares like with like instead of flagging the risk difference.
    grid, book = variants["v"][tok]["final"], data["ref_final"]
    if abs(grid - book) > 0.5:
        raise SystemExit(
            f"{strategy.key}: the variant grid's final capital ({grid:,.2f}) disagrees with "
            f"{strategy.key}_portfolio_daily.xlsx ({book:,.2f}), both at the reference risk "
            f"{eng.RISK_PCT:g}%. The shared calendar in run_portfolio.write_variants has "
            f"drifted from the per-strategy one.")


def section_html(strategy, data, riskbar, daily):
    slip = data.get("slippage", {})
    eyebrow = (f"{strategy.title} strategy &middot; daily &middot; "
               f"${eng.STARTING_CAPITAL / 1000:.0f}k starting capital")
    # NOTE: no "time and price" here. These strategies read the reversal levels only; the
    # aggregate/timing side of the Socrates method is not involved, and saying otherwise
    # misled a first-time reader (user, 2026-07-25).
    # n_markets_all is the RESEARCHED universe; n_markets is how many produced a trade. The
    # page used to print only the latter, which read as though the rest were never tested.
    n_all = data.get("n_markets_all", data["n_markets"])
    # Everything that quotes the cap or a trade count is wrapped in a data-el span: both
    # move when the Rule 4 dial moves, and a lede still claiming "closed at 5R" on a page
    # showing 4R would be worse than no lede at all.
    lede = (f"<span data-el=\"lede4\">{strategy.lede}</span> "
            f"All <b>{n_all} markets</b> in the archive were tested, "
            f"<b>{month_year(data['first'])} &ndash; {month_year(data['last'])}</b>; the "
            f"rules fired on <b data-el=\"ledemk\">{data['n_markets']}</b> of them, and the "
            f"rest are listed with zero trades under <em>By market</em>. Capital moves only "
            f"when a trade closes; each new trade risks "
            f"<span class=\"riskecho\">{strategy.risk_pct:g}%</span> of liquid "
            f"capital, the risk that holds this strategy to a {eng.TARGET_DD:g}% "
            f"maximum drawdown. Figures are net of realistic slippage.")
    # Supplied verbatim by the user (2026-07-28), em dashes and all -- which is why this one
    # sentence keeps them while the rest of the report does not. Everything that used to
    # follow it (the intraday-path caveat, commission, "evidence of an edge") was cut on the
    # same instruction; the caveat text still exists in strategies.py for the rules block.
    note = (f"<b>Backtest, net of slippage.</b> Costs are charged as tick slippage "
            f"&mdash; {slip.get('entry', 1)} tick on entry, {slip.get('target', 1)} on a "
            f"limit take-profit, {slip.get('stop', 3)} on a stop &mdash; converted to R "
            f"through each trade's own risk distance.")
    footer = (f"source: {strategy.key}_portfolio_daily.xlsx &middot; "
              f"{n_all} markets tested, <span data-el=\"footmk\">{data['n_markets']}</span> "
              f"traded &middot; rule 4: <span data-el=\"footrule4\">{strategy.rule4}</span> "
              f"&middot; per-market one-position-at-a-time, portfolio-level concurrency")
    # The cap dial and the cap sweep belong to the cap FAMILY, not to every strategy. A
    # strategy whose Rule 4 is a different shape has no number to dial and does not sit on
    # that axis, so both are left out of its section entirely -- an inert control and a
    # chart of somebody else's strategy would both be worse than their absence.
    return (SECTION_HTML
            .replace("__EYEBROW__", eyebrow)
            .replace("__H1__", f"{strategy.title} equity curve optimized")
            .replace("__LEDE__", lede)
            .replace("__RULES__", rules_html(strategy))
            .replace("__MECHANICS__", strategies.entry_mechanics(strategy.risk_pct))
            .replace("__PRICEONLY__", strategies.PRICE_ONLY_NOTE)
            .replace("__CAPBAR__", CAPBAR_HTML if strategy.r4.in_grid else "")
            .replace("__CAPCHART__", CAPCHART_HTML if strategy.r4.in_grid else "")
            .replace("__RISKBAR__", riskbar)
            .replace("__RISKVAL__", f"{strategy.risk_pct:g}")
            .replace("__CAPMIN__", f"{strategies.CAP_MIN:g}")
            .replace("__CAPMAX__", f"{strategies.CAP_MAX:g}")
            .replace("__CAPSTEP__", f"{strategies.CAP_STEP:g}")
            .replace("__CAPVAL__", f"{(strategy.cap or strategies.QUICKFIX.cap):g}")
            .replace("__NOTE__", note)
            .replace("__DAILY__", daily)
            .replace("__FOOTER__", footer))


def strat_meta():
    return json.dumps([{"key": s.key, "title": s.title, "rule4": s.rule4}
                       for s in strategies.REGISTRY], separators=(",", ":"))


def script_html(datasets, variants, boot):
    return (SCRIPT
            .replace("__DATASETS__", json.dumps(datasets, separators=(",", ":")))
            .replace("__VARIANTS__", json.dumps(variants, separators=(",", ":")))
            .replace("__STRATS__", strat_meta())
            .replace("__REFRISK__", f"{eng.RISK_PCT:g}")
            .replace("__BOOT__", boot))


def build(strategy):
    """One interactive page for `strategy`."""
    data = load_data(strategy)
    variants = load_variants()
    check_variants(strategy, data, variants)
    body = (f'<div class="wrap">\n<nav class="nav noprint"><span class="lbl">Strategy</span>'
            f'{nav_html(strategy)}<span class="navbtns">'
            f'<button class="pdfbtn" data-el="concl" type="button">Conclusions</button>'
            f'<button class="pdfbtn" data-el="pdfopen" type="button">Export PDF</button>'
            f'</span></nav>\n'
            + section_html(strategy, data, RISKBAR_HTML, DAILY_HTML) + "\n</div>")
    html = (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>{strategy.title} equity curve optimized</title>\n{CSS}\n</head>\n'
            f'<body data-strategy="{strategy.key}">\n{body}\n'
            f'{script_html([data], variants, PDF_SCRIPT)}\n</body>\n</html>\n')
    path = page_path(strategy)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    print(f"wrote {path.name}  {len(html):,} bytes")


def build_report(picked):
    """report.html -- every strategy in one document, filtered by ?s= and printed to PDF."""
    datasets = [load_data(s) for s in picked]
    variants = load_variants()
    for s, d in zip(picked, datasets):
        check_variants(s, d, variants)
    # Both dials ride along on the print report, one per strategy: a PDF can compare
    # quickfix at 4R against quickfix at 8R, and each section opens at its own
    # 6%-drawdown risk. The risk box used to be shared, on the reasoning that a like-for-like
    # comparison needs one bet size -- but equal DRAWDOWN is the like-for-like this project
    # ranks on, and one box cannot show three different defaults.
    sections = "\n".join(section_html(s, d, RISKBAR_HTML, "")
                         for s, d in zip(picked, datasets))
    head = (
        '<div class="wrap">\n'
        '<nav class="nav noprint"><span class="lbl">Report</span>'
        '<span style="font-size:13px;color:var(--ink2)">'
        '<span class="repcount"></span> &middot; in the print dialog choose destination '
        '<b>Save as PDF</b>, not "Microsoft Print to PDF", which rasterises every '
        'page into images (large file, no selectable text)</span>'
        '<span class="navbtns">'
        '<button class="pdfbtn" data-el="printnow" type="button">Print / Save as PDF</button>'
        '</span></nav>\n')
    # Sits after every strategy, so it is the last thing in the PDF. Hidden until the script
    # finds text; removed outright when there is none, so an unused field never prints.
    conclusions = (
        '\n<section class="concl" data-el="conclusions" hidden>\n'
        '  <div data-el="cgeneralwrap">\n'
        '    <h2 class="section-h">General conclusions</h2>\n'
        '    <div class="conclbody" data-el="cgeneral"></div>\n'
        '  </div>\n'
        '  <div data-el="cfinalwrap">\n'
        '    <h2 class="section-h">Final conclusions of the author</h2>\n'
        '    <div class="conclbody" data-el="cfinal"></div>\n'
        '  </div>\n'
        '</section>\n')
    html = (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>Strategy report</title>\n{CSS}\n</head>\n<body>\n'
            f'{head}{sections}\n{conclusions}</div>\n'
            f'{script_html(datasets, variants, REPORT_SCRIPT)}\n</body>\n</html>\n')
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(html, encoding="utf-8")
    print(f"wrote {REPORT_PATH.name}  {len(html):,} bytes  "
          f"({', '.join(s.key for s in picked)})")


CONCLUSIONS_PATH = eng.OUT_DIR / "conclusions.html"

CONCLUSIONS_SCRIPT = r"""<script>
// Two free-text fields, kept in this browser and printed at the end of the exported PDF.
// Nothing is sent anywhere and no file on disk is written -- the report reads them back when
// it prints (via localStorage, or via the URL hash when opened from a file:// path, where
// browsers do not reliably share storage between two local documents).
const CONCL_KEY = "strategy_conclusions";
const gEl = document.getElementById("cgeneral");
const fEl = document.getElementById("cfinal");
const status = document.getElementById("cstatus");
function load(){
  let c = null;
  try { c = JSON.parse(localStorage.getItem(CONCL_KEY) || "null"); } catch(e){}
  if (c){ gEl.value = c.general || ""; fEl.value = c.final || ""; }
}
let t = null;
function save(quiet){
  try {
    localStorage.setItem(CONCL_KEY, JSON.stringify({general:gEl.value, final:fEl.value}));
    status.textContent = quiet ? "Saved automatically." : "Saved.";
  } catch(e){
    status.textContent = "Could not save in this browser -- copy the text elsewhere before leaving.";
  }
}
[gEl, fEl].forEach(el => el.addEventListener("input", () => {
  status.textContent = "Typing...";
  clearTimeout(t);
  t = setTimeout(() => save(true), 500);        // autosave, so nothing is lost on navigation
}));
document.getElementById("csave").addEventListener("click", () => save(false));
document.getElementById("cclear").addEventListener("click", () => {
  if (!gEl.value && !fEl.value) return;
  gEl.value = ""; fEl.value = ""; save(false);
});
load();
status.textContent = (gEl.value || fEl.value) ? "Loaded your saved text." : "";
</script>"""


def build_conclusions():
    """The Conclusions editor: two fields that print at the end of the exported PDF."""
    back = "".join(
        f'<a href="{page_path(s).name}">{s.title}</a>' for s in strategies.REGISTRY)
    body = (
        '<div class="wrap">\n'
        '<nav class="nav"><span class="lbl">Back to</span>' + back +
        '<span class="navbtns">'
        '<a class="pdfbtn" href="report.html" target="_blank">Open report</a>'
        '</span></nav>\n'
        '<header>\n'
        '  <div class="eyebrow">Report &middot; conclusions</div>\n'
        '  <h1>Conclusions</h1>\n'
        '  <p class="lede">Whatever you write here is printed at the <b>end of the exported '
        'PDF</b>, after the last strategy. Both fields are optional, an empty one is '
        'left out of the report entirely. The text is saved in this browser as you type; it '
        'is not written to any file and never leaves your machine.</p>\n'
        '</header>\n'
        '<div class="cfield">\n'
        '  <label for="cgeneral">General conclusions</label>\n'
        '  <textarea id="cgeneral" placeholder="What the results show across the '
        'strategies..."></textarea>\n'
        '</div>\n'
        '<div class="cfield">\n'
        '  <label for="cfinal">Final conclusions of the author</label>\n'
        '  <textarea id="cfinal" placeholder="Your own reading, caveats and what you intend '
        'to do next..."></textarea>\n'
        '</div>\n'
        '<div class="cbar">\n'
        '  <button class="pdfbtn" id="csave" type="button">Save</button>\n'
        '  <button class="pdfbtn" id="cclear" type="button">Clear both</button>\n'
        '  <span class="status" id="cstatus"></span>\n'
        '</div>\n'
        '</div>')
    html = (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>Conclusions</title>\n{CSS}\n</head>\n<body>\n{body}\n'
            f'{CONCLUSIONS_SCRIPT}\n</body>\n</html>\n')
    CONCLUSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONCLUSIONS_PATH.write_text(html, encoding="utf-8")
    print(f"wrote {CONCLUSIONS_PATH.name}  {len(html):,} bytes")


def main(argv):
    for s in strategies.selected(argv):
        build(s)
    build_conclusions()
    # The report always carries EVERY strategy that has results, whichever pages were built:
    # the picker filters it client-side, so a partial rebuild must not shrink it.
    have = [s for s in strategies.REGISTRY
            if (eng.OUT_DIR / f"_equity_{s.key}.json").exists()]
    if have:
        build_report(have)


if __name__ == "__main__":
    main(sys.argv[1:])
