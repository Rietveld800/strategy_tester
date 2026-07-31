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
#           risk exactly RISK_PCT of current equity, so 1R = RISK_PCT (pure percentage
#           model, no contracts). A stop-out is -1R.
#   Rule 3 (min reward): the nearest bearish reversal below entry must be at least
#           3.5R below entry, else refuse.
#   Rule 4 (exit): STRATEGY-SPECIFIC -- the one rule that differs between strategies, and it
#           comes in two mechanical forms (see strategies.py):
#             a target POLICY (the cap family, Quickfixwick's entry-bar wick), recomputed on
#               every bar from the levels known at that bar's start, so a newly appearing
#               nearer reversal moves a reversal target in and an elected one falls away.
#               Only OPPOSITE-side reversals ever close a trade early (bearish for a short,
#               bullish for a long) -- never a same-side one. Resolved by `check_exit`.
#             a BAR EXIT (the five "out at bar k's open / close" strategies), which names a
#               price off the bar itself instead of watching a level. There is no TARGET for
#               `check_exit` to resolve, so the named price is taken as given -- and it is the
#               ONLY thing that may close a trade on its own entry bar. The STOP still runs
#               underneath it on every bar the trade is held through, since the stop is not
#               Rule 4: an open exit is taken before the stop (nothing trades ahead of a
#               bar's first price), a close exit after it (a stop triggers intraday, a
#               market-on-close fires at the bell).
#           The cap is a DIAL, not a constant: `run_markets` backtests the whole
#           strategies.CAP_CHOICES grid in one pass so the reports can move it, plus each
#           registered strategy's own Rule 4 for the ones that are not caps at all.
#
# One position per market at a time; a new signal while in a trade is ignored. After each
# close, equity is recomputed and the next trade's risk is taken on the new equity.
#
# The LOOK-AHEAD RULE (critical). The array file dated D already reflects day D's own
# intraday extremes and re-draws any levels D elected. So a bar is ALWAYS evaluated against
# the levels known at its start = the PREVIOUS file's levels, and the reference close comes
# from that same previous file. This holds for entry detection and for target recomputation
# alike.
#
# Path-ambiguity rules on a daily bar (can't see intraday order):
#   - a bar that GAPS through the stop or the target fills at that bar's OPEN (user,
#     2026-07-27). The open is the day's first price, so a level the bar jumped over was
#     taken at the open and nothing else can have been hit before it -- the gap is the one
#     case where the daily bar does tell us the order. On a stop that is worse than the stop
#     price (a gapped stop can lose well over 1R); on a target it is better. Both are the
#     real fill.
#     A gap means price JUMPED OVER the level, so it is measured against the PREVIOUS CLOSE,
#     not against the open alone: a short gaps its target when `open <= target < prev_close`.
#     Testing the open by itself was a bug (fixed 2026-07-27, same day): a short's entry bar
#     closes below its entry by definition, so any target above that close was already in
#     the money before management started, every next open counted as a "gap", and the trade
#     was paid out at that open instead of at its target. An already-through target is NOT a
#     gap -- a resting limit there fills at the limit.
#     The stop needs no such guard: it sits one tick beyond the entry bar's own extreme, so
#     no close can be through it while the trade is still open.
#   - otherwise, stop and target both inside a later bar's range -> booked as 'unknown_pl'
#     at -1R (the benefit of the doubt goes to the loss). With gaps resolved at the open,
#     this is now only the genuinely unknowable case: the bar opened BETWEEN the two and
#     then traded through both.
#   - the entry bar never exits ON A LEVEL: management starts on the bar AFTER entry. The
#     entry bar's high/low are already spent by the time its close confirms the entry, and
#     the stop sits one tick beyond that bar's own extreme, so neither side can trigger
#     there. A BAR EXIT is the one exception, and only because it watches no level:
#     Quickfixclose0 is marked out at that same bar's close, which is a price the bar has
#     already printed rather than one we are guessing the path to.
#   - a bar exit that fires LATER than bar 1 is held through whole bars it did not enter on,
#     and the stop is live on every one of them (see `no_target`). So the gap rules, the
#     bigger-than-1R gapped stop and the -1R convention all apply to Quickfixclose1,
#     Quickfixopen2 and Quickfixclose2 exactly as they do to a target strategy; what those
#     three do NOT have is a target that could be ambiguous against the stop.

