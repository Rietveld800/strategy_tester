# export_charter_trades_1m.py
#
# Hand-off from strategy_tester to charter for the ONE published strategy,
# quickfix1m1dc: its trades keyed by market, which charter overlays on each
# market's DAILY price chart behind the rail's T button.
#
#   python export_charter_trades_1m.py
#
# Output: output/charter_trades_quickfix1m1dc.json
#
# WHY THIS FILE EXISTS BESIDE export_charter_trades.py, rather than inside it.
# That one is the DAILY product's hand-off: it walks strategies.REGISTRY and the
# cap grid, and every trade it writes comes out of engine.py. quickfix1m1dc runs
# on engine_1m over 1-minute bars from ../data_center and is not a Rule 4 on that
# engine at all, so it has no cap, no variant token and nothing to say to
# `hand_offs()`. Since the daily registry was emptied on 2026-08-12 the other
# exporter owns nothing and refuses to run; this one owns the directory.
#
# THE SCHEMA IS CHARTER'S EXISTING ONE, unchanged. That is the point: charter
# globs charter_trades_*.json, reads meta + markets and draws each file as its
# own overlay, so a 1-minute strategy needs no new code over there beyond a
# colour for its exit reason. What it hands over is TRADE GEOMETRY ONLY -- the
# dates and prices the trade plots at -- never the money management, which lives
# in run_1m.portfolio_replay and is a different account per report.
#
# INTRADAY TRADES ON A DAILY PANE. A quickfix1m1dc trade enters at a minute
# inside the session and exits at the next day's settlement (or at its stop,
# which is live throughout). Charter's daily overlay plots by DATE, so the entry
# marker lands on the entry session's bar and the exit marker on the exit
# session's bar, with the line between them. The minute is lost, deliberately:
# the daily pane cannot show it and charter's own 1-minute trade study
# (site/1m/trades.html) is where the intraday path is read. A stop that fires in
# the same session it entered therefore draws a VERTICAL line on one bar, the
# same way quickfixclose0 used to.
#
# Markets are named by their ARRAY FOLDER (Gold_Futures_COMEX), not by the
# engine's contract key (GC), because that folder name is charter's own key for
# a market. run_1m.market_info() is the single mapping for it and covers the
# obsolete markets too.

import json
import sys
from pathlib import Path

import run_1m

HERE = Path(__file__).resolve().parent
IN_JSON = HERE / "output" / "quickfix1m1dc_all.json"
OUT_DIR = HERE / "output"
KEY = "quickfix1m1dc"
TITLE = "Quickfix1m1dc"

# The one-liner charter labels the overlay with, in the T box and its tooltip.
# It is the STRATEGY, not one dial of it: the dials (the geometry band, the
# session lockout, the stop anchor) are stated on the report page, which is
# where a reader who wants them is going anyway.
RULE4 = ("entry on the first reversal print intraday, exit at the next day's "
         "settlement or at the ladder stop")


def out_path(key=KEY):
    return OUT_DIR / f"charter_trades_{key}.json"


def price_decimals(tick):
    """Decimals to print a price at, from the market's tick size.

    Charter carries this per market so a hover reads 4113.7 on gold and
    0.006183 on the yen. Derived rather than stored because the 1m blotter
    already carries the tick and two sources for one number drift.
    """
    if not tick or tick <= 0:
        return 2
    dp = 0
    while dp < 10 and round(tick * (10 ** dp), 6) != int(round(tick * (10 ** dp))):
        dp += 1
    return dp


def session_date(t, which):
    """The SESSION a trade's entry or exit belongs to, as 'YYYY-MM-DD'.

    NOT the date half of the timestamp, and the difference is not academic: a
    futures session opens the previous evening UTC, so on the current window
    4 of 62 trades carry an `entry_ts` dated a day before their `entry_date`
    (GC's 2026-03-02 session starts 2026-03-01 23:00 UTC). Charter plots these
    on DAILY bars, so taking the timestamp's date puts those trades on the
    wrong bar -- which is what the first version of this file did.

    The engine records both dates because only it knows the session; the
    timestamp fallback is for a blotter written before `exit_date` existed
    (2026-08-12) and says so rather than being quietly wrong.
    """
    key = f"{which}_date"
    if t.get(key):
        return str(t[key])
    ts = t.get(f"{which}_ts")
    if not ts:
        return None
    print(f"  {which}_date missing, falling back to the timestamp's date "
          f"(rerun run_1m.py to get the session date)")
    return str(ts)[:10]


def trade_for_chart(t):
    """One blotter row in charter's schema.

    `target` is None and stays None: this strategy watches no profit level, it
    holds to the next settlement, so there is no target price the market could
    have filled. `r` is the NET R the ledger booked, which is what colours a
    scheduled exit (see charter's TRADE_BY_R) -- the daily hand-off passed gross
    there, but this engine's costs are already per trade in R and the net number
    is the one the report and the page agree on.
    """
    return dict(side=t["side"],
                entry_date=session_date(t, "entry"), entry=t["entry"],
                exit_date=session_date(t, "exit"), exit=t.get("exit"),
                stop=t["stop"], target=None, reason=t.get("reason"),
                r=(None if t.get("net_r") is None else round(t["net_r"], 3)),
                bars=None)


def build(data=None):
    """The hand-off payload, from the published blotter alone (no backtest)."""
    if data is None:
        if not IN_JSON.exists():
            raise SystemExit(f"missing {IN_JSON} -- run: python run_1m.py")
        data = json.loads(IN_JSON.read_text(encoding="utf-8"))
    ticks = {r["market"]: r.get("tick") for r in data.get("markets", [])}

    markets, total = {}, 0
    for t in data["trades"]:
        key = t["market"]
        name = run_1m.market_info(key).get("array_dir")
        if not name:
            # A market with no array folder cannot be drawn: charter keys its
            # overlays by folder. Say so rather than dropping it silently.
            print(f"  skipped {key}: no array folder in the market mapping")
            continue
        m = markets.setdefault(name, dict(tick=ticks.get(key),
                                          price_decimals=price_decimals(ticks.get(key)),
                                          trades=[]))
        m["trades"].append(trade_for_chart(t))
        total += 1

    params = data.get("params", {})
    return dict(
        meta=dict(strategy=KEY, title=TITLE, cap=None, rule4=RULE4,
                  timeframe="1min -> plotted on daily", source="strategy_tester",
                  starting_capital=100_000.0,
                  risk_pct=params.get("risk_pct"),
                  n_markets=len(markets), n_trades=total),
        markets=markets,
    )


def prune(keep):
    """Delete every charter_trades_*.json this project no longer owns.

    Charter GLOBS the directory, so a hand-off left behind from a retired
    strategy goes on being drawn -- that is how the five daily strategies and
    the five cap overlays would still be in the T box after being retired. This
    exporter is the only owner now, so anything that is not `keep` goes.
    """
    for p in sorted(OUT_DIR.glob("charter_trades_*.json")):
        if p.name != keep:
            p.unlink()
            print(f"removed stale hand-off: {p.name}")


def write(data=None):
    out = build(data)
    path = out_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{TITLE}: {out['meta']['n_trades']} trades across "
          f"{out['meta']['n_markets']} markets -> {path.name}")
    prune(path.name)
    return out


if __name__ == "__main__":
    sys.exit(0 if write() else 0)
