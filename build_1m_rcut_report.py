# build_1m_rcut_report.py
#
# The R-CUT report (Lode, 2026-08-10): quickfix1m1dc restricted to a BAND of
# ladder geometry - keep only entries whose level-to-stop distance (1R in
# price) falls between a lower and an upper fraction of the market's trailing
# 24-hour high-low range. Pick the two cuts, see that band's equity curve,
# DRAWDOWN and OPEN POSITIONS, its metrics, and a HEATMAP of the whole grid.
#
# WHY EVERY BAND NEEDS ITS OWN ENGINE RUN, and therefore why this script is
# slow (~24s per combination): a refused entry does NOT spend the
# session-lockout allowance, so a band does not merely DROP trades from the
# baseline - a later minute can trigger instead, and the band takes trades the
# baseline never reached. The 0.10-step bands sum to 337 trades against the
# baseline's 137, which is the proof: they are not slices of one run and cannot
# be produced by filtering a blotter. Verified consequence (audit s.15c):
# excluding the sub-0.20 trades removed 19 trades worth +22.49R and UNLOCKED 5
# worth +28.11R, because the tight-ladder setups were spending the session's
# only entry before a better-proportioned setup appeared.
#
# EVERY CELL IS LEVERED TO THE SAME 6% MAX DRAWDOWN: comparing bands at one bet
# size flatters whichever band was allowed to dig the deepest hole, since a
# shallower curve can simply be bet bigger. Method is solve_risk.py's -
# drawdown rises monotonically with risk, so bisect - applied to
# run_1m.portfolio_replay, this project's own account.
#
# RESULTS ARE CACHED AND REUSED. A cell already in the output JSON is not
# re-run (same engine, same dials, so the pass is deterministic), which is what
# makes refining the grid cheap: the 0.05 refinement Lode asked for adds ~95
# passes on top of the 136 already computed instead of redoing all 231.
#
# HOW TO READ IT, and the cautions are not decoration (audit s.15):
# - A narrow band holds a few dozen trades. Its win rate is noisy and its
#   DRAWDOWN is barely an estimate, so the 6%-levered money divides by a number
#   this sample cannot support. The leverage figure illustrates, it does not
#   advise - and levering to a measured drawdown bets biggest exactly where the
#   evidence is thinnest.
# - Check `top market share` before believing a band. The BASELINE's own net R
#   is 49% one market (ZW).
# - The best region is a one-step RIDGE, not a smooth optimum: lower 0.00 and
#   0.10 are identical, lower 0.30 collapses.
#
# Usage:  python build_1m_rcut_report.py            # full grid + refinement
#         python build_1m_rcut_report.py --step 0.5 --max 1.0   # coarse test
#         python build_1m_rcut_report.py --no-reuse # ignore the cache

import json
import sys
import time
from pathlib import Path

import run_1m
import run_1m_matrix as mx

HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "output" / "quickfix1m1dcRcut.json"
OUT_HTML = HERE / "output" / "quickfix1m1dcRcut.html"
# The TRADE cache, and the reason it exists: the metrics are cheap but the
# engine passes are not (~24s each, 231 of them). Caching the finished cells
# was not enough - adding the win-streak and open-position metrics on
# 2026-08-10 needed the trade LISTS, which the cell cache never held, so every
# pass had to run again. Keeping the trades means any future metric is seconds
# of arithmetic instead of an hour and a half of backtesting.
OUT_TRADES = HERE / "output" / "quickfix1m1dcRcut_trades.json"
CHECKPOINT_EVERY = 25      # rewrite the page mid-run so it can be read early

TARGET_DD = 6.0
RISK_TOLERANCE = 0.0005
BASE = dict(tighten=False, allow_pre_activation=False, confirm=False,
            stop_mode="ladder", max_entries_per_session=1)

# 0.05 refinement where the grid actually turns (Lode, 2026-08-10): the ten
# best cells all sit at lower 0.20, and the upper cut's plateau runs 0.40-0.70,
# so those two stretches get half-steps and the rest stays on 0.10.
REFINE_LOWER = (0.10, 0.30)
REFINE_UPPER = (0.40, 0.70)

# DIVERGING AT BREAK-EVEN (Lode, 2026-08-10): red and orange where the account
# ENDS BELOW ITS STARTING CAPITAL, greens above it, deepest green at the best.
# The pivot is a real number, not a visual midpoint - $100,000 is where the
# strategy made nothing - which is what earns a diverging scale here.
# 15 classes, finer than the 7 it replaces, because Lode wanted smaller money
# steps between colours.
# Red/green is the classic colour-vision trap, so it is NEVER the only channel:
# every cell prints its value, and the legend labels the pivot.
# Both arms verified strictly monotone in lightness (OKLab: red arm
# 0.375 -> 0.812 rising, green arm 0.985 -> 0.338 falling), and each step
# carries >= 4.5:1 against its chosen ink.
HEAT_PIVOT = 100_000.0
# The red arm runs from a FIXED floor, not from the observed minimum (Lode,
# 2026-08-10). Anchoring it to the worst cell made a $96.6k result the
# darkest red the scale can show, which reads as a catastrophe when it is a
# 3% loss; from $90,000 the colours sit where the money actually is.
HEAT_MIN = 90_000.0
NEG_RAMP = ["#7f0000", "#b2182b", "#d6604d", "#f4a582", "#fdae61"]
NEG_INK = ["#ffffff", "#ffffff", "#0b0b0b", "#0b0b0b", "#0b0b0b"]
POS_RAMP = ["#f7fcf5", "#e5f5e0", "#ccebc5", "#addd8e", "#8fce7f",
            "#66bd63", "#41ab5d", "#238b45", "#00702f", "#00441b"]