import json
import sys
from pathlib import Path

# charter owns the array parsers; import them rather than rewrite (README contract).
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / ".." / "charter" / "scripts"))
import charting_core as cc  # noqa: E402

import strategies  # noqa: E402   (strategies.py imports nothing, so there is no cycle)

# --- simulation inputs ------------------------------------------------------------
TIMEFRAME = "daily"
ARRAY_ROOT = HERE / ".." / "hyperliquid_bot" / "data" / "array"
OUT_DIR = HERE / "output"
REFERENCE_MARKET = "Gold_Futures_COMEX"   # the market single-market runs use

# No date window: it is data-driven. Entries start at the first bar whose PREVIOUS
# file carries enough reversals, and run to the last available file.
STARTING_CAPITAL = 100_000.0
# --- risk per trade -----------------------------------------------------------------
# Percent of equity risked per trade -- this IS 1R, so every R multiple in the outputs is
# worth this many percent.
#
# It is a property of the STRATEGY, not of the project (`Strategy.risk_pct`, solved by
# `solve_risk.py`): each strategy's default is the risk that puts THAT strategy at a 6%
# maximum drawdown, so every page opens at the same PAIN rather than the same bet size. That
# is the comparison the whole project ranks on, and quoting one strategy's number on another
# strategy's page was simply wrong (user, 2026-07-27).
#
# RISK_PCT is the REFERENCE risk: the one the shared variant grid in `_variants.json` is
# priced at, which the pages self-check their replay against, and the default when a caller
# does not name one. Keeping it fixed is what makes that guard meaningful -- the grid is
# shared by every page, so it cannot be priced per strategy. It is set to quickfix's own
# default because quickfix is the reference strategy; nothing depends on them being equal.
RISK_PCT = 1.39
TARGET_DD = 6.0             # the drawdown budget each strategy's default risk is solved for
FEES = 0.0                  # per-trade cost, in equity percent; 0 for now

MIN_REVERSALS = 3          # Rule 1: at least this many tested reversals
MIN_RR = 3.5               # Rule 3: minimum reward-to-risk to take the trade
# Rule 4's profit cap is NOT a constant here: it belongs to the strategy (strategies.py),
# it is a dial on the reports, and the whole strategies.CAP_CHOICES grid is backtested in
# one pass. Rules 1-3 above are fixed for every strategy and every cap.

# A market is OBSOLETE when its newest daily bar lags the newest daily bar across ALL markets
# by more than this (charter's rule, and relative rather than a hardcoded date so it stays
# correct as the data moves on). Defined here because the engine itself needs it -- see
# CLOSE_OBSOLETE_AT_END.
OBSOLETE_AFTER_DAYS = 30

# Data collection for an obsolete market has stopped for good, so a position still open on
# its last bar would never resolve: it can neither reach its target nor be stopped, and it
# would sit in the ledger as 'open_at_end' forever, tying up risk in the portfolio for a
# trade with no possible outcome. We therefore FLATTEN it at that last bar's CLOSE (exit
# reason 'data_end') -- the last price the data actually gives us -- which books a real
# P&L instead of a permanent unknown.
#
# This applies ONLY to obsolete markets. A position open on the last bar of an ACTIVE market
# is genuinely still running and stays 'open_at_end': tomorrow's file will resolve it.
CLOSE_OBSOLETE_AT_END = True


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
    # No target here: Rule 4 is a property of the POLICY, not of the signal, and the same
    # position is replayed under every Rule 4 in the grid. The position carries the raw
    # ingredients instead -- `risk` (the cap family prices its ceiling off it) and the entry
    # BAR's own high/low/tick (Quickfixwick prices its target off those) -- so a policy never
    # needs anything the position does not already hold.
    return dict(side="short", entry=entry, stop=stop, risk=risk,
                bar_high=bar.high, bar_low=bar.low, tick=tick)


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
                bar_high=bar.high, bar_low=bar.low, tick=tick)


