# research_1m_exit_profile.py
#
# The pre-registered exit-timing study of docs/exit_timing_preregistration.md
# (2026-08-28): the forward-excursion PROFILE of every taken quickfix1m1dc
# trade over a FIXED list of horizons, against a surrogate null, read for
# the predictions P1-P5 written down before this file existed. It is a
# READING like research_1m_rule1.py - no engine passes; it loads the
# blotters and each market's bars/days/files through run_1m.market_inputs
# and does arithmetic on them.
#
# What it measures, per trade and per horizon (section 5 of the doc):
#   x(h)        signed excursion from the FIRST-REVERSAL price (entry_first,
#               not the slipped fill) to the price at the horizon, in the
#               trade's favour. Clock and activation horizons take the close
#               of the last on-book bar at or before the instant; settlement
#               horizons take the day's settlement price - the price the
#               engine books close1 at and Socrates shows as the close.
#   mfe / mae   running best / worst excursion over the bars from the entry
#               bar (inclusive) to the horizon (bars strictly before a
#               settlement instant).
#   SIGNAL PATH (no stop): as if no stop existed - the market after a
#               qualifying trigger (primary for P1, P2). Internally
#               "unconstrained".
#   TRADE PATH (stop as booked): frozen at the trade's OWN stop - the one
#               the blotter recorded at entry, so the 4th/5th ladder stop
#               for variant 2 and the hybrid stop for variant 5 - from the
#               first bar AFTER the entry bar whose high/low prints it (the
#               position, still open with its stop, marked at each moment;
#               primary for P3). Internally "truncated". Wording: Lode,
#               2026-08-28.
#               Precedence follows the engine exactly: a stop on the entry bar
#               never counts, and on a settlement bar the settlement is booked
#               first, so a stop counts for a settlement horizon only if its
#               bar's time is strictly before that settle_ts.
#   denominators: R (rpu, level to stop) and the trailing trading-day range at
#               entry (rpu / rpu_range_ratio where the ratio is recorded).
#
# Horizons (section 6, amendment A1): 30m, 1h, 2h, 4h from entry_ts; then
# settleN (the settlement price), closeN (the session's last bar, its close)
# and openN (the session's first bar, its open) for day 0 (the entry day)
# and days 1-7 (days 1-3 until amendment A2, 2026-08-30). settle1 is the
# engine's close1 exit moment.
#
# Null (section 6): each trade's geometry - side, rpu, stop distance - placed
# at random on-book minutes of the SAME market, the same session time-of-day
# within 30 minutes, a DIFFERENT trading day; B placements in total; the
# observed mean profile is reported with its percentile among null means.
#
# Uncertainty: a day-cluster bootstrap (clusters = entry dates), the same
# device sharpe_stats uses, on m(h) and on differences between horizons.
#
# Agreement check (section 10): for every close1 and stop trade the
# stop-truncated x at the next settlement, in R, must equal the blotter's
# gross_r plus the entry slippage in R - the profile reproduces the engine's
# own booking or the run refuses to write. Same discipline as the ratio pane
# against the blotter.
#
# THIS SCRIPT ONLY ADDS FILES. It writes output/quickfix1m1dc_exit_profile.txt
# and .json and touches nothing else in output/ (Lode, 2026-08-28).
#
# Usage:  python research_1m_exit_profile.py [--no-null] [--null-b N]
#                                             [--reps N] [--keys K ...]
#         --keys restricts the markets loaded (debug only; the reading then
#         says so in its header and is not a verdict).

import argparse
import json
import math
import sys
from bisect import bisect_right
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine_1m  # noqa: E402

DOC = "docs/exit_timing_preregistration.md"
OUT_TXT = HERE / "output" / "quickfix1m1dc_exit_profile.txt"
OUT_JSON = HERE / "output" / "quickfix1m1dc_exit_profile.json"
BLOTTER = HERE / "output" / "quickfix1m1dc_all.json"
MATRIX = HERE / "output" / "quickfix1m1dc_matrix.json"
RULE1 = HERE / "output" / "quickfix1m1dcRule1.json"

SEED = 20260828
BOOT_REPS = 10000
NULL_B = 10000            # total placements (5,000 fallback per the doc)
NULL_MEAN_REPS = 5000     # draws of one placement per trade -> null mean
NULL_TOD_MINUTES = 30     # same session time-of-day, within this
MIN_N = 30                # reading rule 1: below this a horizon is dimmed
FLAT_R = 0.25             # reading rule / decision 1: point estimate cap
TOP_SHARE_MAX = 35.0      # reading rule 2: not carried by one market
DISCONTINUED = frozenset(["CC", "KC", "UDOW", "UNG", "USO"])
SECONDARY_CELL = "variant 5"
PATH_LABEL = {"unconstrained": "signal path (no stop)",
              "truncated": "trade path (stop as booked)"}
STOP_LABEL = {"ladder": "4th/5th stop", "ladder_or_extreme": "hybrid stop",
              "extreme": "wick stop"}     # run_1m_matrix.STOPS naming

NS_MIN = 60 * 10**9

# (name, kind, arg) - kind: clock (minutes after entry); settle / open /
# close (trading days after the entry day, which is day 0). AMENDMENT A1
# (Lode, 2026-08-28): the activation horizon is gone - the Socrates update
# lands at a different point of the session per market (9h35 into a CME
# session, before the ETF open, 5 minutes into Sugar; charter's
# site/1m/timing.html) - and every session's open, settlement and close are
# in, for the entry day and the three that follow.
# AMENDMENT A2 (Lode, 2026-08-30): the day horizon runs to day 7 instead
# of day 3 - the same three structural moments per session, four more
# sessions of them. Nothing else moves: the clock horizons, the deciding
# horizons (settle0, settle1) and every reading rule are as under A1.
HORIZON_DAYS = 7
HORIZONS = [
    ("30m", "clock", 30),
    ("1h", "clock", 60),
    ("2h", "clock", 120),
    ("4h", "clock", 240),
    ("settle0", "settle", 0),
    ("close0", "close", 0),
]
for _d in range(1, HORIZON_DAYS + 1):
    HORIZONS += [(f"open{_d}", "open", _d), (f"settle{_d}", "settle", _d),
                 (f"close{_d}", "close", _d)]
