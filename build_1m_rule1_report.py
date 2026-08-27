# build_1m_rule1_report.py
#
# The RULE 1 sweep (Lode, 2026-08-26): quickfix1m1dc with the tested-reversal
# count as the moving dial. The published rule arms a setup once THREE
# reversals of the ladder have been tested by the session's running extreme;
# this page runs the same model at 1 to 5 tested reversals - entry still at
# the (first touch of, or retrace to) the FIRST reversal - on the two
# published configurations:
#
#   4th/5th stop, band 000-060   (the dials of `variant 2`, the baseline)
#   hybrid stop,  band 020-060   (the dials of `variant 5`)
#
# Ten cells, each its own engine run over the filtered universe: rule 1
# decides WHEN a setup arms, so a different count shifts which minute (and
# which session) triggers, and no blotter filter can reproduce that. The
# rule-1 = 3 rows ARE variant 2 and variant 5, re-measured on this pass, so
# the page carries its own control. At rule 1 = 1 the setup arms on the
# first touch of the first reversal itself (added 2026-08-26, Lode): the
# touch bar needs its close back beyond the level - OHLC cannot order the
# events inside one bar - and any later print fires the market order.
#
# The band and the stop label are read from run_1m_matrix's own tables
# (BAND_CUTS_BY_STOP middle slot, STOP_MODE_BY_LABEL), so this page cannot
# disagree with the matrix about what "hybrid" or the chosen band means -
# same rule as the R-cut grids.
#
# NOT IN A FULL REFRESH, by the same ruling as the R-cut grids (Lode,
# 2026-08-12: a research grid gets its own update button inside its page).
# The page posts `reversals1m` to charter's /api/refresh; the key lives in
# trading_system/refresh.EXTRA_STEPS. Ten passes over 22 markets is a few
# minutes, so there is no cell cache - every click recomputes everything,
# which errs the safe way by construction.
#
# Usage:  python build_1m_rule1_report.py            # the eight cells
#         python build_1m_rule1_report.py --page     # redraw HTML, no backtest

import colorsys
import json
import sys
import time
from datetime import datetime, timezone, date
from pathlib import Path

import run_1m
import run_1m_matrix as mx

HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "output" / "quickfix1m1dcRule1.json"
OUT_HTML = HERE / "output" / "quickfix1m1dcRule1.html"
REFRESH_STEP = "reversals1m"

REVERSAL_COUNTS = (1, 2, 3, 4, 5)
PUBLISHED_COUNT = 3        # the module constant in engine_1m; rows at 3 are
                           # variant 2 / variant 5 re-measured
# Everything off the sweep axis sits at the published baseline, exactly as
# the matrix runs it.
BASE = dict(tighten=False, allow_pre_activation=False, confirm=False,
            max_entries_per_session=1, range_mode="trading_day")
# The two configurations, each carrying its OWN adopted band - the middle
# slot of that anchor's ladder in the matrix, never a literal here.
ANCHORS = [("4th/5th", "variant 2 (published baseline)"),
           ("hybrid", "variant 5")]
# Lightness per tested-reversal count, same idea as the matrix's lockout
# axis: one hue per stop anchor, the published count darkest, and the
# further from it the lighter.
COUNT_LIGHT = {1: 68, 2: 56, 3: 32, 4: 44, 5: 78}


def build_cells():
    """The eight cells: (key, props, dials), in table order."""
    out = []
    for label, matrix_cell in ANCHORS:
        lo, hi = mx.BAND_CUTS_BY_STOP[label][1]
        for n in REVERSAL_COUNTS:
            dials = dict(BASE, stop_mode=mx.STOP_MODE_BY_LABEL[label],
                         min_rpu_range_ratio=lo, max_rpu_range_ratio=hi,
                         min_reversals=n)
            props = dict(stop=label, band=mx.band_label(lo, hi),
                         rule1=n, matrix_cell=matrix_cell,
                         published=(n == PUBLISHED_COUNT))
            suffix = "4th5th" if label == "4th/5th" else label
            out.append((f"{suffix} r{n}", props, dials))
    return out


CELLS = build_cells()


def color_for(props):
    h = mx.STOP_HUE[props["stop"]]
    r, g, b = colorsys.hls_to_rgb(h / 360,
                                  COUNT_LIGHT[props["rule1"]] / 100, 0.68)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255),
                                        round(b * 255))


