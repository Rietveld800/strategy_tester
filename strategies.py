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
# --- Rule 4 comes in two SHAPES ----------------------------------------------------
# 1. THE CAP FAMILY (`target_policy`) -- ride to the first opposite reversal beyond entry,
#    but never past `cap` R. One policy with one number in it. Quickfix is that family at
#    2.5R, Slowfix at no cap; the reports carry the cap as a DIAL across the whole
#    CAP_CHOICES grid, so a page can be re-run at 4R, 6.75R or no cap at all.
#
#    The consequence, stated plainly: with the cap exposed, those two strategies are the
#    SAME strategy at two settings. Set quickfix to no cap and it IS slowfix; set slowfix to
#    2.5R and it IS quickfix, trade for trade. The registry keeps them as two entries
#    because those two settings are the two the research is about, not because the rules
#    underneath differ.
#
# 2. THE ENTRY BAR (`entry_bar_policy`) -- take profit one tick beyond the entry bar's own
#    opposite extreme, fixed at entry. Quickfixpro. This is a genuinely different shape, not
#    a setting of the cap: no reversal level and no R ceiling is involved, and the target
#    does not move once the trade is on. It therefore has NO cap dial -- there is no number
#    in it to dial -- and it is stored in the report's variant grid under its own token
#    rather than as a point on the cap axis.
#
# A `Rule4` (below) is one setting of one shape: its policy, the token its backtest is filed
# under, and every line of prose that quotes it. `Strategy` is a key, a title and one of
# these.
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
# It is called on EVERY bar the trade is open, never once at entry, so a cap-family target
# tracks the reversal ladder as Socrates redraws it: a newly appearing nearer reversal moves
# the target in, an elected one falls away. (An entry-bar target is fixed by construction --
# it is priced off the entry bar, which cannot change -- so calling it every bar returns the
# same number.) Returning None means no target is in force on this bar; only the stop can
# close the trade.
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


def entry_bar_policy():
    """Rule 4 for Quickfixpro: one tick beyond the ENTRY BAR's own opposite extreme.

    Short side (the long is the mirror): take profit one tick BELOW the entry bar's low.
    The trade is buying the initial energy of the move -- if the thesis that made us sell
    into the reversal cluster is right, that low should break more often than the high above
    it, which is where the stop sits. So the whole trade is contained by the entry bar: stop
    one tick above its high, target one tick below its low.

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


# --- Rule 4 as an object ------------------------------------------------------------
class Rule4:
    """ONE setting of Rule 4: its policy, the token its backtest is filed under, and every
    line of prose that quotes it.

    `in_grid` says whether this setting is a point on the report's CAP DIAL. The cap family
    is (every one of CAP_CHOICES is a real backtest the pages can move between); a Rule 4 of
    a different shape is not -- there is no number in it to dial, so its page carries no cap
    control and no "Choosing the profit cap" chart. `cap` is the number for the family and
    None otherwise; do not read it as "no cap" without checking `in_grid` first.
    """

    __slots__ = ("token", "label", "policy", "texts", "cap", "in_grid")

    def __init__(self, token, label, policy, texts, cap=None, in_grid=False):
        self.token = token      # key in _variants.json and in the pages' variant table
        self.label = label      # how the setting is written on a page: '2.5R', 'entry bar'
        self.policy = policy    # the Rule 4 itself
        self.texts = texts      # rule4 / rule4_text / lede / caveat / label
        self.cap = cap          # the cap in R, for the family only
        self.in_grid = in_grid  # is this a position on the report's cap dial?

    def __repr__(self):
        return f"<Rule4 {self.token}>"


def cap_rule4(cap):
    """The cap family at one cap -- a point on the reports' Rule 4 dial."""
    return Rule4(token=cap_token(cap), label=cap_label(cap), policy=target_policy(cap),
                 texts=cap_texts(cap), cap=cap, in_grid=True)


