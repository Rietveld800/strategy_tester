"""The STOP PROFILE: a one-time report on why quickfix1m1dc carries a stop.

Lode, 2026-09-03, after the contracts pages gained their no-stop account:
"I thought we did a study around stoplosses and why we use it." There was
no single study. The stop's case was made in five dated measurements,
none of which ran the strategy without a stop until the no-stop companion
of 2026-09-03 (audit s.21). This page puts the five beside the engine's
own no-stop run so the record reads as one argument.

ONE-TIME BY DESIGN: not a refresh step. The five points are dated prose
(records, not live claims); the measurement table is recomputed from the
JSONs on disk at build time (the matrix's `nostop` block, the published
blotter, the exit-profile JSON, the micro gates) through the SAME replay
code path the contracts pages use, and the page stamps the data window it
was built on. Rebuild by hand when the question is asked again:

    venv\\Scripts\\python.exe build_1m_stop_profile.py

Output: output/quickfix1m1dc_stop_profile.html
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd

import build_1m_report as rep
import research_1m_sizing as sizing
import run_1m_matrix
from build_equity_html import CSS

HERE = Path(__file__).resolve().parent
OUT = HERE / "output" / "quickfix1m1dc_stop_profile.html"
PROFILE_JSON = HERE / "output" / "quickfix1m1dc_exit_profile.json"

CELLS = ["variant 1", "variant 4"]
LABEL = {"variant 1": "variant 1 (published baseline, 4th/5th stop)",
         "variant 4": "variant 4 (hybrid stop)"}


def esc(s):
    return rep.esc(s)


def money(v):
    return rep.money(v)


def stats(trades):
    wins = [t for t in trades if t["net_r"] > 0]
    losses = [t for t in trades if t["net_r"] <= 0]
    net = sum(t["net_r"] for t in trades)
    return dict(
        n=len(trades), wins=len(wins),
        wr=100.0 * len(wins) / len(trades) if trades else 0.0,
        net_r=net,
        avg_w=(sum(t["net_r"] for t in wins) / len(wins)) if wins else 0.0,
        avg_l=(sum(t["net_r"] for t in losses) / len(losses)) if losses else 0.0,
        worst=min((t["net_r"] for t in trades), default=0.0),
        best=max((t["net_r"] for t in trades), default=0.0),
        stops=sum(1 for t in trades if t["reason"] == "stop"),
        below2=sum(1 for t in trades if t["net_r"] < -2.0),
        below3=sum(1 for t in trades if t["net_r"] < -3.0),
        below1=sum(1 for t in trades if -2.0 <= t["net_r"] < -1.0),
        streak=rep.streaks(trades)[1])


def contracts_replay(trades):
    """The contracts pages' own money layer on this trade list: $250k,
    the micro stack, execution costs, refusal at placement."""
    live = sizing.live_trades(trades)
    route, gates = rep.micro_route()
    specs, _ = sizing.load_specs()
    money_of, eod, final, max_dd, refused = rep.replay_micro(
        live, rep.RISK_PCT, rep.SIZING_ACCOUNT, route, specs,
        gates["per_entry"])
    taken = [t for i, t in enumerate(live) if i not in refused]
    return dict(final=final, max_dd=max_dd, taken=len(taken),
                refused=len(refused), live=len(live), trades=taken)


def keys(trades):
    return {(t["market"], t["entry_ts"]) for t in trades}


def profile_reading():
    """The 2026-08-28 pre-registration's two paths at the settlement exit,
    from the exit-profile JSON on disk (its own build stamp is quoted)."""
    if not PROFILE_JSON.exists():
        return None
    d = json.loads(PROFILE_JSON.read_text(encoding="utf-8"))
    out = dict(built=d.get("built"), cells={})
    for name, x in d["samples"].items():
        R = x["all"]["R"]
        sig = R["unconstrained"].get("close1") or R["unconstrained"].get("settle1")
        trd = R["truncated"].get("close1") or R["truncated"].get("settle1")
        stopped = [t for t in x["trades"] if t["reason"] == "stop"]
        inside = sum(1 for t in stopped
                     if t["horizons"].get("settle0", {}).get("stopped"))
        out["cells"][name] = dict(n=x["n"], anchor=x["anchor"], sig=sig,
                                  trd=trd, stops=len(stopped),
                                  inside=inside)
    return out


def kpi(label, value, sub="", tone=""):
    return rep.kpi(label, value, sub, tone)


def cls(v):
    return rep.cls(v)


def fmt_r(v):
    return f"{v:+.2f}R"


def build():
    m = json.loads(rep.MATRIX_JSON.read_text(encoding="utf-8"))
    blotter = json.loads(rep.IN_JSON.read_text(encoding="utf-8"))
    if "nostop" not in m:
        raise SystemExit("the matrix JSON carries no no-stop companions; "
                         "run run_1m_matrix.py first")
    calendar = m.get("calendar") or blotter.get("calendar")
    window = (calendar[0], calendar[-1]) if calendar else ("?", "?")

    rows_engine, rows_contracts, shifts, anatomy = [], [], [], []
    for cell in CELLS:
        v = m["variants"][cell]
        stopped = sorted(m["trades"][cell], key=lambda t: t["entry_ts"])
        ns_block = m["nostop"][cell]
        nostop = sorted(ns_block["trades"], key=lambda t: t["entry_ts"])
        s_st, s_ns = stats(stopped), stats(nostop)
        rows_engine.append((cell, "with the stop", s_st, v["max_dd_pct"],
                            v["final_cash"]))
        rows_engine.append((cell, "no stop", s_ns, ns_block["max_dd_pct"],
                            ns_block["final_cash"]))
        c_st, c_ns = contracts_replay(stopped), contracts_replay(nostop)
        rows_contracts.append((cell, "with the stop", c_st))
        rows_contracts.append((cell, "no stop", c_ns))
        ks, kn = keys(stopped), keys(nostop)
        ls, ln = keys(sizing.live_trades(stopped)), keys(sizing.live_trades(nostop))
        shifts.append((cell, len(ks - kn), len(kn - ks), len(ks & kn),
                       len(ls - ln), len(ln - ls)))
        anatomy.append((cell, s_st, s_ns))

    prof = profile_reading()

    def engine_rows():
        out = []
        for cell, which, s, dd, final in rows_engine:
            tone = "" if which == "with the stop" else " style=\"background:var(--accent-soft)\""
            out.append(
                f'<tr{tone}><td class="l">{esc(LABEL[cell])}</td>'
                f'<td class="l"><b>{which}</b></td>'
                f'<td class="mono">{s["n"]}</td>'
                f'<td class="mono">{s["wr"]:.1f}%</td>'
                f'<td class="mono {cls(s["net_r"])}">{s["net_r"]:+.2f}</td>'
                f'<td class="mono pos">{s["avg_w"]:+.2f}</td>'
                f'<td class="mono neg">{s["avg_l"]:+.2f}</td>'
                f'<td class="mono neg">{s["worst"]:+.2f}</td>'
                f'<td class="mono">{s["streak"]}</td>'
                f'<td class="mono {"neg" if dd > 10 else ""}">{dd:.2f}%</td>'
                f'<td class="mono">{money(final)}</td></tr>')
        return "".join(out)

    def contracts_rows():
        out = []
        for cell, which, c in rows_contracts:
            tone = "" if which == "with the stop" else " style=\"background:var(--accent-soft)\""
            out.append(
                f'<tr{tone}><td class="l">{esc(LABEL[cell])}</td>'
                f'<td class="l"><b>{which}</b></td>'
                f'<td class="mono">{c["taken"]}</td>'
                f'<td class="mono">{c["refused"]}</td>'
                f'<td class="mono {cls(c["final"] - rep.SIZING_ACCOUNT)}">'
                f'{money(c["final"])}</td>'
                f'<td class="mono">{100 * (c["final"] / rep.SIZING_ACCOUNT - 1):+.2f}%</td>'
                f'<td class="mono {"neg" if c["max_dd"] > 10 else ""}">'
                f'{c["max_dd"]:.2f}%</td></tr>')
        return "".join(out)

    def shift_rows():
        return "".join(
            f'<tr><td class="l">{esc(LABEL[cell])}</td>'
            f'<td class="mono">{shared}</td><td class="mono">{blocked}</td>'
            f'<td class="mono">{freed}</td>'
            f'<td class="mono">{lb} / {lf}</td></tr>'
            for cell, blocked, freed, shared, lb, lf in shifts)

    def anatomy_rows():
        out = []
        for cell, s_st, s_ns in anatomy:
            out.append(
                f'<tr><td class="l">{esc(LABEL[cell])}</td>'
                f'<td class="mono">{s_st["stops"]} of {s_st["n"]}</td>'
                f'<td class="mono">{s_st["below1"]} / {s_st["below2"] - s_st["below3"]} / {s_st["below3"]}</td>'
                f'<td class="mono">{s_ns["below1"]} / {s_ns["below2"] - s_ns["below3"]} / {s_ns["below3"]}</td>'
                f'<td class="mono neg">{s_st["worst"]:+.2f}R</td>'
                f'<td class="mono neg">{s_ns["worst"]:+.2f}R</td></tr>')
        return "".join(out)

    def profile_rows():
        if not prof:
            return ('<tr><td class="l" colspan="8">no exit-profile JSON on '
                    'disk (research_1m_exit_profile.py)</td></tr>')
        out = []
        for name, c in prof["cells"].items():
            sig, trd = c["sig"], c["trd"]
            out.append(
                f'<tr><td class="l">{esc(name)}, {esc(c["anchor"])}</td>'
                f'<td class="mono">{c["n"]}</td>'
                f'<td class="mono">{sig["mean"]:+.2f} / {sig["sd"]:.2f} / '
                f'<b>{sig["sharpe"]:.3f}</b></td>'
                f'<td class="mono">{trd["mean"]:+.2f} / {trd["sd"]:.2f} / '
                f'<b>{trd["sharpe"]:.3f}</b></td>'
                f'<td class="mono">{c["inside"]} of {c["stops"]} '
                f'({100 * c["inside"] / c["stops"]:.0f}%)</td></tr>')
        return "".join(out)

    v1 = next(r for r in rows_engine if r[0] == "variant 1" and r[1] == "with the stop")
    v1n = next(r for r in rows_engine if r[0] == "variant 1" and r[1] == "no stop")
    c1 = next(r for r in rows_contracts if r[0] == "variant 1" and r[1] == "with the stop")[2]
    c1n = next(r for r in rows_contracts if r[0] == "variant 1" and r[1] == "no stop")[2]
    blocked1, freed1 = shifts[0][1], shifts[0][2]
    lb1, lf1 = shifts[0][4], shifts[0][5]

    kpis = "".join([
        kpi("Win rate, no stop", f"{v1n[2]['wr']:.1f}%",
            f"against {v1[2]['wr']:.1f}% with the stop (variant 1, engine at 1%)",
            "pos"),
        kpi("Net R, no stop", f"{v1n[2]['net_r']:+.2f}",
            f"against {v1[2]['net_r']:+.2f} with the stop", "neg"),
        kpi("Max drawdown, no stop", f"{v1n[3]:.2f}%",
            f"against {v1[3]:.2f}% with the stop", "neg"),
        kpi("Worst trade, no stop", fmt_r(v1n[2]["worst"]),
            f"against {fmt_r(v1[2]['worst'])} with the stop", "neg"),
        kpi("At $250k, contracts", money(c1n["final"]),
            f"no stop, {c1n['max_dd']:.2f}% DD; with the stop "
            f"{money(c1['final'])} at {c1['max_dd']:.2f}%",
            cls(c1n["final"] - c1["final"])),
        kpi("The list shifts", f"{blocked1} / {freed1}",
            "entries blocked by a still-open position / entries only the "
            f"no-stop run took (engine universe; {lb1} / {lf1} on the "
            "contracts pages' live universe)"),
    ])

    prof_built = esc(prof["built"]) if prof else "n/a"
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>quickfix1m1dc &mdash; stop profile</title>
{CSS}
<style>
.chartnote{{max-width:none}}
.kpis{{display:flex;flex-wrap:wrap}}.kpis .kpi{{flex:1 1 150px}}
.point{{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:16px 20px;margin:12px 0}}
.point .d{{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--accent);
  font-weight:600}}
.point .t{{font-weight:650;font-size:15px;margin:4px 0 8px}}
.point p{{margin:6px 0;color:var(--ink2);font-size:13.5px;line-height:1.5}}
.point .src{{font-size:12px;color:var(--ink3)}}
.point a{{color:var(--accent);text-decoration:none}}
.point a:hover{{text-decoration:underline}}
table.trades td.l b{{font-weight:650}}
</style></head><body>
<div class="wrap">
<header>
  <div class="eyebrow">1-minute workstream &middot; one-time report</div>
  <h1>Why quickfix1m1dc carries a stop</h1>
  <p class="lede">Lode, 2026-09-03: <i>"I thought we did a study around
  stoplosses and why we use it."</i> There was no single study. The stop's
  case was made in <b>five dated measurements</b>, none of which ran the
  strategy without a stop until the no-stop companion of 2026-09-03. This
  page puts the five beside the engine's own no-stop run so the record reads
  as one argument. The figures in the tables are recomputed from the JSONs on
  disk (data window <b>{esc(window[0])}</b> to <b>{esc(window[1])}</b>, built
  {date.today().isoformat()}); the five points are records, dated as written.
  Not in the refresh chain: rebuild by hand with
  <b>build_1m_stop_profile.py</b>.</p>
</header>

<div class="kpis">{kpis}</div>

<div class="section-h">The measurement, 2026-09-03: the same entries with and without a stop order</div>
<p class="chartnote">The engine's own pass with <b>stop_live</b> off (audit
s.21): the stop PRICE still sizes the position, denominates 1R and feeds the
geometry band, so every entry decision is identical; no stop order rests and
every position is carried to the settlement of the day after entry. Both
report cells, on the human-filter universe at the engine's 1% fractional
risk and $100k base. Highlighted rows are the no-stop runs.</p>
<div class="tradecard"><table class="trades"><thead><tr>
<th class="l" style="width:22%">Cell</th><th class="l" style="width:10%">Stop</th>
<th style="width:7%">Trades</th><th style="width:7%">Win %</th>
<th style="width:7%">Net R</th><th style="width:7%">Avg win</th>
<th style="width:7%">Avg loss</th><th style="width:7%">Worst</th>
<th style="width:9%">Losing run</th><th style="width:8%">Max DD</th>
<th style="width:9%">Final @1%</th></tr></thead>
<tbody>{engine_rows()}</tbody></table></div>

<p class="chartnote">The same two lists at the deployment account: <b>$250,000</b>,
the live 22-futures universe, integer contracts with the routed micro stack,
execution costs in the curve, an order refused at placement when even one
micro busts the 1% budget &mdash; the contracts pages' own replay
(<b>replay_micro</b>, one code path).</p>
<div class="tradecard"><table class="trades"><thead><tr>
<th class="l" style="width:30%">Cell</th><th class="l" style="width:14%">Stop</th>
<th style="width:10%">Taken</th><th style="width:10%">Refused</th>
<th style="width:12%">Final</th><th style="width:12%">Return</th>
<th style="width:12%">Max DD</th></tr></thead>
<tbody>{contracts_rows()}</tbody></table></div>

<p class="chartnote"><b>The trade list shifts, it is not re-priced.</b> Counted on the
engine's human-filter universe; the last column counts the same on the
contracts pages' live universe, which is the figure those pages print. A position
that is no longer stopped is still open the next session, so an entry the
stopped run took there is blocked by one position per market; and a market
the stopped run still held can be free for an entry only the no-stop run
takes. This is why the no-stop result is an engine pass and not the stopped
blotter with different exits &mdash; the same argument the geometry band
needed its own runs for (s.15).</p>
<div class="tradecard"><table class="trades"><thead><tr>
<th class="l" style="width:34%">Cell</th><th style="width:15%">Shared entries</th>
<th style="width:17%">Blocked without the stop</th>
<th style="width:17%">Only without the stop</th>
<th style="width:17%">Live universe: blocked / only</th></tr></thead>
<tbody>{shift_rows()}</tbody></table></div>

<p class="chartnote"><b>Where the money goes.</b> With the stop a loser is
capped near -1R (slippage takes it a little past). Without it the same
losers run to the settlement: the columns count net-R losses in the bands
-1R to -2R / -2R to -3R / below -3R.</p>
<div class="tradecard"><table class="trades"><thead><tr>
<th class="l" style="width:30%">Cell</th><th style="width:12%">Stops taken</th>
<th style="width:18%">Losses &lt;-1R, with stop</th>
<th style="width:18%">Losses &lt;-1R, no stop</th>
<th style="width:11%">Worst, stop</th><th style="width:11%">Worst, no stop</th>
</tr></thead><tbody>{anatomy_rows()}</tbody></table></div>

<div class="note"><b>Reading.</b> Dropping the stop lifts the win rate by
roughly twenty points &mdash; the spikes that took a stop and then reversed
are winners now &mdash; and still loses net R, because the losers that were
capped near -1R run to -2R, -3R and beyond, and the drawdown roughly
quadruples. The stop buys about a quarter of the drawdown for about a third
of the win rate. Levered to equal drawdown, the project's ranking rule, the
gap would be wider still. This is shape, not verdict: ~100 trades, eight
months, and a drawdown figure that is the most sample-dependent statistic in
the project. The contracts pages carry both accounts on every refresh so the
question stays measured rather than argued.</div>

<div class="section-h">The five measurements behind the stop, in order</div>
<p class="chartnote">Dated as they were written. Each is a record of the
sample of its day; the shape of every argument has held, the numbers move
with every refresh.</p>

<div class="point"><div class="d">1 &middot; 2026-08-03 &middot; the GC pilot stop sweep</div>
<div class="t">The stop's shape came from here, not its existence</div>
<p>v1's stop was a multiple of the entry-to-running-session-extreme distance,
swept 1.0 to 3.0 in 0.1 steps on gold alone, each point a real backtest. The
tight end paid most (+15.6% at x1.0 against +10.6% at x1.5 and +6.7% at
x3.0, at 1% risk), and the two-phase tightening at the entry-day settlement
improved every setting from x1.3 up by capping day-2 losses at the day
extreme. Eight to ten trades, one market: read the band, not the peak.</p>
<p class="src">Source: <a href="../../data_center/docs/backtest_1m_design.md">data_center/docs/backtest_1m_design.md</a>, "The change is the STOP - two phases".</p></div>

<div class="point"><div class="d">2 &middot; 2026-08-05 / 06 &middot; the trade-by-trade review</div>
<div class="t">Structure-anchored invalidation, and the cascade rule</div>
<p>Reading GC, BTC and ZW trades on the 1m study moved the stop from the
extreme multiple to the <b>ladder anchor</b>, one tick beyond the 5th
reversal (the 4th when only four exist). GC1 died at 07:12 in level-zone
chop under the 1.5x stop and is a winner under the ladder stop; GC7 shows the
ladder stop is TIGHTER than 1.5x and still holds, so this was never a
"wider stops" proposal; GC4 was killed by the tightening, an anti-overnight
feature, on a trade the structural stop would have saved; GC6 loses under
every stop, kept as the honest counterweight. Lode's instinct on BTC2, one
tick beyond the ladder-test high, is exactly the tight end the pilot sweep
favoured. And the rule that governs everything after it: any stop change
changes the TRADE LIST (GC2, GC5, ZW8 exist only because their predecessors
stopped out), so stops compare as equity curves at equal risk, never per
trade.</p>
<p class="src">Source: <a href="../docs/quickfix1m1dc_audit.md">docs/quickfix1m1dc_audit.md</a>, s.1.2 (findings) and s.5 (decisions: "STOP: always one tick beyond the 5th reversal").</p></div>

<div class="point"><div class="d">3 &middot; 2026-08-06 &middot; the stop-anchor grid</div>
<div class="t">"Moving the stop at all is the wrong lever" &mdash; removing it was never on the grid</div>
<p>The matrix ran {{confirm, hold}} x {{ladder, hybrid, extreme}}. The
extreme (wick) stop was far worse (26-31% win rate, 24-29% drawdown); the
hybrid, one tick beyond whichever of the ladder anchor and the session
extreme at entry is further, did exactly what it was predicted to do &mdash;
fewer trades, the best win rate in the grid (39.9% against 36.6%) and the
shortest losing streak (6) &mdash; and still booked about 9.7R less,
because a wider stop is a bigger R denominator and the same move books fewer
R. The ladder anchor earned its place in both directions. The same section
measured the gap risk the confirmation clause had been for: 6 of 80 stop
exits opened through their stop, 0.52R in total, so gap protection was never
the stop's job either.</p>
<p class="src">Source: <a href="../docs/quickfix1m1dc_audit.md">docs/quickfix1m1dc_audit.md</a>, s.10. The hybrid is still a live dial (variant 4) and has its own R-cut grid (s.15f).</p></div>

<div class="point"><div class="d">4 &middot; 2026-08-09 &middot; the path analysis</div>
<div class="t">Every mechanical protection loses money; the closest thing to a stop study before today</div>
<p>Every trade's minute-by-minute path recomputed from the on-book bars
(MAE, MFE, time to each). <b>Exit-before-stop is a negative result:</b>
aborting at -X R for any X in 0.3-0.8 killed more winners than it saved
(best case about -15R), because the survivors chop deep first &mdash; 33 of
72 settlement winners went at least 0.5R adverse before winning and netted
+65R together; even the trades within a hair of the stop were net positive.
A breakeven stop once +Y R up was negative in every cell of Y 0.5-1.5, because
20 winners revisit the entry after being +1R up and then win. A third of the
stop class (19 of 65) had been up at least +1R before dying. Lode's verdict
that day: the win rate has to come from ENTRY SELECTION, and the compact-R
setups (six of seven stopped after being up 1.4R) are not to be filtered
either &mdash; they are high-payoff, execution-critical setups, not bad
ones.</p>
<p class="src">Source: <a href="../docs/quickfix1m1dc_audit.md">docs/quickfix1m1dc_audit.md</a>, s.14 (and s.8 for the stop class's anatomy: 63 stops at -1.19R average as "the whole win-rate problem").</p></div>

<div class="point"><div class="d">5 &middot; 2026-08-28 &middot; the exit-timing pre-registration</div>
<div class="t">"A held trade is variance the stop happens to cap" &mdash; the prediction today's run confirms</div>
<p>Every trade's path was profiled both ways, pre-registered before any
number was looked at: the <b>signal path (no stop)</b>, the market after the
trigger as if no stop existed, and the <b>trade path (stop as booked)</b>,
frozen at the trade's own stop. At the settlement exit the two have about
the same mean on the published cell (the hybrid's no-stop mean is lower)
and the no-stop path about twice the spread, so the per-trade Sharpe is
markedly lower without the stop on both; the stop preserves most of the Sharpe
through day 3 while adding no drift after the first session. Prediction P3
(losers are decided early: the stop prints inside the entry session in the
majority of cases) held. The table reads the exit-profile JSON on disk
(built {prof_built}); mean / sd / Sharpe in R at the close of session 1.</p>
<div class="tradecard"><table class="trades"><thead><tr>
<th class="l" style="width:32%">Sample</th><th style="width:8%">n</th>
<th style="width:22%">Signal path (no stop)</th>
<th style="width:22%">Trade path (stop as booked)</th>
<th style="width:16%">Stops inside the entry session</th></tr></thead>
<tbody>{profile_rows()}</tbody></table></div>
<p class="src">Source: <a href="../docs/exit_timing_preregistration.md">docs/exit_timing_preregistration.md</a>, s.12-13; <a href="quickfix1m1dc_exit_profile.html">quickfix1m1dc_exit_profile.html</a> (research_1m_exit_profile.py).</p></div>

<div class="section-h">What today's run adds, and what it does not decide</div>
<p class="chartnote">The pre-registration estimated the no-stop path per
trade, on the stopped list. The engine run of 2026-09-03 is the first time
the strategy actually ran without a stop, and it adds what a per-trade path
cannot see: the shifted trade list (blocked and freed entries above), the
portfolio drawdown at a shared account, and the integer-contract rendering
with costs. It agrees with the estimate in direction &mdash; same mean per
trade, twice the variance &mdash; and puts a number on the drawdown. It does
not decide anything: the stop stays because every measurement since
2026-08-03 says the same thing from a different side, and the contracts
pages now carry both accounts on every refresh so that stays measured.</p>

<footer>quickfix1m1dc stop profile, one-time report built {date.today().isoformat()}
from output/quickfix1m1dc_matrix.json (nostop block), output/quickfix1m1dc_all.json,
output/quickfix1m1dc_exit_profile.json and the micro gates. Decisions and history:
docs/quickfix1m1dc_audit.md s.21. All times UTC.</footer>
</div></body></html>"""
    OUT.write_text(html, encoding="utf-8")
    print(f"stop profile -> {OUT.name} ({len(html) / 1024:.0f} KB); "
          f"variant 1 no stop {v1n[2]['n']} trades {v1n[2]['wr']:.1f}% "
          f"{v1n[2]['net_r']:+.2f}R DD {v1n[3]:.2f}% vs stopped "
          f"{v1[2]['n']} {v1[2]['wr']:.1f}% {v1[2]['net_r']:+.2f}R DD "
          f"{v1[3]:.2f}%; $250k {money(c1n['final'])} / "
          f"{c1n['max_dd']:.2f}% vs {money(c1['final'])} / {c1['max_dd']:.2f}%")


if __name__ == "__main__":
    build()
