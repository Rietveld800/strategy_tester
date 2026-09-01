"""The quantized-sizing reading: integer contracts against the 1% ideal.

Futures trade in whole contracts, so exactly-1%-of-equity risk does not
exist at the order ticket. This script replays the existing blotters
with INTEGER position sizes and measures what quantization costs -- a
pure post-processing pass over trades already on disk (no engine runs,
seconds), against the idealized fractional replay those pages publish.

Sizing (decisions, Lode 2026-08-21):
  n = floor(equity * risk_pct / (rpu * point_value)), and a trade whose
  budget affords no contract takes ONE anyway (force-1), tagged, so the
  trade list stays capital-independent. The idealized 1% layer remains
  the research currency; this layer is a deployability measurement on
  top, never a replacement. Margin and commissions are out of scope.

Account size: default $2,000,000 (Lode, 2026-09-01) -- chosen so every
market in the universe affords at least one contract inside the 1%
threshold, which turns the test into a measurement of quantization
noise rather than a fight with granularity.

Contract specs come from data_center/metadata/contract_specs.json (the
validated table built by its build_contract_specs.py) -- one source, so
this script and anything downstream cannot disagree about a point
value. ETFs are sized in whole shares; they pay FULL notional (no
margin leverage), so each ETF trade also reports the capital it locks
per 1% risked -- locked/equity = risk_pct * price / rpu, independent of
account size, which is the number the futures-only-portfolio decision
wants.

Replays the published baseline (variant 2's blotter,
quickfix1m1dc_all.json) and variant 5 from the matrix JSON. The event
ordering mirrors run_1m.portfolio_replay exactly (exits before entries
at one timestamp), so with the account grown without bound the
quantized curve converges on the idealized one -- checked and printed.

Output: output/quickfix1m1dc_sizing.txt (and stdout).
"""

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import median

import pandas as pd

import run_1m

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
SPECS = HERE / ".." / "data_center" / "metadata" / "contract_specs.json"

# Research-grade EUR->USD for a EUR-denominated market (FGBL). Not in
# either published universe today; the constant only exists so a
# whole-universe replay cannot silently size FGBL in the wrong currency.
EURUSD = 1.16


def load_specs():
    payload = json.loads(SPECS.read_text(encoding="utf-8"))
    return payload["markets"], payload["built"]


def usd_point_value(spec):
    pv = spec["point_value"]
    return pv * EURUSD if spec.get("currency") == "EUR" else pv


def quantized_replay(trades, specs, start_capital, risk_pct):
    """portfolio_replay's loop with integer contracts. Returns the
    summary dict and the per-trade sizing rows."""
    events = []
    for t in trades:
        events.append((pd.Timestamp(t["entry_ts"]), "entry", t))
        events.append((pd.Timestamp(t["exit_ts"]), "exit", t))
    events.sort(key=lambda e: (e[0], 0 if e[1] == "exit" else 1))
    equity = start_capital
    peak, max_dd = equity, 0.0
    open_risk, rows = {}, []
    for ts, kind, t in events:
        tid = id(t)
        if kind == "entry":
            spec = specs[t["market"]]
            per_unit = t["rpu"] * usd_point_value(spec)
            budget = equity * risk_pct / 100.0
            n = math.floor(budget / per_unit)
            forced = n == 0
            if forced:
                n = 1
            risk = n * per_unit
            row = dict(market=t["market"], type=spec["type"], n=n,
                       forced=forced, per_unit=per_unit, risk=risk,
                       risk_pct=risk / equity * 100.0)
            if spec["type"] == "etf":
                row["locked"] = n * t["entry"]
                row["locked_pct"] = row["locked"] / equity * 100.0
            rows.append(row)
            open_risk[tid] = risk
        else:
            risk = open_risk.pop(tid)
            equity += t["net_r"] * risk
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
    return dict(final=equity, max_dd=max_dd), rows


def pct(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))]