# Quickfixpro's Rule 4. Written out rather than generated, because it is not a setting of
# anything: there is no number in it. Phrased for the short side like every other rule text.
ENTRY_BAR = Rule4(
    token="bar",
    label="entry bar",
    policy=entry_bar_policy(),
    texts=dict(
        label="entry bar",
        rule4="target = one tick beyond the entry bar's own extreme (a short: below its low)",
        rule4_text=(
            "Take profit <b>one tick below the entry bar's own low</b>. The level is fixed "
            "the moment the trade is placed and never moves &mdash; no reversal level and no "
            "R ceiling is involved. The whole trade is contained by the entry bar: the stop "
            "one tick above its high, the target one tick below its low. This is a bet on "
            "the <b>initial energy</b> of the move &mdash; if the thesis behind the entry is "
            "right, that low should break more often than the high does. A winner is worth "
            "whatever the entry bar measured, which is usually well under 3.5R."),
        lede=(
            "Captures the initial energy move only: the target is fixed at entry, one tick "
            "beyond the entry bar's opposite extreme &mdash; a tick below its low on a short "
            "&mdash; and never moves. Stop and target are the two sides of the entry bar, so "
            "the bet is simply that its low breaks before its high."),
        caveat=(
            "the entry bar's low counts as broken whenever the day's range touches one tick "
            "below it"),
    ))


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
    """One strategy = one DEFAULT Rule 4 and its own default RISK, plus the name its outputs
    label themselves with.

    For a cap-family strategy the cap is a default, not a fixed property: every file on disk
    (workbooks, the charter hand-off, the JSON ledgers) is written at it and the pages open
    at it, but the reports carry the whole CAP_CHOICES grid and can be moved off it. A
    strategy whose Rule 4 is not in the family has nothing to move: its page shows that one
    setting, because that IS the strategy.

    `risk_pct` is the risk that puts THIS strategy at the project's drawdown budget
    (`engine.TARGET_DD`, 6%), solved by `solve_risk.py`. It is per strategy because a
    drawdown budget is the thing the reader actually chooses: opening every page at one bet
    size would show three different depths of hole and invite ranking them on return alone.
    Re-solve it whenever the rules, the fill model or the data change, and paste the number
    back here -- it is a measured constant, and stale is the failure mode to watch for.

    Everything the outputs quote comes off the Rule 4 object, so nothing can go stale
    against it.
    """

    __slots__ = ("key", "title", "r4", "risk_pct")

    def __init__(self, key, title, rule4, risk_pct):
        self.key = key          # file/CLI name: quickfix, slowfix, quickfixpro, ...
        self.title = title      # display name on pages and sheets
        self.r4 = rule4         # this strategy's default Rule 4
        self.risk_pct = risk_pct  # % of liquid capital per trade -> TARGET_DD max drawdown

    @property
    def token(self):
        """The key its backtest is filed under in the report's variant grid."""
        return self.r4.token

    @property
    def cap(self):
        """The default cap in R -- for a cap-family strategy only (else None; see Rule4)."""
        return self.r4.cap

    @property
    def target(self):
        """The Rule 4 policy this strategy's on-disk outputs are written at."""
        return self.r4.policy

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
# Every `risk_pct` below is MEASURED, not chosen: it is the risk that puts that strategy at
# engine.TARGET_DD (6%) maximum drawdown on the current data, printed by `solve_risk.py`.
# Re-run that script and paste the numbers back after any change to the rules, the fill
# model or the archive -- they moved when gap fills were added on 2026-07-27, and they will
# move again as the sample grows. engine.RISK_PCT (the reference the shared variant grid is
# priced at) tracks quickfix's number.
#
# quickfix's default cap was 5R until 2026-07-27. It is 2.5R because that is where the
# reports' levered chart puts it: solve for the risk that holds every cap to the same 6%
# drawdown and 2.5R comes out top of the grid, while 5R gives up about a tenth of the final
# capital for the same pain. The dial still reaches 5R, and the charter hand-off still draws
# it, so the old setting stays one click away rather than disappearing.
QUICKFIX = Strategy(key="quickfix", title="Quickfix", rule4=cap_rule4(2.5),
                    risk_pct=1.175)
SLOWFIX = Strategy(key="slowfix", title="Slowfix", rule4=cap_rule4(None),
                   risk_pct=0.396)
# Not a third cap: a different Rule 4 shape, so it carries no cap dial (see ENTRY_BAR).
QUICKFIXPRO = Strategy(key="quickfixpro", title="Quickfixpro", rule4=ENTRY_BAR,
                       risk_pct=0.8)

REGISTRY = [QUICKFIX, SLOWFIX, QUICKFIXPRO]
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
