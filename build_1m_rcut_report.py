# build_1m_rcut_report.py
#
# The R-CUT report (Lode, 2026-08-10): quickfix1m1dc restricted to a BAND of
# ladder geometry - keep only entries whose level-to-stop distance (1R in
# price) falls between a lower and an upper fraction of the market's trailing
# previous trading day's high-low range. Pick the two cuts, see that band's equity curve,
# DRAWDOWN and OPEN POSITIONS, its metrics, and a HEATMAP of the whole grid.
#
# WHY EVERY BAND NEEDS ITS OWN ENGINE RUN, and therefore why this script is
# slow (~24s per combination): a refused entry does NOT spend the
# session-lockout allowance, so a band does not merely DROP trades from the
# baseline - a later minute can trigger instead, and the band takes trades the
# baseline never reached. The 0.10-step bands sum to 337 trades against the
# baseline's 137, which is the proof: they are not slices of one run and cannot
# be produced by filtering a blotter. Verified consequence (audit s.15c):
# excluding the sub-0.20 trades removed 19 trades worth +22.49R and UNLOCKED 5
# worth +28.11R, because the tight-ladder setups were spending the session's
# only entry before a better-proportioned setup appeared.
#
# EVERY CELL IS LEVERED TO THE SAME 6% MAX DRAWDOWN: comparing bands at one bet
# size flatters whichever band was allowed to dig the deepest hole, since a
# shallower curve can simply be bet bigger. Method is solve_risk.py's -
# drawdown rises monotonically with risk, so bisect - applied to
# run_1m.portfolio_replay, this project's own account.
#
# ONE GRID PER STOP ANCHOR (Lode, 2026-08-16). This page used to be the ladder
# stop alone and said so nowhere, so the band it published read as a fact about
# the strategy rather than about the 4th/5th stop. The BAND READS THE STOP
# ANCHOR'S OUTPUT - the ratio's numerator is level-to-stop, so widening the stop
# to the session extreme moves every cell of the grid (audit s.19: PA 7 Aug went
# 0.226 -> 0.557 on the hybrid stop, straight through the upper cut). A band's
# evidence therefore does NOT carry across stop modes, and the only honest way
# to compare them is to run the whole grid on each. Hence `--stop`, two output
# stems and two refresh keys; the labels and the dials come from
# `run_1m_matrix.STOPS`, so the two pages can never disagree with the matrix
# about what "hybrid" means.
#
# RESULTS ARE CACHED AND REUSED. A cell already in the output JSON is not
# re-run (same engine, same dials, so the pass is deterministic), which is what
# makes refining the grid cheap: the 0.05 refinement Lode asked for adds ~95
# passes on top of the 136 already computed instead of redoing all 231. Each
# stop anchor has its OWN cache file, and the cache is keyed on the dials, so
# neither grid can ever be served cells the other computed.
#
# HOW TO READ IT, and the cautions are not decoration (audit s.15):
# - A narrow band holds a few dozen trades. Its win rate is noisy and its
#   DRAWDOWN is barely an estimate, so the 6%-levered money divides by a number
#   this sample cannot support. The leverage figure illustrates, it does not
#   advise - and levering to a measured drawdown bets biggest exactly where the
#   evidence is thinnest.
# - Check `top market share` before believing a band. The BASELINE's own net R
#   is 49% one market (ZW).
# - The best region is a one-step RIDGE, not a smooth optimum: lower 0.00 and
#   0.10 are identical, lower 0.30 collapses.
#
# NEW BARS RECOMPUTE A TAIL, NOT THE GRID (Lode, 2026-08-19: "updating the grid
# is time and energy consuming and it's also not always necessary"). Until then
# one new trading day moved the data fingerprint, which threw away all 232 cells
# and paid ~90 minutes per grid. Now a top-up recomputes the last handful of days
# per cell and splices them onto the cached trades, which is minutes.
#
# It is allowed to do that only because the engine happens to make it cheap AND
# checkable: run_market takes a plain list of Days so a tail is a slice; levels
# are resolved by timestamp, not replayed; and trades are capital-independent in
# R, with the equity curve rebuilt from the whole spliced list by
# portfolio_replay, so no equity path leaks across the join.
#
# The safety is not "the files look appended". It is that the days either side of
# the cut are RECOMPUTED FROM THE REAL BARS AND MUST REPRODUCE THE CACHE exactly
# (verify_overlap); any disagreement abandons the splice and rebuilds everything.
# That is what catches the cases a file-stamp check cannot see -- a re-download,
# a roll calendar that re-stitched history, a market joining the universe. The
# old rule's spirit is intact: a wrong miss costs time, and a wrong hit is not
# reachable without the engine agreeing with the cache first.
#
# Usage:  python build_1m_rcut_report.py            # 4th/5th stop, full grid
#         python build_1m_rcut_report.py --stop hybrid          # hybrid stop
#         python build_1m_rcut_report.py --step 0.5 --max 1.0   # coarse test
#         python build_1m_rcut_report.py --no-reuse # ignore the cache
#         python build_1m_rcut_report.py --no-incremental  # keep the cache but
#                                       # never splice: rebuild when bars move

import hashlib
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

import run_1m
import run_1m_matrix as mx

HERE = Path(__file__).resolve().parent
CHECKPOINT_EVERY = 25      # rewrite the page mid-run so it can be read early

# INCREMENTAL REBUILD (Lode, 2026-08-19). New bars used to throw the whole cache
# away and pay ~90 minutes per grid; now the tail is recomputed and spliced onto
# the cached trades. These two numbers are the whole cost/confidence trade:
#
# OVERLAP_DAYS are cached market days recomputed on purpose so their trades can
# be compared against what the cache holds. That comparison IS the safety
# argument -- see splice_point() and verify_overlap(). More days is a stronger
# proof and a slower run; five covers a top-up plus a couple of days of slack.
#
# PRIME_DAYS run before those and have their trades thrown away. They exist to
# fill the engine's trailing high-low window and prev_trading_date before the
# first day whose trades are kept, so a spliced cell is computed against the
# same primed state a full pass would have had. The window looks back one
# trading day under range_mode="trading_day", so five is generous.
OVERLAP_DAYS = 5
PRIME_DAYS = 5

TARGET_DD = 6.0
RISK_TOLERANCE = 0.0005

# THE TRADED UNIVERSE, BESIDE THE RESEARCH RECORD (Lode, 2026-08-20).
#
# This grid runs the WHOLE universe with no market filter, deliberately: it is the
# record the band was read from, and the note in the page has always said so. But the
# published strategy trades `run_1m.HUMAN_APPROVED` (22 of 31 markets, audit s.16),
# so every equity figure here answers a question about a universe nobody trades - and
# it sits unlabelled next to the identical metric on pages that DO use the traded set.
#
# The trap is real and it caught the person who wrote the decision: on 2026-08-20 the
# hybrid grid's 0.20-0.60 cell read $166,627 against the matrix's $223,146 for what
# looked like the same band. Same arithmetic, different universe. Filtering the grid's
# own cached trades reproduces the matrix EXACTLY - 79 trades, 50.6%, +62.44R, 4.45%
# DD - so nothing was wrong except which question the number answered.
#
# What the nine excluded markets do to that cell: 21 extra trades worth -5.66R, which
# also deepens the drawdown 4.45% -> 6.32%, so the bet size that reaches 6% collapses
# from 1.356% to 0.947% and the final equity with it. The loss of R is the small half;
# the drawdown is what does the damage.
#
# So BOTH are computed and both are shown. The research record keeps its meaning and
# the number a reader will naturally compare is present and labelled. It costs no
# engine passes at all - the trade cache tags every trade with its market, so the
# filtered metrics are arithmetic over trades already in hand, which is why this could
# be added to a grid that takes ninety minutes to build without rebuilding it.
FILTERED_LABEL = "traded universe (market filter, s.16)"
UNFILTERED_LABEL = "research record (whole universe, no filter)"

#: The filtered copy KEEPS its series (curve, drawdown, exposure). They were stripped
#: at first to spare a payload already around 2.4 MB, on the reasoning that a column
#: needs numbers rather than curves - which was wrong in the way that matters: the
#: panes then drew the whole universe whatever the selector said, so switching to the
#: traded universe changed every number on the page except the picture of it (Lode,
#: 2026-08-20). A chart that does not follow its own control is worse than no control.
SERIES_FIELDS = ()
# Every dial EXCEPT the stop anchor, which is what `--stop` chooses. The
# published baseline's dials otherwise, so a cell differs from the baseline in
# the band alone.
# `range_mode` is explicit so the cache key moves with it: the grids
# cache on the dials, and adopting the trading-day window without saying
# so here would have every band re-served from clock-built cells.
BASE = dict(tighten=False, allow_pre_activation=False, confirm=False,
            max_entries_per_session=1, range_mode="trading_day")

# The two grids. `stop_label` is the MATRIX's label for the anchor, so
# `mx.STOP_MODE_BY_LABEL` supplies the engine dial and this file never spells a
# stop_mode out; `step` is the key the page's own update button posts to
# charter's /api/refresh (see trading_system/refresh.EXTRA_STEPS).
VARIANTS = {
    "4th5th": dict(stop_label="4th/5th", suffix="4th5th", step="rcut1m"),
    "hybrid": dict(stop_label="hybrid", suffix="Hybrid", step="rcut1mhybrid"),
}
DEFAULT_VARIANT = "4th5th"

# 0.05 refinement where the grid actually turns (Lode, 2026-08-10): the ten
# best cells all sit at lower 0.20, and the upper cut's plateau runs 0.40-0.70,
# so those two stretches get half-steps and the rest stays on 0.10.
REFINE_LOWER = (0.10, 0.30)
REFINE_UPPER = (0.40, 0.70)