H_NAMES = [h[0] for h in HORIZONS]
H_ENTRY_SETTLE = "settle0"
H_NEXT_SETTLE = "settle1"       # the close1 exit of the engine (its
                                # `reason` label; NOT the close1 horizon
                                # here, which is session 1's last bar)
DECIDING = (H_ENTRY_SETTLE, H_NEXT_SETTLE)   # reading rule 2's horizons


class SpliceError(ValueError):
    """A horizon would cross a contract change. The doc says a splice
    inside the horizon window must raise (section 10)."""


# --------------------------------------------------------------------------
# the market as arrays
# --------------------------------------------------------------------------

class MarketRun:
    """One market's days flattened into arrays, keeping the day structure.

    ts is int64 ns UTC. day_start/day_end index the bar arrays (end is
    exclusive). settle_ts is int64 ns, settle_price a float, contract the
    day's symbol. files are the activation instants in ns, sorted."""

    def __init__(self, days, files):
        ts, o, h, l, c = [], [], [], [], []
        self.day_start, self.day_end = [], []
        self.day_date, self.contract = [], []
        self.settle_ts, self.settle_price = [], []
        for d in days:
            self.day_start.append(len(ts))
            for bts, bo, bh, bl, bc in d.bars:
                ts.append(int(pd.Timestamp(bts).value))
                o.append(bo); h.append(bh); l.append(bl); c.append(bc)
            self.day_end.append(len(ts))
            self.day_date.append(d.date)
            self.contract.append(d.contract)
            self.settle_ts.append(int(pd.Timestamp(d.settle_ts).value))
            self.settle_price.append(float(d.settle_price))
        self.ts = np.asarray(ts, dtype=np.int64)
        self.open = np.asarray(o, dtype=float)
        self.high = np.asarray(h, dtype=float)
        self.low = np.asarray(l, dtype=float)
        self.close = np.asarray(c, dtype=float)
        if np.any(np.diff(self.ts) <= 0):
            raise ValueError("bars must be strictly increasing in time")
        self.activations = sorted(int(pd.Timestamp(f.activation_ts).value)
                                  for f in files)
        self.n_days = len(days)

    def day_of(self, i):
        """Index of the day holding bar i."""
        k = bisect_right(self.day_start, i) - 1
        if k < 0 or i >= self.day_end[k]:
            raise IndexError("bar outside every day")
        return k

    def bar_index(self, ts_ns):
        j = int(np.searchsorted(self.ts, ts_ns))
        if j >= len(self.ts) or self.ts[j] != ts_ns:
            raise KeyError("no bar at that instant")
        return j

    def last_bar_at_or_before(self, ts_ns):
        j = int(np.searchsorted(self.ts, ts_ns, side="right")) - 1
        return j

    def next_activation_after(self, ts_ns):
        """The activation of the levels file AFTER the one live at ts_ns:
        the first activation strictly greater than ts_ns. None past the
        last file."""
        k = bisect_right(self.activations, ts_ns)
        return self.activations[k] if k < len(self.activations) else None


def stop_bar(run, i0, side, stop, upto_excl):
    """First bar index k with i0 < k < upto_excl whose high (short) or low
    (long) prints the stop; None if none. The entry bar never counts (the
    engine tests the stop only for bts > entry_ts)."""
    lo, hi = i0 + 1, upto_excl
    if hi <= lo:
        return None
    if side == "short":
        hits = np.nonzero(run.high[lo:hi] >= stop)[0]
    else:
        hits = np.nonzero(run.low[lo:hi] <= stop)[0]
    return int(lo + hits[0]) if hits.size else None


def excursions(run, i0, j_incl, side, ref):
    """(mfe, mae) over bars i0..j_incl inclusive, signed in the trade's
    favour from ref."""
    hs = run.high[i0:j_incl + 1]
    ls = run.low[i0:j_incl + 1]
    if side == "short":
        return float(ref - ls.min()), float(hs.max() - ref)
    return float(hs.max() - ref), float(ref - ls.min())


