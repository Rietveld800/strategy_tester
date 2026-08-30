"""Tests for research_1m_exit_profile.py - the pre-registered exit-timing
profile (docs/exit_timing_preregistration.md, sections 5, 6 and 10).

What is pinned, on a synthetic gold-like market (tick 0.1) with
hand-computed values:
  - clock horizons take the last bar at or before the instant and flag a
    horizon that falls after the session's last bar;
  - settlement horizons take the settlement PRICE, and their excursions
    stop at the bars strictly before the settlement instant;
  - openN / closeN read the session's first print (its open) and last
    print (its close), and a stop on the open bar prints after the open;
  - stop truncation: a stop printing on the entry bar never counts, a later
    print freezes the path at exactly -1R, and on a settlement bar the
    settlement comes first (the engine's precedence);
  - a splice inside the +3 window raises under strict and is recorded
    otherwise;
  - the AGREEMENT check: trades the engine itself booked on synthetic days
    reproduce gross_r + entry slippage on the stop-truncated path at the
    next settlement, for a close1 and for a stop exit;
  - the flat rule of decision 1 and the day-cluster bootstrap;
  - null placements land on other days at the same session time-of-day.

EXIT_SLOW=1 adds the real-data agreement check over every trade of the
published blotter (minutes: it loads every market's bars).
"""

import os
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import research_1m_exit_profile as ep  # noqa: E402
from engine_1m import Day, LevelsFile, run_market  # noqa: E402

TICK = 0.1


def ts(day, hhmm):
    return pd.Timestamp(f"2026-06-{day:02d} {hhmm}", tz="UTC")


def minute_bars(day, start_hhmm, closes, highs=None, lows=None):
    """One bar per minute from start_hhmm; o = c, h/l default to c."""
    h0, m0 = (int(x) for x in start_hhmm.split(":"))
    out = []
    for i, c in enumerate(closes):
        m = m0 + i
        t = ts(day, f"{h0 + m // 60:02d}:{m % 60:02d}")
        hi = highs[i] if highs and highs[i] is not None else c
        lo = lows[i] if lows and lows[i] is not None else c
        out.append((t, c, max(hi, c), min(lo, c), c))
    return out


def file_at(day_pub, activation, bull, bear=(90.0,), prev_close=99.0):
    return LevelsFile(publish_date=date(2026, 6, day_pub),
                      activation_ts=activation, bull=sorted(bull),
                      bear=sorted(bear), prev_close=prev_close)


BULL5 = [100.0, 100.5, 101.0, 101.5, 102.5]
# The published cell's dials (run_1m.BASELINE): the engine's own defaults
# still carry v1's tighten=True, which the study refuses.
PUBLISHED_DIALS = dict(tighten=False, allow_pre_activation=False,
                       confirm=False, stop_mode="ladder",
                       max_entries_per_session=1, range_mode="trading_day")


# ---------------------------------------------------------------------------
# the hand-built market of the profile tests
# ---------------------------------------------------------------------------

def synthetic_run(splice=True):
    """Day 10: 60 bars 01:00-01:59 falling 0.05 a minute from 100, the entry
    bar (01:10) with a high of 103 (a stop print on the entry bar); settle
    02:30 at 97.0. Day 11: flat 97 with a stop print (high 102.7) at 01:30;
    settle 02:30 at 96.0. Day 12: 08:00-08:59 flat 95, settle 09:30 at
    95.0. Day 13: the next contract (a splice). Files: one live from day 10
    00:00, the next activating day 12 07:35 (no file for day 11)."""
    closes10 = [100.0 - 0.05 * i for i in range(60)]
    highs10 = [None] * 60
    highs10[10] = 103.0
    d10 = Day(date=date(2026, 6, 10), contract="GCQ6",
              bars=minute_bars(10, "01:00", closes10, highs=highs10),
              settle_ts=ts(10, "02:30"), settle_price=97.0)
    closes11 = [97.0] * 60
    highs11 = [None] * 60
    highs11[30] = 102.7
    d11 = Day(date=date(2026, 6, 11), contract="GCQ6",
              bars=minute_bars(11, "01:00", closes11, highs=highs11),
              settle_ts=ts(11, "02:30"), settle_price=96.0)
    d12 = Day(date=date(2026, 6, 12), contract="GCQ6",
              bars=minute_bars(12, "08:00", [95.0] * 60),
              settle_ts=ts(12, "09:30"), settle_price=95.0)
    days = [d10, d11, d12]
    if splice:
        days.append(Day(date=date(2026, 6, 13), contract="GCZ6",
                        bars=minute_bars(13, "01:00", [60.0] * 60),
                        settle_ts=ts(13, "02:30"), settle_price=60.0))
    files = [file_at(9, ts(10, "00:00"), BULL5),
             file_at(11, ts(12, "07:35"), BULL5)]
    return ep.MarketRun(days, files)