# DIVERGING AT BREAK-EVEN (Lode, 2026-08-10): red and orange where the account
# ENDS BELOW ITS STARTING CAPITAL, greens above it, deepest green at the best.
# The pivot is a real number, not a visual midpoint - $100,000 is where the
# strategy made nothing - which is what earns a diverging scale here.
# 15 classes, finer than the 7 it replaces, because Lode wanted smaller money
# steps between colours.
# Red/green is the classic colour-vision trap, so it is NEVER the only channel:
# every cell prints its value, and the legend labels the pivot.
# Both arms verified strictly monotone in lightness (OKLab: red arm
# 0.375 -> 0.812 rising, green arm 0.985 -> 0.338 falling), and each step
# carries >= 4.5:1 against its chosen ink.
HEAT_PIVOT = 100_000.0
# The red arm runs from a FIXED floor, not from the observed minimum (Lode,
# 2026-08-10). Anchoring it to the worst cell made a $96.6k result the
# darkest red the scale can show, which reads as a catastrophe when it is a
# 3% loss; from $90,000 the colours sit where the money actually is.
HEAT_MIN = 90_000.0
NEG_RAMP = ["#7f0000", "#b2182b", "#d6604d", "#f4a582", "#fdae61"]
NEG_INK = ["#ffffff", "#ffffff", "#0b0b0b", "#0b0b0b", "#0b0b0b"]
POS_RAMP = ["#f7fcf5", "#e5f5e0", "#ccebc5", "#addd8e", "#8fce7f",
            "#66bd63", "#41ab5d", "#238b45", "#00702f", "#00441b"]
POS_INK = ["#0b0b0b", "#0b0b0b", "#0b0b0b", "#0b0b0b", "#0b0b0b",
           "#0b0b0b", "#0b0b0b", "#0b0b0b", "#ffffff", "#ffffff"]
C_BAND, C_REF = "#1b7f45", "#898781"      # band green; muted ink for the reference
C_DD, C_POS = "#e34948", "#2a78d6"        # slot 8 red; slot 1 blue for exposure
PANE_H = (360, 150, 130)                  # equity, drawdown, open positions
PRICE_SCALE_W = 76    # identical on all three panes, so the plots line up


def variant(name):
    """Everything that differs between the two grids: the engine dial, the
    three output paths and the refresh key its page posts.

    The stop anchor is resolved through `run_1m_matrix.STOP_MODE_BY_LABEL`
    rather than written here, so `hybrid` on this page is the same dial as
    `hybrid` in the matrix and in charter's variant list, by construction.

    The third file is the TRADE cache, and the reason it exists: the metrics
    are cheap but the engine passes are not (~24s each, 231 of them). Caching
    the finished cells was not enough - adding the win-streak and open-position
    metrics on 2026-08-10 needed the trade LISTS, which the cell cache never
    held, so every pass had to run again. Keeping the trades means any future
    metric is seconds of arithmetic instead of an hour and a half of
    backtesting.
    """
    if name not in VARIANTS:
        raise SystemExit(f"--stop must be one of {', '.join(VARIANTS)}")
    v = dict(VARIANTS[name], name=name)
    v["stop_mode"] = mx.STOP_MODE_BY_LABEL[v["stop_label"]]
    v["dials"] = dict(BASE, stop_mode=v["stop_mode"])
    stem = f"quickfix1m1dcRcut{v['suffix']}"
    v["json"] = HERE / "output" / f"{stem}.json"
    v["html"] = HERE / "output" / f"{stem}.html"
    v["trades"] = HERE / "output" / f"{stem}_trades.json"
    return v


def bars_manifest():
    """Size and mtime of every bars parquet, per file.

    THE CACHE CANNOT BE ALLOWED TO OUTLIVE THE DATA. Cells were keyed on the
    band and the dials alone until 2026-08-12, so a rebuild after new bars
    landed replayed every cell from the previous window in about three seconds
    and republished a grid that no longer matched the baseline beside it. That
    is the one failure mode this page must not have: it is the research record
    the published band was read off.

    This was a single hash until 2026-08-19 and any touch of any file threw the
    whole cache away. Kept per file instead, the same information also answers
    "did the data GROW or did it CHANGE", which is what lets a top-up recompute
    a tail rather than 232 full passes. Ninety-odd files, ~2 ms.
    """
    out = {}
    for p in sorted((run_1m.DC / "data").glob("*/bars/*.parquet")):
        st = p.stat()
        out[f"{p.parent.parent.name}/{p.name}"] = f"{st.st_size}:{int(st.st_mtime)}"
    return out


def manifest_digest(manifest):
    """The old single-value fingerprint, still what the page stamps as `data`."""
    joined = "|".join(f"{k}:{v}" for k, v in sorted(manifest.items()))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def data_only_grew(old, new):
    """True when every file the cache was built on is either UNTOUCHED or has
    GROWN, so the new bars are the old ones with a tail appended.

    New files pass: a roll's next contract, or a market's first bars, add days
    at the end without disturbing what came before.

    Untouched means size AND mtime identical, and the strictness is the point.
    A file rewritten to the same byte count is refused even though its content
    has probably not changed, because this screen is the ONLY thing standing
    between the splice and a rewrite of history OUTSIDE the days verify_overlap
    recomputes -- that check can only speak for the days either side of the cut.
    Measured on the real archive before choosing the rule: of 92 bars files, a
    refresh touched the 22 front contracts it topped up and left 56 sitting on
    their original mtime from months earlier. So the strict form costs nothing
    in practice, and where it does fire it costs a rebuild rather than a wrong
    answer -- the same way round as the all-or-nothing rule it replaced.
    """
    if not old or not new:
        return False
    for name, stamp in old.items():
        fresh = new.get(name)
        if fresh is None:
            return False
        if fresh == stamp:
            continue
        try:
            if int(fresh.split(":")[0]) <= int(stamp.split(":")[0]):
                return False
        except (ValueError, IndexError):
            return False
    return True


# THE ENGINE'S OWN BOOKKEEPING, WHICH A SPLICE MUST NOT COMPARE OR KEEP.
# run_market carries a single account: it seeds `cash` at start_capital and
# sizes each entry at a percent of it, recording risk_usd, pnl_usd and
# cash_after per trade. Those three therefore depend on WHERE THE RUN STARTED,
# not on the trade, so a tail run beginning mid-window disagrees with a full
# pass on them and on nothing else -- verified against real bars, which found
# these three differing and all seventeen rule and fill fields, net_r included,
# identical (tests/test_rcut_incremental.py).
#
# Comparing them would have made verify_overlap fail every single time and
# quietly turned the incremental path off for good. Keeping them would leave a
# spliced list carrying two different account paths stitched together, which is
# a number nobody should read. So they are compared away AND dropped before
# caching. Nothing here reads them: the grid's money comes from
# portfolio_replay, which re-derives equity from net_r and is capital
# independent by construction.
ACCOUNT_FIELDS = ("risk_usd", "pnl_usd", "cash_after")


def comparable(t):
    """A trade reduced to what the engine DECIDED, free of the account path."""
    return {k: v for k, v in t.items() if k not in ACCOUNT_FIELDS}


def trade_key(t):
    """What identifies a trade across two runs. The entry is decided by bars
    STRICTLY BEFORE it, so two runs over the same prefix must produce the same
    keys -- which is what makes disagreement meaningful in verify_overlap."""
    return (t.get("market"), t["entry_ts"], t["side"])


def day_index(calendar, day):
    """Where an ISO day sits in the market-day calendar. ISO dates sort as
    strings, so this is a plain bisect and needs no parsing."""
    lo, hi = 0, len(calendar)
    while lo < hi:
        mid = (lo + hi) // 2
        if calendar[mid] < day:
            lo = mid + 1
        else:
            hi = mid
    return lo


def splice_point(tcache, calendar, first_new):
    """The calendar index W where cached trades can be cut from fresh ones.

    The rule that makes a splice sound: NO TRADE MAY STRADDLE W. If none does,
    every cached trade is either wholly before W (keep it) or wholly at/after it
    (drop it, the tail run recomputes it), and the two halves join with no trade
    counted twice, dropped, or half-simulated.

    It starts OVERLAP_DAYS before the first new day and walks backwards past any
    trade that spans the cut, taking that trade's own entry day as the next
    candidate. Walking back is what handles the engine's forced close: an open
    position at the end of the cached window was booked with reason "data_end"
    at that window's last bar, which is an artefact of where the data stopped
    rather than a trade. It straddles any W at or before its exit, so it is
    always walked past and always recomputed.

    Returns None when no usable cut exists (it would reach the start of the
    calendar), which the caller reads as "just rebuild".
    """
    w = max(0, first_new - OVERLAP_DAYS)
    for _ in range(64):                    # a trade spans days, not months
        if w <= 0:
            return None
        wday = calendar[w]
        earliest = None
        for trades in tcache.values():
            for t in trades:
                if t["entry_date"] < wday <= t["exit_date"]:
                    if earliest is None or t["entry_date"] < earliest:
                        earliest = t["entry_date"]
        if earliest is None:
            return w
        moved = day_index(calendar, earliest)
        if moved >= w:                     # cannot make progress; give up
            return None
        w = moved
    return None


def verify_overlap(cached, fresh, w_day, last_cached_day):
    """Compare a recomputed cell against the cache on the days they share.

    THIS IS THE SAFETY ARGUMENT for incremental rebuilds. data_only_grew() only
    says the files look appended; this recomputes real days from the real bars
    and demands the engine produce exactly what the cache holds. If the bars
    under those days moved -- a re-download, a roll calendar that re-stitched
    history, a market entering the universe -- the trades diverge here and the
    caller falls back to a full rebuild. The cost of that proof is already paid:
    these days are recomputed anyway to prime the engine.

    Trades the cached run closed with "data_end" are excluded from the value
    comparison and compared by KEY only: their exit was invented by the window
    ending, and the fresh run -- which can see the next day -- is right to close
    them somewhere else. splice_point() guarantees such a trade is never kept.

    Returns (ok, detail).
    """
    def window(trades):
        return {trade_key(t): t for t in trades
                if w_day <= t["entry_date"] <= last_cached_day}

    old, new = window(cached), window(fresh)
    if old.keys() != new.keys():
        missing = len(old.keys() - new.keys())
        extra = len(new.keys() - old.keys())
        return False, f"{missing} cached trade(s) gone, {extra} new on shared days"
    for key, was in old.items():
        if was.get("reason") == "data_end":
            continue                        # artefact of the old window's end
        mine, theirs = comparable(was), comparable(new[key])
        if mine != theirs:
            fields = [f for f in mine
                      if f in theirs and mine[f] != theirs[f]]
            return False, (f"{was.get('market')} {was.get('entry_ts')} differs on "
                           f"{', '.join(fields[:4]) or 'shape'}")
    return True, f"{len(old)} trade(s) reproduced exactly"


