# engine.py
#
# The backtest engine shared by EVERY strategy in this project. The strategies themselves
# live in strategies.py; they differ only in Rule 4 (which profit target is in force), so
# everything else -- bar loading, signal detection, the stop, the exit resolution and the
# per-market money model -- lives here and is written once.
#
# The Socrates "time and price meet" method (Erwin Pletsch) is intraday, but we only have
# DAILY array files (one OHLC bar + one set of reversal levels per day). So every intraday
# condition is inferred from the daily bar. That approximation is accepted for now; it will
# be replaced with real intraday prices (IBKR API) later.
#
# SCOPE: this module READS the array (meta) xlsx files produced by hyperliquid_bot (via
# charter's battle-tested parser) and WRITES trade ledgers + equity curves as JSON for
# charter to render. It never scrapes data and never renders charts.
#
# --- Short setup (the long setup is the exact mirror) -----------------------------
# Reference for the day = the PREVIOUS bar's close. Price is assumed to rise from the
# previous close, testing bullish reversals, then fall back.
#
#   Rule 1 (signal): at least 3 bullish reversals lie in (prev_close, high] -- price
#           tested them on the way up. The FIRST reversal is the lowest of these
#           (first one hit rising from prev_close); the SECOND is the next lowest.
#   Rule 2 (clean setup): refuse if the bar's open is at or above the SECOND reversal.
#           An open below the first, or between first and second, is acceptable.
#   Entry trigger: the bar CLOSES below the first reversal. Entry fills at the first
#           reversal price. (Close at or above the first reversal -> no trade.)
#   Stop: one tick above the entry bar's high. Risk = stop - entry. Sizing makes that
#           risk exactly 1% of current equity, so 1R = 1% (pure percentage model, no
#           contracts). A stop-out is -1%.
#   Rule 3 (min reward): the nearest bearish reversal below entry must be at least
#           3.5R below entry, else refuse.
#   Rule 4 (target): STRATEGY-SPECIFIC -- the one rule that differs between strategies.
#           Supplied by the strategy's `target` policy (see strategies.py) and recomputed
#           on every bar from the levels known at that bar's start, so a newly appearing
#           nearer reversal moves the target in and an elected one falls away. Only
#           OPPOSITE-side reversals ever close a trade early (bearish for a short,
#           bullish for a long) -- never a same-side one.
#
# One position per market at a time; a new signal while in a trade is ignored. After each
# close, equity is recomputed and the next trade's 1% is taken on the new equity.
#
# The LOOK-AHEAD RULE (critical). The array file dated D already reflects day D's own
# intraday extremes and re-draws any levels D elected. So a bar is ALWAYS evaluated against
# the levels known at its start = the PREVIOUS file's levels, and the reference close comes
# from that same previous file. This holds for entry detection and for target recomputation
# alike.
#
# Path-ambiguity rules on a daily bar (can't see intraday order):
#   - stop and target both inside a later bar's range -> booked as 'unknown_pl' at -1R
#     (the benefit of the doubt goes to the loss).
#   - a gap past the stop still fills at the stop price (user's choice).
#   - the entry bar NEVER exits: management starts on the bar AFTER entry. The entry
#     bar's high/low are already spent by the time its close confirms the entry, and
#     the stop sits one tick beyond that bar's own extreme, so neither side can trigger
#     there.

import json
import sys
from pathlib import Path

# charter owns the array parsers; import them rather than rewrite (README contract).
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / ".." / "charter" / "scripts"))
import charting_core as cc  # noqa: E402

# --- simulation inputs ------------------------------------------------------------
TIMEFRAME = "daily"
ARRAY_ROOT = HERE / ".." / "hyperliquid_bot" / "data" / "array"
OUT_DIR = HERE / "output"
REFERENCE_MARKET = "Gold_Futures_COMEX"   # the market single-market runs use

# No date window: it is data-driven. Entries start at the first bar whose PREVIOUS
# file carries enough reversals, and run to the last available file.
STARTING_CAPITAL = 100_000.0
RISK_PCT = 1.0              # percent of equity risked per trade (1R)
FEES = 0.0                  # per-trade cost, in equity percent; 0 for now

MIN_REVERSALS = 3          # Rule 1: at least this many tested reversals
MIN_RR = 3.5               # Rule 3: minimum reward-to-risk to take the trade
TARGET_RR = 5.0            # Rule 4 reference distance (quickfix's cap; see strategies.py)


# --- bar loading ------------------------------------------------------------------
class Bar:
    __slots__ = ("date", "open", "high", "low", "close", "bull", "bear")

    def __init__(self, date, ohlc, bull, bear):
        self.date = date
        self.open = ohlc["open"]
        self.high = ohlc["high"]
        self.low = ohlc["low"]
        self.close = ohlc["close"]
        self.bull = bull   # sorted list of bullish reversal levels (major + minor)
        self.bear = bear   # sorted list of bearish reversal levels (major + minor)


