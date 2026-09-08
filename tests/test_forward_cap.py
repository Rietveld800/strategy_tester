"""The forward window's cap (forward_window.py) and the guards around it.

The cap holds every strategy-performance output to the day before rung 6's window
opens. Two things could bypass it: a caller passing the tripwire's keyword, and the
matrix reusing a cache that carries a trade past the cap. Both are guarded here,
and the scan is RECURSIVE over the whole research tree, so a future script in any
subfolder is seen. The tests directory is excluded deliberately (this file names
the keyword), as are the environment and cache folders.
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import forward_window as fw

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {"tests", "venv", ".venv", "__pycache__", ".git", "output"}
KEYWORD = "uncapped=True"


def _code_only(text: str) -> str:
    """Source with docstrings and comments removed, so the scan reads code."""
    without_docstrings = re.sub('"""[^"]*"""', "", text)
    return "\n".join(line.split("#", 1)[0] for line in without_docstrings.splitlines())


def test_the_cap_holds_every_output_to_the_day_before_the_window(tmp_path):
    window = tmp_path / "forward_window.json"
    window.write_text(json.dumps(dict(opens_on="2026-09-15")))
    days = [date(2026, 9, 10 + i) for i in range(10)]           # 09-10 .. 09-19
    assert fw.cap_day(window) == date(2026, 9, 14)
    assert fw.capped(days, path=window)[-1] == date(2026, 9, 14)
    assert fw.capped(days, path=window, uncapped=True)[-1] == date(2026, 9, 19)
    window.write_text(json.dumps(dict(opens_on=None)))
    assert fw.cap_day(window) is None and len(fw.capped(days, path=window)) == 10


def test_the_tripwire_is_the_only_caller_past_the_cap_anywhere_in_the_tree():
    """Recursive. The keyword may appear in the tripwire's one call and nowhere
    else in code; forward_window.py defines the parameter and does not pass it."""
    hits = {}
    for path in ROOT.rglob("*.py"):
        if EXCLUDED_DIRS & set(path.relative_to(ROOT).parts[:-1]):
            continue
        code = _code_only(path.read_text(encoding="utf-8", errors="replace"))
        count = code.count(KEYWORD)
        if count:
            hits[str(path.relative_to(ROOT))] = count
    assert hits == {"forward_tripwire.py": 1}, hits


def test_the_scan_can_actually_see_a_bypass(tmp_path):
    """The guard's own guard (TESTING.md): the same scan over a tree holding a
    bypass must report it, or the test above proves nothing."""
    bad = tmp_path / "some" / "deep" / "script.py"
    bad.parent.mkdir(parents=True)
    bad.write_text("x = run_market(key, uncapped=True)\n", encoding="utf-8")
    hits = [p for p in tmp_path.rglob("*.py")
            if KEYWORD in _code_only(p.read_text(encoding="utf-8"))]
    assert hits == [bad]
    commented = tmp_path / "commented.py"
    commented.write_text("# uncapped=True is mentioned here only\n", encoding="utf-8")
    assert KEYWORD not in _code_only(commented.read_text(encoding="utf-8"))


def test_the_matrix_discards_a_cache_holding_a_trade_past_the_cap(tmp_path, monkeypatch):
    import run_1m_matrix as m
    cache = tmp_path / "cache.json"
    monkeypatch.setattr(m, "CACHE_PATH", cache)
    monkeypatch.setattr(fw, "WINDOW_FILE", tmp_path / "forward_window.json")
    (tmp_path / "forward_window.json").write_text(json.dumps(dict(opens_on="2026-09-15")))
    entry = dict(manifest={}, excluded=None, calendar=[], note="", tick=0.1,
                 cells={"variant_04": dict(trades=[dict(entry_date="2026-09-16")],
                                           geom_days=[], open_position=None)})
    cache.write_text(json.dumps(dict(sig="s", markets={"GC": entry})), encoding="utf-8")
    assert m.load_matrix_cache("s") == {}, "a trade past the cap discards the cache"
    entry["cells"]["variant_04"]["trades"] = [dict(entry_date="2026-09-14")]
    cache.write_text(json.dumps(dict(sig="s", markets={"GC": entry})), encoding="utf-8")
    assert "GC" in m.load_matrix_cache("s"), "a cache within the cap is reused"
