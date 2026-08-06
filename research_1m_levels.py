"""Research: what happens when the SAME reversal levels are traded again.

Lode's observation (2026-08-06, from wheat trades 1-5, five stop-outs in
one session on one market): a winner typically tests the cluster, fires,
and never comes back, while a market that oscillates across the same
levels stops us out again and again. If that is real, the number of
times a cluster has already been tested predicts the next attempt.

NOTHING HERE CHANGES THE STRATEGY. It measures the published baseline so
the problem is understood before anything is designed against it.

Two units of "again", both reported, because they answer different
questions:

  ATTEMPT   another TRADE on the same levels. This is Lode's own
            phrasing: how many losses came before this winner, how long
            the losing streak on one level ran.
  TEST      another TOUCH of the level, whether or not it produced a
            trade. A test that the engine refused (position open, day
            already refused by rule 2) still tells the market's story,
            so the touch count is the wider measure of the same idea.

"The same levels" = same market, same side, same FIRST REVERSAL price,
inside one continuous LEVEL RUN (the consecutive array files that carry
that level as an eligible ladder member). A level that is elected and
reappears later starts a fresh episode rather than continuing the old
one - the market has been somewhere else in between.

A TEST is a maximal run of consecutive minutes whose bar range contains
the level; price has to leave and come back to be tested again.

Output: output/quickfix1m1dc_levels.json (the per-trade table and the
episodes) and output/quickfix1m1dc_levels.html (the readable version, in
the daily reports' format).

Usage: venv\\Scripts\\python.exe research_1m_levels.py [KEY ...]
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

import engine_1m
import run_1m
from build_1m_report import STUDY_BASE, cls, esc, signed, stamp
from build_equity_html import CSS

HERE = Path(__file__).resolve().parent
IN_JSON = HERE / "output" / "quickfix1m1dc_all.json"
OUT_JSON = HERE / "output" / "quickfix1m1dc_levels.json"
OUT_HTML = HERE / "output" / "quickfix1m1dc_levels.html"


# --------------------------------------------------------------- level runs

def eligible(f, side):
    """The ladder the engine would use under file f, on this side."""
    if side == "short":
        return [x for x in f.bull if x > f.prev_close]
    return sorted((x for x in f.bear if x < f.prev_close), reverse=True)


def level_runs(files, side):
    """{level: [(run_index, first_file_i, last_file_i), ...]} by activation
    order. A run breaks when a file does not carry the level."""
    runs = defaultdict(list)
    open_run = {}
    for i, f in enumerate(files):
        have = set(eligible(f, side))
        for lvl in list(open_run):
            if lvl not in have:
                start = open_run.pop(lvl)
                runs[lvl].append((start, i - 1))
        for lvl in have:
            open_run.setdefault(lvl, i)
    for lvl, start in open_run.items():
        runs[lvl].append((start, len(files) - 1))
    return runs


def run_of(runs, lvl, file_i):
    for k, (a, b) in enumerate(runs.get(lvl, [])):
        if a <= file_i <= b:
            return k, a, b
    return None


# -------------------------------------------------------------------- tests

def count_tests(bars, level, t0, t1):
    """Maximal runs of minutes whose range contains `level`, in [t0, t1].

    Consecutive touching minutes are ONE test: a level that price sits on
    for six minutes was tested once, not six times.
    """
    n, inside = 0, False
    for ts, _o, h, l, _c in bars:
        if ts < t0 or ts > t1:
            continue
        hit = l <= level <= h
        if hit and not inside:
            n += 1
        inside = hit
    return n


def annotate(rows):
    """Attempt bookkeeping, from the rows alone. Idempotent, so the page
    can re-derive it without paying for the bar scan again."""
    rows.sort(key=lambda r: r["entry_ts"])
    seen = defaultdict(list)
    for r in rows:
        prior = seen[r["episode"]]
        r["attempt"] = len(prior) + 1
        r["prior_losses"] = 0
        for p in reversed(prior):
            if p["net_r"] > 0:
                break
            r["prior_losses"] += 1
        r["prior_wins"] = sum(1 for p in prior if p["net_r"] > 0)
        r["same_day_prior"] = sum(1 for p in prior
                                  if p["entry_date"] == r["entry_date"])
        prior.append(r)
    # position within the market-DAY, whatever level it fired on: the
    # sharpest cut in the data, and the one Lode actually saw
    byday = defaultdict(list)
    for r in rows:
        byday[(r["market"], r["entry_date"])].append(r)
    for seq in byday.values():
        for n, r in enumerate(seq, 1):
            r["nth_today"] = n
            r["n_today"] = len(seq)
    episodes = []
    for ep, members in seen.items():
        wins = [m for m in members if m["net_r"] > 0]
        episodes.append(dict(
            episode=ep, market=members[0]["market"], side=members[0]["side"],
            level=members[0]["level"], n=len(members), wins=len(wins),
            net_r=round(sum(m["net_r"] for m in members), 3),
            sequence="".join("W" if m["net_r"] > 0 else "L" for m in members),
            first=members[0]["entry_ts"], last=members[-1]["entry_ts"],
            days=len({m["entry_date"] for m in members}),
            run_files=members[0]["run_files"],
            tests_first=members[0]["tests_in_run"],
            tests_last=members[-1]["tests_in_run"]))
    episodes.sort(key=lambda e: (-e["n"], e["net_r"]))
    size = {e["episode"]: e["n"] for e in episodes}
    for r in rows:
        r["episode_n"] = size[r["episode"]]
    return episodes


def main(keys=None):
    data = json.loads(IN_JSON.read_text(encoding="utf-8"))
    trades = sorted(data["trades"], key=lambda t: t["entry_ts"])
    by_key = defaultdict(list)
    for i, t in enumerate(trades):
        by_key[t["market"]].append(i)
    keys = keys or sorted(by_key)

    rows = []
    for key in keys:
        got, _exc = run_1m.market_inputs(key)
        if got is None:
            continue
        days, files, tick, _note = got
        bars = [b for d in days for b in d.bars]
        runs = {s: level_runs(files, s) for s in ("short", "long")}
        acts = [f.activation_ts for f in files]
        for i in by_key[key]:
            t = trades[i]
            ets = pd.Timestamp(t["entry_ts"])
            f = engine_1m._active_file(files, ets)
            file_i = acts.index(f.activation_ts) if f is not None else None
            lvl = t["entry_first"]
            r = run_of(runs[t["side"]], lvl, file_i) if file_i is not None \
                else None
            if r is None:
                # the level was not an eligible ladder member under the
                # file active at entry: only possible if the ladder moved
                # in the same minute, so treat the trade as its own run.
                run_id, a, b = -1, file_i, file_i
            else:
                run_id, a, b = r
            run_start = files[a].activation_ts
            day_start = next(d.bars[0][0] for d in days
                             if str(d.date) == t["entry_date"])
            rows.append(dict(
                i=i, market=key, side=t["side"], level=lvl,
                episode=f"{key}|{t['side']}|{lvl}|{a}",
                entry_ts=t["entry_ts"], exit_ts=t["exit_ts"],
                entry_date=t["entry_date"], reason=t["reason"],
                net_r=t["net_r"], stop=t["stop"],
                run_files=b - a + 1,
                run_start=str(run_start),
                tests_in_run=count_tests(bars, lvl, run_start, ets),
                tests_today=count_tests(bars, lvl, day_start, ets),
            ))
        print(f"{key}: {len(by_key[key])} trades measured", flush=True)

    rows.sort(key=lambda r: r["entry_ts"])
    episodes = annotate(rows)
    write_json(data, rows, episodes)
    build_page()
    return rows, episodes


def write_json(data, rows, episodes):
    OUT_JSON.write_text(json.dumps(dict(
        source=IN_JSON.name, params=data["params"],
        definitions=dict(
            same_levels="market + side + first reversal price, inside one "
                        "continuous level run (consecutive files carrying "
                        "it as an eligible ladder member)",
            test="a maximal run of minutes whose bar range contains the "
                 "level; price must leave and return to be tested again"),
        trades=rows, episodes=episodes), indent=1) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT_JSON.name}: {len(rows)} trades, "
          f"{len(episodes)} episodes")


# ---------------------------------------------------------------- the page

def price(v):
    """Levels print at FULL precision: 620.625 is not 620.63. The shared
    helper rounds above 100, which would blur the very identity this page
    groups on (ZW and ZC are eighths, ZN 64ths)."""
    return f"{v:,.4f}".rstrip("0").rstrip(".")


def bucket(v, edges, labels):
    for e, lab in zip(edges, labels):
        if v <= e:
            return lab
    return labels[-1]


CUTS = [
    ("Attempt on these levels", "attempt",
     lambda r: bucket(r["attempt"], [1, 2, 3], ["1st", "2nd", "3rd", "4th+"]),
     ["1st", "2nd", "3rd", "4th+"],
     "How many trades this level had already produced in this run. "
     "Lode's question in its most direct form."),
    ("Losses in a row before it, same levels", "prior_losses",
     lambda r: bucket(r["prior_losses"], [0, 1, 2],
                      ["none", "1", "2", "3 or more"]),
     ["none", "1", "2", "3 or more"],
     "Counted immediately before this trade, so a win resets it."),
    ("Times the level was tested before entry, this run", "tests_in_run",
     lambda r: bucket(r["tests_in_run"], [1, 3, 6, 12],
                      ["1", "2-3", "4-6", "7-12", "13+"]),
     ["1", "2-3", "4-6", "7-12", "13+"],
     "Every touch counts, including the ones that produced no trade. "
     "This is the wider form of the same idea: a level price keeps "
     "coming back to is a level that is not repelling price."),
    ("Which trade of the day it was, in that market", "nth_today",
     lambda r: bucket(r["nth_today"], [1, 2, 3],
                      ["1st", "2nd", "3rd", "4th+"]),
     ["1st", "2nd", "3rd", "4th+"],
     "Any level, not just the same one. This is the sharpest cut in the "
     "data and the one that matches what Lode saw, and note that on this "
     "sample EVERY same-session repeat was a re-attack of the same level, "
     "so the two questions collapse into one."),
    ("How busy that market-day turned out to be", "n_today",
     lambda r: bucket(r["n_today"], [1, 2, 3],
                      ["1 trade", "2 trades", "3 trades", "4 or more"]),
     ["1 trade", "2 trades", "3 trades", "4 or more"],
     "NOT A TRADEABLE RULE, and it is here as evidence rather than as a "
     "filter: it conditions on how the day ended, which nobody knows at "
     "the first entry. It is the same effect seen from the other side."),
    ("Times tested before entry, THIS session", "tests_today",
     lambda r: bucket(r["tests_today"], [1, 2, 3],
                      ["1", "2", "3", "4 or more"]),
     ["1", "2", "3", "4 or more"],
     "The same count restricted to the entry day, which is the window a "
     "trader actually watches."),
]


def cut_table(rows, cut):
    label, _k, fn, order, note = cut
    groups = defaultdict(list)
    for r in rows:
        groups[fn(r)].append(r)
    body = []
    for lab in order:
        g = groups.get(lab, [])
        if not g:
            continue
        wins = [x for x in g if x["net_r"] > 0]
        tot = sum(x["net_r"] for x in g)
        wr = 100 * len(wins) / len(g)
        body.append(
            f'<tr><td class="l">{lab}</td>'
            f'<td class="mono">{len(g)}</td>'
            f'<td class="mono">{len(wins)}</td>'
            f'<td class="mono">{wr:.0f}%</td>'
            f'<td class="mono {cls(tot)}">{signed(tot)}</td>'
            f'<td class="mono {cls(tot)}">{signed(tot / len(g))}</td></tr>')
    return (f'<div class="section-h">{label}</div>'
            f'<p class="chartnote">{note}</p>'
            f'<div class="tradecard"><table class="trades"><thead><tr>'
            f'<th class="l" style="width:28%">{label}</th>'
            f'<th style="width:14%">Trades</th><th style="width:14%">Wins</th>'
            f'<th style="width:14%">Win %</th><th style="width:15%">Net R</th>'
            f'<th style="width:15%">Avg R</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def episodes_table(episodes):
    body = []
    for e in episodes:
        if e["n"] < 2:
            continue
        seq = "".join(
            f'<b style="color:var(--{"pos" if ch == "W" else "neg"})">{ch}</b>'
            for ch in e["sequence"])
        body.append(
            f'<tr><td class="l">{esc(e["market"])}</td>'
            f'<td class="l">{e["side"]}</td>'
            f'<td class="mono">{price(e["level"])}</td>'
            f'<td class="mono">{e["n"]}</td>'
            f'<td class="l mono">{seq}</td>'
            f'<td class="mono {cls(e["net_r"])}">{signed(e["net_r"])}</td>'
            f'<td class="mono">{e["days"]}</td>'
            f'<td class="mono">{e["tests_first"]} to {e["tests_last"]}</td>'
            f'<td class="l mono">{e["first"][:16]}</td></tr>')
    return (f'<div class="tradecard"><div class="tradescroll">'
            f'<table class="trades"><thead><tr>'
            f'<th class="l" style="width:12%">Market</th>'
            f'<th class="l" style="width:7%">Side</th>'
            f'<th style="width:11%">Level</th><th style="width:8%">Trades</th>'
            f'<th class="l" style="width:12%">Sequence</th>'
            f'<th style="width:10%">Net R</th><th style="width:8%">Days</th>'
            f'<th style="width:14%">Tests</th>'
            f'<th class="l" style="width:18%">First entry</th>'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table></div></div>')


def trades_table(rows, links):
    body = []
    for r in rows:
        link = links.get(r["market"])
        name = esc(r["market"])
        cell = (f'<a href="{link[0]}&amp;t={link[1][r["i"]]}" '
                f'target="_blank">{name}</a>') if link else name
        body.append(
            f'<tr><td class="l" data-s="{name}">{cell}</td>'
            f'<td class="l" data-s="{r["side"]}">{r["side"]}</td>'
            f'<td class="l mono" data-s="{r["entry_ts"]}">'
            f'{stamp(r["entry_ts"])}</td>'
            f'<td class="mono" data-s="{r["level"]}">{price(r["level"])}</td>'
            f'<td class="mono" data-s="{r["attempt"]}">{r["attempt"]}'
            f' of {r["episode_n"]}</td>'
            f'<td class="mono" data-s="{r["prior_losses"]}">'
            f'{r["prior_losses"]}</td>'
            f'<td class="mono" data-s="{r["tests_in_run"]}">'
            f'{r["tests_in_run"]}</td>'
            f'<td class="mono" data-s="{r["tests_today"]}">'
            f'{r["tests_today"]}</td>'
            f'<td class="mono {cls(r["net_r"])}" data-s="{r["net_r"]}">'
            f'{signed(r["net_r"])}</td>'
            f'<td class="l" data-s="{r["reason"]}">{r["reason"]}</td></tr>')
    cols = [("Market", "l", 13), ("Side", "l", 6), ("Entry (UTC)", "l", 15),
            ("Level", "", 10), ("Attempt", "", 10), ("Prior losses", "", 10),
            ("Tests, run", "", 9), ("Tests, day", "", 9), ("R", "", 7),
            ("Exit", "l", 11)]
    head = "".join(
        f'<th class="{c} sortable" data-i="{i}" style="width:{w}%">{lab}'
        f'<span class="ar"></span></th>'
        for i, (lab, c, w) in enumerate(cols))
    return (f'<div class="tradecard"><div class="tradescroll">'
            f'<table class="trades" data-sort="2" data-dir="1">'
            f'<thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div></div>')


SORT_JS = r"""<script>
document.querySelectorAll('table.trades[data-sort]').forEach(function (tbl) {
  var body = tbl.tBodies[0];
  if (!body) return;
  var key = Number(tbl.dataset.sort), dir = Number(tbl.dataset.dir) || 1;
  function val(row, i) {
    var td = row.cells[i];
    var s = td ? (td.dataset.s !== undefined ? td.dataset.s : td.textContent) : '';
    var n = parseFloat(s);
    return (s !== '' && !isNaN(n) && /^[-+0-9.eE]+$/.test(s)) ? n : s;
  }
  function apply() {
    var rows = Array.prototype.slice.call(body.rows);
    rows.sort(function (a, b) {
      var x = val(a, key), y = val(b, key);
      return x === y ? 0 : (x > y ? 1 : -1) * dir;
    });
    rows.forEach(function (r) { body.appendChild(r); });
    tbl.querySelectorAll('th').forEach(function (th) {
      th.classList.remove('sorted');
      var ar = th.querySelector('.ar'); if (ar) ar.textContent = '';
    });
    var th = tbl.querySelector('th[data-i="' + key + '"]');
    if (th) { th.classList.add('sorted');
      var ar = th.querySelector('.ar');
      if (ar) ar.textContent = dir > 0 ? '▲' : '▼'; }
  }
  tbl.querySelectorAll('th.sortable').forEach(function (th) {
    th.addEventListener('click', function () {
      var i = Number(th.dataset.i);
      if (i === key) { dir = -dir; } else { key = i; dir = 1; }
      apply();
    });
  });
  apply();
});
</script>"""


def build_page():
    d = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    rows = d["trades"]
    episodes = annotate(rows)
    write_json(d, rows, episodes)
    wins = [r for r in rows if r["net_r"] > 0]
    losses = [r for r in rows if r["net_r"] <= 0]
    fresh = [r for r in rows if r["attempt"] == 1]
    repeat = [r for r in rows if r["attempt"] > 1]
    multi = [e for e in episodes if e["n"] > 1]
    worst = max(episodes, key=lambda e: -e["net_r"])

    def wr(g):
        return 100 * sum(1 for r in g if r["net_r"] > 0) / len(g) if g else 0

    def tot(g):
        return sum(r["net_r"] for r in g)

    links = {}
    for r in rows:
        links.setdefault(r["market"], [])
    for key in links:
        try:
            folder = run_1m.market_info(key)["array_dir"]
        except (KeyError, StopIteration):
            continue
        order = sorted([r for r in rows if r["market"] == key],
                       key=lambda r: r["entry_ts"])
        links[key] = (f"{STUDY_BASE}?m={folder}",
                      {r["i"]: n + 1 for n, r in enumerate(order)})
    links = {k: v for k, v in links.items() if isinstance(v, tuple)}

    win_prior = defaultdict(int)
    for r in wins:
        win_prior[min(r["prior_losses"], 3)] += 1

    kpis = "".join(
        f'<div class="kpi"><div class="k">{k}</div><div class="v{t}">{v}</div>'
        f'<div class="sub">{s}</div></div>'
        for k, v, s, t in [
            ("Trades", f"{len(rows)}",
             f"{len(episodes)} level episodes", ""),
            ("First attempts", f"{len(fresh)}",
             f"{wr(fresh):.0f}% win rate, {signed(tot(fresh))}R",
             " pos" if tot(fresh) > 0 else " neg"),
            ("Repeat attempts", f"{len(repeat)}",
             f"{wr(repeat):.0f}% win rate, {signed(tot(repeat))}R",
             " pos" if tot(repeat) > 0 else " neg"),
            ("Winners with a loss before them", f"{len(wins) - win_prior[0]}",
             f"of {len(wins)} winners, on the same levels", ""),
            ("Episodes of 2 or more", f"{len(multi)}",
             f"{sum(e['n'] for e in multi)} trades, "
             f"{signed(sum(e['net_r'] for e in multi))}R",
             " pos" if sum(e["net_r"] for e in multi) > 0 else " neg"),
            ("Worst episode", f"{signed(worst['net_r'])}R",
             f"{worst['market']} {worst['side']} {price(worst['level'])}, "
             f"{worst['sequence']}", " neg"),
        ])

    lede = (
        f"Every trade of the published baseline, grouped by the levels it "
        f"fired on. {len(rows)} trades fall into {len(episodes)} episodes, "
        f"{len(multi)} of which produced more than one trade. The question "
        f"is whether a level that has already been traded, or merely tested, "
        f"is worth trading again.")
    findings = (
        f"<b>First attempts win {wr(fresh):.0f}% and make "
        f"{signed(tot(fresh))}R across {len(fresh)} trades. Repeat attempts "
        f"win {wr(repeat):.0f}% and make {signed(tot(repeat))}R across "
        f"{len(repeat)} trades.</b> Of the {len(wins)} winners, "
        f"{win_prior[0]} were the first trade on their levels and "
        f"{len(wins) - win_prior[0]} came after at least one loss there. "
        f"The worst single episode is {worst['market']} "
        f"{worst['side']} at {price(worst['level'])}: {worst['sequence']}, "
        f"{signed(worst['net_r'])}R.")

    cuts = "".join(cut_table(rows, c) for c in CUTS)
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>quickfix1m1dc &mdash; the same levels, traded again</title>
{CSS}
<style>table.trades td a{{color:var(--accent);text-decoration:none;
font-weight:600}}table.trades td a:hover{{text-decoration:underline}}</style>
</head><body><div class="wrap">
<header>
  <div class="eyebrow">1-minute workstream &middot; research</div>
  <h1>The same levels, traded again</h1>
  <p class="lede">{lede}</p>
</header>
<div class="note">{findings}</div>
<div class="kpis">{kpis}</div>
<div class="section-h">What counts as the same</div>
<p class="chartnote"><b>The same levels</b> means the same market, the same
side and the same <b>first reversal price</b>, inside one continuous
<b>level run</b>: the consecutive array files that carry that level as an
eligible ladder member. A level that is elected and reappears later starts a
fresh episode, because the market has been somewhere else in between.
<b>A test</b> is a maximal run of minutes whose bar range contains the level,
so a level price sits on for six minutes was tested once, and price has to
leave and come back to test it again. Tests are counted whether or not they
produced a trade, which is what makes them the wider measure.</p>
{cuts}
<div class="section-h">Every episode that traded more than once</div>
<p class="chartnote">In entry order, W for a winner and L for a loser. This
is where the wheat session lives.</p>
{episodes_table(episodes)}
<div class="section-h">Every trade</div>
<p class="chartnote">Attempt is this trade's position in its episode. Prior
losses counts backwards from it and resets on a win. The market name links
into the 1-minute study at that trade.</p>
{trades_table(rows, links)}
<footer>Research only, nothing here changes the strategy. Built by
research_1m_levels.py from output/{IN_JSON.name} at the published baseline.
All times UTC.</footer>
</div>{SORT_JS}</body></html>"""
    OUT_HTML.write_text(page, encoding="utf-8")
    print(f"page: {len(rows)} trades, {len(episodes)} episodes -> "
          f"{OUT_HTML.name} ({len(page) / 1024:.0f} KB)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--page":
        build_page()
    else:
        main(args or None)
