# research_1m_sharpe.py
#
# The SHARPE reading of the R-cut band grids (Lode, 2026-08-22): is the
# adopted geometry zone a measured edge or the luckiest cell of a 231-cell
# search? Three readings, all arithmetic over the grids' cached trade lists -
# NO engine passes, seconds to run:
#
#   A/B  every cell as per-trade Sharpe WITH ERROR BARS (Lo 2002) and a PSR
#        (Bailey & Lopez de Prado) carrying the skew/kurtosis correction the
#        -1R-floor, long-right-tail R distribution needs. The flag grid says
#        which cells are distinguishable from zero and which are
#        distinguishable from the CHOSEN cell - if almost nothing is, the
#        heatmap's warm zone is one blob of shared evidence, not a zone.
#   C    the band against no band as a PAIRED question (day-cluster
#        bootstrap, shared trades cancel): did the ratio buy per-trade
#        quality faster than it sold trade count? The hurdle is
#        sqrt(n_full / n_band) of per-trade lift for break-even annualised.
#   D    the DEFLATED Sharpe: PSR against the best Sharpe a no-edge search
#        of N effective trials would show anyway. Effective N estimated by
#        the participation ratio of the cells' daily-return correlation
#        matrix (headline) and average-correlation shrinkage (sanity check),
#        with the DSR printed across a whole ladder of N so the estimate's
#        weight is visible, plus the break-even N*.
#
# WHAT THIS CANNOT DO: rescue the sample. With ~80 trades in the chosen cell
# the best available verdict is "not rejected", never "confirmed" - a low DSR
# says the search could have manufactured the result, not that it did.
#
# The universe defaults to the TRADED one (HUMAN_APPROVED, s.16) because that
# is the question anyone acts on; --universe research reads the grid's own
# whole-universe record. Same lesson as the R-cut page's two columns
# (2026-08-20): same arithmetic, different universe, different number.
#
# Usage:  python research_1m_sharpe.py                  # both anchors, traded
#         python research_1m_sharpe.py --stop hybrid    # one anchor
#         python research_1m_sharpe.py --universe research
#
# Output: printed, and the same text under output/quickfix1m1dc_sharpe_*.txt
# so a reading can be quoted later without rerunning it.

import argparse
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np

import run_1m
import run_1m_matrix as mx
import build_1m_rcut_report as rcut
import sharpe_stats as ss

HERE = Path(__file__).resolve().parent

# Cells below this many trades get no statistics: an SR on 12 trades is
# noise with a decimal point, and letting such cells into the cross-trial
# variance or the correlation matrix would let the emptiest corners of the
# grid shape the deflation. They still count toward the trials SEARCHED -
# the search did look at them.
MIN_N = 30

# Market days per year, the annualisation convention. The union calendar is
# what the account actually moves on, so trades-per-year is n scaled by the
# calendar's own span against this.
ANN_DAYS = 252

# The effective-N ladder section D prints DSR across, so the verdict's
# sensitivity to the estimate is on the page whatever the estimate says.
N_LADDER = (3, 5, 10, 20, 50)

BOOT_REPS = 10000


def fnum(x, w=6, p=2):
    return f"{x:{w}.{p}f}" if x is not None else " " * (w - 3) + "n/a"


def cell_num(key):
    """Sort/axis helper: '0.20|0.60' -> (0.20, 0.60), inf upper included."""
    lo, hi = key.split("|")
    return float(lo), float("inf") if hi == "inf" else float(hi)


def chosen_cell_key(matrix, stop_label):
    """The anchor's own middle band slot, read from the matrix rather than
    written here, so this report and the pages cannot disagree about which
    cell was adopted. Each anchor carries 000-050 and full as fixed
    comparison points; the remaining band is its chosen one (2026-08-18)."""
    bands = {v["props"]["band"] for v in matrix["variants"].values()
             if v["props"]["stop"] == stop_label}
    others = bands - {"000-050", "full"}
    if len(others) != 1:
        raise SystemExit(f"cannot identify {stop_label}'s chosen band "
                         f"in the matrix: {sorted(bands)}")
    lo, hi = others.pop().split("-")
    return f"{int(lo) / 100:.2f}|{int(hi) / 100:.2f}"


