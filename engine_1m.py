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
- RULE 3 IS REMOVED (Lode, 2026-08-06): the 3.5x room-to-opposite-
  structure requirement was target-era logic - this strategy exits at
  the next day's settlement regardless, so the requirement guarded
  nothing and its existence clause (no opposite-side reversals -> no
  trade at all) blocked exactly the one-sided files that mark the
  strongest trends (GC 2026-02-02).
- TIGHTENING IS A DIAL (`tighten`): when on, a confirmed trade's stop
  moves to the entry day's extreme +- 1 tick at the entry-day
  settlement (the daily engine's stop, now knowable); when off the
  stop stays where it was placed.
- THE OVERNIGHT WINDOW IS A DIAL (`allow_pre_activation`): when off,
  entries require the ACTIVE file to be the current trading day's own
  update (publish/data date >= previous trading date). Monday's update
  lands Saturday (its second-column date is Monday), so Mondays trade
  from the open in both modes.
- THE SESSION LOCKOUT (`max_entries_per_session`, default 1, Lode
  2026-08-06). At most N ENTRIES per market per session; with N=1 a
  market that has taken its trade is shut for the rest of that day, so
  a stop-out cannot be re-attacked. It is NOT part of rules 1-3: those
  describe what the chart must show, this is a fact about our own
  previous trade, the same family as one-position-per-market.
  Measured before it was built (research_1m_levels.py): the 1st trade
  of a market-day wins 39.4% for +42.51R, the 2nd wins 21.4% for
  -10.39R, the 4th and 5th win nothing. Every same-session repeat in
  the sample was a re-attack of the SAME level.
  IT COUNTS ENTRIES, NOT EXITS, and that distinction is worth 19R: a
  position carried in from the previous session and stopped intraday
  does NOT consume today's allowance. Nine trades sit in that case,
  +19.10R with 6 winners, including the sample's biggest (ZW +13.41R,
  entered 12 minutes after the previous day's position was stopped).
  Being stopped out of yesterday's trade after a fresh session and a
  fresh update is not the same event as re-attacking a level that has
  just chopped you.
  THE LOCKOUT EXPIRES AT THE SESSION BOUNDARY, never longer: returning
  to a level on a LATER day pays (+12.60R on this sample).
- THE CONFIRMATION CLAUSE IS A DIAL (`confirm`, 2026-08-06). On (the
  model as designed): the entry day must settle at least a tick beyond
  the first reversal or the trade is flattened there. Off: every trade
  is carried to the next day's settlement with the stop live, and
  `no_confirm` never appears. The clause is the intraday stand-in for
  the daily engine's own entry trigger (there a trade only exists once
  a bar CLOSES beyond the level), which is why it is a dial and not a
  candidate for removal on sight, unlike rule 3. Never measured until
  now: it had two behaviour tests and no experiment.
- THE STOP ANCHOR IS A DIAL (`stop_mode`, 2026-08-06):
  * "ladder" - one tick beyond the 5th (else 4th) reversal. The model
    as designed.
  * "ladder_or_extreme" - one tick beyond whichever of that anchor and
    the session's RUNNING EXTREME AT ENTRY is further away. Motivated
    by USO 2026-03-13: the session printed 121.15 at 18:19 and the
    trade entered at 18:48 with its stop at 120.51, so the day had
    already traded through its own invalidation. Only ever widens.
  * "extreme" - one tick beyond the running extreme alone, which on a
    quiet day is TIGHTER than the ladder. It is in the grid to tell
    "wider is worse" apart from "moving the stop at all is worse".
  R is denominated level-to-stop in every mode, so a wider stop is a
  smaller position and fewer R on the same move; a stop that is hit
  still costs the same 1% either way. After a same-day re-entry the
  two extreme modes price the new stop off the now-further extreme,
  which is v1's anti-whipsaw property returning.
