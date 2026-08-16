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
from engine_1m import (  # noqa: E402
    Day, LevelsFile, ratio_series, run_market)

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
    the re-entry.

    The mechanic still exists, but the published baseline shuts it off
    with the session lockout, so this test asks for it explicitly."""
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
    trades, _ = run_market(days, [deep_room], TICK,
                           max_entries_per_session=None)
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


def test_confirm_dial_off_carries_the_unconfirmed_trade():
    """The entry day settles AT the first reversal, so the clause aborts
    the trade there. With confirm=False there is no such test: the trade
    is carried to the next day's settlement with the stop live."""
    def make_days():
        return [
            Day(date=date(2026, 6, 10), contract="GCQ6",
                bars=short_entry_day() + flat_bars(10, "04:00", 3, 100.0),
                settle_ts=ts(10, "17:30"), settle_price=100.0),
            Day(date=date(2026, 6, 11), contract="GCQ6",
                bars=flat_bars(11, "01:00", 3, 98.0),
                settle_ts=ts(11, "17:30"), settle_price=98.0),
        ]
    on, _ = run_market(make_days(), [base_file()], TICK, confirm=True)
    off, _ = run_market(make_days(), [base_file()], TICK, confirm=False)
    assert len(on) == 1 and on[0]["reason"] == "no_confirm"
    assert on[0]["exit"] == 100.0 and on[0]["net_r"] < 0
    assert len(off) == 1 and off[0]["reason"] == "close1"
    assert off[0]["exit"] == 98.0 and off[0]["net_r"] > 0


def test_stop_mode_widens_to_a_session_extreme_beyond_the_ladder():
    """The USO case in miniature: the session prints 103.0 before the
    trade exists, past the ladder stop at 102.6. ladder_or_extreme moves
    the stop to 103.1 and R with it (3.1 instead of 2.6), so the SAME
    price move books fewer R."""
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=[bar(ts(10, "01:00"), 99.5, 99.5, 99.5, 99.5),
                  bar(ts(10, "02:00"), 99.5, 103.0, 99.5, 102.5),
                  bar(ts(10, "03:00"), 102.5, 102.5, 99.8, 99.8)]
                 + flat_bars(10, "04:00", 3, 99.7),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 11), contract="GCQ6",
            bars=flat_bars(11, "01:00", 3, 98.0),
            settle_ts=ts(11, "17:30"), settle_price=98.0),
    ]
    ladder, _ = run_market(days, [base_file()], TICK, stop_mode="ladder")
    hybrid, _ = run_market(days, [base_file()], TICK,
                           stop_mode="ladder_or_extreme")
    assert abs(ladder[0]["stop"] - 102.6) < 1e-9
    assert abs(ladder[0]["rpu"] - 2.6) < 1e-9
    assert abs(hybrid[0]["stop"] - 103.1) < 1e-9
    assert abs(hybrid[0]["rpu"] - 3.1) < 1e-9
    assert hybrid[0]["exit"] == ladder[0]["exit"] == 98.0
    assert hybrid[0]["gross_r"] < ladder[0]["gross_r"]


def test_stop_mode_keeps_the_ladder_when_the_extreme_is_inside_it():
    """Running high 102.0 against a ladder stop of 102.6: the hybrid must
    not TIGHTEN, while plain extreme deliberately does (102.1)."""
    def make_days():
        return [
            Day(date=date(2026, 6, 10), contract="GCQ6",
                bars=short_entry_day() + flat_bars(10, "04:00", 3, 99.7),
                settle_ts=ts(10, "17:30"), settle_price=99.5),
            Day(date=date(2026, 6, 11), contract="GCQ6",
                bars=flat_bars(11, "01:00", 3, 98.0),
                settle_ts=ts(11, "17:30"), settle_price=98.0),
        ]
    hybrid, _ = run_market(make_days(), [base_file()], TICK,
                           stop_mode="ladder_or_extreme")
    extreme, _ = run_market(make_days(), [base_file()], TICK,
                            stop_mode="extreme")
    assert abs(hybrid[0]["stop"] - 102.6) < 1e-9
    assert abs(extreme[0]["stop"] - 102.1) < 1e-9
    assert abs(extreme[0]["rpu"] - 2.1) < 1e-9