def solve_risk(trades, target=TARGET_DD):
    """The risk % putting this trade list at `target` max drawdown, or None
    when its curve never digs that deep at any sane bet size."""
    if not trades:
        return None
    def dd(risk):
        return run_1m.portfolio_replay(trades, risk_pct=risk)[1]
    lo, hi = 0.0, 8.0
    while dd(hi) < target:
        hi *= 2
        if hi > 64:
            return None
    while hi - lo > RISK_TOLERANCE:
        mid = (lo + hi) / 2
        if dd(mid) < target:
            lo = mid
        else:
            hi = mid
    return lo


def streaks(trades):
    """(longest losing, longest winning) run in ENTRY order."""
    seq = sorted(trades, key=lambda t: t["entry_ts"])
    worst = best = run_l = run_w = 0
    for t in seq:
        if t["net_r"] < 0:
            run_l += 1
            run_w = 0
        else:
            run_w += 1
            run_l = 0
        worst = max(worst, run_l)
        best = max(best, run_w)
    return worst, best


def exposure(trades):
    """Concurrent open positions over time: (series, max, time-weighted mean).

    At 1% risk per trade N concurrent positions is N% of the account at risk,
    so this is the report's only view of how much is on the table at once -
    the equity curve cannot show it."""
    import pandas as pd
    ev = []
    for t in trades:
        ev.append((int(pd.Timestamp(t["entry_ts"]).timestamp()), 1))
        ev.append((int(pd.Timestamp(t["exit_ts"]).timestamp()), -1))
    ev.sort()
    series, n, peak = [], 0, 0
    area, prev_ts = 0.0, None
    for ts, d in ev:
        if prev_ts is not None:
            area += n * (ts - prev_ts)
        n += d
        peak = max(peak, n)
        if series and series[-1][0] == ts:
            series[-1] = (ts, n)
        else:
            series.append((ts, n))
        prev_ts = ts
    span = (ev[-1][0] - ev[0][0]) if len(ev) > 1 else 0
    return series, peak, (round(area / span, 2) if span else 0.0)


DAY = 86400


def daily_equity(curve, grid, start_capital=100_000.0):
    """The equity curve resampled to ONE POINT PER MARKET DAY, carried
    forward across days with no exit.

    WHY A DAILY GRID AT ALL, and it is not cosmetic (Lode, 2026-08-10):
    lightweight-charts spaces points by INDEX, not by time. Fed the raw
    per-exit curve it gave a busy month more width than a quiet one - "months
    like feb and mei tend to take longer" - so the axis was not a time axis at
    all and dates repeated. One point per day makes index spacing and time
    spacing the same thing, which is also what lets the three panes be read
    against each other.

    WHY MARKET DAYS AND NOT CALENDAR DAYS (Lode, 2026-08-18): the grid is the
    days the account could actually move, it is shared by every cell of the
    grid, and it runs to the LAST one rather than to this cell's last exit -
    see run_1m. The pane draws it as a STEP for the same reason."""
    return [(run_1m.grid_seconds(d), v)
            for d, v in run_1m.carry_forward(curve, grid, start_capital)]


def drawdown_series(daily):
    """Percent below the running peak, on the DAILY closes plotted beside it.
    Negative, so the pane reads downward from zero."""
    out, peak = [], None
    for ts, eq in daily:
        peak = eq if peak is None else max(peak, eq)
        out.append((ts, -round((peak - eq) / peak * 100.0, 3)))
    return out


def daily_exposure(pos_series, daily):
    """Concurrent open positions, as the DAY'S MAXIMUM - the peak amount of
    the account on the table that day, on the same daily grid as the rest."""
    per_day = {}
    for ts, n in pos_series:
        d = ts // DAY
        per_day[d] = max(per_day.get(d, 0), n)
    out, last = [], 0
    for ts, _ in daily:
        d = ts // DAY
        last = per_day.get(d, 0)
        out.append((ts, last))
    return out


def measure(trades, grid):
    """Metrics for one band, at 1% and levered to TARGET_DD.

    `grid` is the market-day axis every cell's panes are drawn on, so two
    bands can be read against each other without one of them being a
    shorter line for having stopped trading in July."""
    n = len(trades)
    if not n:
        return None
    wins = [t["net_r"] for t in trades if t["net_r"] > 0]
    losses = [t["net_r"] for t in trades if t["net_r"] <= 0]
    netr = sum(t["net_r"] for t in trades)
    gross_w, gross_l = sum(wins), -sum(losses)
    final1, dd1, curve1 = run_1m.portfolio_replay(trades, risk_pct=1.0)
    lose_streak, win_streak = streaks(trades)
    _, dd_r = mx.entry_order_metrics(trades)
    risk6 = solve_risk(trades)
    if risk6:
        final6, dd6, curve6 = run_1m.portfolio_replay(trades, risk_pct=risk6)
    else:
        final6, dd6, curve6 = final1, dd1, curve1
    pos_series, pos_max, pos_mean = exposure(trades)
    # Display grids: one point per market day, so the axis is a time axis.
    d_curve = daily_equity(curve6, grid)
    d_dd = drawdown_series(d_curve)
    d_pos = daily_exposure(pos_series, d_curve)
    # The daily-close figure for the TABLE is taken at 1% risk, so it sits
    # beside the intraday one on the same basis. Reading it off the levered
    # curve instead just restates the 6% target, which every cell hits by
    # construction and which tells the reader nothing.
    d_curve1 = daily_equity(curve1, grid)
    dd_close = -min((v for _, v in drawdown_series(d_curve1)), default=0.0)
    per_market = {}
    for t in trades:
        per_market[t["market"]] = per_market.get(t["market"], 0.0) + t["net_r"]
    top_mkt, top_r = max(per_market.items(), key=lambda kv: kv[1])
    return dict(
        trades=n, wins=len(wins), win_rate=round(100 * len(wins) / n, 1),
        net_r=round(netr, 2), avg_r=round(netr / n, 3),
        profit_factor=round(gross_w / gross_l, 2) if gross_l else None,
        avg_win=round(gross_w / len(wins), 2) if wins else None,
        avg_loss=round(-gross_l / len(losses), 2) if losses else None,
        longest_losing_streak=lose_streak, longest_winning_streak=win_streak,
        max_dd_r=dd_r, max_dd_pct=round(dd1, 2), final_1pct=round(final1, 2),
        # The pane draws daily closes, so the depth it SHOWS gets its own row -
        # the worst-reached figure above is deeper by construction.
        max_dd_close_pct=round(dd_close, 2),
        risk_6pct=round(risk6, 3) if risk6 else None,
        final_6pct=round(final6, 2), max_dd_6pct=round(dd6, 2),
        pos_max=pos_max, pos_mean=pos_mean,
        markets=len(per_market), top_market=top_mkt,
        top_market_share=round(100 * top_r / netr, 0) if netr > 0 else None,
        exit_mix={r: sum(1 for t in trades if t["reason"] == r)
                  for r in ("stop", "close1", "no_confirm", "data_end")},
        # Curves are the LEVERED ones (equal pain is the comparison asked
        # for), on the daily grid the panes need.
        curve=d_curve, dd=d_dd, pos=d_pos,
        levered=bool(risk6),
    )


def rebuild_tail(tcache, old_calendar, calendar, combos, run_cell, log=print):
    """Recompute the tail of every cached cell and splice it on. None = rebuild.

    Everything that could make this unsound is checked and refused rather than
    assumed, in the order that costs least: the cached window must be a PREFIX
    of the new one (anything else is a re-stitch, not a top-up), there must be
    new days, and a straddle-free cut must exist. Only then does it spend engine
    passes, and each one is verified against the cache before its result is
    used.
    """
    if not tcache or not old_calendar:
        return None
    if list(old_calendar) != list(calendar[:len(old_calendar)]):
        log("incremental: the cached calendar is not a prefix of the new one "
            "-- history was re-stitched, so every cell is rebuilt.")
        return None
    first_new = len(old_calendar)
    if first_new >= len(calendar):
        log("incremental: no new market days, but the bars moved -- rebuilding "
            "rather than guessing what changed.")
        return None

    w = splice_point(tcache, calendar, first_new)
    if w is None:
        log("incremental: no straddle-free cut in range -- rebuilding.")
        return None

    w_day, last_cached = calendar[w], old_calendar[-1]
    prime_day = date.fromisoformat(calendar[max(0, w - PRIME_DAYS)])
    log(f"incremental: {len(calendar) - first_new} new market day(s) "
        f"({calendar[first_new]} to {calendar[-1]}). Cutting at {w_day}, "
        f"priming from {prime_day}: {len(calendar) - w} of {len(calendar)} days "
        f"per cell, {first_new - w} of them cached days recomputed as the "
        f"check.")

    fresh_cache, t0 = {}, time.time()
    for n, (lo, hi) in enumerate(combos, 1):
        key = cell_key(lo, hi)
        cached = tcache.get(key)
        if cached is None:
            # A cell the cache never held (a finer grid than last time). It has
            # no tail to splice onto, so it is a normal full pass.
            fresh_cache[key] = run_cell(lo, hi, None)
            continue
        tail = run_cell(lo, hi, prime_day)
        ok, detail = verify_overlap(cached, tail, w_day, last_cached)
        if not ok:
            log(f"incremental ABANDONED at {key}: {detail}. The cached trades "
                f"do not reproduce from the current bars, so the whole grid is "
                f"rebuilt.")
            return None
        kept = [t for t in cached if t["entry_date"] < w_day]
        if any(t.get("reason") == "data_end" for t in kept):
            log(f"incremental ABANDONED at {key}: a forced data_end exit "
                f"survived the cut, which splice_point should make impossible.")
            return None
        spliced = kept + [t for t in tail if t["entry_date"] >= w_day]
        spliced.sort(key=lambda t: t["entry_ts"])
        fresh_cache[key] = spliced
        if n == 1 or n % 25 == 0:
            per = (time.time() - t0) / n
            log(f"  [{n}/{len(combos)}] {key}: {len(spliced)} trades "
                f"({detail})   (~{per * (len(combos) - n) / 60:.0f} min left)")
    log(f"incremental: {len(fresh_cache)} cells spliced in "
        f"{(time.time() - t0) / 60:.1f} min.")
    return fresh_cache