def profile_at(run, i0, side, entry_first, rpu, stop, strict=True):
    """The profile of one geometry placed at bar i0 - dict horizon name ->
    dict(x, mfe, mae, x_trunc, mfe_trunc, mae_trunc, stopped, flag, ts) in
    PRICE units, or dict(reason=...) where the horizon does not exist.

    `strict=True` raises SpliceError when a settlement horizon crosses a
    contract change; strict=False records reason="splice" instead."""
    sign = -1.0 if side == "short" else 1.0
    d0 = run.day_of(i0)
    entry_ts = int(run.ts[i0])
    out = {}

    def value_at(j):
        return float(sign * (run.close[j] - entry_first))

    def truncated(j_incl, limit_excl, settle_value=None):
        """The stop-truncated reading up to bar j_incl (inclusive), with a
        stop counting only if it printed on a bar with index < limit_excl."""
        k = stop_bar(run, i0, side, stop, limit_excl)
        if k is not None:
            mfe, _mae = excursions(run, i0, k, side, entry_first)
            return dict(x=-float(rpu), mfe=mfe, mae=float(rpu), stopped=True,
                        stop_ts=int(run.ts[k]))
        mfe, mae = excursions(run, i0, j_incl, side, entry_first)
        x = (settle_value if settle_value is not None else value_at(j_incl))
        return dict(x=x, mfe=mfe, mae=mae, stopped=False, stop_ts=None)

    for name, kind, arg in HORIZONS:
        if kind == "clock":
            instant = entry_ts + arg * NS_MIN
            j = run.last_bar_at_or_before(instant)
            if j < i0:
                out[name] = dict(reason="before entry")
                continue
            dj = run.day_of(j)
            if run.contract[dj] != run.contract[d0]:
                if strict:
                    raise SpliceError(name)
                out[name] = dict(reason="splice")
                continue
            flag = None
            if j == run.day_end[dj] - 1 and instant > run.ts[j]:
                flag = "session ended"
            mfe, mae = excursions(run, i0, j, side, entry_first)
            tr = truncated(j, j + 1)
            out[name] = dict(x=value_at(j), mfe=mfe, mae=mae,
                             x_trunc=tr["x"], mfe_trunc=tr["mfe"],
                             mae_trunc=tr["mae"], stopped=tr["stopped"],
                             stop_ts=tr["stop_ts"], flag=flag,
                             ts=int(instant), bar_ts=int(run.ts[j]))
            continue
        dk = d0 + arg
        if dk >= run.n_days:
            out[name] = dict(reason="data end")
            continue
        if run.contract[dk] != run.contract[d0]:
            if strict:
                raise SpliceError(name)
            out[name] = dict(reason="splice")
            continue
        if run.day_end[dk] <= run.day_start[dk]:
            out[name] = dict(reason="no bars")
            continue
        if kind == "settle":
            sts = run.settle_ts[dk]
            sval = float(sign * (run.settle_price[dk] - entry_first))
            # bars strictly before the settlement instant
            j = run.last_bar_at_or_before(sts - 1)
            if j < i0:
                j = i0
            limit = int(np.searchsorted(run.ts, sts))   # first bar >= sts
            mfe, mae = excursions(run, i0, j, side, entry_first)
            tr = truncated(j, limit, settle_value=sval)
            out[name] = dict(x=sval, mfe=mfe, mae=mae,
                             x_trunc=tr["x"], mfe_trunc=tr["mfe"],
                             mae_trunc=tr["mae"], stopped=tr["stopped"],
                             stop_ts=tr["stop_ts"], flag=None,
                             ts=int(sts), bar_ts=int(run.ts[j]))
        elif kind == "open":
            # the session's first print: the open of its first bar. Bars
            # strictly before it carry the excursions; a stop on the open
            # bar itself prints AFTER the open and does not count here.
            j = run.day_start[dk]
            oval = float(sign * (run.open[j] - entry_first))
            mfe, mae = excursions(run, i0, j - 1, side, entry_first)
            mfe, mae = max(mfe, oval), max(mae, -oval)
            tr = truncated(j - 1, j, settle_value=oval)
            if tr["stopped"]:
                tr_mfe, tr_mae = tr["mfe"], tr["mae"]
            else:
                tr_mfe, tr_mae = max(tr["mfe"], oval), max(tr["mae"], -oval)
            out[name] = dict(x=oval, mfe=mfe, mae=mae,
                             x_trunc=tr["x"], mfe_trunc=tr_mfe,
                             mae_trunc=tr_mae, stopped=tr["stopped"],
                             stop_ts=tr["stop_ts"], flag=None,
                             ts=int(run.ts[j]), bar_ts=int(run.ts[j]))
        else:                                       # close: the last bar
            j = run.day_end[dk] - 1
            mfe, mae = excursions(run, i0, j, side, entry_first)
            tr = truncated(j, j + 1)
            out[name] = dict(x=value_at(j), mfe=mfe, mae=mae,
                             x_trunc=tr["x"], mfe_trunc=tr["mfe"],
                             mae_trunc=tr["mae"], stopped=tr["stopped"],
                             stop_ts=tr["stop_ts"], flag=None,
                             ts=int(run.ts[j]), bar_ts=int(run.ts[j]))
    return out


# --------------------------------------------------------------------------
# trades
# --------------------------------------------------------------------------

def trade_profile(run, t, strict=False):
    """Profile of a blotter trade on its market's run. Raises if the trade
    cannot be placed (no bar at entry_ts, wrong contract, tightened stop)."""
    if t.get("stop_tightened") is not None:
        raise ValueError("tightened stops are outside this study "
                         "(tighten=False in every cell it reads)")
    entry_ns = int(pd.Timestamp(t["entry_ts"]).value)
    i0 = run.bar_index(entry_ns)
    d0 = run.day_of(i0)
    if run.contract[d0] != t["contract"]:
        raise ValueError(f"entry bar sits in {run.contract[d0]}, trade says "
                         f"{t['contract']}")
    if run.day_date[d0] != date.fromisoformat(t["entry_date"]):
        raise ValueError("entry bar's session is not the trade's entry_date")
    return profile_at(run, i0, t["side"], t["entry_first"], t["rpu"],
                      t["stop"], strict=strict)


def agreement_check(t, prof, tick):
    """The stop-truncated x at the next settlement, in R, must equal the
    blotter's gross_r plus the fill's distance from the level in R - the
    entry slippage (2 ticks / rpu) on a touch fill, the gap-through
    distance plus slippage on a fill from the open (2 of 100 published
    trades; PA 2026-05-21, PL 2026-08-17). The profile measures from the
    LEVEL either way; the check translates. For a stop trade the stop bar
    must be the exit bar. Returns None when it agrees, else a message."""
    h = prof.get(H_NEXT_SETTLE)
    if (h is None or "reason" in h) and t["reason"] == "stop"             and t["exit_date"] == t["entry_date"]:
        # A window-end entry (run_1m's published pass admits them since
        # 2026-08-30) stopped inside its own session has no next
        # settlement in the data yet; the entry day's last print carries
        # the whole session, so the booking is checked there.
        h = prof.get("close0")
    if h is None or "reason" in h:
        return f"no next settlement horizon ({h and h.get('reason')})"
    sign = -1.0 if t["side"] == "short" else 1.0
    fill_r = sign * (t["entry"] - t["entry_first"]) / t["rpu"]
    slip_r = engine_1m.ENTRY_SLIP_TICKS * tick / t["rpu"]
    if fill_r + 1e-9 < slip_r:
        return f"fill {t['entry']} is nearer the level than the slippage"
    want = t["gross_r"] + fill_r
    got = h["x_trunc"] / t["rpu"]
    if abs(got - want) > 1e-3:
        return (f"x_trunc/rpu {got:.4f} != gross_r + fill offset {want:.4f} "
                f"(reason {t['reason']})")
    if t["reason"] == "stop":
        if not h["stopped"]:
            return "blotter says stop, profile never printed it"
        if h["stop_ts"] != int(pd.Timestamp(t["exit_ts"]).value):
            return "stop bar differs from the blotter's exit bar"
    elif t["reason"] == "close1" and h["stopped"]:
        return "blotter says close1, profile printed the stop first"
    return None


