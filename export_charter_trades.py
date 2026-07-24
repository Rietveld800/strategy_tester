# export_charter_trades.py
#
# Hand-off from strategy_tester to charter: write one JSON of the quickfix trades, keyed
# by market, that charter overlays on each market's daily price chart. This is trade
# GEOMETRY only (dates + prices on the chart) -- the shared-account money management
# (position sizing, portfolio P&L) lives in quickfix_portfolio.py and is not needed here.
#
# Each trade carries the entry/exit the way it plots on price: entry at the first-reversal
# price on the entry bar, exit at the fill level (target / stop / opposite reversal) on the
# exit bar. An 'unknown_pl' trade is booked at the stop, so its exit price is the stop. An
# 'open_at_end' trade never exited, so exit_date/exit are null (charter draws it as open).
#
# Output: output/charter_trades.json  (charter reads it at build time; see charter README).

import json

import quickfix as qf
from quickfix_all import market_dirs

OUT = qf.HERE / "output" / "charter_trades.json"


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
                target=t["target_5r"], reason=reason,
                r=(None if t["r_multiple"] is None else round(t["r_multiple"], 3)),
                bars=t["bars_in_trade"])


def run():
    markets, total = {}, 0
    for d in market_dirs():
        bars = qf.load_bars(d)
        if not bars:
            continue
        tick, dp = qf.infer_tick(bars)
        res = qf.backtest(bars, tick, dp)
        if not res["trades"]:
            continue
        rows = [trade_for_chart(t) for t in res["trades"]]
        markets[d.name] = dict(tick=tick, price_decimals=dp, trades=rows)
        total += len(rows)
        print(f"{d.name:38} {len(rows):>3} trades")

    out = dict(
        meta=dict(strategy="quickfix", timeframe="daily", source="strategy_tester",
                  starting_capital=qf.STARTING_CAPITAL, risk_pct=qf.RISK_PCT,
                  n_markets=len(markets), n_trades=total),
        markets=markets,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\n{total} trades across {len(markets)} markets -> {OUT}")


if __name__ == "__main__":
    run()