GEOM = dict(side="short", entry_first=100.0, rpu=2.6, stop=102.6)


def prof(run, strict=False):
    i0 = run.bar_index(int(ts(10, "01:10").value))
    return ep.profile_at(run, i0, strict=strict, **GEOM)


def test_clock_horizon_reads_the_last_bar_at_or_before_the_instant():
    p = prof(synthetic_run())
    h = p["30m"]                      # instant 01:40 -> bar 40, close 98.0
    assert h["x"] == pytest.approx(2.0)
    assert h["bar_ts"] == int(ts(10, "01:40").value)
    assert h["flag"] is None
    assert h["mfe"] == pytest.approx(2.0)     # 100 - min low (98.0)
    assert h["mae"] == pytest.approx(3.0)     # the entry bar's 103 high


def test_clock_horizon_past_the_session_end_is_flagged():
    p = prof(synthetic_run())
    h = p["1h"]                       # instant 02:10, last bar 01:59
    assert h["bar_ts"] == int(ts(10, "01:59").value)
    assert h["flag"] == "session ended"
    assert h["x"] == pytest.approx(2.95)


def test_settlement_horizons_take_the_settlement_price():
    p = prof(synthetic_run())
    assert p["settle0"]["x"] == pytest.approx(3.0)      # 100 - 97.0
    assert p["settle0"]["mfe"] == pytest.approx(2.95)   # bars only
    assert p["settle1"]["x"] == pytest.approx(4.0)       # 100 - 96.0
    assert p["settle2"]["x"] == pytest.approx(5.0)         # 100 - 95.0


def test_open_and_close_horizons_read_the_sessions_first_and_last_print():
    p = prof(synthetic_run())
    c0 = p["close0"]                  # day 10's last bar, close 97.05
    assert c0["bar_ts"] == int(ts(10, "01:59").value)
    assert c0["x"] == pytest.approx(2.95)
    o1 = p["open1"]                   # day 11's first bar, open 97.0
    assert o1["bar_ts"] == int(ts(11, "01:00").value)
    assert o1["x"] == pytest.approx(3.0)
    assert o1["mfe"] == pytest.approx(3.0)       # the open print counts
    assert p["close1"]["x"] == pytest.approx(3.0)
    assert p["open2"]["x"] == pytest.approx(5.0)  # day 12 opens at 95
    assert p["close2"]["x"] == pytest.approx(5.0)
    assert p["settle3"] == {"reason": "splice"}
    assert p["open3"] == {"reason": "splice"}
    assert p["close3"] == {"reason": "splice"}


def test_a_stop_on_the_open_bar_prints_after_the_open():
    """A stop whose print is the session's FIRST bar does not count at
    openN (the open comes first) but counts at every later horizon."""
    d10 = Day(date=date(2026, 6, 10), contract="GCQ6",
              bars=minute_bars(10, "01:00", [100.0 - 0.05 * i
                                             for i in range(60)]),
              settle_ts=ts(10, "02:30"), settle_price=97.0)
    highs11 = [None] * 60
    highs11[0] = 103.0
    d11 = Day(date=date(2026, 6, 11), contract="GCQ6",
              bars=minute_bars(11, "01:00", [97.0] * 60, highs=highs11),
              settle_ts=ts(11, "02:30"), settle_price=96.0)
    run = ep.MarketRun([d10, d11], [file_at(9, ts(10, "00:00"), BULL5)])
    p = prof(run)
    assert p["open1"]["stopped"] is False
    assert p["open1"]["x_trunc"] == pytest.approx(3.0)
    assert p["settle1"]["stopped"] is True
    assert p["settle1"]["stop_ts"] == int(ts(11, "01:00").value)
    assert p["close1"]["x_trunc"] == pytest.approx(-2.6)


