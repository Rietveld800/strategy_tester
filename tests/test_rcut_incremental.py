"""Tests for the R-cut grid's incremental rebuild (Lode, 2026-08-19).

The claim being pinned is one sentence: A SPLICED GRID EQUALS THE GRID A FULL
REBUILD WOULD HAVE PRODUCED. Everything here exists to make that falsifiable
rather than plausible, because the thing being made faster is the research
record a published band was read off, and a wrong cache hit is invisible once
the page is drawn.

It is tested at two levels, because two different things can be wrong:

1. THE SPLICE ARITHMETIC -- which trades are kept, which are recomputed, where
   the cut goes. Tested against a deterministic stand-in "engine" whose full
   answer is known, so `spliced == full` is an exact assertion and needs no
   bars. This is where the awkward cases live: a trade straddling the cut, the
   forced `data_end` exit at the old window's end, a re-stitched calendar.

2. THE WARM-UP -- whether the real engine, started part-way through the window,
   reproduces what it produces from the start. No amount of arithmetic settles
   that; it needs the real bars and real passes, so it is guarded behind
   RCUT_SLOW=1 and takes minutes.

Run the fast ones with `python -m pytest tests/test_rcut_incremental.py`, and
the slow one with `RCUT_SLOW=1` set as well.
"""

import os
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_1m_rcut_report as rc  # noqa: E402


CAL = [f"2026-06-{d:02d}" for d in range(1, 21)]     # 20 market days


def trade(market, entry, exit_, side="long", reason="close1", net_r=1.0):
    """A trade shaped like the engine's, with only the fields the splice reads."""
    return dict(market=market, side=side,
                entry_date=entry, entry_ts=f"{entry} 12:00:00+00:00",
                exit_date=exit_, exit_ts=f"{exit_} 20:00:00+00:00",
                reason=reason, net_r=net_r)


# --- day_index -----------------------------------------------------------

def test_day_index_finds_a_day_and_the_gap_where_one_is_missing():
    assert rc.day_index(CAL, "2026-06-01") == 0
    assert rc.day_index(CAL, "2026-06-10") == 9
    # A date that is not itself a market day lands on the next one, which is
    # what keeps a weekend entry_date from throwing the cut off the calendar.
    assert rc.day_index(CAL, "2026-06-09T00:00") == 9


# --- data_only_grew ------------------------------------------------------

def test_growth_screen_accepts_appends_new_files_and_touched_mtimes():
    old = {"GC/GCZ6.parquet": "100:5", "CL/CLU6.parquet": "80:5"}
    assert rc.data_only_grew(old, {"GC/GCZ6.parquet": "140:9",
                                   "CL/CLU6.parquet": "80:5"})
    # A new contract file is a roll, not a rewrite.
    assert rc.data_only_grew(old, {"GC/GCZ6.parquet": "100:5",
                                   "CL/CLU6.parquet": "80:5",
                                   "CL/CLV6.parquet": "12:9"})

def test_growth_screen_refuses_anything_that_lost_data():
    old = {"GC/GCZ6.parquet": "100:5", "CL/CLU6.parquet": "80:5"}
    assert not rc.data_only_grew(old, {"GC/GCZ6.parquet": "90:9",
                                       "CL/CLU6.parquet": "80:5"})   # shrank
    assert not rc.data_only_grew(old, {"GC/GCZ6.parquet": "100:5"})   # vanished
    assert not rc.data_only_grew(old, {})
    assert not rc.data_only_grew(None, {"GC/GCZ6.parquet": "100:5"})  # no manifest


def test_growth_screen_refuses_a_same_size_rewrite():
    """The hole this closes. verify_overlap only recomputes the days around the
    cut, so a file rewritten UNDER the older cached days would never be caught
    there. Refusing a moved mtime at the same size is what covers them, and it
    is affordable because a top-up leaves files it is not extending alone."""
    old = {"GC/GCZ6.parquet": "100:5"}
    assert not rc.data_only_grew(old, {"GC/GCZ6.parquet": "100:9"})


# --- splice_point --------------------------------------------------------

def test_cut_sits_the_overlap_back_from_the_first_new_day_when_nothing_spans_it():
    cache = {"base": [trade("GC", "2026-06-02", "2026-06-03"),
                      trade("CL", "2026-06-05", "2026-06-05")]}
    # 15 cached days, so the first new day is index 15 and the cut is 5 back.
    assert rc.splice_point(cache, CAL, 15) == 10


def test_cut_walks_back_past_a_trade_that_spans_it():
    # Entered before the natural cut (index 10 = 06-11) and still open after it.
    cache = {"base": [trade("GC", "2026-06-08", "2026-06-13")]}
    assert rc.splice_point(cache, CAL, 15) == rc.day_index(CAL, "2026-06-08")


