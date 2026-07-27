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
# --- Rule 4 is ONE family, parameterized by a cap ---------------------------------
# Rule 4 used to be a hand-written function per strategy. It is now a single policy with
# one number in it -- the profit CAP in R:
#
#     ride to the first opposite reversal beyond entry, but never past `cap` R.
#
#   quickfix = this policy at cap 5.0        slowfix = this policy at cap None (no ceiling)
#
# That is not a simplification imposed on the strategies, it is what they always were:
# quickfix's old "5R, or a nearer opposite reversal" and slowfix's "the first opposite
# reversal, no cap" are the same rule with and without a ceiling. Writing it once makes the
# cap a DIAL, which is the whole point -- the reports can re-run the backtest at 4R, 6.75R
# or no cap at all and show what changes.
#
# The consequence, stated plainly: with the cap exposed, the two strategies are the same
# strategy at two settings. Set quickfix to no cap and it IS slowfix; set slowfix to 5R and
# it IS quickfix, trade for trade. The registry keeps them as two entries because those two
# settings are the two the research is about, not because the rules underneath differ.
#
# --- The target policy ------------------------------------------------------------
# Signature: policy(pos, bull, bear) -> (price_or_None, "target_r" | "reversal" | "none")
#
#   pos    the open position: side, entry, stop, risk. The cap price is derived here from
#          `risk`, not stored on the position -- the cap is a property of the policy, and
#          the same position is replayed under many caps.
#   bull   bullish reversal levels known at the START of the bar being evaluated.
#   bear   bearish reversal levels known at the START of that bar.
#
# It is called on EVERY bar the trade is open, never once at entry, so the target tracks
# the reversal ladder as Socrates redraws it: a newly appearing nearer reversal moves the
# target in, an elected one falls away. Returning None means no target is in force on this
# bar -- only the stop can close the trade.
#
# Only OPPOSITE-side reversals may close a trade (bearish levels close a short, bullish
# levels close a long); a same-side level is never an exit.

# The caps the reports precompute, so the number can be moved without a rebuild: 2R to 10R
# in quarter-R steps, plus the uncapped setting. Every one of them is a full backtest --
# changing the cap changes the exits, and through "one position per market at a time" it
# changes which later signals are taken as well, so it cannot be replayed in the browser
# the way the risk percentage can.
CAP_MIN, CAP_MAX, CAP_STEP = 2.0, 10.0, 0.25
CAP_GRID = [round(CAP_MIN + i * CAP_STEP, 2)
            for i in range(int(round((CAP_MAX - CAP_MIN) / CAP_STEP)) + 1)]
# None = no ceiling, listed first because it is one end of the same scale.
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
                "far away it is &mdash; there is <b>no ceiling</b>, so a level sitting 8R "
                "away is ridden to 8R. Rule 3 already guarantees it is at least 3.5R away. "
                "If every level below has been elected, the trade simply waits, holding, "
                "until a new one appears; the stop stays in place throughout.")
    return (f"Take profit at <b>{cap:g}R</b>. If a bearish reversal sits closer than "
            f"{cap:g}R below the entry, that level becomes the target instead &mdash; price "
            f"is likely to turn there rather than run through it. The target is recomputed "
            f"every day, so a newly drawn level can pull it in. <b>{cap:g}R is a hard "
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


# --- rules 1-3: identical in every strategy, written once --------------------------
# Written for someone who has never seen the method, and phrased for the SHORT side
# throughout, since the long side is its exact mirror (bearish ladder for entry, bullish
# for targets).
SHARED_RULES = [
    ("Signal",
     "At least <b>3 bullish reversal levels</b> lie between the previous day's close and "
     "today's high &mdash; price rose into them and tested them. The lowest of those is the "
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
    return ("<b>Entry and stop.</b> The bar must <b>close below the first reversal</b> "
            "&mdash; the proof that price probed the cluster and snapped back. The trade "
            "fills at that reversal price, and the stop sits <b>one tick above that bar's "
            f"high</b>. Position size makes that distance exactly {risk_pct:g}% of capital, "
            f"so <b>1R = {risk_pct:g}%</b>. One position per market at a time; management "
            "starts the day after entry.")

# The correction that prompted this block: the umbrella method is "time and price meet", but
# THESE strategies use the price half alone. Saying otherwise misleads a first-time reader.
PRICE_ONLY_NOTE = (
    "Entries come from the <b>reversal levels only</b>. No timing, cycle or aggregate "
    "turning-point signal is involved &mdash; this is the price half of the Socrates method "
    "on its own."
)


class Strategy:
    """One strategy = one default cap, plus the name its outputs label themselves with.

    The cap is a DEFAULT, not a fixed property: every file on disk (workbooks, the charter
    hand-off, the JSON ledgers) is written at this cap, and the pages open at it, but the
    reports carry the whole CAP_CHOICES grid and can be moved off it. Everything derived
    from the cap -- the Rule 4 policy and every line of text that quotes the number -- is a
    property, so nothing can go stale against it.
    """

    __slots__ = ("key", "title", "cap")

    def __init__(self, key, title, cap):
        self.key = key          # file/CLI name: quickfix, slowfix, ...
        self.title = title      # display name on pages and sheets
        self.cap = cap          # default Rule 4 ceiling in R, or None for no ceiling

    @property
    def target(self):
        """The Rule 4 policy at this strategy's own cap."""
        return target_policy(self.cap)

    @property
    def rule4(self):
        return rule4_line(self.cap)

    @property
    def rule4_text(self):
        return rule4_text(self.cap)

    @property
    def lede(self):
        return lede_text(self.cap)

    @property
    def caveat(self):
        return caveat_text(self.cap)

    def rules(self):
        """The four numbered rules as (number, name, html) -- 1-3 shared, 4 this cap's."""
        out = [(i + 1, name, text) for i, (name, text) in enumerate(SHARED_RULES)]
        out.append((4, "Target", self.rule4_text))
        return out

    def __repr__(self):
        return f"<Strategy {self.key} cap={cap_token(self.cap)}>"


# quickfix's default cap was 5R until 2026-07-27. It is 2.5R because that is where the
# reports' levered chart puts it: solve for the risk that holds every cap to the same 6%
# drawdown and 2.5R comes out top of the grid, while 5R gives up about a tenth of the final
# capital for the same pain. engine.RISK_PCT is set to the risk that setting needs. The dial
# still reaches 5R, and the charter hand-off still draws it, so the old setting stays one
# click away rather than disappearing.
QUICKFIX = Strategy(key="quickfix", title="Quickfix", cap=2.5)
SLOWFIX = Strategy(key="slowfix", title="Slowfix", cap=None)

REGISTRY = [QUICKFIX, SLOWFIX]
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
    `python run_all.py slowfix` redoes just the one.
    """
    return [get(a) for a in argv] if argv else list(REGISTRY)