def profile_rows(trades, runs, ticks, strict=False):
    """Profiles for a trade list -> (rows, failures). A row carries the
    trade's identity, rpu, ratio, market and its horizon dicts in R AND in
    range units."""
    rows, failures = [], []
    for t in trades:
        key = t["market"]
        run = runs.get(key)
        if run is None:
            failures.append((t, "market not loaded"))
            continue
        try:
            prof = trade_profile(run, t, strict=strict)
        except (KeyError, ValueError, IndexError) as e:
            failures.append((t, f"{type(e).__name__}: {e}"))
            continue
        msg = agreement_check(t, prof, ticks[key])
        if msg is not None:
            failures.append((t, "AGREEMENT: " + msg))
            continue
        rows.append(dict(
            market=key, side=t["side"], contract=t["contract"],
            entry_ts=t["entry_ts"], entry_date=t["entry_date"],
            exit_date=t["exit_date"], reason=t["reason"],
            rpu=t["rpu"], ratio=t.get("rpu_range_ratio"),
            gross_r=t["gross_r"], net_r=t["net_r"],
            horizons=prof))
    return rows, failures


def series(rows, name, field, denom):
    """Per-trade values of one horizon field in one denominator (R or
    range), with their entry-date clusters and markets. Trades where the
    horizon does not exist, or the range denominator is unknown, are
    left out."""
    vals, clusters, markets = [], [], []
    for r in rows:
        h = r["horizons"].get(name)
        if h is None or "reason" in h:
            continue
        if denom == "R":
            d = r["rpu"]
        else:
            if r["ratio"] is None:
                continue
            d = r["rpu"] / r["ratio"]
        vals.append(h[field] / d)
        clusters.append(r["entry_date"])
        markets.append(r["market"])
    return np.asarray(vals, dtype=float), clusters, markets


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------

def cluster_bootstrap_mean(values, clusters, reps=BOOT_REPS, seed=SEED):
    """Day-cluster bootstrap of the mean: resample entry dates with
    replacement, take every value on the drawn dates. Returns mean, ci_lo,
    ci_hi (2.5/97.5), se, p_le_0."""
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return None
    keys = sorted(set(clusters))
    groups = {k: [] for k in keys}
    for v, c in zip(values, clusters):
        groups[c].append(v)
    groups = [np.asarray(groups[k]) for k in keys]
    rng = np.random.default_rng(seed)
    n = len(groups)
    means = np.empty(reps)
    for r in range(reps):
        pick = rng.integers(0, n, n)
        cat = np.concatenate([groups[i] for i in pick])
        means[r] = cat.mean()
    return dict(mean=float(values.mean()), ci_lo=float(np.percentile(means, 2.5)),
                ci_hi=float(np.percentile(means, 97.5)),
                se=float(means.std(ddof=1)), p_le_0=float(np.mean(means <= 0)))


def cluster_bootstrap_diff(a_vals, a_clusters, b_vals, b_clusters,
                           reps=BOOT_REPS, seed=SEED):
    """Day-cluster bootstrap of mean(a) - mean(b) for two DISJOINT trade
    sets on one calendar of entry dates."""
    keys = sorted(set(a_clusters) | set(b_clusters))
    ga = {k: [] for k in keys}
    gb = {k: [] for k in keys}
    for v, c in zip(a_vals, a_clusters):
        ga[c].append(v)
    for v, c in zip(b_vals, b_clusters):
        gb[c].append(v)
    ga = [np.asarray(ga[k]) for k in keys]
    gb = [np.asarray(gb[k]) for k in keys]
    rng = np.random.default_rng(seed)
    n = len(keys)
    diffs = []
    for _ in range(reps):
        pick = rng.integers(0, n, n)
        a = np.concatenate([ga[i] for i in pick])
        b = np.concatenate([gb[i] for i in pick])
        if a.size == 0 or b.size == 0:
            continue
        diffs.append(a.mean() - b.mean())
    if len(diffs) < reps // 2:
        return None
    d = np.asarray(diffs)
    return dict(mean=float(np.mean(a_vals) - np.mean(b_vals)),
                ci_lo=float(np.percentile(d, 2.5)),
                ci_hi=float(np.percentile(d, 97.5)),
                p_le_0=float(np.mean(d <= 0)), reps=len(d))


def horizon_stats(rows, path, denom):
    """Per horizon: n, mean, sd, hit rate, sharpe, median, mfe, mae,
    e-ratio, top market share. path in {'unconstrained', 'truncated'}."""
    xf, mf, af = (("x", "mfe", "mae") if path == "unconstrained"
                  else ("x_trunc", "mfe_trunc", "mae_trunc"))
    out = {}
    for name in H_NAMES:
        x, cl, mk = series(rows, name, xf, denom)
        if x.size == 0:
            out[name] = dict(n=0)
            continue
        mfe, _, _ = series(rows, name, mf, denom)
        mae, _, _ = series(rows, name, af, denom)
        sd = float(x.std(ddof=1)) if x.size > 1 else float("nan")
        by_m = {}
        for v, m in zip(x, mk):
            by_m[m] = by_m.get(m, 0.0) + v
        total = float(x.sum())
        top_m, top_v = max(by_m.items(), key=lambda kv: kv[1])
        top_share = (100.0 * top_v / total) if total > 0 else None
        out[name] = dict(
            n=int(x.size), mean=float(x.mean()), sd=sd,
            hit=float(np.mean(x > 0)),
            sharpe=(float(x.mean() / sd) if sd and sd > 0 else None),
            median=float(np.median(x)),
            mfe=float(mfe.mean()), mae=float(mae.mean()),
            e_ratio=(float(mfe.mean() / mae.mean()) if mae.mean() > 0
                     else None),
            top_market=top_m, top_share=top_share,
            flagged=sum(1 for r in rows
                        if (r["horizons"].get(name) or {}).get("flag")))
    return out