- LADDER GEOMETRY IS A DIAL (`min_rpu_range_ratio` /
  `max_rpu_range_ratio`, both None = off, 2026-08-10). Refuse an entry
  whose risk distance (level-to-stop) is smaller / larger than the given
  fraction of the market's trailing 24-hour high-low range. ADOPTED into
  the published baseline at 0.00 / 0.50 (Lode, 2026-08-10, audit s.15e).
  The upper cut has a derivation, not just a table: under the fixed
  settlement exit a ladder wider than half a day's travel has a payoff
  capped below 2R against a full -1R downside (s.15b), and the sweep
  shows a plateau at 0.40-0.55, not a fitted point. The LOWER cut is
  deliberately 0.00 = no lower cut: the researched 0.20 ridge is a
  one-step discontinuity carried by five trades, and the sub-0.20 region
  (compact ladders, possibly with a wider stop) has its own
  investigation parked (s.15d). Mechanics, so the number is
  reproducible:
  * The window is the trailing RANGE_WINDOW of wall clock,
    holding the bars strictly BEFORE the candidate minute - the same
    definition s.14 measured, so its buckets and this dial agree.
  * It RESETS AT A CONTRACT ROLL: prices either side of a splice are not
    comparable, so a window may not span one.
  * With fewer than MIN_RANGE_BARS in the window the filter cannot
    judge and DOES NOT REFUSE (a short window would otherwise read as a
    tiny range, i.e. a huge ratio, and reject the day after every roll).
    Those cases are counted as `range_unjudged` rather than hidden.
  * A refused entry does NOT spend the session-lockout allowance - no
    entry happened - so a later minute may trigger instead. The trade
    list therefore SHIFTS rather than shrinks, which is exactly why this
    is an engine dial and not a post-filter over the blotter.

Rules recap (short side; long is the mirror):
- Every minute, rules 1 and 3 evaluate fresh against the ACTIVE levels
  file (its ladder AND its own prev_close) using the session's RUNNING
  extremes, no matter when those extremes were made.
- Ladder = the file's bullish reversals above prev_close, ascending.
  Rule 1: >= MIN_REVERSALS tested (run_high reached them); the ladder
  itself must carry >= MIN_LADDER levels. first = lowest, second = next.
- Rule 2: one verdict per (day, ladder): refuse if day open >= second.
- Trigger: once armed, the first minute in which the first-reversal
  price PRINTS (low <= first <= high) - the market order fires at the
  level, entry = first - ENTRY_SLIP_TICKS. If the bar GAPS past the
  level without printing it (prev close above, high below), the order
  fires at the first available price: entry = open - slippage. A bar
  merely trading beyond the level (price already past it) is NOT a
  trigger - the level itself must trade or be jumped. If the arming
  minute itself prints the level, its CLOSE must be back beyond the
  level (OHLC cannot order events inside one bar).
- Confirmation at entry-day settlement (`confirm`, OFF at the published
  baseline since 2026-08-06): settle must be >= 1 tick beyond
  min(entry-time first, active-ladder first at settlement); else exit at
  the settlement price (reason no_confirm).
