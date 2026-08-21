# The R-cut per-market splice (market_gains) must reproduce a full run when
# markets gain days WITHOUT moving the union calendar - the exact state two
# refreshes in one day left the Hybrid grid in on 2026-08-21, which then cost
# a full ~93-minute rebuild for want of this view.
#
# Real engine, real bars, so it runs only under RCUT_SLOW=1:
#
#   RCUT_SLOW=1 python tests/test_rcut_market_days.py
#
# Scenario built here: GC and URA unchanged (GC owns the union's last day),
# PL and ZW cached one day short with their then-last day re-flagged
# entries_allowed=False, exactly as the loaders flag a window end. The union
# calendar of the cached state therefore EQUALS the current one, and only
# per-market calendars can place the cut.
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run_1m                                  # noqa: E402
import build_1m_rcut_report as rc              # noqa: E402
from engine_1m import Day                      # noqa: E402

GAINERS = ["PL", "ZW"]
STABLE = ["GC", "URA"]
CELLS = [(None, None), (0.0, 0.5), (0.2, 0.6), (0.25, 0.30), (0.5, None)]


def reflag_last(days):
    last = days[-1]
    return days[:-1] + [Day(date=last.date, contract=last.contract,
                            bars=last.bars, settle_ts=last.settle_ts,
                            settle_price=last.settle_price,
                            entries_allowed=False)]


def truncated(days):
    """The market one day shorter, its then-last day flagged as window end."""
    return reflag_last(list(days[:-1]))


def make_run_cell(universe, dials):
    """The script's run() over a fixed market universe - same comparable
    stripping, same tagging, same ordering."""
    def run_cell(lo, hi, first_date=None):
        cell = dict(dials, min_rpu_range_ratio=lo, max_rpu_range_ratio=hi)
        trades = []
        for key, (days, files, tick) in universe.items():
            use = days
            if first_date is not None:
                use = [d for d in days if d.date >= first_date]
                if not use:
                    continue
            tr, _ = run_1m.engine_1m.run_market(use, files, tick, **cell)
            for t in tr:
                t["market"] = key
            trades.extend(rc.comparable(t) for t in tr)
        trades.sort(key=lambda t: t["entry_ts"])
        return trades
    return run_cell


def main():
    if os.environ.get("RCUT_SLOW") != "1":
        print("RCUT_SLOW=1 not set - skipping the real-bars per-market "
              "splice test.")
        return 0
    dials = rc.variant("hybrid")["dials"]
    current, cached = {}, {}
    for key in STABLE + GAINERS:
        inputs, excluded = run_1m.market_inputs(key)
        if inputs is None:
            print(f"{key}: EXCLUDED ({excluded['reason']}) - cannot build "
                  f"the scenario, aborting")
            return 1
        days, files, tick, _note = inputs
        current[key] = (days, files, tick)
        cached[key] = ((truncated(days) if key in GAINERS else days),
                       files, tick)
    # The scenario only exists if a stable market owns the union's last day.
    last_union = max(d[0][-1].date for d in current.values())
    if not any(current[k][0][-1].date == last_union for k in STABLE):
        print("scenario impossible: no stable market owns the union's last "
              "day - pick different markets")
        return 1

    def md(universe):
        return {k: [d.date.isoformat() for d in v[0]]
                for k, v in universe.items()}

    def union(universe):
        return [d.isoformat() for d in run_1m.calendar_union(
            [[day.date for day in v[0]] for v in universe.values()])]

    old_cal, new_cal = union(cached), union(current)
    if old_cal != new_cal:
        print("scenario broken: the union calendar moved "
              f"({old_cal[-1]} vs {new_cal[-1]})")
        return 1

    run_cached = make_run_cell(cached, dials)
    run_current = make_run_cell(current, dials)
    tcache = {rc.cell_key(lo, hi): run_cached(lo, hi) for lo, hi in CELLS}
    full = {rc.cell_key(lo, hi): run_current(lo, hi) for lo, hi in CELLS}

    spliced = rc.rebuild_tail(
        tcache, old_cal, new_cal, CELLS, run_current,
        log=lambda m: print("  " + m),
        old_market_days=md(cached), new_market_days=md(current),
        changed_markets=set(GAINERS))
    bad = 0
    if spliced is None:
        print("FAIL: the per-market splice refused a spliceable scenario")
        bad += 1
    else:
        for key in full:
            if spliced[key] != full[key]:
                print(f"FAIL {key}: spliced != full "
                      f"({len(spliced[key])} vs {len(full[key])} trades)")
                bad += 1
            else:
                print(f"  ok {key}: {len(full[key])} trades, "
                      f"spliced == full")

    # The refusal case: a market whose files moved but that gained no day
    # means the change is inside its history - must rebuild.
    refused = rc.rebuild_tail(
        tcache, old_cal, new_cal, CELLS, run_current,
        log=lambda m: print("  " + m),
        old_market_days=md(cached), new_market_days=md(current),
        changed_markets=set(GAINERS) | {"GC"})
    if refused is not None:
        print("FAIL: a changed-but-not-grown market did not force a rebuild")
        bad += 1
    else:
        print("  ok refusal: changed-but-not-grown market rebuilds")

    print("PASS" if bad == 0 else f"FAIL: {bad} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