def test_stop_on_the_entry_bar_never_counts_and_a_later_print_freezes():
    p = prof(synthetic_run())
    assert p["30m"]["stopped"] is False          # entry-bar 103 ignored
    assert p["30m"]["x_trunc"] == pytest.approx(2.0)
    assert p["settle0"]["stopped"] is False
    nxt = p["settle1"]                       # stop printed day 11 01:30
    assert nxt["stopped"] is True
    assert nxt["stop_ts"] == int(ts(11, "01:30").value)
    assert nxt["x_trunc"] == pytest.approx(-2.6)   # exactly -1R in price
    assert nxt["mae_trunc"] == pytest.approx(2.6)
    assert nxt["mfe_trunc"] == pytest.approx(3.0)  # best before the stop
    assert p["close1"]["stopped"] is True
    assert p["close1"]["x_trunc"] == pytest.approx(-2.6)
    assert p["open1"]["stopped"] is False        # printed after the open


def test_settlement_beats_a_stop_on_the_settlement_bar():
    """A stop printing on the bar AT settle_ts does not count for that
    settlement horizon (the engine books the settlement first) but does
    count for every later horizon."""
    d10 = Day(date=date(2026, 6, 10), contract="GCQ6",
              bars=minute_bars(10, "01:00", [100.0 - 0.05 * i
                                             for i in range(60)]),
              settle_ts=ts(10, "02:30"), settle_price=97.0)
    closes11 = [97.0] * 91                      # 01:00 .. 02:30
    highs11 = [None] * 91
    highs11[90] = 103.0                         # the 02:30 bar
    d11 = Day(date=date(2026, 6, 11), contract="GCQ6",
              bars=minute_bars(11, "01:00", closes11, highs=highs11),
              settle_ts=ts(11, "02:30"), settle_price=96.0)
    d12 = Day(date=date(2026, 6, 12), contract="GCQ6",
              bars=minute_bars(12, "01:00", [95.0] * 60),
              settle_ts=ts(12, "02:30"), settle_price=95.0)
    run = ep.MarketRun([d10, d11, d12], [file_at(9, ts(10, "00:00"), BULL5)])
    p = prof(run)
    assert p["settle1"]["stopped"] is False
    assert p["settle1"]["x_trunc"] == pytest.approx(4.0)
    assert p["settle2"]["stopped"] is True
    assert p["settle2"]["x_trunc"] == pytest.approx(-2.6)


def test_a_splice_inside_the_window_raises_under_strict():
    run = synthetic_run(splice=True)
    with pytest.raises(ep.SpliceError):
        prof(run, strict=True)
    p = prof(run, strict=False)
    assert p["settle3"] == {"reason": "splice"}
    assert p["settle2"]["x"] == pytest.approx(5.0)   # earlier ones intact


def test_past_the_data_end_is_a_reason_not_a_crash():
    p = prof(synthetic_run(splice=False))
    assert p["settle3"] == {"reason": "data end"}
    assert p["close7"] == {"reason": "data end"}


def test_the_horizon_list_runs_to_day_seven():
    # amendment A2 (2026-08-30): three moments per session, days 0..7
    assert ep.HORIZON_DAYS == 7
    assert len(ep.H_NAMES) == 27
    assert ep.H_NAMES[:6] == ["30m", "1h", "2h", "4h", "settle0", "close0"]
    assert ep.H_NAMES[-3:] == ["open7", "settle7", "close7"]
    assert ep.DECIDING == ("settle0", "settle1")


# ---------------------------------------------------------------------------
# agreement with the engine's own booking
# ---------------------------------------------------------------------------

