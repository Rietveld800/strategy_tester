"""The dial matrix for quickfix1m1dc v2: one pass over the data (each
market's days/files load once), every variant run on the same inputs.

FULL FACTORIAL SINCE 2026-08-13 (Lode). The grid used to be one axis
(the session lockout) with four cells riding along beside it, and every
cell was NAMED for the one dial it moved - "hybrid stop", "no lockout",
"band 0.00-0.50". That naming only works while each cell is one step
from the baseline, and it hid the combinations: the table could not say
what the hybrid stop is worth WITHOUT the lockout, or whether the 0.20
lower cut still earns its place under a wick stop. So the cells are now
numbered - `variant 1` .. `variant 27` - and the PROPERTIES are
columns on the page instead of prose in a name:

  lockout : 1 / 2 / none        (max_entries_per_session)
  stop    : 4th/5th / hybrid / wick   (stop_mode: ladder /
            ladder_or_extreme / extreme - "wick" is one tick beyond the
            session's running extreme AT ENTRY, above the high for a
            short and below the low for a long)
  band    : 000-050 / 020-050 / full  (the geometry cut; `full` = dial
            off), plus the hand-picked bands of two extra cells
  markets : 22 (the human market filter, s.16) / 31 (the whole universe)

27 cells are the full cross of lockout x stop x band on the FILTERED
universe, and since 2026-08-18 that is the WHOLE grid: the three extra
cells (`variant 28` 015-020, `variant 29` 025-065, `variant 30` the
market filter's off-state) were removed at Lode's call along with their
reports. The published baseline is `variant 2` (lockout 1, 4th/5th,
000-060, 22 markets) and it is an ordinary row here: it can be switched
off on the chart like any other.

THE BAND AXIS IS NESTED UNDER THE STOP ANCHOR (Lode, 2026-08-18), which
is why the cross is still 3x3x3. Each anchor keeps `000-050` and `full`
as fixed comparison points and carries its OWN chosen band in the middle
slot - 4th/5th `000-060`, hybrid `020-060`, wick `020-050` - read off
that anchor's own re-swept R-cut grid. A shared ladder could not express
it: `variant 2` and `variant 5` sit in the same slot, so one axis would
force one band on both anchors, and the band reads the stop anchor's
output (audit s.19).

Everything not on those four axes stays at the published baseline: no
tightening, overnight window blocked, no confirmation clause. Read the
LOSING STREAK and the drawdown first.

Earlier grids, all in git and written up in the audit: {tighten} x
{window} picked the baseline (sections 6 and 7), {confirm} x {stop
anchor} removed the confirmation clause and kept the ladder stop
(section 10), and the lockout axis (2026-08-07 to 2026-08-13) measured
what a market that has already traded today is worth - the 1st trade of
a market-day at 39.4% and +42.51R against the 2nd at 21.4% and -10.39R,
which is the measurement the lockout rule follows from.

EVERY ROW CARRIES A CHECKBOX (default on, plus all-on / all-off), which
is what makes 27 curves readable at all: the colours run in families -
hue by stop anchor, shade by band, lightness by lockout - so a family
can be read together, and anything else is switched off.

Metrics per variant, portfolio level (Lode's priority order): longest
losing streak (entry order, net R), max shared-account drawdown (worst
reached, and on daily closes beside it, the same pair the main report
shows), net R, win rate, trade count, final cash at 1% risk, and the 6%
solve (risk per trade + final). THE PLOTTED CURVES ARE THE LEVERED ONES
(Lode, 2026-08-11): every cell at a constant 6% max drawdown, risk
solved per cell by bisection, because at one bet size the tallest curve
is partly just the deepest hole that cell was allowed to dig. Output:
output/quickfix1m1dc_matrix.json + output/quickfix1m1dc_matrix.html.

Usage: python run_1m_matrix.py [KEY ...] (default: all eligible).
`--no-reuse` ignores the per-market cache and recomputes everything (see
the cache block below VARIANTS: a market whose input files have not moved
since the last run is reused whole from
output/quickfix1m1dc_matrix_cache.json - trades, rows, calendar and its
ratio file - and any file change recomputes the whole market; nothing is
spliced). `--page` redraws the HTML with no backtest.
"""

import colorsys
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import run_1m

HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "output" / "quickfix1m1dc_matrix.json"
OUT_HTML = HERE / "output" / "quickfix1m1dc_matrix.html"
# One file per market, keyed by the STOP LABEL this page prints, holding
# the geometry ratio at every armed minute (engine_1m.ratio_series) so
# charter's 1m study can draw it as a pane. Written here rather than in
# run_1m.py because this is the pass that already holds every market's
# bars in memory AND the pass that ships the trades the pane sits under -
# a pane built from a different run than the trades beside it would be a
# quiet lie. Keyed by label, not by engine mode, so charter can look it
# up straight from a variant's `props.stop` with no second mapping.
OUT_RATIO = HERE / "output" / "ratio"

# Everything off the four axes sits at the published baseline and never
# moves: no tightening, overnight window blocked, no confirmation clause.
# `range_mode` is stated here rather than left to the engine default so
# the dials a cell ran are self-describing in the JSON, and so anything
# that caches on them (the R-cut grids) invalidates when it changes.
BASE = dict(tighten=False, allow_pre_activation=False, confirm=False,
            range_mode="trading_day")
HUMAN_APPROVED = run_1m.HUMAN_APPROVED

# The four axes. Each entry is (label, dials it sets); the label is what
# the page prints in that property's column, and the JSON carries both.
LOCKOUTS = [("1", dict(max_entries_per_session=1)),
            ("2", dict(max_entries_per_session=2)),
            ("none", dict(max_entries_per_session=None))]
