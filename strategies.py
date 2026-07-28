# strategies.py
#
# The strategy registry. Every strategy shares the engine (engine.py) -- the same signal,
# the same clean-setup filter, the same stop, the same 3.5R reward filter and the same
# daily-proxy exit resolution -- and differs ONLY in Rule 4: which profit target is in
# force while the trade is open.
#
# A strategy therefore takes EXACTLY THE SAME SETUPS as every other one; they part company
# only in where those trades are closed. Comparing two strategies compares exits, nothing
# else. (Not the same TRADES, note: an earlier exit frees the market sooner, and one
# position per market at a time means a later signal can be taken that a longer hold would
# have missed. Same rules, same signals; the realised trade list still differs.)
#
# --- Rule 4 comes in FOUR SHAPES ------------------------------------------------------
# 1. THE CAP FAMILY (`target_policy`) -- ride to the first opposite reversal beyond entry,
#    but never past `cap` R. One policy with one number in it. Quickfix is that family at
#    1.9R; the reports carry the cap as a DIAL across the whole CAP_CHOICES grid, so a page
#    can be re-run at 1.7R, 6.75R or no cap at all.
#
#    The consequence, stated plainly: with the cap exposed, a 'strategy' in this family is
#    just a dial position. Quickfix at no cap IS what used to be registered as Slowfix,
#    trade for trade -- which is why that entry was retired (see REGISTRY): the dial already
#    reaches it, and a second page for one setting earned nothing.
#
# 2. THE ENTRY BAR'S WICK (`entry_bar_policy`) -- take profit one tick beyond the entry
#    bar's own opposite extreme, fixed at entry. Quickfixwick. A price TARGET like the cap
#    family, so it goes through the same exit machinery (stop, gaps, ambiguity), but it is
#    not priced off a reversal or an R multiple, so it is not a point on the cap dial.
#
# 3. THE ENTRY BAR'S CLOSE (`close_exit`) -- flat the same day, at the entry bar's own
#    close. Quickfixclose.
#
# 4. THE NEXT BAR'S OPEN (`open_exit`) -- flat at the open of the bar that follows the entry
#    bar, so the trade is carried through one nightly session and no further. Quickfixopen.
#
# Shapes 3 and 4 are NOT price targets, they are BAR EVENTS: "get out at this bar's close",
# "get out at the next bar's open". No level is being watched, so `check_exit`'s in-range /
# gap / ambiguity resolution has nothing to resolve, and they are expressed as a `bar_exit`
# on the Rule4 instead of as a target policy (see `Rule4` and `engine.backtest`).
#
# THE STOP NEVER TRADES on those two. Quickfixclose is closed on the bar that opened it, and
# the stop sits one tick beyond that bar's own extreme, so it cannot be reached; quickfixopen
# is closed at the FIRST price of the next bar, so nothing can trade ahead of the exit. The
# stop is still what SIZES the position (1R = the stop distance), which is its important
# job -- but it is not a floor under the loss: an adverse overnight gap takes quickfixopen
# out for more than 1R, exactly as a gapped stop does everywhere else in this project.
#
# A `Rule4` (below) is ONE setting: its policy or bar exit, the token its backtest is filed
# under, whether it is a point on the cap axis (`in_grid`), and every line of prose that
# quotes it. `Strategy` is a key, a title and one of these.
#
# To add a FIFTH shape: write the factory beside these, build a `Rule4` with `in_grid=False`
# and its own prose, and register a `Strategy` on it. Nothing downstream needs changing
# except a new exit reason, which must be added to `VAR_REASONS`, `prettyReason` AND
# charter's `TRADE_COLORS`.
#
# --- The target policy ------------------------------------------------------------
# Signature: policy(pos, bull, bear) -> (price_or_None, reason)
#
#   pos    the open position: side, entry, stop, risk, and the entry bar's own high, low
#          and tick. Nothing derived is stored on it -- the cap price and the entry-bar
#          target are both computed by the policy, because the same position is replayed
#          under every Rule 4 in the grid.
#   bull   bullish reversal levels known at the START of the bar being evaluated.
#   bear   bearish reversal levels known at the START of that bar.
#
#   reason is what the ledger calls the exit: "target_r" (the R cap), "reversal" (the engine
#          names it for the side of the level that closed it), "target_bar" (the entry bar's
#          extreme), or "none" when no target is in force on this bar.
#
# --- The bar exit (shapes 3 and 4) --------------------------------------------------
# Signature: bar_exit(pos, bar, k) -> (price, reason) or None
#
#   pos    the open position, as above.
#   bar    the bar being evaluated -- which is the whole point: these shapes exit on a bar
#          EVENT (its close, the next one's open) rather than at a level, so unlike a target
#          policy they are handed the bar and read a price straight off it.
#   k      bars since entry. 0 IS the entry bar: a bar exit is the only thing in this engine
#          that may close a trade there, and `engine.backtest` calls it once at k=0 straight
#          after the entry is booked for exactly that reason.
#
# Returning None means "not on this bar" and the position stays open. A Rule4 carries either
# a policy or a bar_exit, never both.
#
# It is called on EVERY bar the trade is open, never once at entry, so a cap-family target
# tracks the reversal ladder as Socrates redraws it: a newly appearing nearer reversal moves
# the target in, an elected one falls away. (An entry-bar target is fixed by construction --
# it is priced off the entry bar, which cannot change -- so calling it every bar returns the
# same number.) Returning None means no target is in force on this bar; only the stop can
# close the trade.
#
# Only OPPOSITE-side reversals may close a trade (bearish levels close a short, bullish
# levels close a long); a same-side level is never an exit.