def report_config(name, trades, specs, account, risk_pct, lines):
    ideal_final, ideal_dd, _ = run_1m.portfolio_replay(
        trades, start_capital=account, risk_pct=risk_pct)
    q, rows = quantized_replay(trades, specs, account, risk_pct)
    big, _ = quantized_replay(trades, specs, account * 1000, risk_pct)
    big_ideal, _, _ = run_1m.portfolio_replay(
        trades, start_capital=account * 1000, risk_pct=risk_pct)
    conv = abs(big["final"] / (account * 1000)
               - big_ideal / (account * 1000))

    fut = [r for r in rows if r["type"] == "future"]
    etf = [r for r in rows if r["type"] == "etf"]
    forced = [r for r in rows if r["forced"]]
    risks = [r["risk_pct"] for r in rows]

    w = lines.append
    w("")
    w(f"== {name}  ({len(trades)} trades)")
    w(f"   idealized {risk_pct:g}% fractional : final"
      f" ${ideal_final:,.0f}  max DD {ideal_dd:.2f}%")
    w(f"   quantized integer sizing   : final ${q['final']:,.0f}"
      f"  max DD {q['max_dd']:.2f}%")
    w(f"   quantization cost          : final"
      f" {q['final'] / ideal_final * 100 - 100:+.2f}%  DD"
      f" {q['max_dd'] - ideal_dd:+.2f} points")
    w(f"   forced trades (n_intended=0): {len(forced)}"
      + (f"  ({', '.join(sorted({r['market'] for r in forced}))})"
         if forced else ""))
    w(f"   realized risk per trade    : min {min(risks):.3f}%"
      f"  p25 {pct(risks, .25):.3f}%  median {median(risks):.3f}%"
      f"  p75 {pct(risks, .75):.3f}%  max {max(risks):.3f}%"
      f"  (budget {risk_pct:g}%)")
    w(f"   convergence check at x1000 account: quantized-vs-ideal"
      f" return delta {conv * 100:.4f} pct points")

    w("   per market (futures):")
    w(f"     {'mkt':<5} {'trades':>6} {'contracts min/med/max':>22}"
      f" {'median $/contract':>18} {'forced':>6}")
    for m in sorted({r["market"] for r in fut}):
        rs = [r for r in fut if r["market"] == m]
        ns = [r["n"] for r in rs]
        w(f"     {m:<5} {len(rs):>6} "
          f"{min(ns):>8}/{int(median(ns))}/{max(ns):<8}"
          f" {median(r['per_unit'] for r in rs):>17,.0f}"
          f" {sum(r['forced'] for r in rs):>6}")
    if etf:
        w("   ETFs (whole shares, FULL notional paid -- no leverage):")
        w(f"     {'mkt':<5} {'trades':>6} {'median shares':>13}"
          f" {'locked %equity med/max':>22}  over 100% = not fillable"
          f" without margin")
        for m in sorted({r["market"] for r in etf}):
            rs = [r for r in etf if r["market"] == m]
            w(f"     {m:<5} {len(rs):>6}"
              f" {int(median(r['n'] for r in rs)):>13,}"
              f" {median(r['locked_pct'] for r in rs):>10.1f}%"
              f" /{max(r['locked_pct'] for r in rs):>6.1f}%")
        over = [r for r in etf if r["locked_pct"] > 100.0]
        w(f"     locking more than the whole account: {len(over)} of"
          f" {len(etf)} ETF trades (ratio is account-size independent:"
          f" locked/equity = risk% x price/rpu)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", type=float, default=2_000_000.0)
    ap.add_argument("--risk", type=float, default=1.0)
    args = ap.parse_args()

    specs, built = load_specs()
    baseline = json.loads(
        (OUT / "quickfix1m1dc_all.json").read_text(encoding="utf-8"))
    matrix = json.loads(
        (OUT / "quickfix1m1dc_matrix.json").read_text(encoding="utf-8"))

    lines = [
        "quickfix1m1dc -- quantized contract sizing"
        f" (research_1m_sizing.py, {datetime.now():%Y-%m-%d %H:%M})",
        f"account ${args.account:,.0f}, risk {args.risk:g}% per trade,"
        f" integer contracts, force-1 at n=0",
        f"specs: data_center/metadata/contract_specs.json"
        f" (built {built}); margin and commissions out of scope",
    ]
    report_config("published baseline (variant 2, 4th/5th stop,"
                  " band 000-060)",
                  baseline["trades"], specs, args.account, args.risk,
                  lines)
    report_config("variant 5 (hybrid stop, band 020-060)",
                  matrix["trades"]["variant 5"], specs, args.account,
                  args.risk, lines)

    text = "\n".join(lines) + "\n"
    out = OUT / "quickfix1m1dc_sizing.txt"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
