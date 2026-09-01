"""Entry-minute liquidity: measured, not assumed (Lode, 2026-09-02).

The question: "do we have any idea how many contracts were trading at
our entries or do we just assume there's always liquidity minus the
slippage?" Until this script the honest answer was ASSUME: the fill
model books the reversal price plus a fixed tick slippage and never
looks at volume. This measures what actually printed.

For every live-universe trade in the published blotter, the ON-BOOK
volume of the exact ENTRY MINUTE is read from the contract's own bars
(data_center expand_process.load_bars -- the same bars the engine
traded), beside the day's median minute volume for context, and
compared with the position sizes the deployment replays take at $250k
and $2M. Participation = our contracts / contracts printed in that
minute.

WHAT THIS PROVES AND WHAT IT DOES NOT: printed volume is trades that
HAPPENED, not the depth that was resting -- a market order can fill
more than the minute's print by eating the book, and it can also move
the price doing it. Low participation against printed volume is good
evidence the fixed slippage is enough; participation near or above
100% of the minute's print says the fill model is optimistic there
and the market's real capacity needs the order book (IB later), not
bars. Taxes stay out of everything; this is liquidity, not cost.

No purchases, reads bars already on disk (~10-20s). Writes
output/quickfix1m1dc_liquidity.txt.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from statistics import median

import pandas as pd

import research_1m_sizing as sizing
import run_1m
from build_1m_report import replay_contracts

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
DC = HERE / ".." / "data_center"
sys.path.insert(0, str((DC / "scripts").resolve()))
import expand_process  # noqa: E402  (data_center's sanctioned reader)

ACCOUNTS = [250_000.0, 2_000_000.0]


def bars_path(key, contract):
    info = run_1m.market_info(key)
    folder = DC / "data" / f"{info['array_dir']}_{key}" / "bars"
    p = folder / f"{contract}.parquet"
    if p.exists():
        return p
    # IFUS raw symbols carry double spaces; the files are named after
    # the raw symbol verbatim, so fall back to a tolerant match.
    want = "".join(contract.split()).lower()
    for cand in folder.glob("*.parquet"):
        if "".join(cand.stem.split()).lower() == want:
            return cand
    return None


def main():
    trades = sizing.live_trades(
        json.loads((OUT / "quickfix1m1dc_all.json")
                   .read_text(encoding="utf-8"))["trades"])
    n_at = {}
    for acct in ACCOUNTS:
        money_of, _, _, _, _ = replay_contracts(trades, 1.0, acct)
        n_at[acct] = {i: m["n"] for i, m in money_of.items()}

    cache, rows, missing = {}, [], []
    for i, t in enumerate(trades):
        p = bars_path(t["market"], t["contract"])
        if p is None:
            missing.append(f"{t['market']} {t['contract']}")
            continue
        if p not in cache:
            cache[p] = expand_process.load_bars(p)
        bars = cache[p]
        ts = pd.Timestamp(t["entry_ts"]).floor("min")
        try:
            vol = int(bars.loc[ts, "volume"])
        except KeyError:
            missing.append(f"{t['market']} {t['entry_ts']} (no bar)")
            continue
        day = bars[bars.index.date == ts.date()]["volume"]
        rows.append(dict(
            i=i, market=t["market"], entry_ts=t["entry_ts"],
            vol=vol, day_median=float(day.median()),
            n250=n_at[ACCOUNTS[0]].get(i), n2m=n_at[ACCOUNTS[1]].get(i)))

    lines = [
        "quickfix1m1dc -- entry-minute liquidity, measured"
        f" (research_1m_liquidity.py, {datetime.now():%Y-%m-%d %H:%M})",
        "on-book volume of the exact entry minute, from the contract's"
        " own bars (expand_process.load_bars -- what the engine traded);"
        " participation = our contracts / contracts printed that minute.",
        "Printed volume is a floor on activity, not the resting depth:"
        " low participation supports the fixed-slippage fill model, high"
        " participation flags it as optimistic there.",
        "",
        f"{'mkt':<5} {'n':>3} {'entry-min vol':>16} {'day med/min':>11}"
        f" {'ctr@250k':>9} {'part@250k':>9} {'ctr@2M':>7} {'part@2M':>8}",
    ]
    worst = []
    for key in sorted({r["market"] for r in rows}):
        rs = [r for r in rows if r["market"] == key]
        vols = sorted(r["vol"] for r in rs)
        med_v = vols[len(vols) // 2]

        def part(r, n):
            return (n / r["vol"] * 100.0) if (n and r["vol"]) else None

        p250 = [part(r, r["n250"]) for r in rs if r["n250"]]
        p2m = [part(r, r["n2m"]) for r in rs if r["n2m"]]
        for r in rs:
            for acct, n in (("250k", r["n250"]), ("2M", r["n2m"])):
                pc = part(r, n)
                if pc is not None and pc >= 20.0:
                    worst.append(
                        f"  {r['market']} {r['entry_ts'][:16]}: {n}"
                        f" contracts into a {r['vol']}-lot minute"
                        f" ({pc:.0f}% at ${acct})")
        lines.append(
            f"{key:<5} {len(rs):>3}"
            f" {min(vols):>6,}/{med_v:,}/{max(vols):,}"
            f" {median(r['day_median'] for r in rs):>11,.0f}"
            f" {max((r['n250'] or 0) for r in rs):>9,}"
            f" {f'{max(p250):.1f}%' if p250 else '-':>9}"
            f" {max((r['n2m'] or 0) for r in rs):>7,}"
            f" {f'{max(p2m):.1f}%' if p2m else '-':>8}")
    lines += [
        "",
        "entry-min vol column is min/median/max across that market's"
        " entries; ctr and part columns are the WORST (largest) case.",
        "",
        "== flagged entries (>= 20% of the minute's print):",
    ]
    lines += worst or ["  none"]
    if missing:
        lines += ["", "== no bar found for:"] + [f"  {m}" for m in missing]
    text = "\n".join(lines) + "\n"
    out = OUT / "quickfix1m1dc_liquidity.txt"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
