# research_1m_rule1.py
#
# The EVIDENCE reading of the rule 1 sweep (Lode, 2026-08-27: "how could we
# further improve with proving the r3 to be the best approach?"). Three
# readings, all arithmetic over quickfix1m1dcRule1.json - NO engine passes,
# seconds to run:
#
#   A  PAIRED BOOTSTRAP. Rule 3 against every other count as a paired
#      question on shared market days (the day-cluster bootstrap of
#      sharpe_stats, the same method that put P <= 0.02 on band-vs-no-band):
#      resample the days, take both cells' trades on them, difference the
#      net R and the per-trade Sharpe. Shared trades cancel, so the P value
#      prices exactly what differs. NO SELECTION PENALTY is applied,
#      deliberately: rule 1 = 3 is the pre-existing Socrates rule, not a
#      cell picked off this sweep, so there is no search to deflate for -
#      the one statistical mercy of this comparison.
#
#   B  MARGINAL-TRADE DECOMPOSITION. On a thin sample a MECHANISM
#      generalizes better than a ranking, so split each rival's blotter
#      against rule 3's by (market, entry session, side): trades both took
#      at the same minute (identical, they cancel), trades both took at a
#      different minute (the count moved the timing), and trades only one
#      side took. If the trades a LOWER count adds - entries on levels with
#      fewer tests - lose money consistently across months, that is the
#      mechanism "a level with fewer tests is less proven", which is worth
#      more than any single P value here.
#
#   C  ROLLING DIFFERENCE. Months are arbitrary cuts, so the r3-minus-rN
#      cumulative net R is read as a series on the market days: the share
#      of rolling ~3-month windows in which r3 is ahead, the worst
#      give-back of the advantage, and the month-end waypoints. An
#      advantage that grinds up across regimes is structure; one big step
#      in one regime is a regime.
#
# WHAT THIS CANNOT DO: rescue the sample. Eight months and 37-187 trades
# per cell bound every verdict at "not rejected"; the pre-registered
# forward test (the frozen rules scoring new months as they land) is the
# only thing that upgrades it.
#
# Usage:  python research_1m_rule1.py
# Output: printed, and the same text under
# output/quickfix1m1dcRule1_research.txt so a reading can be quoted later
# without rerunning it.

import json
from datetime import datetime
from pathlib import Path

import numpy as np

import build_1m_rule1_report as r1
import sharpe_stats as ss

HERE = Path(__file__).resolve().parent
OUT_TXT = HERE / "output" / "quickfix1m1dcRule1_research.txt"

BOOT_REPS = 10000
SEED = 20260827
ROLL_DAYS = 60          # ~3 months of market days, the rolling window
RIVALS = [n for n in r1.REVERSAL_COUNTS if n != r1.PUBLISHED_COUNT]


def fnum(x, w=7, p=2):
    return f"{x:+{w}.{p}f}" if x is not None else " " * (w - 1) + "-"


def cell_trades(payload, suffix, n):
    return sorted(payload["trades"][f"{suffix} r{n}"],
                  key=lambda t: t["entry_ts"])


def paired_delta_netr(days_a, days_b, reps=BOOT_REPS, seed=SEED):
    """Day-cluster bootstrap of total net R (a) - (b): resample market days
    with replacement, sum both cells' trades on the sampled days, difference.
    Kept beside the reading rather than in sharpe_stats: it is this page's
    question (money on shared days), not a reusable formula."""
    sa = np.array([d.sum() for d in days_a])
    sb = np.array([d.sum() for d in days_b])
    n_days = len(sa)
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, n_days, (reps, n_days))
    deltas = (sa - sb)[picks].sum(axis=1)
    return dict(mean=float(deltas.mean()),
                ci_lo=float(np.percentile(deltas, 2.5)),
                ci_hi=float(np.percentile(deltas, 97.5)),
                p_le_0=float(np.mean(deltas <= 0.0)))


def classify(trades_r3, trades_rn):
    """The marginal-trade split, keyed by (market, entry session, side).

    `identical` pairs entered the SAME minute (same fills, they cancel in
    any paired comparison); `shifted` pairs are the same session and side
    at a different minute - the count moved the timing - reported as the
    net R each side booked on those sessions; `only` is what one count
    took and the other never did.
    """
    def key(t):
        return (t["market"], t["entry_date"], t["side"])
    a = {}
    for t in trades_r3:
        a.setdefault(key(t), []).append(t)
    b = {}
    for t in trades_rn:
        b.setdefault(key(t), []).append(t)
    out = dict(identical=[], shifted_r3=[], shifted_rn=[],
               only_r3=[], only_rn=[])
    for k, ts in a.items():
        if k in b:
            for t in ts:
                if any(u["entry_ts"] == t["entry_ts"] for u in b[k]):
                    out["identical"].append(t)
                else:
                    out["shifted_r3"].append(t)
        else:
            out["only_r3"].extend(ts)
    for k, ts in b.items():
        if k in a:
            for t in ts:
                if not any(u["entry_ts"] == t["entry_ts"] for u in a[k]):
                    out["shifted_rn"].append(t)
        else:
            out["only_rn"].extend(ts)
    return out


def bucket_line(name, trades):
    n = len(trades)
    if not n:
        return f"    {name:24s}    -"
    wins = sum(1 for t in trades if t["net_r"] > 0)
    net = sum(t["net_r"] for t in trades)
    months = {}
    for t in trades:
        months[t["entry_date"][:7]] = (months.get(t["entry_date"][:7], 0.0)
                                       + t["net_r"])
    neg = sum(1 for v in months.values() if round(v, 2) < 0)
    return (f"    {name:24s} {n:4d} trades  wr {100 * wins / n:5.1f}%  "
            f"net {fnum(net)}R  avg {fnum(net / n, 6, 3)}R  "
            f"losing months {neg}/{len(months)}")