POS_INK = ["#0b0b0b", "#0b0b0b", "#0b0b0b", "#0b0b0b", "#0b0b0b",
           "#0b0b0b", "#0b0b0b", "#0b0b0b", "#ffffff", "#ffffff"]
C_BAND, C_REF = "#1b7f45", "#898781"      # band green; muted ink for the reference
C_DD, C_POS = "#e34948", "#2a78d6"        # slot 8 red; slot 1 blue for exposure
PANE_H = (360, 150, 130)                  # equity, drawdown, open positions
PRICE_SCALE_W = 76    # identical on all three panes, so the plots line up


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


def streaks(trades):
    """(longest losing, longest winning) run in ENTRY order."""
    seq = sorted(trades, key=lambda t: t["entry_ts"])
    worst = best = run_l = run_w = 0
    for t in seq:
        if t["net_r"] < 0:
            run_l += 1
            run_w = 0
        else:
            run_w += 1
            run_l = 0
        worst = max(worst, run_l)
        best = max(best, run_w)
    return worst, best


def exposure(trades):
    """Concurrent open positions over time: (series, max, time-weighted mean).

    At 1% risk per trade N concurrent positions is N% of the account at risk,
    so this is the report's only view of how much is on the table at once -
    the equity curve cannot show it."""
    import pandas as pd
    ev = []
    for t in trades:
        ev.append((int(pd.Timestamp(t["entry_ts"]).timestamp()), 1))
        ev.append((int(pd.Timestamp(t["exit_ts"]).timestamp()), -1))
    ev.sort()
    series, n, peak = [], 0, 0
    area, prev_ts = 0.0, None
    for ts, d in ev:
        if prev_ts is not None:
            area += n * (ts - prev_ts)
        n += d
        peak = max(peak, n)
        if series and series[-1][0] == ts:
            series[-1] = (ts, n)
        else:
            series.append((ts, n))
        prev_ts = ts
    span = (ev[-1][0] - ev[0][0]) if len(ev) > 1 else 0
    return series, peak, (round(area / span, 2) if span else 0.0)


DAY = 86400