def load_bars(market_dir):
    """All valid daily bars for a market directory, oldest -> newest.

    Bars whose OVERVIEW block has no OHLC are skipped. Reversal sets may be empty on the
    early bars of a market (older files carry no reversal block at all -- verified in
    charter's ROADMAP, 2026-07-19): those simply produce no signals, so the backtest
    naturally starts once a market's reversals are first reported.
    """
    paths = sorted(Path(market_dir).glob(f"*/{TIMEFRAME}/*_array.xlsx"))
    bars = []
    for p in paths:
        try:
            date, ohlc, rev = cc.parse_array(p)
        except Exception:
            continue
        if ohlc is None:
            continue
        bull = sorted(rev["bull_major"] | rev["bull_minor"])
        bear = sorted(rev["bear_major"] | rev["bear_minor"])
        bars.append(Bar(date, ohlc, bull, bear))
    bars.sort(key=lambda b: b.date)
    return bars


def infer_tick(bars):
    """Smallest price step, from the number of decimals in the close prices.

    Same inference charter uses for its crosshair (gold -> 1 decimal -> 0.1).
    """
    dp = 0
    for b in bars:
        s = f"{round(b.close, 6):.6f}".rstrip("0")
        if "." in s:
            dp = max(dp, len(s.rsplit(".", 1)[1]))
    return 10.0 ** (-dp), dp


def market_dirs():
    """Every market directory that has daily array files (skip #Charts, _vps2, etc.)."""
    out = []
    for d in sorted(ARRAY_ROOT.iterdir()):
        if not d.is_dir() or d.name.startswith(("#", "_")):
            continue
        if any(d.glob(f"*/{TIMEFRAME}/*_array.xlsx")):
            out.append(d)
    return out


# --- signal detection -------------------------------------------------------------
def detect_short(bar, prev_close, tick, bull, bear):
    """Return an entry dict for a short signal on `bar`, or None.

    `bull`/`bear` are the reversal levels KNOWN AT THE START OF THE BAR (the previous
    file's set), never `bar`'s own file: that file already reflects this bar's intraday
    extremes and re-draws elected levels, which is look-ahead.

    tested bullish reversals = levels in (prev_close, high]; first = lowest, second
    = next. Rule 2: open < second. Trigger: close < first. Rule 3: nearest bearish
    reversal below entry >= 3.5R below entry.

    Rules 1-3 are strategy-independent, so every strategy takes exactly the same trades;
    only Rule 4 (where they are closed) differs.
    """
    tested = [lvl for lvl in bull if prev_close < lvl <= bar.high]
    if len(tested) < MIN_REVERSALS:
        return None
    first, second = tested[0], tested[1]
    if bar.open >= second:                 # Rule 2
        return None
    if bar.close >= first:                 # entry trigger
        return None
    entry = first
    stop = bar.high + tick
    risk = stop - entry
    if risk <= 0:
        return None
    below = [b for b in bear if b < entry]
    if not below:                          # Rule 3 needs a bearish reversal below
        return None
    nearest = max(below)
    if (entry - nearest) < MIN_RR * risk:  # Rule 3
        return None
    return dict(side="short", entry=entry, stop=stop, risk=risk,
                target_5r=entry - TARGET_RR * risk)


def detect_long(bar, prev_close, tick, bull, bear):
    """Mirror of detect_short. tested bearish reversals = levels in [low, prev_close);
    first = highest, second = next; Rule 2: open > second; trigger: close > first;
    Rule 3: nearest bullish reversal above entry >= 3.5R above entry.

    `bull`/`bear` are the previous file's levels (known at the bar's start), as in
    detect_short.
    """
    tested = sorted((lvl for lvl in bear if bar.low <= lvl < prev_close),
                    reverse=True)
    if len(tested) < MIN_REVERSALS:
        return None
    first, second = tested[0], tested[1]
    if bar.open <= second:                 # Rule 2
        return None
    if bar.close <= first:                 # entry trigger
        return None
    entry = first
    stop = bar.low - tick
    risk = entry - stop
    if risk <= 0:
        return None
    above = [b for b in bull if b > entry]
    if not above:                          # Rule 3 needs a bullish reversal above
        return None
    nearest = min(above)
    if (nearest - entry) < MIN_RR * risk:  # Rule 3
        return None
    return dict(side="long", entry=entry, stop=stop, risk=risk,
                target_5r=entry + TARGET_RR * risk)


