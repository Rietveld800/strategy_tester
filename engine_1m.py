"""1-minute backtest engine for quickfix1m1dc (v2, standalone).

Design v1 and every original rule decision: see
../data_center/docs/backtest_1m_design.md. The v2 entry/stop model is
Lode's audit decisions (2026-08-06, docs/quickfix1m1dc_audit.md):

- ENTRY IS A MARKET ORDER AT THE LEVEL TOUCH, not a limit resolved on
  1-minute closes. The 1m chart is a visual validator; we model acting
  in real time and charge a flat ENTRY_SLIP_TICKS (2) of adverse
  slippage on every entry. No fill uncertainty, no phantom trades, no
  missed winners.
- R IS DENOMINATED FROM THE FIRST-REVERSAL PRICE to the stop, never
  from the slipped entry (Lode: risk is computed on the level).
- STOP IS LADDER-ANCHORED: one tick beyond the 5th reversal of the
  eligible ladder, or beyond the 4th when only four exist. A setup
  requires the ladder to carry at least MIN_LADDER (4) reversals.
  No multiplier, no cluster/gap logic (parked by decision).
- TIGHTENING IS A DIAL (`tighten`): when on, a confirmed trade's stop
  moves to the entry day's extreme +- 1 tick at the entry-day
  settlement (the daily engine's stop, now knowable); when off the
  stop stays where it was placed.
- THE OVERNIGHT WINDOW IS A DIAL (`allow_pre_activation`): when off,
  entries require the ACTIVE file to be the current trading day's own
  update (publish/data date >= previous trading date). Monday's update
  lands Saturday (its second-column date is Monday), so Mondays trade
  from the open in both modes.

Rules recap (short side; long is the mirror):
- Every minute, rules 1 and 3 evaluate fresh against the ACTIVE levels
  file (its ladder AND its own prev_close) using the session's RUNNING
  extremes, no matter when those extremes were made.
- Ladder = the file's bullish reversals above prev_close, ascending.
  Rule 1: >= MIN_REVERSALS tested (run_high reached them); the ladder
  itself must carry >= MIN_LADDER levels. first = lowest, second = next.
- Rule 2: one verdict per (day, ladder): refuse if day open >= second.
- Rule 3: nearest bearish reversal below first must be >= MIN_RR x the
  entry-to-extreme distance (max(run_high - first, 1 tick)) below it.
- Trigger: once armed, the first minute in which the first-reversal
  price PRINTS (low <= first <= high) - the market order fires at the
  level, entry = first - ENTRY_SLIP_TICKS. If the bar GAPS past the
  level without printing it (prev close above, high below), the order
  fires at the first available price: entry = open - slippage. A bar
  merely trading beyond the level (price already past it) is NOT a
  trigger - the level itself must trade or be jumped. If the arming
  minute itself prints the level, its CLOSE must be back beyond the
  level (OHLC cannot order events inside one bar).
- Confirmation at entry-day settlement: settle must be >= 1 tick beyond
  min(entry-time first, active-ladder first at settlement); else exit at
  the settlement price (reason no_confirm).
- Exit: next trading day's settlement (reason close1). Stop live
  throughout (reason stop). No new entries at/after the settlement.
  Same-day re-entry after a stop-out is allowed (fresh trigger; the
  ladder stop does not widen - only rule 3's growing base gates it).
"""

from dataclasses import dataclass

MIN_REVERSALS = 3         # tested reversals required (rule 1)
MIN_LADDER = 4            # levels the ladder must carry (stop anchor)
MIN_RR = 3.5
ENTRY_SLIP_TICKS = 2      # market-order entry slippage, in the PRICE
                          # (4 -> 2, Lode 2026-08-06)
RISK_PCT = 1.0            # percent of cash balance risked per trade
STARTING_CAPITAL = 100_000.0
SLIP_STOP_TICKS = 2       # stop exits (3 -> 2, Lode 2026-08-06)
SLIP_SCHEDULED_TICKS = 1  # settlement exits are scheduled orders


@dataclass
class LevelsFile:
    """One Socrates daily array file, as the backtest may know it."""
    publish_date: object          # datetime.date of the filename (DATA date)
    activation_ts: object         # tz-aware UTC Timestamp it became known
    bull: list                    # sorted bullish reversal prices
    bear: list                    # sorted bearish reversal prices
    prev_close: float             # the file's own OVERVIEW close


@dataclass
class Day:
    """One trading date of one front contract."""
    date: object                  # datetime.date (trading date)
    contract: str
    bars: list                    # [(ts, open, high, low, close), ...] session bars
    settle_ts: object             # tz-aware UTC Timestamp of the settlement
    settle_price: float
    entries_allowed: bool = True  # False on roll-boundary / window-end days


