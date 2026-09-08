"""The rung 6 tripwire (forward_tripwire.py): two bits out, nothing else.

Offline, against a fake research run. What is proven: the forward set is the trades
entered on or after the opening day; forward days are the union of calendars from
that day; each bit flips at the right moment and latches; the trip date and the
reached date are the only dates that leave; the output carries exactly the allowed
keys and no number; nothing else is written to disk; nothing intermediate reaches
stdout; and a closed window computes nothing.
"""

import io
import json
import sys
from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import forward_tripwire as tw

OPENS = date(2026, 9, 15)


def _trade(entry, exit_, net_r, ts="10:00:00"):
    return dict(entry_date=entry, entry_ts=f"{entry} {ts}", exit_ts=f"{exit_} 14:00:00",
                net_r=net_r)


def _calendar(first, n):
    from datetime import timedelta
    return [first + timedelta(days=i) for i in range(n)]


# ------------------------------------------------------------ the filters
def test_forward_trades_are_those_entered_on_or_after_the_opening_day():
    trades = [_trade("2026-09-14", "2026-09-15", 1.0), _trade("2026-09-15", "2026-09-16", 1.0),
              _trade("2026-09-20", "2026-09-21", -1.0, ts="09:00:00")]
    fwd = tw.forward_trades(trades, OPENS)
    assert [t["entry_date"] for t in fwd] == ["2026-09-15", "2026-09-20"]


def test_forward_days_are_the_union_of_calendars_from_the_opening_day():
    a = _calendar(date(2026, 9, 10), 10)               # 09-10 .. 09-19
    b = [date(2026, 9, 18), date(2026, 9, 25)]
    days = tw.forward_days([a, b], OPENS, up_to=date(2026, 9, 22))
    assert days[0] == OPENS and days[-1] == date(2026, 9, 19) and len(days) == 5


# -------------------------------------------------------------- the judge
def test_the_bits_flip_at_the_right_moment_and_latch():
    quiet = dict(max_dd_pct=3.0, day_count=10, trade_count=5, days=[], trades=[])
    s = tw.judge(previous={}, **quiet)
    assert s == dict(tripped=False, trip_date=None, grading_reached=False, reached_date=None)
    trades = [_trade("2026-09-15", "2026-09-16", -1.0)]
    s = tw.judge(previous=s, max_dd_pct=9.0, day_count=10, trade_count=1, days=[], trades=trades)
    assert s["tripped"] is True and s["trip_date"] == "2026-09-16"
    s = tw.judge(previous=s, max_dd_pct=1.0, day_count=10, trade_count=1, days=[], trades=[])
    assert s["tripped"] is True and s["trip_date"] == "2026-09-16", "latched"
    days = _calendar(OPENS, 60)
    thirty = [_trade("2026-09-15", "2026-09-16", 0.5) for _ in range(29)] + \
             [_trade("2026-11-20", "2026-11-21", 0.5)]
    s = tw.judge(previous={}, max_dd_pct=1.0, day_count=60, trade_count=30, days=days,
                 trades=thirty)
    assert s["grading_reached"] is True
    assert s["reached_date"] == "2026-11-20", "the later of day sixty and trade thirty"
    s = tw.judge(previous={}, max_dd_pct=1.0, day_count=60, trade_count=29, days=days, trades=[])
    assert s["grading_reached"] is False, "whichever comes second"


def test_the_ceiling_is_strict_and_the_numbers_do_not_leave_the_judge():
    s = tw.judge(previous={}, max_dd_pct=8.9, day_count=0, trade_count=0, days=[], trades=[])
    assert s["tripped"] is False
    for key in s:
        assert key in ("tripped", "trip_date", "grading_reached", "reached_date")


# ------------------------------------------------------------- the output
def test_the_output_carries_exactly_the_allowed_keys_and_no_number(tmp_path):
    now = datetime(2026, 9, 16, 7, 0, tzinfo=timezone.utc)
    record = tw.output_record(dict(tripped=False, grading_reached=False), opens_on=OPENS, now=now)
    assert set(record) == set(tw.OUTPUT_KEYS)
    out = tmp_path / "forward_tripwire.json"
    tw._write(record, path=out)
    written = json.loads(out.read_text())
    assert set(written) == set(tw.OUTPUT_KEYS)
    forbidden = ("equity", "drawdown", "net_r", "trade_count", "day_count", "curve", "running")
    assert not any(f in json.dumps(written) for f in forbidden)
    assert [p.name for p in tmp_path.iterdir()] == ["forward_tripwire.json"], "nothing else written"
    with pytest.raises(AssertionError):
        tw._write(dict(record, drawdown=4.2), path=tmp_path / "other.json")


