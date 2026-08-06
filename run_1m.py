"""Run quickfix1m1dc across all backtest-eligible markets (v2).

Eligible = fingerprint-verified futures (all GLBX, uniform session rules)
plus the two ETFs, which are gated inline: their RTH-derived daily bars
must match the Socrates bars on >= 90% of dates or they are excluded.
Markets excluded pending verification (ZB, BTC, SR3, PL, FGBL, SB, DX)
are not run — Lode's quality ruling: a backtest against bars that do not
match Socrates is meaningless.

Levels and prev_close are decoded with the same per-market price codecs
as the fingerprint (ZN 64ths, ZW/ZC eighths) — the reversal levels in the
xlsx are in Socrates notation too.

Outputs: output/quickfix1m1dc_all.json, output/quickfix1m1dc_report.html
(built by build_1m_report.py), console summary.
Usage: python run_1m.py [KEY ...] (default: all eligible).
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / ".." / "charter" / "scripts"))
sys.path.insert(0, str(HERE / ".." / "data_center" / "scripts"))
import charting_core as cc  # noqa: E402
from expand_process import (  # noqa: E402
    CLOSE_FROM_SETTLEMENT,
    PRICE_CODEC,
    SENTINEL,
    TRADE_SESSION_BARS,
    decode_price,
    trading_date_series,
)

import engine_1m  # noqa: E402

DC = HERE / ".." / "data_center"
ARRAY_ROOT = HERE / ".." / "hyperliquid_bot" / "data" / "array"
META = DC / "metadata"
OUT_JSON = HERE / "output" / "quickfix1m1dc_all.json"
# The page is built by build_1m_report.py (the report), and the 2x2 by
# run_1m_matrix.py, which reads this LIB_PATH.
LIB_PATH = DC / "scripts" / "lightweight-charts.4.2.3.standalone.js"

PX_SCALE = 1e-9
ACTIVATION_UTC = "07:35"
# The published baseline (Lode, 2026-08-06): the matrix winner on every
# priority metric - no settlement tightening, no entries before the
# day's own update is active. run_1m_matrix.py still runs all four.
BASELINE = dict(tighten=False, allow_pre_activation=False)
STAT_SETTLEMENT = 3
FILES_FROM = date(2025, 12, 20)
ETF_MATCH_MIN = 0.90

ELIGIBLE_FUTURES = ["GC", "YM", "6E", "6J", "LE", "HG", "CL", "NG", "PA",
                    "NQ", "ES", "SI", "ZW", "ZC", "ZN",
                    "PL",   # verified 2026-08-03, market-by-market pass
                    "ZB",   # degraded era included on H/L evidence;
                            # entry blackout Apr 6-16
                    "SB",   # trade-derived, close ~ settlement +-1 tick
                    "DX",   # H/L exchange-exact; open vendor-noisy
                            # (Mondays), close ~ settlement
                    "FGBL",  # open+settlement exact; vendor clips H/L
                             # on ~28% of days (levels caveat)
                    "BTC",   # QUARTERLY contract; M6 segment only —
                             # U6 era excluded for sparsity (Lode)
                    "CC", "KC"]  # obsolete softs, frozen calendars,
                                 # window Jan 12-Apr 17
ETFS = ["URA", "VIXY",
        # Obsolete ETFs (window Jan 12-Apr 17), verified vs EQUS.SUMMARY:
        # 5 perfect with cent-truncation, GLD within 1 cent.
        "UDOW", "GLD", "SLV", "USO", "UNG", "WEAT"]

# Binance spot crypto (obsolete, free Binance Vision klines). Socrates
# shows integer-rounded UTC-day bars; inline gate verifies that.
BINANCE = {"BTCB": ("Bitcoin_Per_USD_Binance", "BTCUSDT"),
           "ETHB": ("Ethereum_Per_USD_Binance", "ETHUSDT")}

OBSOLETE_INFO = {
    "UDOW": "ProShares_UltraPro_Dow",
    "GLD": "SPDR_Gold_Shares",
    "SLV": "iShares_Silver_Trust",
    "USO": "United_States_Oil_Fund_LP",
    "UNG": "United_States_Natural_Gas_Fund_LP",
    "WEAT": "Teucrium_Wheat_Fund",
    "CC": "Cocoa_NYCSCE_Futures",
    "KC": "Coffee_NYCSCE_Futures",
    "BTCB": "Bitcoin_Per_USD_Binance",
    "ETHB": "Ethereum_Per_USD_Binance",
}

MAPPING = json.loads(
    (DC / "config" / "market_mapping.json").read_text(encoding="utf-8"))


def market_info(key):
    m = next((m for m in MAPPING["markets"] if m.get("key") == key), None)
    if m is not None:
        return m
    return {"key": key, "array_dir": OBSOLETE_INFO[key]}


def market_dir(m):
    return DC / "data" / f"{m['array_dir']}_{m['key']}"


def load_levels_and_socbars(m):
    """LevelsFiles (codec-decoded) + the Socrates daily OHLC per date."""
    codec = PRICE_CODEC.get(m["key"])

    def dec(x):
        return decode_price(x, codec) if codec else x

    files, socbars = [], {}
    for p in sorted((ARRAY_ROOT / m["array_dir"]).glob(
            "*/daily/*_array.xlsx")):
        stamp = p.stem.split("_")[-2].rstrip("d")
        try:
            d = date(2000 + int(stamp[:2]), int(stamp[2:4]), int(stamp[4:6]))
        except ValueError:
            continue
        if d < FILES_FROM:
            continue
        try:
            _v, ohlc, rev = cc.parse_array(p)
        except Exception:
            continue
        if ohlc is None:
            continue
        socbars[d] = {k: dec(ohlc[k])
                      for k in ("open", "high", "low", "close")}
        activation = pd.Timestamp(f"{d + timedelta(days=1)} {ACTIVATION_UTC}",
                                  tz="UTC")
        files.append(engine_1m.LevelsFile(
            publish_date=d, activation_ts=activation,
            bull=sorted(dec(x) for x in (rev["bull_major"] | rev["bull_minor"])),
            bear=sorted(dec(x) for x in (rev["bear_major"] | rev["bear_minor"])),
            prev_close=dec(ohlc["close"])))
    files.sort(key=lambda f: f.activation_ts)
    return files, socbars


def load_settlements(m):
    stats = pd.read_parquet(market_dir(m) / "statistics" / "statistics.parquet")
    stats = stats[stats["stat_type"] == STAT_SETTLEMENT].reset_index()
    stats = stats[(stats["price"] > 0) & (stats["price"] < SENTINEL)]
    if stats["ts_ref"].isna().all():
        # XEUR leaves ts_ref NaT: key by publication trading date.
        stats["trading_date"] = trading_date_series(
            stats["ts_event"], m["dataset"], m["key"])
    else:
        stats["trading_date"] = stats["ts_ref"].dt.date
    out = {}
    for (sym, d), grp in stats.groupby(["symbol", "trading_date"]):
        grp = grp.sort_values("ts_event")
        out[(sym, d)] = (grp["ts_event"].iloc[0],
                         grp["price"].iloc[-1] * PX_SCALE)
    return out


def futures_days(m):
    calendar = json.loads(
        (META / f"roll_calendar_{m['key']}.json").read_text(encoding="utf-8"))
    # Trade-close markets (ZB, SB, DX) take their day-close events from
    # the session's last bar; SB/DX have no statistics at all (IFUS $95).
    # FGBL is trade-BARRED but settlement-CLOSED: its Socrates close is
    # the Eurex settlement, which we own.
    trade_close = (m["key"] in TRADE_SESSION_BARS
                   and m["key"] not in CLOSE_FROM_SETTLEMENT)
    settlements = {} if trade_close else load_settlements(m)
    days, excluded = [], 0
    blackout = set()
    for b in calendar.get("entry_blackout", []):
        d = date.fromisoformat(b["first_date"])
        while d <= date.fromisoformat(b["last_date"]):
            blackout.add(d)
            d += timedelta(days=1)
    segments = calendar["segments"]
    for i, seg in enumerate(segments):
        path = market_dir(m) / "bars" / f"{seg['symbol']}.parquet"
        if not path.exists():
            continue
        bars = pd.read_parquet(path).reset_index()
        # ICE minute data carries zero/sentinel price rows; ALL FOUR
        # fields must be sane. v1 filled at the level so a bad OPEN was
        # latent - v2's market-order fill uses it (CC blowup, 2026-08-06).
        px = bars[["open", "high", "low", "close"]]
        bars = bars[(px.gt(0).all(axis=1))
                    & (px.lt(SENTINEL).all(axis=1))]
        ts_ct = bars["ts_event"].dt.tz_convert("America/Chicago")
        bars["trading_date"] = (ts_ct + pd.Timedelta(hours=7)).dt.date
        first = date.fromisoformat(seg["first_date"])
        last = date.fromisoformat(seg["last_date"])
        d = first
        while d <= last:
            day_bars = bars[bars["trading_date"] == d]
            if trade_close and not day_bars.empty:
                last_bar = day_bars.sort_values("ts_event").iloc[-1]
                settle = (last_bar["ts_event"],
                          last_bar["close"] * PX_SCALE)
            else:
                settle = settlements.get((seg["symbol"], d))
            if not day_bars.empty and settle is not None:
                allowed = not ((i > 0 and d == first) or d == last
                               or d in blackout)
                if not allowed:
                    excluded += 1
                days.append(engine_1m.Day(
                    date=d, contract=seg["symbol"],
                    bars=list(zip(day_bars["ts_event"],
                                  day_bars["open"] * PX_SCALE,
                                  day_bars["high"] * PX_SCALE,
                                  day_bars["low"] * PX_SCALE,
                                  day_bars["close"] * PX_SCALE)),
                    settle_ts=settle[0], settle_price=settle[1],
                    entries_allowed=allowed))
            d += timedelta(days=1)
    return days, excluded


# Primary-exchange 1-min files per ETF (Lode, 2026-08-03: option 1).
# Verification happened OFFLINE against EQUS.SUMMARY (the official
# consolidated daily summary Socrates uses): URA 63/69 exact, VIXY
# 133/141. CAVEAT: single-venue bars miss consolidated extremes by >5c
# on ~40% of days — level-touch noise at highs/lows, documented in
# docs/socrates_data_conventions.md.
ETF_PRIMARY = {"URA": "URA_ARCX.parquet", "VIXY": "VIXY_BATS.parquet",
               "UDOW": "UDOW_ARCX.parquet", "GLD": "GLD_ARCX.parquet",
               "SLV": "SLV_ARCX.parquet", "USO": "USO_ARCX.parquet",
               "UNG": "UNG_ARCX.parquet", "WEAT": "WEAT_ARCX.parquet"}


def etf_days(m):
    """RTH days for an ETF from its primary-exchange bars. The window
    runs to 16:05 NY so the closing-auction print (the official close)
    is always inside the last bar."""
    path = market_dir(m) / "bars" / ETF_PRIMARY[m["key"]]
    bars = pd.read_parquet(path).reset_index()
    ts_ny = bars["ts_event"].dt.tz_convert("America/New_York")
    bars["ny_date"] = ts_ny.dt.date
    rth = bars[(ts_ny.dt.time >= pd.Timestamp("09:30").time())
               & (ts_ny.dt.time < pd.Timestamp("16:05").time())]
    days = []
    for d, grp in rth.groupby("ny_date"):
        grp = grp.sort_values("ts_event")
        c = grp["close"].iloc[-1] * PX_SCALE
        days.append(engine_1m.Day(
            date=d, contract=m["key"],
            bars=list(zip(grp["ts_event"], grp["open"] * PX_SCALE,
                          grp["high"] * PX_SCALE, grp["low"] * PX_SCALE,
                          grp["close"] * PX_SCALE)),
            settle_ts=grp["ts_event"].iloc[-1], settle_price=c))
    if days:
        days[-1].entries_allowed = False  # window end, no exit day left
    return days


def binance_days_and_match(key, socbars):
    """UTC-day sessions from Binance Vision 1m klines. Socrates shows
    integer-rounded values, so the gate compares at +-0.5."""
    _array_dir, sym = BINANCE[key]
    frames = []
    for z in sorted((DC / "data" / "_binance").glob(f"{sym}-1m-*.zip")):
        df = pd.read_csv(z, header=None, usecols=[0, 1, 2, 3, 4, 5],
                         names=["t", "open", "high", "low", "close",
                                "volume"])
        frames.append(df)
    df = pd.concat(frames)
    unit = "us" if df["t"].iloc[0] > 1e14 else "ms"
    df["ts"] = pd.to_datetime(df["t"], unit=unit, utc=True)
    df["d"] = df["ts"].dt.date
    days, match, checked = [], 0, 0
    for d, grp in df.groupby("d"):
        grp = grp.sort_values("ts")
        o = grp["open"].iloc[0]
        h = grp["high"].max()
        l = grp["low"].min()
        c = grp["close"].iloc[-1]
        soc = socbars.get(d)
        if soc is not None:
            checked += 1
            if max(abs(soc["open"] - o), abs(soc["high"] - h),
                   abs(soc["low"] - l), abs(soc["close"] - c)) <= 0.5:
                match += 1
        days.append(engine_1m.Day(
            date=d, contract=sym,
            bars=list(zip(grp["ts"], grp["open"], grp["high"],
                          grp["low"], grp["close"])),
            settle_ts=grp["ts"].iloc[-1], settle_price=c))
    if days:
        days[-1].entries_allowed = False
    rate = match / checked if checked else 0.0
    return days, rate


def market_inputs(key):
    """(days, files, tick, note) for a market, or (None, exclusion dict).
    Loading is the slow part; run_1m_matrix.py calls this once per market
    and runs the engine dials on the same inputs."""
    m = market_info(key)
    files, socbars = load_levels_and_socbars(m)
    if key in BINANCE:
        days, rate = binance_days_and_match(key, socbars)
        if rate < 0.9:
            return None, {"market": key, "status": "EXCLUDED",
                          "reason": f"Binance UTC-day match {rate:.2f} "
                                    f"< 0.9"}
        return (days, files, 0.01,
                f"Binance spot, UTC days, match {rate:.2f}"), None
    if key in ETFS:
        days = etf_days(m)
        tick = 0.01
        note = ("ETF, primary-exchange bars; verified offline vs "
                "EQUS.SUMMARY")
    else:
        calendar = json.loads(
            (META / f"contract_calendar_{key}.json").read_text(
                encoding="utf-8")) if key != "GC" else json.loads(
            (META / "contract_calendar_GC.json").read_text(encoding="utf-8"))
        tick = calendar[0]["tick_size"]
        days, _ = futures_days(m)
        note = "futures, frozen calendar"
    if not days:
        return None, {"market": key, "status": "EXCLUDED",
                      "reason": "no tradable days"}
    return (days, files, tick, note), None


def run_market(key, tighten=True, allow_pre_activation=True):
    inputs, excluded = market_inputs(key)
    if inputs is None:
        return None, excluded
    days, files, tick, note = inputs
    trades, summary = engine_1m.run_market(
        days, files, tick, tighten=tighten,
        allow_pre_activation=allow_pre_activation)
    for t in trades:
        t["market"] = key
    summary.update(market=key, status="OK", note=note, tick=tick)
    return trades, summary


def portfolio_replay(all_trades, start_capital=100_000.0, risk_pct=1.0):
    """Shared-account replay: 1% of current equity at each entry, P&L in R
    applied at exit. Trades are capital-independent in R, same principle
    as the daily project's simulate()."""
    events = []
    for t in all_trades:
        events.append((pd.Timestamp(t["entry_ts"]), "entry", t))
        events.append((pd.Timestamp(t["exit_ts"]), "exit", t))
    events.sort(key=lambda e: (e[0], 0 if e[1] == "exit" else 1))
    equity = start_capital
    curve, open_risk = [], {}
    peak, max_dd = equity, 0.0
    for ts, kind, t in events:
        tid = id(t)
        if kind == "entry":
            open_risk[tid] = equity * risk_pct / 100.0
        else:
            risk = open_risk.pop(tid, equity * risk_pct / 100.0)
            equity += t["net_r"] * risk
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
            # One point per SECOND, keeping the last equity: several exits
            # can share a timestamp and lightweight-charts rejects
            # duplicate times in setData (matrix page showed one dot,
            # Lode 2026-08-06).
            pt = (int(ts.timestamp()), round(equity, 2))
            if curve and curve[-1][0] == pt[0]:
                curve[-1] = pt
            else:
                curve.append(pt)
    return equity, max_dd, curve