# "wick" IS the engine's `extreme` mode (confirmed by Lode, 2026-08-13):
# one tick beyond the session's running extreme AT ENTRY - above the high
# for a short, below the low for a long. At entry is the only extreme that
# exists; the rest of the day is not knowable there, and the stop does not
# trail afterwards.
STOPS = [("4th/5th", dict(stop_mode="ladder")),
         ("hybrid", dict(stop_mode="ladder_or_extreme")),
         ("wick", dict(stop_mode="extreme"))]
# The stop axis is also the only dial the geometry ratio depends on (the
# lockout and the band decide what to DO with the number, never what it
# is), so three series cover all 27 cells.
STOP_MODE_BY_LABEL = {lab: d["stop_mode"] for lab, d in STOPS}


def band_label(lo, hi):
    """`020-050` from the two cuts, `full` when the dial is off.

    DERIVED, never written by hand: the band is the one property whose
    label could silently disagree with the dials the cell actually ran,
    and a page that prints `015-020` over a 0.20-0.50 run is worse than
    no page. Every cell's label comes through here.
    """
    if lo is None and hi is None:
        return "full"
    return f"{round(lo * 100):03d}-{round(hi * 100):03d}"


# THE BAND AXIS IS PER STOP ANCHOR (Lode, 2026-08-18). It was one shared
# ladder, which cannot express what the re-swept grids say: under the
# trading-day window the two anchors want DIFFERENT cuts, and `variant 2`
# and `variant 5` sit in the same slot of that ladder, so a shared axis
# could only ever give them the same band. THE BAND READS THE STOP
# ANCHOR'S OUTPUT (audit s.19) - a band measured on one anchor was never
# evidence about the other - so the axis being nested under the stop is
# the honest shape, not a special case.
#
# Slot 0 and slot 2 are the fixed comparison points every anchor keeps
# (`000-050` and the dial OFF). Slot 1 is that anchor's CHOSEN band, read
# off its own R-cut grid, and it is the slot the published cells sit in:
# `variant 2` (4th/5th) and `variant 5` (hybrid). Chosen deliberately
# BROAD rather than at the grid's optimum - the sweep's best hybrid cell
# was 0.45-0.55 on 36 trades with 48% of them one market, which is the
# curve-fitting trap the page warns about (Lode: "too narrow ... we're
# probably just price-fitting"), and 0.65 was left on the table for being
# on the edge of the measured region.
BAND_CUTS_BY_STOP = {
    "4th/5th": [(0.00, 0.50), (0.00, 0.60), (None, None)],
    "hybrid":  [(0.00, 0.50), (0.20, 0.60), (None, None)],
    "wick":    [(0.00, 0.50), (0.20, 0.50), (None, None)],
}
BANDS_BY_STOP = {
    stop: [(band_label(lo, hi),
            dict(min_rpu_range_ratio=lo, max_rpu_range_ratio=hi))
           for lo, hi in cuts]
    for stop, cuts in BAND_CUTS_BY_STOP.items()}

# Cells OUTSIDE the factorial, appended in this order so the numbering of
# 1..27 never moves. (stop label, lockout label, lower cut, upper cut,
# markets label); the dials, the band label and the colour all follow from
# those five, and "31" is the whole universe (no market filter).
#
# 28 and 29 (Lode, 2026-08-16) are each read off their own stop anchor's
# R-cut grid (audit s.15f) at the published lockout: the best-performing
# band for that anchor, carried into the matrix so it is re-measured on
# every refresh instead of resting on the grid it was picked from.
#
# 30 is THE MARKET FILTER'S OFF-STATE, restored (Lode, 2026-08-16) after
# it was displaced from cell 28 the same day. It is the ONLY cell that
# leaves the filtered universe, and it exists because every rule's
# off-state is re-measured on every pass rather than resting on the sample
# it was adopted on - that principle is the reason the watch-cells were
# folded into the grid at all, and the filter is a rule like the others.
# Its dials are the ones Lode set for it in the first place (lockout 1 /
# hybrid / 000-050, NOT the published dials), so it still pairs with
# `variant 4`: same lockout, same stop, same band, only the filter differs.
# THE WINDOW IS NO LONGER AN AXIS (Lode, 2026-08-17). `variant 31`
# measured `trading_day` against the published `clock` baseline for one
# refresh and the window was adopted on the reading, so every cell runs
# it and there is nothing left to compare: the cell is gone and the page
# has no `window` column. The measurement that decided it is audit s.19j;
# `clock` survives as an engine dial for anyone who needs the old
# denominator back.
EXTRA_CELLS = []

# Colour families, so 27 curves can still be read as a picture: HUE is
# the stop anchor, a hue SHIFT is the band, LIGHTNESS is the lockout.
# Two cells of the same family sit next to each other in colour, which is
# the comparison the eye is usually making.
STOP_HUE = {"4th/5th": 145, "hybrid": 215, "wick": 25}
# The three band slots sit at -20 / 0 / +20 of their stop's hue, so a
# cell still reads as its stop anchor's family and no two shades land on
# the same hue (4th/5th 105-165, hybrid 195-255, wick 5-45).
# Slot 0 / slot 1 / slot 2 of a stop's own ladder, so a cell still reads
# as its anchor's family whatever cuts that anchor chose.
BAND_SHIFT = {"000-050": -20, "020-050": 0, "000-060": 0, "020-060": 0,
              "full": 20}
LOCK_LIGHT = {"1": 32, "2": 46, "none": 61}
# Kept for the day a cell leaves the 22-market universe again: it would
# otherwise wear a stop anchor's hue and read as a dial on those axes.
UNFILTERED_HSL = (300, 0.65, 0.45)


