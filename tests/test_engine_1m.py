"""Tests for engine_1m v2 - the audit-decision mechanics (2026-08-06):
market-order entry at the level touch with 2 ticks slippage, R denominated
level-to-ladder-stop, ladder-anchored stop (5th else 4th reversal), the
tighten and allow_pre_activation dials. Synthetic minute bars; prices in
gold-like terms, tick 0.1 (slippage = 0.2)."""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine_1m import Day, LevelsFile, run_market  # noqa: E402

TICK = 0.1


def ts(day, hhmm):
    return pd.Timestamp(f"2026-06-{day:02d} {hhmm}", tz="UTC")


def bar(t, o, h, l, c):
    return (t, o, h, l, c)


def flat_bars(day, start_hhmm, n, price):
    """n identical doji minutes starting at start_hhmm."""
    h0, m0 = (int(x) for x in start_hhmm.split(":"))
    out = []
    for i in range(n):
        m = m0 + i
        out.append(bar(ts(day, f"{h0 + m // 60:02d}:{m % 60:02d}"),
                       price, price, price, price))
    return out


def file_at(day_pub, activation, bull, bear, prev_close):
    return LevelsFile(publish_date=date(2026, 6, day_pub),
                      activation_ts=activation, bull=sorted(bull),
                      bear=sorted(bear), prev_close=prev_close)


# Five-level ladder above prev_close 99.0: first 100.0, second 100.5,
# stop anchor = 5th (102.5) -> ladder stop 102.6, rpu = 2.6 from first.
BULL5 = [100.0, 100.5, 101.0, 101.5, 102.5]


def base_file(day_pub=9, activation=None, bull=None, bear=None):
    return file_at(day_pub, activation or ts(10, "00:00"),
                   bull=bull or BULL5, bear=bear or [90.0], prev_close=99.0)


def short_entry_day(day=10):
    """Open 99.5 (below second 100.5); the rally bar tests four reversals
    (high 102) and closes back above the first, so it does NOT enter (the
    arming bar needs its close back beyond the level); the next bar's low
    touches 100 -> market order, entry 100 - 2 ticks = 99.8."""
    return [
        bar(ts(day, "01:00"), 99.5, 99.5, 99.5, 99.5),
        bar(ts(day, "02:00"), 99.5, 102.0, 99.5, 101.5),
        bar(ts(day, "03:00"), 101.5, 101.5, 99.8, 99.8),
    ]


def test_basic_short_slipped_entry_ladder_stop_close1():
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=short_entry_day() + flat_bars(10, "04:00", 3, 99.7),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 11), contract="GCQ6",
            bars=flat_bars(11, "01:00", 3, 98.0),
            settle_ts=ts(11, "17:30"), settle_price=98.0),
    ]
    trades, summary = run_market(days, [base_file()], TICK)
    assert summary["trades"] == 1
    t = trades[0]
    assert t["side"] == "short"
    assert "03:00" in t["entry_ts"]          # not the arming bar
    assert abs(t["entry"] - 99.8) < 1e-9     # 100.0 - 2 ticks slippage
    assert abs(t["stop"] - 102.6) < 1e-9     # 5th reversal 102.5 + tick
    assert abs(t["rpu"] - 2.6) < 1e-9        # first->stop, NOT entry->stop
    assert abs(t["stop_tightened"] - 102.1) < 1e-9   # day high 102 + tick
    assert t["reason"] == "close1" and t["exit"] == 98.0
    assert abs(t["gross_r"] - (99.8 - 98.0) / 2.6) < 1e-3


def test_four_level_ladder_anchors_stop_on_fourth():
    f = base_file(bull=[100.0, 100.5, 101.0, 101.5])   # no 5th
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=short_entry_day() + flat_bars(10, "04:00", 3, 99.7),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 11), contract="GCQ6",
            bars=flat_bars(11, "01:00", 3, 98.0),
            settle_ts=ts(11, "17:30"), settle_price=98.0),
    ]
    trades, _ = run_market(days, [f], TICK)
    assert len(trades) == 1
    assert abs(trades[0]["stop"] - 101.6) < 1e-9   # 4th (101.5) + tick