# --- trade management -------------------------------------------------------------
def check_exit(policy, pos, bar, bull, bear, prev_close):
    """Does `pos` close on `bar`? Returns (exit_price, reason) or None.

    Only ever called on bars AFTER the entry bar: the profit target can never be reached
    on the entry bar itself (the entry is confirmed on that bar's close, so its high/low
    are already spent -- and by construction the stop is one tick beyond that bar's own
    extreme). Management therefore starts the day after entry.

    `bull`/`bear` are the previous file's levels (known at the bar's start). The target in
    force comes from the Rule 4 `policy` and is recomputed here on every bar. It may be
    None -- an uncapped run has no target while no opposite reversal exists beyond entry --
    in which case only the stop can close the trade. On a later bar, in this order:

      - the bar OPENED beyond the stop   -> GAPPED out; fills at the OPEN, not at the stop.
        A gap is the one case where a daily bar reveals the intraday order: the open is the
        day's first price, so nothing can have traded before it. The loss is therefore
        bigger than 1R by however far the gap ran.
      - the bar GAPPED past the target -> fills at the open, better than the target for the
        same reason. A gap means price JUMPED OVER the level: `prev_close` must be on the
        near side of the target and the open on the far side. Testing the open alone was a
        bug (found 2026-07-27): a short's entry bar closes BELOW the entry by definition, so
        whenever the target sat above that close it was already in the money before
        management started, the next open was "past" it as a matter of course, and the trade
        was paid out at that open instead of at its target. It cost quickfix ~24R of free
        profit at 2.5R and made a 0R cap the best setting on the whole grid, at +1.94R a
        trade for a target sitting ON the entry price. An already-through target is not a
        gap: a resting limit there fills AT the limit, which is what the in-range branch
        below does.
      - only the target in range   -> clean win at the target;
      - only the stop in range      -> clean stop (-1R);
      - BOTH in range on one bar     -> the intraday order is unknowable, so we give the
        benefit of the doubt to a loss: 'unknown_pl', exit_price None, booked -1R. Now that
        gaps are resolved above, this is only the bar that opened BETWEEN the two levels and
        then traded through both -- which really is unknowable without intraday prices.

    The two gap tests are mutually exclusive by construction (a short's target is below its
    entry and its stop above it, so one open cannot be beyond both), but the stop is checked
    first anyway, keeping the same doubt-goes-to-the-loss convention as the ambiguous case.

    The STOP needs no already-through guard, only the target does. A stop sits one tick
    beyond the entry bar's own extreme, so the entry close can never be through it; and on
    any later bar a previous close beyond the stop is impossible, because that bar would
    already have closed the trade.

    The policy NAMES its own exit, and the name goes into the ledger as it comes: 'target_r'
    = the R cap itself was hit, at whatever cap the run used; 'target_bar' = Quickfixwick's
    entry-bar wick. The one name the policy does not settle is 'reversal', which is
    resolved here into the SIDE of the level that closed the trade -- the policy knows a
    reversal target is in force, but the ledger wants to say which ladder it came off.
    """
    target, treason = policy(pos, bull, bear)
    if pos["side"] == "short":
        stop_in = bar.high >= pos["stop"]
        target_in = target is not None and bar.low <= target
        stop_gap = bar.open >= pos["stop"]
        # a REAL gap: price was on the near side of the target at the last close, and opened
        # past it. Without the prev_close half, an already-in-the-money target pays out at
        # the open -- see the note above.
        target_gap = target is not None and bar.open <= target < prev_close
        treason_name = "bearish_reversal" if treason == "reversal" else treason
    else:
        stop_in = bar.low <= pos["stop"]
        target_in = target is not None and bar.high >= target
        stop_gap = bar.open <= pos["stop"]
        target_gap = target is not None and bar.open >= target > prev_close
        treason_name = "bullish_reversal" if treason == "reversal" else treason

    if stop_gap:                        # gapped through the stop -> filled at the open
        return bar.open, "stop"
    if target_gap:                      # gapped past the target -> filled at the open
        return bar.open, treason_name
    if stop_in and target_in:
        return None, "unknown_pl"
    if stop_in:
        return pos["stop"], "stop"
    if target_in:
        return target, treason_name
    return None