def test_cut_always_walks_past_the_forced_data_end_exit():
    """The engine books an open position at the window's last bar with reason
    `data_end`. That exit is an artefact of where the data stopped, so it must
    never be kept -- and it is exactly a trade that spans any cut at or before
    it, so splice_point walks past it without knowing what `data_end` means."""
    cache = {"base": [trade("GC", "2026-06-09", "2026-06-15",
                            reason="data_end")]}
    w = rc.splice_point(cache, CAL, 15)
    assert w <= rc.day_index(CAL, "2026-06-09")


def test_no_usable_cut_gives_up_rather_than_cutting_at_the_start():
    # A trade open across almost the whole window leaves nowhere safe to cut.
    cache = {"base": [trade("GC", "2026-06-01", "2026-06-15")]}
    assert rc.splice_point(cache, CAL, 15) is None


# --- verify_overlap ------------------------------------------------------

def test_overlap_passes_when_the_engine_reproduces_the_cache():
    shared = [trade("GC", "2026-06-11", "2026-06-12"),
              trade("CL", "2026-06-13", "2026-06-14")]
    ok, detail = rc.verify_overlap(shared, list(shared), "2026-06-10",
                                   "2026-06-15")
    assert ok and "2" in detail


def test_overlap_fails_when_a_value_moved():
    cached = [trade("GC", "2026-06-11", "2026-06-12", net_r=1.0)]
    fresh = [trade("GC", "2026-06-11", "2026-06-12", net_r=1.4)]
    ok, detail = rc.verify_overlap(cached, fresh, "2026-06-10", "2026-06-15")
    assert not ok and "net_r" in detail


def test_overlap_fails_when_a_trade_appears_or_disappears():
    cached = [trade("GC", "2026-06-11", "2026-06-12")]
    ok, _ = rc.verify_overlap(cached, [], "2026-06-10", "2026-06-15")
    assert not ok
    ok, _ = rc.verify_overlap([], cached, "2026-06-10", "2026-06-15")
    assert not ok


def test_a_data_end_trade_is_compared_by_key_but_not_by_value():
    """The fresh run can see the next day, so it closes that position somewhere
    the cached run could not. That is expected and must not abandon the splice
    -- but the trade must still be THERE, or the entries have moved."""
    cached = [trade("GC", "2026-06-14", "2026-06-15", reason="data_end",
                    net_r=0.2)]
    fresh = [trade("GC", "2026-06-14", "2026-06-17", reason="close1",
                   net_r=2.6)]
    ok, _ = rc.verify_overlap(cached, fresh, "2026-06-10", "2026-06-15")
    assert ok
    moved = [trade("GC", "2026-06-14", "2026-06-17", side="short")]
    ok, _ = rc.verify_overlap(cached, moved, "2026-06-10", "2026-06-15")
    assert not ok


# --- rebuild_tail: the splice equals the full answer ---------------------

class Oracle:
    """A stand-in engine with a known full answer.

    It returns the trades of `full` that start on or after the date asked for,
    which is precisely what a correct engine with a perfect warm-up would do.
    So `rebuild_tail`'s output can be compared against `full` itself, and any
    difference is the splice arithmetic being wrong rather than the engine.
    """

    def __init__(self, full):
        self.full = full
        self.calls = []

    def __call__(self, lo, hi, first_date=None):
        self.calls.append((rc.cell_key(lo, hi), first_date))
        trades = self.full[rc.cell_key(lo, hi)]
        if first_date is None:
            return list(trades)
        return [t for t in trades if t["entry_date"] >= first_date.isoformat()]


COMBOS = [(None, None), (0.2, 0.5)]


def full_answer():
    """Two cells over the whole 20-day window, including a trade that spans the
    natural cut and one that runs into the new days."""
    return {
        rc.cell_key(None, None): [
            trade("GC", "2026-06-02", "2026-06-03"),
            trade("CL", "2026-06-09", "2026-06-12"),      # spans a 06-11 cut
            trade("GC", "2026-06-14", "2026-06-15"),
            # Open when the cached window ended on 06-15, so the cache holds it
            # as a forced `data_end` exit and the real answer runs on to 06-17.
            trade("SB", "2026-06-15", "2026-06-17"),
            trade("ZW", "2026-06-16", "2026-06-17"),      # in the new days
        ],
        rc.cell_key(0.2, 0.5): [
            trade("GC", "2026-06-04", "2026-06-05"),
            trade("ZW", "2026-06-17", "2026-06-18"),
        ],
    }