def filtered_metrics(trades, grid):
    """The same cell, measured on the markets the strategy actually trades.

    Returns None when the filter leaves nothing - a cell can be entirely made of
    markets the filter excludes, and an empty cell must read as empty rather than as
    a zero that looks like a result.
    """
    kept = [t for t in trades if t.get("market") in run_1m.HUMAN_APPROVED]
    measured = measure(kept, grid)
    if measured is None:
        return None
    return {k: v for k, v in measured.items() if k not in SERIES_FIELDS}


def cell_key(lo, hi):
    """Cache/report key for a band. The baseline is (None, None)."""
    if lo is None and hi is None:
        return "baseline"
    return f"{lo:.2f}|{'inf' if hi is None else f'{hi:.2f}'}"


def edge_list(step, top):
    """The 0.10 grid plus 0.05 half-steps in the two refined stretches."""
    edges = {round(i * step, 2) for i in range(int(round(top / step)) + 1)}
    if step >= 0.10:                     # only refine the real grid, not a test
        for lo, hi in (REFINE_LOWER, REFINE_UPPER):
            v = lo
            while v <= hi + 1e-9:
                edges.add(round(v, 2))
                v += 0.05
    return sorted(edges)


def main():
    argv = sys.argv[1:]
    step = float(argv[argv.index("--step") + 1]) if "--step" in argv else 0.10
    top = float(argv[argv.index("--max") + 1]) if "--max" in argv else 1.50
    reuse = "--no-reuse" not in argv
    # `--no-incremental` keeps the cache but refuses the tail splice, so a run
    # can be forced back to the pre-2026-08-19 behaviour without throwing away
    # cells that are still exactly valid. `--no-reuse` still overrides both.
    incremental = reuse and "--no-incremental" not in argv
    v = variant(argv[argv.index("--stop") + 1] if "--stop" in argv
                else DEFAULT_VARIANT)
    dials = v["dials"]
    edges = edge_list(step, top)
    print(f"stop anchor: {v['stop_label']} ({v['stop_mode']}) "
          f"-> {v['html'].name}", flush=True)

    # Reuse TRADES, not finished cells: metrics are recomputed every build, so
    # adding a metric never costs an engine pass again.
    #
    # The cache is keyed on the DIALS *and* the DATA (see data_fingerprint):
    # either one moving throws all of it away, because a cell computed on last
    # week's bars is not an answer to today's question and the page has no way
    # to show that it is stale once it is drawn.
    manifest = bars_manifest()
    fingerprint = manifest_digest(manifest)
    tcache, calendar = {}, []
    # Set when the data moved but looks appended: the cells are stale, yet their
    # trades are still the right answer for every day before the new ones, so
    # the tail is recomputed instead of the whole grid. Carries the cache to
    # splice onto and the calendar it was computed over.
    pending = None
    if reuse and v["trades"].exists():
        try:
            old = json.loads(v["trades"].read_text(encoding="utf-8"))
            if old.get("dials") != dials:
                print("cache ignored: the dials have changed", flush=True)
            elif old.get("data") == fingerprint:
                tcache = old.get("trades", {})
                # The market-day calendar is cached with the trades and on
                # the same fingerprint, so it can never describe a different
                # window than they were computed on. A cache written before
                # it existed has none, and markets() below rebuilds it.
                calendar = old.get("calendar", [])
                print(f"reusing trades for {len(tcache)} cells from "
                      f"{v['trades'].name}", flush=True)
            elif (incremental and old.get("trades") and old.get("calendar")
                  and data_only_grew(old.get("bars"), manifest)):
                pending = (old["trades"], old["calendar"])
                print(f"the 1-minute data has grown since this cache was built "
                      f"({old.get('data')} -> {fingerprint}); every file it was "
                      f"built on is still there and no smaller, so the tail is "
                      f"a candidate for splicing. Verified below.", flush=True)
            elif incremental and not old.get("bars"):
                # Says the true reason rather than blaming the data. A cache
                # written before the per-file manifest existed has nothing to
                # compare against, so its ONE rebuild is unavoidable and every
                # run after it can splice.
                print(f"cache ignored: it was built before this grid recorded "
                      f"a per-file manifest, so there is nothing to check the "
                      f"new bars against. This rebuild is the last full one; "
                      f"it writes the manifest, and the next top-up splices a "
                      f"tail instead.", flush=True)
            else:
                print(f"cache ignored: the 1-minute data has changed since it "
                      f"was built ({old.get('data')} -> {fingerprint}) in a way "
                      f"that is not a top-up -- a file shrank, vanished, or was "
                      f"rewritten at the same size. Every cell is a fresh "
                      f"engine pass.", flush=True)
        except ValueError:
            pass

    t0 = time.time()
    # LAZY: loading every market costs ~100s, and a rebuild that only changes
    # how the metrics are computed needs no market data at all - the trades
    # are already cached. Load on the first cache miss, not before.
    loaded = []

    def markets():
        if not loaded:
            for key in run_1m.ELIGIBLE_FUTURES + run_1m.ETFS:
                try:
                    inputs, excluded = run_1m.market_inputs(key)
                except Exception as exc:
                    print(f"{key}: ERROR {type(exc).__name__}: {exc}",
                          flush=True)
                    continue
                if inputs is not None:
                    loaded.append((key, inputs))
            print(f"loaded {len(loaded)} markets in {time.time() - t0:.0f}s",
                  flush=True)
        return loaded

    def run(lo, hi, first_date=None):
        """One cell. `first_date` runs only that day onward, for the tail
        rebuild -- the engine takes a plain list of Days, so a slice is all it
        takes, and `files` is passed whole because levels are resolved by
        timestamp (_active_file) rather than replayed in order."""
        cell = dict(dials, min_rpu_range_ratio=lo, max_rpu_range_ratio=hi)
        trades = []
        for key, (days, files, tick, note) in markets():
            if first_date is not None:
                days = [d for d in days if d.date >= first_date]
                if not days:
                    continue
            tr, _ = run_1m.engine_1m.run_market(days, files, tick, **cell)
            for t in tr:
                t["market"] = key
            # Dropped here, once, so a cell means the same thing whether it came
            # from a full pass or a spliced tail: see ACCOUNT_FIELDS.
            trades.extend(comparable(t) for t in tr)
        trades.sort(key=lambda t: t["entry_ts"])
        return trades

    combos = [(None, None)]          # the baseline rides in the same loop
    combos += [(lo, hi) for i, lo in enumerate(edges) for hi in edges[i + 1:]]
    combos += [(lo, None) for lo in edges]

    # The tail rebuild, if the cache looked appendable. It needs the market data
    # (so `markets()` pays its ~100s here) and the NEW calendar, which is also
    # what the equity axis below is drawn on. Any doubt returns None and the
    # grid falls through to the full rebuild it would have done anyway.
    if pending is not None:
        old_trades, old_calendar = pending
        calendar = [d.isoformat() for d in run_1m.calendar_union(
            [[day.date for day in days]
             for _key, (days, _f, _t, _n) in markets()])]
        spliced = rebuild_tail(old_trades, old_calendar, calendar, combos, run,
                               log=lambda m: print(m, flush=True))
        if spliced is None:
            calendar = []            # rebuilt below, from the same markets()
        else:
            tcache = spliced

    fresh = sum(1 for lo, hi in combos if cell_key(lo, hi) not in tcache)
    print(f"{len(combos)} combinations over {len(edges)} edges; "
          f"{len(combos) - fresh} from cache, {fresh} to backtest "
          f"(~{fresh * 24 / 60:.0f} min)", flush=True)

    v["json"].parent.mkdir(exist_ok=True)
    cells, baseline = {}, None
    t1, done = time.time(), 0

    def checkpoint():
        payload = dict(
            strategy=f"quickfix1m1dc - ladder-geometry band (R cut), "
                     f"{v['stop_label']} stop",
            audit_doc="docs/quickfix1m1dc_audit.md (s.15)",
            target_dd=TARGET_DD, step=step, edges=edges,
            dials=dials, baseline=baseline,
            # Which grid this is. The page states its stop anchor in the
            # heading and posts `refresh_step` from its own update button, so a
            # reader can never take one anchor's band for the other's and the
            # button can never rebuild the wrong file.
            # THIS anchor's adopted band, so the page can open on it without a
            # literal that goes stale the next time a band is adopted.
            adopted=list(mx.BAND_CUTS_BY_STOP[v["stop_label"]][1]),
            variant=v["name"], stop_label=v["stop_label"],
            stop_mode=v["stop_mode"], refresh_step=v["step"],
            # Stamped so the PAGE can say which data it was computed on. This
            # grid is the only output here that is not rebuilt by the refresh
            # (Lode, 2026-08-12: it has its own button instead), so "when was
            # this last true" is a question the reader will actually have.
            built=datetime.now().strftime("%Y-%m-%d %H:%M"),
            data=fingerprint,
            # The size of the WHOLE grid, not of `cells`. A checkpoint writes
            # only the cells finished so far, so the page would otherwise
            # quote its own progress as the cost of a rebuild ("49 bands")
            # and undersell it by a factor of five mid-run.
            n_cells=len(combos),
            cells={k: m for k, m in cells.items() if m})
        v["json"].write_text(json.dumps(payload) + "\n", encoding="utf-8")
        v["html"].write_text(page(payload), encoding="utf-8")
        # `bars` is the per-file manifest the next run compares against to
        # decide whether its tail can be spliced; `data` is that manifest's
        # digest, kept because the page stamps it and an exact match is still
        # the fast path. A cache written before `bars` existed simply cannot
        # take the incremental path and rebuilds once.
        v["trades"].write_text(json.dumps(dict(dials=dials, data=fingerprint,
                                               bars=manifest,
                                               calendar=calendar,
                                               trades=tcache)),
                               encoding="utf-8")

    grid = []
    for i, (lo, hi) in enumerate(combos, 1):
        key = cell_key(lo, hi)
        trades = tcache.get(key)
        if trades is None:
            trades = run(lo, hi)
            tcache[key] = trades
            done += 1
        if trades and not grid:
            # ONE axis for the whole grid, fixed by the FIRST cell - the
            # uncut baseline, which is combos[0] and so always this one.
            # Every band is then drawn between the same two dates whatever
            # its own first and last trade were.
            if not calendar:
                calendar = [d.isoformat() for d in run_1m.calendar_union(
                    [[day.date for day in days]
                     for _key, (days, _f, _t, _n) in markets()])]
            grid = run_1m.market_day_grid(calendar, trades[0]["entry_ts"])
            print(f"CALENDAR: {len(calendar)} market days, grid {grid[0]} to "
                  f"{grid[-1]}", flush=True)
        m = measure(trades, grid)
        if m is not None:
            m["filtered"] = filtered_metrics(trades, grid)
        if lo is None and hi is None:
            baseline = m
        else:
            cells[key] = m
        left = ((time.time() - t1) / done * (fresh - done)) if done else 0
        print(f"[{i}/{len(combos)}] {key}: "
              + (f"{m['trades']}t {m['net_r']:+.2f}R avg {m['avg_r']:+.2f} "
                 f"DD {m['max_dd_pct']}% pos<={m['pos_max']} "
                 f"{m['longest_winning_streak']}W/{m['longest_losing_streak']}L"
                 f" -> ${m['final_6pct']:,.0f}" if m else "no trades")
              + f"   (~{left / 60:.0f} min left)", flush=True)
        if baseline is not None and i % CHECKPOINT_EVERY == 0:
            checkpoint()
            print(f"  -- checkpoint: {len(cells)} cells on the page --",
                  flush=True)

    checkpoint()
    print(f"\nwrote {v['json'].name}, {v['html'].name} and "
          f"{v['trades'].name} in {(time.time() - t0) / 60:.0f} min",
          flush=True)