# --------------------------------------------------------------------------
# the null
# --------------------------------------------------------------------------

def null_placements(run, i0, side, rpu, n_place, rng, tod_minutes=NULL_TOD_MINUTES,
                    attempts=25):
    """n_place random placements of the geometry at bar i0 on the same
    market: a different trading day, the same session time-of-day within
    tod_minutes. Returns a list of profile dicts (strict=False)."""
    d0 = run.day_of(i0)
    offset = int(run.ts[i0] - run.ts[run.day_start[d0]])
    out = []
    tol = tod_minutes * NS_MIN
    for _ in range(n_place):
        for _try in range(attempts):
            dk = int(rng.integers(0, run.n_days))
            if dk == d0 or run.day_end[dk] <= run.day_start[dk]:
                continue
            target = run.ts[run.day_start[dk]] + offset
            lo = int(np.searchsorted(run.ts[run.day_start[dk]:run.day_end[dk]],
                                     target - tol)) + run.day_start[dk]
            hi = int(np.searchsorted(run.ts[run.day_start[dk]:run.day_end[dk]],
                                     target + tol, side="right")) + run.day_start[dk]
            if hi <= lo:
                continue
            k = int(rng.integers(lo, hi))
            ref = float(run.close[k])
            stop = ref + rpu if side == "short" else ref - rpu
            out.append(profile_at(run, k, side, ref, rpu, stop, strict=False))
            break
    return out


def null_profiles(rows, runs, total_b, seed=SEED):
    """Per trade, a list of placement profiles; ~total_b placements in
    all. Each row's index in `rows` keys the result."""
    rng = np.random.default_rng(seed)
    per = max(1, int(math.ceil(total_b / max(1, len(rows)))))
    out = []
    for r in rows:
        run = runs[r["market"]]
        i0 = run.bar_index(int(pd.Timestamp(r["entry_ts"]).value))
        out.append(null_placements(run, i0, r["side"], r["rpu"], per, rng))
    return out


def null_mean_percentiles(rows, placements, path, denom, reps=NULL_MEAN_REPS,
                          seed=SEED):
    """For each horizon: the observed mean and its percentile in the
    distribution of null means (each rep draws one placement per trade)."""
    xf = "x" if path == "unconstrained" else "x_trunc"
    rng = np.random.default_rng(seed + 1)
    out = {}
    for name in H_NAMES:
        obs, _, _ = series(rows, name, xf, denom)
        if obs.size < 1:
            out[name] = dict(n=0)
            continue
        per_trade = []
        for r, pl in zip(rows, placements):
            h = r["horizons"].get(name)
            if h is None or "reason" in h:
                continue
            if denom == "R":
                d = r["rpu"]
            else:
                if r["ratio"] is None:
                    continue
                d = r["rpu"] / r["ratio"]
            vals = [p[name][xf] / d for p in pl
                    if p.get(name) is not None and "reason" not in p[name]]
            if vals:
                per_trade.append(np.asarray(vals))
        if not per_trade:
            out[name] = dict(n=int(obs.size), null_reps=0)
            continue
        means = np.empty(reps)
        for i in range(reps):
            means[i] = np.mean([v[rng.integers(0, v.size)] for v in per_trade])
        out[name] = dict(n=int(obs.size), observed=float(obs.mean()),
                         null_mean=float(means.mean()),
                         null_sd=float(means.std(ddof=1)),
                         percentile=float(np.mean(means <= obs.mean())),
                         null_reps=int(reps), placements=int(
                             sum(v.size for v in per_trade)))
    return out


# --------------------------------------------------------------------------
# predictions
# --------------------------------------------------------------------------

def flat_rule(boot, cap=FLAT_R):
    """Decision 1: flat = 95% interval covers zero AND point estimate under
    cap. Returns (verdict, note)."""
    if boot is None:
        return "indeterminate", "no bootstrap"
    covers = boot["ci_lo"] <= 0.0 <= boot["ci_hi"]
    small = boot["mean"] < cap
    if covers and small:
        note = ""
        if 0.10 <= boot["mean"] < cap:
            note = ("point estimate between 0.10R and 0.25R: flat enough to "
                    "exit, not 'no drift' (doc s.6)")
        return "flat", note
    if not covers and boot["mean"] >= cap:
        return "rising", ""
    if covers and not small:
        return "cannot decide", "interval covers zero, point estimate >= cap"
    return "declining" if boot["mean"] < 0 else "rising", ""


def per_trade_delta(rows, h_a, h_b, field, denom):
    """x(h_a) - x(h_b) per trade where both exist."""
    vals, cl = [], []
    for r in rows:
        a, b = r["horizons"].get(h_a), r["horizons"].get(h_b)
        if not a or not b or "reason" in a or "reason" in b:
            continue
        if denom == "R":
            d = r["rpu"]
        else:
            if r["ratio"] is None:
                continue
            d = r["rpu"] / r["ratio"]
        vals.append((a[field] - b[field]) / d)
        cl.append(r["entry_date"])
    return np.asarray(vals), cl


