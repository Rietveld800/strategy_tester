# build_1m_exit_profile_page.py
#
# The PAGE of the pre-registered exit-timing study: draws what
# research_1m_exit_profile.py measured (output/quickfix1m1dc_exit_profile.json)
# and nothing more. No engine passes, no bar loading - it reads the study's
# own JSON, recomputes the per-horizon bootstrap intervals from the
# per-trade values it carries, and writes ONE additional file,
# output/quickfix1m1dc_exit_profile.html. It touches nothing else in
# output/ (Lode, 2026-08-28), is not in the refresh chain and has no update
# button: the study is a reading, re-run by hand.
#
# WHAT THE PAGE DRAWS IS A SUBSET OF WHAT THE STUDY MEASURED (Lode,
# 2026-08-30): variant 5 only (the hybrid stop), the 'all' universe
# only (every taken trade, the discontinued markets included - Lode's
# choice after the 17-market page read 74 of variant 5's 88 trades), and
# the horizons WITHOUT settle2 .. settle12 - every
# session's open and close stay, and so do settle0 and settle1, the
# deciding horizons. The study itself is unchanged: it still runs both
# samples, both universes and all forty-two horizons as pre-registered,
# and the verdict lines printed here are ITS verdicts, read on the full
# list (P2's "every later horizon" includes the settlements the page
# does not draw). The null was run on the 'all' universe, so its line
# and table are on the page. P4 is shown for the hybrid anchor alone,
# to match. PAGE_SAMPLES / PAGE_UNIVERSES /
# PAGE_HORIZONS / PAGE_P4_ANCHORS below are the whole of that choice.
#
# Per sample and universe drawn, in R units:
#   - the mean excursion profile m(h) on the unconstrained path (the SIGNAL)
#     with its 95% day-cluster bootstrap interval, the stop-truncated path
#     (the TRADE) beside it, and the null's mean where it was run;
#   - the per-trade Sharpe S(h) of both paths;
#   - the statistics table and the verdict lines exactly as the reading
#     printed them.
# Then the P4 tables and the combined verdicts.
#
# Charts are inline SVG: categorical horizons need no time axis, and
# the page stays self-contained.
#
# Usage: python build_1m_exit_profile_page.py

import html
import json
from pathlib import Path

import numpy as np

import research_1m_exit_profile as ep

HERE = Path(__file__).resolve().parent
OUT_HTML = HERE / "output" / "quickfix1m1dc_exit_profile.html"
CI_REPS = 4000

PAGE_SAMPLES = ("variant 4",)
PAGE_UNIVERSES = ("all",)
PAGE_HORIZONS = [n for n in ep.H_NAMES
                 if not (n.startswith("settle") and int(n[6:]) >= 2)]
PAGE_P4_ANCHORS = ("hybrid",)

COL_U = "#1A4889"      # unconstrained path
COL_T = "#B0402A"      # stop-truncated path
COL_N = "#888"         # the null's mean
W, H = 1500, 320
PAD_L, PAD_R, PAD_T, PAD_B = 46, 14, 14, 52


def esc(s):
    return html.escape(str(s))


def fmt(x, p=3):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x:.{p}f}"


def horizon_series(rows, path, denom="R"):
    """Per horizon: (values, clusters) for the excursion of one path."""
    field = "x" if path == "unconstrained" else "x_trunc"
    out = {}
    for name in PAGE_HORIZONS:
        vals, cl, _ = ep.series(rows, name, field, denom)
        out[name] = (vals, cl)
    return out


def profile_with_ci(rows, path):
    """[(mean, lo, hi, n) per horizon]; the CI is the day-cluster
    bootstrap of the reading, at a reduced rep count for the page."""
    out = []
    for name, (vals, cl) in horizon_series(rows, path).items():
        if vals.size == 0:
            out.append((None, None, None, 0))
            continue
        b = ep.cluster_bootstrap_mean(vals, cl, reps=CI_REPS)
        out.append((b["mean"], b["ci_lo"], b["ci_hi"], int(vals.size)))
    return out