def cached_from(full, last_day):
    """What the cache would hold if the window had ended at `last_day`: trades
    wholly inside it, and an open position booked as `data_end` on its last
    bar -- the engine's real behaviour, which the splice has to survive."""
    out = {}
    for key, trades in full.items():
        kept = []
        for t in trades:
            if t["exit_date"] <= last_day:
                kept.append(dict(t))
            elif t["entry_date"] <= last_day:
                forced = dict(t, exit_date=last_day,
                              exit_ts=f"{last_day} 20:00:00+00:00",
                              reason="data_end", net_r=0.11)
                kept.append(forced)
        out[key] = kept
    return out


def test_spliced_grid_equals_a_full_rebuild():
    full = full_answer()
    old_cal, cache = CAL[:15], cached_from(full, CAL[14])
    oracle = Oracle(full)

    spliced = rc.rebuild_tail(cache, old_cal, CAL, COMBOS, oracle,
                              log=lambda m: None)

    assert spliced is not None
    for key in full:
        assert spliced[key] == full[key], key
    # And it did so by running tails, not whole windows.
    assert all(first is not None for _key, first in oracle.calls)


def test_the_forced_exit_never_survives_the_splice():
    full = full_answer()
    old_cal, cache = CAL[:15], cached_from(full, CAL[14])
    assert any(t["reason"] == "data_end"
               for trades in cache.values() for t in trades)

    spliced = rc.rebuild_tail(cache, old_cal, CAL, COMBOS, Oracle(full),
                              log=lambda m: None)

    assert not any(t["reason"] == "data_end"
                   for trades in spliced.values() for t in trades)


def test_a_cell_the_cache_never_held_is_run_in_full():
    full = full_answer()
    full[rc.cell_key(0.3, 0.6)] = [trade("GC", "2026-06-03", "2026-06-04")]
    combos = COMBOS + [(0.3, 0.6)]
    cache = cached_from(full_answer(), CAL[14])        # without the new cell
    oracle = Oracle(full)

    spliced = rc.rebuild_tail(cache, CAL[:15], CAL, combos, oracle,
                              log=lambda m: None)

    assert spliced[rc.cell_key(0.3, 0.6)] == full[rc.cell_key(0.3, 0.6)]
    assert (rc.cell_key(0.3, 0.6), None) in oracle.calls


def test_a_disagreeing_engine_abandons_the_splice():
    """The case the whole design exists to catch: the bars under the shared days
    moved, so the cache is not a valid prefix. It must rebuild, not splice.

    The corruption has to sit INSIDE the recomputed overlap, because that is the
    span verify_overlap can speak for. Days older than the cut are protected by
    the file screen instead -- see test_growth_screen_refuses_a_same_size_rewrite
    -- and the two together are what cover the window.
    """
    full = full_answer()
    cache = cached_from(full, CAL[14])
    spanning = [t for t in cache[rc.cell_key(None, None)]
                if t["entry_date"] >= "2026-06-11"]
    assert spanning, "fixture must have a trade inside the overlap to corrupt"
    spanning[0]["net_r"] = 99.0

    assert rc.rebuild_tail(cache, CAL[:15], CAL, COMBOS, Oracle(full),
                           log=lambda m: None) is None


def test_a_restitched_calendar_is_refused():
    full = full_answer()
    cache = cached_from(full, CAL[14])
    shifted = ["2026-05-30"] + CAL[1:]        # not a prefix any more
    assert rc.rebuild_tail(cache, CAL[:15], shifted, COMBOS, Oracle(full),
                           log=lambda m: None) is None


def test_no_new_days_is_refused_rather_than_guessed():
    full = full_answer()
    cache = cached_from(full, CAL[-1])
    assert rc.rebuild_tail(cache, CAL, CAL, COMBOS, Oracle(full),
                           log=lambda m: None) is None


# --- the warm-up, against the real engine --------------------------------

@pytest.mark.skipif(not os.environ.get("RCUT_SLOW"),
                    reason="real engine passes; set RCUT_SLOW=1")