def read_predictions(rows, stats_u, stats_t, denom, reps=BOOT_REPS):
    """P1, P2, P3 on one sample in one denominator. Returns a dict of
    verdict dicts; 'dimmed' where n < MIN_N.

    Amendment A1: P1's flat clause was defined on the activation horizon,
    which is gone, so it is RETIRED - the first reading's verdict stands
    (doc s.12). What remains of P1 is the rise through the entry session
    (settle0 - 30m); the day-1 session (settle1 - settle0) and the
    overnight gap (open1 - close0) are printed as DESCRIPTIVE deltas, not
    as pre-registered tests. P2 is read on the full list and is stricter:
    the Sharpe peak must sit at or before settle1 AND every later horizon
    must be lower."""
    out = {}
    rise, cl_r = per_trade_delta(rows, H_ENTRY_SETTLE, "30m", "x", denom)
    day1, cl_1 = per_trade_delta(rows, H_NEXT_SETTLE, H_ENTRY_SETTLE, "x", denom)
    gap, cl_g = per_trade_delta(rows, "open1", "close0", "x", denom)
    b_rise = cluster_bootstrap_mean(rise, cl_r, reps) if rise.size else None
    b_day1 = cluster_bootstrap_mean(day1, cl_1, reps) if day1.size else None
    b_gap = cluster_bootstrap_mean(gap, cl_g, reps) if gap.size else None
    rose = (b_rise is not None and b_rise["mean"] > 0 and b_rise["ci_lo"] > 0)
    p1 = dict(n_rise=int(rise.size), rise=b_rise, rose=rose,
              n_day1=int(day1.size), day1=b_day1,
              n_gap=int(gap.size), gap=b_gap,
              verdict="retired (flat clause needs the activation horizon, "
                      "dropped by amendment A1; the first reading stands)")
    out["P1"] = p1
    sh = {n: stats_u[n].get("sharpe") for n in H_NAMES}
    ns = {n: stats_u[n].get("n", 0) for n in H_NAMES}
    avail = [n for n in H_NAMES if sh[n] is not None and ns[n] >= MIN_N]
    i_ns = H_NAMES.index(H_NEXT_SETTLE)
    later = [n for n in avail if H_NAMES.index(n) > i_ns]
    p2 = dict(sharpe=sh, n=ns)
    if H_NEXT_SETTLE not in avail or not later:
        p2["verdict"] = "dimmed"
    else:
        peak = max(avail, key=lambda n: sh[n])
        i_peak = H_NAMES.index(peak)
        declines = all(sh[n] < sh[H_NEXT_SETTLE] for n in later)
        p2.update(peak=peak, declines=declines, later=later)
        p2["verdict"] = ("not rejected" if i_peak <= i_ns and declines
                         else "rejected (H2)" if i_peak > i_ns
                         else "indeterminate")
    out["P2"] = p2
    stops = [r for r in rows if r["reason"] == "stop"]
    inside = sum(1 for r in stops if r["exit_date"] == r["entry_date"])
    p3 = dict(n_stops=len(stops), inside=inside,
              share=(inside / len(stops) if stops else None))
    if len(stops) < MIN_N:
        p3["verdict"] = "dimmed"
    else:
        p3["verdict"] = ("not rejected" if inside > len(stops) / 2
                         else "rejected")
    out["P3"] = p3
    return out


def top_share_ok(stats, names=DECIDING):
    """Reading rule 2: the deciding horizons are not carried by one market."""
    shares = [stats[n].get("top_share") for n in names if stats[n].get("n")]
    return all(s is None or s < TOP_SHARE_MAX for s in shares), shares