def color_for(props):
    """The curve colour for a cell, from its properties (see above).

    Emitted as HEX. The families are picked in HSL because that is the
    space the scheme is defined in, but lightweight-charts is handed
    `#rrggbb` - every other page in this project feeds it hex, and a
    colour string it cannot parse fails inside the paint loop where no
    console error and no test would show it.
    """
    if props["markets"] != "22":
        h, s, li = UNFILTERED_HSL
    else:
        h = (STOP_HUE[props["stop"]] + BAND_SHIFT[props["band"]]) % 360
        s, li = 0.68, LOCK_LIGHT[props["lockout"]] / 100
    r, g, b = colorsys.hls_to_rgb(h / 360, li, s)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255),
                                        round(b * 255))


def variant_slug(name):
    """Filename form of a variant name: `variant 5` -> `variant_05`.

    The number is zero-padded so the files of a 28-cell grid sort the way
    the grid reads. Owned here because the matrix names the cells; the
    JSON carries the result per variant as `slug`, and build_1m_report.py
    and research_1m_levels.py import this function so a variant page can
    never land under a name the matrix does not use.
    """
    m = re.match(r"^(.*?)\s*(\d+)$", name.strip())
    head = re.sub(r"[^a-z0-9]+", "_",
                  (m.group(1) if m else name).lower()).strip("_")
    return f"{head}_{int(m.group(2)):02d}" if m else head


def build_grid():
    """The 27 cells: the full lockout x stop x band cross, filtered
    universe, each anchor carrying its own band ladder.

    Returns (name, dials, markets, props) tuples in the numbered order.

    THE NUMBERING IS LOAD-BEARING and must stay put: variants 1..27 are
    read by number in the audit, in charter's `?v=` links and in every
    report filename. Extras are only ever APPENDED, which is what
    EXTRA_CELLS is for; it is empty since 2026-08-18, when cells 28-30
    were removed. Nothing below 28 moved when they went.
    """
    out = []
    for lock_lab, lock in LOCKOUTS:
        for stop_lab, stop in STOPS:
            for band_lab, band in BANDS_BY_STOP[stop_lab]:
                props = dict(lockout=lock_lab, stop=stop_lab,
                             band=band_lab, markets="22")
                out.append((f"variant {len(out) + 1}",
                            dict(BASE, **lock, **stop, **band),
                            HUMAN_APPROVED, props))
    lock_dials = dict(LOCKOUTS)
    for stop_lab, lock_lab, lo, hi, mkt_lab in EXTRA_CELLS:
        props = dict(lockout=lock_lab, stop=stop_lab,
                     band=band_label(lo, hi), markets=mkt_lab)
        out.append((f"variant {len(out) + 1}",
                    dict(BASE, **lock_dials[lock_lab],
                         stop_mode=STOP_MODE_BY_LABEL[stop_lab],
                         min_rpu_range_ratio=lo, max_rpu_range_ratio=hi),
                    HUMAN_APPROVED if mkt_lab == "22" else None, props))
    return out


VARIANTS = build_grid()
# The published run (lockout 1, 4th/5th, 020-050, 22 markets). It is an
# ORDINARY row on the page - it carries a checkbox like every other cell
# and can be switched off (Lode, 2026-08-13) - and this constant only
# marks it in the table and the JSON.
BASELINE_NAME = "variant 2"
COLORS = {name: color_for(props) for name, _, _, props in VARIANTS}

# --- the per-market cache (2026-08-21) --------------------------------------
#
# A refresh reruns every market from scratch, but a market whose input files
# did not move since the last run can only produce the byte-identical result,
# so its engine passes are bought work. This cache is PER MARKET and
# ALL-OR-NOTHING: a market is either reused whole - its trades, its per-cell
# summary rows, its day calendar and its already-written ratio file - or
# recomputed whole. Nothing is spliced and no number is derived, so every
# cached figure (account fields and the geometry counters included) is the
# engine's own output for exactly these inputs. That is a weaker save than
# the R-cut grid's tail splice (build_1m_rcut_report.py), and deliberately
# so: the matrix's per-market rows carry whole-run counters and the engine's
# own cash path, which a splice cannot reproduce without changing what the
# engine reports - a design decision that has not been made. The frozen
# markets (CC, KC, the delisted ETFs) hit this cache every day; every market
# hits it on a run where no new data landed.
#
# Reuse requires BOTH keys to match:
#   - the grid signature: every cell's name, dials and universe, plus the
#     engine constants and loader settings a result depends on. Any change
#     discards the whole cache. An engine CODE change without a constant
#     change is not detected - after one, run once with --no-reuse.
#   - the market's file manifest: size:mtime of every file its inputs come
#     from (its daily array xlsx, its bars/statistics parquet, its roll
#     calendar, the market mapping, Binance zips). Any difference - growth,
#     rewrite or deletion - recomputes the market; there is no partial credit.
CACHE_PATH = HERE / "output" / "quickfix1m1dc_matrix_cache.json"