@dataclass
class _Position:
    side: str
    contract: str
    entry_date: object
    entry_ts: object
    entry: float                  # slipped market-order fill
    stop: float                   # the LIVE stop (may tighten at entry-day close)
    stop_entry: float             # the ladder stop as set at entry
    rpu: float                    # risk per unit = |stop - FIRST REVERSAL|
    entry_first: float            # first reversal at entry (confirmation base)
    risk_usd: float
    confirmed: bool = False
    stop_tightened: float = None  # set at entry-day close when tighten=True


def _active_file(files, ts):
    """Latest file activated at or before ts; None before the first."""
    live = None
    for f in files:
        if f.activation_ts <= ts:
            live = f
        else:
            break
    return live


def _short_setup(f, run_high):
    """(first, second, stop_anchor) under file f, or None."""
    ladder = [lvl for lvl in f.bull if lvl > f.prev_close]
    if len(ladder) < MIN_LADDER:
        return None
    tested = [lvl for lvl in ladder if lvl <= run_high]
    if len(tested) < MIN_REVERSALS:
        return None
    anchor = ladder[4] if len(ladder) > 4 else ladder[3]
    return tested[0], tested[1], anchor


def _long_setup(f, run_low):
    ladder = sorted((lvl for lvl in f.bear if lvl < f.prev_close),
                    reverse=True)
    if len(ladder) < MIN_LADDER:
        return None
    tested = [lvl for lvl in ladder if lvl >= run_low]
    if len(tested) < MIN_REVERSALS:
        return None
    anchor = ladder[4] if len(ladder) > 4 else ladder[3]
    return tested[0], tested[1], anchor