def test_unknown_stop_mode_raises():
    import pytest
    with pytest.raises(ValueError):
        run_market([], [], TICK, stop_mode="cluster")


def reentry_day_bars():
    """Entry 03:00, stopped 04:00, price returns and touches again 05:00."""
    bars = short_entry_day()
    bars += [
        bar(ts(10, "04:00"), 100.9, 102.7, 100.9, 102.6),      # takes the stop
        bar(ts(10, "05:00"), 102.6, 102.6, 99.9, 99.9),        # returns, touch
    ]
    return bars + flat_bars(10, "06:00", 3, 99.7)


def test_session_lockout_blocks_the_second_entry():
    """The default: one entry per market-session. The re-entry that the
    test above books is simply never taken, and the day ends flat rather
    than re-attacking the level that just stopped us."""
    deep_room = base_file(bear=[70.0])
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6", bars=reentry_day_bars(),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 11), contract="GCQ6",
            bars=flat_bars(11, "01:00", 3, 98.0),
            settle_ts=ts(11, "17:30"), settle_price=98.0),
    ]
    one, _ = run_market(days, [deep_room], TICK)                 # default 1
    two, _ = run_market(days, [deep_room], TICK,
                        max_entries_per_session=2)
    off, _ = run_market(days, [deep_room], TICK,
                        max_entries_per_session=None)
    assert len(one) == 1 and one[0]["reason"] == "stop"
    assert len(two) == 2 and len(off) == 2


def test_lockout_expires_at_the_session_boundary():
    """Stopped out today, a fresh trigger TOMORROW still trades: the
    lockout is a session rule, and returning to a level on a later day is
    what the research says pays."""
    deep_room = base_file(bear=[70.0])
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6", bars=reentry_day_bars(),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 11), contract="GCQ6",
            bars=short_entry_day(day=11) + flat_bars(11, "06:00", 2, 99.7),
            settle_ts=ts(11, "17:30"), settle_price=99.0),
        Day(date=date(2026, 6, 12), contract="GCQ6",
            bars=flat_bars(12, "01:00", 3, 98.0),
            settle_ts=ts(12, "17:30"), settle_price=98.0),
    ]
    trades, _ = run_market(days, [deep_room], TICK)
    assert len(trades) == 2
    assert trades[0]["entry_date"] == "2026-06-10"
    assert trades[1]["entry_date"] == "2026-06-11"


def test_carried_position_stopped_intraday_leaves_the_allowance_intact():
    """THE 19R DISTINCTION: the lockout counts ENTRIES, not exits. A
    position carried in from the previous session and stopped this morning
    does not spend today's allowance, so the fresh signal still trades."""
    deep_room = base_file(bear=[70.0])
    days = [
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=short_entry_day() + flat_bars(10, "04:00", 2, 99.7),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
        # Day 2 takes out yesterday's stop on its first bar and then sets
        # up afresh. That bar has to OPEN below the second reversal or
        # rule 2 refuses the whole session and the lockout never gets a
        # say - which is what the first draft of this test did.
        Day(date=date(2026, 6, 11), contract="GCQ6",
            bars=[bar(ts(11, "00:30"), 99.5, 102.7, 99.5, 102.6)]
                 + short_entry_day(day=11) + flat_bars(11, "06:00", 2, 99.7),
            settle_ts=ts(11, "17:30"), settle_price=99.0),
        Day(date=date(2026, 6, 12), contract="GCQ6",
            bars=flat_bars(12, "01:00", 3, 98.0),
            settle_ts=ts(12, "17:30"), settle_price=98.0),
    ]
    trades, _ = run_market(days, [deep_room], TICK)              # default 1
    assert len(trades) == 2
    assert trades[0]["reason"] == "stop"
    assert trades[0]["exit_ts"].startswith("2026-06-11")   # stopped today
    assert trades[1]["entry_date"] == "2026-06-11"         # and still traded


# --- ratio_series: the %R/24hRange pane's data -----------------------
# The pane exists to show the minutes the dial REFUSED, which the blotter
# cannot record (a refused entry leaves no trade). That only helps if the
# number under the chart is the same number the engine judged, so the
# binding test is AGREEMENT with run_market at the minutes both can see.


