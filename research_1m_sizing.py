"""The quantized-sizing reading: integer contracts against the 1% ideal.

Futures trade in whole contracts, so exactly-1%-of-equity risk does not
exist at the order ticket. This script replays the existing blotters
with INTEGER position sizes and measures what quantization costs -- a
pure post-processing pass over trades already on disk (no engine runs,
seconds), against the idealized fractional replay those pages publish.

Sizing (Lode 2026-08-21, refusal policy revised 2026-09-01):
  n = floor(equity * risk_pct / (rpu * point_value)); at n = 0 the
  order is REFUSED at placement -- "We're not going to force a trade
  above that 1%" -- and the same setup is released the moment grown
  capital affords one contract, in the backtest exactly as in real
  time. (The original force-1 policy is superseded; refusals make the
  quantized trade list a SUBSET of the blotter, so this layer is no
  longer capital-independent -- that is the point.) The idealized 1%
  layer remains the research currency; this layer is a deployability
  measurement on top, never a replacement. Margin is out of scope.
  EXECUTION COSTS ARE IN THE CURVE since 2026-09-01 (Lode): each side
  of each taken position pays commission + exchange + NFA per contract
  from execution_costs.py (documented and sourced there; taxes
  excluded by decision). Slippage stays in R where the engine put it;
  costs are dollars here -- the fill and the bill never overlap.

Account size: default $150,000 (Lode, 2026-09-01) -- the deployment
scenario: most markets afford one contract, and the PA/PL/SI-class
trades sit refused until equity grows to release them. `--account
2000000` reproduces the everything-fits reading.

KNOWN APPROXIMATION, stated rather than hidden: a refusal here is
post-processing, so it removes the trade but cannot re-run the session
lockout -- in the live engine a refused ORDER spends nothing and a
later setup that session could still enter. Same class of shift the
geometry band needed its own engine runs for; acceptable while
refusals are rare, and a money-aware engine pass is the exact fix if
they stop being rare.

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

import execution_costs
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


def contract_size(equity, risk_pct, per_unit):
    """(contracts, refused): floor sizing, REFUSE at n=0 (Lode,
    2026-09-01: "We're not going to force a trade above that 1%" --
    the order is refused at placement when one contract risks more
    than the budget, and the trade is released the moment grown
    capital affords it, in the backtest exactly as in real time).
    Supersedes the 2026-08-21 force-1 policy. THE one sizing rule --
    build_1m_report's contracts pages import it from here, so the
    pages and this reading cannot disagree about what a budget
    affords."""
    n = math.floor(equity * risk_pct / 100.0 / per_unit)
    return (n, n == 0)


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
    open_risk, rows, costs_paid = {}, [], 0.0
    for ts, kind, t in events:
        tid = id(t)
        if kind == "entry":
            spec = specs[t["market"]]
            is_etf = spec["type"] == "etf"
            per_unit = t["rpu"] * usd_point_value(spec)
            n, refused = contract_size(equity, risk_pct, per_unit)
            row = dict(market=t["market"], type=spec["type"], n=n,
                       refused=refused, per_unit=per_unit,
                       entry_date=t["entry_date"],
                       risk=n * per_unit,
                       risk_pct=n * per_unit / equity * 100.0)
            if is_etf and n:
                row["locked"] = n * t["entry"]
                row["locked_pct"] = row["locked"] / equity * 100.0
            rows.append(row)
            if not refused:
                # Execution costs, per side (execution_costs.py --
                # documented and sourced; taxes excluded by decision).
                # The entry side is paid the moment the order fills.
                side = execution_costs.cost_per_side(
                    t["market"], n, is_etf=is_etf, eurusd=EURUSD)
                row["cost_rt"] = 2.0 * side
                equity -= side
                costs_paid += side
                open_risk[tid] = (row["risk"], side)
        else:
            got = open_risk.pop(tid, None)
            if got is None:
                continue  # the entry was refused; nothing to book
            risk, side = got
            equity += t["net_r"] * risk - side
            costs_paid += side
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
    return dict(final=equity, max_dd=max_dd, costs=costs_paid), rows


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

    taken = [r for r in rows if not r["refused"]]
    fut = [r for r in taken if r["type"] == "future"]
    etf = [r for r in taken if r["type"] == "etf"]
    refused = [r for r in rows if r["refused"]]
    risks = [r["risk_pct"] for r in taken]

    w = lines.append
    w("")
    w(f"== {name}  ({len(trades)} trades in the blotter)")
    w(f"   idealized {risk_pct:g}% fractional : final"
      f" ${ideal_final:,.0f}  max DD {ideal_dd:.2f}%  (all"
      f" {len(trades)} trades)")
    w(f"   quantized, refuse-at-n=0   : final ${q['final']:,.0f}"
      f"  max DD {q['max_dd']:.2f}%  ({len(taken)} taken,"
      f" {len(refused)} refused)")
    w(f"   quantization+refusals+costs: final"
      f" {q['final'] / ideal_final * 100 - 100:+.2f}%  DD"
      f" {q['max_dd'] - ideal_dd:+.2f} points against the ideal")
    rts = [r["cost_rt"] for r in taken if "cost_rt" in r]
    w(f"   execution costs paid       : ${q['costs']:,.2f} total,"
      f" median ${median(rts):,.2f} per round turn"
      f" (execution_costs.py: IBKR commission + exchange + NFA,"
      f" sourced; taxes excluded)" if rts else
      "   execution costs paid       : none")
    if refused:
        w(f"   refused at order placement : "
          + ", ".join(f"{r['market']} {r['entry_date']}"
                      f" (1 contract = ${r['per_unit']:,.0f})"
                      for r in refused))
        w("   release rule: the same setup is taken the moment grown"
          " capital affords one contract inside the budget -- no trade"
          " is ever forced above it.")
    if risks:
        w(f"   realized risk per trade    : min {min(risks):.3f}%"
          f"  p25 {pct(risks, .25):.3f}%  median {median(risks):.3f}%"
          f"  p75 {pct(risks, .75):.3f}%  max {max(risks):.3f}%"
          f"  (budget {risk_pct:g}%)")
    w(f"   at x1000 account the delta to the ideal is"
      f" {conv * 100:.4f} pct points -- quantization and refusals"
      f" vanish there, so this residual IS the execution-cost drag"
      f" (the frictionless ideal pays none by design)")

    w("   per market (futures):")
    w(f"     {'mkt':<5} {'taken':>6} {'contracts min/med/max':>22}"
      f" {'median $/contract':>18} {'refused':>7}")
    ref_by = {}
    for r in refused:
        ref_by[r["market"]] = ref_by.get(r["market"], 0) + 1
    for m in sorted({r["market"] for r in fut} | set(ref_by)):
        rs = [r for r in fut if r["market"] == m]
        ns = [r["n"] for r in rs]
        band = (f"{min(ns):>8}/{int(median(ns))}/{max(ns):<8}"
                if ns else f"{'-':>8}/{'-'}/{'-':<8}")
        per = ([r["per_unit"] for r in rs]
               or [r["per_unit"] for r in refused if r["market"] == m])
        w(f"     {m:<5} {len(rs):>6} {band}"
          f" {median(per):>17,.0f}"
          f" {ref_by.get(m, 0):>7}")
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
    ap.add_argument("--account", type=float, default=150_000.0)
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
        f" integer contracts, REFUSED at n=0 (no forcing; released as"
        f" capital grows)",
        f"specs: data_center/metadata/contract_specs.json"
        f" (built {built}); execution costs from execution_costs.py"
        f" (sourced 2026-09-01, taxes excluded); margin out of scope",
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
