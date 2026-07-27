# export_charter_trades.py
#
# Hand-off from strategy_tester to charter: write ONE JSON PER PROFIT CAP of that cap's
# trades, keyed by market, which charter overlays on each market's daily price chart. This
# is trade GEOMETRY only (dates + prices on the chart) -- the shared-account money
# management (position sizing, portfolio P&L) lives in run_portfolio.py and is not needed
# here.
#
# BY CAP, NOT BY STRATEGY (2026-07-27). The overlay used to be one file per registered
# strategy, quickfix and slowfix. Now that Rule 4 is one family with the cap as its only
# parameter, the useful thing to compare on a price chart is a few CAPS -- see
# CHARTER_CAPS below. Slowfix is no longer exported at all: it is the same family at no
# cap, its trades are the least interesting on the chart, and the reports already carry it.
# (Slowfix remains a full strategy everywhere else -- the workbooks and the HTML reports
# are unchanged. This is only about what charter draws.)
#
# Each trade carries the entry/exit the way it plots on price: entry at the first-reversal
# price on the entry bar, exit at the fill level (R cap / stop / opposite reversal) on the
# exit bar. An 'unknown_pl' trade is booked at the stop, so its exit price is the stop. An
# 'open_at_end' trade never exited, so exit_date/exit are null (charter draws it as open).
#
#   python export_charter_trades.py
#
# Output: output/charter_trades_cap<NN>_<NN>.json -- one file per cap, all in the same
# schema, so charter reads a fixed pattern instead of a new path shape per cap (charter
# reads these at build time; see charter's README). The names are zero-padded so filename
# order IS cap order: charter sorts by filename and shows the boxes in that order.

import json
import sys

import engine as eng
import strategies

# The caps handed to charter. Deliberately a SHORT list, not the whole grid: every cap takes
# exactly the same setups (Rules 1-3 do not involve the cap), so their entry markers land on
# identical bars at identical prices -- 33 overlays would stack 33 triangles on one point and
# fan 33 exit lines from it. Charter also has only four line styles, and colour already means
# the outcome. Three caps is what stays readable.
#
# 2R, 2.25R and 2.5R are the levered sweet spot the reports single out -- 2.5R is quickfix's
# documented default, so it has to be here: the charts would otherwise draw every cap except
# the one the strategy actually runs at. 5R is what that default used to be, kept as the
# comparison the tight caps are worth reading against.
CHARTER_CAPS = [2.0, 2.25, 2.5, 5.0]


def charter_key(cap):
    """Zero-padded key/filename stem for a cap: 2.0 -> cap02_00, 2.25 -> cap02_25.

    Padded so that sorting the filenames sorts the caps -- charter globs and sorts, and
    'cap10' would otherwise land before 'cap2'.
    """
    whole = int(cap)
    frac = int(round((cap - whole) * 100))
    return f"cap{whole:02d}_{frac:02d}"


def out_path(cap):
    return eng.OUT_DIR / f"charter_trades_{charter_key(cap)}.json"


def trade_for_chart(t):
    reason = t["exit_reason"]
    if reason == "open_at_end":
        exit_date, exit_price = None, None
    elif reason == "unknown_pl":
        exit_date, exit_price = t["exit_date"], t["stop"]     # booked at the stop
    else:
        exit_date, exit_price = t["exit_date"], t["exit_price"]
    return dict(side=t["side"], entry_date=t["entry_date"], entry=t["entry"],
                exit_date=exit_date, exit=exit_price, stop=t["stop"],
                target=t["target"], reason=reason,
                r=(None if t["r_multiple"] is None else round(t["r_multiple"], 3)),
                bars=t["bars_in_trade"])


def export(cap, results):
    """One cap's trades, keyed by market, in charter's schema."""
    tok = strategies.cap_token(cap)
    markets, total = {}, 0
    for m in results:
        trades = m["var"][tok]["trades"]
        if not trades:
            continue
        markets[m["name"]] = dict(tick=m["tick"], price_decimals=m["dp"],
                                  trades=[trade_for_chart(t) for t in trades])
        total += len(trades)

    out = dict(
        meta=dict(strategy=charter_key(cap), title=strategies.cap_label(cap),
                  cap=tok, rule4=strategies.rule4_line(cap),
                  timeframe=eng.TIMEFRAME, source="strategy_tester",
                  starting_capital=eng.STARTING_CAPITAL, risk_pct=eng.RISK_PCT,
                  n_markets=len(markets), n_trades=total),
        markets=markets,
    )
    path = out_path(cap)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{strategies.cap_label(cap):>7}: {total} trades across {len(markets)} markets "
          f"-> {path.name}")


def prune(caps):
    """Delete hand-off files this export no longer owns.

    Charter GLOBS charter_trades_*.json, so a file left behind from an earlier set keeps
    being drawn -- which is how slowfix would go on appearing on the charts after being
    dropped here. Only files matching this exact pattern are touched, and each one is named
    as it goes.
    """
    keep = {out_path(c).name for c in caps}
    for p in sorted(eng.OUT_DIR.glob("charter_trades_*.json")):
        if p.name not in keep:
            p.unlink()
            print(f"removed stale hand-off: {p.name}")


def main(argv):
    caps = [float(a) for a in argv] if argv else list(CHARTER_CAPS)
    results = eng.run_markets(strategies.REGISTRY, caps=caps)
    print()
    for cap in caps:
        export(cap, results)
    prune(caps)


if __name__ == "__main__":
    main(sys.argv[1:])
