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


#: The fixture must separate the two candidate rules by at least this much, and the
#: assertion below states it as a floor rather than reusing the 1e-6 of a
#: `pytest.approx` comparison. Measured 2026-09-12 across the five seeds below with
#: `FIRST_BAR_WIDEN = 20`: 2.78e-04 at the weakest seed and 5.60e-02 at the
#: strongest, so the floor carries a margin of ~28x at worst.
#:
#: WHY THE FLOOR IS STATED AND THE FIXTURE IS SEED-ROBUST. The first version of this
#: guard used one seed and a first bar left at its natural width. It DID fire when
#: perturbed - removing the discriminating bar produced separation 4.07e-07 and the
#: assertion failed with its own message, so it could not pass silently - but its
#: separation on the committed seed was 4.62e-06 against a 1e-6 threshold, a margin
#: of 4.6x, and that seed was the weakest of six tested by an order of magnitude. A
#: guard whose whole job is discrimination should not sit that close to its own
#: threshold; a margin is not a pass condition until it is written down.
MIN_RULE_SEPARATION = 1e-5

#: How much wider than its natural span the first bar is made. The point is to put a
#: large `r1[0] = m[0] - o[0]` into the series - a first observation whose open sits
#: at the low of a deliberately wide bar - so the two rules part company by a margin
#: that does not depend on the luck of a seed.
FIRST_BAR_WIDEN = 20.0


@pytest.mark.parametrize("seed", [20260912, 1, 2, 7, 12345])
def test_the_first_observation_enters_no_expectation(seed):
    """The defect the control caught, pinned by a fixture that DISCRIMINATES.

    The two published files pin the rule between them, but only as a pair and only
    at the whole-estimator level. This asks the question directly: the two candidate
    de-meaning rules are computed here, independently of `edge.py`, from the
    published pseudocode, and the implementation must match the one that excludes
    t=0 and must NOT match the one that includes it.

    The fixture has to make the two differ, or it proves nothing (TESTING.md, "it
    cannot discriminate", and the blind-fixture rule the EDGE control produced). It
    is run over five seeds and asserts its own separation floor first, so a future
    change that quietly stops it discriminating fails here rather than passing.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    n = 400
    mid = 100.0 + np.cumsum(rng.normal(0.0, 0.05, n))
    o_p = mid + rng.normal(0.0, 0.02, n)
    c_p = mid + rng.normal(0.0, 0.02, n)
    h_p = np.maximum(o_p, c_p) + np.abs(rng.normal(0.0, 0.03, n))
    l_p = np.minimum(o_p, c_p) - np.abs(rng.normal(0.0, 0.03, n))
    # The discriminating bar, built rather than hoped for: a deliberately wide first
    # bar whose open sits at its low, so r1[0] is large while t=0 still contributes
    # no transition of its own. Close is clamped back inside the bar so the fixture
    # stays valid OHLC.
    span = h_p[0] - l_p[0]
    h_p[0] += FIRST_BAR_WIDEN * span
    l_p[0] -= FIRST_BAR_WIDEN * span
    o_p[0] = l_p[0]
    c_p[0] = min(max(c_p[0], l_p[0]), h_p[0])

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
    separation = abs(including - excluding) / abs(excluding)
    assert separation >= MIN_RULE_SEPARATION, (
        f"seed {seed}: the fixture separates the two rules by only {separation:.2e}, "
        f"below the stated floor {MIN_RULE_SEPARATION:.0e}; it proves nothing")

    got = edge(o_p, h_p, l_p, c_p)
    assert got is not None
    assert got.spread == pytest.approx(excluding, rel=PROPOSED_RTOL)
    assert got.spread != pytest.approx(including, rel=MIN_RULE_SEPARATION / 10)


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
