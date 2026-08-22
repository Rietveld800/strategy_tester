# sharpe_stats.py
#
# Pure statistics for the Sharpe reading of the R-cut grids
# (research_1m_sharpe.py). Kept free of project imports on purpose: the tests
# pin these formulas without loading bars, market mappings or pandas, and the
# report script stays the only place that knows where trades live.
#
# Conventions, chosen once and shared by every caller:
#
# - The unit is the PER-TRADE Sharpe on net R: mean(net_r) / std(net_r),
#   sample std. Per trade because the geometry band decides per trade, and
#   because scaling risk% multiplies every trade's return alike, so the number
#   is leverage-invariant - the property the levered-to-6%-drawdown comparison
#   buys by bisection, had here by algebra. It deliberately ignores trade
#   FREQUENCY; the annualised figure (sr * sqrt(trades per year)) puts that
#   back, and a band that refuses trades must clear sqrt(n_full / n_band) of
#   per-trade lift to break even on that basis.
#
# - The standard error is Lo (2002), the iid form: sqrt((1 + SR^2/2) / n).
#   The skew/kurtosis correction is NOT folded into the SE; it lives in the
#   PSR denominator (Mertens), where it matters most - these R distributions
#   have a floor near -1R and a long right tail, nothing like normal.
#
# - PSR and DSR follow Bailey & Lopez de Prado ("The Sharpe Ratio Efficient
#   Frontier" 2012, "The Deflated Sharpe Ratio" 2014). PSR is the probability
#   that the TRUE Sharpe exceeds a benchmark given n, skew and kurtosis; DSR
#   is PSR against the benchmark a no-edge search would have produced anyway:
#   the expected maximum of N independent null trials whose estimated SRs
#   spread with the variance actually observed across the grid's cells.
#
# - Effective N: the grid's 231 cells share most of their trades, so they are
#   nowhere near 231 independent trials. The headline estimate is the
#   participation ratio of the cells' daily-return correlation matrix,
#   (sum lambda)^2 / sum lambda^2 - no thresholds, no clustering knobs; the
#   sanity check is the average-correlation shrinkage N / (1 + (N-1)*rho).

import math
from statistics import NormalDist

import numpy as np

EULER_GAMMA = 0.5772156649015329
_NORM = NormalDist()


def moments(rs):
    """n, mean, sample std (ddof=1), skewness and kurtosis (normal = 3).

    Skew and kurtosis use the population std, the plain moment estimators the
    PSR formula was derived with; the Sharpe itself uses the sample std."""
    a = np.asarray(rs, dtype=float)
    n = int(a.size)
    if n < 2:
        return dict(n=n, mean=float(a.mean()) if n else None,
                    sd=None, skew=None, kurt=None)
    mean = float(a.mean())
    sd = float(a.std(ddof=1))
    sd0 = float(a.std(ddof=0))
    if sd0 == 0.0:
        return dict(n=n, mean=mean, sd=0.0, skew=None, kurt=None)
    z = (a - mean) / sd0
    return dict(n=n, mean=mean, sd=sd,
                skew=float(np.mean(z ** 3)), kurt=float(np.mean(z ** 4)))


def sharpe(rs):
    """Per-trade Sharpe with Lo's standard error and a 95% interval.

    Returns a dict of n, mean, sd, skew, kurt, sr, se, ci_lo, ci_hi - the sr
    fields None when the list cannot support them (n < 2 or zero spread)."""
    m = moments(rs)
    out = dict(m, sr=None, se=None, ci_lo=None, ci_hi=None)
    if m["n"] < 2 or not m["sd"]:
        return out
    sr = m["mean"] / m["sd"]
    se = math.sqrt((1.0 + sr * sr / 2.0) / m["n"])
    out.update(sr=sr, se=se, ci_lo=sr - 1.96 * se, ci_hi=sr + 1.96 * se)
    return out


def psr(sr, n, skew, kurt, benchmark=0.0):
    """Probabilistic Sharpe Ratio: P(true SR > benchmark | n, skew, kurt).

    None when the inputs cannot carry the formula (n < 2, or the Mertens
    variance term goes non-positive, which extreme skew can do)."""
    if sr is None or n is None or n < 2 or skew is None or kurt is None:
        return None
    var = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if var <= 0.0:
        return None
    z = (sr - benchmark) * math.sqrt(n - 1.0) / math.sqrt(var)
    return _NORM.cdf(z)