def oscillating_bars(day, start_hhmm, n, lo, hi):
    """n minutes alternating lo/hi, so the trailing window has a RANGE.
    flat_bars gives a zero range, where the ratio is undefined by rule."""
    h0, m0 = (int(x) for x in start_hhmm.split(":"))
    out = []
    for i in range(n):
        m = m0 + i
        t = ts(day, f"{h0 + m // 60:02d}:{m % 60:02d}")
        p = lo if i % 2 else hi
        out.append(bar(t, p, p, p, p))
    return out


def history_then_entry():
    """A day of 120 bars (so the window is judgeable) then the standard
    short setup the day after."""
    return [
        Day(date=date(2026, 6, 9), contract="GCQ6",
            bars=oscillating_bars(9, "03:00", 120, 98.0, 100.0),
            settle_ts=ts(9, "17:30"), settle_price=99.0),
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=short_entry_day() + flat_bars(10, "04:00", 3, 99.7),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
        Day(date=date(2026, 6, 11), contract="GCQ6",
            bars=flat_bars(11, "01:00", 3, 98.0),
            settle_ts=ts(11, "17:30"), settle_price=98.0),
    ]


def value_at(series, when, line="main", side="bull"):
    """The series' value at a timestamp: change points hold until the
    next one, exactly as the chart expands them. A number is a ratio; a
    string is the reason there is a gap. `side` picks the reversal set -
    "bull" is the ladder above prev_close, which is the SHORT setup."""
    cur = None
    for t, v in series[side][line]:
        if t > pd.Timestamp(when).timestamp():
            break
        cur = v
    return cur


def ratios(series, line="main", side="bull"):
    return [v for _t, v in series[side][line] if isinstance(v, float)]


def test_ratio_series_agrees_with_the_trade_it_judged():
    days = history_then_entry()
    trades, _ = run_market(days, [base_file()], TICK)
    assert len(trades) == 1 and trades[0]["rpu_range_ratio"] is not None
    ser = ratio_series(days, [base_file()], TICK)
    assert value_at(ser, trades[0]["entry_ts"]) == \
        trades[0]["rpu_range_ratio"]


def test_ratio_series_reports_the_minutes_no_trade_records():
    """The refusal case: with the band cutting this setup out there is no
    trade at all, and the series still carries the number that refused
    it. This is the whole reason the function exists."""
    days = history_then_entry()
    trades, summary = run_market(days, [base_file()], TICK,
                                 max_rpu_range_ratio=0.10)
    assert trades == [] and summary["refused_wide"] >= 1
    ser = ratio_series(days, [base_file()], TICK)
    assert ratios(ser) and max(ratios(ser)) > 0.10


def test_ratio_series_gaps_where_the_dial_cannot_judge():
    """Fewer than MIN_RANGE_BARS in the trailing window -> no ratio, the
    weekend-open case where the dial abstains and the entry goes through
    unjudged. A gap in the line, not a zero."""
    days = history_then_entry()[1:]          # drop the 120-bar history
    trades, _ = run_market(days, [base_file()], TICK)
    assert len(trades) == 1 and trades[0]["rpu_range_ratio"] is None
    ser = ratio_series(days, [base_file()], TICK)
    assert not ratios(ser)
    assert value_at(ser, trades[0]["entry_ts"]) == "short-window"


def test_ratio_series_follows_the_stop_anchor():
    """The stop mode is the only dial the number depends on, which is why
    three series cover all 30 matrix cells. The session extreme here (102)
    is INSIDE the ladder stop (102.6), so `extreme` is the tighter one."""
    days = history_then_entry()
    ladder = ratio_series(days, [base_file()], TICK, stop_mode="ladder")
    wick = ratio_series(days, [base_file()], TICK, stop_mode="extreme")
    assert max(ratios(wick)) < max(ratios(ladder))


def test_ratio_series_rejects_an_unknown_stop_mode():
    import pytest
    with pytest.raises(ValueError):
        ratio_series([], [], TICK, stop_mode="nonsense")