def test_three_level_ladder_is_no_setup():
    f = base_file(bull=[100.0, 100.5, 101.0])      # ladder < MIN_LADDER
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=short_entry_day() + flat_bars(10, "04:00", 3, 99.7),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
    ]
    trades, _ = run_market(days, [f], TICK)
    assert trades == []


def test_no_confirm_exit_at_entry_day_settlement():
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=short_entry_day() + flat_bars(10, "04:00", 3, 100.0),
            settle_ts=ts(10, "17:30"), settle_price=100.0),  # not 1 tick below
    ]
    trades, _ = run_market(days, [base_file()], TICK)
    assert len(trades) == 1
    assert trades[0]["reason"] == "no_confirm"
    assert trades[0]["exit"] == 100.0


def test_update_switch_enables_trade_from_pre_update_extremes():
    """The canonical example: the old ladder is far away; the running high
    102 was made BEFORE the new ladder arrives at 07:35; once the new
    ladder is active the next touch of its first reversal enters."""
    old = file_at(8, ts(9, "00:00"), bull=[110.0, 111.0, 112.0, 113.0],
                  bear=[90.0], prev_close=99.0)
    new = file_at(9, ts(10, "07:35"), bull=BULL5,
                  bear=[90.0], prev_close=99.0)
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=[
                bar(ts(10, "01:00"), 99.5, 99.5, 99.5, 99.5),
                bar(ts(10, "02:00"), 99.5, 102.0, 99.5, 101.5),  # pre-update
                bar(ts(10, "08:00"), 101.5, 101.5, 99.8, 99.8),  # post-update
            ] + flat_bars(10, "09:00", 3, 99.7),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 11), contract="GCQ6",
            bars=flat_bars(11, "01:00", 3, 98.0),
            settle_ts=ts(11, "17:30"), settle_price=98.0),
    ]
    trades, _ = run_market(days, [old, new], TICK)
    assert len(trades) == 1
    assert "08:00" in trades[0]["entry_ts"]
    assert abs(trades[0]["entry"] - 99.8) < 1e-9


def test_gap_through_level_fills_from_first_available_price():
    """Armed the bar before; the next bar OPENS below the first reversal
    (price jumped the level) -> the market order fills from the open, not
    the level: entry = open - 2 ticks."""
    bars = [
        bar(ts(10, "01:00"), 99.5, 99.5, 99.5, 99.5),
        bar(ts(10, "02:00"), 99.5, 102.0, 100.2, 101.5),  # arms, low ABOVE first
        bar(ts(10, "03:00"), 99.7, 99.7, 99.7, 99.7),     # gaps under 100
    ]
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=bars + flat_bars(10, "04:00", 3, 99.6),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 11), contract="GCQ6",
            bars=flat_bars(11, "01:00", 3, 98.0),
            settle_ts=ts(11, "17:30"), settle_price=98.0),
    ]
    trades, _ = run_market(days, [base_file()], TICK)
    assert len(trades) == 1
    assert abs(trades[0]["entry"] - (99.7 - 0.2)) < 1e-9


def test_no_opposite_reversals_is_still_a_trade():
    """Rule 3 is REMOVED (Lode, 2026-08-06): a file with a full ladder and
    NO opposite-side reversals - the GC 2026-02-02 configuration - trades
    normally; there is no room requirement and no existence requirement."""
    f = base_file(bear=[])
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=short_entry_day() + flat_bars(10, "04:00", 3, 99.7),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 11), contract="GCQ6",
            bars=flat_bars(11, "01:00", 3, 98.0),
            settle_ts=ts(11, "17:30"), settle_price=98.0),
    ]
    trades, _ = run_market(days, [f], TICK)
    assert len(trades) == 1
    assert "03:00" in trades[0]["entry_ts"]
    assert trades[0]["reason"] == "close1"


