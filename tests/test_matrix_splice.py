# The matrix tail splice must reproduce a full run exactly - trades (rule
# fields), per-day geometry counters and the derived account fields alike.
#
# Same shape as the R-cut slow tests: this runs the REAL engine on the real
# bars, so it costs minutes and runs only under MATRIX_SLOW=1:
#
#   MATRIX_SLOW=1 python tests/test_matrix_splice.py [KEY ...]
#
# For each market it builds the cache entry a run over a TRUNCATED window
# would have written - the truncated window's last day gets
# entries_allowed=False and open positions force-close as data_end, exactly
# as futures_days flags a window end - then splices that entry forward over
# the full window and compares every cell against a plain full run.
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run_1m                            # noqa: E402
import run_1m_matrix as mx               # noqa: E402
from engine_1m import Day                # noqa: E402

NEW_DAYS = 3        # how many trailing market days play the part of "new"


def truncated(days, n_keep):
    """The Days a run over the shorter window would have seen: same objects
    up to the boundary, and the boundary day re-flagged as the window end."""
    prefix = list(days[:n_keep])
    last = prefix[-1]
    prefix[-1] = Day(date=last.date, contract=last.contract, bars=last.bars,
                     settle_ts=last.settle_ts,
                     settle_price=last.settle_price, entries_allowed=False)
    return prefix


def run_cells(key, days, files, tick):
    """Every cell of the grid on the given window, as the cache stores it."""
    cells = {}
    for name, dials, markets, _props in mx.VARIANTS:
        if markets is not None and key not in markets:
            continue
        trades, summary = run_1m.engine_1m.run_market(
            days, files, tick, geom_by_day=True, **dials)
        trades, summary = mx.plain_floats(trades, summary)
        geom = summary.pop("geom_days")
        for t in trades:
            t["market"] = key
        cells[name] = dict(trades=trades, geom_days=geom)
    return cells


def check_market(key):
    inputs, excluded = run_1m.market_inputs(key)
    if inputs is None:
        print(f"{key}: EXCLUDED ({excluded['reason']}) - skipped")
        return 0, 0
    days, files, tick, note = inputs
    if len(days) < mx.OVERLAP_DAYS + mx.PRIME_DAYS + NEW_DAYS + 5:
        print(f"{key}: too few days ({len(days)}) - skipped")
        return 0, 0
    cal = [d.date for d in days]
    w0 = len(days) - NEW_DAYS
    prefix = truncated(days, w0)
    cached = run_cells(key, prefix, files, tick)
    full = run_cells(key, days, files, tick)
    ok = bad = 0
    for name in full:
        out = mx.splice_cell(key, cached[name]["trades"],
                             cached[name]["geom_days"], days, files, tick,
                             dict(next(d for n, d, _m, _p in mx.VARIANTS
                                       if n == name)),
                             cal, w0)
        if out is None:
            print(f"  FAIL {key}/{name}: splice returned None")
            bad += 1
            continue
        sp_trades, sp_geom = out
        f_trades = full[name]["trades"]
        probs = []
        if ([mx.comparable(t) for t in sp_trades]
                != [mx.comparable(t) for t in f_trades]):
            probs.append("trades differ")
        if sp_geom != full[name]["geom_days"]:
            probs.append("geometry days differ")
        else:
            fa = mx.apply_account(sp_trades)
            fb = mx.apply_account(f_trades)
            if fa != fb or sp_trades != f_trades:
                probs.append("account fields differ")
        if probs:
            print(f"  FAIL {key}/{name}: {'; '.join(probs)}")
            bad += 1
        else:
            ok += 1
    print(f"{key}: {ok} cells spliced == full"
          + (f", {bad} FAILED" if bad else ""))
    return ok, bad


def main():
    if os.environ.get("MATRIX_SLOW") != "1":
        print("MATRIX_SLOW=1 not set - skipping the real-bars splice test "
              "(it runs the whole grid three times per market).")
        return 0
    keys = sys.argv[1:] or ["GC", "PA", "ZW", "LE", "URA"]
    total_ok = total_bad = 0
    for key in keys:
        ok, bad = check_market(key)
        total_ok += ok
        total_bad += bad
    print(f"\n{total_ok} cells verified, {total_bad} failed")
    if total_bad:
        return 1
    print("The tail splice reproduces a full run on every checked cell.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
