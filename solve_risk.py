# solve_risk.py
#
# Solve each strategy's DEFAULT RISK: the percentage of liquid capital per trade that puts
# that strategy at engine.TARGET_DD (6%) maximum drawdown on the current data.
#
#   venv\Scripts\python.exe solve_risk.py             # every registered strategy
#   venv\Scripts\python.exe solve_risk.py quickfixwick   # just one
#
# NOT every strategy is published at its solved risk. Only quickfix is (`risk_solved=True`);
# the three quick exits are published at a flat 1% by the user's choice, so their solve is
# printed for information and they are never called stale. See `Strategy` in strategies.py.
#
# Those numbers live as constants in `strategies.py` (`Strategy.risk_pct`) because everything
# downstream -- the workbooks, the JSON ledgers, the pages' opening risk, the "1R = x%" line
# in the rules block -- has to agree on one published figure, and re-solving on every run
# would make the reports quietly move under the reader. This script is how the constants are
# derived: RUN IT AND PASTE THE NUMBERS BACK whenever the rules, the fill model or the
# archive change. It prints the paste-ready line for each strategy and says whether the
# constant currently in the registry is still right.
#
# Why per strategy at all: a drawdown budget is the thing actually being chosen, and return
# is what comes out of it. Opening every page at one bet size shows different depths of hole
# and invites ranking them on return alone -- which flatters whichever strategy was allowed
# to dig deepest. Solved this way, the pages are directly comparable. (`comparison.html`
# makes the same argument across strategies rather than across caps, and does the same
# bisection in the browser to do it.)
#
# Method: maximum drawdown rises monotonically with risk (a bigger bet swings the balance
# further), so a plain bisection finds it. It calls run_portfolio's OWN `account()` -- never
# a second copy of the money management, which would be free to drift and would then hand
# back a risk that does not actually produce the target.

import sys

import engine as eng
import run_portfolio as rp
import strategies

TOLERANCE = 0.0005          # percent of risk; ~1e-3 of a basis point on the final figure


def solve(raw, all_days, first_day, target=None):
    """The risk that puts this account at `target` max drawdown, or None if unreachable."""
    target = eng.TARGET_DD if target is None else target

    def dd(risk):
        with rp.at_risk(risk):
            return rp.account(raw, all_days, first_day)[1]["max_dd"]

    lo, hi = 0.0, 8.0
    while dd(hi) < target:                 # a very shallow strategy may need a bigger bet
        hi *= 2
        if hi > 100:
            return None
    while hi - lo > TOLERANCE:
        mid = (lo + hi) / 2
        if dd(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main(argv):
    picked = strategies.selected(argv)
    results = eng.run_markets(picked, caps=[s.cap for s in picked if s.r4.in_grid],
                              progress=False)
    print(f"target max drawdown: {eng.TARGET_DD:g}%\n")
    stale = []
    for s in picked:
        raw, all_days = rp.collect(results, lambda m, k=s.key: m["res"][k]["trades"])
        rp.prepare(raw)
        first_day = rp.first_trading_day(raw, all_days)
        risk = solve(raw, all_days, first_day)
        if risk is None:
            # Not a failure. Quickfixclose0 lands here by construction: its exits are all on
            # the right side of entry on gross terms, so the account barely dips and no bet
            # size reaches a 6% hole. Which is exactly why it is published at a chosen 1%.
            print(f"{s.key:12} cannot reach {eng.TARGET_DD:g}% at any risk"
                  + ("" if s.risk_solved else f"  (published at a chosen "
                                              f"{s.risk_pct:g}%, so this is expected)"))
            continue
        with rp.at_risk(risk):
            st = rp.account(raw, all_days, first_day)[1]
        # Rounded to 3 decimals, which is what goes in the registry; report the drawdown the
        # ROUNDED number actually produces, not the unrounded solution's, so the printed line
        # is the one that will be true after pasting.
        shown = round(risk, 3)
        with rp.at_risk(shown):
            st = rp.account(raw, all_days, first_day)[1]

        # STALE means "the registered risk no longer hits the target", NOT "it differs from
        # my solve in the third decimal". The registry carries deliberately round numbers
        # (quickfix is 1.39, this solver says 1.391) and demanding an exact match would leave
        # the tool permanently complaining about a rounding difference that moves the drawdown
        # by nothing. Same 0.05 tolerance the report's own chart uses on its bisection.
        with rp.at_risk(s.risk_pct):
            reg = rp.account(raw, all_days, first_day)[1]
        ok = abs(reg["max_dd"] - eng.TARGET_DD) <= 0.05
        print(f"{s.key:12} solved {shown:<6g} -> ${st['final']:>10,.0f} "
              f"({st['ret']:+8.2f}%)  maxDD {st['max_dd']:5.2f}%  "
              f"ret/DD {st['ret'] / st['max_dd']:5.1f}x")
        # A strategy published at a CHOSEN risk is never stale: its registered number was
        # never meant to hit the target, so measuring it against one would be nagging about
        # a decision rather than reporting a drift. The solve above is still printed, since
        # "what 6% would cost this strategy" is worth knowing even when it is not the setting.
        print(f"{'':12} registry {s.risk_pct:<6g} -> ${reg['final']:>9,.0f} "
              f"({reg['ret']:+8.2f}%)  maxDD {reg['max_dd']:5.2f}%  "
              + ("chosen, not solved" if not s.risk_solved else
                 "still on target" if ok else "OFF TARGET -- UPDATE IT"))
        if s.risk_solved and not ok:
            stale.append((s, shown))

    if stale:
        print("\nPaste into strategies.py:")
        for s, shown in stale:
            print(f"    {s.key}: risk_pct={shown:g}")
        print("\n...and set engine.RISK_PCT to quickfix's number (the shared variant grid "
              "is priced at it).")
        return 1
    print("\nevery registered risk_pct is current")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