def daily_equity(curve, start_capital=100_000.0):
    """The equity curve resampled to ONE POINT PER CALENDAR DAY, carried
    forward across days with no exit.

    WHY, and it is not cosmetic (Lode, 2026-08-10): lightweight-charts spaces
    points by INDEX, not by time. Fed the raw per-exit curve it gave a busy
    month more width than a quiet one - "months like feb and mei tend to take
    longer" - so the axis was not a time axis at all and dates repeated. One
    point per day makes index spacing and time spacing the same thing, which
    is also what lets the three panes be read against each other."""
    if not curve:
        return []
    by_day = {}
    for ts, eq in curve:
        by_day[ts // DAY] = eq          # last equity of that day wins
    lo, hi = min(by_day), max(by_day)
    out, last = [((lo - 1) * DAY, start_capital)], start_capital
    for d in range(lo, hi + 1):
        last = by_day.get(d, last)
        out.append((d * DAY, round(last, 2)))
    return out


def drawdown_series(daily):
    """Percent below the running peak, on the DAILY closes plotted beside it.
    Negative, so the pane reads downward from zero."""
    out, peak = [], None
    for ts, eq in daily:
        peak = eq if peak is None else max(peak, eq)
        out.append((ts, -round((peak - eq) / peak * 100.0, 3)))
    return out


def daily_exposure(pos_series, daily):
    """Concurrent open positions, as the DAY'S MAXIMUM - the peak amount of
    the account on the table that day, on the same daily grid as the rest."""
    per_day = {}
    for ts, n in pos_series:
        d = ts // DAY
        per_day[d] = max(per_day.get(d, 0), n)
    out, last = [], 0
    for ts, _ in daily:
        d = ts // DAY
        last = per_day.get(d, 0)
        out.append((ts, last))
    return out


def measure(trades):
    """Metrics for one band, at 1% and levered to TARGET_DD."""
    n = len(trades)
    if not n:
        return None
    wins = [t["net_r"] for t in trades if t["net_r"] > 0]
    losses = [t["net_r"] for t in trades if t["net_r"] <= 0]
    netr = sum(t["net_r"] for t in trades)
    gross_w, gross_l = sum(wins), -sum(losses)
    final1, dd1, curve1 = run_1m.portfolio_replay(trades, risk_pct=1.0)
    lose_streak, win_streak = streaks(trades)
    _, dd_r = mx.entry_order_metrics(trades)
    risk6 = solve_risk(trades)
    if risk6:
        final6, dd6, curve6 = run_1m.portfolio_replay(trades, risk_pct=risk6)
    else:
        final6, dd6, curve6 = final1, dd1, curve1
    pos_series, pos_max, pos_mean = exposure(trades)
    # Display grids: one point per calendar day, so the axis is a time axis.
    d_curve = daily_equity(curve6)
    d_dd = drawdown_series(d_curve)
    d_pos = daily_exposure(pos_series, d_curve)
    # The daily-close figure for the TABLE is taken at 1% risk, so it sits
    # beside the intraday one on the same basis. Reading it off the levered
    # curve instead just restates the 6% target, which every cell hits by
    # construction and which tells the reader nothing.
    dd_close = -min((v for _, v in drawdown_series(daily_equity(curve1))),
                    default=0.0)
    per_market = {}
    for t in trades:
        per_market[t["market"]] = per_market.get(t["market"], 0.0) + t["net_r"]
    top_mkt, top_r = max(per_market.items(), key=lambda kv: kv[1])
    return dict(
        trades=n, wins=len(wins), win_rate=round(100 * len(wins) / n, 1),
        net_r=round(netr, 2), avg_r=round(netr / n, 3),
        profit_factor=round(gross_w / gross_l, 2) if gross_l else None,
        avg_win=round(gross_w / len(wins), 2) if wins else None,
        avg_loss=round(-gross_l / len(losses), 2) if losses else None,
        longest_losing_streak=lose_streak, longest_winning_streak=win_streak,
        max_dd_r=dd_r, max_dd_pct=round(dd1, 2), final_1pct=round(final1, 2),
        # The pane draws daily closes, so the depth it SHOWS gets its own row -
        # the worst-reached figure above is deeper by construction.
        max_dd_close_pct=round(dd_close, 2),
        risk_6pct=round(risk6, 3) if risk6 else None,
        final_6pct=round(final6, 2), max_dd_6pct=round(dd6, 2),
        pos_max=pos_max, pos_mean=pos_mean,
        markets=len(per_market), top_market=top_mkt,
        top_market_share=round(100 * top_r / netr, 0) if netr > 0 else None,
        exit_mix={r: sum(1 for t in trades if t["reason"] == r)
                  for r in ("stop", "close1", "no_confirm", "data_end")},
        # Curves are the LEVERED ones (equal pain is the comparison asked
        # for), on the daily grid the panes need.
        curve=d_curve, dd=d_dd, pos=d_pos,
        levered=bool(risk6),
    )


def cell_key(lo, hi):
    """Cache/report key for a band. The baseline is (None, None)."""
    if lo is None and hi is None:
        return "baseline"
    return f"{lo:.2f}|{'inf' if hi is None else f'{hi:.2f}'}"


def edge_list(step, top):
    """The 0.10 grid plus 0.05 half-steps in the two refined stretches."""
    edges = {round(i * step, 2) for i in range(int(round(top / step)) + 1)}
    if step >= 0.10:                     # only refine the real grid, not a test
        for lo, hi in (REFINE_LOWER, REFINE_UPPER):
            v = lo
            while v <= hi + 1e-9:
                edges.add(round(v, 2))
                v += 0.05
    return sorted(edges)


def main():
    argv = sys.argv[1:]
    step = float(argv[argv.index("--step") + 1]) if "--step" in argv else 0.10
    top = float(argv[argv.index("--max") + 1]) if "--max" in argv else 1.50
    reuse = "--no-reuse" not in argv
    edges = edge_list(step, top)

    # Reuse TRADES, not finished cells: metrics are recomputed every build, so
    # adding a metric never costs an engine pass again.
    tcache = {}
    if reuse and OUT_TRADES.exists():
        try:
            old = json.loads(OUT_TRADES.read_text(encoding="utf-8"))
            if old.get("dials") == BASE:
                tcache = old.get("trades", {})
                print(f"reusing trades for {len(tcache)} cells from "
                      f"{OUT_TRADES.name}", flush=True)
        except ValueError:
            pass

    t0 = time.time()
    # LAZY: loading every market costs ~100s, and a rebuild that only changes
    # how the metrics are computed needs no market data at all - the trades
    # are already cached. Load on the first cache miss, not before.
    loaded = []

    def markets():
        if not loaded:
            for key in run_1m.ELIGIBLE_FUTURES + run_1m.ETFS:
                try:
                    inputs, excluded = run_1m.market_inputs(key)
                except Exception as exc:
                    print(f"{key}: ERROR {type(exc).__name__}: {exc}",
                          flush=True)
                    continue
                if inputs is not None:
                    loaded.append((key, inputs))
            print(f"loaded {len(loaded)} markets in {time.time() - t0:.0f}s",
                  flush=True)
        return loaded

    def run(lo, hi):
        dials = dict(BASE, min_rpu_range_ratio=lo, max_rpu_range_ratio=hi)
        trades = []
        for key, (days, files, tick, note) in markets():
            tr, _ = run_1m.engine_1m.run_market(days, files, tick, **dials)
            for t in tr:
                t["market"] = key
            trades.extend(tr)
        trades.sort(key=lambda t: t["entry_ts"])
        return trades

    combos = [(None, None)]          # the baseline rides in the same loop
    combos += [(lo, hi) for i, lo in enumerate(edges) for hi in edges[i + 1:]]
    combos += [(lo, None) for lo in edges]
    fresh = sum(1 for lo, hi in combos if cell_key(lo, hi) not in tcache)
    print(f"{len(combos)} combinations over {len(edges)} edges; "
          f"{len(combos) - fresh} from cache, {fresh} to backtest "
          f"(~{fresh * 24 / 60:.0f} min)", flush=True)

    OUT_JSON.parent.mkdir(exist_ok=True)
    cells, baseline = {}, None
    t1, done = time.time(), 0

    def checkpoint():
        payload = dict(
            strategy="quickfix1m1dc - ladder-geometry band (R cut)",
            audit_doc="docs/quickfix1m1dc_audit.md (s.15)",
            target_dd=TARGET_DD, step=step, edges=edges,
            dials=BASE, baseline=baseline,
            cells={k: v for k, v in cells.items() if v})
        OUT_JSON.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        OUT_HTML.write_text(page(payload), encoding="utf-8")
        OUT_TRADES.write_text(json.dumps(dict(dials=BASE, trades=tcache)),
                              encoding="utf-8")

    for i, (lo, hi) in enumerate(combos, 1):
        key = cell_key(lo, hi)
        trades = tcache.get(key)
        if trades is None:
            trades = run(lo, hi)
            tcache[key] = trades
            done += 1
        m = measure(trades)
        if lo is None and hi is None:
            baseline = m
        else:
            cells[key] = m
        left = ((time.time() - t1) / done * (fresh - done)) if done else 0
        print(f"[{i}/{len(combos)}] {key}: "
              + (f"{m['trades']}t {m['net_r']:+.2f}R avg {m['avg_r']:+.2f} "
                 f"DD {m['max_dd_pct']}% pos<={m['pos_max']} "
                 f"{m['longest_winning_streak']}W/{m['longest_losing_streak']}L"
                 f" -> ${m['final_6pct']:,.0f}" if m else "no trades")
              + f"   (~{left / 60:.0f} min left)", flush=True)
        if baseline is not None and i % CHECKPOINT_EVERY == 0:
            checkpoint()
            print(f"  -- checkpoint: {len(cells)} cells on the page --",
                  flush=True)

    checkpoint()
    print(f"\nwrote {OUT_JSON.name}, {OUT_HTML.name} and {OUT_TRADES.name} "
          f"in {(time.time() - t0) / 60:.0f} min", flush=True)


def page(p):
    lib = run_1m.LIB_PATH.read_text(encoding="utf-8")
    data = json.dumps(p)
    heat = json.dumps(dict(pivot=HEAT_PIVOT, floor=HEAT_MIN,
                           neg=NEG_RAMP, negInk=NEG_INK,
                           pos=POS_RAMP, posInk=POS_INK))
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>quickfix1m1dc - R cut</title><style>
:root {{
  --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --band:{C_BAND}; --ref:{C_REF};
  --dd:{C_DD}; --pos:{C_POS};
}}
body {{ background:var(--surface); color:var(--ink);
font:13px system-ui,-apple-system,"Segoe UI",sans-serif; margin:0;
padding:14px; }}
#head {{ max-width:1150px; }}
.note {{ color:var(--ink-2); line-height:1.45; }}
.warn {{ color:#B25000; }}
b.k {{ font-weight:600; }}
/* Panes: three charts, NEVER two y-scales on one plot. Each container's
   height includes its own time-axis band - a fixed height that excludes the
   axis is what clipped the labels here on 2026-08-10. */
.pane {{ margin-top:6px; }}
/* The three panes live in one positioned box so a single hand-drawn vertical
   line can span all of them (see the crosshair note in the script). */
#panes {{ position:relative; }}
#vline {{ position:absolute; top:0; bottom:0; width:0;
border-left:1px dashed #52514e; display:none; pointer-events:none; z-index:4; }}
#chart {{ height:{PANE_H[0]}px; }} #chartDD {{ height:{PANE_H[1]}px; }}
#chartPos {{ height:{PANE_H[2]}px; }}
#bar {{ display:flex; gap:18px; align-items:center; flex-wrap:wrap;
margin-top:10px; }}
select {{ font:13px inherit; padding:2px 4px; }}
.legend {{ display:flex; gap:14px; align-items:center; color:var(--ink-2);
margin-top:8px; font-size:12px; }}
.legend i {{ display:inline-block; width:16px; height:3px; margin-right:5px;
vertical-align:middle; }}
/* SCOPED TO #tbl / .hm ON PURPOSE. A bare `table` rule also hits the <table>
   lightweight-charts builds INSIDE the chart container: a margin-top on it
   pushed the whole chart down, so the time axis hung outside the box and the
   date labels were cut in half (Lode, 2026-08-10). Never style bare element
   selectors on a page that hosts a third-party widget. */
#tbl {{ border-collapse:collapse; margin-top:14px;
font-variant-numeric:tabular-nums; }}
#tbl td, #tbl th {{ padding:4px 10px; border-bottom:1px solid var(--grid);
text-align:right; }}
#tbl td:first-child, #tbl th:first-child {{ text-align:left; }}
.hm {{ border-collapse:separate; border-spacing:2px; margin-top:6px;
font-variant-numeric:tabular-nums; font-size:11px; }}
.hm th {{ color:var(--ink-2); font-weight:600; padding:2px 5px;
text-align:center; }}
.hm th.rowh {{ text-align:right; }}
.hm td {{ width:52px; height:24px; text-align:center; cursor:pointer;
border-radius:3px; }}
.hm td.empty {{ background:transparent; cursor:default; }}
.hm td.sel {{ outline:2px solid var(--ink); outline-offset:1px; }}
#hmlegend {{ display:flex; align-items:center; gap:0; margin-top:8px;
font-size:11px; color:var(--ink-2); }}
#hmlegend .sw {{ width:34px; height:12px; }}
#tip {{ position:fixed; pointer-events:none; background:var(--surface);
border:1px solid var(--axis); border-radius:4px; padding:6px 8px;
font-size:12px; box-shadow:0 2px 8px rgba(11,11,11,.12); display:none;
z-index:9; font-variant-numeric:tabular-nums; }}
h3 {{ font-size:13px; margin:18px 0 0; }}
</style></head><body>
<div id="head"><b>quickfix1m1dc - ladder geometry band</b>
<span class="note"> Keep only entries whose <b class="k">1R in price
(level to ladder stop)</b> falls between the two cuts, as a fraction of that
market's trailing 24-hour high-low range. Every band is its OWN engine run - a
refused entry does not spend the session-lockout allowance, so a band takes
trades the baseline never reached and is not a slice of it. Each cell is
levered to a constant <b class="k">{p['target_dd']}% max drawdown</b>, because
comparing at one bet size flatters whichever band dug the deepest hole.
<b class="k">ADOPTED (Lode): lower 0.20, upper 0.50</b> is the published
band (upper adopted 2026-08-10, audit s.15e; lower raised from 0.00 on
2026-08-11, s.17, with the s.15c ridge caution on record). The published
baseline also carries the human MARKET FILTER (s.16), which this grid does
NOT: every cell here runs the whole universe, and "all trades" is the
pre-adoption engine with no cuts, so this page stays the research record
the band was read from.</span>
</div>
<div id="bar">
  <label>lower cut <select id="lo"></select></label>
  <label>upper cut <select id="hi"></select></label>
  <span id="risk" class="note"></span>