def grid_sig():
    """Signature of everything besides the input DATA that decides a cell's
    output. Stable across runs, moves when the grid or the engine dials move."""
    e = run_1m.engine_1m
    payload = dict(
        variants=[[name, dials,
                   sorted(markets) if markets is not None else None]
                  for name, dials, markets, _props in VARIANTS],
        engine=dict(risk_pct=e.RISK_PCT, start_capital=e.STARTING_CAPITAL,
                    entry_slip=e.ENTRY_SLIP_TICKS,
                    stop_slip=e.SLIP_STOP_TICKS,
                    sched_slip=e.SLIP_SCHEDULED_TICKS,
                    min_ladder=e.MIN_LADDER, min_reversals=e.MIN_REVERSALS,
                    min_range_bars=e.MIN_RANGE_BARS,
                    range_window=str(e.RANGE_WINDOW)),
        loader=dict(files_from=str(run_1m.FILES_FROM),
                    activation=str(run_1m.ACTIVATION_UTC),
                    price_codec=run_1m.PRICE_CODEC))
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def market_manifest(key):
    """size:mtime_ns stamps of every file this market's inputs are read from.

    A superset is fine (an unused file's stamp only ever forces a recompute);
    a MISSING source is not, so this mirrors each loader's own paths:
    load_levels_and_socbars' daily array glob, futures_days' roll calendar +
    bars + statistics parquet (rglob covers both), etf_days' bars file,
    binance_days_and_match's kline zips, and the market mapping that names
    the directories.
    """
    m = run_1m.market_info(key)
    paths = sorted((run_1m.ARRAY_ROOT / m["array_dir"]).glob(
        "*/daily/*_array.xlsx"))
    mdir = run_1m.market_dir(m)
    if mdir.is_dir():
        paths += sorted(mdir.rglob("*.parquet"))
    extras = [run_1m.META / f"roll_calendar_{key}.json",
              run_1m.DC / "config" / "market_mapping.json"]
    if key == "GC":
        extras.append(run_1m.META / "contract_calendar_GC.json")
    if key in run_1m.BINANCE:
        sym = run_1m.BINANCE[key][1]
        extras += sorted((run_1m.DC / "data" / "_binance").glob(
            f"{sym}-1m-*.zip"))
    root = run_1m.DC.parent
    out = {}
    for p in paths + [x for x in extras if x.exists()]:
        st = p.stat()
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = str(p)
        out[rel] = f"{st.st_size}:{st.st_mtime_ns}"
    return out


def cell_names_for(key):
    """The cells this market belongs to under the current grid."""
    return {name for name, _d, markets, _p in VARIANTS
            if markets is None or key in markets}


def load_matrix_cache(sig):
    """The cache's market entries, or {} when absent, unreadable, or built
    under a different grid signature - all three mean the same thing: no
    entry is reusable."""
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if raw.get("sig") != sig:
        print(f"cache: grid signature changed, discarding {CACHE_PATH.name}",
              flush=True)
        return {}
    return raw.get("markets", {})


def save_matrix_cache(sig, markets):
    CACHE_PATH.parent.mkdir(exist_ok=True)
    CACHE_PATH.write_text(json.dumps(
        dict(sig=sig, markets=markets), separators=(",", ":")) + "\n",
        encoding="utf-8")


def entry_reusable(ent, key, manifest):
    """True when a cached market entry answers for today's inputs whole:
    same files, and (for a market that ran) every current cell present plus
    its ratio file still on disk - the ratio series ships from the same run
    as the trades it sits under, so a missing file voids the entry rather
    than being rebuilt from a separate load."""
    if ent is None or ent.get("manifest") != manifest:
        return False
    if ent.get("excluded"):
        return True
    return (set(ent.get("cells", {})) == cell_names_for(key)
            and (OUT_RATIO / f"{key}.json").exists())


def entry_order_metrics(trades):
    """Longest losing streak and max cumulative-R drawdown, ENTRY order."""
    seq = sorted(trades, key=lambda t: t["entry_ts"])
    streak = longest = 0
    cum = peak = 0.0
    max_dd_r = 0.0
    for t in seq:
        if t["net_r"] < 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
        cum += t["net_r"]
        peak = max(peak, cum)
        max_dd_r = max(max_dd_r, peak - cum)
    return longest, round(max_dd_r, 2)


def solve_risk(trades, target=6.0, tol=0.0005):
    """The risk % that puts this trade list at `target` max drawdown -
    the same bisection the report and the R-cut page use (drawdown rises
    monotonically with risk). Here so the CHART can draw every cell at
    equal pain: at one bet size the tallest curve is partly just the
    deepest hole that cell was allowed to dig (Lode, 2026-08-11)."""
    if not trades:
        return None
    def dd(risk):
        return run_1m.portfolio_replay(trades, risk_pct=risk)[1]
    lo, hi = 0.0, 8.0
    while dd(hi) < target:
        hi *= 2
        if hi > 64:
            return None
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if dd(mid) < target:
            lo = mid
        else:
            hi = mid
    return lo