def sharpe_line(rows, path):
    out = []
    for _name, (vals, _cl) in horizon_series(rows, path).items():
        if vals.size < 2 or vals.std(ddof=1) == 0:
            out.append(None)
        else:
            out.append(float(vals.mean() / vals.std(ddof=1)))
    return out


def svg_chart(title, lines, ylabel, zero=True):
    """lines: list of dict(name, color, values[len(H_NAMES)], ci=[(lo,hi)]|None,
    dash=bool). Values may be None."""
    xs = [PAD_L + i * (W - PAD_L - PAD_R) / (len(PAGE_HORIZONS) - 1)
          for i in range(len(PAGE_HORIZONS))]
    allv = [v for ln in lines for v in ln["values"] if v is not None]
    for ln in lines:
        for c in ln.get("ci") or []:
            if c is not None:
                allv += [c[0], c[1]]
    if not allv:
        return f"<div class='nochart'>{esc(title)}: nothing to draw</div>"
    lo, hi = min(allv + [0.0]), max(allv + [0.0])
    span = (hi - lo) or 1.0
    lo -= 0.06 * span
    hi += 0.06 * span

    def y(v):
        return PAD_T + (hi - v) / (hi - lo) * (H - PAD_T - PAD_B)

    parts = [f"<svg viewBox='0 0 {W} {H}' class='chart'>",
             f"<text x='{PAD_L}' y='11' class='ct'>{esc(title)}</text>"]
    # y ticks
    step = nice_step(hi - lo)
    t = np.ceil(lo / step) * step
    while t <= hi:
        parts.append(f"<line x1='{PAD_L}' x2='{W - PAD_R}' y1='{y(t):.1f}' "
                     f"y2='{y(t):.1f}' class='grid'/>")
        parts.append(f"<text x='{PAD_L - 4}' y='{y(t) + 3:.1f}' "
                     f"class='yt'>{t:.2f}</text>")
        t += step
    if zero and lo < 0 < hi:
        parts.append(f"<line x1='{PAD_L}' x2='{W - PAD_R}' y1='{y(0):.1f}' "
                     f"y2='{y(0):.1f}' class='zero'/>")
    # x labels
    for i, name in enumerate(PAGE_HORIZONS):
        parts.append(f"<text x='{xs[i]:.1f}' y='{H - PAD_B + 14}' class='xt' "
                     f"transform='rotate(-40 {xs[i]:.1f} {H - PAD_B + 14})'>"
                     f"{esc(name)}</text>")
    parts.append(f"<text x='{W - PAD_R}' y='11' class='yl' "
                 f"text-anchor='end'>{esc(ylabel)}</text>")
    for ln in lines:
        pts = [(xs[i], y(v)) for i, v in enumerate(ln["values"])
               if v is not None]
        if ln.get("ci"):
            for i, c in enumerate(ln["ci"]):
                if c is None:
                    continue
                parts.append(f"<line x1='{xs[i]:.1f}' x2='{xs[i]:.1f}' "
                             f"y1='{y(c[0]):.1f}' y2='{y(c[1]):.1f}' "
                             f"stroke='{ln['color']}' stroke-width='1.2' "
                             f"opacity='0.7'/>")
                for v in c:
                    parts.append(f"<line x1='{xs[i] - 3:.1f}' x2='{xs[i] + 3:.1f}' "
                                 f"y1='{y(v):.1f}' y2='{y(v):.1f}' "
                                 f"stroke='{ln['color']}' stroke-width='1.2' "
                                 f"opacity='0.7'/>")
        if len(pts) > 1:
            d = " ".join(f"{'M' if k == 0 else 'L'}{px:.1f},{py:.1f}"
                         for k, (px, py) in enumerate(pts))
            dash = " stroke-dasharray='5,4'" if ln.get("dash") else ""
            parts.append(f"<path d='{d}' fill='none' stroke='{ln['color']}' "
                         f"stroke-width='2'{dash}/>")
        for px, py in pts:
            parts.append(f"<circle cx='{px:.1f}' cy='{py:.1f}' r='2.6' "
                         f"fill='{ln['color']}'/>")
    # legend
    lx = PAD_L + 6
    for ln in lines:
        parts.append(f"<line x1='{lx}' x2='{lx + 16}' y1='{PAD_T + 8}' "
                     f"y2='{PAD_T + 8}' stroke='{ln['color']}' stroke-width='2'"
                     f"{' stroke-dasharray=\"5,4\"' if ln.get('dash') else ''}/>")
        parts.append(f"<text x='{lx + 20}' y='{PAD_T + 11}' class='lg'>"
                     f"{esc(ln['name'])}</text>")
        lx += 24 + 6.2 * len(ln["name"])
    parts.append("</svg>")
    return "".join(parts)