# The caps the reports precompute, so the number can be moved without a rebuild. Every one is
# a full backtest -- changing the cap changes the exits, and through "one position per market
# at a time" it changes which later signals are taken as well, so it cannot be replayed in
# the browser the way the risk percentage can.
#
# ONE grid, at two resolutions (2026-07-28). It runs 0R to 10R, at TENTH-R steps up to
# CAP_FINE_TO and quarter-R above it: the interesting structure is all in the low end (the
# levered plateau starts at 1.3R and the cliffs are between 2R and 3R), while above 5.5R the
# family has flattened out and quarter-R is more resolution than the sample can carry.
#
# It replaced a pair of grids -- a 2R-10R dial axis and a separate 0R-3R detail grid for a
# second chart. One grid, one axis, one chart section: the split existed only because the
# dial could not reach below 2R, and this one can.
#
# 0R is kept deliberately even though it is degenerate (the ceiling sits ON the entry). It is
# the sanity anchor: an already-through-target bug showed up on 2026-07-27 precisely because
# a 0R cap came out best on the whole grid, which is impossible on its face.
CAP_MIN, CAP_MAX, CAP_STEP = 0.0, 10.0, 0.1
CAP_FINE_TO, CAP_COARSE_STEP = 5.5, 0.25
CAP_GRID = ([round(i * CAP_STEP, 2)
             for i in range(int(round(CAP_FINE_TO / CAP_STEP)) + 1)] +
            [round(CAP_FINE_TO + i * CAP_COARSE_STEP, 2)
             for i in range(1, int(round((CAP_MAX - CAP_FINE_TO) / CAP_COARSE_STEP)) + 1)])

# Everything that is actually BACKTESTED: the grid plus the uncapped run. None = no ceiling,
# listed first because it is one end of the same scale. 74 caps + uncapped; the backtests
# themselves are trivial next to the ~60s archive parse, and the cost that matters is the
# ~420 KB the packed rows add to every page.
CAP_CHOICES = [None] + CAP_GRID


def cap_token(cap):
    """The cap as a JSON key / URL value: 'none', '5', '4.25'."""
    return "none" if cap is None else f"{cap:g}"


def cap_label(cap):
    """The cap as it is written on a page: 'no cap', '5R', '4.25R'."""
    return "no cap" if cap is None else f"{cap:g}R"


