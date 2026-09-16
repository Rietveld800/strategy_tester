"""The forward window's cap on every strategy-performance output (live_engine,
ENGINE_ARCHITECTURE.md, Phase 2, 2026-09-08).

From the day rung 6's forward window opens, no research page may show forward
trades, equity or drawdown - not the matrix, not the variant reports, not the
contracts or capitals pages, not a research script's console. The pre-registration
file `forward_window.json` carries the opening date, and this module turns it into
one cap that every consumer of bars applies by default: **the last allowed day is
the day before the window opens**. Raw prices are exempt (the charter's price
charts read bars directly and show no strategy); the tripwire is the ONLY consumer
allowed past the cap, and it says so by name when it asks.

While the window is closed (no opening date) there is no cap and nothing changes.

THE CAP WAS LIFTED BY RULING (Lode, 2026-09-16; ENGINE_ARCHITECTURE.md Phase 2,
"LATER RULING, 2026-09-16", commit b5a44d4; the code step pre-registered in 3e77331).
The lift is one dated field in the same file, `cap_lifted_on`: while it is set,
`cap_day` is None and every consumer shows every day. The mechanism stays, so a
future pre-registered window can cap again by removing the field or writing a new
file. `uncapped=True` keeps its meaning as the name of the one consumer that must
never be capped, whatever the file says.
"""

import json
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
WINDOW_FILE = HERE / "forward_window.json"


def opens_on(path=None):
    """The window's opening date, or None while it is closed."""
    path = path or WINDOW_FILE
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8")).get("opens_on")
    return None if raw in (None, "") else date.fromisoformat(raw)


def cap_lifted_on(path=None):
    """The date the display cap was lifted by ruling, or None while it holds."""
    path = path or WINDOW_FILE
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8")).get("cap_lifted_on")
    return None if raw in (None, "") else date.fromisoformat(raw)


def cap_day(path=None):
    """The last day a strategy-performance output may include, or None for no cap.

    None while the window is closed, and None once the cap is lifted by ruling
    (`cap_lifted_on` set); otherwise the day before the window opens."""
    if cap_lifted_on(path) is not None:
        return None
    day = opens_on(path)
    return None if day is None else day - timedelta(days=1)


def capped(days, *, uncapped=False, path=None):
    """`days` (objects with a `.date`, or dates) up to and including the cap.

    `uncapped=True` is the tripwire's word; nothing else passes it.
    """
    if uncapped:
        return list(days)
    cap = cap_day(path)
    if cap is None:
        return list(days)
    return [d for d in days if (d.date if hasattr(d, "date") and not isinstance(d, date) else d) <= cap]