def nice_step(span):
    raw = span / 5.0
    mag = 10 ** np.floor(np.log10(raw)) if raw > 0 else 1.0
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def stats_table(stats, path_label):
    # top market, share % and the session-ended count are in the study's
    # txt and not on the page (Lode, 2026-08-30).
    head = ("<tr><th>horizon</th><th>n</th><th>mean R</th><th>sd</th>"
            "<th>hit</th><th>Sharpe</th><th>median</th><th>MFE</th><th>MAE</th>"
            "<th>e-ratio</th></tr>")
    body = []
    for name in PAGE_HORIZONS:
        s = stats[name]
        if not s.get("n"):
            body.append(f"<tr class='dim'><td>{esc(name)}</td><td>0</td>"
                        f"<td colspan='8'>no horizon</td></tr>")
            continue
        cls = " class='dim'" if s["n"] < ep.MIN_N else ""
        body.append(
            f"<tr{cls}><td>{esc(name)}</td><td>{s['n']}</td>"
            f"<td>{fmt(s['mean'])}</td><td>{fmt(s['sd'])}</td>"
            f"<td>{fmt(s['hit'], 2)}</td><td>{fmt(s['sharpe'])}</td>"
            f"<td>{fmt(s['median'])}</td><td>{fmt(s['mfe'])}</td>"
            f"<td>{fmt(s['mae'])}</td><td>{fmt(s['e_ratio'], 2)}</td>"
            f"</tr>")
    return (f"<div class='tt'>{esc(path_label)}</div><table class='st'>"
            f"{head}{''.join(body)}</table>")


def verdict_block(preds, top_ok, shares):
    p1, p2, p3 = preds["P1"], preds["P2"], preds["P3"]

    def bl(b):
        if not b:
            return "n/a"
        return (f"mean {b['mean']:+.3f}, 95% [{b['ci_lo']:+.3f}, "
                f"{b['ci_hi']:+.3f}], P(&le;0) {b['p_le_0']:.3f}")
    lines = [
        f"<b>P1</b> rise (settle0 &minus; 30m): {bl(p1['rise'])}, rose = "
        f"{p1['rose']}; descriptive day-1 session (settle1 &minus; settle0): "
        f"{bl(p1.get('day1'))}; overnight gap (open1 &minus; close0): "
        f"{bl(p1.get('gap'))} &rarr; <b>{esc(p1['verdict'])}</b>",
        f"<b>P2</b> Sharpe peak at "
        f"'{esc(p2.get('peak', '-'))}', every later horizon lower than settle1: "
        f"{p2.get('declines', '-')} &rarr; <b>{esc(p2['verdict'])}</b>",
        f"<b>P3</b> stops inside the entry session: {p3['inside']}/"
        f"{p3['n_stops']}"
        + (f" = {100 * p3['share']:.0f}%" if p3['share'] is not None else "")
        + f" &rarr; <b>{esc(p3['verdict'])}</b>",
        f"top-market share at the deciding horizons: "
        f"{[round(float(s), 1) if s is not None else None for s in shares]}"
        f" &rarr; {'ok' if top_ok else '<b class=bad>carried by one market</b>'}",
    ]
    return "<ul class='vd'>" + "".join(f"<li>{ln}</li>" for ln in lines) + "</ul>"