def expected_max_sr(var_trials, n_trials):
    """SR0: the expected best ESTIMATED Sharpe among n_trials independent
    trials whose true Sharpe is zero, when the estimates spread with variance
    var_trials. The deflation benchmark of the DSR."""
    if n_trials <= 1 or var_trials <= 0.0:
        return 0.0
    return math.sqrt(var_trials) * (
        (1.0 - EULER_GAMMA) * _NORM.inv_cdf(1.0 - 1.0 / n_trials)
        + EULER_GAMMA * _NORM.inv_cdf(1.0 - 1.0 / (n_trials * math.e)))


def dsr(sr, n, skew, kurt, var_trials, n_trials):
    """Deflated Sharpe Ratio: PSR against the luckiest of n_trials nulls."""
    return psr(sr, n, skew, kurt,
               benchmark=expected_max_sr(var_trials, n_trials))


def breakeven_n(sr, n, skew, kurt, var_trials, n_max, conf=0.95):
    """The largest effective N at which the DSR still clears `conf`.

    None when even N = 1 fails (the undeflated PSR itself is below conf);
    n_max when deflation never bites within the trials actually searched.
    DSR falls monotonically in N, so a linear scan is exact and cheap."""
    best = None
    for n_trials in range(1, n_max + 1):
        d = dsr(sr, n, skew, kurt, var_trials, n_trials)
        if d is None or d < conf:
            break
        best = n_trials
    return best


def participation_ratio(corr):
    """Effective number of independent series in a correlation matrix:
    (sum lambda)^2 / sum lambda^2. Identity -> N, all-ones -> 1, k identical
    blocks -> k. Negative eigenvalues (numerical noise) are clipped."""
    lam = np.clip(np.linalg.eigvalsh(np.asarray(corr, dtype=float)), 0.0, None)
    total = float(lam.sum())
    if total == 0.0:
        return 0.0
    return total * total / float(np.square(lam).sum())


def neff_average_corr(n, rho_bar):
    """Average-correlation shrinkage: N / (1 + (N-1)*rho). The one-number
    sanity check beside the participation ratio."""
    rho = min(1.0, max(0.0, rho_bar))
    return n / (1.0 + (n - 1) * rho)


def daily_returns(trades, calendar):
    """Net R per market day as a vector on the calendar, booked at exit -
    the day the account books it. A date off the calendar (should not exist)
    lands on the nearest following day rather than being dropped silently."""
    idx = {d: i for i, d in enumerate(calendar)}
    v = np.zeros(len(calendar))
    last = len(calendar) - 1
    for t in trades:
        i = idx.get(t["exit_date"])
        if i is None:
            i = min(int(np.searchsorted(np.array(calendar),
                                        t["exit_date"])), last)
        v[i] += t["net_r"]
    return v


def by_entry_day(trades, calendar):
    """One array of net R per calendar day, keyed by ENTRY date - the day the
    band made its decision - for the day-cluster bootstrap."""
    idx = {d: i for i, d in enumerate(calendar)}
    days = [[] for _ in calendar]
    for t in trades:
        i = idx.get(t["entry_date"])
        if i is not None:
            days[i].append(t["net_r"])
    return [np.asarray(d) for d in days]


def paired_delta_sr(days_a, days_b, reps=10000, seed=20260822, min_n=5):
    """Day-cluster bootstrap of SR(a) - SR(b) for two cells sharing a
    calendar. Each rep resamples MARKET DAYS with replacement and takes both
    cells' trades on those days, so shared trades cancel in the difference and
    same-day cross-market correlation stays inside its cluster.

    Returns mean, se, ci_lo/ci_hi (2.5/97.5 percentiles), p_le_0 (share of
    reps where the delta was <= 0) and the rep count that produced usable
    Sharpes on both sides."""
    n_days = len(days_a)
    if n_days != len(days_b):
        raise ValueError("cells must share one calendar")
    rng = np.random.default_rng(seed)
    deltas = []
    for _ in range(reps):
        pick = rng.integers(0, n_days, n_days)
        a = [days_a[i] for i in pick if days_a[i].size]
        b = [days_b[i] for i in pick if days_b[i].size]
        if not a or not b:
            continue
        ra, rb = np.concatenate(a), np.concatenate(b)
        if ra.size < min_n or rb.size < min_n:
            continue
        sda, sdb = ra.std(ddof=1), rb.std(ddof=1)
        if sda == 0.0 or sdb == 0.0:
            continue
        deltas.append(ra.mean() / sda - rb.mean() / sdb)
    if len(deltas) < reps // 2:
        return None
    d = np.asarray(deltas)
    return dict(mean=float(d.mean()), se=float(d.std(ddof=1)),
                ci_lo=float(np.percentile(d, 2.5)),
                ci_hi=float(np.percentile(d, 97.5)),
                p_le_0=float(np.mean(d <= 0.0)), reps=int(d.size))