</div>
<div id="panes">
  <div id="vline"></div>
  <div class="legend"><span><i style="background:var(--band)"></i>selected
  band</span><span class="note">equity at the levered bet size - the
  all-trades comparison is in the table, not as a second curve</span></div>
  <div class="pane" id="chart"></div>
  <div class="legend"><span><i style="background:var(--dd)"></i>drawdown %
  below peak</span><span class="note">on daily closes; the worst intraday
  figure is in the table</span></div>
  <div class="pane" id="chartDD"></div>
  <div class="legend"><span><i style="background:var(--pos)"></i>open
  positions (concurrent)</span><span class="note">at 1% risk each, N open =
  N% at risk</span></div>
  <div class="pane" id="chartPos"></div>
</div>

<h3>Final equity at {p['target_dd']}% drawdown - the whole grid</h3>
<div class="note">Rows are the lower cut, columns the upper. Click a cell to
load it. Blank = the upper cut is not above the lower.</div>
<div id="hm"></div>
<div id="hmlegend"></div>
<div id="tip"></div>

<h3>Metrics for the selected band</h3>
<table id="tbl"></table>

<p class="note warn" style="max-width:1150px"><b>Read the R columns, not the
money.</b> A narrow band holds a few dozen trades: its win rate is noisy and
its drawdown is barely an estimate, so levering to {p['target_dd']}% divides by
a number this sample cannot support - and leverage to a measured drawdown bets
biggest exactly where the evidence is thinnest. Check <b class="k">top market
share</b>: the BASELINE's own net R is 49% one market. The best region is a
one-step ridge, not a smooth optimum. Audit s.15.</p>