def sample_section(label, sres):
    rows = sres["trades"]
    anchor = sres.get("anchor", "")
    if "all" not in sres and label in sres:
        # the first run's JSON nested the readings one level down
        sres = dict(sres, **sres[label])
    out = [f"<h2>{esc(label)} &mdash; {esc(anchor)} &mdash; {sres['n']} trades profiled"
           f"{', ' + str(sres['failures']) + ' not placed' if sres['failures'] else ''}</h2>"]
    for uname in PAGE_UNIVERSES:
        u = sres.get(uname)
        if not u:
            continue
        urows = (rows if uname == "all"
                 else [r for r in rows if r["market"] not in ep.DISCONTINUED])
        pu = profile_with_ci(urows, "unconstrained")
        pt = profile_with_ci(urows, "truncated")
        lines = [
            dict(name=ep.PATH_LABEL["unconstrained"], color=COL_U,
                 values=[p[0] for p in pu],
                 ci=[(p[1], p[2]) if p[0] is not None else None for p in pu]),
            dict(name=ep.PATH_LABEL["truncated"], color=COL_T,
                 values=[p[0] for p in pt]),
        ]
        null = u.get("null")
        if null:
            lines.append(dict(name="null mean", color=COL_N, dash=True,
                              values=[null[n].get("null_mean")
                                      if null[n].get("null_reps") else None
                                      for n in PAGE_HORIZONS]))
        c1 = svg_chart(f"mean excursion m(h), R units - {uname}", lines,
                       "R per trade; whiskers = 95% day-cluster bootstrap")
        c2 = svg_chart(f"per-trade Sharpe S(h) - {uname}", [
            dict(name=ep.PATH_LABEL["unconstrained"], color=COL_U,
                 values=sharpe_line(urows, "unconstrained")),
            dict(name=ep.PATH_LABEL["truncated"], color=COL_T,
                 values=sharpe_line(urows, "truncated"))],
            "mean / sd of x(h)")
        r = u["R"]
        out.append(f"<h3>universe: {esc(uname)} &mdash; {len(urows)} trades</h3>")
        out.append(f"<div class='charts'>{c1}{c2}</div>")
        out.append(stats_table(r["unconstrained"],
                               f"{ep.PATH_LABEL['unconstrained']}, R units"))
        out.append(stats_table(r["truncated"],
                               f"{ep.PATH_LABEL['truncated']} - {anchor}, R units"))
        shares = [r["unconstrained"][n].get("top_share") for n in ep.DECIDING]
        out.append("<div class='tt'>verdicts, R units</div>"
                   + verdict_block(r["predictions"], r["top_share_ok"], shares))
        rg = u["range"]
        shares_g = [rg["unconstrained"][n].get("top_share") for n in ep.DECIDING]
        out.append("<div class='tt'>verdicts, trailing trading-day range units"
                   "</div>" + verdict_block(rg["predictions"],
                                            rg["top_share_ok"], shares_g))
        if null:
            out.append(null_table(null))
    comb = sres.get("combined", {})
    out.append("<div class='tt'>combined verdicts - the study's, over both "
               "universes (all AND the 17 markets, the latter not on this "
               "page) and both denominators</div><ul class='vd'>"
               + "".join(f"<li><b>{esc(k)}</b>: {esc(v)}</li>"
                         for k, v in comb.items()) + "</ul>")
    return "".join(out)


def null_table(null):
    head = ("<tr><th>horizon</th><th>n</th><th>observed</th><th>null mean</th>"
            "<th>null sd</th><th>percentile</th><th>placements</th></tr>")
    body = []
    for name in PAGE_HORIZONS:
        s = null[name]
        if not s.get("null_reps"):
            body.append(f"<tr class='dim'><td>{esc(name)}</td>"
                        f"<td colspan='6'>no null</td></tr>")
            continue
        body.append(f"<tr><td>{esc(name)}</td><td>{s['n']}</td>"
                    f"<td>{fmt(s['observed'])}</td><td>{fmt(s['null_mean'])}</td>"
                    f"<td>{fmt(s['null_sd'])}</td><td>{fmt(s['percentile'])}</td>"
                    f"<td>{s['placements']}</td></tr>")
    return ("<div class='tt'>null: the same geometry at random minutes of the "
            "same market, same session time-of-day &plusmn;30m, other days "
            f"({ep.PATH_LABEL['unconstrained']}, R units)</div>"
            f"<table class='st'>{head}{''.join(body)}</table>")