def measure(trades, rows):
    """Portfolio metrics for one cell, 1% and levered to 6% max drawdown -
    the same figures the matrix table carries, derived the same way."""
    trades = sorted(trades, key=lambda t: t["entry_ts"])
    n = len(trades)
    wins = sum(1 for t in trades if t["net_r"] > 0)
    final, max_dd, curve = run_1m.portfolio_replay(trades)
    risk6 = mx.solve_risk(trades)
    if risk6:
        final6, _, curve6 = run_1m.portfolio_replay(trades, risk_pct=risk6)
    else:
        final6, curve6 = final, curve
    streak, max_dd_r = mx.entry_order_metrics(trades)
    mix = {r: sum(1 for t in trades if t["reason"] == r)
           for r in ("stop", "no_confirm", "close1", "data_end")}
    mix_wins = sum(1 for t in trades
                   if t["reason"] == "close1" and t["net_r"] > 0)
    per_market = {}
    for t in trades:
        per_market[t["market"]] = per_market.get(t["market"], 0.0) + t["net_r"]
    net_r = round(sum(t["net_r"] for t in trades), 2)
    top_mkt, top_r = (max(per_market.items(), key=lambda kv: kv[1])
                      if per_market else (None, 0.0))
    geom = {k: sum(r.get(k, 0) for r in rows)
            for k in ("refused_wide", "refused_tight", "range_unjudged")}
    return dict(
        trades=n, wins=wins,
        win_rate=round(100 * wins / n, 1) if n else None,
        net_r=net_r,
        avg_r=round(net_r / n, 3) if n else None,
        longest_losing_streak=streak, max_dd_r=max_dd_r,
        final_cash=round(final, 2), max_dd_pct=round(max_dd, 2),
        max_dd_close_pct=mx.close_dd_pct(curve),
        risk_6pct=round(risk6, 3) if risk6 else None,
        final_6pct=round(final6, 2),
        exit_mix=mix, close1_wins=mix_wins,
        markets_traded=len(per_market),
        top_market=top_mkt,
        top_market_share=(round(100 * top_r / net_r)
                          if net_r > 0 and top_r > 0 else None),
        geometry=geom,
        curve=curve6,
    )


def main():
    keys = [k for k in (run_1m.ELIGIBLE_FUTURES + run_1m.ETFS
                        + list(run_1m.BINANCE))
            if k in run_1m.HUMAN_APPROVED]
    results = {name: {"trades": [], "rows": []} for name, _p, _d in CELLS}
    skipped, sessions = [], []
    tot = {"load": 0.0, "engine": 0.0}
    t_run = time.perf_counter()
    for key in keys:
        t0 = time.perf_counter()
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
        t_load = time.perf_counter() - t0
        tot["load"] += t_load
        sessions.append([d.date for d in days])
        t0 = time.perf_counter()
        line = []
        for name, _props, dials in CELLS:
            trades, summary = run_1m.engine_1m.run_market(
                days, files, tick, **dials)
            for t in trades:
                t["market"] = key
            results[name]["trades"].extend(trades)
            results[name]["rows"].append(summary)
            line.append(f"{summary['trades']}t")
        t_engine = time.perf_counter() - t0
        tot["engine"] += t_engine
        print(f"{key}: {' '.join(line)}  |  load {t_load:.1f}s "
              f"engine {t_engine:.1f}s", flush=True)
    print(f"\nTIMING: load {tot['load']:.0f}s  |  engine "
          f"{tot['engine']:.0f}s ({len(CELLS)} cells x {len(sessions)} "
          f"markets)  |  total {time.perf_counter() - t_run:.0f}s",
          flush=True)

    calendar = run_1m.calendar_union(sessions)
    if calendar:
        print(f"CALENDAR: {len(calendar)} market days, {calendar[0]} to "
              f"{calendar[-1]}", flush=True)
    report = {}
    for name, props, dials in CELLS:
        m = measure(results[name]["trades"], results[name]["rows"])
        report[name] = dict(props=props, dials=dials,
                            color=color_for(props), **m)
        print(f"{name} [{props['stop']}, {props['band']}, rule 1 = "
              f"{props['rule1']}]: {m['trades']} trades, wr "
              f"{m['win_rate']}%, net {m['net_r']}R, streak "
              f"{m['longest_losing_streak']}, max DD {m['max_dd_pct']}% "
              f"-> at 6% DD: {m['risk_6pct']}% risk, "
              f"${m['final_6pct']:,.0f}", flush=True)

    # The rule-1 = 3 rows are variant 2 and variant 5; when the matrix JSON
    # is present and on the same data, they must agree - print the check.
    try:
        mjs = json.loads(mx.OUT_JSON.read_text(encoding="utf-8"))
        for name, vname in (("4th5th r3", "variant 2"),
                            ("hybrid r3", "variant 5")):
            v = mjs["variants"][vname]
            r = report[name]
            tag = ("MATCH" if (v["trades"], v["net_r"]) ==
                   (r["trades"], r["net_r"]) else
                   "DIFFERS (stale matrix or moved data?)")
            print(f"check vs matrix: {name} {r['trades']}t {r['net_r']}R "
                  f"vs {vname} {v['trades']}t {v['net_r']}R -> {tag}",
                  flush=True)
    except (OSError, KeyError, ValueError):
        pass

    OUT_JSON.parent.mkdir(exist_ok=True)
    built = datetime.now().strftime("%Y-%m-%d %H:%M")
    OUT_JSON.write_text(json.dumps(dict(
        strategy="quickfix1m1dc v2 - rule 1 tested-reversal sweep",
        refresh_step=REFRESH_STEP,
        built=built,
        params=dict(risk_pct=run_1m.engine_1m.RISK_PCT,
                    entry_slip_ticks=run_1m.engine_1m.ENTRY_SLIP_TICKS,
                    min_ladder=run_1m.engine_1m.MIN_LADDER,
                    published_min_tested=run_1m.engine_1m.MIN_REVERSALS),
        reversal_counts=list(REVERSAL_COUNTS),
        calendar=[d.isoformat() for d in calendar],
        cells={n: {k: v for k, v in r.items() if k != "curve"}
               for n, r in report.items()},
        trades={n: results[n]["trades"] for n, _p, _d in CELLS},
        excluded=skipped), indent=1) + "\n", encoding="utf-8")

    trades_by_cell = {n: results[n]["trades"] for n, _p, _d in CELLS}
    write_page(report, calendar, built, trades_by_cell)
    months = write_month_pages(trades_by_cell,
                               [str(d) for d in calendar], built)
    print(f"\nwrote {OUT_JSON.name}, {OUT_HTML.name} and "
          f"{len(months)} monthly pages ({month_name(months[0])} - "
          f"{month_name(months[-1])})")