def top_market(trades):
    """Largest single market's share of net R - measure()'s convention."""
    per = {}
    for t in trades:
        per[t["market"]] = per.get(t["market"], 0.0) + t["net_r"]
    if not per:
        return None, None
    netr = sum(per.values())
    mkt, r = max(per.items(), key=lambda kv: kv[1])
    return mkt, (100.0 * r / netr if netr > 0 else None)


def crosscheck(matrix, stop_label, key, trades):
    """The traded-universe slice of the grid's chosen cell must reproduce the
    matrix's own cell for the same dials trade for trade (the 2026-08-20
    lesson made a check): same trade keys, same net R. A mismatch means the
    two inputs were built on different data windows - the reading still
    prints, flagged, because a stale grid is visible rather than fatal."""
    name = next((n for n, v in matrix["variants"].items()
                 if v["props"]["stop"] == stop_label
                 and v["props"]["lockout"] == "1"
                 and v["props"]["band"] not in ("000-050", "full")), None)
    if name is None:
        return "no matching matrix cell found"
    mine = {(t["market"], t["entry_ts"], t["side"]) for t in trades}
    theirs = {(t["market"], t["entry_ts"], t["side"])
              for t in matrix["trades"][name]}
    if mine == theirs:
        return f"OK: {key} (traded universe) == matrix {name}, {len(mine)} trades"
    return (f"WARNING: {key} vs matrix {name} disagree "
            f"({len(mine)} vs {len(theirs)} trades, {len(mine ^ theirs)} "
            f"differ) - grids likely built on different data windows")