def rolling_read(days_r3, days_rn, calendar):
    """The r3-minus-rN difference as a series on the market days."""
    diff = np.array([a.sum() - b.sum()
                     for a, b in zip(days_r3, days_rn)])
    cum = diff.cumsum()
    peak = np.maximum.accumulate(cum)
    giveback = float((peak - cum).max())
    gb_end = int((peak - cum).argmax())
    gb_start = int(np.argmax(cum[:gb_end + 1])) if gb_end else 0
    if len(diff) > ROLL_DAYS:
        roll = np.convolve(diff, np.ones(ROLL_DAYS), "valid")
        ahead = float(np.mean(roll > 0.0))
    else:
        ahead = None
    month_end = {}
    for i, d in enumerate(calendar):
        month_end[d[:7]] = cum[i]
    return dict(total=float(cum[-1]), ahead=ahead, giveback=giveback,
                gb_span=(calendar[gb_start][:10], calendar[gb_end][:10]),
                month_end=month_end)


def anchor_report(label, suffix, payload, calendar, out):
    def w(line=""):
        print(line, flush=True)
        out.append(line)

    band = r1.mx.band_label(*r1.mx.BAND_CUTS_BY_STOP[label][1])
    w()
    w("=" * 78)
    w(f"{label} stop, band {band}")
    w("=" * 78)
    r3 = cell_trades(payload, suffix, r1.PUBLISHED_COUNT)
    days3 = ss.by_entry_day(r3, calendar)

    w()
    w("A. PAIRED BOOTSTRAP - rule 3 against each count, shared market days")
    w(f"   {BOOT_REPS} day resamples; P = share of resamples in which rule 3")
    w("   was NOT ahead. No selection deflation: rule 3 is the pre-existing")
    w("   rule, not a cell picked off this sweep.")
    w(f"   {'pair':10s} {'n3':>4s} {'nN':>4s}   "
      f"{'dNetR':>8s} {'95% CI':>18s} {'P(<=0)':>7s}   "
      f"{'dSR/trade':>9s} {'P(<=0)':>7s}")
    for n in RIVALS:
        rn = cell_trades(payload, suffix, n)
        daysn = ss.by_entry_day(rn, calendar)
        dr = paired_delta_netr(days3, daysn)
        dsr = ss.paired_delta_sr(days3, daysn, reps=BOOT_REPS, seed=SEED)
        sr_txt = (f"{fnum(dsr['mean'], 8, 3)} {dsr['p_le_0']:7.3f}"
                  if dsr else f"{'-':>8s} {'-':>7s}")
        w(f"   r3 vs r{n} {len(r3):4d} {len(rn):4d}   "
          f"{fnum(dr['mean'], 8)} [{fnum(dr['ci_lo'])}, {fnum(dr['ci_hi'])}]"
          f" {dr['p_le_0']:7.3f}   {sr_txt}")

    w()
    w("B. MARGINAL-TRADE DECOMPOSITION - where each difference comes from")
    w("   (market, entry session, side): identical entries cancel; a shifted")
    w("   minute is the count moving the trigger; 'only' is what one count")
    w("   took and the other never did. The mechanism question: do the")
    w("   trades a LOWER count adds - less-proven levels - lose money")
    w("   consistently?")
    for n in RIVALS:
        rn = cell_trades(payload, suffix, n)
        c = classify(r3, rn)
        w(f"   r3 vs r{n}:")
        w(bucket_line("identical (cancel)", c["identical"]))
        w(bucket_line(f"shifted, r3's side", c["shifted_r3"]))
        w(bucket_line(f"shifted, r{n}'s side", c["shifted_rn"]))
        w(bucket_line("only r3 took", c["only_r3"]))
        w(bucket_line(f"only r{n} took", c["only_rn"]))

    w()
    w(f"C. ROLLING DIFFERENCE - r3 minus rN on the market days "
      f"({ROLL_DAYS}-day windows)")
    w("   'ahead' = share of rolling windows in which r3 gained more than")
    w("   rN; the give-back is the worst stretch the advantage handed back.")
    for n in RIVALS:
        rn = cell_trades(payload, suffix, n)
        daysn = ss.by_entry_day(rn, calendar)
        r = rolling_read(days3, daysn, calendar)
        me = "  ".join(f"{m[5:]}:{v:+.1f}"
                       for m, v in sorted(r["month_end"].items()))
        ahead = (f"{100 * r['ahead']:.0f}%" if r["ahead"] is not None
                 else "-")
        w(f"   r3 - r{n}: total {fnum(r['total'])}R  |  ahead in {ahead} "
          f"of windows  |  worst give-back {r['giveback']:.2f}R "
          f"({r['gb_span'][0]} to {r['gb_span'][1]})")
        w(f"      month-end cum: {me}")


def main():
    payload = json.loads(r1.OUT_JSON.read_text(encoding="utf-8"))
    calendar = payload["calendar"]
    out = []

    def w(line=""):
        print(line, flush=True)
        out.append(line)

    w(f"THE RULE 1 EVIDENCE READING - {datetime.now():%Y-%m-%d %H:%M}")
    w(f"sweep built {payload.get('built', 'unknown')}, "
      f"{len(calendar)} market days, {calendar[0]} to {calendar[-1]}")
    w("All arithmetic over the sweep's own trades; no engine passes. The")
    w("verdict ceiling on this sample is 'not rejected', never 'confirmed'.")
    for label, _mc in r1.ANCHORS:
        suffix = "4th5th" if label == "4th/5th" else label
        anchor_report(label, suffix, payload, calendar, out)
    OUT_TXT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT_TXT.name}")


if __name__ == "__main__":
    main()
