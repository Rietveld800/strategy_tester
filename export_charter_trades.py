# export_charter_trades.py
#
# Hand-off from strategy_tester to charter: write ONE JSON PER STRATEGY of that strategy's
# trades, keyed by market, which charter overlays on each market's daily price chart. This
# is trade GEOMETRY only (dates + prices on the chart) -- the shared-account money
# management (position sizing, portfolio P&L) lives in run_portfolio.py and is not needed
# here.
#
# Each trade carries the entry/exit the way it plots on price: entry at the first-reversal
# price on the entry bar, exit at the fill level (target / stop / opposite reversal) on the
# exit bar. An 'unknown_pl' trade is booked at the stop, so its exit price is the stop. An
# 'open_at_end' trade never exited, so exit_date/exit are null (charter draws it as open).
#
#   python export_charter_trades.py            # every registered strategy
#   python export_charter_trades.py slowfix    # just one
#
# Output: output/charter_trades_<strategy>.json -- one file per strategy, all in the same
# schema, so charter reads a fixed pattern instead of a new path shape per strategy
# (charter reads these at build time; see charter's README).

import json
import sys

import engine as eng
import strategies


def out_path(strategy):
    return eng.OUT_DIR / f"charter_trades_{strategy.key}.json"


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


def export(strategy, results):
    markets, total = {}, 0
    for m in results:
        trades = m["res"][strategy.key]["trades"]
        if not trades:
            continue
        markets[m["name"]] = dict(tick=m["tick"], price_decimals=m["dp"],
                                  trades=[trade_for_chart(t) for t in trades])
        total += len(trades)

    out = dict(
        meta=dict(strategy=strategy.key, title=strategy.title, rule4=strategy.rule4,
                  timeframe=eng.TIMEFRAME, source="strategy_tester",
                  starting_capital=eng.STARTING_CAPITAL, risk_pct=eng.RISK_PCT,
                  n_markets=len(markets), n_trades=total),
        markets=markets,
    )
    path = out_path(strategy)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{strategy.key}: {total} trades across {len(markets)} markets -> {path}")


def main(argv):
    picked = strategies.selected(argv)
    # Only the strategies' own caps: the hand-off is always at the documented default, and
    # the report's cap dial is display-side exploration that never touches these files.
    results = eng.run_markets(picked, caps=[s.cap for s in picked])
    print()
    for s in picked:
        export(s, results)


if __name__ == "__main__":
    main(sys.argv[1:])
