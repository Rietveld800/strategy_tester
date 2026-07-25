# strategies.py
#
# The strategy registry. Every strategy shares the engine (engine.py) -- the same signal,
# the same clean-setup filter, the same stop, the same 3.5R reward filter and the same
# daily-proxy exit resolution -- and differs ONLY in Rule 4: which profit target is in
# force while the trade is open. That target is a function here.
#
# A strategy therefore takes EXACTLY THE SAME TRADES as every other one; they part company
# only in where those trades are closed. Comparing two strategies compares exits, nothing
# else.
#
# Adding a strategy: write its target policy, add a Strategy(...) below, append it to
# REGISTRY. Every runner (single-market ledger, per-market xlsx, portfolio, HTML page,
# charter hand-off) picks it up automatically -- including the page's navigation buttons.
#
# --- The target policy ------------------------------------------------------------
# Signature: policy(pos, bull, bear) -> (price_or_None, "target_5r" | "reversal")
#
#   pos    the open position: side, entry, stop, risk, target_5r (= entry -/+ 5R, the
#          reference distance the engine always computes, used or ignored per strategy).
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


def quickfix_target(pos, bull, bear):
    """Rule 4, quickfix: 5R, or an opposite reversal that sits CLOSER than 5R.

    The 5R level is a hard ceiling on the trade: if no reversal interrupts, the trade is
    taken off there. A reversal between entry and 5R is treated as the real obstacle and
    becomes the target instead, so the trade is closed where price is most likely to turn.
    """
    if pos["side"] == "short":
        below = [b for b in bear if pos["target_5r"] < b < pos["entry"]]
        if below:
            return max(below), "reversal"     # highest reversal above the 5R floor
        return pos["target_5r"], "target_5r"
    above = [b for b in bull if pos["entry"] < b < pos["target_5r"]]
    if above:
        return min(above), "reversal"         # lowest reversal below the 5R ceiling
    return pos["target_5r"], "target_5r"


def slowfix_target(pos, bull, bear):
    """Rule 4, slowfix: the FIRST opposite reversal beyond entry closes the trade. No 5R.

    There is no cap, so a level sitting 8R away is ridden to 8R -- that is the whole point
    of the strategy, and why it is 'slow' next to quickfix. Rule 3 still demands that the
    nearest opposite reversal be at least 3.5R away at entry, so a winner is at least 3.5R
    unless a nearer reversal appears later and pulls the target in.

    If no opposite reversal exists beyond entry (they were all elected), NO target is in
    force: the trade waits, holding, until one appears again. The stop stays in place the
    whole time, so a position can never be stranded forever.
    """
    if pos["side"] == "short":
        below = [b for b in bear if b < pos["entry"]]
        return (max(below), "reversal") if below else (None, "none")
    above = [b for b in bull if b > pos["entry"]]
    return (min(above), "reversal") if above else (None, "none")


# --- how the strategies read on a report ------------------------------------------
# Rules 1-3 are identical in every strategy, so they are written once here; Rule 4 is the
# per-strategy one and lives on the Strategy itself. Written for someone who has never seen
# the method, and phrased for the SHORT side throughout, since the long side is its exact
# mirror (bearish ladder for entry, bullish for targets).
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
ENTRY_MECHANICS = (
    "<b>Entry and stop.</b> The bar must <b>close below the first reversal</b> &mdash; the "
    "proof that price probed the cluster and snapped back. The trade fills at that reversal "
    "price, and the stop sits <b>one tick above that bar's high</b>. Position size makes "
    "that distance exactly 1% of capital, so <b>1R = 1%</b>. One position per market at a "
    "time; management starts the day after entry."
)

# The correction that prompted this block: the umbrella method is "time and price meet", but
# THESE strategies use the price half alone. Saying otherwise misleads a first-time reader.
PRICE_ONLY_NOTE = (
    "Entries come from the <b>reversal levels only</b>. No timing, cycle or aggregate "
    "turning-point signal is involved &mdash; this is the price half of the Socrates method "
    "on its own."
)


class Strategy:
    """One strategy: its Rule 4 policy plus the text every output labels itself with."""

    __slots__ = ("key", "title", "rule4", "rule4_text", "lede", "caveat", "target")

    def __init__(self, key, title, rule4, rule4_text, lede, caveat, target):
        self.key = key          # file/CLI name: quickfix, slowfix, ...
        self.title = title      # display name on pages and sheets
        self.rule4 = rule4      # one line: what Rule 4 does (goes into every meta block)
        self.rule4_text = rule4_text   # the full Rule 4 card on the report
        self.lede = lede        # the paragraph under the page heading
        self.caveat = caveat    # the strategy-specific half of the page's honesty note
        self.target = target    # the Rule 4 policy function

    def rules(self):
        """The four numbered rules as (number, name, html) -- 1-3 shared, 4 this strategy's."""
        out = [(i + 1, name, text) for i, (name, text) in enumerate(SHARED_RULES)]
        out.append((4, "Target", self.rule4_text))
        return out

    def __repr__(self):
        return f"<Strategy {self.key}>"


QUICKFIX = Strategy(
    key="quickfix",
    title="Quickfix",
    rule4="target = 5R, or an opposite reversal nearer than 5R",
    rule4_text="Take profit at <b>5R</b>. If a bearish reversal sits closer than 5R below "
               "the entry, that level becomes the target instead &mdash; price is likely to "
               "turn there rather than run through it. The target is recomputed every day, "
               "so a newly drawn level can pull it in. <b>5R is a hard ceiling on every "
               "winner.</b>",
    lede="Takes profit fast: a trade is closed at 5R, or earlier at the first opposite "
         "reversal that sits between entry and 5R. The 5R ceiling caps every winner.",
    caveat="a 5R target counts as hit whenever the day's range touches it",
    target=quickfix_target,
)

SLOWFIX = Strategy(
    key="slowfix",
    title="Slowfix",
    rule4="target = the first opposite reversal beyond entry, no 5R cap",
    rule4_text="Take profit at the <b>first bearish reversal below the entry</b>, however "
               "far away it is &mdash; there is <b>no 5R ceiling</b>, so a level sitting 8R "
               "away is ridden to 8R. Rule 3 already guarantees it is at least 3.5R away. "
               "If every level below has been elected, the trade simply waits, holding, "
               "until a new one appears; the stop stays in place throughout.",
    lede="Same entries as quickfix, held longer: there is no 5R ceiling, so a trade runs "
         "to the first opposite reversal beyond entry however far away that is. Rule 3 "
         "keeps that level at least 3.5R away at entry.",
    caveat="a reversal target counts as hit whenever the day's range touches it",
    target=slowfix_target,
)

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
