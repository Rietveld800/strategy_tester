"""Tests for the market-day grid the equity and drawdown panes are drawn
on (Lode, 2026-08-18): `run_1m.calendar_union`, `market_day_grid`, `place`
and `carry_forward`.

The thing being pinned is that an equity curve is a STEP FUNCTION on the
days some market was open - flat while nothing closes, the whole move at
the exit, and carried on to the LAST market day rather than stopping at
the last trade. These are pure date and list operations, so they need no
bars and no engine pass.
"""

import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import run_1m  # noqa: E402


def d(day):
    return date(2026, 6, day)


def secs(day, hh=12):
    return int(datetime(2026, 6, day, hh, tzinfo=timezone.utc).timestamp())


# The universe's calendars do not agree: one market trades Monday to
# Friday, another is a frozen soft that stopped on the Wednesday, and a
# third opens on the Saturday.
MON_TO_FRI = [d(1), d(2), d(3), d(4), d(5)]
FROZEN = [d(1), d(2), d(3)]
WEEKEND = [d(6)]


def test_calendar_is_the_union_of_every_market_that_ran():
    cal = run_1m.calendar_union([MON_TO_FRI, FROZEN, WEEKEND])
    assert cal == [d(1), d(2), d(3), d(4), d(5), d(6)]


def test_calendar_union_of_nothing_is_empty():
    assert run_1m.calendar_union([]) == []
    assert run_1m.calendar_union([[], []]) == []


def test_grid_starts_one_market_day_before_the_first_entry():
    """The lead-in is a market day, not a calendar day: it is the plateau
    the line starts on, before the account had traded."""
    grid = run_1m.market_day_grid(MON_TO_FRI, d(3))
    assert grid == [d(2), d(3), d(4), d(5)]


def test_grid_takes_the_calendar_as_iso_strings_too():
    """It travels through the JSON as strings and comes back as dates."""
    iso = [x.isoformat() for x in MON_TO_FRI]
    assert run_1m.market_day_grid(iso, "2026-06-03 15:21:00+00:00") == [
        d(2), d(3), d(4), d(5)]


def test_grid_runs_to_the_last_market_day_not_the_last_trade():
    """The point of the whole exercise (Lode): the curve is as up to date
    as the data, so a fortnight with no trade is a flat fortnight."""
    curve = [(secs(2), 104_000.0)]          # one exit, on the Tuesday
    grid = run_1m.market_day_grid(MON_TO_FRI, d(1))
    out = run_1m.carry_forward(curve, grid)
    assert [x for x, _ in out] == MON_TO_FRI
    assert out[-1] == (d(5), 104_000.0)


def test_the_curve_is_flat_until_it_jumps():
    """Today $104,000 and tomorrow $108,000 is one flat day and one
    vertical, never a slope through the days between."""
    curve = [(secs(2), 104_000.0), (secs(5), 108_000.0)]
    out = run_1m.carry_forward(curve, run_1m.market_day_grid(MON_TO_FRI, d(1)))
    assert [v for _, v in out] == [100_000.0, 104_000.0, 104_000.0,
                                   104_000.0, 108_000.0]


def test_the_last_exit_of_a_day_is_that_day_s_balance():
    curve = [(secs(2, 9), 104_000.0), (secs(2, 18), 101_000.0)]
    out = run_1m.carry_forward(curve, run_1m.market_day_grid(MON_TO_FRI, d(1)))
    assert [v for _, v in out] == [100_000.0, 101_000.0, 101_000.0,
                                   101_000.0, 101_000.0]


def test_an_exit_off_the_calendar_lands_on_the_next_market_day():
    """A stop can trade at 23:30 UTC on a Sunday whose TRADING date is the
    Monday. The calendar holds trading dates, so that P&L has to move
    forward onto the Monday rather than fall off the curve."""
    sunday = int(datetime(2026, 6, 7, 23, 30,
                          tzinfo=timezone.utc).timestamp())
    grid = [d(5), d(8), d(9)]
    out = run_1m.carry_forward([(sunday, 97_000.0)], grid)
    assert out == [(d(5), 100_000.0), (d(8), 97_000.0), (d(9), 97_000.0)]


def test_nothing_a_replay_booked_falls_off_the_front_of_the_grid():
    grid = [d(4), d(5)]
    out = run_1m.carry_forward([(secs(1), 96_000.0)], grid)
    assert out == [(d(4), 96_000.0), (d(5), 96_000.0)]


def test_place_is_the_first_grid_day_at_or_after_the_date():
    grid = [d(1), d(4), d(8)]
    assert run_1m.place(d(1), grid) == 0
    assert run_1m.place(d(2), grid) == 1     # forward, never back
    assert run_1m.place(d(4), grid) == 1
    assert run_1m.place(d(9), grid) == 2     # clamped, not dropped


def test_grid_seconds_is_utc_midnight():
    assert run_1m.grid_seconds(d(3)) == int(
        datetime(2026, 6, 3, tzinfo=timezone.utc).timestamp())


def test_the_fallback_grid_is_calendar_days_and_stops_at_the_last_exit():
    """Only for a JSON written before the calendar existed. It is the old
    behaviour, weekends and all, and every caller says so on the console."""
    trades = [dict(entry_ts="2026-06-01 10:00:00+00:00",
                   exit_ts="2026-06-03 18:00:00+00:00")]
    assert run_1m.calendar_fallback(trades) == [d(1), d(2), d(3)]
    assert run_1m.calendar_fallback([]) == []