def anchor_report(stop_name, universe, matrix, out):
    v = rcut.variant(stop_name)
    if not v["trades"].exists():
        out(f"SKIP {stop_name}: {v['trades'].name} not built yet")
        return
    tc = json.loads(v["trades"].read_text(encoding="utf-8"))
    calendar = tc["calendar"]
    years = len(calendar) / ANN_DAYS

    def pick(trades):
        if universe == "traded":
            return [t for t in trades if t["market"] in run_1m.HUMAN_APPROVED]
        return list(trades)

    cells = {k: pick(ts) for k, ts in tc["trades"].items()}
    stats = {k: ss.sharpe([t["net_r"] for t in ts])
             for k, ts in cells.items()}
    chosen = chosen_cell_key(matrix, v["stop_label"])

    def ann(st):
        if st["sr"] is None:
            return None
        return st["sr"] * math.sqrt(st["n"] / years)

    out("=" * 78)
    out(f"R-CUT SHARPE REPORT -- stop anchor: {v['stop_label']} "
        f"(stop_mode={v['stop_mode']})")
    out(f"inputs   : {v['trades'].name}  ({len(tc['trades']) - 1} cells "
        f"+ baseline, data to {calendar[-1]})")
    out(f"universe : {universe}"
        + ("  (HUMAN_APPROVED, 22 markets)" if universe == "traded"
           else "  (whole grid record, no market filter)"))
    out(f"unit     : per-trade Sharpe on net R; annSR = SR * sqrt(trades/yr),"
        f" {len(calendar)} market days = {years:.2f} yr @ {ANN_DAYS}/yr")
    out(f"gates    : statistics need n >= {MIN_N} trades")
    if universe == "traded":
        out(f"crosscheck: {crosscheck(matrix, v['stop_label'], chosen, cells[chosen])}")
    out("")

    # ---- A. anchor rows -------------------------------------------------
    eligible = {k: st for k, st in stats.items()
                if k != "baseline" and st["n"] >= MIN_N and st["sr"] is not None}
    best = max(eligible, key=lambda k: eligible[k]["sr"]) if eligible else None
    rows = [("full (no band)", "baseline"), (f"CHOSEN {chosen}", chosen)]
    for extra in ("0.00|0.50", "0.20|0.50"):
        if extra != chosen and extra in stats:
            rows.append((extra, extra))
    if best and best != chosen:
        rows.append((f"best cell {best}", best))

    out("A. ANCHOR ROWS")
    out("  cell                 n  meanR  stdR      SR     SE   95% CI"
        "           annSR  PSR(>0)  top mkt")
    for label, key in rows:
        st = stats[key]
        p = ss.psr(st["sr"], st["n"], st["skew"], st["kurt"])
        mkt, share = top_market(cells[key])
        top = f"{share:3.0f}% {mkt}" if share is not None else "   n/a"
        out(f"  {label:<18} {st['n']:>3}  {fnum(st['mean'],5)}  {fnum(st['sd'],5)}"
            f"  {fnum(st['sr'])}  {fnum(st['se'],5)}"
            f"  [{fnum(st['ci_lo'],5)},{fnum(st['ci_hi'],6)}]"
            f"  {fnum(ann(st),6,2)}  {fnum(p,7,3)}  {top}")
    out("")

    # ---- B. the grid ----------------------------------------------------
    los = sorted({cell_num(k)[0] for k in stats if k != "baseline"})
    his = sorted({cell_num(k)[1] for k in stats if k != "baseline"})
    ch = stats[chosen]

    def key_of(lo, hi):
        h = "inf" if math.isinf(hi) else f"{hi:.2f}"
        return f"{lo:.2f}|{h}"

    def flag(st):
        if st["n"] < MIN_N or st["sr"] is None:
            return " ."
        f = "*" if st["ci_lo"] > 0 else " "
        overlap = (st["ci_lo"] <= ch["ci_hi"] and ch["ci_lo"] <= st["ci_hi"])
        return f + ("~" if overlap else " ")

    out(f"B. THE GRID  (SR per trade; rows = lower cut, cols = upper cut;"
        f" '.' = n < {MIN_N})")
    head = "        " + "".join(f"{('inf' if math.isinf(h) else f'{h:.2f}'):>7}"
                                for h in his)
    out(head)
    for lo in los:
        line = f"  {lo:.2f}  "
        for hi in his:
            st = stats.get(key_of(lo, hi))
            line += f"{fnum(st['sr'], 7)}" if st and st["n"] >= MIN_N \
                and st["sr"] is not None else f"{'.':>7}"
        out(line)
    out("")
    out(f"  flags ('*' 95% CI excludes 0; '~' CI overlaps CHOSEN {chosen};"
        f" '.' n < {MIN_N})")
    out(head)
    for lo in los:
        line = f"  {lo:.2f}  "
        for hi in his:
            st = stats.get(key_of(lo, hi))
            line += f"{flag(st) if st else '':>7}"
        out(line)
    out("")

    # ---- C. band vs no band, paired -------------------------------------
    out("C. BAND vs NO BAND (day-cluster bootstrap, paired on shared days)")
    base, band = stats["baseline"], ch
    if base["sr"] is not None and band["sr"] is not None:
        shared = ({(t["market"], t["entry_ts"], t["side"]) for t in cells[chosen]}
                  & {(t["market"], t["entry_ts"], t["side"])
                     for t in cells["baseline"]})
        da = ss.daily_returns(cells[chosen], calendar)
        db = ss.daily_returns(cells["baseline"], calendar)
        rho = (float(np.corrcoef(da, db)[0, 1])
               if da.std() > 0 and db.std() > 0 else None)
        boot = ss.paired_delta_sr(ss.by_entry_day(cells[chosen], calendar),
                                  ss.by_entry_day(cells["baseline"], calendar),
                                  reps=BOOT_REPS)
        need = math.sqrt(base["n"] / band["n"])
        lift = band["sr"] / base["sr"] if base["sr"] > 0 else None
        out(f"  delta SR (chosen - full)     {fnum(band['sr'] - base['sr'])}")
        if boot:
            out(f"  bootstrap: mean {fnum(boot['mean'])}  se {fnum(boot['se'],5)}"
                f"  95% [{fnum(boot['ci_lo'],5)},{fnum(boot['ci_hi'],6)}]"
                f"  P(delta<=0) {boot['p_le_0']:.3f}  ({boot['reps']} reps)")
        else:
            out("  bootstrap: too few usable reps")
        out(f"  trades shared with full run  {len(shared)} of {band['n']}"
            + (f";  daily-return corr {rho:.2f}" if rho is not None else ""))
        out(f"  required lift for equal annSR  x{need:.2f}"
            f"  (= sqrt({base['n']}/{band['n']}), the trades the band refuses)")
        out(f"  measured lift                  "
            + (f"x{lift:.2f}" if lift else "n/a (full run SR <= 0)"))
    else:
        out("  not computable (a side lacks trades)")
    out("")

    # ---- D. selection penalty -------------------------------------------
    out("D. SELECTION PENALTY (the price-fitting number)")
    n_searched = len(tc["trades"]) - 1          # every cell the search looked at
    srs = np.array([st["sr"] for st in eligible.values()])
    out(f"  trials searched                {n_searched} cells"
        f"  ({len(eligible)} with n >= {MIN_N} enter the estimates)")
    if len(eligible) < 3 or band["sr"] is None:
        out("  too few eligible cells for a deflation estimate")
        return
    var_trials = float(np.var(srs, ddof=1))
    out(f"  cross-cell SR spread           var {var_trials:.4f}"
        f"  (sd {math.sqrt(var_trials):.3f})")

    # Effective N. Zero-variance daily series cannot enter a correlation.
    keys = [k for k in eligible]
    series = np.array([ss.daily_returns(cells[k], calendar) for k in keys])
    keep = series.std(axis=1) > 0
    series = series[keep]
    corr = np.corrcoef(series)
    n_pr = ss.participation_ratio(corr)
    off = corr[~np.eye(len(corr), dtype=bool)]
    rho_bar = float(off.mean())
    n_avg = ss.neff_average_corr(len(corr), rho_bar)
    out(f"  effective N, participation     {n_pr:.1f}"
        f"   (eigenvalues of {len(corr)} cells' daily-return correlation)")
    out(f"  effective N, avg-correlation   {n_avg:.1f}"
        f"   (rho_bar {rho_bar:.2f}; the sanity check)")

    ns = sorted(set(list(N_LADDER) + [max(1, round(n_pr)),
                                      max(1, round(n_avg)), n_searched]))
    out("  expected best SR of a NO-EDGE search (SR0), and the chosen cell's"
        " DSR, by N:")
    out("      N    " + "".join(f"{n:>7}" for n in ns))
    out("      SR0  " + "".join(
        f"{ss.expected_max_sr(var_trials, n):>7.2f}" for n in ns))
    out("      DSR  " + "".join(
        fnum(ss.dsr(band['sr'], band['n'], band['skew'], band['kurt'],
                    var_trials, n), 7, 3) for n in ns))
    star = ss.breakeven_n(band["sr"], band["n"], band["skew"], band["kurt"],
                          var_trials, n_searched)
    if star is None:
        out("  break-even N*: none - the PSR is below 0.95 before any deflation")
    elif star == n_searched:
        out(f"  break-even N*: >= {n_searched} - DSR holds 0.95 across the "
            "whole search")
    else:
        out(f"  break-even N*: {star} - DSR >= 0.95 only while effective N <= {star}")
    out("")


def main():
    ap = argparse.ArgumentParser(description="Sharpe reading of the R-cut grids")
    ap.add_argument("--stop", choices=[*rcut.VARIANTS, "both"], default="both")
    ap.add_argument("--universe", choices=["traded", "research"],
                    default="traded")
    args = ap.parse_args()

    matrix = json.loads((HERE / "output" / "quickfix1m1dc_matrix.json")
                        .read_text(encoding="utf-8"))
    lines = []

    def out(s=""):
        lines.append(s)
        print(s)

    out(f"built {datetime.now():%Y-%m-%d %H:%M}  --  research reading, not a"
        " page in the refresh chain")
    out("")
    stops = list(rcut.VARIANTS) if args.stop == "both" else [args.stop]
    for s in stops:
        anchor_report(s, args.universe, matrix, out)

    dest = HERE / "output" / f"quickfix1m1dc_sharpe_{args.universe}.txt"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written: {dest}")


if __name__ == "__main__":
    main()