def p4_section(p4):
    if not p4:
        return "<h2>P4</h2><p>rule 1 sweep payload not found</p>"
    out = ["<h2>P4 &mdash; rule 1 = 3 against the marginal trades of lower "
           "counts (unpowered by construction; recorded for the forward "
           "window)</h2>"]
    for anchor in PAGE_P4_ANCHORS:
        cells = p4.get(anchor)
        if not cells:
            out.append(f"<p>{esc(anchor)}: not in the payload</p>")
            continue
        for rn, hres in cells.items():
            head = ("<tr><th>horizon</th><th>n r3</th><th>n marginal</th>"
                    "<th>m(r3)</th><th>m(marginal)</th><th>diff</th>"
                    "<th>95% CI</th><th>P(&le;0)</th></tr>")
            body = []
            for name in PAGE_HORIZONS:
                h = hres.get(name)
                if not h:
                    body.append(f"<tr class='dim'><td>{esc(name)}</td>"
                                f"<td colspan='7'>no horizon</td></tr>")
                    continue
                cls = (" class='dim'" if min(h['n_r3'], h['n_marg']) < ep.MIN_N
                       else "")
                d = h["diff"]
                body.append(f"<tr{cls}><td>{esc(name)}</td><td>{h['n_r3']}</td>"
                            f"<td>{h['n_marg']}</td><td>{fmt(h['m_r3'])}</td>"
                            f"<td>{fmt(h['m_marg'])}</td><td>{d['mean']:+.3f}</td>"
                            f"<td>[{d['ci_lo']:+.3f}, {d['ci_hi']:+.3f}]</td>"
                            f"<td>{d['p_le_0']:.3f}</td></tr>")
            out.append(f"<div class='tt'>{esc(anchor)}: r3 vs {esc(rn)}-only "
                       f"({ep.PATH_LABEL['unconstrained']}, R units)</div>"
                       f"<table class='st'>{head}{''.join(body)}</table>")
    return "".join(out)


CSS = """
body { background:#fff; color:#222; font:13px -apple-system,Segoe UI,sans-serif;
       margin:0; padding:16px 22px; max-width:1560px; }
h1 { font-size:20px; margin:0 0 4px; }
h2 { font-size:16px; margin:28px 0 6px; border-bottom:1px solid #ddd;
     padding-bottom:4px; }
h3 { font-size:14px; margin:18px 0 6px; }
.meta { color:#555; margin-bottom:10px; }
.rules { background:#f5f5f5; border:1px solid #e3e3e3; padding:10px 14px;
         margin:10px 0 16px; line-height:1.5; }
.charts { display:flex; flex-wrap:wrap; gap:16px; margin:8px 0 12px; }
.chart { width:1500px; height:320px; background:#fff; border:1px solid #e6e6e6; }
.ct { font-size:12px; font-weight:600; fill:#222; }
.yt { font-size:10px; fill:#555; text-anchor:end; }
.xt { font-size:10px; fill:#444; text-anchor:end; }
.yl { font-size:10px; fill:#777; }
.lg { font-size:10px; fill:#333; }
.grid { stroke:#eee; stroke-width:1; }
.zero { stroke:#999; stroke-width:1; stroke-dasharray:3,3; }
.tt { font-weight:600; margin:12px 0 4px; }
table.st { border-collapse:collapse; margin-bottom:8px; }
table.st th, table.st td { padding:3px 9px; border-bottom:1px solid #e4e4e4;
                           text-align:right; white-space:nowrap; }
table.st th:first-child, table.st td:first-child { text-align:left; }
table.st th { background:#f3f3f3; font-weight:600; }
tr.dim td { color:#aaa; }
ul.vd { margin:4px 0 10px 18px; line-height:1.55; }
.bad { color:#B0402A; }
.nochart { color:#888; padding:20px; }
.foot { color:#666; margin-top:28px; border-top:1px solid #ddd;
        padding-top:8px; }
@media print { .charts { break-inside:avoid; } h2 { break-before:page; } }
"""