def close_dd_pct(curve, start_capital=100_000.0):
    """Max drawdown on daily CLOSING balances, peak and trough both read
    at the bell: the gentler figure the main report shows next to the
    worst-reached one. The curve is per-exit, so the last point of each
    UTC day is that day's close."""
    eod = {}
    for ts, v in curve:
        eod[ts // 86400] = v
    peak, worst = start_capital, 0.0
    for day in sorted(eod):
        peak = max(peak, eod[day])
        worst = max(worst, (peak - eod[day]) / peak * 100.0)
    return round(worst, 2)


def main():
    reuse = "--no-reuse" not in sys.argv[1:]
    keys = [a for a in sys.argv[1:] if not a.startswith("--")] or (
        run_1m.ELIGIBLE_FUTURES + run_1m.ETFS + list(run_1m.BINANCE))
    results = {name: {"trades": [], "rows": []} for name, _, _, _ in VARIANTS}
    skipped, sessions = [], []
    sig = grid_sig()
    # Old cache entries ride along with whatever this run recomputes: an
    # entry only ever answers for its own manifest, so keeping the rest is
    # what lets a subset run (`run_1m_matrix.py GC`) refresh one market's
    # entry without voiding the others.
    cache_markets = load_matrix_cache(sig) if reuse else {}
    # Phase timers: where a matrix run's wall clock goes (load = market
    # data, engine = the cell passes, ratio = the pane series). Printed
    # per market and totalled at the end, so the next time a step's cost
    # drifts from its documentation the run itself says so.
    tot = {"load": 0.0, "engine": 0.0, "ratio": 0.0}
    engine_passes = ratio_passes = cached_markets = 0
    t_run = time.perf_counter()
    for key in keys:
        t0 = time.perf_counter()
        try:
            manifest = market_manifest(key)
        except Exception:
            # An unknown or unmapped key; market_inputs below reports it
            # the way it always has.
            manifest = None
        if reuse and entry_reusable(cache_markets.get(key), key, manifest):
            ent = cache_markets[key]
            if ent.get("excluded"):
                skipped.append(ent["excluded"])
                print(f"{key}: EXCLUDED (cached) - "
                      f"{ent['excluded']['reason']}", flush=True)
                continue
            sessions.append([date.fromisoformat(x) for x in ent["calendar"]])
            ran = 0
            base_line = "-"
            for name, _dials, markets, _props in VARIANTS:
                if markets is not None and key not in markets:
                    continue
                cell = ent["cells"][name]
                results[name]["trades"].extend(cell["trades"])
                results[name]["rows"].append(cell["row"])
                ran += 1
                if name == BASELINE_NAME:
                    base_line = (f"{cell['row']['trades']}t "
                                 f"{cell['row']['net_r_total']}R")
            cached_markets += 1
            print(f"{key}: {BASELINE_NAME} {base_line}  |  {ran} cells"
                  f"  |  cached ({time.perf_counter() - t0:.1f}s)",
                  flush=True)
            continue
        try:
            inputs, excluded = run_1m.market_inputs(key)
        except Exception as exc:
            skipped.append({"market": key,
                            "reason": f"{type(exc).__name__}: {exc}"})
            print(f"{key}: ERROR {type(exc).__name__}: {exc}", flush=True)
            continue
        if inputs is None:
            skipped.append(excluded)
            print(f"{key}: EXCLUDED - {excluded['reason']}", flush=True)
            if manifest is not None:
                cache_markets[key] = dict(manifest=manifest,
                                          excluded=excluded)
                save_matrix_cache(sig, cache_markets)
            continue
        days, files, tick, note = inputs
        t_load = time.perf_counter() - t0
        tot["load"] += t_load
        # Every market that loads contributes its trading dates to the
        # market-day calendar the curves are drawn on, whatever any cell
        # made of it - including the nine outside the filtered universe,
        # since the whole grid runs the filtered universe.
        sessions.append([d.date for d in days])
        # The progress line quotes the BASELINE cell and counts the rest:
        # 27 cells x "name Nt R" is a line nobody reads, and the full
        # per-market figures are in the JSON for every cell anyway.
        ran = 0
        base_line = "-"
        ent_cells = {}
        t0 = time.perf_counter()
        for name, dials, markets, _props in VARIANTS:
            if markets is not None and key not in markets:
                continue
            trades, summary = run_1m.engine_1m.run_market(
                days, files, tick, **dials)
            engine_passes += 1
            # Normalise to plain Python floats (bit-exact - the values do
            # not move) so a fresh market and a cached one feed the report
            # the same TYPES. The engine's numbers arrive as numpy floats,
            # and numpy rounds a half-way case by scaling where Python
            # rounds it decimally: variant 8's max drawdown of 7.335 read
            # 7.34 fresh and 7.33 from cache (2026-08-21) with every trade
            # bit-identical. Python's is the decimally-correct rounding,
            # so plain floats are the normal form.
            trades = [{k: float(v) if isinstance(v, float) else v
                       for k, v in t.items()} for t in trades]
            summary = {k: float(v) if isinstance(v, float) else v
                       for k, v in summary.items()}
            for t in trades:
                t["market"] = key
            summary.update(market=key, note=note, tick=tick)
            results[name]["trades"].extend(trades)
            results[name]["rows"].append(summary)
            ent_cells[name] = dict(trades=trades, row=summary)
            ran += 1
            if name == BASELINE_NAME:
                base_line = (f"{summary['trades']}t "
                             f"{summary['net_r_total']}R")
        # The geometry-ratio pane's data: three series, one per stop
        # anchor, from the bars already loaded. `both_sides` must stay 0 -
        # the pane reports the wider of two simultaneously armed ladders,
        # and if that ever starts happening the choice should be made on
        # purpose rather than discovered later.
        t_engine = time.perf_counter() - t0
        tot["engine"] += t_engine
        OUT_RATIO.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        series = {}
        for label, mode in STOP_MODE_BY_LABEL.items():
            s = run_1m.engine_1m.ratio_series(days, files, tick,
                                              stop_mode=mode)
            series[label] = {"bull": s["bull"], "bear": s["bear"]}
            ratio_passes += 1
        (OUT_RATIO / f"{key}.json").write_text(
            json.dumps({"market": key, "tick": tick, "series": series},
                       separators=(",", ":")), encoding="utf-8")
        t_ratio = time.perf_counter() - t0
        tot["ratio"] += t_ratio
        if manifest is not None:
            # Checkpoint after every computed market, so a stopped run
            # keeps what it finished - the entries are independent.
            cache_markets[key] = dict(
                manifest=manifest, excluded=None,
                calendar=[d.date.isoformat() for d in days],
                cells=ent_cells)
            save_matrix_cache(sig, cache_markets)
        n = sum(len(v[side]["main"]) for v in series.values()
                for side in ("bull", "bear"))
        print(f"{key}: {BASELINE_NAME} {base_line}  |  {ran} cells"
              f"  |  ratio {n} pts"
              f"  |  load {t_load:.1f}s engine {t_engine:.1f}s"
              f" ratio {t_ratio:.1f}s", flush=True)

    t_all = time.perf_counter() - t_run
    other = t_all - sum(tot.values())
    print(f"\nTIMING: load {tot['load']:.0f}s"
          f"  |  engine {tot['engine']:.0f}s ({engine_passes} passes)"
          f"  |  ratio {tot['ratio']:.0f}s ({ratio_passes} passes)"
          f"  |  cached {cached_markets} markets"
          f"  |  other {other:.0f}s  |  market loop {t_all:.0f}s", flush=True)

    calendar = run_1m.calendar_union(sessions)
    if calendar:
        print(f"\nCALENDAR: {len(calendar)} market days, {calendar[0]} to "
              f"{calendar[-1]} - every curve is drawn on it and runs to "
              f"the right-hand date", flush=True)
    report = {}
    for name, dials, markets, props in VARIANTS:
        trades = sorted(results[name]["trades"],
                        key=lambda t: t["entry_ts"])
        final, max_dd, curve = run_1m.portfolio_replay(trades)
        # The plotted curve is the LEVERED one - every cell at the same 6%
        # max drawdown, risk solved per cell - so the chart compares equal
        # pain instead of handing the deepest hole the tallest line. The
        # table keeps the 1% figures beside the solved ones.
        risk6 = solve_risk(trades)
        if risk6:
            final6, _, curve6 = run_1m.portfolio_replay(trades,
                                                        risk_pct=risk6)
        else:
            final6, curve6 = final, curve
        streak, max_dd_r = entry_order_metrics(trades)
        wins = sum(1 for t in trades if t["net_r"] > 0)
        # The exit mix is what this grid is actually about: the clause
        # moves trades between no_confirm and the other two, the stop
        # anchor moves them between stop and the settlement exits.
        mix = {}
        for r in ("stop", "no_confirm", "close1", "data_end"):
            sub = [t for t in trades if t["reason"] == r]
            mix[r] = dict(n=len(sub),
                          wins=sum(1 for t in sub if t["net_r"] > 0),
                          net_r=round(sum(t["net_r"] for t in sub), 2))
        # Geometry-dial bookkeeping, summed over markets: how many entries
        # the dial refused and how often it had to abstain for want of a
        # window. Zero on every cell that leaves the dial off.
        geom = {k: sum(r.get(k, 0) for r in results[name]["rows"])
                for k in ("refused_wide", "refused_tight", "range_unjudged")}
        report[name] = dict(
            props=props,
            slug=variant_slug(name),
            baseline=(name == BASELINE_NAME),
            color=COLORS[name],
            dials=dials,
            markets=sorted(markets) if markets is not None else None,
            markets_run=len(results[name]["rows"]),
            geometry=geom,
            trades=len(trades),
            win_rate=round(100 * wins / len(trades), 1) if trades else None,
            net_r=round(sum(t["net_r"] for t in trades), 2),
            longest_losing_streak=streak,
            max_dd_r=max_dd_r,
            final_cash=round(final, 2),
            max_dd_pct=round(max_dd, 2),
            max_dd_close_pct=close_dd_pct(curve),
            risk_6pct=round(risk6, 3) if risk6 else None,
            final_6pct=round(final6, 2),
            exit_mix=mix,
            curve=curve6,
        )
        print(f"\n{name} [lockout {props['lockout']}, {props['stop']}, "
              f"{props['band']}, {props['markets']} markets]: "
              f"{report[name]['trades']} trades, "
              f"wr {report[name]['win_rate']}%, "
              f"net {report[name]['net_r']}R, "
              f"longest losing streak {streak}, "
              f"max DD {report[name]['max_dd_pct']}% "
              f"(closes {report[name]['max_dd_close_pct']}%, "
              f"${report[name]['final_cash']:,.0f}) "
              f"-> at 6% DD: {report[name]['risk_6pct']}% risk, "
              f"${report[name]['final_6pct']:,.0f}", flush=True)

    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(dict(
        strategy="quickfix1m1dc v2 (audit decisions 2026-08-06)",
        audit_doc="docs/quickfix1m1dc_audit.md",
        params=dict(risk_pct=run_1m.engine_1m.RISK_PCT,
                    entry_slip_ticks=run_1m.engine_1m.ENTRY_SLIP_TICKS,
                    min_ladder=run_1m.engine_1m.MIN_LADDER,
                    min_tested=run_1m.engine_1m.MIN_REVERSALS),
        variants={n: {k: v for k, v in r.items() if k != "curve"}
                  for n, r in report.items()},
        # The market-day grid every curve here is drawn on. It is in the
        # JSON because the pages built FROM this file draw curves too
        # (--page, build_1m_report.py --variant) and none of them loads a
        # single bar; rebuilding it there would cost ~100s to draw a line.
        calendar=[d.isoformat() for d in calendar],
        per_market={n: results[n]["rows"] for n, _, _, _ in VARIANTS},
        trades={n: results[n]["trades"] for n, _, _, _ in VARIANTS},
        excluded=skipped), indent=1) + "\n", encoding="utf-8")

    write_page(report, calendar)
    print(f"\nwrote {OUT_JSON.name} and {OUT_HTML.name}")