<script>{lib}</script><script>
const P = {data}, H = {heat};

/* Three panes, one measure each: a dual-axis plot invents correlations that
   are not in the data, so equity, drawdown and exposure never share a scale.
   Three things make them read as ONE stacked chart instead of three charts:
   an identical price-scale width (otherwise each plot starts at a different
   x and the time axes do not line up), the time axis drawn ONLY under the
   bottom pane, and a crosshair mirrored across all three. */
function mkChart(el, h, showTime) {{
  return LightweightCharts.createChart(el, {{
    width: el.clientWidth, height: h,
    layout: {{ background: {{ color:'#fcfcfb' }}, textColor:'#52514e',
      attributionLogo:false, fontSize:11 }},
    grid: {{ vertLines:{{visible:false}},
      horzLines:{{color:'#e1e0d9', style:0}} }},
    rightPriceScale: {{ borderColor:'#c3c2b7', minimumWidth:{PRICE_SCALE_W},
      scaleMargins:{{top:0.10, bottom:0.10}} }},
    timeScale: {{ visible: showTime, timeVisible:false, secondsVisible:false,
      borderColor:'#c3c2b7' }},
    // The crosshair is mirrored onto the other panes, so it has to be
    // VISIBLE - the library default is a hairline that vanishes on a light
    // surface. The time label rides on the bottom pane only, since it is the
    // only one drawing a time axis.
    crosshair: {{
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: {{ color:'#52514e', width:1, style:2,
        labelVisible: showTime, labelBackgroundColor:'#52514e' }},
      horzLine: {{ color:'#52514e', width:1, style:2,
        labelBackgroundColor:'#52514e' }},
    }},
  }});
}}
const elEq = document.getElementById('chart'),
      elDD = document.getElementById('chartDD'),
      elPos = document.getElementById('chartPos');