def target_policy(cap):
    """Rule 4 at one cap. `cap` in R, or None for no ceiling at all.

    Short side (the long is the mirror): the trade wants the first bearish reversal below
    entry. A ceiling `cap`R below entry overrides it in both directions --

      - a reversal ABOVE the ceiling (nearer than the cap) is the real obstacle and becomes
        the target, because price is more likely to turn there than to run through it;
      - a reversal BELOW the ceiling (further than the cap), or no reversal at all, leaves
        the ceiling itself as the target.

    With cap=None the ceiling never exists, so the trade rides to the first opposite
    reversal however far away it is -- and if every level beyond entry has been elected, NO
    target is in force and the trade simply waits, holding, until one appears. The stop
    stays in place throughout, so a position can never be stranded forever. That waiting
    case is the ONLY behaviour a capped run cannot produce: a ceiling is always somewhere.
    """
    def policy(pos, bull, bear):
        if pos["side"] == "short":
            ceiling = None if cap is None else pos["entry"] - cap * pos["risk"]
            beyond = [b for b in bear
                      if b < pos["entry"] and (ceiling is None or b > ceiling)]
            if beyond:
                return max(beyond), "reversal"       # highest reversal above the ceiling
            return (None, "none") if ceiling is None else (ceiling, "target_r")
        ceiling = None if cap is None else pos["entry"] + cap * pos["risk"]
        beyond = [b for b in bull
                  if b > pos["entry"] and (ceiling is None or b < ceiling)]
        if beyond:
            return min(beyond), "reversal"           # lowest reversal below the ceiling
        return (None, "none") if ceiling is None else (ceiling, "target_r")
    return policy


def entry_bar_policy():
    """Rule 4 for Quickfixwick: one tick beyond the ENTRY BAR's own opposite extreme.

    Short side (the long is the mirror): take profit one tick BELOW the entry bar's low --
    a tick past the wick the bar printed on its way back down. The trade is buying the
    initial energy of the move: if the thesis that made us sell into the reversal cluster is
    right, that low should break more often than the high above it, which is where the stop
    sits. So the whole trade is contained by the entry bar, stop one tick above its high,
    target one tick below its low.

    The target is FIXED at entry and never moves. It is priced off the entry bar, and the
    entry bar cannot change, so recomputing it every bar (which the engine does, uniformly
    for every policy) returns the same number every time. Reversal levels are not consulted
    at all -- this Rule 4 is not the cap family with a different number in it, it is a
    different shape, and it has no cap to dial.

    The target is always strictly beyond the entry: the entry trigger requires the bar to
    CLOSE below the first reversal (the entry price), and the close is inside the bar's
    range, so low <= close < entry on a short. There is no degenerate case to guard.

    Note what this does to the R multiple of a winner: it is whatever the entry bar happened
    to measure -- (entry - low + tick) / (high + tick - entry) -- typically well under Rule
    3's 3.5R, and sometimes under 1R. Rule 3 still applies unchanged (it is Rule 3, not Rule
    4), so the SETUPS are identical to every other strategy; it just no longer describes the
    target, only the room the trade was given.
    """
    def policy(pos, bull, bear):
        if pos["side"] == "short":
            return pos["bar_low"] - pos["tick"], "target_bar"
        return pos["bar_high"] + pos["tick"], "target_bar"
    return policy


def close_exit():
    """Rule 4 for Quickfixclose: out at the ENTRY BAR's own close, the same day.

    A bar exit rather than a target, because there is no level being watched: the trade is
    marked out at whatever that day closed at. k == 0 is the entry bar, and it is the only
    bar this rule ever fires on, so the position never sees a second day.

    It cannot lose on GROSS terms, and that is a property of the entry rule rather than a
    flattering assumption: the entry trigger requires the bar to close BEYOND the entry
    price (a short only fires when the close is below the first reversal, which is where it
    filled), so marking out at that same close is always on the right side of entry. What
    can still lose is the NET trade, when the move from the reversal to the close is smaller
    than the two ticks of slippage charged to get in and out. That is where this strategy's
    losers come from, and it is why it has a drawdown at all.

    The stop never trades here -- it sits one tick beyond this very bar's extreme, which is
    already spent by the time the close confirms the entry. It still sizes the position.
    """
    def rule(pos, bar, k):
        return (bar.close, "exit_close") if k == 0 else None
    return rule


def open_exit():
    """Rule 4 for Quickfixopen: out at the OPEN of the bar that follows the entry bar.

    The trade is carried through one nightly session and no further. k == 0 (the entry bar)
    returns None, so the position survives the day it was opened; on the next bar the open
    is taken, unconditionally.

    Unconditional is the honest word. The open is the first price of that bar, so nothing
    can trade ahead of it: there is no order the market could have filled first, which means
    no stop test and no path ambiguity to resolve. What the trade earns is exactly what the
    overnight session did to it, which is the whole question this strategy asks.

    The flip side, stated plainly because it is the risk: the stop is not a floor. An adverse
    gap takes the trade out at the gap, well past the stop, for more than 1R -- the same
    arithmetic as a gapped stop anywhere else in this project, except that here EVERY exit
    is at an open, so it is not a rare case.
    """
    def rule(pos, bar, k):
        return None if k == 0 else (bar.open, "exit_open")
    return rule