def build():
    data = json.loads(ep.OUT_JSON.read_text(encoding="utf-8"))
    parts = [f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
             f"<title>quickfix1m1dc - exit-timing profile (pre-registered)</title>"
             f"<style>{CSS}</style></head><body>",
             "<h1>quickfix1m1dc &mdash; the exit-timing profile, variant 4 "
             "(hybrid stop), every taken trade</h1>",
             f"<div class='meta'>study built {esc(data['built'])} &middot; "
             f"pre-registration <code>{esc(data['doc'])}</code> &middot; reading "
             f"<code>output/quickfix1m1dc_exit_profile.txt</code> &middot; "
             f"taken trades only &middot; this page draws the study's JSON and "
             f"decides nothing</div>",
             "<div class='rules'>"
             "<b>What is drawn.</b> For every taken trade, the signed excursion "
             "from the first-reversal price at FIXED horizons: 30m, 1h, 2h, 4h "
             "after entry, then the entry day's settlement (settle0) and last "
             "print (close0), the next settlement (settle1, the engine's close1 "
             "exit moment), and for days 1-12 each session's first print "
             "(openN) and last print (closeN). "
             "<b>This page is one reading of the study.</b> The pre-registered "
             "study reads two samples (the published variant 1 and variant 4), "
             "two universes (every taken trade / the 17 surviving markets) and "
             f"{len(ep.H_NAMES)} horizons; the whole of it is in the .txt. This "
             "page shows ONE of those readings: <b>variant 4</b>, universe "
             "<b>all</b> (every taken trade, the discontinued markets CC, KC, "
             f"UDOW, UNG, USO included), at {len(PAGE_HORIZONS)} of the "
             f"{len(ep.H_NAMES)} horizons - settle2 .. settle12 are left out, "
             "every session's open and close stay, and so do settle0 and "
             "settle1, the deciding horizons. Charts and tables are that "
             "reading's numbers unchanged. The verdict lines are the study's, "
             "computed on its full horizon list, so P2's 'every later horizon' "
             "includes the settlements not drawn here. The 'combined verdicts' "
             "block folds this reading together with the 17-market one and "
             "both denominators (reading rules 4 and 6), which is why it can "
             "read differently from the verdicts printed above it. "
             "<b>Two paths.</b> <i>Signal path (no stop)</i> = the market after a "
             "qualifying trigger, followed as if no stop existed. <i>Trade path "
             "(stop as booked)</i> = the same path frozen at the trade's OWN stop "
             "- the one the blotter recorded at entry, the hybrid stop for "
             "variant 4, named in each heading - from the first bar after the "
             "entry bar that prints it; "
             "no scheduled exit, so a point on it is the position still open "
             "with its stop, marked at that moment. "
             f"<b>Rules fixed before the run:</b> flat = 95% interval covers 0 and "
             f"point estimate under {data['flat_r']}R; a horizon under n = "
             f"{data['min_n']} is dimmed; a deciding horizon with one market over "
             f"{data['top_share_max']:.0f}% of the summed excursion forbids 'not "
             f"rejected'. Bootstrap reps {data['reps']}, seed {data['seed']}, null "
             f"placements {data['null_b']}. No exit rule is swept and no optimum "
             "is read off these curves.</div>"]
    for label in PAGE_SAMPLES:
        sres = data["samples"].get(label)
        if sres is None:
            raise SystemExit(f"{label!r} is not in the study JSON")
        parts.append(sample_section(label, sres))
    parts.append(p4_section(data.get("P4")))
    parts.append("<div class='foot'>Verdict ceiling on this sample: 'not "
                 "rejected', never 'confirmed'. The forward window is the next "
                 "sample. This file is ADDITIONAL output; nothing else in "
                 "output/ is written by the study.</div></body></html>")
    OUT_HTML.write_text("".join(parts), encoding="utf-8")
    print(f"wrote {OUT_HTML.name} ({OUT_HTML.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