def test_rule2_refusal_blocks_day_for_that_ladder():
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=[
                bar(ts(10, "01:00"), 100.5, 100.5, 100.5, 100.5),  # open = second
                bar(ts(10, "02:00"), 100.5, 102.0, 100.4, 101.5),
                bar(ts(10, "03:00"), 101.5, 101.5, 99.8, 99.8),
            ],
            settle_ts=ts(10, "17:30"), settle_price=99.5),
    ]
    trades, _ = run_market(days, [base_file()], TICK)
    assert trades == []


def test_same_day_reentry_keeps_ladder_stop():
    """Stopped out at the ladder stop; price returns through the level and
    re-enters the same day. The ladder stop does NOT widen (unlike the old
    extreme-multiple stop); with rule 3 removed only a fresh trigger gates
    the re-entry."""
    deep_room = base_file(bear=[70.0])
    bars = short_entry_day()                                   # entry 03:00
    bars += [
        bar(ts(10, "04:00"), 100.9, 102.7, 100.9, 102.6),      # takes the stop
        bar(ts(10, "05:00"), 102.6, 102.6, 99.9, 99.9),        # returns, touch
    ]
    bars += flat_bars(10, "06:00", 3, 99.7)
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6", bars=bars,
            settle_ts=ts(10, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 11), contract="GCQ6",
            bars=flat_bars(11, "01:00", 3, 98.0),
            settle_ts=ts(11, "17:30"), settle_price=98.0),
    ]
    trades, _ = run_market(days, [deep_room], TICK)
    assert len(trades) == 2
    first, second = trades
    assert first["reason"] == "stop" and abs(first["exit"] - 102.6) < 1e-9
    # a stop-out costs MORE than 1R now: slippage widened entry-to-stop
    assert first["gross_r"] < -1.0
    assert abs(second["entry"] - 99.8) < 1e-9
    assert abs(second["stop"] - first["stop"]) < 1e-9   # same ladder stop
    # day extreme 102.7 + tick is NOT tighter than 102.6 -> no tightening
    assert second["stop_tightened"] is None
    assert second["reason"] == "close1"


def test_moved_first_reversal_tightens_confirmation():
    """Entry on the overnight ladder (first = 100.0); the 07:35 update
    moves the first reversal DOWN to 99.4. Settlement at 99.6 is 1+ tick
    below the entry-time first but NOT below the new first -> no_confirm."""
    old = base_file(day_pub=8, activation=ts(9, "00:00"))
    new = file_at(9, ts(10, "07:35"), bull=[99.4, 100.5, 101.0, 101.5],
                  bear=[90.0], prev_close=99.0)
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=short_entry_day() + flat_bars(10, "08:00", 3, 99.6),
            settle_ts=ts(10, "17:30"), settle_price=99.6),
    ]
    trades, _ = run_market(days, [old, new], TICK)
    assert len(trades) == 1
    assert trades[0]["reason"] == "no_confirm"


def test_no_entries_after_settlement():
    bars = [
        bar(ts(10, "01:00"), 99.5, 99.5, 99.5, 99.5),
        bar(ts(10, "02:00"), 99.5, 102.0, 99.5, 101.5),
        bar(ts(10, "18:00"), 101.5, 101.5, 99.8, 99.8),  # after settle_ts
    ]
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6", bars=bars,
            settle_ts=ts(10, "17:30"), settle_price=101.0),
    ]
    trades, _ = run_market(days, [base_file()], TICK)
    assert trades == []


def test_entries_excluded_day_still_manages_position():
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=short_entry_day() + flat_bars(10, "04:00", 3, 99.7),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 11), contract="GCQ6",
            bars=[bar(ts(11, "01:00"), 99.5, 106.5, 99.5, 106.0)],
            settle_ts=ts(11, "17:30"), settle_price=106.0,
            entries_allowed=False),
    ]
    trades, _ = run_market(days, [base_file()], TICK)
    assert len(trades) == 1
    assert trades[0]["reason"] == "stop"