# --- how a cap reads on a report --------------------------------------------------
# Every one of these is a function of the cap, because the cap is a dial: a page showing
# 4.25R must not carry a rule card that still says 5R. The report swaps them as the dial
# moves, so they are generated HERE and shipped to the page rather than written twice.

def rule4_line(cap):
    """The one-liner that labels the strategy in metadata, navigation and footers."""
    if cap is None:
        return "target = the first opposite reversal beyond entry, no cap"
    return f"target = {cap:g}R, or an opposite reversal nearer than {cap:g}R"


def rule4_text(cap):
    """The full Rule 4 card on the report."""
    if cap is None:
        return ("Take profit at the <b>first bearish reversal below the entry</b>, however "
                "far away it is, there is <b>no ceiling</b>, so a level sitting 8R "
                "away is ridden to 8R. Rule 3 already guarantees it is at least 3.5R away. "
                "If every level below has been elected, the trade simply waits, holding, "
                "until a new one appears; the stop stays in place throughout.")
    return (f"Take profit at <b>{cap:g}R</b>. If a bearish reversal sits closer than "
            f"{cap:g}R below the entry, that level becomes the target instead, price "
            f"is likely to turn there rather than run through it. <b>{cap:g}R is a hard "
            f"ceiling on every winner.</b>")


def lede_text(cap):
    """The cap-dependent opening sentence of the page's lede."""
    if cap is None:
        return ("Held to the end of the move: there is no ceiling, so a trade runs to the "
                "first opposite reversal beyond entry however far away that is. Rule 3 "
                "keeps that level at least 3.5R away at entry.")
    return (f"Takes profit at a fixed ceiling: a trade is closed at {cap:g}R, or earlier at "
            f"the first opposite reversal that sits between entry and {cap:g}R. The "
            f"{cap:g}R ceiling caps every winner.")


def caveat_text(cap):
    """The strategy-specific half of the page's honesty note."""
    if cap is None:
        return "a reversal target counts as hit whenever the day's range touches it"
    return f"a {cap:g}R target counts as hit whenever the day's range touches it"


def cap_texts(cap):
    """Everything on a page that has to change when the cap does, for one cap."""
    return dict(rule4=rule4_line(cap), rule4_text=rule4_text(cap),
                lede=lede_text(cap), caveat=caveat_text(cap), label=cap_label(cap))


# --- Rule 4 as an object ------------------------------------------------------------
class Rule4:
    """ONE setting of Rule 4: how it closes a trade, the token its backtest is filed under,
    and every line of prose that quotes it.

    It closes a trade in one of TWO ways, and carries exactly one of them:

      `policy`    a price TARGET, recomputed on every bar and resolved by the engine's
                  shared exit machinery (stop first, then gaps, then ambiguity). The cap
                  family and Quickfixwick.
      `bar_exit`  a BAR EVENT -- "this bar's close", "the next bar's open". No level is being
                  watched, so there is nothing for that machinery to resolve, and the engine
                  takes the price the rule names. Quickfixclose and Quickfixopen. It is also
                  the only thing that may close a trade on its ENTRY bar.

    `in_grid` says whether this setting is a point on the report's CAP DIAL. The cap family
    is (every one of CAP_CHOICES is a real backtest the pages can move between); a Rule 4 of
    a different shape is not -- there is no number in it to dial, so its page carries no cap
    control and no "Choosing the profit cap" chart. `cap` is the number for the family and
    None otherwise; do not read it as "no cap" without checking `in_grid` first.
    """

    __slots__ = ("token", "label", "policy", "bar_exit", "texts", "cap", "in_grid")

    def __init__(self, token, label, texts, policy=None, bar_exit=None, cap=None,
                 in_grid=False):
        if (policy is None) == (bar_exit is None):
            raise ValueError(f"Rule4 {token!r}: give exactly one of policy / bar_exit")
        self.token = token      # key in _variants.json and in the pages' variant table
        self.label = label      # how the setting is written on a page: '2.5R', 'day close'
        self.policy = policy    # a price target, or None
        self.bar_exit = bar_exit  # a bar event, or None
        self.texts = texts      # rule4 / rule4_text / lede / caveat / label
        self.cap = cap          # the cap in R, for the family only
        self.in_grid = in_grid  # is this a position on the report's cap dial?

    def __repr__(self):
        return f"<Rule4 {self.token}>"