def run_market(days, files, tick, risk_pct=RISK_PCT,
               start_capital=STARTING_CAPITAL, tighten=True,
               allow_pre_activation=True):
    """Run quickfix1m1dc v2 over consecutive Days. Returns (trades, summary).

    `files` must be sorted by activation_ts. Bars must be chronological.
    `tighten` / `allow_pre_activation` are the two audit dials.
    """
    trades = []
    cash = start_capital
    pos = None
    zero_dist_entries = 0
    prev_trading_date = None

    def book(pos, exit_ts, exit_price, reason):
        nonlocal cash
        sign = -1.0 if pos.side == "short" else 1.0
        gross_r = sign * (exit_price - pos.entry) / pos.rpu
        exit_ticks = (SLIP_STOP_TICKS if reason == "stop"
                      else SLIP_SCHEDULED_TICKS)
        cost_r = exit_ticks * tick / pos.rpu
        net_r = gross_r - cost_r
        cash += net_r * pos.risk_usd
        trades.append(dict(
            side=pos.side, contract=pos.contract,
            entry_date=str(pos.entry_date), entry_ts=str(pos.entry_ts),
            entry=pos.entry, stop=pos.stop_entry, rpu=pos.rpu,
            entry_first=pos.entry_first,
            stop_tightened=pos.stop_tightened,
            exit_ts=str(exit_ts), exit=exit_price, reason=reason,
            gross_r=round(gross_r, 4), cost_r=round(cost_r, 4),
            net_r=round(net_r, 4), risk_usd=round(pos.risk_usd, 2),
            pnl_usd=round(net_r * pos.risk_usd, 2),
            cash_after=round(cash, 2)))

    for day in days:
        if pos is not None and pos.contract != day.contract:
            # Should be unreachable given roll-boundary entry exclusions.
            raise RuntimeError(
                f"position in {pos.contract} carried into {day.contract} day")

        run_high = run_low = None
        prev_c = None
        day_open = day.bars[0][1] if day.bars else None
        settled = False
        # Rule 2 verdicts, one per (ladder, side), keyed by publish_date.
        rule2 = {}

        def settle(pos_):
            """Confirmation on the entry day; close1 exit afterwards."""
            if pos_ is None:
                return None
            if pos_.entry_date != day.date:
                book(pos_, day.settle_ts, day.settle_price, "close1")
                return None
            f = _active_file(files, day.settle_ts)
            threshold = pos_.entry_first
            setup = None
            if f is not None:
                setup = (_short_setup(f, run_high)
                         if pos_.side == "short"
                         else _long_setup(f, run_low))
            if setup is not None:
                new_first = setup[0]
                threshold = (min(threshold, new_first)
                             if pos_.side == "short"
                             else max(threshold, new_first))
            ok = (day.settle_price <= threshold - tick
                  if pos_.side == "short"
                  else day.settle_price >= threshold + tick)
            if not ok:
                book(pos_, day.settle_ts, day.settle_price, "no_confirm")
                return None
            pos_.confirmed = True
            if tighten:
                # The entry day's extreme is now known: the stop moves to
                # one tick beyond it - but only when that is TIGHTER than
                # the ladder stop (after a same-day re-entry the day
                # extreme can sit beyond the ladder stop; tightening must
                # never loosen). The R denominator stays the level-to-
                # ladder-stop distance - position size was set there.
                t = (run_high + tick if pos_.side == "short"
                     else run_low - tick)
                tighter = (t < pos_.stop if pos_.side == "short"
                           else t > pos_.stop)
                if tighter:
                    pos_.stop_tightened = t
                    pos_.stop = t
            return pos_

        for bts, o, h, l, c in day.bars:
            if not settled and bts >= day.settle_ts:
                pos = settle(pos)
                settled = True

            prev_high, prev_low = run_high, run_low
            run_high = h if run_high is None else max(run_high, h)
            run_low = l if run_low is None else min(run_low, l)

            # --- manage an open position ---------------------------------
            if pos is not None:
                if pos.side == "short" and h >= pos.stop and bts > pos.entry_ts:
                    book(pos, bts, pos.stop, "stop")
                    pos = None
                elif pos.side == "long" and l <= pos.stop and bts > pos.entry_ts:
                    book(pos, bts, pos.stop, "stop")
                    pos = None

            # --- look for an entry ---------------------------------------
            scan = not (pos is not None or not day.entries_allowed
                        or settled)
            f = _active_file(files, bts) if scan else None
            if f is not None and not allow_pre_activation and (
                    prev_trading_date is None
                    or f.publish_date < prev_trading_date):
                f = None  # the day's own update is not active yet
            for side in ("short", "long") if f is not None else ():
                setup = (_short_setup(f, run_high) if side == "short"
                         else _long_setup(f, run_low))
                if setup is None:
                    continue
                first, second, anchor = setup
                key = (f.publish_date, side)
                if key not in rule2:
                    rule2[key] = (day_open < second if side == "short"
                                  else day_open > second)
                if not rule2[key]:
                    continue
                prints = l <= first <= h
                gap_beyond = (prev_c is not None
                              and ((prev_c > first and h < first)
                                   if side == "short"
                                   else (prev_c < first and l > first)))
                if not (prints or gap_beyond):
                    continue
                # Was the setup armed before this bar? If it arms on this
                # very bar, OHLC cannot order the intra-bar events, so the
                # close must be back beyond the level to prove the return.
                setup_prev = None
                if (prev_high if side == "short" else prev_low) is not None:
                    setup_prev = (_short_setup(f, prev_high)
                                  if side == "short"
                                  else _long_setup(f, prev_low))
                if setup_prev is None:
                    returned = prints and (c <= first if side == "short"
                                           else c >= first)
                    if not returned:
                        continue
                    entry_base = first
                else:
                    entry_base = o if gap_beyond else first
                dist = (run_high - first) if side == "short" else (first - run_low)
                if dist <= 0:
                    zero_dist_entries += 1
                base = max(dist, tick)
                if side == "short":
                    opposite = [b for b in f.bear if b < first]
                    if not opposite or (first - max(opposite)) < MIN_RR * base:
                        continue
                    stop = anchor + tick
                    rpu = stop - first
                    entry_price = entry_base - ENTRY_SLIP_TICKS * tick
                else:
                    opposite = [b for b in f.bull if b > first]
                    if not opposite or (min(opposite) - first) < MIN_RR * base:
                        continue
                    stop = anchor - tick
                    rpu = first - stop
                    entry_price = entry_base + ENTRY_SLIP_TICKS * tick
                risk_usd = cash * risk_pct / 100.0
                pos = _Position(side=side, contract=day.contract,
                                entry_date=day.date, entry_ts=bts,
                                entry=entry_price, stop=stop, stop_entry=stop,
                                rpu=rpu, entry_first=first,
                                risk_usd=risk_usd)
                break
            prev_c = c

        if not settled:
            pos = settle(pos)
        prev_trading_date = day.date

    if pos is not None:
        last = days[-1]
        book(pos, last.settle_ts, last.settle_price, "data_end")
        pos = None

    wins = [t for t in trades if t["net_r"] > 0]
    summary = dict(
        trades=len(trades), wins=len(wins),
        win_rate=round(100.0 * len(wins) / len(trades), 1) if trades else None,
        net_r_total=round(sum(t["net_r"] for t in trades), 2),
        final_cash=round(cash, 2),
        return_pct=round(100.0 * (cash / start_capital - 1.0), 2),
        zero_dist_entries=zero_dist_entries,
        reasons={r: sum(1 for t in trades if t["reason"] == r)
                 for r in ("stop", "no_confirm", "close1", "data_end")},
    )
    return trades, summary