def page(p):
    lib = run_1m.LIB_PATH.read_text(encoding="utf-8")
    data = json.dumps(p)
    heat = json.dumps(dict(pivot=HEAT_PIVOT, floor=HEAT_MIN,
                           neg=NEG_RAMP, negInk=NEG_INK,
                           pos=POS_RAMP, posInk=POS_INK))
    # A page that does not name its stop anchor invites exactly the mistake
    # this split was made to end (Lode, 2026-08-16), so the anchor is in the
    # title, in the first sentence and in the definition of 1R.
    name = p.get("variant", DEFAULT_VARIANT)
    label = p.get("stop_label", VARIANTS[DEFAULT_VARIANT]["stop_label"])
    other = "hybrid" if name == "4th5th" else "4th5th"
    other_html = f"quickfix1m1dcRcut{VARIANTS[other]['suffix']}.html"
    hand = "python build_1m_rcut_report.py" + (
        "" if name == DEFAULT_VARIANT else f" --stop {name}")
    if name == "4th5th":
        stop_note = ("one tick beyond the <b class=\"k\">5th reversal</b> of "
                     "the ladder, the 4th when the ladder carries only four. "
                     "This is the PUBLISHED dial, and the band adopted below "
                     "was read off this grid.")
        band_note = ("<b class=\"k\">ADOPTED (Lode): lower 0.00, upper "
                     "0.60</b> is the published band for this anchor (audit "
                     "s.19k, 2026-08-18). It replaced 0.20 / 0.50 - upper "
                     "adopted 2026-08-10 s.15e, lower raised from 0.00 on "
                     "2026-08-11 s.17 - when both grids were re-swept under "
                     "the trading-day window: the wider Monday denominator "
                     "shifted every ratio DOWN, so a ceiling fitted at half a "
                     "session was too tight, and on this anchor the LOWER cut "
                     "stopped earning its place at all (the leaders sit at "
                     "0.00-0.10). Chosen BROAD rather than at the grid's "
                     "optimum, which is the s.15c ridge caution applied.")
    else:
        stop_note = ("the ladder stop OR the session's running extreme at "
                     "entry, <b class=\"k\">whichever is wider</b> "
                     "(<code>ladder_or_extreme</code>, matrix cell "
                     "<b class=\"k\">variant 5</b>). NOT the published dial.")
        band_note = ("<b class=\"k\">ADOPTED (Lode): lower 0.20, upper "
                     "0.60</b> is this anchor's own band (audit s.19k, "
                     "2026-08-18) - it no longer borrows the 4th/5th one, and "
                     "it could not: 1R in price IS the numerator of the "
                     "ratio, so a wider stop pushes every setup up the scale "
                     "(audit s.19: PA 2026-08-07 reads 0.226 on the ladder "
                     "stop and 0.557 on this one, through the upper cut). "
                     "Deliberately NOT the grid's optimum - <b class=\"k\">"
                     "0.45-0.55</b> tops this table on 36 trades with 48% of "
                     "them in one market, which is the trap the <b class=\"k"
                     "\">top market share</b> column exists to catch.")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>quickfix1m1dc - R cut ({label} stop)</title><style>
:root {{
  --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --band:{C_BAND}; --ref:{C_REF};
  --dd:{C_DD}; --pos:{C_POS};
}}
body {{ background:var(--surface); color:var(--ink);
font:13px system-ui,-apple-system,"Segoe UI",sans-serif; margin:0;
padding:14px; }}
#head {{ max-width:1150px; }}
.note {{ color:var(--ink-2); line-height:1.45; }}
.warn {{ color:#B25000; }}
b.k {{ font-weight:600; }}
/* Panes: three charts, NEVER two y-scales on one plot. Each container's
   height includes its own time-axis band - a fixed height that excludes the
   axis is what clipped the labels here on 2026-08-10. */
.pane {{ margin-top:6px; }}
/* The three panes live in one positioned box so a single hand-drawn vertical
   line can span all of them (see the crosshair note in the script). */
#panes {{ position:relative; }}
#vline {{ position:absolute; top:0; bottom:0; width:0;
border-left:1px dashed #52514e; display:none; pointer-events:none; z-index:4; }}
#chart {{ height:{PANE_H[0]}px; }} #chartDD {{ height:{PANE_H[1]}px; }}
#chartPos {{ height:{PANE_H[2]}px; }}
#bar {{ display:flex; gap:18px; align-items:center; flex-wrap:wrap;
margin-top:10px; }}
select {{ font:13px inherit; padding:2px 4px; }}
/* The page's own update control. This grid is the one output the refresh
   button does NOT rebuild (Lode, 2026-08-12), so the button for it lives
   here, next to the numbers it changes. */
#upd {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap;
margin-top:12px; padding:9px 12px; border:1px solid var(--grid);
border-radius:8px; background:#fff; max-width:1150px; }}
#updbtn {{ font:13px inherit; font-weight:600; padding:5px 13px;
border:1px solid var(--axis); border-radius:6px; background:#f2f1ec;
color:var(--ink); cursor:pointer; }}
#updbtn:hover:enabled {{ border-color:var(--band); }}
#updbtn:disabled {{ opacity:.45; cursor:default; }}
#updlog {{ display:none; margin-top:10px; max-width:1150px; max-height:340px;
overflow:auto; background:#14150f; color:#d7d6cd; border-radius:8px;
padding:10px 12px; font:11.5px ui-monospace,Consolas,monospace;
white-space:pre-wrap; }}
.legend {{ display:flex; gap:14px; align-items:center; color:var(--ink-2);
margin-top:8px; font-size:12px; }}
.legend i {{ display:inline-block; width:16px; height:3px; margin-right:5px;
vertical-align:middle; }}
/* SCOPED TO #tbl / .hm ON PURPOSE. A bare `table` rule also hits the <table>
   lightweight-charts builds INSIDE the chart container: a margin-top on it
   pushed the whole chart down, so the time axis hung outside the box and the
   date labels were cut in half (Lode, 2026-08-10). Never style bare element
   selectors on a page that hosts a third-party widget. */
#tbl {{ border-collapse:collapse; margin-top:14px;
font-variant-numeric:tabular-nums; }}
#tbl td, #tbl th {{ padding:4px 10px; border-bottom:1px solid var(--grid);
text-align:right; }}
#tbl td:first-child, #tbl th:first-child {{ text-align:left; }}
/* The traded-universe column is the one a reader should compare against the
   matrix and the variant report, so it is inked like the band column rather
   than greyed like the reference. */
#tbl td.filt {{ color:var(--ink); }}
.uh {{ color:var(--muted); font-weight:400; font-size:11px; }}
.hm {{ border-collapse:separate; border-spacing:2px; margin-top:6px;
font-variant-numeric:tabular-nums; font-size:11px; }}
.hm th {{ color:var(--ink-2); font-weight:600; padding:2px 5px;
text-align:center; }}
.hm th.rowh {{ text-align:right; }}
.hm td {{ width:52px; height:24px; text-align:center; cursor:pointer;
border-radius:3px; }}
.hm td.empty {{ background:transparent; cursor:default; }}
.hm td.sel {{ outline:2px solid var(--ink); outline-offset:1px; }}
#hmlegend {{ display:flex; align-items:center; gap:0; margin-top:8px;
font-size:11px; color:var(--ink-2); }}
#hmlegend .sw {{ width:34px; height:12px; }}
#tip {{ position:fixed; pointer-events:none; background:var(--surface);
border:1px solid var(--axis); border-radius:4px; padding:6px 8px;
font-size:12px; box-shadow:0 2px 8px rgba(11,11,11,.12); display:none;
z-index:9; font-variant-numeric:tabular-nums; }}
h3 {{ font-size:13px; margin:18px 0 0; }}
</style></head><body>
<div id="head"><b>quickfix1m1dc - ladder geometry band, {label} stop</b>
<span class="note"> <b class="k">Stop anchor: {label}</b> - {stop_note}
Keep only entries whose <b class="k">1R in price (level to the {label}
stop)</b> falls between the two cuts, as a fraction of that market's trailing
previous trading day's high-low range (adopted 2026-08-17, audit s.19j; it was a flat 24h of clock before, which held only half a session after a weekend). Every band is its OWN engine run - a
refused entry does not spend the session-lockout allowance, so a band takes
trades the baseline never reached and is not a slice of it. Each cell is
levered to a constant <b class="k">{p['target_dd']}% max drawdown</b>, because
comparing at one bet size flatters whichever band dug the deepest hole.
{band_note} The published
baseline also carries the human MARKET FILTER (s.16), which this grid's
ENGINE RUNS do NOT: every cell here is computed on the whole universe, and
"all trades" is the pre-adoption engine with no cuts, so this page stays the
research record the band was read from. <b class="k">Since 2026-08-20 every
cell is ALSO reported on the traded universe</b> - the same trades with the
market filter applied - because the whole-universe equity figure sits next
to the identical metric on the matrix and the variant report, which do carry
the filter, and comparing them is a mistake the page used to invite. It
caught the author of the filter: the hybrid grid's 0.20-0.60 cell read
$166,627 against the matrix's $223,146 for what looked like the same band.
Nothing was wrong but the question - the nine excluded markets add trades
that lose a little R and deepen the drawdown, so the bet size reaching {p['target_dd']}%
falls and the final equity with it. The table shows both columns, the
tooltip carries the traded figure, and the <b class="k">heatmap</b> selector
above chooses which universe it colours. The other stop anchor has its own grid, built the
same way and read the same way:
<a href="{other_html}">{other_html}</a>.</span>
</div>
<div id="upd">
  <button id="updbtn" type="button" disabled>Update this grid</button>
  <span id="updnote" class="note">built <b class="k">{p.get('built', 'unknown')}</b>
  &middot; every other page is rebuilt by charter's Update button, this grid is
  not: it is {p.get('n_cells') or len(p.get('cells') or {{}})} bands at one
  engine pass each, about <b class="k">90 minutes</b>. Press this when you want
  it re-read on current data.</span>
