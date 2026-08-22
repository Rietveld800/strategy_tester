# Pins the formulas in sharpe_stats.py: the Sharpe/SE/PSR arithmetic, the
# deflation benchmark, both effective-N estimators and the bootstrap's
# invariances. Pure math, no project data.

import math

import numpy as np
import pytest

import sharpe_stats as ss


def test_sharpe_basic():
    st = ss.sharpe([1.0, -1.0, 1.0, -1.0])
    assert st["n"] == 4
    assert st["mean"] == pytest.approx(0.0)
    assert st["sr"] == pytest.approx(0.0)
    # Lo's SE at SR = 0 is sqrt(1/n)
    assert st["se"] == pytest.approx(0.5)
    assert st["ci_lo"] == pytest.approx(-0.98)
    assert st["ci_hi"] == pytest.approx(0.98)


def test_sharpe_degenerate():
    assert ss.sharpe([1.0])["sr"] is None
    assert ss.sharpe([2.0, 2.0, 2.0])["sr"] is None


def test_psr_normal_case():
    # sr=0.2, n=100, normal shape: z = 0.2*sqrt(99)/sqrt(1 + 0.5*0.04*... )
    # var = 1 - 0 + (3-1)/4 * 0.04 = 1.02; z = 1.9701...; Phi(z) = 0.9756
    p = ss.psr(0.2, 100, 0.0, 3.0)
    assert p == pytest.approx(0.9756, abs=1e-3)
    # at the benchmark itself the probability is one half
    assert ss.psr(0.2, 100, 0.0, 3.0, benchmark=0.2) == pytest.approx(0.5)
    # positive skew helps (smaller variance term), negative hurts
    assert ss.psr(0.2, 100, 1.0, 3.0) > p > ss.psr(0.2, 100, -1.0, 3.0)


def test_psr_guards():
    assert ss.psr(None, 100, 0.0, 3.0) is None
    assert ss.psr(0.2, 1, 0.0, 3.0) is None
    # Mertens variance term driven non-positive by extreme skew
    assert ss.psr(2.0, 100, 5.0, 3.0) is None


def test_expected_max_sr():
    assert ss.expected_max_sr(1.0, 1) == 0.0
    assert ss.expected_max_sr(0.0, 100) == 0.0
    # grows with N, scales with sqrt(var)
    a, b = ss.expected_max_sr(1.0, 10), ss.expected_max_sr(1.0, 100)
    assert 0 < a < b
    assert ss.expected_max_sr(4.0, 10) == pytest.approx(2 * a)
    # N=2 closed form: (1-g)*z(0.5) + g*z(1 - 1/(2e)) with z(0.5) = 0
    from statistics import NormalDist
    want = ss.EULER_GAMMA * NormalDist().inv_cdf(1 - 1 / (2 * math.e))
    assert ss.expected_max_sr(1.0, 2) == pytest.approx(want)


def test_dsr_below_psr():
    p = ss.psr(0.3, 80, -0.5, 4.0)
    d = ss.dsr(0.3, 80, -0.5, 4.0, 0.02, 20)
    assert d < p


def test_breakeven_n():
    # a strong cell survives some deflation, and the scan is monotone
    star = ss.breakeven_n(0.5, 100, 0.0, 3.0, 0.01, 231)
    assert star is not None and 1 <= star <= 231
    assert ss.dsr(0.5, 100, 0.0, 3.0, 0.01, star) >= 0.95
    if star < 231:
        assert ss.dsr(0.5, 100, 0.0, 3.0, 0.01, star + 1) < 0.95
    # a weak cell fails before any deflation
    assert ss.breakeven_n(0.05, 30, 0.0, 3.0, 0.01, 231) is None


def test_participation_ratio():
    assert ss.participation_ratio(np.eye(5)) == pytest.approx(5.0)
    assert ss.participation_ratio(np.ones((5, 5))) == pytest.approx(1.0)
    # two independent identical blocks -> 2
    block = np.kron(np.eye(2), np.ones((3, 3)))
    assert ss.participation_ratio(block) == pytest.approx(2.0)


def test_neff_average_corr():
    assert ss.neff_average_corr(10, 0.0) == pytest.approx(10.0)
    assert ss.neff_average_corr(10, 1.0) == pytest.approx(1.0)
    assert ss.neff_average_corr(10, 0.5) == pytest.approx(10 / 5.5)


def test_daily_returns_placement():
    cal = ["2026-01-02", "2026-01-05", "2026-01-06"]
    trades = [dict(exit_date="2026-01-05", net_r=1.5),
              dict(exit_date="2026-01-05", net_r=-0.5),
              dict(exit_date="2026-01-06", net_r=2.0)]
    v = ss.daily_returns(trades, cal)
    assert v.tolist() == [0.0, 1.0, 2.0]
    # an off-calendar date lands on the nearest following day, not dropped
    v2 = ss.daily_returns([dict(exit_date="2026-01-04", net_r=3.0)], cal)
    assert v2.tolist() == [0.0, 3.0, 0.0]


def test_paired_delta_sr_identical_cells():
    cal = [f"2026-01-{d:02d}" for d in range(1, 29)]
    rng = np.random.default_rng(7)
    trades = [dict(entry_date=cal[i % len(cal)], net_r=float(r))
              for i, r in enumerate(rng.normal(0.3, 1.0, 200))]
    days = ss.by_entry_day(trades, cal)
    boot = ss.paired_delta_sr(days, days, reps=500)
    # identical cells: every resample gives delta exactly zero
    assert boot["mean"] == pytest.approx(0.0)
    assert boot["se"] == pytest.approx(0.0)


def test_paired_delta_sr_detects_gap():
    cal = [f"2026-01-{d:02d}" for d in range(1, 29)]
    rng = np.random.default_rng(7)
    good = [dict(entry_date=cal[i % len(cal)], net_r=float(r))
            for i, r in enumerate(rng.normal(0.8, 1.0, 300))]
    flat = [dict(entry_date=cal[i % len(cal)], net_r=float(r))
            for i, r in enumerate(rng.normal(0.0, 1.0, 300))]
    boot = ss.paired_delta_sr(ss.by_entry_day(good, cal),
                              ss.by_entry_day(flat, cal), reps=500)
    assert boot["mean"] > 0.5
    assert boot["p_le_0"] < 0.05