def cap_rule4(cap):
    """The cap family at one cap -- a point on the reports' Rule 4 dial."""
    return Rule4(token=cap_token(cap), label=cap_label(cap), policy=target_policy(cap),
                 texts=cap_texts(cap), cap=cap, in_grid=True)


# --- the three Rule 4 shapes that are NOT caps --------------------------------------
# Their prose is WRITTEN rather than generated, because there is no number in any of them to
# generate it from. Phrased for the short side like every other rule text, and free of em
# dashes like all report prose (user, 2026-07-28).
#
# All three carry in_grid=False, so their pages drop the cap dial and the "Choosing the
# profit cap" section: neither has anything to say about a strategy that is not a point on
# the cap axis. That machinery is exactly what it was built for.

WICK = Rule4(
    token="wick",
    label="entry bar wick",
    policy=entry_bar_policy(),
    texts=dict(
        label="entry bar wick",
        rule4="target = one tick beyond the entry bar's own wick (a short: below its low)",
        rule4_text=(
            "Take profit <b>one tick below the entry bar's own low</b>, a tick past the "
            "wick it printed on the way back down. The level is fixed the moment the trade "
            "is placed and never moves, no reversal level and no R ceiling is involved. The "
            "whole trade is contained by the entry bar: the stop one tick above its high, "
            "the target one tick below its low. This is a bet on the <b>initial energy</b> "
            "of the move, if the thesis behind the entry is right, that low should break "
            "more often than the high does. A winner is worth whatever the entry bar "
            "measured, which is usually well under 3.5R."),
        lede=(
            "Captures the initial energy move only: the target is fixed at entry, one tick "
            "beyond the entry bar's own wick, a tick below its low on a short, and never "
            "moves. Stop and target are the two sides of the entry bar, so the bet is "
            "simply that its low breaks before its high."),
        caveat=(
            "the entry bar's low counts as broken whenever the day's range touches one tick "
            "below it"),
    ))

DAY_CLOSE = Rule4(
    token="close",
    label="day close",
    bar_exit=close_exit(),
    texts=dict(
        label="day close",
        rule4="exit = the entry bar's own close, flat the same day",
        rule4_text=(
            "Close the position at <b>the entry bar's own close</b>. The trade is opened and "
            "shut on the same day: it fills at the first reversal and is marked out at that "
            "day's closing price, so nothing is ever carried overnight. The entry trigger "
            "requires that close to be beyond the entry price, so on gross terms this exit "
            "cannot lose, the losers are the trades whose move was smaller than the "
            "slippage charged to get in and out. <b>The stop never trades</b>, it is spent "
            "by the time the close confirms the entry and is here only to size the "
            "position."),
        lede=(
            "Flat by the bell: the position is closed at the entry bar's own close, the same "
            "day it was opened, so nothing is carried through the nightly session. It fills "
            "at the first reversal and is marked out at that day's closing price."),
        caveat=(
            "entry and exit both land on one daily bar, so the fill at the reversal and the "
            "fill at the close are assumed to be the same day's first and last prices"),
    ))

NEXT_OPEN = Rule4(
    token="open",
    label="next open",
    bar_exit=open_exit(),
    texts=dict(
        label="next open",
        rule4="exit = the open of the price bar that follows the entry bar",
        rule4_text=(
            "Close the position at <b>the open of the next price bar</b>, usually the "
            "following day. The trade is carried through one nightly session and no "
            "further. That open is the first price of the bar, so nothing can trade ahead "
            "of it and the exit is <b>unconditional</b>: there is no level to reach and no "
            "path to be ambiguous about. <b>The stop never trades</b>, it is here only to "
            "size the position, which means an adverse overnight gap takes the trade out "
            "for more than 1R."),
        lede=(
            "Holds through one night and no longer: the position is closed at the open of "
            "the price bar that follows the entry bar. That open is the first price of the "
            "day, so the exit is unconditional, and what the trade earns is exactly what "
            "the nightly session did to it."),
        caveat=(
            "the whole result is the overnight move, so it rests entirely on the next bar's "
            "open being a fillable price"),
    ))


