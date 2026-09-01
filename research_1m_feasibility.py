"""The $100k feasibility reading of the live-universe candidate.

THE UNIVERSE UNDER STUDY (Lode, 2026-09-01): 22 markets -- the 19 GLBX
futures of the currently-updated Socrates set, plus FGBL (KEPT despite
being EUR-denominated; the currency is an accepted complication, not an
exclusion) and the two IFUS markets (SB, DX). JGB stays OUT (the data
gap). The ETFs (URA, VIXY) are outside this scoping, consistent with
the futures-only lean. STANDARDISATION is a point of attention: a
universe where some markets trade full-size and others trade micros is
two operational regimes, and every MICRO verdict below is a deviation
from uniformity that the micro study has to weigh.

THE QUESTION: how many of the 22 can be traded at a $100,000 account
without one contract busting the 1%-of-equity risk threshold?

Three evidence layers, weakest last:
- REAL stop distances where the strategy has traded: per-contract risk
  = rpu x point_value over the blotter's own trades (variant 2, the
  published anchor, and variant 5, the hybrid stop -- wider stops, so
  bigger dollar risk; both shown). The share of trades where ONE
  full-size contract fits the budget is the honest feasibility number,
  because rpu varies trade by trade -- a market can be infeasible at
  its median and still fit a third of its setups.
- The MEASURED micro catalog (data_center metadata/micro_catalog.json)
  as the gap-filler: the smallest listed smaller contract scales the
  same dollar risk by its size fraction. Fractions marked unverified
  (MZW/MZC presumed 1/10, MJY presumed 1/10 with its quote direction
  unknown) stay flagged until definitions are bought.
- A RANGE-BASED estimate for markets with no trades in the window:
  the geometry band accepts a level-to-stop distance of 0.2-0.6 of the
  trailing day's range, so 0.4 x median daily range x point_value
  stands in for a typical setup's per-contract risk (0.2 and 0.6
  bracket it). An estimate, clearly labelled, never pooled with the
  real numbers.

Specs come from data_center's validated contract_specs.json (one
source); FGBL converts at research_1m_sizing.EURUSD. No engine passes,
no purchases, seconds. Writes output/quickfix1m1dc_feasibility.txt.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from statistics import median

import pandas as pd
import pyarrow.parquet as pq

import research_1m_sizing as sizing
import run_1m

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
DC = HERE / ".." / "data_center"
CATALOG = DC / "metadata" / "micro_catalog.json"

# The live-universe candidate (Lode, 2026-09-01). Order: GLBX, then the
# kept non-CME markets.
LIVE22 = ["GC", "BTC", "SR3", "ZW", "ZC", "YM", "6E", "6J", "LE", "HG",
          "CL", "NG", "PA", "PL", "NQ", "ES", "SI", "ZN", "ZB",
          "FGBL", "SB", "DX"]

# The smallest LISTED smaller contract per market. ALL VERIFIED since
# 2026-09-01 from purchased GLBX definitions (data_center
# micro_buy_definitions.py, derived micro-vs-parent unit quantities in
# the same unit and currency -- MJY included: 1,250,000 JPY, a true
# 1/10 of 6J in the same quote direction). The treasuries' 10Y/30Y are
# deliberately absent: yield-quoted cash-settled contracts, NOT a
# smaller ZN/ZB (confirmed NOT COMPARABLE by the same validation).
# Silver's floor is SIL at 1/5 -- QI, the other listed root, is 1/2.
MICRO_BEST = {
    "GC": ("MGC", 0.10, True),   # 1OZ (1/100) exists too; MGC suffices
    "SI": ("SIL", 0.20, True),
    "HG": ("MHG", 0.10, True),
    "CL": ("MCL", 0.10, True),
    "NG": ("MNG", 0.10, True),   # verified 1,000 MMBtu -- smaller than QG
    "ES": ("MES", 0.10, True),
    "NQ": ("MNQ", 0.10, True),
    "YM": ("MYM", 0.10, True),
    "6E": ("M6E", 0.10, True),
    "BTC": ("MBT", 0.02, True),
    "ZW": ("MZW", 0.10, True),   # verified 500 bu
    "ZC": ("MZC", 0.10, True),   # verified 500 bu
    "6J": ("MJY", 0.10, True),   # verified 1.25M JPY, same direction
}

RANGE_DAYS = 90
BAND_TYPICAL, BAND_LO, BAND_HI = 0.4, 0.2, 0.6


def per_contract_risks(trades, specs):
    """market -> sorted per-contract dollar risks, one per trade."""
    out = {}
    for t in trades:
        spec = specs.get(t["market"])
        if spec is None:
            continue
        out.setdefault(t["market"], []).append(
            t["rpu"] * sizing.usd_point_value(spec))
    return {k: sorted(v) for k, v in out.items()}


def median_daily_range(key):
    """Median high-low of the front row over the last RANGE_DAYS
    sessions, in quote units. Front approximated per date by the
    max-volume non-spread row with a real close -- uniform across
    markets, which is what a yardstick wants."""
    info = run_1m.market_info(key)
    daily = DC / "data" / f"{info['array_dir']}_{key}" / "daily" / \
        "ohlcv-1d.parquet"
    if not daily.exists():
        return None
    df = pq.read_table(daily, columns=["ts_event", "symbol", "high",
                                       "low", "close", "volume"]
                       ).to_pandas().reset_index()
    df = df[(df["close"] > 0) & ~df["symbol"].str.contains("-")]
    front = (df.sort_values("volume").groupby("ts_event").tail(1)
             .sort_values("ts_event").tail(RANGE_DAYS))
    if front.empty:
        return None
    return float(((front["high"] - front["low"]) * 1e-9).median())


def share_fit(risks, budget):
    return 100.0 * sum(1 for r in risks if r <= budget) / len(risks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", type=float, default=100_000.0)
    ap.add_argument("--risk", type=float, default=1.0)
    args = ap.parse_args()
    budget = args.account * args.risk / 100.0

    specs, built = sizing.load_specs()
    v2 = json.loads((OUT / "quickfix1m1dc_all.json")
                    .read_text(encoding="utf-8"))["trades"]
    v5 = json.loads((OUT / "quickfix1m1dc_matrix.json")
                    .read_text(encoding="utf-8"))["trades"]["variant 5"]
    r2, r5 = per_contract_risks(v2, specs), per_contract_risks(v5, specs)

    lines = [
        "quickfix1m1dc -- $100k live-universe feasibility"
        f" (research_1m_feasibility.py, {datetime.now():%Y-%m-%d %H:%M})",
        f"account ${args.account:,.0f}, risk threshold {args.risk:g}% ="
        f" ${budget:,.0f} per trade; specs built {built}",
        "universe: the 22-market live candidate (19 GLBX + FGBL kept"
        " despite EUR + SB, DX; JGB out; ETFs out of scope)",
        "",
        "Per-contract dollar risk of ONE full-size contract at the"
        " strategy's own stops (v2 = published 4th/5th anchor, v5 ="
        " hybrid, wider). 'fit%' = share of that market's trades where"
        " one contract stays inside the budget. est@0.4 = 0.4 x median"
        f" {RANGE_DAYS}-day range x point value, the yardstick for"
        " markets with no trades in the window (brackets 0.2-0.6).",
        "",
        f"{'mkt':<5} {'v2 n':>4} {'v2 med':>8} {'v2 fit%':>7}"
        f" {'v5 n':>4} {'v5 med':>8} {'v5 fit%':>7}"
        f" {'est@0.4':>8} {'micro':>6} {'x':>5}"
        f" {'micro med':>9}  verdict",
    ]

    verdicts = {}
    for key in LIVE22:
        spec = specs[key]
        est = None
        rng = median_daily_range(key)
        if rng is not None:
            est = BAND_TYPICAL * rng * sizing.usd_point_value(spec)
        a, b = r2.get(key, []), r5.get(key, [])
        med2 = median(a) if a else None
        med5 = median(b) if b else None
        # The evidence for the verdict: real stops when they exist (the
        # WIDER anchor decides, erring safe), the estimate otherwise.
        basis = max(x for x in (med2, med5) if x is not None) \
            if (a or b) else est
        micro = MICRO_BEST.get(key)
        micro_med = basis * micro[1] if (micro and basis) else None
        if basis is None:
            verdict = "NO DATA"
        elif basis <= budget:
            verdict = "FULL"
        elif micro_med is not None and micro_med <= budget:
            verdict = ("MICRO" if micro[2]
                       else "MICRO (fraction unverified)")
        elif a or b:
            pooled = sorted(a + b)
            fit_full = share_fit(pooled, budget)
            fit_micro = (share_fit([r * micro[1] for r in pooled], budget)
                         if micro else 0.0)
            if fit_full > 0:
                verdict = f"PARTIAL ({fit_full:.0f}% of trades fit)"
            elif fit_micro > 0:
                verdict = (f"PARTIAL with {micro[0]}"
                           f" ({fit_micro:.0f}% of trades fit)")
            else:
                verdict = "GAP"
        else:
            verdict = "GAP (estimated)"
        verdicts[key] = verdict
        lines.append(
            f"{key:<5} {len(a):>4} "
            f"{f'{med2:,.0f}' if med2 else '-':>8} "
            f"{f'{share_fit(a, budget):.0f}' if a else '-':>7} "
            f"{len(b):>4} "
            f"{f'{med5:,.0f}' if med5 else '-':>8} "
            f"{f'{share_fit(b, budget):.0f}' if b else '-':>7} "
            f"{f'{est:,.0f}' if est else '-':>8} "
            f"{micro[0] if micro else '-':>6} "
            f"{f'1/{round(1 / micro[1])}' if micro else '-':>5} "
            f"{f'{micro_med:,.0f}' if micro_med else '-':>9}"
            f"  {verdict}")

    full = [k for k, v in verdicts.items() if v == "FULL"]
    micro_v = [k for k, v in verdicts.items() if v.startswith("MICRO")]
    micro_unv = [k for k, v in verdicts.items() if "unverified" in v]
    partial = [k for k, v in verdicts.items() if v.startswith("PARTIAL")]
    gap = [k for k, v in verdicts.items() if v.startswith("GAP")]
    lines += [
        "",
        f"== the answer at ${args.account:,.0f} / {args.risk:g}%:",
        f"   FULL SIZE          : {len(full):>2} of 22 "
        f"({', '.join(full)})",
        f"   + MICRO fills      : {len(micro_v):>2} more "
        f"({', '.join(micro_v)})"
        + (f" -- of which {', '.join(micro_unv)} carry an UNVERIFIED"
           f" size fraction" if micro_unv else ""),
        f"   PARTIAL only       : {len(partial):>2} "
        f"({', '.join(partial) or '-'}) -- tradable only on the setups"
        f" whose own stop fits, a per-trade skip rule",
        f"   GAP                : {len(gap):>2} "
        f"({', '.join(gap) or '-'})",
        "",
        "== the PA/PL question (asked explicitly): the catalog PROBED"
        " MPA and MPL on GLBX and neither exists, so no CME micro can"
        " fill this gap. What could: (a) a per-trade skip rule -- take"
        " the trade only when one contract fits the budget -- which the"
        " PARTIAL percentages above price out; (b) TOCOM/OSE lists"
        " smaller platinum group contracts, but that venue is outside"
        " our data (same boat as JGB) and JPY-denominated; (c) the"
        " PPLT/PALL ETFs, which the futures-only lean excludes. None"
        " is standard, which is the point of attention.",
        "",
        "== standardisation: every MICRO verdict is a second"
        " operational regime (different root, own specs, own liquidity"
        " to verify -- listing is proven, liquidity is NOT). The"
        " uniform alternatives are: raise capital until FULL covers"
        " the universe (the $2M reading), or shrink the universe to"
        " the FULL list.",
        "",
        "Estimates are yardsticks: 0.4 x median daily range stands in"
        " for a typical setup's stop; the band brackets 0.2-0.6, so a"
        " market near the line can swing verdicts. Real stops decide"
        " wherever trades exist, and the WIDER anchor (hybrid) is the"
        " one the verdict reads, erring safe.",
    ]

    text = "\n".join(lines) + "\n"
    out = OUT / "quickfix1m1dc_feasibility.txt"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