# --- trade management -------------------------------------------------------------
def check_exit(strategy, pos, bar, bull, bear):
    """Does `pos` close on `bar`? Returns (exit_price, reason) or None.

    Only ever called on bars AFTER the entry bar: the profit target can never be reached
    on the entry bar itself (the entry is confirmed on that bar's close, so its high/low
    are already spent -- and by construction the stop is one tick beyond that bar's own
    extreme). Management therefore starts the day after entry.

    `bull`/`bear` are the previous file's levels (known at the bar's start). The target in
    force comes from the STRATEGY (Rule 4) and is recomputed here on every bar. It may be
    None -- slowfix has no target while no opposite reversal exists beyond entry -- in
    which case only the stop can close the trade. On a later bar:

      - only the target in range   -> clean win at the target;
      - only the stop in range      -> clean stop (-1%);
      - BOTH in range on one bar     -> the intraday order is unknowable, so we give the
        benefit of the doubt to a loss: 'unknown_pl', exit_price None, booked -1%.
    """
    target, treason = strategy.target(pos, bull, bear)
    if pos["side"] == "short":
        stop_in = bar.high >= pos["stop"]
        target_in = target is not None and bar.low <= target
        treason_name = "target_5r" if treason == "target_5r" else "bearish_reversal"
    else:
        stop_in = bar.low <= pos["stop"]
        target_in = target is not None and bar.high >= target
        treason_name = "target_5r" if treason == "target_5r" else "bullish_reversal"

    if stop_in and target_in:
        return None, "unknown_pl"
    if stop_in:
        return pos["stop"], "stop"
    if target_in:
        return target, treason_name
    return None


def r_multiple(pos, exit_price):
    if pos["side"] == "short":
        return (pos["entry"] - exit_price) / pos["risk"]
    return (exit_price - pos["entry"]) / pos["risk"]


# --- backtest loop ----------------------------------------------------------------
def backtest(bars, tick, dp, strategy):
    """Run `strategy` over `bars` (oldest -> newest) with fresh capital.

    Data-driven window: entries fire from the first bar whose PREVIOUS file carries
    enough reversals, and run to the last bar. Returns dict(trades, equity_curve,
    final_equity, first_trade_date). One position at a time; the entry bar never exits
    (management starts the next bar); an open position at the end is reported unrealized.
    """
    equity = STARTING_CAPITAL
    trades, equity_curve = [], []
    pos, tid = None, 0

    for i, bar in enumerate(bars):
        # levels + reference close KNOWN AT THE START OF THIS BAR = the previous file
        prev = bars[i - 1] if i > 0 else None
        sig_bull = prev.bull if prev else []
        sig_bear = prev.bear if prev else []

        # 1) manage an open position on this bar (never enter and manage same bar)
        if pos is not None:
            hit = check_exit(strategy, pos, bar, sig_bull, sig_bear)
            if hit is not None:
                exit_price, reason = hit
                equity = _close(pos, bar, i, exit_price, reason, equity,
                                trades, equity_curve, dp)
                pos = None
            continue

        # 2) look for a new entry only when flat (needs a previous file)
        if prev is None:
            continue
        entry = (detect_short(bar, prev.close, tick, sig_bull, sig_bear)
                 or detect_long(bar, prev.close, tick, sig_bull, sig_bear))
        if entry is None:
            continue

        tid += 1
        risk_dollars = equity * RISK_PCT / 100.0
        pos = dict(id=tid, entry_index=i, entry_date=bar.date,
                   equity_before=equity, risk_dollars=risk_dollars, **entry)
        # the Rule 4 level in force at entry, recorded for the ledger (it can move later)
        pos["target"] = strategy.target(pos, sig_bull, sig_bear)[0]
        # the entry bar never exits: management starts on the next bar (loop continues)

    if pos is not None:                        # still open at the end -> reported, unrealized
        trades.append(dict(id=pos["id"], side=pos["side"],
                           entry_date=str(pos["entry_date"].date()),
                           exit_date=None, bars_in_trade=None,
                           entry=_r(pos["entry"], dp), stop=_r(pos["stop"], dp),
                           risk_per_unit=_r(pos["risk"], dp),
                           target=_r(pos["target"], dp) if pos["target"] is not None else None,
                           exit_price=None, exit_reason="open_at_end",
                           r_multiple=None, pnl_pct=None,
                           equity_before=round(pos["equity_before"], 2),
                           equity_after=round(pos["equity_before"], 2)))

    first_trade = trades[0]["entry_date"] if trades else None
    return dict(trades=trades, equity_curve=equity_curve, final_equity=equity,
                first_trade_date=first_trade)