</div>
<pre id="updlog"></pre>
<div id="bar">
  <label>lower cut <select id="lo"></select></label>
  <label>upper cut <select id="hi"></select></label>
  <label>heatmap <select id="uni">
    <option value="filtered">traded universe (market filter)</option>
    <option value="whole">whole universe (research record)</option>
  </select></label>
  <span id="risk" class="note"></span>
</div>
<div id="panes">
  <div id="vline"></div>
  <div class="legend"><span><i style="background:var(--band)"></i>selected
  band</span><span class="note">equity at the levered bet size - the
  all-trades comparison is in the table, not as a second curve</span></div>
  <div class="pane" id="chart"></div>
  <div class="legend"><span><i style="background:var(--dd)"></i>drawdown %
  below peak</span><span class="note">on daily closes; the worst intraday
  figure is in the table</span></div>
  <div class="pane" id="chartDD"></div>
  <div class="legend"><span><i style="background:var(--pos)"></i>open
  positions (concurrent)</span><span class="note">at 1% risk each, N open =
  N% at risk</span></div>
  <div class="pane" id="chartPos"></div>
</div>

<h3>Final equity at {p['target_dd']}% drawdown - every band in the grid</h3>
<div class="note">Rows are the lower cut, columns the upper. Click a cell to
load it. Blank = the upper cut is not above the lower.
<b class="k">"Every band" is about the BANDS, not the markets</b> - which
universe these figures are measured on is the <b class="k">heatmap</b>
selector above, and the legend below the map names it. The phrase used to
read "the whole grid", which was fine until the page could show two
universes and "whole" started reading as "whole universe".</div>
<div id="hm"></div>
<div id="hmlegend"></div>
<div id="tip"></div>

<h3>Metrics for the selected band</h3>
<table id="tbl"></table>

<p class="note warn" style="max-width:1150px"><b>Read the R columns, not the
money.</b> A narrow band holds a few dozen trades: its win rate is noisy and
its drawdown is barely an estimate, so levering to {p['target_dd']}% divides by
a number this sample cannot support - and leverage to a measured drawdown bets
biggest exactly where the evidence is thinnest. Check <b class="k">top market
share</b>: the BASELINE's own net R is 49% one market. The best region is a
one-step ridge, not a smooth optimum. Audit s.15.</p>

<script>{lib}</script><script>
const P = {data}, H = {heat};

/* Three panes, one measure each: a dual-axis plot invents correlations that
   are not in the data, so equity, drawdown and exposure never share a scale.
   Three things make them read as ONE stacked chart instead of three charts:
   an identical price-scale width (otherwise each plot starts at a different
   x and the time axes do not line up), the time axis drawn ONLY under the
   bottom pane, and a crosshair mirrored across all three. */
function mkChart(el, h, showTime) {{
  return LightweightCharts.createChart(el, {{
    width: el.clientWidth, height: h,
    layout: {{ background: {{ color:'#fcfcfb' }}, textColor:'#52514e',
      attributionLogo:false, fontSize:11 }},
    grid: {{ vertLines:{{visible:false}},
      horzLines:{{color:'#e1e0d9', style:0}} }},
    rightPriceScale: {{ borderColor:'#c3c2b7', minimumWidth:{PRICE_SCALE_W},
      scaleMargins:{{top:0.10, bottom:0.10}} }},
    timeScale: {{ visible: showTime, timeVisible:false, secondsVisible:false,
      borderColor:'#c3c2b7' }},
    // The crosshair is mirrored onto the other panes, so it has to be
    // VISIBLE - the library default is a hairline that vanishes on a light
    // surface. The time label rides on the bottom pane only, since it is the
    // only one drawing a time axis.
    crosshair: {{
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: {{ color:'#52514e', width:1, style:2,
        labelVisible: showTime, labelBackgroundColor:'#52514e' }},
      horzLine: {{ color:'#52514e', width:1, style:2,
        labelBackgroundColor:'#52514e' }},
    }},
  }});
}}
const elEq = document.getElementById('chart'),
      elDD = document.getElementById('chartDD'),
      elPos = document.getElementById('chartPos');
const cEq = mkChart(elEq, {PANE_H[0]}, false),
      cDD = mkChart(elDD, {PANE_H[1]}, false),
      cPos = mkChart(elPos, {PANE_H[2]}, true);
const PANES = [cEq, cDD, cPos];
/* STEP LINES (Lode, 2026-08-18). The balance stands still until a trade
   closes and then jumps, so it is held flat from one market day to the next
   and the whole move is the vertical there - a slope between two exits
   eleven days apart draws eleven days of gain that nothing booked. The
   drawdown pane is the same curve read against its peak, so it steps too. */
const STEP = LightweightCharts.LineType.WithSteps;
const sBand = cEq.addLineSeries({{ color:'{C_BAND}', lineWidth:2,
  lineType: STEP, priceLineVisible:false, lastValueVisible:false }});
/* NO REFERENCE CURVE. The "all trades" line used to sit here in grey and it
   was actively misleading: it is a DIFFERENT cut of the grid, so it rises
   while the selected band falls, which reads as the equity going up while the
   drawdown pane deepens (Lode, 2026-08-10 - the numbers were always
   consistent, the second curve was not). The comparison lives in the metrics
   table, where the two columns cannot be mistaken for one series. */
/* Drawdown as a BASELINE series anchored at zero, not an area series: an area
   fills from the line to the bottom of the pane, so a SHALLOW drawdown drew
   the biggest block of colour - inverted, exactly as Lode read it. A baseline
   series fills only between zero and the line, so the ink is the drawdown. */
const sDD = cDD.addBaselineSeries({{
  baseValue: {{ type:'price', price:0 }},
  bottomLineColor:'{C_DD}', bottomFillColor1:'rgba(227,73,72,0.10)',
  bottomFillColor2:'rgba(227,73,72,0.45)',
  topLineColor:'{C_DD}', topFillColor1:'rgba(227,73,72,0)',
  topFillColor2:'rgba(227,73,72,0)',
  lineWidth:1, lineType: STEP,
  priceLineVisible:false, lastValueVisible:false }});
// Open positions as BARS, like the other variant reports (Lode).
const sPos = cPos.addHistogramSeries({{ color:'{C_POS}', base:0,
  priceLineVisible:false, lastValueVisible:false }});

/* Keep the three time scales in step BY TIME, not by logical index. The panes
   hold different numbers of points - equity and drawdown change only at exits,
   exposure changes at every entry AND exit - so logical index 50 is a
   different date in each, and syncing logical ranges pulled them apart
   (Lode: "the time axis of the panes are not lined up"). */
let syncing = false;
PANES.forEach(src => {{
  src.timeScale().subscribeVisibleTimeRangeChange(r => {{
    if (!r || syncing) return;
    syncing = true;
    PANES.forEach(dst => {{
      if (dst !== src) dst.timeScale().setVisibleRange(r);
    }});
    syncing = false;
  }});
}});
/* ONE VERTICAL LINE ACROSS ALL THREE PANES, drawn by hand.
   The library's own setCrosshairPosition was mirroring the line onto the other
   panes ~150px away from the cursor (Lode's report3.png), and it also threw
   during a cold load's first setData. Both problems vanish with a plain
   overlay: the panes now share an identical width and price-scale width, so
   THE SAME X IS THE SAME MOMENT IN ALL THREE by construction - no time
   lookup, nothing to drift. lwc keeps its own crosshair inside whichever pane
   is hovered, which is what draws the price and date labels. */
const panesBox = document.getElementById('panes');
const vline = document.getElementById('vline');
panesBox.addEventListener('mousemove', e => {{
  const r = panesBox.getBoundingClientRect();
  const x = e.clientX - r.left;
  // Stay out of the price-scale gutter, where there is no plot to point at.
  if (x < 0 || x > r.width - {PRICE_SCALE_W}) {{
    vline.style.display = 'none';
    return;
  }}
  vline.style.left = x + 'px';
  vline.style.display = 'block';
}});
panesBox.addEventListener('mouseleave',
  () => {{ vline.style.display = 'none'; }});
window.addEventListener('resize', () => {{
  cEq.resize(elEq.clientWidth, {PANE_H[0]});
  cDD.resize(elDD.clientWidth, {PANE_H[1]});
  cPos.resize(elPos.clientWidth, {PANE_H[2]});
}});

const lo = document.getElementById('lo'), hi = document.getElementById('hi');
P.edges.forEach(e => lo.add(new Option(e.toFixed(2), e)));
P.edges.forEach(e => hi.add(new Option(e.toFixed(2), e)));
hi.add(new Option('no cap', 'inf'));

const money = v => '$' + Math.round(v).toLocaleString('en-US');
const keyOf = (a, b) => a.toFixed(2) + '|' + (b === null ? 'inf' : b.toFixed(2));

/* `b` is the ALL-TRADES reference, in whichever universe the selector asks for,
   and `uname` names it in the header. It followed nothing before, so a table
   whose two band columns were explicitly labelled still carried a third column
   silently measured on the whole universe. */
