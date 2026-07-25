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


class Strategy:
    """One strategy: its Rule 4 policy plus the text every output labels itself with."""

    __slots__ = ("key", "title", "rule4", "lede", "caveat", "target")

    def __init__(self, key, title, rule4, lede, caveat, target):
        self.key = key          # file/CLI name: quickfix, slowfix, ...
        self.title = title      # display name on pages and sheets
        self.rule4 = rule4      # one line: what Rule 4 does (goes into every meta block)
        self.lede = lede        # the paragraph under the page heading
        self.caveat = caveat    # the strategy-specific half of the page's honesty note
        self.target = target    # the Rule 4 policy function

    def __repr__(self):
        return f"<Strategy {self.key}>"


QUICKFIX = Strategy(
    key="quickfix",
    title="Quickfix",
    rule4="target = 5R, or an opposite reversal nearer than 5R",
    lede="Takes profit fast: a trade is closed at 5R, or earlier at the first opposite "
         "reversal that sits between entry and 5R. The 5R ceiling caps every winner.",
    caveat="a 5R target counts as hit whenever the day's range touches it",
    target=quickfix_target,
)

SLOWFIX = Strategy(
    key="slowfix",
    title="Slowfix",
    rule4="target = the first opposite reversal beyond entry, no 5R cap",
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
