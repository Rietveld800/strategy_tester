"""The EDGE positive control, guarded so it cannot rot.

`live_engine/FILL_CALIBRATION.md` section 4a makes reproducing the authors'
published values the gate on the whole tradability harness. A gate that is run once
by hand and then forgotten is not a gate, so it runs here too, on the same saved
fixtures and against the same published constants.

WHY THE MISSING-VALUE FILE IS NOT OPTIONAL, recorded because the project already
paid for the lesson on 2026-09-12: the first implementation agreed with the
missing-value file to 1e-16 while being WRONG, because that file's very first Open
is blank and the defect lived entirely at t=0. A later correction then reproduced
the complete file exactly while breaking the missing-value file by 5e-05. Either
fixture alone certifies a wrong rule; both together pin it. This is TESTING.md's
"it cannot discriminate" with two fixtures that each discriminate on a different
axis, and neither may be dropped for being slow or redundant.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tradability"))

from edge import edge                                            # noqa: E402
from gate_edge import EXPECTED, PROPOSED_RTOL, read_ohlc          # noqa: E402

REFERENCE = Path(__file__).resolve().parent.parent / "tradability" / "reference"


@pytest.mark.parametrize("filename", sorted(EXPECTED))
def test_edge_reproduces_the_published_values(filename):
    """Every published figure, on both published inputs, inside the tolerance."""
    o, h, l, c = read_ohlc(REFERENCE / filename)
    got = edge(o, h, l, c)
    want = EXPECTED[filename]

    assert got is not None, f"{filename}: the estimator returned missing"
    assert got.nobs == 10000

    checked = {"spread": got.spread, **got.published_fields()}
    assert set(checked) == set(want), "the published field set changed"
    for name, ours in checked.items():
        assert ours == pytest.approx(want[name], rel=PROPOSED_RTOL), \
            f"{filename}: {name} ours={ours!r} published={want[name]!r}"


def test_the_first_observation_enters_no_expectation():
    """The defect the control caught, pinned by a fixture that DISCRIMINATES.

    The two published files pin the rule between them, but only as a pair and only
    at the whole-estimator level. This asks the question directly: the two candidate
    de-meaning rules are computed here, independently of `edge.py`, from the
    published pseudocode, and the implementation must match the one that excludes
    t=0 and must NOT match the one that includes it.

    The fixture has to make the two differ, or it proves nothing (TESTING.md, "it
    cannot discriminate"). A first bar far from the rest does that: it moves
    `mean(r1)` measurably while contributing no transition of its own.
    """
    import numpy as np

    rng = np.random.default_rng(20260912)
    n = 400
    mid = 100.0 + np.cumsum(rng.normal(0.0, 0.05, n))
    o_p = mid + rng.normal(0.0, 0.02, n)
    c_p = mid + rng.normal(0.0, 0.02, n)
    h_p = np.maximum(o_p, c_p) + np.abs(rng.normal(0.0, 0.03, n))
    l_p = np.minimum(o_p, c_p) - np.abs(rng.normal(0.0, 0.03, n))
    # The discriminating bar: a first observation whose open sits far below its
    # own midpoint, so r1[0] is large and the two rules part company.
    o_p[0] = l_p[0]

    def candidate(include_first: bool) -> float:
        o, h, l, c = np.log(o_p), np.log(h_p), np.log(l_p), np.log(c_p)
        m = (h + l) / 2.0
        lg = lambda a: np.concatenate(([np.nan], a[:-1]))       # noqa: E731
        h1, l1, c1, m1 = lg(h), lg(l), lg(c), lg(m)
        r1, r2, r3, r4, r5 = m - o, o - m1, m - c1, c1 - m1, o - c1

        def ind(cond, *ops):
            out = np.where(cond, 1.0, 0.0)
            miss = np.zeros(out.shape, dtype=bool)
            for x in ops:
                miss |= np.isnan(x)
            return np.where(miss, np.nan, out)

        tau = ind((h != l) | (l != c1), h, l, c1)
        pt = np.nanmean(tau)
        po = np.nanmean(ind((tau == 1) & (o != h), tau, o, h)) + \
            np.nanmean(ind((tau == 1) & (o != l), tau, o, l))
        pc = np.nanmean(ind((tau == 1) & (c1 != h1), tau, c1, h1)) + \
            np.nanmean(ind((tau == 1) & (c1 != l1), tau, c1, l1))
        sl = slice(None) if include_first else slice(1, None)
        d1 = r1 - np.nanmean(r1[sl]) / pt * tau
        d3 = r3 - np.nanmean(r3[sl]) / pt * tau
        d5 = r5 - np.nanmean(r5[sl]) / pt * tau
        x1 = -4.0 / po * d1 * r2 + -4.0 / pc * d3 * r4
        x2 = -4.0 / po * d1 * r5 + -4.0 / pc * d5 * r4
        e1, e2 = np.nanmean(x1), np.nanmean(x2)
        v1 = np.nanmean(x1 * x1) - e1 * e1
        v2 = np.nanmean(x2 * x2) - e2 * e2
        vt = v1 + v2
        s2 = (v2 * e1 + v1 * e2) / vt if vt > 0 else (e1 + e2) / 2.0
        return float(np.sqrt(abs(s2)))

    including, excluding = candidate(True), candidate(False)
    assert including != pytest.approx(excluding, rel=1e-6), \
        "the fixture does not discriminate between the two rules; it proves nothing"

    got = edge(o_p, h_p, l_p, c_p)
    assert got is not None
    assert got.spread == pytest.approx(excluding, rel=PROPOSED_RTOL)
    assert got.spread != pytest.approx(including, rel=1e-6)


def test_too_short_a_series_is_missing_not_zero():
    """Fewer than three observations returns missing, as the pseudocode states."""
    assert edge([1.0, 1.0], [1.0, 1.0], [1.0, 1.0], [1.0, 1.0]) is None


def test_a_flat_series_is_missing_not_a_spread_of_zero():
    """No period with tau=1 means the estimator cannot speak, and says so."""
    flat = [10.0] * 50
    assert edge(flat, flat, flat, flat) is None


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        edge([1.0, 2.0, 3.0], [1.0, 2.0], [1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