def test_ratio_series_gates_what_the_band_never_got_to_vote_on():
    """A NUMBER means the band was the deciding vote. The variant-blind
    gates come first and leave a REASON, so a minute no trade could have
    happened in cannot show a legal-looking green value (PA 2026-08-11
    05:27 carried 0.4706 with no active file and rule 2 against it)."""
    days = history_then_entry()
    f = base_file()
    ser = ratio_series(days, [f], TICK)
    # Before the file activates (ts(10, "00:00")) there is no ratio.
    assert value_at(ser, ts(9, "04:00")) == "no-file"
    # Rule 2: a session opening at/above the second reversal is shut for
    # that ladder all day, so the whole session is a gap and not a value.
    gap = [Day(date=date(2026, 6, 9), contract="GCQ6",
               bars=oscillating_bars(9, "03:00", 120, 98.0, 100.0),
               settle_ts=ts(9, "17:30"), settle_price=99.0),
           Day(date=date(2026, 6, 10), contract="GCQ6",
               bars=[bar(ts(10, "01:00"), 101.0, 101.0, 101.0, 101.0)]
                    + short_entry_day(),
               settle_ts=ts(10, "17:30"), settle_price=99.5)]
    trades, _ = run_market(gap, [f], TICK)
    assert trades == []                       # open 101.0 >= second 100.5
    s2 = ratio_series(gap, [f], TICK)
    assert value_at(s2, ts(10, "03:00")) == "rule2"
    assert not ratios(s2)


def test_ratio_series_gaps_a_day_that_takes_no_entries():
    days = history_then_entry()
    days[1].entries_allowed = False
    ser = ratio_series(days, [base_file()], TICK)
    assert value_at(ser, ts(10, "03:00")) == "no-entries"


def test_ratio_series_draws_the_old_levels_as_a_second_line():
    """A session opens before its own levels do, and the pane shows both
    answers there (Lode, 2026-08-16): `main` from the session's OWN update
    across the whole session, `prev` from the levels actually live at that
    minute, emitted ONLY until the update activates. Where `prev` runs is
    exactly the pre-update window."""
    old = file_at(8, ts(9, "00:00"), bull=[100.0, 100.5, 101.0, 101.5,
                                           104.5], bear=[90.0],
                  prev_close=99.0)
    new = file_at(9, ts(10, "06:00"), bull=BULL5, bear=[90.0],
                  prev_close=99.0)
    days = [
        # The history sits in the EVENING so it is still inside the
        # trailing 24h at 07:00 the next morning; at 03:00 it would be
        # pruned and both lines would read short-window instead.
        Day(date=date(2026, 6, 9), contract="GCQ6",
            bars=oscillating_bars(9, "20:00", 120, 98.0, 100.0),
            settle_ts=ts(9, "23:00"), settle_price=99.0),
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=short_entry_day() + flat_bars(10, "07:00", 3, 99.7),
            settle_ts=ts(10, "17:30"), settle_price=99.5),
    ]
    ser = ratio_series(days, [old, new], TICK)
    # 03:00 is before the 06:00 activation: both lines, and they differ
    # because the old ladder's 5th reversal sits at 104.5, not 102.5.
    before_main = value_at(ser, ts(10, "03:00"))
    before_prev = value_at(ser, ts(10, "03:00"), line="prev")
    assert isinstance(before_main, float) and isinstance(before_prev, float)
    assert before_prev > before_main
    # After the update the blue line stops: there is nothing to reference.
    assert value_at(ser, ts(10, "07:00"), line="prev") is None
    assert isinstance(value_at(ser, ts(10, "07:00")), float)


def test_ratio_series_has_no_second_line_when_no_update_lands():
    """No update today (charter's amber 'no Socrates update' stretches):
    the live file IS the session's own file, so there is one line."""
    days = history_then_entry()
    ser = ratio_series(days, [base_file()], TICK)
    assert all(v is None for _t, v in ser["bull"]["prev"])