def rebuild_page():
    """Redraw the page from the matrix JSON, with NO backtest.

    The grid is ~9 minutes and the page is the part that gets edited, so
    a layout or colour change must not cost a data pass. The curves are
    the only thing the JSON does not carry, and they come back from the
    stored trades in seconds (`portfolio_replay` + the same 6% solve).
    Colours are recomputed from the properties rather than read back, so
    a palette edit lands here too. Usage: `python run_1m_matrix.py
    --page`.
    """
    m = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    report = {}
    for name, v in m["variants"].items():
        trades = sorted(m["trades"][name], key=lambda t: t["entry_ts"])
        risk6 = solve_risk(trades)
        _final, _dd, curve = run_1m.portfolio_replay(
            trades, risk_pct=risk6) if risk6 else run_1m.portfolio_replay(
            trades)
        report[name] = dict(v, color=color_for(v["props"]), curve=curve)
    calendar = m.get("calendar")
    if not calendar:
        calendar = run_1m.calendar_fallback(
            [t for cell in m["trades"].values() for t in cell])
        print("WARNING: this matrix JSON predates the market-day calendar. "
              "The curves are drawn on calendar days and stop at the last "
              "exit; re-run the matrix to get the real grid.")
    write_page(report, calendar)
    print(f"redrew {OUT_HTML.name} from {OUT_JSON.name} "
          f"({len(report)} cells, no backtest)")


