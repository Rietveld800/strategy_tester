# export_charter_trades.py
#
# Hand-off from strategy_tester to charter: write ONE JSON PER OVERLAY of that overlay's
# trades, keyed by market, which charter overlays on each market's daily price chart. This
# is trade GEOMETRY only (dates + prices on the chart) -- the shared-account money
# management (position sizing, portfolio P&L) lives in run_portfolio.py and is not needed
# here.
#
# WHAT GETS AN OVERLAY. Two lists, because Rule 4 comes in two shapes:
#
#   CHARTER_CAPS        a few settings of the CAP FAMILY. Not one file per strategy: a
#                       cap-family strategy is just a dial position, so the useful comparison
#                       on a price chart is a handful of caps (2026-07-27).
#   CHARTER_STRATEGIES  strategies whose Rule 4 is NOT a cap, exported by KEY because there
#                       is no cap number to name the file after. Quickfixpro today.
#
# This list is INDEPENDENT of the reports' cap grid and need not sit on it -- 2.25R is
# exported and is on no grid the reports draw. run_pipeline backtests whatever it names.
#
# Each trade carries the entry/exit the way it plots on price: entry at the first-reversal
# price on the entry bar, exit at the fill level (R cap / entry-bar target / stop / opposite
# reversal) on the exit bar. An 'unknown_pl' trade is booked at the stop, so its exit price
# is the stop. An 'open_at_end' trade never exited, so exit_date/exit are null (charter draws
# it as open).
#
#   python export_charter_trades.py
#
# Output: output/charter_trades_<key>.json -- one file per overlay, all in the same schema,
# so charter reads a fixed pattern instead of a new path shape per overlay (charter reads
# these at build time; see charter's README). Cap names are zero-padded so filename order IS
# cap order: charter sorts by filename and shows the boxes in that order.

import json
import sys

import engine as eng
import strategies

# The caps handed to charter. Deliberately a SHORT list, not the whole grid: every cap takes
# exactly the same setups (Rules 1-3 do not involve the cap), so their entry markers land on
# identical bars at identical prices -- 33 overlays would stack 33 triangles on one point and
# fan 33 exit lines from it. Charter also draws every overlay identically, and colour already
# means the outcome. Four caps is what stays readable.
#
# 1.9R FIRST, because it is quickfix's documented default: it has to be here, or the charts
# draw every cap except the one the strategy actually runs at. (It was added on 2026-07-28
# when the default moved there from 2.5R -- if the default moves again, move this with it.)
# 2R, 2.25R and 2.5R bracket it, the levered band the reports single out; 5R is a wider
# comparison the tight caps are worth reading against.
CHARTER_CAPS = [1.9, 2.0, 2.25, 2.5, 5.0]

# Strategies outside the cap family, exported whole. EMPTY since 2026-07-28: Quickfixpro was
# the only one and was retired (user). The list stays because the export handles a strategy
# and a cap through exactly the same code path, so re-adding one is a single key.
CHARTER_STRATEGIES = []


def charter_key(cap):
    """Zero-padded key/filename stem for a cap: 2.0 -> cap02_00, 2.25 -> cap02_25.

    Padded so that sorting the filenames sorts the caps -- charter globs and sorts, and
    'cap10' would otherwise land before 'cap2'.
    """
    whole = int(cap)
    frac = int(round((cap - whole) * 100))
    return f"cap{whole:02d}_{frac:02d}"


def hand_offs(caps=None, keys=None):
    """Every overlay this export owns, as (file key, title, rule 4 line, variant token).

    Caps first, then the non-cap strategies. Charter lists the boxes in FILENAME order, and
    'quickfixpro' sorts after every 'cap..' name, so the caps stay together in cap order and
    the strategies follow them.
    """
    caps = CHARTER_CAPS if caps is None else caps
    keys = CHARTER_STRATEGIES if keys is None else keys
    out = [(charter_key(c), strategies.cap_label(c), strategies.rule4_line(c),
            strategies.cap_token(c)) for c in caps]
    for k in keys:
        s = strategies.get(k)
        out.append((s.key, s.title, s.rule4, s.token))
    return out


def out_path(key):
    return eng.OUT_DIR / f"charter_trades_{key}.json"


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


def export(item, results):
    """One overlay's trades, keyed by market, in charter's schema.

    `item` is a `hand_offs()` tuple, so a cap and a whole strategy are written by exactly the
    same code -- charter's schema does not care which shape of Rule 4 produced the trades.
    """
    key, title, rule4, tok = item
    markets, total = {}, 0
    for m in results:
        trades = m["var"][tok]["trades"]
        if not trades:
            continue
        markets[m["name"]] = dict(tick=m["tick"], price_decimals=m["dp"],
                                  trades=[trade_for_chart(t) for t in trades])
        total += len(trades)

    out = dict(
        meta=dict(strategy=key, title=title, cap=tok, rule4=rule4,
                  timeframe=eng.TIMEFRAME, source="strategy_tester",
                  starting_capital=eng.STARTING_CAPITAL, risk_pct=eng.RISK_PCT,
                  n_markets=len(markets), n_trades=total),
        markets=markets,
    )
    path = out_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{title:>12}: {total} trades across {len(markets)} markets -> {path.name}")


def prune(items):
    """Delete hand-off files this export no longer owns.

    Charter GLOBS charter_trades_*.json, so a file left behind from an earlier set keeps
    being drawn -- which is how slowfix would go on appearing on the charts after being
    dropped here. Only files matching this exact pattern are touched, and each one is named
    as it goes.
    """
    keep = {out_path(i[0]).name for i in items}
    for p in sorted(eng.OUT_DIR.glob("charter_trades_*.json")):
        if p.name not in keep:
            p.unlink()
            print(f"removed stale hand-off: {p.name}")


def main(argv):
    # Arguments select the CAPS only; the non-cap strategies are always handed over, since
    # naming one on the command line would mean guessing whether it is a cap or a key.
    caps = [float(a) for a in argv] if argv else list(CHARTER_CAPS)
    items = hand_offs(caps=caps)
    # Only the caps being exported, not the whole dial grid: run_markets adds each registered
    # strategy's own Rule 4 on top, which is what brings Quickfixpro's run along.
    results = eng.run_markets(strategies.REGISTRY, caps=caps)
    print()
    for item in items:
        export(item, results)
    prune(items)


if __name__ == "__main__":
    main(sys.argv[1:])
