"""The rung 6 tripwire: two bits out, nothing intermediate kept (live_engine,
ENGINE_ARCHITECTURE.md, Phase 2, 2026-09-08).

THE ANTI-PEEK INTERLOCK. The forward window of rung 6 is graded on data_center's
Parquet under this engine's own fill model, at a cadence fixed before the window
opened. Its hard stop - a forward drawdown beyond the ceiling - and its grading
condition - sixty forward trading days or thirty forward trades, whichever comes
second - both need the forward run computed continuously, and a person reading a
forward equity curve to do that would put a peek at the centre of the design.

So this job computes the forward run in memory and persists TWO BITS:

  tripped            forward drawdown has exceeded the ceiling (with the trip date)
  grading_reached    the grading condition has been met (with the date it was met)

and nothing else: no running R, no drawdown, no equity curve, no trade count, on no
output, in no log line. The series exists for the seconds of the run and is
discarded; on grading day the whole computation is rerun from the same Parquet,
which is why nothing needs keeping. The tests prove the output has exactly the
allowed keys and that nothing else was written.

THE WINDOW OPENS ON A DATE, OR IT IS CLOSED. `forward_window.json` beside this file
is the pre-registration as this job reads it: `opens_on`, null until
MARKET_SELECTION.md is dated (Lode's decision, the only item on the window's
critical path), and `markets`, the surviving traded set the window is judged on.
With no date the job reports the window closed and computes nothing.

Both bits are latched: once tripped, tripped stays; once reached, reached stays.
The trip date and the reached date are the only dates that leave this job.

    venv/Scripts/python.exe forward_tripwire.py            # compute, persist the bits
    venv/Scripts/python.exe forward_tripwire.py --status   # print the bits, compute nothing
"""

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WINDOW_FILE = HERE / "forward_window.json"
OUTPUT_FILE = HERE / "output" / "forward_tripwire.json"

#: The pre-registration this job serves (Phase 2). Editable only until the window
#: opens; the window file records the values in force on its opening day.
#: THE DECISION BEHIND EACH CONSTANT, cited (audit s.23, 2026-09-09): the cell is
#: variant 4 (lockout 1, hybrid stop, band 0.00-0.60), decided by Lode on 2026-09-09;
#: the ceiling is twice that cell's own max drawdown on the seventeen surviving
#: markets to 2026-08-18 under this module's replay (5.60%, run_1m.portfolio_replay,
#: computed 2026-09-09). The 8.9 written on 2026-09-08 was variant 5's drawdown
#: doubled and applied to a variant 4 run: a constant without a decision, the
#: near miss s.23 records. A constant here carries its decision or it is a guess.
VARIANT = "variant 4"
CEILING_DD_PCT = 11.2
GRADING_DAYS = 60
GRADING_TRADES = 30
#: The only keys the output may carry. The test holds the file to this set.
OUTPUT_KEYS = ("window_open", "opens_on", "tripped", "trip_date", "grading_reached",
               "reached_date", "computed_at", "variant", "ceiling_dd_pct",
               "grading_days", "grading_trades", "bars_through", "bars_fresh")


# ================================================================== the judges
def forward_trades(trades, opens_on: date):
    """Trades entered on or after the window's opening day, in entry order."""
    kept = [t for t in trades if date.fromisoformat(str(t["entry_date"])[:10]) >= opens_on]
    return sorted(kept, key=lambda t: str(t["entry_ts"]))


def forward_days(calendars, opens_on: date, up_to: date):
    """Forward trading days: the union of the markets' own calendars from the
    opening day up to `up_to`, inclusive. Dates only; nothing about trades."""
    days = set()
    for dates in calendars:
        for d in dates:
            d = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
            if opens_on <= d <= up_to:
                days.add(d)
    return sorted(days)


def judge(*, max_dd_pct, day_count, trade_count, days, trades, previous):
    """The two bits from the forward run's summary numbers, latched on `previous`.

    Pure. `days` and `trades` are the sorted forward days and trades, used only to
    name the dates the bits flipped. Returns the new state; the numbers do not
    leave this function.
    """
    state = dict(previous or {})
    if not state.get("tripped") and max_dd_pct > CEILING_DD_PCT:
        state["tripped"] = True
        state["trip_date"] = _trip_date(trades)
    state.setdefault("tripped", False)
    state.setdefault("trip_date", None)
    reached = day_count >= GRADING_DAYS and trade_count >= GRADING_TRADES
    if not state.get("grading_reached") and reached:
        state["grading_reached"] = True
        state["reached_date"] = _reached_date(days, trades)
    state.setdefault("grading_reached", False)
    state.setdefault("reached_date", None)
    return state


def _trip_date(trades):
    """The exit day of the forward trade that closed most recently: the day the
    ceiling was seen to be breached, not the day of the deepest loss."""
    exits = sorted(str(t["exit_ts"])[:10] for t in trades if t.get("exit_ts"))
    return exits[-1] if exits else None


def _reached_date(days, trades):
    """The later of the sixtieth forward day and the thirtieth trade's entry day."""
    day = str(days[GRADING_DAYS - 1]) if len(days) >= GRADING_DAYS else None
    trade = (str(trades[GRADING_TRADES - 1]["entry_date"])[:10]
             if len(trades) >= GRADING_TRADES else None)
    return max(d for d in (day, trade) if d) if (day and trade) else None