const cEq = mkChart(elEq, {PANE_H[0]}, false),
      cDD = mkChart(elDD, {PANE_H[1]}, false),
      cPos = mkChart(elPos, {PANE_H[2]}, true);
const PANES = [cEq, cDD, cPos];
const sBand = cEq.addLineSeries({{ color:'{C_BAND}', lineWidth:2,
  priceLineVisible:false, lastValueVisible:false }});
/* NO REFERENCE CURVE. The "all trades" line used to sit here in grey and it
   was actively misleading: it is a DIFFERENT cut of the grid, so it rises
   while the selected band falls, which reads as the equity going up while the
   drawdown pane deepens (Lode, 2026-08-10 - the numbers were always
   consistent, the second curve was not). The comparison lives in the metrics
   table, where the two columns cannot be mistaken for one series. */
/* Drawdown as a BASELINE series anchored at zero, not an area series: an area
   fills from the line to the bottom of the pane, so a SHALLOW drawdown drew
   the biggest block of colour - inverted, exactly as Lode read it. A baseline
   series fills only between zero and the line, so the ink is the drawdown. */
const sDD = cDD.addBaselineSeries({{
  baseValue: {{ type:'price', price:0 }},
  bottomLineColor:'{C_DD}', bottomFillColor1:'rgba(227,73,72,0.10)',
  bottomFillColor2:'rgba(227,73,72,0.45)',
  topLineColor:'{C_DD}', topFillColor1:'rgba(227,73,72,0)',
  topFillColor2:'rgba(227,73,72,0)',
  lineWidth:1, priceLineVisible:false, lastValueVisible:false }});
// Open positions as BARS, like the other variant reports (Lode).
const sPos = cPos.addHistogramSeries({{ color:'{C_POS}', base:0,
  priceLineVisible:false, lastValueVisible:false }});

/* Keep the three time scales in step BY TIME, not by logical index. The panes
   hold different numbers of points - equity and drawdown change only at exits,
   exposure changes at every entry AND exit - so logical index 50 is a
   different date in each, and syncing logical ranges pulled them apart
   (Lode: "the time axis of the panes are not lined up"). */
let syncing = false;
PANES.forEach(src => {{
  src.timeScale().subscribeVisibleTimeRangeChange(r => {{
    if (!r || syncing) return;
    syncing = true;
    PANES.forEach(dst => {{
      if (dst !== src) dst.timeScale().setVisibleRange(r);
    }});
    syncing = false;
  }});
}});
/* ONE VERTICAL LINE ACROSS ALL THREE PANES, drawn by hand.
   The library's own setCrosshairPosition was mirroring the line onto the other
   panes ~150px away from the cursor (Lode's report3.png), and it also threw
   during a cold load's first setData. Both problems vanish with a plain
   overlay: the panes now share an identical width and price-scale width, so
   THE SAME X IS THE SAME MOMENT IN ALL THREE by construction - no time
   lookup, nothing to drift. lwc keeps its own crosshair inside whichever pane
   is hovered, which is what draws the price and date labels. */
const panesBox = document.getElementById('panes');
const vline = document.getElementById('vline');
panesBox.addEventListener('mousemove', e => {{
  const r = panesBox.getBoundingClientRect();
  const x = e.clientX - r.left;
  // Stay out of the price-scale gutter, where there is no plot to point at.
  if (x < 0 || x > r.width - {PRICE_SCALE_W}) {{
    vline.style.display = 'none';
    return;
  }}
  vline.style.left = x + 'px';
  vline.style.display = 'block';
}});
panesBox.addEventListener('mouseleave',
  () => {{ vline.style.display = 'none'; }});
window.addEventListener('resize', () => {{
  cEq.resize(elEq.clientWidth, {PANE_H[0]});
  cDD.resize(elDD.clientWidth, {PANE_H[1]});
  cPos.resize(elPos.clientWidth, {PANE_H[2]});
}});

const lo = document.getElementById('lo'), hi = document.getElementById('hi');
P.edges.forEach(e => lo.add(new Option(e.toFixed(2), e)));
P.edges.forEach(e => hi.add(new Option(e.toFixed(2), e)));
hi.add(new Option('no cap', 'inf'));

const money = v => '$' + Math.round(v).toLocaleString('en-US');
const keyOf = (a, b) => a.toFixed(2) + '|' + (b === null ? 'inf' : b.toFixed(2));