function rows(m, b, uname) {{
  const R = [
    ['trades', m.trades, b.trades],
    ['wins', m.wins, b.wins],
    ['win rate %', m.win_rate, b.win_rate],
    ['net R', m.net_r, b.net_r],
    ['avg R per trade', m.avg_r, b.avg_r],
    ['profit factor', m.profit_factor, b.profit_factor],
    ['avg win / avg loss (R)', m.avg_win + ' / ' + m.avg_loss,
     b.avg_win + ' / ' + b.avg_loss],
    ['longest WINNING streak', m.longest_winning_streak,
     b.longest_winning_streak],
    ['longest losing streak', m.longest_losing_streak,
     b.longest_losing_streak],
    ['max open positions', m.pos_max, b.pos_max],
    ['avg open positions', m.pos_mean, b.pos_mean],
    ['max DD (R)', m.max_dd_r, b.max_dd_r],
    ['max DD % at 1% risk', m.max_dd_pct + '%', b.max_dd_pct + '%'],
    ['max DD % on daily closes, 1% risk',
     m.max_dd_close_pct + '%', b.max_dd_close_pct + '%'],
    ['final at 1% risk', money(m.final_1pct), money(b.final_1pct)],
    ['risk for ' + P.target_dd + '% DD',
     m.risk_6pct ? m.risk_6pct + '%' : 'never reaches it',
     b.risk_6pct + '%'],
    ['final at ' + P.target_dd + '% DD', money(m.final_6pct),
     money(b.final_6pct)],
    ['markets', m.markets, b.markets],
    ['top market', m.top_market + ' (' + (m.top_market_share ?? '-') + '%)',
     b.top_market + ' (' + (b.top_market_share ?? '-') + '%)'],
    ['stop / day-2 / abort',
     m.exit_mix.stop + ' / ' + m.exit_mix.close1 + ' / '
       + m.exit_mix.no_confirm,
     b.exit_mix.stop + ' / ' + b.exit_mix.close1 + ' / '
       + b.exit_mix.no_confirm],
  ];
  /* THE THIRD COLUMN: the same band on the markets the strategy actually trades.
     This grid runs the whole universe on purpose (it is the record the band was
     read from), but the published strategy trades 22 of 31 - so without this
     column the equity figure here invites a comparison against the matrix and the
     variant report that it cannot support. Blank where the filter leaves the cell
     empty, never zero: an empty cell must read as empty. */
  const f = m.filtered;
  const fv = (get, dash) => f ? get(f) : (dash ?? '-');
  const F = [
    fv(x => x.trades), fv(x => x.wins), fv(x => x.win_rate), fv(x => x.net_r),
    fv(x => x.avg_r), fv(x => x.profit_factor),
    fv(x => x.avg_win + ' / ' + x.avg_loss),
    fv(x => x.longest_winning_streak), fv(x => x.longest_losing_streak),
    fv(x => x.pos_max), fv(x => x.pos_mean), fv(x => x.max_dd_r),
    fv(x => x.max_dd_pct + '%'), fv(x => x.max_dd_close_pct + '%'),
    fv(x => money(x.final_1pct)),
    fv(x => x.risk_6pct ? x.risk_6pct + '%' : 'never reaches it'),
    fv(x => money(x.final_6pct)), fv(x => x.markets),
    fv(x => x.top_market + ' (' + (x.top_market_share ?? '-') + '%)'),
    fv(x => x.exit_mix.stop + ' / ' + x.exit_mix.close1 + ' / '
            + x.exit_mix.no_confirm),
  ];
  return '<tr><th>metric</th><th>band<br><span class="uh">whole universe</span>'
    + '</th><th>band<br><span class="uh">traded universe</span></th>'
    + '<th>all trades<br><span class="uh">' + (uname || 'whole universe')
    + '</span></th></tr>'
    + R.map((r, i) => '<tr><td>' + r[0] + '</td><td><b>' + r[1]
        + '</b></td><td class="filt"><b>' + (F[i] ?? '-') + '</b></td>'
        + '<td style="color:var(--muted)">' + r[2]
        + '</td></tr>').join('');
}}

/* ---- heatmap: DIVERGING at break-even. Below the starting capital the cell
   is red through orange, above it green, deepest green at the best. Each arm
   is scaled to its own span, because the losing side is a few thousand
   dollars wide and the winning side is ninety - a symmetric scale would spend
   half its colours on almost nothing. The value is printed in every cell, so
   colour is never the only channel. ---- */
/* RECOMPUTED PER UNIVERSE. The scale is anchored to the largest value it is
   actually drawing; keeping the whole-universe maximum while showing filtered
   numbers would wash the whole map toward the pale end and quietly understate
   every cell. */
let vMax = 0;
function rescale() {{
  const vals = Object.values(P.cells).filter(Boolean)
    .map(valueOf).filter(v => v !== null);
  vMax = vals.length ? Math.max(...vals) : H.pivot;
}}
function colorFor(v) {{
  if (v < H.pivot) {{
    // From a FIXED floor, so the reds mean the same money on every rebuild.
    const span = Math.max(H.pivot - H.floor, 1e-9);
    const i = Math.min(H.neg.length - 1,
      Math.max(0, Math.floor((v - H.floor) / span * H.neg.length)));
    return [H.neg[i], H.negInk[i]];
  }}
  const span = Math.max(vMax - H.pivot, 1e-9);
  const i = Math.min(H.pos.length - 1,
    Math.max(0, Math.floor((v - H.pivot) / span * H.pos.length)));
  return [H.pos[i], H.posInk[i]];
}}

/* WHICH UNIVERSE THE HEATMAP SHOWS. The grid is built on the whole universe - it
   is the research record the band was read from - and the strategy trades 22 of 31
   (audit s.16). Both are real answers to different questions, so the page asks
   which one you want rather than picking silently. */
function universe() {{
  const el = document.getElementById('uni');
  return el && el.value === 'whole' ? 'whole' : 'filtered';
}}
function valueOf(m) {{
  if (universe() === 'whole') return m.final_6pct;
  return m.filtered ? m.filtered.final_6pct : null;
}}

function drawHeat() {{
  rescale();
  const ups = P.edges.map(e => e.toFixed(2)).concat(['inf']);
  let h = '<table class="hm"><tr><th class="rowh">lower \\\\ upper</th>'
    + ups.map(u => '<th>' + (u === 'inf' ? 'none' : u) + '</th>').join('')
    + '</tr>';
  for (const l of P.edges) {{
    h += '<tr><th class="rowh">' + l.toFixed(2) + '</th>';
    for (const u of ups) {{
      const k = l.toFixed(2) + '|' + u;
      const m = P.cells[k];
      if (!m) {{ h += '<td class="empty"></td>'; continue; }}
      /* The heatmap follows the universe toggle, because the headline number is
         the one that gets compared and quoted. A cell the filter empties is drawn
         blank rather than as a zero. */
      const v = valueOf(m);
      if (v === null) {{ h += '<td class="empty"></td>'; continue; }}
      const [bg, fg] = colorFor(v);
      h += '<td data-k="' + k + '" style="background:' + bg
        + ';color:' + fg + '">' + Math.round(v / 1000) + 'k</td>';
    }}
    h += '</tr>';
  }}
  document.getElementById('hm').innerHTML = h + '</table>';
  let lg = '<span style="margin-right:6px">' + money(H.floor) + '</span>';
  H.neg.forEach(c => {{ lg += '<span class="sw" style="background:' + c
    + '"></span>'; }});
  lg += '<span style="margin:0 6px">' + money(H.pivot)
    + ' break-even</span>';
  H.pos.forEach(c => {{ lg += '<span class="sw" style="background:' + c
    + '"></span>'; }});
  const bl = universe() === 'filtered' && P.baseline.filtered
    ? P.baseline.filtered.final_6pct : P.baseline.final_6pct;
  lg += '<span style="margin-left:6px">' + money(vMax)
    + '</span><span style="margin-left:14px">all trades: ' + money(bl)
    + '</span><span style="margin-left:14px" class="uh">heatmap: '
    + (universe() === 'filtered' ? 'traded universe, 22 markets'
                                 : 'whole universe, no market filter') + '</span>';
  document.getElementById('hmlegend').innerHTML = lg;
}}

const tip = document.getElementById('tip');
document.getElementById('hm').addEventListener('mousemove', e => {{
  const td = e.target.closest('td[data-k]');
  if (!td) {{ tip.style.display = 'none'; return; }}
  const m = P.cells[td.dataset.k], k = td.dataset.k.split('|');
  /* THE TOOLTIP FOLLOWS THE SELECTOR, like the map it sits on and the panes
     below it (Lode, 2026-08-21). It used to read the whole universe always,
     with the traded figure appended as a footnote - so hovering a cell drawn
     from 22 markets reported the trade count and win rate of 31. Same defect
     as the panes had, one surface later: every number on this page answers the
     question the selector asks, and the OTHER universe is the footnote. */
  const filt = universe() === 'filtered';
  const sel = filt ? m.filtered : m;
  const other = filt ? m : m.filtered;
  const otherName = filt ? 'whole universe' : 'traded universe';
  const head = '<b>' + k[0] + ' to ' + (k[1] === 'inf' ? 'no cap' : k[1])
    + '</b>';
  if (!sel) {{
    tip.innerHTML = head + '<br><span class="uh">no trades on the traded '
      + 'universe</span><br><span class="uh">' + otherName + ': '
      + money(other.final_6pct) + ', ' + other.trades + ' trades</span>';
  }} else {{
    tip.innerHTML = head
      + '<br>' + money(sel.final_6pct) + ' at ' + (sel.risk_6pct ?? '-')
      + '% risk<br>' + sel.trades + ' trades, wr ' + sel.win_rate + '%, '
      + sel.net_r + 'R<br>avg ' + sel.avg_r + 'R, PF ' + sel.profit_factor
      + '<br>streaks ' + sel.longest_winning_streak + 'W / '
      + sel.longest_losing_streak + 'L, pos&le;' + sel.pos_max
      + '<br>top market ' + sel.top_market + ' '
      + (sel.top_market_share ?? '-') + '%'
      + (other
          ? '<br><span class="uh">' + otherName + ': '
            + money(other.final_6pct) + ', ' + other.trades + ' trades, '
            + other.net_r + 'R</span>'
          : '<br><span class="uh">' + otherName + ': no trades</span>');
  }}
  tip.style.display = 'block';
  tip.style.left = Math.min(e.clientX + 14, innerWidth - 230) + 'px';
  tip.style.top = (e.clientY + 14) + 'px';
}});
document.getElementById('hm').addEventListener('mouseleave',
  () => {{ tip.style.display = 'none'; }});