def previous_trading_day(day: date) -> date:
    """The last weekday before `day`: the day whose bars the morning top-up brings."""
    d = day - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def bars_freshness(calendars, today: date):
    """(newest bar day across the markets, fresh?) - the precondition the chained
    top-up must satisfy: the newest day is at least the previous trading day. A
    date and a bit; neither says anything about performance."""
    newest = None
    for dates in calendars:
        for d in dates:
            d = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
            if newest is None or d > newest:
                newest = d
    fresh = newest is not None and newest >= previous_trading_day(today)
    return newest, fresh


def output_record(state, *, opens_on, now, bars_through=None, bars_fresh=None):
    return dict(window_open=opens_on is not None,
                bars_through=None if bars_through is None else str(bars_through),
                bars_fresh=bars_fresh,
                opens_on=None if opens_on is None else opens_on.isoformat(),
                tripped=bool(state.get("tripped", False)), trip_date=state.get("trip_date"),
                grading_reached=bool(state.get("grading_reached", False)),
                reached_date=state.get("reached_date"),
                computed_at=now.isoformat(), variant=VARIANT, ceiling_dd_pct=CEILING_DD_PCT,
                grading_days=GRADING_DAYS, grading_trades=GRADING_TRADES)


# ====================================================================== the run
class PreRegistrationDrift(Exception):
    """The pre-registration file and this module disagree on a number. Both are
    edited together, before the window opens, or not at all."""


def read_window(path=None):
    """(opens_on or None, the traded market keys) from the pre-registration file.

    THE FILE'S NUMBERS ARE AUTHORITATIVE and the module's constants must equal them:
    a ceiling, a cadence or a variant that differs between the two is a drift, and
    a drift after the window opened would be a rule changed after the fact. So the
    read refuses, loudly, rather than picking a side (Lode, 2026-09-08)."""
    path = path or WINDOW_FILE                 # resolved at call time, so tests can redirect it
    if not path.exists():
        return None, []
    window = json.loads(path.read_text(encoding="utf-8"))
    expected = dict(variant=VARIANT, ceiling_dd_pct=CEILING_DD_PCT,
                    grading_days=GRADING_DAYS, grading_trades=GRADING_TRADES)
    drift = {k: (window.get(k), v) for k, v in expected.items()
             if k in window and window[k] != v}
    if drift:
        raise PreRegistrationDrift(f"forward_window.json disagrees with forward_tripwire.py: {drift}")
    raw = window.get("opens_on")
    opens_on = None if raw in (None, "") else date.fromisoformat(raw)
    return opens_on, list(window.get("markets", []))


def read_previous(path=None):
    path = path or OUTPUT_FILE
    if not path.exists():
        return {}
    prev = json.loads(path.read_text(encoding="utf-8"))
    return {k: prev.get(k) for k in ("tripped", "trip_date", "grading_reached", "reached_date")}


def compute(opens_on: date, *, run_market, replay, markets, dials, today: date):
    """The forward run in memory: returns only the two bits' inputs, as numbers
    that die with the caller's frame."""
    all_trades, calendars = [], []
    for key in markets:
        result = run_market(key, uncapped=True, **dials)      # the one caller past the cap
        if result is None or result[0] is None:
            continue
        trades, _summary, dates = result
        all_trades.extend(trades)
        calendars.append(dates)
    fwd = forward_trades(all_trades, opens_on)
    days = forward_days(calendars, opens_on, today)
    _equity, max_dd, _curve = replay(fwd) if fwd else (None, 0.0, [])
    bars_through, bars_fresh = bars_freshness(calendars, today)
    return dict(max_dd_pct=float(max_dd), day_count=len(days), trade_count=len(fwd),
                days=days, trades=fwd, bars_through=bars_through, bars_fresh=bars_fresh)


def main(argv=None, now=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    now = now or datetime.now(timezone.utc)         # injectable, so tests own the clock
    opens_on, markets = read_window()
    if "--status" in argv:
        print(json.dumps(read_previous() | dict(window_open=opens_on is not None,
                                                opens_on=str(opens_on) if opens_on else None)))
        return 0
    if opens_on is None:
        record = output_record({}, opens_on=None, now=now)
        _write(record)
        print("forward window closed: forward_window.json carries no opens_on; nothing computed")
        return 0
    if not markets:
        print("forward window misconfigured: forward_window.json names no markets")
        return 2
    import run_1m
    import run_1m_matrix
    dials = next(d for name, d, _, _ in run_1m_matrix.VARIANTS if name == VARIANT)
    numbers = compute(opens_on, run_market=run_1m.run_market, replay=run_1m.portfolio_replay,
                      markets=markets, dials=dials, today=now.date())
    bars_through, bars_fresh = numbers.pop("bars_through"), numbers.pop("bars_fresh")
    if not bars_fresh:
        # THE FRESHNESS PRECONDITION: without the previous trading day's bars the
        # run would judge on a stale window. The bits are left as they were and
        # the record says the bars are stale; the board alarms on that.
        record = output_record(read_previous(), opens_on=opens_on, now=now,
                               bars_through=bars_through, bars_fresh=False)
        _write(record)
        print(f"tripwire: bars stale (through {bars_through}); bits unchanged")
        return 3
    state = judge(previous=read_previous(), **numbers)
    del numbers                                    # the series dies here, deliberately
    record = output_record(state, opens_on=opens_on, now=now,
                           bars_through=bars_through, bars_fresh=True)
    _write(record)
    print(f"tripwire: tripped={record['tripped']} grading_reached={record['grading_reached']} "
          f"bars_through={bars_through}")
    return 0


def _write(record, path=None):
    path = path or OUTPUT_FILE
    assert set(record) == set(OUTPUT_KEYS), sorted(set(record) ^ set(OUTPUT_KEYS))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