def rebuild_page():
    """Redraw the page from the JSON, no backtest (`--page`), the same
    escape hatch the matrix has: the page is the part that gets edited."""
    p = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    report = {}
    for name, cell in p["cells"].items():
        trades = sorted(p["trades"][name], key=lambda t: t["entry_ts"])
        risk6 = cell.get("risk_6pct")
        _f, _d, curve = (run_1m.portfolio_replay(trades, risk_pct=risk6)
                         if risk6 else run_1m.portfolio_replay(trades))
        report[name] = dict(cell, color=color_for(cell["props"]),
                            curve=curve)
    write_page(report, p["calendar"], p.get("built", "unknown"), p["trades"])
    months = write_month_pages(p["trades"], p["calendar"],
                               p.get("built", "unknown"))
    print(f"redrew {OUT_HTML.name} and {len(months)} monthly pages from "
          f"{OUT_JSON.name} ({len(report)} cells, no backtest)")


# The page's own update control, same mechanics as the R-cut pages: probe
# 127.0.0.1:8000..8019 for charter's serve.py (the page is opened off disk,
# so it has no origin), POST text/plain so a null origin needs no CORS
# preflight, stream the log, reload when done. __STEP__ / __BUILT__ are
# replaced in write_page - a plain string, so no f-string brace-doubling.
UPDATER_JS = """
(function updater() {
  const btn = document.getElementById('updbtn');
  const note = document.getElementById('updnote');
  const log = document.getElementById('updlog');
  const STEP = '__STEP__';
  let base = null, at = 0;
  const say = t => { note.innerHTML = t; };
  function write(lines) {
    if (!lines || !lines.length) return;
    log.style.display = 'block';
    log.textContent += lines.join('\\n') + '\\n';
    log.scrollTop = log.scrollHeight;
  }
  async function probe() {
    for (let port = 8000; port < 8020; port++) {
      const url = 'http://127.0.0.1:' + port;
      try {
        const ctl = new AbortController();
        const t = setTimeout(() => ctl.abort(), 1200);
        const r = await fetch(url + '/api/refresh', {signal: ctl.signal});
        clearTimeout(t);
        if (!r.ok) continue;
        const j = await r.json();
        if (j && typeof j.state === 'string') return {url, snap: j};
      } catch (e) { /* not this port */ }
    }
    return null;
  }
  async function poll() {
    let r;
    try {
      r = await (await fetch(base + '/api/refresh?from=' + at)).json();
    } catch (e) {
      say('lost the connection to the server - the run may still be going; '
          + 'reload this page to reattach.');
      btn.disabled = false;
      return;
    }
    write(r.lines);
    at = r.next;
    if (r.state === 'running') return setTimeout(poll, 1000);
    btn.disabled = false;
    if (r.state === 'done') {
      say('done - reloading this page with the new sweep...');
      setTimeout(() => location.reload(), 900);
    } else {
      say('<b>' + r.state + '</b> - see the log below. Nothing on this '
          + 'page has changed.');
    }
  }
  async function start() {
    btn.disabled = true;
    log.textContent = '';
    at = 0;
    say('starting...');
    let r;
    try {
      r = await fetch(base + '/api/refresh', {
        method: 'POST',
        headers: {'Content-Type': 'text/plain'},
        body: JSON.stringify({steps: [STEP]})
      });
    } catch (e) {
      btn.disabled = false;
      return say('could not reach the server: ' + e.message);
    }
    if (r.status === 409) {
      say('a run is already going - following it.');
    } else if (!r.ok) {
      btn.disabled = false;
      return say('the server refused the run (HTTP ' + r.status + ').');
    } else {
      say('running - about <b>5-10 minutes</b> (ten engine passes over '
          + 'the 22 markets). You can leave this page; the run is on the '
          + 'server, and reloading reattaches to it.');
    }
    poll();
  }
  probe().then(found => {
    if (!found) {
      return say('built <b>__BUILT__</b> - to rebuild it from this page, '
        + 'start charter\\'s server (<b>python serve.py</b> in ../charter) '
        + 'and reload. By hand: <b>python build_1m_rule1_report.py</b> in '
        + 'strategy_tester.');
    }
    base = found.url;
    btn.disabled = false;
    if (found.snap.state === 'running') {
      btn.disabled = true;
      say('a run is already going - following it.');
      poll();
    }
  });
  btn.addEventListener('click', start);
})();
"""