def write_page(report, calendar):
    """The matrix page: one chart, one table, a checkbox per row."""
    lib = run_1m.LIB_PATH.read_text(encoding="utf-8")
    # ONE grid for all 27 curves (Lode, 2026-08-18): resampled to the
    # market days and stepped, so a quiet fortnight is a flat fortnight
    # instead of a diagonal, and every cell starts and ends on the same
    # x whatever its own first and last trade were. That is what makes
    # the lines comparable side by side - a cell that stopped trading in
    # July used to be a SHORTER line and read as a shorter history.
    first = min((c[0][0] for c in (r["curve"] for r in report.values()) if c),
                default=None)
    grid = run_1m.market_day_grid(
        calendar,
        datetime.fromtimestamp(first, tz=timezone.utc).date()
        if first else date.today())
    # The row order IS the variant order, and so is the series order: the
    # checkbox carries its row's index and toggles series[i], so nothing
    # here may be sorted or filtered on its way to the page.
    head = "".join(
        f"<tr data-i='{i}'{' class=base' if r['baseline'] else ''}>"
        f"<td><input type='checkbox' class='v' data-i='{i}' checked></td>"
        f"<td>{n}{' *' if r['baseline'] else ''}</td>"
        f"<td>{r['props']['lockout']}</td><td>{r['props']['stop']}</td>"
        f"<td>{r['props']['band']}</td><td>{r['markets_run']}</td>"
        f"<td>{r['trades']}</td><td>{r['win_rate']}</td>"
        f"<td>{r['net_r']}</td><td><b>{r['longest_losing_streak']}</b></td>"
        f"<td>{r['max_dd_r']}</td><td>{r['max_dd_pct']}%</td>"
        f"<td>{r['max_dd_close_pct']}%</td>"
        f"<td>${r['final_cash']:,.0f}</td>"
        # A cell whose drawdown never reaches 6% at any bet size has no
        # solve: it is drawn at 1% and says so rather than printing a
        # None. Only reachable on a thin sample (a debug run over one
        # market), never on the published universe.
        f"<td>{str(r['risk_6pct']) + '%' if r['risk_6pct'] else '- (1%)'}</td>"
        f"<td><b>${r['final_6pct']:,.0f}</b></td>"
        f"<td>{r['exit_mix']['close1']['wins']} / "
        f"{r['exit_mix']['close1']['n'] - r['exit_mix']['close1']['wins']} / "
        f"{r['exit_mix']['stop']['n']} / "
        f"{r['exit_mix']['no_confirm']['n']}</td>"
        f"<td>{(str(r['geometry']['refused_wide'] + r['geometry']['refused_tight'])
                + ' / ' + str(r['geometry']['range_unjudged']))
               if (r['geometry']['refused_wide'] + r['geometry']['refused_tight'])
               else ''}</td>"
        f"<td><i style='background:{r['color']}'></i></td></tr>"
        for i, (n, r) in enumerate(report.items()))
    series = "\n".join(
        f"series.push(chart.addLineSeries({{color:'{r['color']}', "
        f"lineWidth:2, lineType:LightweightCharts.LineType.WithSteps, "
        f"priceLineVisible:false, lastValueVisible:false}})"
        f");\nseries[series.length-1].setData("
        f"{json.dumps([{'time': run_1m.grid_seconds(d), 'value': v}
                       for d, v in run_1m.carry_forward(r['curve'], grid)])});"
        for r in report.values())
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>quickfix1m1dc v2 - dial matrix</title><style>
body {{ background:#fff; color:#222; font:13px -apple-system,Segoe UI,
sans-serif; margin:0; padding:14px; }}
/* Fill the window's height with the chart (Lode, 2026-08-11: a taller
   plot spreads the y axis, so the lines separate and the scale reads).
   autoSize on the chart tracks this through window resizes. */
#chart {{ height:calc(100vh - 330px); min-height:480px; }}
/* SCOPED TO #tbl. A bare `table` rule also hits the <table> that
   lightweight-charts builds inside the chart container, and a margin-top on
   it pushes the whole chart down so the time axis hangs out of its box and
   the date labels are cut in half (found on the R-cut page, 2026-08-10, and
   this page had it too). */
#tbl {{ border-collapse:collapse; margin-top:14px; }}
#tbl td, #tbl th {{ padding:4px 10px; border-bottom:1px solid #ddd;
text-align:right; }}
#tbl td:first-child, #tbl th:first-child {{ text-align:left; }}
#tbl td:nth-child(2), #tbl th:nth-child(2),
#tbl td:nth-child(3), #tbl th:nth-child(3),
#tbl td:nth-child(4), #tbl th:nth-child(4),
#tbl td:nth-child(5), #tbl th:nth-child(5) {{ text-align:left; }}
/* The four PROPERTY columns are what turns a numbered cell back into a
   model, so they are boxed off from the metrics beside them. */