def test_compute_runs_the_research_engine_and_keeps_only_the_summary(monkeypatch):
    calls = []

    def fake_run_market(key, **dials):
        calls.append((key, dials.get("min_rpu_range_ratio")))
        return ([_trade("2026-09-16", "2026-09-17", -2.0), _trade("2026-09-01", "2026-09-02", 5.0)],
                dict(), _calendar(date(2026, 9, 1), 30))

    def fake_replay(trades):
        return 90_000.0, 10.0, [("x", 1)]

    numbers = tw.compute(OPENS, run_market=fake_run_market, replay=fake_replay,
                         markets=["GC", "ES"], dials=dict(min_rpu_range_ratio=0.0),
                         today=date(2026, 9, 30))
    assert [c[0] for c in calls] == ["GC", "ES"] and calls[0][1] == 0.0
    assert numbers["trade_count"] == 2 and numbers["max_dd_pct"] == 10.0
    assert numbers["day_count"] == 16                       # 09-15 .. 09-30 within the calendar


def test_main_prints_only_the_bits_and_a_closed_window_computes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(tw, "WINDOW_FILE", tmp_path / "forward_window.json")
    monkeypatch.setattr(tw, "OUTPUT_FILE", tmp_path / "out" / "forward_tripwire.json")
    (tmp_path / "forward_window.json").write_text(json.dumps(dict(opens_on=None, markets=["GC"])))
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert tw.main([]) == 0
    written = json.loads((tmp_path / "out" / "forward_tripwire.json").read_text())
    assert written["window_open"] is False and written["tripped"] is False
    assert "closed" in buf.getvalue()
    # an open window with a fake engine: stdout carries the two bits and nothing numeric
    (tmp_path / "forward_window.json").write_text(json.dumps(dict(opens_on="2026-09-15",
                                                                   markets=["GC"])))
    import types
    fake_run_1m = types.SimpleNamespace(
        run_market=lambda key, **d: ([_trade("2026-09-16", "2026-09-17", -1.0)], {}, _calendar(OPENS, 3)),
        portfolio_replay=lambda trades: (99_000.0, 12.5, []))
    fake_matrix = types.SimpleNamespace(VARIANTS=[("variant 4", dict(min_rpu_range_ratio=0.0), None, None)])
    monkeypatch.setitem(sys.modules, "run_1m", fake_run_1m)
    monkeypatch.setitem(sys.modules, "run_1m_matrix", fake_matrix)
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert tw.main([]) == 0
    text = buf.getvalue()
    assert "tripped=True" in text and "grading_reached=False" in text
    assert "12.5" not in text and "99" not in text, "no intermediate number reaches stdout"
    written = json.loads((tmp_path / "out" / "forward_tripwire.json").read_text())
    assert written["tripped"] is True and written["trip_date"] == "2026-09-17"
    assert set(written) == set(tw.OUTPUT_KEYS)


# ------------------------------------------------ the pre-registration file
def test_a_drift_between_the_file_and_the_module_refuses(tmp_path):
    path = tmp_path / "forward_window.json"
    path.write_text(json.dumps(dict(opens_on=None, markets=["GC"], ceiling_dd_pct=8.9,
                                    grading_days=60, grading_trades=30, variant="variant 4")))
    assert tw.read_window(path) == (None, ["GC"])
    path.write_text(json.dumps(dict(opens_on=None, markets=["GC"], ceiling_dd_pct=10.0)))
    with pytest.raises(tw.PreRegistrationDrift):
        tw.read_window(path)


def test_the_real_file_agrees_with_the_module_and_names_the_selection_files_traded_set():
    """The pre-registration file's market set must be MARKET_SELECTION.md's surviving
    set, read from the selection file itself; typed twice is drift waiting to happen."""
    opens_on, markets = tw.read_window(tw.WINDOW_FILE)
    selection = tw.HERE.parent / "live_engine" / "MARKET_SELECTION.md"
    if not selection.exists():
        pytest.skip("live_engine's MARKET_SELECTION.md is not on this machine")
    text = selection.read_text(encoding="utf-8")
    table = text.split("## The set", 1)[1].split("### Excluded", 1)[0]
    rows = [line.split("|")[1].strip() for line in table.splitlines()
            if line.startswith("| ") and not line.startswith("| Market") and "---" not in line]
    assert rows, "no markets parsed from the selection file"
    assert sorted(markets) == sorted(rows), "forward_window.json and MARKET_SELECTION.md disagree"
    assert len(markets) == 17