- Exit: next trading day's settlement (reason close1). Stop live
  throughout (reason stop). No new entries at/after the settlement.
  Same-day re-entry after a stop-out is allowed (fresh trigger; the
  ladder stop does not widen - only rule 3's growing base gates it).
"""

from collections import deque
from dataclasses import dataclass
from datetime import timedelta

MIN_REVERSALS = 3         # tested reversals required (rule 1)
# Trailing window for the geometry dial. A timedelta, not seconds: bar
# timestamps arrive as pandas Timestamps and this module stays pandas-free.
RANGE_WINDOW = timedelta(hours=24)
MIN_RANGE_BARS = 60      # below this the geometry dial abstains (see above)
MIN_LADDER = 4            # levels the ladder must carry (stop anchor)
ENTRY_SLIP_TICKS = 2      # market-order entry slippage, in the PRICE
                          # (4 -> 2, Lode 2026-08-06)
RISK_PCT = 1.0            # percent of cash balance risked per trade
STARTING_CAPITAL = 100_000.0
SLIP_STOP_TICKS = 2       # stop exits (3 -> 2, Lode 2026-08-06)
SLIP_SCHEDULED_TICKS = 1  # settlement exits (close1, no_confirm): the time
                          # is known in advance, so the order can be worked.
                          # NOT a liquidity claim - the day's volume peaks are
                          # the open and the session close, and settlement is
                          # neither (Lode, 2026-08-06)


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


STOP_MODES = ("ladder", "ladder_or_extreme", "extreme")


def run_market(days, files, tick, risk_pct=RISK_PCT,
               start_capital=STARTING_CAPITAL, tighten=True,
               allow_pre_activation=True, confirm=True, stop_mode="ladder",
               max_entries_per_session=1, min_rpu_range_ratio=None,
               max_rpu_range_ratio=None):
    """Run quickfix1m1dc v2 over consecutive Days. Returns (trades, summary).

    `files` must be sorted by activation_ts. Bars must be chronological.
    `tighten`, `allow_pre_activation`, `confirm`, `stop_mode` and the two
    `*_rpu_range_ratio` bounds are the dials; see the module docstring for
    what each one means.
    """
    if stop_mode not in STOP_MODES:
        raise ValueError(f"stop_mode must be one of {STOP_MODES}")
    trades = []
    cash = start_capital
    pos = None
    zero_dist_entries = 0
    prev_trading_date = None
    # Trailing high-low window for the geometry dial: bars strictly before
    # the candidate minute, never spanning a contract splice.
    geometry_on = (min_rpu_range_ratio is not None
                   or max_rpu_range_ratio is not None)
    win = deque()
    win_contract = None
    refused_tight = refused_wide = range_unjudged = 0

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
        if day.contract != win_contract:      # a splice is not a price move
            win.clear()
            win_contract = day.contract

        run_high = run_low = None
        prev_c = None
        day_open = day.bars[0][1] if day.bars else None
        settled = False
        # The session lockout counts ENTRIES TAKEN TODAY, so a position
        # carried in from the previous session spends none of it (see the
        # module docstring: that distinction is worth 19R).
        entries_today = 0
        # Rule 2 verdicts, one per (ladder, side), keyed by publish_date.
        rule2 = {}

        def settle(pos_):
            """Confirmation on the entry day; close1 exit afterwards."""
            if pos_ is None:
                return None
            if pos_.entry_date != day.date:
                book(pos_, day.settle_ts, day.settle_price, "close1")
                return None
            if confirm:
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

            # Prune the trailing window to the bars strictly before this
            # minute (it is appended to at the bottom of the loop).
            if geometry_on:
                cutoff = bts - RANGE_WINDOW
                while win and win[0][0] < cutoff:
                    win.popleft()

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
            locked = (max_entries_per_session is not None
                      and entries_today >= max_entries_per_session)
            scan = not (pos is not None or not day.entries_allowed
                        or settled or locked)
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
                # The stop anchor: structure, the session's running extreme
                # at this minute, or the further of the two. run_high /
                # run_low already include THIS bar, so the extreme modes
                # cover the trigger bar's own spike.
                if side == "short":
                    stop = anchor + tick
                    if stop_mode != "ladder":
                        ext = run_high + tick
                        stop = max(stop, ext) if stop_mode == \
                            "ladder_or_extreme" else ext
                    rpu = stop - first
                    entry_price = entry_base - ENTRY_SLIP_TICKS * tick
                else:
                    stop = anchor - tick
                    if stop_mode != "ladder":
                        ext = run_low - tick
                        stop = min(stop, ext) if stop_mode == \
                            "ladder_or_extreme" else ext
                    rpu = first - stop
                    entry_price = entry_base + ENTRY_SLIP_TICKS * tick
                # Ladder geometry against the trailing range. Abstain when
                # the window is too short to judge; refusing does not spend
                # the lockout allowance, so a later minute may trigger.
                if geometry_on:
                    if len(win) < MIN_RANGE_BARS:
                        range_unjudged += 1
                    else:
                        rng = (max(x[1] for x in win)
                               - min(x[2] for x in win))
                        ratio = rpu / rng if rng > 0 else None
                        if ratio is not None:
                            if (max_rpu_range_ratio is not None
                                    and ratio > max_rpu_range_ratio):
                                refused_wide += 1
                                continue
                            if (min_rpu_range_ratio is not None
                                    and ratio < min_rpu_range_ratio):
                                refused_tight += 1
                                continue
                risk_usd = cash * risk_pct / 100.0
                pos = _Position(side=side, contract=day.contract,
                                entry_date=day.date, entry_ts=bts,
                                entry=entry_price, stop=stop, stop_entry=stop,
                                rpu=rpu, entry_first=first,
                                risk_usd=risk_usd)
                entries_today += 1
                break
            prev_c = c
            if geometry_on:
                win.append((bts, h, l))

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
        # Geometry dial bookkeeping: zero on every run with the dial off.
        refused_wide=refused_wide,
        refused_tight=refused_tight,
        range_unjudged=range_unjudged,
    )
    return trades, summary