# --- rules 1-3: identical in every strategy, written once --------------------------
# Written for someone who has never seen the method, and phrased for the SHORT side
# throughout, since the long side is its exact mirror (bearish ladder for entry, bullish
# for targets).
SHARED_RULES = [
    ("Signal",
     "At least <b>3 bullish reversal levels</b> lie between the previous day's close and "
     "today's high, price rose into them and tested them. The lowest of those is the "
     "<b>first</b> reversal, the next one up the <b>second</b>."),
    ("Clean setup",
     "Refuse the trade if the bar <b>opened at or above the second</b> reversal. Opening "
     "below the first, or between the first and the second, is fine; opening above the "
     "second means price was already inside the cluster when the day began."),
    ("Room to move",
     "The nearest <b>bearish</b> reversal below the entry must be at least <b>3.5R</b> "
     "below it. Any closer and there is not enough room to pay for the risk being taken."),
]

# Rules 1-4 say which setups qualify; this says how the trade is actually placed. A reader
# cannot size a trade or read an R multiple without it.
#
# A FUNCTION of the risk, not a constant: 1R is whatever percentage of capital is being
# risked, and that is a number the page can be re-dialled to. It said "1R = 1%" for as long
# as the risk happened to be 1%, which stopped being true the moment the default moved.
# (strategies.py imports nothing on purpose -- engine imports THIS module -- so the risk is
# passed in by the caller rather than read from engine.)
def entry_mechanics(risk_pct):
    return ("<b>Entry and stop.</b> The bar must <b>close below the first reversal</b>, "
            "the proof that price probed the cluster and snapped back. The trade "
            "fills at that reversal price, and the stop sits <b>one tick above that bar's "
            f"high</b>. Position size makes that distance exactly {risk_pct:g}% of capital, "
            f"so <b>1R = {risk_pct:g}%</b>. One position per market at a time; management "
            "starts the day after entry.")

# The correction that prompted this block: the umbrella method is "time and price meet", but
# THESE strategies use the price half alone. Saying otherwise misleads a first-time reader.
PRICE_ONLY_NOTE = (
    "Entries come from the <b>reversal levels only</b>. No timing, cycle or aggregate "
    "turning-point signal is involved, this is the price half of the Socrates method "
    "on its own."
)


class Strategy:
    """One strategy = one DEFAULT Rule 4 and its own default RISK, plus the name its outputs
    label themselves with.

    For a cap-family strategy the cap is a default, not a fixed property: every file on disk
    (workbooks, the charter hand-off, the JSON ledgers) is written at it and the pages open
    at it, but the reports carry the whole CAP_CHOICES grid and can be moved off it. A
    strategy whose Rule 4 is not in the family has nothing to move: its page shows that one
    setting, because that IS the strategy.

    `risk_pct` is the risk the strategy is published at, and `risk_solved` says where that
    number came from:

      True   it is MEASURED: the risk that puts THIS strategy at the project's drawdown
             budget (`engine.TARGET_DD`, 6%), solved by `solve_risk.py`. Quickfix. A drawdown
             budget is the thing the reader actually chooses, so publishing every page at
             its own 6% risk makes them comparable at equal PAIN rather than equal bet size.
             Re-solve it whenever the rules, the fill model or the data change and paste the
             number back here -- stale is the failure mode to watch for.
      False  it is CHOSEN: a plain 1% (user, 2026-07-28). The three quick-exit strategies are
             published this way. Their exits are so fast that the R scale stops meaning much,
             and quickfixclose barely draws down at all, so a 6%-drawdown solve would either
             not converge or hand back a bet size nobody would take. `solve_risk.py` still
             prints what the solve WOULD be for them, it just does not call them stale.

    Everything the outputs quote comes off the Rule 4 object, so nothing can go stale
    against it.
    """

    __slots__ = ("key", "title", "r4", "risk_pct", "risk_solved")

    def __init__(self, key, title, rule4, risk_pct, risk_solved=True):
        self.key = key          # file/CLI name: quickfix, quickfixwick, ...
        self.title = title      # display name on pages and sheets
        self.r4 = rule4         # this strategy's default Rule 4
        self.risk_pct = risk_pct  # % of liquid capital per trade
        self.risk_solved = risk_solved  # is risk_pct the solved TARGET_DD risk, or a choice?

    @property
    def token(self):
        """The key its backtest is filed under in the report's variant grid."""
        return self.r4.token

    @property
    def cap(self):
        """The default cap in R -- for a cap-family strategy only (else None; see Rule4)."""
        return self.r4.cap

    @property
    def rule4(self):
        return self.r4.texts["rule4"]

    @property
    def rule4_text(self):
        return self.r4.texts["rule4_text"]

    @property
    def lede(self):
        return self.r4.texts["lede"]

    @property
    def caveat(self):
        return self.r4.texts["caveat"]

    def rules(self):
        """The four numbered rules as (number, name, html) -- 1-3 shared, 4 this one's."""
        out = [(i + 1, name, text) for i, (name, text) in enumerate(SHARED_RULES)]
        out.append((4, "Target", self.rule4_text))
        return out

    def __repr__(self):
        return f"<Strategy {self.key} rule4={self.r4.token}>"