def combine(verdicts):
    """Reading rules 4 and 6: a prediction's verdict across universes and
    denominators - all must agree on 'not rejected' or 'rejected'; any
    dimmed leaves it dimmed; anything else is indeterminate."""
    vs = [v["verdict"] for v in verdicts]
    if all(v.startswith("retired") for v in vs):
        return vs[0]
    if any(v == "dimmed" for v in vs):
        return "dimmed"
    if all(v == "not rejected" for v in vs):
        return "not rejected"
    if all(v.startswith("rejected") for v in vs):
        return vs[0]
    return "indeterminate (universes/denominators disagree)"


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def load_samples():
    """The trade lists this study reads (doc section 4)."""
    blotter = json.loads(BLOTTER.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    samples = {
        "variant 2 (published)": [t for t in blotter["trades"]
                                  if t["reason"] != "data_end"],
        SECONDARY_CELL: [t for t in matrix["trades"][SECONDARY_CELL]
                         if t["reason"] != "data_end"],
    }
    anchors = {
        "variant 2 (published)": STOP_LABEL[blotter["params"]["stop_mode"]],
        SECONDARY_CELL: STOP_LABEL[
            matrix["variants"][SECONDARY_CELL]["dials"]["stop_mode"]],
    }
    rule1 = (json.loads(RULE1.read_text(encoding="utf-8"))
             if RULE1.exists() else None)
    return samples, anchors, rule1, blotter, matrix


def load_runs(keys):
    import run_1m
    runs, ticks, excluded = {}, {}, {}
    for key in sorted(keys):
        inputs, exc = run_1m.market_inputs(key)
        if inputs is None:
            excluded[key] = exc
            continue
        days, files, tick, _note = inputs
        runs[key] = MarketRun(days, files)
        ticks[key] = tick
    return runs, ticks, excluded


# --------------------------------------------------------------------------
# the reading
# --------------------------------------------------------------------------

def fnum(x, w=7, p=3):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return " " * (w - 3) + "n/a"
    return f"{x:{w}.{p}f}"


def table(stats, w):
    w(f"  {'horizon':16} {'n':>4} {'mean':>7} {'sd':>7} {'hit':>6} "
      f"{'sharpe':>7} {'median':>7} {'mfe':>7} {'mae':>7} {'e-rat':>6} "
      f"{'top':>5} {'share':>6}  flag")
    for name in H_NAMES:
        s = stats[name]
        if s.get("n", 0) == 0:
            w(f"  {name:16} {0:>4}  (no horizon)")
            continue
        dim = " (dimmed, n<30)" if s["n"] < MIN_N else ""
        fl = f"{s['flagged']} session-ended" if s.get("flagged") else ""
        w(f"  {name:16} {s['n']:>4} {fnum(s['mean'])} {fnum(s['sd'])} "
          f"{fnum(s['hit'], 6, 2)} {fnum(s['sharpe'])} {fnum(s['median'])} "
          f"{fnum(s['mfe'])} {fnum(s['mae'])} {fnum(s['e_ratio'], 6, 2)} "
          f"{s['top_market']:>5} {fnum(s['top_share'], 6, 1)}  {fl}{dim}")


def boot_line(b):
    if b is None:
        return "n/a"
    return (f"mean {b['mean']:+.3f}  95% [{b['ci_lo']:+.3f}, {b['ci_hi']:+.3f}]"
            f"  P(<=0) {b['p_le_0']:.3f}")


def sample_reading(label, rows, runs, args, w, result, anchor=""):
    """Everything for one sample on both universes and both denominators."""
    universes = {"all": rows,
                 "17 markets": [r for r in rows
                                if r["market"] not in DISCONTINUED]}
    res = {}
    for uname, urows in universes.items():
        w()
        w(f"== {label} | {anchor} | universe: {uname} | {len(urows)} trades")
        ures = {}
        for denom in ("R", "range"):
            su = horizon_stats(urows, "unconstrained", denom)
            st = horizon_stats(urows, "truncated", denom)
            w()
            w(f"-- {PATH_LABEL['unconstrained']}, {denom} units")
            table(su, w)
            w(f"-- {PATH_LABEL['truncated']} - {anchor}, {denom} units")
            table(st, w)
            preds = read_predictions(urows, su, st, denom, args.reps)
            ok, shares = top_share_ok(su)
            p1, p2, p3 = preds["P1"], preds["P2"], preds["P3"]
            w()
            w(f"  P1 rise (settle0 - 30m):        {boot_line(p1['rise'])}"
              f"  n={p1['n_rise']}  rose={p1['rose']}")
            w(f"  descriptive: day-1 session (settle1 - settle0): "
              f"{boot_line(p1['day1'])}  n={p1['n_day1']}")
            w(f"  descriptive: overnight gap (open1 - close0):    "
              f"{boot_line(p1['gap'])}  n={p1['n_gap']}")
            w(f"  P1 verdict: {p1['verdict']}")
            if "peak" in p2:
                w(f"  P2 sharpe peak at '{p2['peak']}', every later horizon "
                  f"lower than settle1: {p2['declines']} -> {p2['verdict']}")
            else:
                w(f"  P2 verdict: {p2['verdict']}")
            w(f"  P3 stops inside the entry session: {p3['inside']}/"
              f"{p3['n_stops']}"
              + (f" = {100 * p3['share']:.0f}%" if p3['share'] is not None
                 else "") + f" -> {p3['verdict']}")
            w(f"  top-market share at the deciding horizons: "
              f"{[round(float(s), 1) if s is not None else None for s in shares]}"
              f" -> {'ok' if ok else 'CARRIED BY ONE MARKET'}")
            ures[denom] = dict(unconstrained=su, truncated=st,
                               predictions=preds, top_share_ok=ok)
        if args.null and uname == "all":
            w()
            w(f"-- null: same geometry at random minutes of the same market, "
              f"same session time-of-day +-{NULL_TOD_MINUTES}m, other days")
            placements = null_profiles(urows, runs, args.null_b)
            npct = null_mean_percentiles(urows, placements, "unconstrained", "R")
            w(f"  ({PATH_LABEL['unconstrained']}, R units)")
            w(f"  {'horizon':16} {'n':>4} {'observed':>9} {'null mean':>10} "
              f"{'null sd':>8} {'pctile':>7} {'placements':>10}")
            for name in H_NAMES:
                s = npct[name]
                if not s.get("null_reps"):
                    w(f"  {name:16} {s.get('n', 0):>4}  (no null)")
                    continue
                w(f"  {name:16} {s['n']:>4} {fnum(s['observed'], 9)} "
                  f"{fnum(s['null_mean'], 10)} {fnum(s['null_sd'], 8)} "
                  f"{fnum(s['percentile'], 7)} {s['placements']:>10}")
            ures["null"] = npct
        res[uname] = ures
    # the combined verdicts (rules 4 and 6)
    w()
    w(f"  {label}: combined verdicts (both universes AND both denominators)")
    comb = {}
    for p in ("P1", "P2", "P3"):
        vs = [res[u][d]["predictions"][p] for u in res for d in ("R", "range")]
        comb[p] = combine(vs)
        w(f"    {p}: {comb[p]}")
    carried = not all(res[u][d]["top_share_ok"] for u in res
                      for d in ("R", "range"))
    if carried:
        w(f"    reading rule 2: a deciding horizon ({', '.join(DECIDING)}) is "
          f"carried by one market - nothing above may read 'not rejected'")
        comb = {p: ("indeterminate (one market)" if v == "not rejected"
                    else v) for p, v in comb.items()}
    res["combined"] = comb
    result.update(res)
    return comb


def p4_reading(rule1, runs, ticks, args, w, result):
    """P4: r3 trades against the trades only r1 / r2 take, per anchor."""
    if rule1 is None:
        w("  P4: rule 1 sweep payload not found - skipped")
        return
    w()
    w("== P4: rule 1 = 3 against the marginal trades of lower counts "
      "(expected unpowered, doc s.7 rule 5)")
    out = {}
    for anchor in ("4th5th", "hybrid"):
        r3 = rule1["trades"].get(f"{anchor} r3", [])
        rows3, f3 = profile_rows([t for t in r3 if t["reason"] != "data_end"],
                                 runs, ticks)
        key3 = {(t["market"], t["entry_ts"], t["side"]) for t in r3}
        anchor_out = {}
        for n in (1, 2):
            rn = rule1["trades"].get(f"{anchor} r{n}", [])
            marginal = [t for t in rn
                        if (t["market"], t["entry_ts"], t["side"]) not in key3
                        and t["reason"] != "data_end"]
            rowsn, fn = profile_rows(marginal, runs, ticks)
            w()
            w(f"-- {anchor}: r3 ({len(rows3)} trades) vs r{n}-only "
              f"({len(rowsn)} marginal trades; {len(fn)} unplaceable)")
            w(f"  {'horizon':16} {'m(r3)':>8} {'m(r'+str(n)+'-only)':>12} "
              f"{'diff':>8} {'95% CI':>18} {'P(<=0)':>7}")
            hres = {}
            for name in H_NAMES:
                a, ca, _ = series(rows3, name, "x", "R")
                b, cb, _ = series(rowsn, name, "x", "R")
                if a.size == 0 or b.size == 0:
                    w(f"  {name:16}  (no horizon)")
                    continue
                bd = cluster_bootstrap_diff(a, ca, b, cb, args.reps)
                dim = " (dimmed)" if min(a.size, b.size) < MIN_N else ""
                if bd is None:
                    w(f"  {name:16} {fnum(a.mean(), 8)} {fnum(b.mean(), 12)}"
                      f"   bootstrap failed{dim}")
                    continue
                w(f"  {name:16} {fnum(a.mean(), 8)} {fnum(b.mean(), 12)} "
                  f"{bd['mean']:+8.3f} [{bd['ci_lo']:+7.3f}, {bd['ci_hi']:+7.3f}]"
                  f" {bd['p_le_0']:7.3f}{dim}")
                hres[name] = dict(n_r3=int(a.size), n_marg=int(b.size),
                                  m_r3=float(a.mean()), m_marg=float(b.mean()),
                                  diff=bd)
            anchor_out[f"r{n}"] = hres
        out[anchor] = anchor_out
    w()
    w("  P4 verdict: unpowered on this window by construction (marginal sets "
      "under 30 trades); recorded, re-read on the forward sample. A "
      "suggestive dimmed curve is not a result.")
    result["P4"] = out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-null", dest="null", action="store_false")
    ap.add_argument("--null-b", type=int, default=NULL_B)
    ap.add_argument("--reps", type=int, default=BOOT_REPS)
    ap.add_argument("--keys", nargs="*", default=None,
                    help="debug: restrict the markets loaded")
    args = ap.parse_args()

    samples, anchors, rule1, blotter, matrix = load_samples()
    keys = set()
    for trades in samples.values():
        keys |= {t["market"] for t in trades}
    if rule1 is not None:
        for cell in rule1["trades"].values():
            keys |= {t["market"] for t in cell}
    if args.keys:
        keys &= set(args.keys)
    print(f"loading {len(keys)} markets ...", flush=True)
    runs, ticks, excluded = load_runs(keys)
    for k, e in excluded.items():
        print(f"  {k}: EXCLUDED - {e['reason']}")

    out, result = [], dict(
        doc=DOC, built=datetime.now().strftime("%Y-%m-%d %H:%M"),
        horizons=H_NAMES, seed=SEED, reps=args.reps,
        null_b=(args.null_b if args.null else 0), min_n=MIN_N,
        flat_r=FLAT_R, top_share_max=TOP_SHARE_MAX,
        blotter_params=blotter.get("params"),
        secondary_dials=matrix["variants"][SECONDARY_CELL]["dials"],
        samples={})

    def w(line=""):
        print(line, flush=True)
        out.append(line)

    w(f"THE EXIT-TIMING PROFILE - {result['built']}")
    w(f"pre-registration: {DOC}; taken trades only; horizons fixed; no exit "
      f"rule is swept and no optimum is read")
    w(f"paths: '{PATH_LABEL['unconstrained']}' = the market after a trigger, "
      f"as if no stop existed; '{PATH_LABEL['truncated']}' = frozen at the "
      f"trade's OWN stop (the anchor named per sample), no scheduled exit")
    if args.keys:
        w(f"DEBUG RUN restricted to {sorted(keys)} - NOT a verdict")
    w(f"bootstrap reps {args.reps}, seed {SEED}; flat = 95% CI covers 0 and "
      f"point estimate < {FLAT_R}R; dimmed below n = {MIN_N}; top-market "
      f"share must stay under {TOP_SHARE_MAX:.0f}%")

    all_failures = []
    for label, trades in samples.items():
        rows, failures = profile_rows(trades, runs, ticks)
        all_failures += [(label, t, m) for t, m in failures]
        w()
        w(f"{label} - {anchors[label]}: {len(rows)} trades profiled, "
          f"{len(failures)} not placed")
        for t, m in failures:
            w(f"  NOT PLACED {t['market']} {t['side']} {t['entry_ts']}: {m}")
        result["samples"][label] = dict(
            n=len(rows), failures=len(failures), anchor=anchors[label],
            trades=[dict(r, horizons={k: v for k, v in r["horizons"].items()})
                    for r in rows])
        sample_reading(label, rows, runs, args, w, result["samples"][label],
                       anchor=anchors[label])
    p4_reading(rule1, runs, ticks, args, w, result)

    agreement = [f for f in all_failures if f[2].startswith("AGREEMENT")]
    if agreement:
        w()
        w(f"AGREEMENT CHECK FAILED on {len(agreement)} trades - the profile "
          f"does not reproduce the engine's booking; nothing written.")
        for label, t, m in agreement:
            w(f"  {label} {t['market']} {t['side']} {t['entry_ts']}: {m}")
        sys.exit(2)

    w()
    w("Verdict ceiling on this sample: 'not rejected', never 'confirmed'. "
      "The forward window is the next sample.")
    OUT_TXT.write_text("\n".join(out) + "\n", encoding="utf-8")
    OUT_JSON.write_text(json.dumps(result, indent=1, default=str),
                        encoding="utf-8")
    print(f"\nwrote {OUT_TXT.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
