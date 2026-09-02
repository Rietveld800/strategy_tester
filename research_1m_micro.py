"""Micro fidelity and liquidity: the gates for micro routing.

Before a single micro contract carries real money, two things are
MEASURED per market on the bars just bought (data_center
data/_micros/, 2026-09-02, $22.11):

- FIDELITY: at every parent entry minute (v2 and v5 blotters, live
  universe), does the matching micro contract print, and how far is
  its close from the parent's close, in PARENT ticks? The reversal
  levels live in the parent's price space; a micro that does not track
  that space at our minutes cannot take our stops.
- LIQUIDITY: the micro's own volume in those minutes, against the
  largest top-up stack the ladder would ever add (about 1/fraction - 1
  contracts per full contract of headroom).

Only micro roots with SOURCED execution costs are candidates (an
unpriceable leg cannot be replayed honestly): MJY, MZW, MZC, MNG and
1OZ wait for IB fee lines, so 6J has no candidate yet and ZW/ZC route
to the XW/XC minis, NG to QG.

GATES (documented, deliberately strict -- a failed gate means FULL
CONTRACTS ONLY for that market, never a worse fill assumption):
  fidelity: coverage >= 90% of entry minutes have a micro bar,
            median |micro - parent| <= 1 parent tick,
            p90 <= 2 parent ticks;
  liquidity: median entry-minute micro volume >= 2x the largest
            top-up stack (2 / fraction).

The micro contract is matched by symbol construction (micro root +
the parent contract's own month/year suffix -- MGCJ6 beside GCJ6),
which pins the SAME expiry month: same underlying, same month, so
arbitrage is what keeps the prints together, and this study checks it
did. Writes output/quickfix1m1dc_micro_gates.json (consumed by the
micro capital ladders) and quickfix1m1dc_micro_gates.txt.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from statistics import median

import pandas as pd

import execution_costs
import research_1m_sizing as sizing
import run_1m

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
DC = HERE / ".." / "data_center"
sys.path.insert(0, str((DC / "scripts").resolve()))
import expand_process  # noqa: E402

MICRO_BARS = DC / "data" / "_micros" / "bars" / "ohlcv-1m.parquet"
GATES_JSON = OUT / "quickfix1m1dc_micro_gates.json"

# Sourced-cost candidates per parent, smallest fraction first. The
# fractions and ticks come from the verified catalog at run time; this
# names only WHICH roots may route.
CANDIDATES = {
    "GC": ["MGC"], "SI": ["SIL"], "HG": ["MHG"], "CL": ["MCL", "QM"],
    "NG": ["QG"], "ES": ["MES"], "NQ": ["MNQ"], "YM": ["MYM"],
    "6E": ["M6E"], "BTC": ["MBT"], "ZW": ["XW"], "ZC": ["XC"],
}

COVERAGE_MIN = 0.90
MEDIAN_TICKS_MAX = 1.0
P90_TICKS_MAX = 2.0
LIQ_MULT = 2.0


def catalog_verified():
    cat = json.loads((DC / "metadata" / "micro_catalog.json")
                     .read_text(encoding="utf-8"))
    return {p["root"]: p["verified"] for p in cat["products"]
            if (p.get("verified") or {}).get("status") == "VERIFIED"}


def parent_bars_path(key, contract):
    info = run_1m.market_info(key)
    folder = DC / "data" / f"{info['array_dir']}_{key}" / "bars"
    p = folder / f"{contract}.parquet"
    return p if p.exists() else None


def micro_symbol(root, parent_contract, parent_key, known):
    """The micro expiry matching the parent's: root + the parent's own
    month/year suffix, year normalised to what the micro series uses."""
    suffix = parent_contract[len(parent_key):]
    m = re.match(r"([FGHJKMNQUVXZ])(\d{1,2})$", suffix)
    if not m:
        return None
    month, year = m.groups()
    for y in (year[-1], year):
        cand = f"{root}{month}{y}"
        if cand in known:
            return cand
    return None


def main():
    v2 = json.loads((OUT / "quickfix1m1dc_all.json")
                    .read_text(encoding="utf-8"))["trades"]
    v5 = json.loads((OUT / "quickfix1m1dc_matrix.json")
                    .read_text(encoding="utf-8"))["trades"]["variant 5"]
    # One measurement set per (market, contract, entry minute): the two
    # blotters overlap heavily and a duplicate minute is not evidence.
    seen, entries = set(), []
    for t in sizing.live_trades(v2) + sizing.live_trades(v5):
        k = (t["market"], t["contract"], t["entry_ts"])
        if k not in seen:
            seen.add(k)
            entries.append(t)

    verified = catalog_verified()
    micro = pd.read_parquet(MICRO_BARS,
                            columns=["open", "close", "volume", "symbol"])
    micro = micro.reset_index()
    tscol = "ts_event" if "ts_event" in micro.columns else micro.columns[0]
    micro = micro.set_index([micro["symbol"], micro[tscol]])
    known_syms = set(micro["symbol"].unique())

    parent_cache = {}
    results, lines = {}, [
        "quickfix1m1dc -- micro fidelity and liquidity gates"
        f" (research_1m_micro.py, {datetime.now():%Y-%m-%d %H:%M})",
        "fidelity in PARENT ticks at parent entry minutes (v2+v5, live"
        " universe, deduplicated); liquidity = the micro's own volume"
        " in those minutes.",
        f"gates: coverage >= {COVERAGE_MIN:.0%}, median diff <="
        f" {MEDIAN_TICKS_MAX:g} tick, p90 <= {P90_TICKS_MAX:g} ticks,"
        f" median volume >= {LIQ_MULT:g}x the largest top-up stack.",
        "",
        f"{'mkt':<4} {'root':<4} {'frac':>5} {'n':>3} {'cover':>6}"
        f" {'med dT':>7} {'p90 dT':>7} {'med vol':>8} {'need':>5}"
        f"  verdict",
    ]
    for key, roots in CANDIDATES.items():
        trades = [t for t in entries if t["market"] == key]
        if not trades:
            continue
        spec_tick = json.loads(
            (DC / "metadata" / "contract_specs.json")
            .read_text(encoding="utf-8"))["markets"][key]["tick"]
        for root in roots:
            v = verified[root]
            frac = v["fraction"]
            diffs, vols, matched = [], [], 0
            for t in trades:
                sym = micro_symbol(root, t["contract"], key, known_syms)
                if sym is None:
                    continue
                ts = pd.Timestamp(t["entry_ts"]).floor("min")
                try:
                    row = micro.loc[(sym, ts)]
                except KeyError:
                    continue
                pth = parent_bars_path(key, t["contract"])
                if pth is None:
                    continue
                if pth not in parent_cache:
                    parent_cache[pth] = expand_process.load_bars(pth)
                try:
                    pclose = float(parent_cache[pth].loc[ts, "close"]) * 1e-9
                except KeyError:
                    continue
                mclose = float(row["close"]) * 1e-9
                matched += 1
                diffs.append(abs(mclose - pclose) / spec_tick)
                vols.append(int(row["volume"]))
            n = len(trades)
            coverage = matched / n if n else 0.0
            need = LIQ_MULT / frac
            if matched:
                med_d = median(diffs)
                p90_d = sorted(diffs)[max(0, int(0.9 * len(diffs)) - 1)]
                med_v = median(vols)
                passed = (coverage >= COVERAGE_MIN
                          and med_d <= MEDIAN_TICKS_MAX
                          and p90_d <= P90_TICKS_MAX
                          and med_v >= need)
                why = [] if passed else [
                    w for c, w in [
                        (coverage < COVERAGE_MIN, "coverage"),
                        (med_d > MEDIAN_TICKS_MAX, "median diff"),
                        (p90_d > P90_TICKS_MAX, "p90 diff"),
                        (med_v < need, "liquidity")] if c]
            else:
                med_d = p90_d = med_v = None
                passed, why = False, ["no matched bars"]
            results.setdefault(key, []).append(dict(
                root=root, fraction=frac, tick=v["tick"],
                point_value=v.get("point_value"),
                n_entries=n, coverage=round(coverage, 3),
                median_diff_ticks=(round(med_d, 3)
                                   if med_d is not None else None),
                p90_diff_ticks=(round(p90_d, 3)
                                if p90_d is not None else None),
                median_minute_volume=med_v, needed_volume=need,
                passed=passed, why_failed=why))
            lines.append(
                f"{key:<4} {root:<4} {frac:>5g} {n:>3} {coverage:>6.0%}"
                f" {med_d if med_d is not None else float('nan'):>7.2f}"
                f" {p90_d if p90_d is not None else float('nan'):>7.2f}"
                f" {med_v if med_v is not None else 0:>8,.0f}"
                f" {need:>5.0f}"
                f"  {'PASS' if passed else 'FAIL: ' + ', '.join(why)}")
    routed = {k: next((r for r in rs if r["passed"]), None)
              for k, rs in results.items()}
    lines += ["", "== routing (first passing candidate per market):"]
    for k in sorted(results):
        r = routed[k]
        lines.append(f"  {k:<4} -> " + (f"{r['root']} (1/{round(1 / r['fraction'])})"
                                        if r else "FULL CONTRACTS ONLY"))
    lines += ["", "no sourced candidate (full only): 6J, LE, PA, PL, SI"
              " has SIL" , "unsourced fee rows (excluded until IB):"
              " MJY, MZW, MZC, MNG, 1OZ"]
    payload = dict(
        built=datetime.now().strftime("%Y-%m-%d %H:%M"),
        gates=dict(coverage_min=COVERAGE_MIN,
                   median_ticks_max=MEDIAN_TICKS_MAX,
                   p90_ticks_max=P90_TICKS_MAX, liq_mult=LIQ_MULT),
        candidates=results,
        routing={k: (r["root"] if r else None)
                 for k, r in routed.items()},
    )
    GATES_JSON.write_text(json.dumps(payload, indent=1) + "\n",
                          encoding="utf-8")
    text = "\n".join(lines) + "\n"
    (OUT / "quickfix1m1dc_micro_gates.txt").write_text(text,
                                                      encoding="utf-8")
    print(text)
    print(f"wrote {GATES_JSON}")


if __name__ == "__main__":
    main()