# --- the registry -------------------------------------------------------------------
# FOUR strategies, one per Rule 4 shape. They share Rules 1-3 exactly, so they take exactly
# the same setups, and comparing them compares nothing but where the profit is taken. That
# comparison is what `output/comparison.html` exists for.
#
# quickfix's `risk_pct` is MEASURED: the risk that puts it at engine.TARGET_DD (6%) maximum
# drawdown on the current data, printed by `solve_risk.py`. Re-run that script and paste the
# number back after any change to the rules, the fill model or the archive -- it moved when
# gap fills were added on 2026-07-27, and it will move again as the sample grows.
# engine.RISK_PCT (the reference the shared variant grid is priced at) tracks it.
#
# The other three are published at a flat 1%, CHOSEN not solved (user, 2026-07-28), which is
# what `risk_solved=False` records. See `Strategy` for why.
#
# quickfix's default cap was 5R until 2026-07-27, then 2.5R. It is 1.9R because that is where
# the reports' levered chart puts it: solve for the risk that holds every cap to the same 6%
# drawdown and 1.9R comes out top of the grid. The dial still reaches every other setting,
# and the charter hand-off still draws a few of them, so nothing has disappeared.
QUICKFIX = Strategy(key="quickfix", title="Quickfix", rule4=cap_rule4(1.9),
                    risk_pct=1.39)

# The three quick exits. Not caps: three different Rule 4 SHAPES, so none of them carries a
# cap dial or the "Choosing the profit cap" charts (in_grid=False on their Rule 4 objects).
#
# Quickfixwick carried a different key from 2026-07-27 to 2026-07-28, was retired, and came
# back under its present name on 2026-07-28 (user) because the name says what it does: it
# takes profit a tick past the entry bar's WICK. The rule itself is unchanged, and the old
# key was removed everywhere on the user's instruction -- it is in git; do not reinstate it.
QUICKFIXWICK = Strategy(key="quickfixwick", title="Quickfixwick", rule4=WICK,
                        risk_pct=1.0, risk_solved=False)
QUICKFIXCLOSE = Strategy(key="quickfixclose", title="Quickfixclose", rule4=DAY_CLOSE,
                         risk_pct=1.0, risk_solved=False)
QUICKFIXOPEN = Strategy(key="quickfixopen", title="Quickfixopen", rule4=NEXT_OPEN,
                        risk_pct=1.0, risk_solved=False)

# SLOWFIX -- the cap family at no cap -- was retired from the registry on 2026-07-28 (user):
# once every cap became reachable on one dial, a whole registered strategy for the uncapped
# end stopped earning its page. It was never a separate method, and nothing about it is lost:
# "no cap" is still a setting of the dial, still the dashed reference line on both charts,
# and still the worst point of the family at equal drawdown, which is the finding that made
# showing it in full redundant. Its outputs were deleted with it.
REGISTRY = [QUICKFIX, QUICKFIXWICK, QUICKFIXCLOSE, QUICKFIXOPEN]
BY_KEY = {s.key: s for s in REGISTRY}


def get(key):
    """Look up one strategy by key, with a helpful error listing the valid ones."""
    try:
        return BY_KEY[key]
    except KeyError:
        raise SystemExit(f"unknown strategy {key!r} -- known: "
                         + ", ".join(BY_KEY)) from None


def selected(argv):
    """Strategies named on the command line, or ALL of them when nothing is named.

    Every runner uses this, so `python run_all.py` regenerates everything while
    `python run_all.py quickfixwick` redoes just the one.
    """
    return [get(a) for a in argv] if argv else list(REGISTRY)