#tbl td:nth-child(6), #tbl th:nth-child(6) {{ border-right:2px solid #bbb; }}
#tbl td i {{ display:inline-block; width:22px; height:10px; }}
#tbl tr.off td {{ opacity:.35; }}
#tbl tr.base td:nth-child(2) {{ font-weight:600; }}
#ctl {{ margin-top:10px; }}
#ctl button {{ font:inherit; padding:2px 10px; margin-right:6px; }}
</style></head><body>
<b>quickfix1m1dc v2 - the dial matrix</b>
<span style="color:#666"> market-order entries,
{run_1m.engine_1m.ENTRY_SLIP_TICKS} ticks entry slippage,
{run_1m.engine_1m.SLIP_STOP_TICKS} on a stop and
{run_1m.engine_1m.SLIP_SCHEDULED_TICKS} on a settlement exit, 1% risk on
the level-to-stop distance, no tightening, overnight window blocked, no
confirmation clause.
Every combination of the four properties is its own engine run, and the
properties are COLUMNS rather than a name, so the table can be read
across as well as down.
<b>lockout</b> = at most N ENTRIES per market per session, expiring at
the session boundary (a position carried in from the previous session
and stopped intraday does not spend the allowance).
<b>stop</b>: <b>4th/5th</b> one tick beyond the 5th reversal (4th when
only four), <b>hybrid</b> whichever of that and the session's running
extreme at entry is further away, <b>wick</b> the running extreme alone -
a tick above the entry day's high for a short, below its low for a long.
<b>band</b> = the geometry cut: refuse an entry whose level-to-stop
distance is outside that fraction of the PREVIOUS TRADING DAY's high-low range
(<b>full</b> = no cut). THE BAND LADDER IS THE STOP ANCHOR'S OWN: each
keeps <b>000-050</b> and <b>full</b> as fixed comparison points and
carries its chosen band in the middle slot &mdash; 4th/5th
<b>000-060</b>, hybrid <b>020-060</b>, wick <b>020-050</b> &mdash; read
off that anchor's own R-cut grid under the trading-day window. A band
measured on one anchor was never evidence about the other.

<b>markets</b>: {len(HUMAN_APPROVED)} = the chart-structure inspection's
universe (audit s.16, never a judgment on a market's backtest result),
31 = every market that produced a run. <b>variant 30</b> is the market
filter's OFF-STATE and the only cell that leaves the filtered universe;
it sits at lockout 1 / hybrid / 000-050 rather than at the published
dials, so it pairs with <b>variant 4</b> and the filter is the only
difference between them.
The published baseline is <b>{BASELINE_NAME}</b> (marked *), and it is an
ordinary row here.
Read the losing streak and the drawdown first.</span>
<div style="color:#666; margin-top:8px"><b style="color:#222">The curves
are drawn at a constant 6% max drawdown</b> - risk per trade solved per
cell by bisection (the table's <b>risk @6% DD</b> column), because at one
shared bet size the tallest curve is partly just the deepest hole that
cell was allowed to dig. The 1% figures stay in the table beside the
solved ones. <b style="color:#222">Colour reads as a family</b>: hue is
the stop anchor (green 4th/5th, blue hybrid, orange wick), the shade
within a hue is the band, and the lighter the line the looser the
lockout. The two extra BAND cells take the outermost shade of their own
anchor's hue, so they still read as part of that family; the one
31-market cell is magenta, outside every family, because what makes it
different is not one of those three dials.</div>
<div id="chart"></div>
<div id="ctl"><button id="allon">all on</button>
<button id="alloff">all off</button>
<span style="color:#666">- untick a row to drop its curve; the baseline
too.</span></div>
<table id="tbl"><tr><th></th><th>variant</th>
<th>lockout</th><th>stop</th><th>band</th>
<th title="markets that produced a run in this cell">markets</th>
<th>trades</th><th>wr%</th><th>netR</th>
<th>longest losing streak</th><th>max DD (R)</th><th>max DD %</th>
<th>max DD close %</th><th>final @1%</th>
<th>risk @6% DD</th><th>final @6% DD</th>
<th>day-2 win / day-2 loss / stop / abort</th>
<th title="entries the geometry dial refused / times it abstained for want of a window. Since the trading-day window was adopted (2026-08-17) it reaches the previous trading date rather than a flat 24h, so it abstains only in the first bars after a contract roll">geom refused / unjudged</th>
<th></th></tr>{head}</table>
<script>{lib}</script><script>
const chart = LightweightCharts.createChart(
  document.getElementById('chart'),
  {{ autoSize: true,
     layout: {{ background: {{ color: '#ffffff' }}, textColor: '#333',
     attributionLogo: false }},
     grid: {{ vertLines: {{ visible: false }},
              horzLines: {{ visible: false }} }},
     timeScale: {{ timeVisible: true }} }});
const series = [];
{series}
chart.timeScale().fitContent();
// series[i] IS the row with data-i="i" - both are written in variant
// order and neither list is ever sorted, which is the whole contract
// between the table and the chart.
const boxes = [...document.querySelectorAll('#tbl input.v')];
function apply(cb) {{
  const i = +cb.dataset.i;
  series[i].applyOptions({{visible: cb.checked}});
  cb.closest('tr').classList.toggle('off', !cb.checked);
}}
boxes.forEach(cb => cb.addEventListener('change', () => apply(cb)));
function setAll(on) {{
  boxes.forEach(cb => {{ cb.checked = on; apply(cb); }});
}}
document.getElementById('allon').onclick = () => setAll(true);
document.getElementById('alloff').onclick = () => setAll(false);
</script></body></html>"""
    OUT_HTML.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    if "--page" in sys.argv[1:]:
        rebuild_page()
    else:
        main()