def no_target(pos, bull, bear):
    """A target policy that never has a target: 'only the stop is watching this bar'.

    This is how a BAR EXIT gets the stop. Rule 4 is the exit rule, and the stop is not Rule 4
    (user, 2026-07-31), so a bar exit that holds the trade past its entry bar is stopped out
    on the bars in between exactly as any other strategy would be, gap fills and all. Passing
    this to `check_exit` reuses that shared machinery rather than writing a second, subtly
    different stop test beside it: with no target, `check_exit` reduces to the gapped-stop
    branch and the in-range stop branch, and neither the ambiguity case nor the target gap
    can arise.
    """
    return None, "none"


def r_multiple(pos, exit_price):
    if pos["side"] == "short":
        return (pos["entry"] - exit_price) / pos["risk"]
    return (exit_price - pos["entry"]) / pos["risk"]


# --- backtest loop ----------------------------------------------------------------
def backtest(bars, tick, dp, rule4, close_at_end=False, risk_pct=None):
    """Run one `rule4` (a strategies.Rule4) over `bars` (oldest -> newest), fresh capital.

    Data-driven window: entries fire from the first bar whose PREVIOUS file carries
    enough reversals, and run to the last bar. Returns dict(trades, equity_curve,
    final_equity, first_trade_date). One position at a time.

    Rule 4 arrives as the whole object rather than as a bare policy because it may close a
    trade in either of two ways (see strategies.Rule4): a price TARGET resolved by
    `check_exit`, or a BAR EXIT that names a price off the bar itself. A bar exit is also
    the only thing allowed to close a trade on its own ENTRY bar, so it is called once at
    k=0 immediately after the entry is booked; a target policy is not, and management for it
    starts the next bar as it always has. On every LATER bar a bar exit runs beside the stop
    rather than instead of it (`no_target`), ordered by `rule4.bar_exit_at`.

    `close_at_end` decides what happens to a position still open on the LAST bar:
      False (active market)   -> reported as 'open_at_end', unrealized, no P&L. The market
                                 is still being collected, so the trade is genuinely running.
      True  (obsolete market) -> flattened at that bar's CLOSE as 'data_end' with a real
                                 P&L. The data has stopped, so the trade could never
                                 resolve. Callers pass run_markets' obsolete flag; see
                                 CLOSE_OBSOLETE_AT_END.

    `risk_pct` scales the reported percentages and this single-market equity curve; it does
    NOT change which trades fire or their R multiples, which are fixed by price and reversals
    alone. That is why the portfolio and the pages can re-run the money management at any
    risk without re-running the backtest. Defaults to the reference RISK_PCT.
    """
    risk_pct = RISK_PCT if risk_pct is None else risk_pct
    policy, bar_exit = rule4.policy, rule4.bar_exit
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
            if bar_exit is not None:
                # A bar EVENT, not a level: there is no target to be ambiguous about, and the
                # rule reads a price straight off the bar. But the STOP is not Rule 4, so it
                # is still watching every bar the trade is held through (user, 2026-07-31) --
                # which matters as soon as a bar exit fires later than bar 1.
                #
                # The order on the exit bar is not a guess:
                #   an OPEN exit wins outright. The open is the bar's first price, so nothing
                #     can have traded ahead of it. (A stop the open gapped through would fill
                #     at that same open anyway, so the two agree even then.)
                #   a CLOSE exit yields to the stop. A stop triggers the moment price touches
                #     it; a market-on-close waits for the bell. So a stop inside that bar's
                #     range was hit first, and it is resolved with the usual gap handling.
                # `Rule4.bar_exit_at` is which of the two.
                hit = bar_exit(pos, bar, i - pos["entry_index"])
                if hit is None or rule4.bar_exit_at != "open":
                    stopped = check_exit(no_target, pos, bar, sig_bull, sig_bear, prev.close)
                    if stopped is not None:
                        hit = stopped
            else:
                # prev.close is the last price before this bar opened -- the reference the
                # gap test needs to tell a jump OVER the target from a target that was
                # already through. `prev` is never None here: no position exists on bar 0.
                hit = check_exit(policy, pos, bar, sig_bull, sig_bear, prev.close)
            if hit is not None:
                exit_price, reason = hit
                equity = _close(pos, bar, i, exit_price, reason, equity,
                                trades, equity_curve, dp, risk_pct)
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
        risk_dollars = equity * risk_pct / 100.0
        pos = dict(id=tid, entry_index=i, entry_date=bar.date,
                   equity_before=equity, risk_dollars=risk_dollars, **entry)
        # The Rule 4 level in force at entry, recorded for the ledger (it can move later).
        # A bar exit has no level at all -- "the next bar's open" is not a price anything
        # knows yet -- so the ledger's `target` is honestly null for those.
        pos["target"] = (None if bar_exit is not None
                         else policy(pos, sig_bull, sig_bear)[0])
        # A target policy cannot exit here: the entry bar's range is spent and the stop sits
        # one tick beyond it, so management starts on the next bar. A BAR EXIT can, and
        # Quickfixclose0 is exactly that -- marked out at this bar's own close.
        if bar_exit is not None:
            hit = bar_exit(pos, bar, 0)
            if hit is not None:
                equity = _close(pos, bar, i, hit[0], hit[1], equity,
                                trades, equity_curve, dp, risk_pct)
                pos = None

    if pos is not None and close_at_end:       # obsolete market -> flatten at the last close
        last = bars[-1]
        equity = _close(pos, last, len(bars) - 1, last.close, "data_end", equity,
                        trades, equity_curve, dp, risk_pct)
    elif pos is not None:                      # still open at the end -> reported, unrealized
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