def _close(pos, bar, i, exit_price, reason, equity, trades, equity_curve, dp):
    """Realize a closed trade, append it, update and record equity, return new equity.

    An 'unknown_pl' exit has no fill price: the path was ambiguous, so it is booked at
    -1R (-1%) with exit_price null -- the benefit of the doubt goes to a loss.
    """
    if reason == "unknown_pl":
        r, exit_out = -1.0, None
    else:
        r, exit_out = r_multiple(pos, exit_price), _r(exit_price, dp)
    pnl_pct = r * RISK_PCT - FEES
    equity_after = equity * (1 + pnl_pct / 100.0)
    trades.append(dict(
        id=pos["id"], side=pos["side"],
        entry_date=str(pos["entry_date"].date()), exit_date=str(bar.date.date()),
        bars_in_trade=i - pos["entry_index"],
        entry=_r(pos["entry"], dp), stop=_r(pos["stop"], dp),
        risk_per_unit=_r(pos["risk"], dp),
        target=_r(pos["target"], dp) if pos["target"] is not None else None,
        exit_price=exit_out, exit_reason=reason,
        r_multiple=round(r, 4), pnl_pct=round(pnl_pct, 4),
        equity_before=round(equity, 2), equity_after=round(equity_after, 2)))
    equity_curve.append(dict(date=str(bar.date.date()),
                             equity=round(equity_after, 2)))
    return equity_after


def _r(x, dp):
    return round(x, dp)


# --- all markets, all strategies, one pass ----------------------------------------
def run_markets(strategies, progress=True):
    """Backtest EVERY market for EVERY strategy given, in one pass.

    Reading and parsing the array xlsx files is by far the slow part, so each market's
    bars are parsed ONCE and reused for all strategies -- which is also why the runners
    take a precomputed result list: a full refresh loads the archive once, not once per
    output file.

    Returns a list of dicts: name, bars, tick, dp, res={strategy key -> backtest result}.
    """
    out = []
    for d in market_dirs():
        bars = load_bars(d)
        if not bars:
            continue
        tick, dp = infer_tick(bars)
        res = {s.key: backtest(bars, tick, dp, s) for s in strategies}
        out.append(dict(name=d.name, bars=bars, tick=tick, dp=dp, res=res))
        if progress:
            parts = []
            for s in strategies:
                r = res[s.key]
                closed = [t for t in r["trades"] if t["exit_reason"] != "open_at_end"]
                parts.append(f"{s.key} {len(closed):>3}tr "
                             f"{(r['final_equity'] / STARTING_CAPITAL - 1) * 100:+7.2f}%")
            print(f"{d.name:38} bars={len(bars):>4}  " + "  |  ".join(parts))
    return out


# --- single-market run (the reference ledger) -------------------------------------
def run_single(strategy, market=REFERENCE_MARKET):
    """One market, fresh capital: write the JSON ledger and print a summary."""
    bars = load_bars(ARRAY_ROOT / market)
    tick, dp = infer_tick(bars)
    res = backtest(bars, tick, dp, strategy)
    result = dict(
        meta=dict(market=market, timeframe=TIMEFRAME, strategy=strategy.key,
                  start=str(bars[0].date.date()), end=str(bars[-1].date.date()),
                  starting_capital=STARTING_CAPITAL, risk_pct=RISK_PCT,
                  tick=tick, fees=FEES, min_reversals=MIN_REVERSALS,
                  min_rr=MIN_RR, target_rr=TARGET_RR, rule4=strategy.rule4),
        trades=res["trades"],
        equity_curve=[dict(date=str(bars[0].date.date()),
                           equity=STARTING_CAPITAL)] + res["equity_curve"],
    )
    out_path = OUT_DIR / f"{strategy.key}_{_short(market)}_{TIMEFRAME}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _summary(strategy, res["trades"], res["final_equity"], out_path)
    return result


def _short(market):
    """First word of a market folder name, lowercased -- Gold_Futures_COMEX -> gold."""
    return market.split("_")[0].lower()


def _summary(strategy, trades, equity, out_path):
    closed = [t for t in trades if t["exit_reason"] != "open_at_end"]
    wins = [t for t in closed if t["pnl_pct"] > 0]
    print(f"{strategy.key}: {len(closed)} closed"
          + (" (+1 open at end)" if len(trades) > len(closed) else ""))
    if closed:
        wr = 100 * len(wins) / len(closed)
        print(f"wins: {len(wins)}  win rate: {wr:.1f}%")
        for t in closed:
            print(f"  #{t['id']:>2} {t['side']:<5} {t['entry_date']} -> "
                  f"{t['exit_date']} ({t['bars_in_trade']}d) "
                  f"{t['exit_reason']:<16} R={t['r_multiple']:+.2f} "
                  f"pnl={t['pnl_pct']:+.2f}%")
    print(f"final equity: ${equity:,.2f}  "
          f"({(equity / STARTING_CAPITAL - 1) * 100:+.2f}%)")
    print(f"written: {out_path}")


if __name__ == "__main__":
    import strategies

    for _s in strategies.selected(sys.argv[1:]):
        run_single(_s)
        print()
