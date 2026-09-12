"""The EDGE estimator: effective bid-ask spread from open, high, low and close.

Ardia, Guidotti & Kroencke (2024), Journal of Financial Economics 161, 103916.
`live_engine/FILL_CALIBRATION.md` section 4.5 states the definition and section 4a
makes this the GATE on the whole tradability harness: nothing else is computed
until this reproduces the authors' published values.

WRITTEN FROM THE PUBLISHED PSEUDOCODE, NOT FROM THEIR CODE, and that is deliberate.
`tradability/reference/PSEUDOCODE_README.md` is the authors' own specification,
saved beside the two data files it names. Implementing from the specification and
checking against their published constants makes the control independent of this
machine reproducing their environment, their package version or their numpy - which
is a class of false agreement, and of false alarm, that executing their code here
would have left in.

EVERY INTERMEDIATE IS RETURNED, because the README publishes eight of them. A gate
that can only say "the number differs" sends the next session hunting; one that can
say WHICH intermediate differs has localised the defect before anyone starts.

Missing values are part of the specification and not an afterthought: the authors
publish a second data file with a random subset blanked and its own expected value,
so `nan` handling is itself under test. Every mean here is a nan-skipping mean, as
the pseudocode's "if non-missing else missing" requires.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class EdgeResult:
    """The estimate and every intermediate the reference publishes."""

    spread: float
    pt: float
    po: float
    pc: float
    e1: float
    e2: float
    v1: float
    v2: float
    s2: float
    nobs: int

    def published_fields(self) -> dict:
        """The eight the README tabulates, in its order."""
        return dict(pt=self.pt, po=self.po, pc=self.pc, e1=self.e1,
                    e2=self.e2, v1=self.v1, v2=self.v2, s2=self.s2)


def _lag(a: np.ndarray) -> np.ndarray:
    """One period back, the first element missing. `lag` in the pseudocode."""
    out = np.empty_like(a)
    out[0] = np.nan
    out[1:] = a[:-1]
    return out


def _indicator(condition: np.ndarray, *operands: np.ndarray) -> np.ndarray:
    """A pseudocode indicator: the condition as 1.0/0.0, or nan where any operand
    it was computed from is missing. Written out rather than relying on numpy's
    comparison-with-nan, because `nan != x` is True and would silently make a
    missing observation count as an informative one."""
    out = np.where(condition, 1.0, 0.0)
    missing = np.zeros(out.shape, dtype=bool)
    for operand in operands:
        missing |= np.isnan(operand)
    return np.where(missing, np.nan, out)


def edge(open_, high, low, close, sign: bool = False) -> EdgeResult | None:
    """The estimator. Returns None where the pseudocode returns missing.

    A value of 0.01 is a spread of 1%, as the reference states.
    """
    o_p = np.asarray(open_, dtype=float)
    h_p = np.asarray(high, dtype=float)
    l_p = np.asarray(low, dtype=float)
    c_p = np.asarray(close, dtype=float)

    nobs = len(o_p)
    if len(h_p) != nobs or len(l_p) != nobs or len(c_p) != nobs:
        raise ValueError("open, high, low and close must have the same length")
    if nobs < 3:
        return None

    with np.errstate(divide="ignore", invalid="ignore"):
        o = np.log(o_p)
        h = np.log(h_p)
        l = np.log(l_p)
        c = np.log(c_p)
        m = (h + l) / 2.0

        h1, l1, c1, m1 = _lag(h), _lag(l), _lag(c), _lag(m)

        r1 = m - o
        r2 = o - m1
        r3 = m - c1
        r4 = c1 - m1
        r5 = o - c1

        tau = _indicator((h != l) | (l != c1), h, l, c1)
        po1 = _indicator((tau == 1.0) & (o != h), tau, o, h)
        po2 = _indicator((tau == 1.0) & (o != l), tau, o, l)
        pc1 = _indicator((tau == 1.0) & (c1 != h1), tau, c1, h1)
        pc2 = _indicator((tau == 1.0) & (c1 != l1), tau, c1, l1)

        pt = np.nanmean(tau)
        po = np.nanmean(po1) + np.nanmean(po2)
        pc = np.nanmean(pc1) + np.nanmean(pc2)

        if np.nansum(tau) < 2 or po == 0 or pc == 0:
            return None

        # THE FIRST OBSERVATION ENTERS NO EXPECTATION. The estimator is over
        # period-to-period transitions: every quantity it sums involves a lag, so
        # t=0 has no transition to contribute. `r1 = m - o` is the one return
        # needing no lag, so on a COMPLETE series it is defined at t=0 while
        # `r2`..`r5` are not - and letting it into `mean(r1)` lets an observation
        # the estimator never sums set the constant the estimator is centred on.
        #
        # Found 2026-09-12 by the section 4a control, which is the only reason it
        # was found: on the authors' complete file the error lands at ~3e-07
        # relative on e1 and ~5e-07 on the spread - far too small to notice by
        # eye, far too large to be float noise.
        #
        # IT TOOK BOTH PUBLISHED FILES TO GET THIS RIGHT, and that is worth
        # recording here rather than only in the report. The missing-value file
        # agreed to 1e-16 WITH the defect present, because its very first Open is
        # blank: t=0 was already missing, so that fixture could not see the
        # difference at all. And the first correction tried - masking these means
        # by tau's own validity - reproduced the complete file exactly while
        # breaking the missing-value file by 5e-05, because on that file tau is
        # missing on many interior rows the estimator does use. Either fixture
        # alone would have certified a wrong rule.
        r1_from_1 = r1[1:]
        r3_from_1 = r3[1:]
        r5_from_1 = r5[1:]

        d1 = r1 - np.nanmean(r1_from_1) / pt * tau
        d3 = r3 - np.nanmean(r3_from_1) / pt * tau
        d5 = r5 - np.nanmean(r5_from_1) / pt * tau

        x1 = -4.0 / po * d1 * r2 + -4.0 / pc * d3 * r4
        x2 = -4.0 / po * d1 * r5 + -4.0 / pc * d5 * r4

        e1 = np.nanmean(x1)
        e2 = np.nanmean(x2)

        v1 = np.nanmean(x1 * x1) - e1 * e1
        v2 = np.nanmean(x2 * x2) - e2 * e2

        vt = v1 + v2
        s2 = (v2 * e1 + v1 * e2) / vt if vt > 0 else (e1 + e2) / 2.0

        s = float(np.sqrt(np.abs(s2)))
        if sign and s2 < 0:
            s = -s

    return EdgeResult(spread=s, pt=float(pt), po=float(po), pc=float(pc),
                      e1=float(e1), e2=float(e2), v1=float(v1), v2=float(v2),
                      s2=float(s2), nobs=nobs)