# A count "winning" a market needs half an R of daylight before it is
# called a win or a loss; anything closer is a tie. Coarse on purpose - a
# tenth of an R between two eight-trade cells is noise, not a verdict.
TIE_R = 0.5
# Below this many rule-3 trades a market's row is dimmed and left out of
# the win/loss count: a comparison against one or two trades is not a
# comparison. Dimmed, never hidden, the house rule.
MIN_R3_TRADES = 3


def market_table(trades_by_cell, suffix, title):
    """One anchor's per-market breakdown: net R per rule-1 count, the best
    count per row shaded, rows ordered by the rule-3 result.

    Derived from the payload's own trades at page-build time (Lode,
    2026-08-26: "check per market whether rule 1 = 3 still wins"), so it
    can never lag the grid above it and `--page` rebuilds it too. The
    summary counts only markets with a rule-3 sample; the reading rules
    the first analysis surfaced are printed with the table, because two
    kinds of row flatter the flanks for free: a market that loses money at
    EVERY count (there, trading less just loses less) and a thin row
    (one or two trades is not a sample).
    """
    per = {}
    for n in REVERSAL_COUNTS:
        for t in trades_by_cell[f"{suffix} r{n}"]:
            cell = per.setdefault(t["market"], {}).setdefault(n, [0, 0.0])
            cell[0] += 1
            cell[1] += t["net_r"]

    def stat(m, n):
        return per[m].get(n, (0, 0.0))

    order = sorted(per, key=lambda m: -stat(m, 3)[1])
    wins = ties = losses = 0
    rows = []
    for m in order:
        vals = {n: stat(m, n)[1] for n in REVERSAL_COUNTS}
        best = max(REVERSAL_COUNTS, key=lambda n: vals[n])
        thin = stat(m, 3)[0] < MIN_R3_TRADES
        if not thin:
            if best == PUBLISHED_COUNT:
                wins += 1
            elif abs(vals[best] - vals[PUBLISHED_COUNT]) <= TIE_R:
                ties += 1
            else:
                losses += 1
        cells = []
        for n in REVERSAL_COUNTS:
            tr, r = stat(m, n)
            cls = " class='best'" if (tr and n == best) else ""
            cells.append(f"<td{cls}>"
                         f"{f'{tr} / {r:+.2f}' if tr else '-'}</td>")
        rows.append(f"<tr{' class=dim' if thin else ''}><td>{m}</td>"
                    + "".join(cells) + f"<td>r{best}</td></tr>")
    judged = wins + ties + losses
    summary = (f"rule 1 = {PUBLISHED_COUNT} best in <b>{wins}</b> of the "
               f"{judged} markets with a rule-3 sample, within {TIE_R}R of "
               f"the best in {ties}, beaten in {losses}; rows under "
               f"{MIN_R3_TRADES} rule-3 trades are dimmed and not counted.")
    head = "".join(
        f"<th>r{n}{' *' if n == PUBLISHED_COUNT else ''}</th>"
        for n in REVERSAL_COUNTS)
    return (f"<div><b>{title}</b><br><span class='note'>{summary}</span>"
            f"<table class='pm'><tr><th>market</th>{head}<th>best</th></tr>"
            + "".join(rows) + "</table></div>")


