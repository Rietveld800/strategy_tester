# build_equity_html.py
# Generate a self-contained, interactive equity-curve page from the portfolio results.
# Reads output/_equity_data.json (written by quickfix_portfolio.py) and injects it into an
# HTML template -> output/equity_curve.html.

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "output" / "_equity_data.json").read_text())

TEMPLATE = r"""<style>
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
header{margin-bottom:26px;}
.eyebrow{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);
  font-weight:600;margin-bottom:12px;}
h1{font-size:clamp(26px,4.4vw,40px);line-height:1.08;margin:0 0 12px;letter-spacing:-.02em;
  text-wrap:balance;font-weight:650;}
.lede{max-width:66ch;color:var(--ink2);font-size:15px;margin:0;}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--border);
  border:1px solid var(--border);border-radius:12px;overflow:hidden;margin:28px 0 22px;}
.kpi{background:var(--surface);padding:14px 16px 15px;display:flex;flex-direction:column;gap:5px;}
.kpi .k{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink3);font-weight:600;}
.kpi .v{font-size:clamp(17px,2.2vw,21px);font-weight:600;letter-spacing:-.01em;}
.kpi .v.pos{color:var(--pos)}.kpi .v.neg{color:var(--neg)}
.kpi .sub{font-size:11px;color:var(--ink3);}
@media(max-width:820px){.kpis{grid-template-columns:repeat(3,1fr)}}
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
.stats4{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--border);
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
.dbar{position:relative;height:5px;margin-top:4px;border-radius:3px;background:var(--grid);}
.dbar i{position:absolute;top:0;height:100%;border-radius:3px;}
.dbar .z{position:absolute;left:50%;top:-1px;bottom:-1px;width:1px;background:var(--border);}
footer{margin-top:30px;font-size:12px;color:var(--ink3);}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>

<div class="wrap">
  <header>
    <div class="eyebrow">Quickfix strategy &middot; daily &middot; shared $100k account</div>
    <h1>Portfolio equity curve</h1>
    <p class="lede">One account trading the Socrates time-and-price reversal signals across
      41 markets, Dec 2025 &ndash; Jul 2026. Capital moves only when a trade closes; each new
      trade risks 1% of liquid capital. Figures are net of realistic slippage.</p>
  </header>

  <section class="kpis" id="kpis"></section>

  <section class="card">
    <div class="charthead">
      <span class="t">Capital, drawdown &amp; positions open</span>
      <span class="s">net of slippage &middot; hover for any day</span>
    </div>
    <div class="plot" id="plot">
      <svg id="svg" role="img" aria-label="Portfolio equity, drawdown and open positions over time"></svg>
      <div class="tip" id="tip"></div>
    </div>
  </section>

  <p class="note"><b>Backtest, net of slippage.</b> Costs are charged as tick slippage
    &mdash; 1 tick on entry, 1 on a limit take-profit, 3 on a stop &mdash; converted to R
    through each trade's own risk distance (about $5.1k of drag here, gross was
    +164.1%). Still optimistic on the rest: the entry-day intraday path is assumed
    favorable, a 5R target counts as hit whenever the day's range touches it, and there is
    no commission or funding. Read it as evidence of a strong edge, not a return forecast.</p>

  <h2 class="section-h">Per-trade statistics</h2>
  <section class="stats4" id="tradestats"></section>

  <div class="tradecard">
    <div class="charthead" style="padding:12px 14px 10px">
      <span class="t">All trades</span>
      <span class="s"><span id="tcount"></span> &middot; click a column to sort</span>
    </div>
    <div class="tradescroll">
      <table class="trades" id="ttbl"><thead id="thead"></thead><tbody id="ttbody"></tbody></table>
    </div>
  </div>

  <h2 class="section-h">By market</h2>
  <div class="tradecard">
    <div class="charthead" style="padding:12px 14px 10px">
      <span class="t">Per-market performance</span>
      <span class="s"><span id="mcount"></span> &middot; click a column to sort</span>
    </div>
    <div class="tradescroll">
      <table class="trades" id="mtbl"><thead id="mhead"></thead><tbody id="mbody"></tbody></table>
    </div>
  </div>

  <details>
    <summary>Daily data</summary>
    <div class="tscroll"><table id="tbl"><thead><tr>
      <th>Date</th><th>Capital</th><th>Drawdown</th><th>Open</th><th>Activity</th>
    </tr></thead><tbody id="tbody"></tbody></table></div>
  </details>

  <footer class="mono">source: quickfix_portfolio_daily.xlsx &middot; 41 markets &middot; per-market one-position-at-a-time, portfolio-level concurrency</footer>
</div>

<script>
const DATA = __DATA__;
const P = DATA.points, N = P.length;
const fmtUSD = v => "$" + Math.round(v).toLocaleString("en-US");
const fmtK = v => "$" + (v/1000).toFixed(0) + "k";
const pct = v => (v>=0?"+":"") + v.toFixed(1) + "%";
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const kpis = [
  ["Final capital", fmtUSD(DATA.final), "", "net, from $100k"],
  ["Total return", pct(DATA.ret*100), DATA.ret>=0?"pos":"neg", "gross "+pct(DATA.gross_ret*100)],
  ["Max drawdown", DATA.maxdd.toFixed(2)+"%", "neg", "peak to trough"],
  ["Time in market", DATA.time_in_market.toFixed(0)+"%", "", "of trading days"],
  ["Win rate", DATA.win_rate.toFixed(1)+"%", "", DATA.n_trades+" trades"],
  ["Max concurrent", String(DATA.max_open), "", "positions open"],
];
document.getElementById("kpis").innerHTML = kpis.map(k =>
  `<div class="kpi"><span class="k">${k[0]}</span><span class="v ${k[2]} mono">${k[1]}</span>`+
  `<span class="sub">${k[3]}</span></div>`).join("");

document.getElementById("tbody").innerHTML = P.map(p => {
  const act = [p.entries?`<span style="color:var(--pos)">${p.entries}</span>`:"",
               p.exits?`<span style="color:var(--neg)">${p.exits}</span>`:""].filter(Boolean).join(" &nbsp; ");
  return `<tr><td class="mono">${p.date}</td><td class="mono">${fmtUSD(p.cash)}</td>`+
    `<td class="mono ${p.dd<0?'neg':''}">${p.dd.toFixed(2)}%</td>`+
    `<td class="mono">${p.open}</td><td style="text-align:left;white-space:normal;font-size:11px">${act||"&mdash;"}</td></tr>`;
}).join("");

// ---- per-trade statistics + sortable trades table -------------------------------
const TS=[
  ["Average win", fmtUSD(DATA.avg_win), "pos", "+"+DATA.avg_win_pct.toFixed(2)+"% per win"],
  ["Average loss", "−"+fmtUSD(Math.abs(DATA.avg_loss)), "neg", DATA.avg_loss_pct.toFixed(2)+"% per loss"],
  ["Longest win streak", String(DATA.long_win), "pos", "consecutive wins"],
  ["Longest loss streak", String(DATA.long_loss), "neg", "consecutive losses"],
];
document.getElementById("tradestats").innerHTML = TS.map(k=>
  `<div class="kpi"><span class="k">${k[0]}</span><span class="v ${k[2]} mono">${k[1]}</span>`+
  `<span class="sub">${k[3]}</span></div>`).join("");

const T=DATA.trades;
document.getElementById("tcount").textContent=T.length+" trades";
const fmtPrice=v=>{ if(v==null)return "—"; const a=Math.abs(v);
  const dp=a>=100?1:a>=1?2:a>=0.01?4:6;
  return v.toLocaleString("en-US",{minimumFractionDigits:dp,maximumFractionDigits:dp}); };
const signFix=(v,d)=> v==null?"—":(v>=0?"+":"−")+Math.abs(v).toFixed(d);
const signUSD=v=> v==null?"—":(v>=0?"+$":"−$")+Math.abs(v).toLocaleString("en-US",{maximumFractionDigits:0});
const prettyReason=r=>({target_5r:"5R target",stop:"stop",unknown_pl:"unknown P/L",
  bullish_reversal:"bull reversal",bearish_reversal:"bear reversal",open_at_end:"open at end"})[r]||r;
const COLS=[
  {k:"market",l:"Market",t:"s",w:15},{k:"side",l:"Side",t:"s",w:6},
  {k:"din",l:"In",t:"d",w:8.5},{k:"dout",l:"Out",t:"d",w:8.5},{k:"bars",l:"Bars",t:"n",w:5},
  {k:"pin",l:"In",t:"n",f:fmtPrice,w:8},{k:"pout",l:"Out",t:"n",f:fmtPrice,w:8},
  {k:"sl",l:"Stop",t:"n",f:fmtPrice,w:8},{k:"r",l:"R",t:"n",f:v=>signFix(v,2),color:1,w:6.5},
  {k:"pnl",l:"P&L $",t:"n",f:signUSD,color:1,w:8},
  {k:"pnlpct",l:"P&L %",t:"n",f:v=>signFix(v,2)+"%",color:1,w:8},
  {k:"reason",l:"Reason",t:"s",f:prettyReason,w:10.5},
];
document.getElementById("ttbl").insertAdjacentHTML("afterbegin",
  "<colgroup>"+COLS.map(c=>`<col style="width:${c.w}%">`).join("")+"</colgroup>");
let sortKey="din", sortDir=1;
function renderHead(){
  document.getElementById("thead").innerHTML="<tr>"+COLS.map(c=>{
    const on=c.k===sortKey, ar=on?`<span class="ar">${sortDir>0?"▲":"▼"}</span>`:"";
    return `<th data-k="${c.k}" class="${c.t!=='n'?'l':''}${on?' sorted':''}">${c.l}${ar}</th>`;
  }).join("")+"</tr>";
  document.querySelectorAll("#thead th").forEach(th=>th.onclick=()=>{
    const k=th.dataset.k;
    if(k===sortKey) sortDir=-sortDir; else {sortKey=k; sortDir=(COLS.find(c=>c.k===k).t==="n")?-1:1;}
    renderHead(); renderRows();
  });
}
function renderRows(){
  const col=COLS.find(c=>c.k===sortKey);
  const rows=[...T].sort((a,b)=>{
    let x=a[sortKey], y=b[sortKey];
    if(x==null&&y==null)return 0; if(x==null)return 1; if(y==null)return -1;
    return (col.t==="n" ? (x-y) : String(x).localeCompare(String(y)))*sortDir;
  });
  document.getElementById("ttbody").innerHTML=rows.map(t=>"<tr>"+COLS.map(c=>{
    const v=t[c.k], disp=c.f?c.f(v):(v==null?"—":v);
    let cls=(c.t==="n")?"mono":"l";
    if(c.color&&v!=null) cls+=v>0?" pos":v<0?" neg":"";
    return `<td class="${cls}">${disp}</td>`;
  }).join("")+"</tr>").join("");
}
renderHead(); renderRows();

// ---- per-market analysis (aggregated from the trades, excluding open-at-end) -----
const byM={};
for(const t of T){ if(t.reason==="open_at_end") continue;
  const m=byM[t.market]||(byM[t.market]={market:t.market,n:0,wins:0,pnl:0,totalr:0,best:-1e9,worst:1e9});
  m.n++; if(t.pnl>0)m.wins++; m.pnl+=t.pnl; m.totalr+=t.r;
  m.best=Math.max(m.best,t.r); m.worst=Math.min(m.worst,t.r);
}
const MK=Object.values(byM).map(m=>Object.assign(m,{winrate:100*m.wins/m.n, avgr:m.totalr/m.n}));
const maxAbsPnl=Math.max(1,...MK.map(m=>Math.abs(m.pnl)));
document.getElementById("mcount").textContent=MK.length+" markets";
const MCOLS=[
  {k:"market",l:"Market",t:"s",w:22},{k:"n",l:"Trades",t:"n",w:9},
  {k:"winrate",l:"Win %",t:"n",f:v=>v.toFixed(0)+"%",w:10},
  {k:"pnl",l:"P&L $",t:"n",f:signUSD,bar:1,w:22},
  {k:"totalr",l:"Total R",t:"n",f:v=>signFix(v,2),color:1,w:11},
  {k:"avgr",l:"Avg R",t:"n",f:v=>signFix(v,2),color:1,w:10},
  {k:"best",l:"Best R",t:"n",f:v=>signFix(v,2),w:8},{k:"worst",l:"Worst R",t:"n",f:v=>signFix(v,2),w:8},
];
document.getElementById("mtbl").insertAdjacentHTML("afterbegin",
  "<colgroup>"+MCOLS.map(c=>`<col style="width:${c.w}%">`).join("")+"</colgroup>");
function pnlBar(v){ const frac=Math.min(Math.abs(v)/maxAbsPnl,1)*50, pos=v>=0;
  return `<div class="${v>0?'pos':v<0?'neg':''}">${signUSD(v)}</div>`+
    `<div class="dbar"><span class="z"></span><i style="left:${(pos?50:50-frac).toFixed(1)}%;`+
    `width:${frac.toFixed(1)}%;background:${pos?'var(--pos)':'var(--neg)'}"></i></div>`; }
let mKey="pnl", mDir=-1;
function mHead(){
  document.getElementById("mhead").innerHTML="<tr>"+MCOLS.map(c=>{
    const on=c.k===mKey, ar=on?`<span class="ar">${mDir>0?"▲":"▼"}</span>`:"";
    return `<th data-k="${c.k}" class="${c.t!=='n'?'l':''}${on?' sorted':''}">${c.l}${ar}</th>`;
  }).join("")+"</tr>";
  document.querySelectorAll("#mhead th").forEach(th=>th.onclick=()=>{
    const k=th.dataset.k;
    if(k===mKey) mDir=-mDir; else {mKey=k; mDir=(MCOLS.find(c=>c.k===k).t==="n")?-1:1;}
    mHead(); mRows();
  });
}
function mRows(){
  const col=MCOLS.find(c=>c.k===mKey);
  const rows=[...MK].sort((a,b)=>{ const x=a[mKey],y=b[mKey];
    return (col.t==="n"?(x-y):String(x).localeCompare(String(y)))*mDir; });
  document.getElementById("mbody").innerHTML=rows.map(m=>"<tr>"+MCOLS.map(c=>{
    const v=m[c.k]; const disp=c.bar?pnlBar(v):(c.f?c.f(v):v);
    let cls=(c.t==="n")?"mono":"l"; if(c.color&&v!=null) cls+=v>0?" pos":v<0?" neg":"";
    return `<td class="${cls}">${disp}</td>`;
  }).join("")+"</tr>").join("");
}
mHead(); mRows();

function niceTicks(min,max,n){
  const raw=(max-min)/n, mag=Math.pow(10,Math.floor(Math.log10(raw))), norm=raw/mag;
  let step = norm<1.5?1:norm<3?2:norm<7?5:10; step*=mag;
  const out=[]; for(let v=Math.ceil(min/step)*step; v<=max+1e-6; v+=step) out.push(v);
  return out;
}

const svg=document.getElementById("svg"), plot=document.getElementById("plot"), tip=document.getElementById("tip");
const NS="http://www.w3.org/2000/svg";
const mk=(t,a)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
let geom=null;

function render(){
  const W=plot.clientWidth||880;
  const padT=14, mainH=262, gap=16, ddH=60, posH=60, xAxisH=22;
  const mainBot=padT+mainH, ddTop=mainBot+gap, ddBot=ddTop+ddH;
  const posTop=ddBot+gap, posBot=posTop+posH, H=posBot+xAxisH;
  const mL=58, mR=18, plotW=W-mL-mR;
  svg.setAttribute("viewBox",`0 0 ${W} ${H}`); svg.setAttribute("height",H);
  while(svg.firstChild) svg.removeChild(svg.firstChild);

  const cash=P.map(p=>p.cash);
  const lo=Math.min(...cash,DATA.start), hi=Math.max(...cash), span=hi-lo;
  const yMin=lo-span*0.06, yMax=hi+span*0.10;
  const x=i=> mL + (N<=1?0:i/(N-1))*plotW;
  const y=v=> padT + mainH - (v-yMin)/(yMax-yMin)*mainH;
  const ddLo=Math.min(...P.map(p=>p.dd),-0.5), yd=v=> ddTop + (-v)/(-ddLo)*ddH;
  const maxOpen=Math.max(DATA.max_open,1), yp=v=> posBot - (v/maxOpen)*posH;

  // equity y-grid
  niceTicks(yMin,yMax,5).forEach(v=>{ if(v<yMin||v>yMax)return;
    svg.appendChild(mk("line",{x1:mL,x2:W-mR,y1:y(v),y2:y(v),stroke:"var(--grid)","stroke-width":1}));
    const t=mk("text",{x:mL-9,y:y(v)+3.5,"text-anchor":"end","font-size":11,fill:"var(--ink3)"});
    t.textContent=fmtK(v); svg.appendChild(t);
  });
  // $100k start reference
  svg.appendChild(mk("line",{x1:mL,x2:W-mR,y1:y(DATA.start),y2:y(DATA.start),stroke:"var(--ref)",
    "stroke-width":1.2,"stroke-dasharray":"3 4"}));
  const rl=mk("text",{x:mL+4,y:y(DATA.start)-5,"font-size":10,fill:"var(--ink3)"});
  rl.textContent="$100k start"; svg.appendChild(rl);

  // month gridlines + labels (span all panels)
  let lastM=-1;
  P.forEach((p,i)=>{const m=+p.date.slice(5,7)-1;
    if(m!==lastM){lastM=m;
      if(i>1) svg.appendChild(mk("line",{x1:x(i),x2:x(i),y1:padT,y2:posBot,stroke:"var(--grid)","stroke-width":1}));
      const t=mk("text",{x:x(i),y:H-6,"text-anchor":"middle","font-size":11,fill:"var(--ink3)"});
      t.textContent=MONTHS[m]+(m===0?" '26":""); svg.appendChild(t);
    }});

  // equity area + line
  const lp=P.map((p,i)=>`${x(i).toFixed(1)},${y(p.cash).toFixed(1)}`);
  svg.appendChild(mk("path",{d:`M${x(0)},${y(yMin)} L`+lp.join(" L")+` L${x(N-1)},${y(yMin)} Z`,fill:"var(--accent-soft)"}));
  const line=mk("path",{d:"M"+lp.join(" L"),fill:"none",stroke:"var(--accent-line)","stroke-width":2,
    "stroke-linejoin":"round","stroke-linecap":"round"});
  svg.appendChild(line);

  // drawdown
  svg.appendChild(mk("line",{x1:mL,x2:W-mR,y1:yd(0),y2:yd(0),stroke:"var(--grid)","stroke-width":1}));
  const ddp=P.map((p,i)=>`${x(i).toFixed(1)},${yd(p.dd).toFixed(1)}`);
  svg.appendChild(mk("path",{d:`M${x(0)},${yd(0)} L`+ddp.join(" L")+` L${x(N-1)},${yd(0)} Z`,fill:"var(--neg-soft)"}));
  svg.appendChild(mk("path",{d:"M"+ddp.join(" L"),fill:"none",stroke:"var(--neg)","stroke-width":1.4}));
  svg.appendChild(txt(mL-9,yd(ddLo)+3.5,ddLo.toFixed(0)+"%","end",10,"var(--ink3)"));
  svg.appendChild(txt(mL+4,ddTop-5,"DRAWDOWN","start",10.5,"var(--ink3)",".04em"));

  // positions open -- bars; a gap (no bar) is a day out of the market
  svg.appendChild(mk("line",{x1:mL,x2:W-mR,y1:posBot,y2:posBot,stroke:"var(--grid)","stroke-width":1}));
  const barW=Math.max(1.6,Math.min(7,plotW/N*0.72));
  P.forEach((p,i)=>{ if(p.open>0){ const by=yp(p.open);
    svg.appendChild(mk("rect",{x:(x(i)-barW/2).toFixed(1),y:by.toFixed(1),width:barW.toFixed(1),
      height:(posBot-by).toFixed(1),fill:"var(--bars)",rx:1,opacity:.85})); }});
  svg.appendChild(txt(mL-9,yp(maxOpen)+3.5,String(maxOpen),"end",10,"var(--ink3)"));
  svg.appendChild(txt(mL-9,posBot+3.5,"0","end",10,"var(--ink3)"));
  svg.appendChild(txt(mL+4,posTop-5,"POSITIONS OPEN","start",10.5,"var(--ink3)",".04em"));

  // endpoint
  const ex=x(N-1), ey=y(cash[N-1]);
  svg.appendChild(mk("circle",{cx:ex,cy:ey,r:4,fill:"var(--accent-line)",stroke:"var(--surface)","stroke-width":2}));
  const el=txt(ex-8,ey-9,fmtUSD(cash[N-1]),"end",12.5,"var(--ink)"); el.setAttribute("font-weight",600);
  svg.appendChild(el);

  // crosshair
  const cross=mk("line",{x1:0,x2:0,y1:padT,y2:posBot,stroke:"var(--ink2)","stroke-width":1,"stroke-dasharray":"2 3",opacity:0});
  const dot=mk("circle",{r:4.5,fill:"var(--accent-line)",stroke:"var(--surface)","stroke-width":2,opacity:0});
  const ddot=mk("circle",{r:3.5,fill:"var(--neg)",stroke:"var(--surface)","stroke-width":1.5,opacity:0});
  svg.appendChild(cross);svg.appendChild(dot);svg.appendChild(ddot);

  if(!matchMedia("(prefers-reduced-motion:reduce)").matches){
    const len=line.getTotalLength(); line.style.strokeDasharray=len; line.style.strokeDashoffset=len;
    line.animate([{strokeDashoffset:len},{strokeDashoffset:0}],{duration:900,easing:"cubic-bezier(.4,0,.1,1)",fill:"forwards"});
  }
  geom={W,mL,plotW,x,y,yd,ex,ey,cross,dot,ddot};
}

function txt(x,y,s,anchor,size,fill,ls){
  const t=mk("text",{x:x,y:y,"font-size":size,fill:fill});
  if(anchor)t.setAttribute("text-anchor",anchor); if(ls)t.setAttribute("letter-spacing",ls);
  t.textContent=s; return t;
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
render();
new ResizeObserver(render).observe(plot);
</script>
"""

html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
(HERE / "output" / "equity_curve.html").write_text(html, encoding="utf-8")
print("wrote output/equity_curve.html", len(html), "bytes")
