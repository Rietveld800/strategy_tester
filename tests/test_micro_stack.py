"""The micro stack replay (build_1m_report.replay_micro) pinned on
synthetic trades: with no routed micro it is the full-contracts replay
exactly, a routed micro tops the position up toward the budget with
its stop rounded AWAY on the micro's own grid, and the refusal only
fires when even one micro does not fit."""

import build_1m_report as rep
import research_1m_sizing as sizing


SPECS = {
    "ES": dict(type="future", point_value=50.0, tick=0.25),
}
ROUTE = {"ES": dict(root="MES", fraction=0.1, tick=0.25)}


def trade(rpu, net_r, entry="2026-03-02 10:00:00+00:00",
          exit_="2026-03-03 19:00:00+00:00", reason="close1"):
    return dict(market="ES", contract="ESM6", side="long", rpu=rpu,
                entry=5000.0, entry_first=5000.0, stop=5000.0 - rpu,
                net_r=net_r, entry_ts=entry, exit_ts=exit_, reason=reason)


def test_no_route_equals_full_contracts_replay(monkeypatch):
    monkeypatch.setattr(sizing, "load_specs", lambda: (SPECS, "test"))
    trades = [trade(10.0, 2.0), trade(20.0, -1.0,
                                      "2026-03-04 10:00:00+00:00",
                                      "2026-03-05 19:00:00+00:00", "stop")]
    full = rep.replay_contracts(trades, 1.0, 250_000.0)
    stack = rep.replay_micro(trades, 1.0, 250_000.0, {}, SPECS, {})
    assert stack[2] == full[2] and stack[3] == full[3]
    assert stack[4] == full[4]
    for i in full[0]:
        assert stack[0][i]["n"] == full[0][i]["n"]
        assert stack[0][i]["k"] == 0
        assert abs(stack[0][i]["pnl_usd"] - full[0][i]["pnl_usd"]) < 1e-9


def test_micro_tops_up_toward_budget():
    # 1% of $250k = $2,500; ES at rpu 10 risks $500 a contract -> 5
    # full, $0 left; at rpu 12 -> 4 full ($2,400), $100 left, a micro
    # risks 12 x 5 = $60 -> one micro fits.
    t = trade(12.0, 1.0)
    key = f"{t['market']}|{t['contract']}|{t['entry_ts']}"
    per_entry = {key: dict(root="MES", basis=0.0, volume=1000)}
    money_of, _, _, _, refused = rep.replay_micro(
        [t], 1.0, 250_000.0, ROUTE, SPECS, per_entry)
    assert not refused
    m = money_of[0]
    assert (m["n"], m["k"]) == (4, 1)
    assert m["risk_usd"] == 4 * 600.0 + 60.0
    assert m["risk_pct"] <= 1.0


def test_micro_stop_rounds_away_on_the_micro_grid():
    # A long's stop below entry rounds DOWN to the grid; a short's
    # stop above entry rounds UP. A stop already on the grid stays.
    assert rep.rounded_micro_stop(5000.0, 4990.1, 0.25) == 4990.0
    assert rep.rounded_micro_stop(5000.0, 5009.9, 0.25) == 5010.0
    assert rep.rounded_micro_stop(5000.0, 4990.25, 0.25) == 4990.25


def test_refused_only_when_no_micro_fits():
    # $250k / 1% = $2,500 budget. rpu 60 on ES risks $3,000 a full
    # contract (refused full-only) but $300 a micro -> the stack takes
    # 8 micros. rpu 600 risks $3,000 a micro too -> refused.
    a = trade(60.0, 1.0)
    b = trade(600.0, 1.0, "2026-03-04 10:00:00+00:00",
              "2026-03-05 19:00:00+00:00")
    per_entry = {f"ES|ESM6|{a['entry_ts']}": dict(root="MES", basis=0.0,
                                                  volume=1000),
                 f"ES|ESM6|{b['entry_ts']}": dict(root="MES", basis=0.0,
                                                  volume=1000)}
    money_of, _, _, _, refused = rep.replay_micro(
        [a, b], 1.0, 250_000.0, ROUTE, SPECS, per_entry)
    assert (money_of[0]["n"], money_of[0]["k"]) == (0, 8)
    assert list(refused) == [1]


def test_participation_cap_bounds_the_micro_leg():
    t = trade(60.0, 1.0)
    per_entry = {f"ES|ESM6|{t['entry_ts']}": dict(root="MES", basis=0.0,
                                                  volume=6)}
    money_of, _, _, _, _ = rep.replay_micro(
        [t], 1.0, 250_000.0, ROUTE, SPECS, per_entry)
    assert money_of[0]["k"] == int(6 * rep.PARTICIPATION_CAP)