# ---- the monthly pages (Lode, 2026-08-27) ---------------------------------
#
# "Run the backtest over a single month and do this for all months ... if r3
# wins almost every month then that is proof of the r3 edge." One page per
# month of the backtest window, quickfix1m1dcRule1_<month>.html.
#
# THE MONTHS ARE A PARTITION OF THE FULL RUN, NOT EIGHT ISOLATED BACKTESTS.
# Every trade of the sweep is assigned to the month of its ENTRY session and
# nothing is recomputed: the engine carries state across days (the session
# lockout, a position held into the next session, the trailing range window),
# so an isolated January run would open with missing carry-ins and end with
# forced exits, and its numbers would not add up to anything. Partitioned by
# entry month, the eight tables SUM EXACTLY to the sweep page's totals, which
# is what makes "does rule 3 win every month" a decomposition of the same
# evidence rather than a new experiment.
#
# A month holds a handful of trades per cell, so the monthly winner is noisy
# by construction: the pages print net R and the ordering, and the reading
# rule beside them - read the SIGN and the consistency across months, not
# the exact figure.

MONTHS_EN = ("january", "february", "march", "april", "may", "june", "july",
             "august", "september", "october", "november", "december")


def month_name(mk):
    """`2026-01` -> `january`. Filenames carry the month name alone (Lode's
    naming); the page title carries the year too."""
    return MONTHS_EN[int(mk[5:7]) - 1]


def month_path(mk):
    return HERE / "output" / f"quickfix1m1dcRule1_{month_name(mk)}.html"


def month_stats(trades):
    n = len(trades)
    wins = sum(1 for t in trades if t["net_r"] > 0)
    net = sum(t["net_r"] for t in trades)
    return dict(trades=n, win_rate=round(100 * wins / n, 1) if n else None,
                net_r=round(net, 2), avg_r=round(net / n, 3) if n else None)


def month_links(months, current=None, main_link=False):
    """The navigation line every page in the family shares."""
    parts = []
    if main_link:
        parts.append(f"<a href='{OUT_HTML.name}'>full window</a>")
    for mk in months:
        label = month_name(mk)
        parts.append(f"<b>{label}</b>" if mk == current
                     else f"<a href='{month_path(mk).name}'>{label}</a>")
    return " &middot; ".join(parts)