def _close(pos, bar, i, exit_price, reason, equity, trades, equity_curve, dp, risk_pct):
    """Realize a closed trade, append it, update and record equity, return new equity.

    An 'unknown_pl' exit has no fill price: the path was ambiguous, so it is booked at
    -1R with exit_price null -- the benefit of the doubt goes to a loss.
    """
    if reason == "unknown_pl":
        r, exit_out = -1.0, None
    else:
        r, exit_out = r_multiple(pos, exit_price), _r(exit_price, dp)
    pnl_pct = r * risk_pct - FEES
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
def run_markets(picked, caps=None, progress=True):
    """Backtest EVERY market at EVERY cap in the grid, in one pass over the archive.

    Reading and parsing the array xlsx files is by far the slow part, so each market's
    bars are parsed ONCE and reused -- which is also why the runners take a precomputed
    result list: a full refresh loads the archive once, not once per output file.

    What is backtested is RULE 4 SETTINGS, not strategies: two strategies sharing a cap are
    one run, computed once and shared. Each strategy is then just a pointer into
    that grid at its own default. `caps` defaults to strategies.CAP_CHOICES -- the grid the
    reports let you move the dial across -- and every `picked` strategy's own Rule 4 is
    added on top, which is how the three strategies outside the cap family get run at all.
    Pass a shorter `caps` list (e.g. just the defaults) when only the on-disk outputs are
    wanted.

    Every market is loaded FIRST, because obsolescence is a cross-market property: it is
    measured against the newest daily bar across all markets, and the backtest needs to know
    it up front (an obsolete market's open position is flattened at its last close rather
    than left unresolved -- see CLOSE_OBSOLETE_AT_END).

    Returns a list of dicts: name, bars, tick, dp, obsolete,
      var = {Rule 4 token -> result}  every cap in the grid, plus every picked strategy's own
      res = {strategy key -> result}  the same objects, at each strategy's default Rule 4.
    """
    if caps is None:
        caps = list(strategies.CAP_CHOICES)
    rules = {strategies.cap_token(c): strategies.cap_rule4(c) for c in caps}
    # A strategy whose Rule 4 is off the grid -- a cap that is not in `caps`, or a Rule 4
    # that is not a cap at all -- must still be runnable. setdefault, so a strategy sitting
    # on a grid cap shares that one run rather than duplicating it.
    for s in picked:
        rules.setdefault(s.token, s.r4)

    loaded = []
    for d in market_dirs():
        bars = load_bars(d)
        if bars:
            loaded.append((d.name, bars))
    if not loaded:
        return []
    newest = max(b[-1].date for _, b in loaded)

    out = []
    for name, bars in loaded:
        obsolete = (newest - bars[-1].date).days > OBSOLETE_AFTER_DAYS
        tick, dp = infer_tick(bars)
        flatten = obsolete and CLOSE_OBSOLETE_AT_END
        # The grid is priced at the REFERENCE risk: it is shared by every page, so it cannot
        # carry one strategy's risk. Only the reported percentages depend on that -- the
        # trades and their R multiples do not -- and run_portfolio re-runs the money
        # management from R anyway.
        var = {tok: backtest(bars, tick, dp, r4, close_at_end=flatten)
               for tok, r4 in rules.items()}
        # A strategy's own run reuses the grid's when its risk IS the reference, and is a
        # second pass otherwise: the per-market workbook reports percentages and a fresh-
        # capital equity curve, and those must be at the risk the strategy is documented at.
        res = {}
        for s in picked:
            res[s.key] = (var[s.token] if abs(s.risk_pct - RISK_PCT) < 1e-9 else
                          backtest(bars, tick, dp, s.r4, close_at_end=flatten,
                                   risk_pct=s.risk_pct))
        out.append(dict(name=name, bars=bars, tick=tick, dp=dp, obsolete=obsolete,
                        var=var, res=res))
        if progress:
            parts = []
            for s in picked:
                r = res[s.key]
                closed = [t for t in r["trades"] if t["exit_reason"] != "open_at_end"]
                parts.append(f"{s.key} {len(closed):>3}tr "
                             f"{(r['final_equity'] / STARTING_CAPITAL - 1) * 100:+7.2f}%")
            print(f"{'OBS ' if obsolete else '    '}{name:38} bars={len(bars):>4}  "
                  + "  |  ".join(parts))
    return out


# --- single-market run (the reference ledger) -------------------------------------
def run_single(strategy, market=REFERENCE_MARKET):
    """One market, fresh capital: write the JSON ledger and print a summary."""
    bars = load_bars(ARRAY_ROOT / market)
    tick, dp = infer_tick(bars)
    res = backtest(bars, tick, dp, strategy.r4, risk_pct=strategy.risk_pct)
    result = dict(
        meta=dict(market=market, timeframe=TIMEFRAME, strategy=strategy.key,
                  start=str(bars[0].date.date()), end=str(bars[-1].date.date()),
                  starting_capital=STARTING_CAPITAL, risk_pct=strategy.risk_pct,
                  tick=tick, fees=FEES, min_reversals=MIN_REVERSALS,
                  min_rr=MIN_RR, target_cap=strategy.cap, rule4_token=strategy.token,
                  rule4=strategy.rule4),
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
    for _s in strategies.selected(sys.argv[1:]):
        run_single(_s)
        print()