document.getElementById('hm').addEventListener('click', e => {{
  const td = e.target.closest('td[data-k]');
  if (!td) return;
  const [a, b] = td.dataset.k.split('|');
  lo.value = String(parseFloat(a));
  hi.value = b === 'inf' ? 'inf' : String(parseFloat(b));
  show();
}});

function show() {{
  const a = parseFloat(lo.value);
  const bv = hi.value === 'inf' ? null : parseFloat(hi.value);
  const tbl = document.getElementById('tbl');
  const risk = document.getElementById('risk');
  const clear = msg => {{ tbl.innerHTML = '<tr><td>' + msg + '</td></tr>';
    sBand.setData([]); sDD.setData([]); sPos.setData([]);
    risk.textContent = ''; }};
  if (bv !== null && bv <= a) return clear(
    'the upper cut must be above the lower cut');
  const m = P.cells[keyOf(a, bv)];
  if (!m) return clear('this combination was not computed');
  /* THE PANES FOLLOW THE SELECTOR. Whichever universe the heatmap is showing is
     the one drawn here, so the picture and the numbers can never disagree. */
  const series = universe() === 'filtered' ? m.filtered : m;
  if (!series) return clear(
    'this band takes no trades on the traded universe - switch the heatmap to the '
    + 'research record to see it on the whole universe');
  sBand.setData(series.curve.map(c => ({{time:c[0], value:c[1]}})));
  sDD.setData(series.dd.map(c => ({{time:c[0], value:c[1]}})));
  sPos.setData(series.pos.map(c => ({{time:c[0], value:c[1]}})));
  const uname = universe() === 'filtered'
    ? 'traded universe (market filter)' : 'whole universe (research record)';
  /* The all-trades reference, in the SAME universe the rest of this view is in. */
  const ref = (universe() === 'filtered' && P.baseline.filtered)
    ? P.baseline.filtered : P.baseline;
  tbl.innerHTML = rows(m, ref, uname);
  risk.textContent = (series.levered
    ? ('bet ' + series.risk_6pct + '% per trade for ' + P.target_dd
       + '% drawdown  ->  ' + money(series.final_6pct))
    : ('never reaches ' + P.target_dd + '% drawdown - shown at 1% risk'))
    + '   -   panes show the ' + uname;
  document.querySelectorAll('.hm td.sel').forEach(
    td => td.classList.remove('sel'));
  const cell = document.querySelector(
    '.hm td[data-k="' + keyOf(a, bv) + '"]');
  if (cell) cell.classList.add('sel');
  /* One explicit range on all three panes, from the widest series, so they
     start aligned rather than each fitting its own first/last point.
     ON THE NEXT FRAME, and never fatal: setVisibleRange needs the pane's
     MEASURED size, which lightweight-charts leaves null until its first
     layout. Called inline on a cold load it threw "Value is null" and took
     the whole of show() with it - empty panes and an unbuilt table, while the
     identical call from the console a second later worked (2026-08-10). Data
     lands first; the range is cosmetic and can retry. */
  const t0 = Math.min(series.pos[0][0], series.curve[0][0], ref.curve[0][0]);
  const t1 = Math.max(series.pos[series.pos.length - 1][0],
    series.curve[series.curve.length - 1][0],
    ref.curve[ref.curve.length - 1][0]);
  const applyRange = tries => {{
    try {{
      syncing = true;
      PANES.forEach(c => c.timeScale().setVisibleRange({{from: t0, to: t1}}));
    }} catch (e) {{
      if (tries > 0) return requestAnimationFrame(() => applyRange(tries - 1));
      console.warn('R-cut: could not set the shared range', e);
    }} finally {{ syncing = false; }}
  }};
  requestAnimationFrame(() => applyRange(5));
}}
lo.onchange = hi.onchange = show;
/* The toggle redraws the map and the legend. The selected band's table and panes
   show BOTH universes already, so they do not need redrawing - only the heatmap
   has to choose one. */
document.getElementById('uni').onchange = () => {{ drawHeat(); show(); }};
// Defaults from the edges that EXIST: a coarse grid has no 0.20 option, and
// setting a missing value leaves the select empty and the page on an error row.
function nearest(sel, want) {{
  let best = sel.options[0].value, d = Infinity;
  for (const o of sel.options) {{
    const v = parseFloat(o.value);
    if (!isNaN(v) && Math.abs(v - want) < d) {{ d = Math.abs(v - want);
      best = o.value; }}
  }}
  return best;
}}
function init() {{
  drawHeat();
  /* Open on THIS anchor's adopted band, carried in the payload rather than
     hardcoded: the two grids adopted different bands (4th/5th 0.00-0.60, hybrid
     0.20-0.60, audit s.19k) and a single literal here was stale for both. */
  lo.value = nearest(lo, P.adopted ? P.adopted[0] : 0.20);
  hi.value = nearest(hi, P.adopted && P.adopted[1] !== null ? P.adopted[1] : 0.60);
  if (parseFloat(hi.value) <= parseFloat(lo.value)) hi.value = 'inf';
  show();
  if (!sBand.data().length) throw new Error('no series data drawn');
}}
/* BOOT WITH RETRIES, and the reason is worth knowing (2026-08-10). On a COLD
   load the first `setData` throws lightweight-charts' "Value is null" - its
   internals are not ready while a ~4 MB inline payload is still being parsed
   and laid out - yet the identical call succeeds a moment later. Chasing the
   exact internal was not worth more time than this: the page retries until the
   library is ready, which is bounded, self-healing and visible in the console
   if it ever gives up. Two frames of rAF were NOT enough on this page. */
function boot(tries) {{
  try {{
    init();
  }} catch (e) {{
    if (tries > 0) return setTimeout(() => boot(tries - 1), 80);
    console.error('R-cut: init failed after retries:', e);
    document.getElementById('tbl').innerHTML =
      '<tr><td>init failed: ' + e.message + ' (see console)</td></tr>';
  }}
}}
boot(15);

/* ---- this page's own update button -------------------------------------
   Every other 1-minute page is rebuilt by charter's Update button. This grid
   is not (Lode, 2026-08-12): it is ~231 engine passes, about ninety minutes,
   which is not a thing to hang off a button somebody presses to see this
   morning's bars. So the control for it lives on the page that shows the
   result, and it drives the SAME runner - it posts this grid's own step key to
   charter's /api/refresh, which is exactly what the rail button posts for the
   ordinary steps. No second way to build anything. The key comes from the
   payload (`rcut1m` for the 4th/5th stop, `rcut1mhybrid` for the hybrid one),
   so a page can only ever rebuild ITSELF.

   The server is FOUND, not configured: this file is usually opened straight
   off disk, so it has no origin to infer a port from. serve.py takes the first
   free port from 8000, so try that handful. A GET /api/refresh is a cheap
   probe and is the same call the poll uses. */
(function updater() {{
  const btn = document.getElementById('updbtn');
  const note = document.getElementById('updnote');
  const log = document.getElementById('updlog');
  const STEP = '{p.get('refresh_step', 'rcut1m')}';
  let base = null, at = 0;

  const say = t => {{ note.innerHTML = t; }};
  function write(lines) {{
    if (!lines || !lines.length) return;
    log.style.display = 'block';
    log.textContent += lines.join('\\n') + '\\n';
    log.scrollTop = log.scrollHeight;
  }}

  async function probe() {{
    for (let port = 8000; port < 8020; port++) {{
      const url = 'http://127.0.0.1:' + port;
      try {{
        /* A 1.2s cap per port: a closed port rejects at once, but a port held
           by something that is not this server can hang the whole sweep. */
        const ctl = new AbortController();
        const t = setTimeout(() => ctl.abort(), 1200);
        const r = await fetch(url + '/api/refresh', {{signal: ctl.signal}});
        clearTimeout(t);
        if (!r.ok) continue;
        const j = await r.json();
        if (j && typeof j.state === 'string') return {{url, snap: j}};
      }} catch (e) {{ /* not this port */ }}
    }}
    return null;
  }}

  async function poll() {{
    let r;
    try {{
      r = await (await fetch(base + '/api/refresh?from=' + at)).json();
    }} catch (e) {{
      say('lost the connection to the server - the run may still be going; '
          + 'reload this page to reattach.');
      btn.disabled = false;
      return;
    }}
    write(r.lines);
    at = r.next;
    if (r.state === 'running') return setTimeout(poll, 1000);
    btn.disabled = false;
    if (r.state === 'done') {{
      say('done - reloading this page with the new grid...');
      /* The page is a static file the run has just rewritten, so the only way
         to show the result is to re-read it from disk. */
      setTimeout(() => location.reload(), 900);
    }} else {{
      say('<b class="k">' + r.state + '</b> - see the log below. Nothing on '
          + 'this page has changed.');
    }}
  }}

  async function start() {{
    btn.disabled = true;
    log.textContent = '';
    at = 0;
    say('starting...');
    let r;
    try {{
      /* text/plain, not application/json: a JSON content type makes this a
         CORS preflight, and a page opened from disk has a null origin. The
         server json.loads() the body whatever it is labelled. */
      r = await fetch(base + '/api/refresh', {{
        method: 'POST',
        headers: {{'Content-Type': 'text/plain'}},
        body: JSON.stringify({{steps: [STEP]}})
      }});
    }} catch (e) {{
      btn.disabled = false;
      return say('could not reach the server: ' + e.message);
    }}
    if (r.status === 409) {{
      say('a run is already going - following it.');
    }} else if (!r.ok) {{
      btn.disabled = false;
      return say('the server refused the run (HTTP ' + r.status + ').');
    }} else {{
      say('running - about <b class="k">90 minutes</b> for a full grid, less '
          + 'when the 1-minute data has not moved since the last build. You '
          + 'can leave this page; the run is on the server, and reloading '
          + 'reattaches to it.');
    }}
    poll();
  }}

  probe().then(found => {{
    if (!found) {{
      return say('built <b class="k">{p.get("built", "unknown")}</b> &middot; '
        + 'to rebuild it from this page, start charter\\'s server '
        + '(<b class="k">python serve.py</b> in ../charter) and reload. '
        + 'By hand: <b class="k">{hand}</b>.');
    }}
    base = found.url;
    btn.disabled = false;
    if (found.snap.state === 'running') {{
      btn.disabled = true;
      say('a run is already going - following it.');
      poll();
    }}
  }});

  btn.addEventListener('click', start);
}})();
</script></body></html>"""


if __name__ == "__main__":
    main()