def write_month_pages(trades_by_cell, calendar_iso, built):
    """One page per month of the backtest window, from the sweep's own
    trades. Returns the months written."""
    months = sorted({d[:7] for d in calendar_iso})
    # (anchor label, suffix, {cell name: {month: trades}})
    anchors = []
    for label, _mc in ANCHORS:
        suffix = "4th5th" if label == "4th/5th" else label
        by_month = {}
        for n in REVERSAL_COUNTS:
            cell = {}
            for t in trades_by_cell[f"{suffix} r{n}"]:
                cell.setdefault(t["entry_date"][:7], []).append(t)
            by_month[n] = cell
        band = mx.band_label(*mx.BAND_CUTS_BY_STOP[label][1])
        anchors.append((label, band, by_month))
    for mk in months:
        title = f"{month_name(mk).capitalize()} {mk[:4]}"
        sections = []
        for label, band, by_month in anchors:
            stats = {n: month_stats(by_month[n].get(mk, []))
                     for n in REVERSAL_COUNTS}
            best = max(REVERSAL_COUNTS,
                       key=lambda n: stats[n]["net_r"])
            rows = "".join(
                f"<tr{' class=base' if n == PUBLISHED_COUNT else ''}>"
                f"<td>r{n}{' *' if n == PUBLISHED_COUNT else ''}</td>"
                f"<td>{s['trades']}</td>"
                f"<td>{s['win_rate'] if s['win_rate'] is not None else '-'}</td>"
                f"<td{' class=best' if (n == best and s['trades']) else ''}>"
                f"{s['net_r']:+.2f}</td>"
                f"<td>{s['avg_r'] if s['avg_r'] is not None else '-'}</td>"
                f"</tr>"
                for n, s in stats.items())
            # The all-months strip: net R per count per month, this month's
            # column highlighted, so the cross-month verdict is readable
            # from any page of the family.
            strip_head = "".join(
                f"<th{' class=cur' if m == mk else ''}>{month_name(m)[:3]}"
                f"</th>" for m in months)
            strip_rows = ""
            for n in REVERSAL_COUNTS:
                vals = {m: round(sum(t['net_r']
                                     for t in by_month[n].get(m, [])), 2)
                        for m in months}
                winners = {m: max(REVERSAL_COUNTS, key=lambda k: round(
                    sum(t['net_r'] for t in by_month[k].get(m, [])), 2))
                    for m in months}
                strip_rows += (
                    f"<tr{' class=base' if n == PUBLISHED_COUNT else ''}>"
                    f"<td>r{n}{' *' if n == PUBLISHED_COUNT else ''}</td>"
                    + "".join(
                        f"<td class='{'cur ' if m == mk else ''}"
                        f"{'best' if winners[m] == n else ''}'>"
                        f"{vals[m]:+.2f}</td>" for m in months)
                    + f"<td>{sum(vals.values()):+.2f}</td></tr>")
            sections.append(
                f"<h3>{label} stop, band {band}</h3>"
                f"<table class='pm'><tr><th>rule 1</th><th>trades</th>"
                f"<th>wr%</th><th>netR</th><th>avg R</th></tr>{rows}</table>"
                f"<div class='note' style='margin-top:14px'>net R by month, "
                f"every month of the window (best count per month shaded, "
                f"this month's column boxed):</div>"
                f"<table class='pm strip'><tr><th></th>{strip_head}"
                f"<th>total</th></tr>{strip_rows}</table>")
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>quickfix1m1dc v2 - rule 1 sweep, {title}</title><style>
body {{ background:#fff; color:#222; font:13px -apple-system,Segoe UI,
sans-serif; margin:0; padding:14px; max-width:1150px; }}
.note {{ color:#666; }}
h3 {{ font-size:13px; margin:20px 0 4px; }}
.pm {{ border-collapse:collapse; margin-top:6px; }}
.pm td, .pm th {{ padding:3px 9px; border-bottom:1px solid #ddd;
text-align:right; font-size:12px; }}
.pm td:first-child, .pm th:first-child {{ text-align:left; }}
.pm td.best {{ background:#e5f5e0; }}
.pm tr.base td:first-child {{ font-weight:600; }}
.strip td.cur, .strip th.cur {{ border-left:1px solid #999;
border-right:1px solid #999; }}
#nav {{ margin-top:10px; }}
</style></head><body>
<b>quickfix1m1dc v2 - rule 1 sweep, {title}</b>
<span class="note"> The sweep's trades assigned to the month of their ENTRY
session - a partition of the full run, not an isolated backtest: the engine
carries state across days (the lockout, positions held into the next
session, the trailing window), so these tables sum exactly to the
<a href="{OUT_HTML.name}">full-window page</a>. A trade entered at the end
of the month and exited in the next counts here, in its entry month.
<b style="color:#222">A month is a handful of trades per cell</b>: read the
sign and the consistency across months, not the exact figure - the monthly
winner is noisy by construction. The rows at rule 1 = 3 (marked *) are the
published rule.</span>
<div id="nav" class="note">{month_links(months, current=mk,
                                        main_link=True)}</div>
{''.join(sections)}
<div class="note" style="margin-top:18px">built <b style="color:#222">
{built}</b> &middot; rebuilt together with the sweep: the update button on
the <a href="{OUT_HTML.name}">full-window page</a> recomputes every month,
and so does <b>--page</b>.</div>
</body></html>"""
        month_path(mk).write_text(html, encoding="utf-8")
    return months


def write_page(report, calendar, built, trades_by_cell):
    """The sweep page: one chart, one table, a checkbox per row, the
    per-market breakdown, and its own update button. Layout follows the
    matrix page."""
    lib = run_1m.LIB_PATH.read_text(encoding="utf-8")
    first = min((c[0][0] for c in (r["curve"] for r in report.values()) if c),
                default=None)
    grid = run_1m.market_day_grid(
        calendar,
        datetime.fromtimestamp(first, tz=timezone.utc).date()
        if first else date.today())
    head = "".join(
        f"<tr data-i='{i}'{' class=base' if r['props']['published'] else ''}>"
        f"<td><input type='checkbox' class='v' data-i='{i}' checked></td>"
        f"<td>{r['props']['rule1']}"
        f"{' *' if r['props']['published'] else ''}</td>"
        f"<td>{r['props']['stop']}</td><td>{r['props']['band']}</td>"
        f"<td>{r['trades']}</td><td>{r['win_rate']}</td>"
        f"<td>{r['net_r']}</td><td>{r['avg_r']}</td>"
        f"<td><b>{r['longest_losing_streak']}</b></td>"
        f"<td>{r['max_dd_r']}</td><td>{r['max_dd_pct']}%</td>"
        f"<td>{r['max_dd_close_pct']}%</td>"
        f"<td>${r['final_cash']:,.0f}</td>"
        f"<td>{str(r['risk_6pct']) + '%' if r['risk_6pct'] else '- (1%)'}</td>"
        f"<td><b>${r['final_6pct']:,.0f}</b></td>"
        f"<td>{r['close1_wins']} / "
        f"{r['exit_mix']['close1'] - r['close1_wins']} / "
        f"{r['exit_mix']['stop']}</td>"
        f"<td>{r['top_market'] or ''}"
        f"{(' ' + str(r['top_market_share']) + '%') if r['top_market_share'] else ''}</td>"
        f"<td><i style='background:{r['color']}'></i></td></tr>"
        for i, r in enumerate(report.values()))
    series = "\n".join(
        f"series.push(chart.addLineSeries({{color:'{r['color']}', "
        f"lineWidth:2, lineType:LightweightCharts.LineType.WithSteps, "
        f"priceLineVisible:false, lastValueVisible:false}})"
        f");\nseries[series.length-1].setData("
        f"{json.dumps([{'time': run_1m.grid_seconds(d), 'value': v}
                       for d, v in run_1m.carry_forward(r['curve'], grid)])});"
        for r in report.values())
    updater = (UPDATER_JS.replace("__STEP__", REFRESH_STEP)
               .replace("__BUILT__", built))
    pm = "".join(
        market_table(trades_by_cell,
                     "4th5th" if label == "4th/5th" else label,
                     f"{label} stop, band "
                     f"{mx.band_label(*mx.BAND_CUTS_BY_STOP[label][1])}")
        for label, _mc in ANCHORS)
    months = sorted({str(d)[:7] for d in calendar})
    month_nav = month_links(months)
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>quickfix1m1dc v2 - rule 1 sweep (tested reversals)</title><style>
body {{ background:#fff; color:#222; font:13px -apple-system,Segoe UI,
sans-serif; margin:0; padding:14px; }}
#chart {{ height:calc(100vh - 330px); min-height:480px; }}
/* SCOPED TO #tbl - a bare `table` rule also hits the <table>
   lightweight-charts builds inside the chart container (see the matrix
   page's note). */
#tbl {{ border-collapse:collapse; margin-top:14px; }}
#tbl td, #tbl th {{ padding:4px 10px; border-bottom:1px solid #ddd;
text-align:right; }}
#tbl td:first-child, #tbl th:first-child,
#tbl td:nth-child(2), #tbl th:nth-child(2),
#tbl td:nth-child(3), #tbl th:nth-child(3),
#tbl td:nth-child(4), #tbl th:nth-child(4) {{ text-align:left; }}
/* The property columns are boxed off from the metrics beside them. */
#tbl td:nth-child(4), #tbl th:nth-child(4) {{ border-right:2px solid #bbb; }}
#tbl td i {{ display:inline-block; width:22px; height:10px; }}
#tbl tr.off td {{ opacity:.35; }}
#tbl tr.base td:nth-child(2) {{ font-weight:600; }}
#ctl {{ margin-top:10px; }}
#ctl button, #updbtn {{ font:inherit; padding:2px 10px; margin-right:6px; }}
#upd {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap;
margin-top:12px; padding:9px 12px; border:1px solid #ddd;
border-radius:8px; max-width:1150px; }}
#updbtn {{ font-weight:600; padding:5px 13px; border:1px solid #999;
border-radius:6px; background:#f2f1ec; cursor:pointer; }}
#updbtn:disabled {{ opacity:.45; cursor:default; }}
#updlog {{ display:none; margin-top:10px; max-width:1150px; max-height:340px;
overflow:auto; background:#14150f; color:#d7d6cd; border-radius:8px;
padding:10px 12px; font:11.5px ui-monospace,Consolas,monospace;
white-space:pre-wrap; }}
.note {{ color:#666; }}
/* The per-market breakdown: one table per anchor, side by side. Scoped
   class, same reason as #tbl. */
#pm {{ display:flex; gap:34px; flex-wrap:wrap; align-items:flex-start;
margin-top:8px; }}
.pm {{ border-collapse:collapse; margin-top:6px; }}
.pm td, .pm th {{ padding:3px 8px; border-bottom:1px solid #ddd;
text-align:right; font-size:12px; }}
.pm td:first-child, .pm th:first-child {{ text-align:left; }}
.pm td.best {{ background:#e5f5e0; }}
.pm tr.dim td {{ opacity:.45; }}
</style></head><body>
<b>quickfix1m1dc v2 - rule 1 sweep: how many reversals must be tested
before the setup arms</b>
<span class="note"> The published rule 1 arms a setup once
<b style="color:#222">3</b> reversals of the ladder have been tested by the
session's running extreme; entry is still the retrace to the FIRST
reversal. This page runs the same model at <b style="color:#222">1, 2, 3,
4 and 5</b> tested reversals, on the two published configurations - the
4th/5th stop with its band 000-060 (the dials of variant 2, the published
baseline) and the hybrid stop with its band 020-060 (variant 5). At
<b style="color:#222">rule 1 = 1</b> the setup arms on the first touch of
the first reversal itself: the touch bar needs its close back beyond the
level (OHLC cannot order the events inside one bar), and any later print
fires the market order at once. Rule 2 is unchanged at every count - the
day open is judged against the ladder's second reversal, tested or not.
Every cell is its own engine run on the filtered universe (22 markets,
s.16): rule 1 decides WHEN a setup arms, so a different count shifts which
minute triggers and which session spends its lockout - no blotter filter
can reproduce that. The rows at rule 1 = 3 (marked *) ARE variant 2 and
variant 5, re-measured on this pass. Everything else sits at the published
baseline: lockout 1, no tightening, overnight window blocked, no
confirmation clause, trading-day range window.</span>
<div class="note" style="margin-top:8px"><b style="color:#222">The curves
are drawn at a constant 6% max drawdown</b> - risk per trade solved per
cell by bisection (the table's <b>risk @6% DD</b> column), because at one
bet size the tallest curve is partly just the deepest hole that cell was
allowed to dig. <b style="color:#222">Colour</b>: green is the 4th/5th
stop, blue the hybrid; the darkest shade is the published count (3), and
the further a count sits from it the lighter its line (4, then 2, then 1,
lightest 5). Read the losing streak, the drawdown and the top-market share
before the money: a count that books few trades is a thin sample, not a
better rule.</div>
<div id="upd">
  <button id="updbtn" type="button" disabled>Update this sweep</button>
  <span id="updnote" class="note">built <b style="color:#222">{built}</b>
  &middot; this page is not rebuilt by charter's Update button; it is ten
  engine passes, about <b style="color:#222">5-10 minutes</b>. Press this
  when you want it re-read on current data.</span>
</div>
<pre id="updlog"></pre>
<div id="chart"></div>
<div id="ctl"><button id="allon">all on</button>
<button id="alloff">all off</button>
<span class="note">- untick a row to drop its curve; the baseline too.</span></div>
<table id="tbl"><tr><th></th><th>rule 1</th>
<th>stop</th><th>band</th>
<th>trades</th><th>wr%</th><th>netR</th><th>avg R</th>
<th>longest losing streak</th><th>max DD (R)</th><th>max DD %</th>
<th>max DD close %</th><th>final @1%</th>
<th>risk @6% DD</th><th>final @6% DD</th>
<th>day-2 win / day-2 loss / stop</th>
<th title="the market carrying the largest share of the cell's net R">top market</th>
<th></th></tr>{head}</table>
<div style="margin-top:20px"><b>Per market: does rule 1 = 3 hold
everywhere?</b>
<span class="note"> Trades / net R per market per count, rows ordered by
the rule-3 result, the best count of each row shaded. Read the shading
with two rules: a "win" on a market that loses money at EVERY count is
less exposure to a losing market, not a better arming rule, and a dimmed
row (under 3 rule-3 trades) is not a sample. Derived from the same trades
as the grid above, on every build.</span></div>
<div id="pm">{pm}</div>
<div style="margin-top:20px"><b>Month by month</b>
<span class="note"> the same trades partitioned by entry month, one page
per month (they sum exactly to this page's totals):</span><br>
<span class="note">{month_nav}</span></div>
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
{updater}
</script></body></html>"""
    OUT_HTML.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    if "--page" in sys.argv[1:]:
        rebuild_page()
    else:
        main()