function rows(m, b) {{
  const R = [
    ['trades', m.trades, b.trades],
    ['wins', m.wins, b.wins],
    ['win rate %', m.win_rate, b.win_rate],
    ['net R', m.net_r, b.net_r],
    ['avg R per trade', m.avg_r, b.avg_r],
    ['profit factor', m.profit_factor, b.profit_factor],
    ['avg win / avg loss (R)', m.avg_win + ' / ' + m.avg_loss,
     b.avg_win + ' / ' + b.avg_loss],
    ['longest WINNING streak', m.longest_winning_streak,
     b.longest_winning_streak],
    ['longest losing streak', m.longest_losing_streak,
     b.longest_losing_streak],
    ['max open positions', m.pos_max, b.pos_max],
    ['avg open positions', m.pos_mean, b.pos_mean],
    ['max DD (R)', m.max_dd_r, b.max_dd_r],
    ['max DD % at 1% risk', m.max_dd_pct + '%', b.max_dd_pct + '%'],
    ['max DD % on daily closes, 1% risk',
     m.max_dd_close_pct + '%', b.max_dd_close_pct + '%'],
    ['final at 1% risk', money(m.final_1pct), money(b.final_1pct)],
    ['risk for ' + P.target_dd + '% DD',
     m.risk_6pct ? m.risk_6pct + '%' : 'never reaches it',
     b.risk_6pct + '%'],
    ['final at ' + P.target_dd + '% DD', money(m.final_6pct),
     money(b.final_6pct)],
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
        + '</b></td><td style="color:var(--muted)">' + r[2]
        + '</td></tr>').join('');
}}

/* ---- heatmap: DIVERGING at break-even. Below the starting capital the cell
   is red through orange, above it green, deepest green at the best. Each arm
   is scaled to its own span, because the losing side is a few thousand
   dollars wide and the winning side is ninety - a symmetric scale would spend
   half its colours on almost nothing. The value is printed in every cell, so
   colour is never the only channel. ---- */
const vals = Object.values(P.cells).filter(Boolean).map(m => m.final_6pct);
const vMin = Math.min(...vals), vMax = Math.max(...vals);
function colorFor(v) {{
  if (v < H.pivot) {{
    // From a FIXED floor, so the reds mean the same money on every rebuild.
    const span = Math.max(H.pivot - H.floor, 1e-9);
    const i = Math.min(H.neg.length - 1,
      Math.max(0, Math.floor((v - H.floor) / span * H.neg.length)));
    return [H.neg[i], H.negInk[i]];
  }}
  const span = Math.max(vMax - H.pivot, 1e-9);
  const i = Math.min(H.pos.length - 1,
    Math.max(0, Math.floor((v - H.pivot) / span * H.pos.length)));
  return [H.pos[i], H.posInk[i]];
}}

function drawHeat() {{
  const ups = P.edges.map(e => e.toFixed(2)).concat(['inf']);
  let h = '<table class="hm"><tr><th class="rowh">lower \\\\ upper</th>'
    + ups.map(u => '<th>' + (u === 'inf' ? 'none' : u) + '</th>').join('')
    + '</tr>';
  for (const l of P.edges) {{
    h += '<tr><th class="rowh">' + l.toFixed(2) + '</th>';
    for (const u of ups) {{
      const k = l.toFixed(2) + '|' + u;
      const m = P.cells[k];
      if (!m) {{ h += '<td class="empty"></td>'; continue; }}
      const [bg, fg] = colorFor(m.final_6pct);
      h += '<td data-k="' + k + '" style="background:' + bg
        + ';color:' + fg + '">'
        + Math.round(m.final_6pct / 1000) + 'k</td>';
    }}
    h += '</tr>';
  }}
  document.getElementById('hm').innerHTML = h + '</table>';
  let lg = '<span style="margin-right:6px">' + money(H.floor) + '</span>';
  H.neg.forEach(c => {{ lg += '<span class="sw" style="background:' + c
    + '"></span>'; }});
  lg += '<span style="margin:0 6px">' + money(H.pivot)
    + ' break-even</span>';
  H.pos.forEach(c => {{ lg += '<span class="sw" style="background:' + c
    + '"></span>'; }});
  lg += '<span style="margin-left:6px">' + money(vMax)
    + '</span><span style="margin-left:14px">all trades: '
    + money(P.baseline.final_6pct) + '</span>';
  document.getElementById('hmlegend').innerHTML = lg;
}}

const tip = document.getElementById('tip');
document.getElementById('hm').addEventListener('mousemove', e => {{
  const td = e.target.closest('td[data-k]');
  if (!td) {{ tip.style.display = 'none'; return; }}
  const m = P.cells[td.dataset.k], k = td.dataset.k.split('|');
  tip.innerHTML = '<b>' + k[0] + ' to ' + (k[1] === 'inf' ? 'no cap' : k[1])
    + '</b><br>' + money(m.final_6pct) + ' at ' + (m.risk_6pct ?? '-')
    + '% risk<br>' + m.trades + ' trades, wr ' + m.win_rate + '%, '
    + m.net_r + 'R<br>avg ' + m.avg_r + 'R, PF ' + m.profit_factor
    + '<br>streaks ' + m.longest_winning_streak + 'W / '
    + m.longest_losing_streak + 'L, pos&le;' + m.pos_max
    + '<br>top market ' + m.top_market + ' ' + (m.top_market_share ?? '-')
    + '%';
  tip.style.display = 'block';
  tip.style.left = Math.min(e.clientX + 14, innerWidth - 230) + 'px';
  tip.style.top = (e.clientY + 14) + 'px';
}});
document.getElementById('hm').addEventListener('mouseleave',
  () => {{ tip.style.display = 'none'; }});