def test_ratio_series_keeps_the_two_reversal_sets_apart():
    """PA 2026-05-04, the square wave: price sat between a bull ladder 64
    points above and a bear ladder 80 below, and ONE line had to answer
    for both, so something had to choose - and every rule for choosing is
    discontinuous somewhere. Choosing the nearest first reversal flipped
    the whole numerator each time price crossed the midpoint, between
    1.273 and 3.764 (Lode, 2026-08-16). A series PER SIDE removes the
    choice: each is constant while its own ladder is, whatever price
    does in between."""
    f = file_at(9, ts(10, "00:00"),
                bull=[160.0, 162.0, 163.0, 164.0, 165.0],   # rpu 5.1
                bear=[ 40.0,  30.0,  25.0,  20.0,  10.0],   # rpu 30.1
                prev_close=99.0)
    # Price oscillates across the midpoint of the two first reversals
    # (100.0), which is exactly what the nearest-first rule flipped on.
    mid = (160.0 + 40.0) / 2
    bars = []
    for i in range(180):
        p = mid + (6.0 if i % 2 else -6.0)
        h0, m0 = 3, i
        bars.append(bar(ts(10, f"{h0 + m0 // 60:02d}:{m0 % 60:02d}"),
                        p, p + 1, p - 1, p))
    days = [Day(date=date(2026, 6, 10), contract="GCQ6", bars=bars,
                settle_ts=ts(10, "17:30"), settle_price=mid)]
    ser = ratio_series(days, [f], TICK)
    bull, bear = ratios(ser, side="bull"), ratios(ser, side="bear")
    assert bull and bear, "expected a line on each side, not a gap"
    # One ladder is ~6x the other. Each side stays on its own ladder, so
    # neither line can carry the other's number and neither can step.
    assert max(bull) / min(bull) < 1.5
    assert max(bear) / min(bear) < 1.5
    assert min(bear) > max(bull) * 3


def test_ratio_series_bull_is_the_short_ladder_and_bear_the_long():
    """The panes are named for the REVERSAL SET, the engine for the setup
    built on it. Getting these crossed would put every number under the
    wrong pane, so it is pinned: bull = above prev_close = SHORT."""
    f = file_at(9, ts(10, "00:00"),
                bull=[100.0, 100.5, 101.0, 101.5, 102.5],   # rpu 2.6
                bear=[90.0, 85.0, 80.0, 75.0, 60.0],        # rpu 30.1
                prev_close=99.0)
    days = [
        Day(date=date(2026, 6, 9), contract="GCQ6",
            bars=oscillating_bars(9, "20:00", 120, 98.0, 100.0),
            settle_ts=ts(9, "23:00"), settle_price=99.0),
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=flat_bars(10, "01:00", 30, 99.0),
            settle_ts=ts(10, "17:30"), settle_price=99.0),
    ]
    ser = ratio_series(days, [f], TICK)
    rng = 2.0                                  # the oscillation's range
    assert abs(value_at(ser, ts(10, "01:10"), side="bull")
               - 2.6 / rng) < 1e-3
    assert abs(value_at(ser, ts(10, "01:10"), side="bear")
               - 30.1 / rng) < 1e-3


def test_ratio_series_rule2_is_per_side():
    """Rule 2 shuts ONE ladder for the session. The other side's pane must
    keep its line - they are separate questions now."""
    f = file_at(9, ts(10, "00:00"),
                bull=[100.0, 100.5, 101.0, 101.5, 102.5],
                bear=[90.0, 85.0, 80.0, 75.0, 60.0], prev_close=99.0)
    days = [
        Day(date=date(2026, 6, 9), contract="GCQ6",
            bars=oscillating_bars(9, "20:00", 120, 98.0, 100.0),
            settle_ts=ts(9, "23:00"), settle_price=99.0),
        # Opens at 101.0, at/above the bull ladder's second (100.5), so
        # rule 2 refuses the SHORT side all day. The bear side is fine.
        Day(date=date(2026, 6, 10), contract="GCQ6",
            bars=flat_bars(10, "01:00", 30, 101.0),
            settle_ts=ts(10, "17:30"), settle_price=101.0),
    ]
    ser = ratio_series(days, [f], TICK)
    assert value_at(ser, ts(10, "01:10"), side="bull") == "rule2"
    assert isinstance(value_at(ser, ts(10, "01:10"), side="bear"), float)
    # RULE 2 STOPS THE TRADE, NOT THE MEASUREMENT (Lode, 2026-08-16): the
    # refused side still carries its ratio, in the line charter draws
    # purple, and it is the SAME number the band would have judged.
    # rpu 2.6 over a trailing range of 3.0 (the 98-100 history plus the
    # session's own flat 101.0 bars), the same arithmetic the band uses.
    r2 = value_at(ser, ts(10, "01:10"), line="rule2", side="bull")
    assert isinstance(r2, float) and abs(r2 - 2.6 / 3.0) < 1e-3
    # ... and the side that was NOT refused has no purple line at all.
    assert value_at(ser, ts(10, "01:10"), line="rule2", side="bear") is None