def entry_day_bars(day, after):
    """The rally-and-return pattern of test_engine_1m: open 99.5, a bar
    testing four reversals (high 102) closing back above the first, then
    the touch (low 99.8) that fires the market order; `after` follows."""
    return [
        (ts(day, "01:00"), 99.5, 99.5, 99.5, 99.5),
        (ts(day, "02:00"), 99.5, 102.0, 99.5, 101.5),
        (ts(day, "03:00"), 101.5, 101.5, 99.8, 99.8),
    ] + after


def gapped_entry_day_bars(day, after):
    """As entry_day_bars, but the bar after the rally never prints the level:
    it opens 99.5 with a high of 99.7, so the fill comes from its open."""
    return [
        (ts(day, "01:00"), 99.5, 99.5, 99.5, 99.5),
        (ts(day, "02:00"), 99.5, 102.0, 99.5, 101.5),
        (ts(day, "03:00"), 99.5, 99.7, 99.4, 99.5),
    ] + after


def engine_days(stop_day10=False, gap=False):
    after = ([(ts(10, "04:00"), 99.7, 102.7, 99.7, 99.7)] if stop_day10
             else [(ts(10, "04:00"), 99.7, 99.7, 99.7, 99.7)])
    after += [(ts(10, "05:00"), 99.6, 99.6, 99.6, 99.6)]
    # a previous session, because with allow_pre_activation=False the
    # engine only trades on a file dated on or after the previous trading
    # date - there is none on a market's first day
    return [
        Day(date=date(2026, 6, 9), contract="GCQ6",
            bars=[(ts(9, "01:00"), 99.5, 99.5, 99.5, 99.5)],
            settle_ts=ts(9, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=(gapped_entry_day_bars if gap else entry_day_bars)(10, after),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 11), contract="GCQ6",
            bars=[(ts(11, "01:00"), 98.0, 98.0, 98.0, 98.0),
                  (ts(11, "02:00"), 98.1, 98.1, 98.1, 98.1)],
            settle_ts=ts(11, "17:30"), settle_price=98.0),
        Day(date=date(2026, 6, 12), contract="GCQ6",
            bars=[(ts(12, "01:00"), 98.0, 98.0, 98.0, 98.0)],
            settle_ts=ts(12, "17:30"), settle_price=98.0),
    ]


@pytest.mark.parametrize("stop_day10, gap, reason", [
    (False, False, "close1"), (True, False, "stop"), (False, True, "close1")])
def test_profile_reproduces_the_engines_booking(stop_day10, gap, reason):
    days = engine_days(stop_day10, gap)
    files = [file_at(9, ts(10, "00:00"), BULL5)]
    trades, summary = run_market(days, files, TICK, **PUBLISHED_DIALS)
    assert summary["trades"] == 1
    t = dict(trades[0], market="GC")
    assert t["reason"] == reason
    if gap:
        assert t["entry"] == pytest.approx(99.3)     # open 99.5 - 2 ticks
        assert t["entry_first"] == pytest.approx(100.0)
    run = ep.MarketRun(days, files)
    p = ep.trade_profile(run, t)
    assert ep.agreement_check(t, p, TICK) is None
    # and the check has teeth: a wrong gross_r is caught
    bad = dict(t, gross_r=t["gross_r"] + 0.5)
    assert ep.agreement_check(bad, p, TICK) is not None


def test_a_window_end_stop_is_checked_on_the_entry_days_last_print():
    # the published pass admits entries on the window's last day
    # (2026-08-30); one stopped in its own session has no settle1 yet
    days = engine_days(stop_day10=True)[:2]
    files = [file_at(9, ts(10, "00:00"), BULL5)]
    trades, _ = run_market(days, files, TICK, **PUBLISHED_DIALS)
    t = dict(trades[0], market="GC")
    assert t["reason"] == "stop" and t["exit_date"] == t["entry_date"]
    p = ep.trade_profile(ep.MarketRun(days, files), t)
    assert p["settle1"] == {"reason": "data end"}
    assert ep.agreement_check(t, p, TICK) is None
    bad = dict(t, gross_r=t["gross_r"] + 0.5)
    assert ep.agreement_check(bad, p, TICK) is not None
    # a close1 booking still needs the next settlement
    assert "no next settlement" in ep.agreement_check(
        dict(t, reason="close1"), p, TICK)