document.getElementById('hm').addEventListener('click', e => {{
  const td = e.target.closest('td[data-k]');
  if (!td) return;
  const [a, b] = td.dataset.k.split('|');
  lo.value = String(parseFloat(a));
  hi.value = b === 'inf' ? 'inf' : String(parseFloat(b));
  show();
}});

function show() {{
  const a = parseFloat(lo.value);
  const bv = hi.value === 'inf' ? null : parseFloat(hi.value);
  const tbl = document.getElementById('tbl');
  const risk = document.getElementById('risk');
  const clear = msg => {{ tbl.innerHTML = '<tr><td>' + msg + '</td></tr>';
    sBand.setData([]); sDD.setData([]); sPos.setData([]);
    risk.textContent = ''; }};
  if (bv !== null && bv <= a) return clear(
    'the upper cut must be above the lower cut');
  const m = P.cells[keyOf(a, bv)];
  if (!m) return clear('this combination was not computed');
  sBand.setData(m.curve.map(c => ({{time:c[0], value:c[1]}})));
  sDD.setData(m.dd.map(c => ({{time:c[0], value:c[1]}})));
  sPos.setData(m.pos.map(c => ({{time:c[0], value:c[1]}})));
  tbl.innerHTML = rows(m, P.baseline);
  risk.textContent = m.levered
    ? ('bet ' + m.risk_6pct + '% per trade for ' + P.target_dd
       + '% drawdown  ->  ' + money(m.final_6pct))
    : ('never reaches ' + P.target_dd + '% drawdown - shown at 1% risk');
  document.querySelectorAll('.hm td.sel').forEach(
    td => td.classList.remove('sel'));
  const cell = document.querySelector(
    '.hm td[data-k="' + keyOf(a, bv) + '"]');
  if (cell) cell.classList.add('sel');
  /* One explicit range on all three panes, from the widest series, so they
     start aligned rather than each fitting its own first/last point.
     ON THE NEXT FRAME, and never fatal: setVisibleRange needs the pane's
     MEASURED size, which lightweight-charts leaves null until its first
     layout. Called inline on a cold load it threw "Value is null" and took
     the whole of show() with it - empty panes and an unbuilt table, while the
     identical call from the console a second later worked (2026-08-10). Data
     lands first; the range is cosmetic and can retry. */
  const t0 = Math.min(m.pos[0][0], m.curve[0][0], P.baseline.curve[0][0]);
  const t1 = Math.max(m.pos[m.pos.length - 1][0],
    m.curve[m.curve.length - 1][0],
    P.baseline.curve[P.baseline.curve.length - 1][0]);
  const applyRange = tries => {{
    try {{
      syncing = true;
      PANES.forEach(c => c.timeScale().setVisibleRange({{from: t0, to: t1}}));
    }} catch (e) {{
      if (tries > 0) return requestAnimationFrame(() => applyRange(tries - 1));
      console.warn('R-cut: could not set the shared range', e);
    }} finally {{ syncing = false; }}
  }};
  requestAnimationFrame(() => applyRange(5));
}}
lo.onchange = hi.onchange = show;
// Defaults from the edges that EXIST: a coarse grid has no 0.20 option, and
// setting a missing value leaves the select empty and the page on an error row.
function nearest(sel, want) {{
  let best = sel.options[0].value, d = Infinity;
  for (const o of sel.options) {{
    const v = parseFloat(o.value);
    if (!isNaN(v) && Math.abs(v - want) < d) {{ d = Math.abs(v - want);
      best = o.value; }}
  }}
  return best;
}}
function init() {{
  drawHeat();
  // Open on the ADOPTED band (0.20/0.50, s.15e + s.17).
  lo.value = nearest(lo, 0.20);
  hi.value = nearest(hi, 0.50);
  if (parseFloat(hi.value) <= parseFloat(lo.value)) hi.value = 'inf';
  show();
  if (!sBand.data().length) throw new Error('no series data drawn');
}}
/* BOOT WITH RETRIES, and the reason is worth knowing (2026-08-10). On a COLD
   load the first `setData` throws lightweight-charts' "Value is null" - its
   internals are not ready while a ~4 MB inline payload is still being parsed
   and laid out - yet the identical call succeeds a moment later. Chasing the
   exact internal was not worth more time than this: the page retries until the
   library is ready, which is bounded, self-healing and visible in the console
   if it ever gives up. Two frames of rAF were NOT enough on this page. */
function boot(tries) {{
  try {{
    init();
  }} catch (e) {{
    if (tries > 0) return setTimeout(() => boot(tries - 1), 80);
    console.error('R-cut: init failed after retries:', e);
    document.getElementById('tbl').innerHTML =
      '<tr><td>init failed: ' + e.message + ' (see console)</td></tr>';
  }}
}}
boot(15);
</script></body></html>"""


if __name__ == "__main__":
    main()