def main():
    keys = sys.argv[1:] or (ELIGIBLE_FUTURES + ETFS + list(BINANCE))
    all_trades, rows, skipped = [], [], []
    for key in keys:
        try:
            trades, summary = run_market(key, **BASELINE)
        except Exception as exc:
            skipped.append({"market": key,
                            "reason": f"{type(exc).__name__}: {exc}"})
            print(f"{key}: ERROR {type(exc).__name__}: {exc}", flush=True)
            continue
        if trades is None:
            skipped.append(summary)
            print(f"{key}: EXCLUDED - {summary['reason']}", flush=True)
            continue
        all_trades.extend(trades)
        rows.append(summary)
        print(f"{key}: {summary['trades']} trades, wr "
              f"{summary['win_rate']}%, net {summary['net_r_total']}R "
              f"({summary['note']})", flush=True)

    all_trades.sort(key=lambda t: t["entry_ts"])
    final, max_dd, _curve = portfolio_replay(all_trades)
    total_r = round(sum(t["net_r"] for t in all_trades), 2)
    wins = sum(1 for t in all_trades if t["net_r"] > 0)
    wr = round(100 * wins / len(all_trades), 1) if all_trades else None
    print(f"\nPORTFOLIO: {len(all_trades)} trades across {len(rows)} "
          f"markets, wr {wr}%, net {total_r}R, final ${final:,.2f} "
          f"({(final / 100_000 - 1) * 100:+.2f}%), max drawdown "
          f"{max_dd:.2f}% at 1% risk")

    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(dict(
        strategy="quickfix1m1dc",
        design_doc="../data_center/docs/backtest_1m_design.md",
        params=dict(risk_pct=engine_1m.RISK_PCT,
                    entry_slip_ticks=engine_1m.ENTRY_SLIP_TICKS,
                    min_ladder=engine_1m.MIN_LADDER,
                    min_tested=engine_1m.MIN_REVERSALS,
                    stop="ladder (5th else 4th reversal +- 1 tick)",
                    **BASELINE,
                    activation_utc=ACTIVATION_UTC),
        portfolio=dict(final=round(final, 2), max_dd_pct=round(max_dd, 2),
                       trades=len(all_trades), win_rate=wr,
                       net_r=total_r),
        markets=rows, excluded=skipped, trades=all_trades),
        indent=2) + "\n", encoding="utf-8")
    import build_1m_report
    build_1m_report.build()
    print(f"wrote {OUT_JSON.name}")


if __name__ == "__main__":
    main()