def test_a_tightened_stop_is_refused():
    days = engine_days()
    files = [file_at(9, ts(10, "00:00"), BULL5)]
    trades, _ = run_market(days, files, TICK, **PUBLISHED_DIALS)
    t = dict(trades[0], market="GC", stop_tightened=101.0)
    with pytest.raises(ValueError):
        ep.trade_profile(ep.MarketRun(days, files), t)


# ---------------------------------------------------------------------------
# statistics and the reading rules
# ---------------------------------------------------------------------------

def test_flat_rule_of_decision_one():
    assert ep.flat_rule(dict(mean=0.05, ci_lo=-0.2, ci_hi=0.3))[0] == "flat"
    v, note = ep.flat_rule(dict(mean=0.18, ci_lo=-0.1, ci_hi=0.4))
    assert v == "flat" and "0.10R" in note
    assert ep.flat_rule(dict(mean=0.40, ci_lo=0.1, ci_hi=0.7))[0] == "rising"
    assert (ep.flat_rule(dict(mean=0.40, ci_lo=-0.1, ci_hi=0.9))[0]
            == "cannot decide")
    assert ep.flat_rule(None)[0] == "indeterminate"


def test_cluster_bootstrap_is_deterministic_and_brackets_the_mean():
    rng = np.random.default_rng(1)
    vals = rng.normal(0.5, 1.0, 120)
    clusters = [f"d{i // 3}" for i in range(120)]
    a = ep.cluster_bootstrap_mean(vals, clusters, reps=2000)
    b = ep.cluster_bootstrap_mean(vals, clusters, reps=2000)
    assert a == b
    assert a["mean"] == pytest.approx(vals.mean())
    assert a["ci_lo"] < a["mean"] < a["ci_hi"]
    assert ep.cluster_bootstrap_mean([], [], reps=10) is None


def test_cluster_bootstrap_diff_sees_a_real_difference():
    a = np.full(60, 1.0) + np.arange(60) * 0.001
    b = np.full(60, 0.0) + np.arange(60) * 0.001
    ca = [f"d{i}" for i in range(60)]
    cb = [f"d{i + 60}" for i in range(60)]
    d = ep.cluster_bootstrap_diff(a, ca, b, cb, reps=500)
    assert d["mean"] == pytest.approx(1.0, abs=1e-6)
    assert d["ci_lo"] > 0.9 and d["p_le_0"] == 0.0


def test_null_placements_sit_on_other_days_at_the_same_time_of_day():
    run = synthetic_run(splice=False)
    i0 = run.bar_index(int(ts(10, "01:10").value))
    rng = np.random.default_rng(3)
    pl = ep.null_placements(run, i0, "short", 2.6, 40, rng, tod_minutes=30)
    assert len(pl) == 40
    # every placement carries the fixed horizon list
    assert all(set(p.keys()) == set(ep.H_NAMES) for p in pl)


def test_combine_applies_the_agreement_rules():
    nr = dict(verdict="not rejected")
    assert ep.combine([nr, nr, nr, nr]) == "not rejected"
    assert ep.combine([nr, nr, dict(verdict="dimmed"), nr]) == "dimmed"
    assert ep.combine([nr, dict(verdict="rejected (H2)"), nr, nr]).startswith(
        "indeterminate")


# ---------------------------------------------------------------------------
# the real blotter (slow, opt in)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("EXIT_SLOW") != "1",
                    reason="set EXIT_SLOW=1 to load every market's bars")
def test_every_published_trade_reproduces_its_booking():
    samples, _anchors, _rule1, _b, _m = ep.load_samples()
    trades = samples["variant 2 (published)"]
    keys = {t["market"] for t in trades}
    runs, ticks, _exc = ep.load_runs(keys)
    rows, failures = ep.profile_rows(trades, runs, ticks)
    assert failures == [], failures
    assert len(rows) == len(trades)