def test_real_engine_tail_matches_a_full_pass_on_the_shared_days():
    """Does the engine, started part-way through, reproduce itself?

    PRIME_DAYS exists on the theory that the trailing high-low window and
    prev_trading_date are the only state carried across a day boundary, so a
    few days of lead-in is enough. That is a claim about the engine, not about
    this file's arithmetic, and only real bars can settle it. One market, one
    cell, so it costs a couple of passes rather than an hour.
    """
    import run_1m

    key = "GC"
    inputs, _excluded = run_1m.market_inputs(key)
    assert inputs is not None, f"{key} has no bars to test against"
    days, files, tick, _note = inputs
    assert len(days) > 40, "need a window longer than the warm-up to test one"

    dials = dict(rc.BASE, stop_mode=rc.mx.STOP_MODE_BY_LABEL["4th/5th"],
                 min_rpu_range_ratio=None, max_rpu_range_ratio=None)
    whole, _ = run_1m.engine_1m.run_market(days, files, tick, **dials)

    cut = days[-15].date                      # start the tail 15 days back
    tail, _ = run_1m.engine_1m.run_market(
        [d for d in days if d.date >= cut], files, tick, **dials)

    # Compare on the days after the warm-up: trades entered at least PRIME_DAYS
    # after the tail's own start, which is what a splice would ever keep.
    keep_from = days[-15 + rc.PRIME_DAYS].date.isoformat()

    def kept(trades):
        return [t for t in trades
                if t["entry_date"] >= keep_from and t["reason"] != "data_end"]

    mine, theirs = kept(whole), kept(tail)
    assert mine and len(mine) == len(theirs)
    # What the engine DECIDED is identical: side, entry, stop, rpu, the
    # geometry ratio, the exit and net_r.
    assert [rc.comparable(t) for t in mine] == [rc.comparable(t) for t in theirs]

    # And the ONLY fields that move are the account path, which is why
    # ACCOUNT_FIELDS exists. Pinned as a fact about the engine: if a future
    # change makes a rule field depend on where the run started, the assertion
    # above breaks and the splice must be reconsidered, not widened.
    moved = {f for a, b in zip(mine, theirs) for f in a if a[f] != b[f]}
    assert moved <= set(rc.ACCOUNT_FIELDS), moved


@pytest.mark.skipif(not os.environ.get("RCUT_SLOW"),
                    reason="real engine passes; set RCUT_SLOW=1")
def test_real_bars_splice_equals_a_full_rebuild():
    """The whole claim, on real bars, with nothing simulated.

    A cache is built the way a real one is -- by running the engine over a
    window that stops short -- and then the last days are added and spliced.
    The result must equal the grid a full rebuild produces over the whole
    window, cell for cell and field for field. Two markets and two cells, so it
    is a handful of passes rather than the ninety minutes a real grid costs.
    """
    import run_1m

    loaded = []
    for key in ("GC", "CL"):
        inputs, _excluded = run_1m.market_inputs(key)
        if inputs is not None:
            loaded.append((key, inputs))
    assert loaded, "no bars on disk to test against"

    dials = dict(rc.BASE, stop_mode=rc.mx.STOP_MODE_BY_LABEL["4th/5th"])
    combos = [(None, None), (0.2, 0.5)]

    def window(lo, hi, first=None, last=None):
        cell = dict(dials, min_rpu_range_ratio=lo, max_rpu_range_ratio=hi)
        out = []
        for key, (days, files, tick, _note) in loaded:
            days = [d for d in days
                    if (first is None or d.date >= first)
                    and (last is None or d.date <= last)]
            if not days:
                continue
            trades, _ = run_1m.engine_1m.run_market(days, files, tick, **cell)
            for t in trades:
                t["market"] = key
            out.extend(rc.comparable(t) for t in trades)
        out.sort(key=lambda t: t["entry_ts"])
        return out

    def calendar_to(last=None):
        return [d.isoformat() for d in run_1m.calendar_union(
            [[day.date for day in days
              if last is None or day.date <= last]
             for _key, (days, _f, _t, _n) in loaded])]

    full_cal = calendar_to()
    assert len(full_cal) > 30

    # Prefer a cut where a position is still OPEN, because that is the case the
    # splice has to survive: the cache holds a forced `data_end` exit that the
    # full rebuild never books. Which days those are depends on the bars, so it
    # is searched for rather than assumed -- and if the window holds none, the
    # equivalence is still worth asserting and the Oracle tests above cover the
    # forced exit on their own.
    cut, cache = None, None
    for candidate in full_cal[-4:-14:-1]:
        day = date.fromisoformat(candidate)
        trial = {rc.cell_key(lo, hi): window(lo, hi, last=day) for lo, hi in combos}
        if any(t["reason"] == "data_end"
               for trades in trial.values() for t in trades):
            cut, cache = day, trial
            break
    if cut is None:
        cut = date.fromisoformat(full_cal[-4])
        cache = {rc.cell_key(lo, hi): window(lo, hi, last=cut) for lo, hi in combos}

    old_cal = calendar_to(cut)
    truth = {rc.cell_key(lo, hi): window(lo, hi) for lo, hi in combos}

    spliced = rc.rebuild_tail(cache, old_cal, full_cal, combos,
                              lambda lo, hi, first: window(lo, hi, first=first),
                              log=lambda m: None)

    assert spliced is not None, "the splice was abandoned on clean appended data"
    for key in truth:
        assert spliced[key] == truth[key], key