def test_tighten_dial_on_and_off():
    """Day 2 rallies to 102.2: with tightening the stop moved to the day
    extreme + tick (102.1) at the entry-day settlement and the trade stops
    for a sub-1R loss; without it the ladder stop 102.6 holds -> close1."""
    def make_days():
        return [
            Day(date=date(2026, 6, 10), contract="GCQ6",
                bars=short_entry_day() + flat_bars(10, "04:00", 3, 99.7),
                settle_ts=ts(10, "17:30"), settle_price=99.5),
            Day(date=date(2026, 6, 11), contract="GCQ6",
                bars=[bar(ts(11, "01:00"), 99.5, 102.2, 99.5, 102.0)],
                settle_ts=ts(11, "17:30"), settle_price=102.0),
        ]
    on, _ = run_market(make_days(), [base_file()], TICK, tighten=True)
    off, _ = run_market(make_days(), [base_file()], TICK, tighten=False)
    assert on[0]["reason"] == "stop"
    assert abs(on[0]["exit"] - 102.1) < 1e-9
    assert -1.0 < on[0]["gross_r"] < -0.5      # (99.8-102.1)/2.6
    assert off[0]["reason"] == "close1"
    assert off[0]["stop_tightened"] is None
    assert abs(off[0]["exit"] - 102.0) < 1e-9


def test_window_dial_blocks_stale_file_entries():
    """allow_pre_activation=False: entries need the day's OWN update. The
    03:00 touch runs on the previous day's file -> blocked; after the
    07:35 activation the 08:00 touch enters."""
    file_a = base_file(day_pub=8, activation=ts(9, "07:35"))
    file_b = base_file(day_pub=9, activation=ts(10, "07:35"))
    def make_days():
        return [
            Day(date=date(2026, 6, 9), contract="GCQ6",
                bars=flat_bars(9, "01:00", 3, 99.5),
                settle_ts=ts(9, "17:30"), settle_price=99.5),
            Day(date=date(2026, 6, 10), contract="GCQ6",
                bars=short_entry_day() + [
                    bar(ts(10, "08:00"), 99.8, 101.0, 99.8, 99.8),
                ] + flat_bars(10, "09:00", 3, 99.7),
                settle_ts=ts(10, "17:30"), settle_price=99.5),
            Day(date=date(2026, 6, 11), contract="GCQ6",
                bars=flat_bars(11, "01:00", 3, 98.0),
                settle_ts=ts(11, "17:30"), settle_price=98.0),
        ]
    blocked, _ = run_market(make_days(), [file_a, file_b], TICK,
                            allow_pre_activation=False)
    allowed, _ = run_market(make_days(), [file_a, file_b], TICK,
                            allow_pre_activation=True)
    assert len(blocked) == 1 and "08:00" in blocked[0]["entry_ts"]
    assert len(allowed) == 1 and "03:00" in allowed[0]["entry_ts"]


def test_window_dial_monday_trades_from_open():
    """Monday's update is Saturday's landing (publish date = Friday, the
    data date). Blocking pre-activation entries must NOT block Monday:
    the file's publish date equals the previous trading date."""
    monday_update = base_file(day_pub=5, activation=ts(6, "07:35"))
    days = [
        Day(date=date(2026, 6, 5), contract="GCQ6",
            bars=flat_bars(5, "01:00", 3, 99.5),
            settle_ts=ts(5, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 8), contract="GCQ6",   # Monday
            bars=short_entry_day(day=8) + flat_bars(8, "04:00", 3, 99.7),
            settle_ts=ts(8, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 9), contract="GCQ6",
            bars=flat_bars(9, "01:00", 3, 98.0),
            settle_ts=ts(9, "17:30"), settle_price=98.0),
    ]
    trades, _ = run_market(days, [monday_update], TICK,
                           allow_pre_activation=False)
    assert len(trades) == 1
    assert "03:00" in trades[0]["entry_ts"]
