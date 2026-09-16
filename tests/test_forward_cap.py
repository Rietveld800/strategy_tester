"""The forward window's cap (forward_window.py) and the guards around it.

The cap holds every strategy-performance output to the day before rung 6's window
opens. Two things could bypass it: a caller passing the tripwire's keyword, and the
matrix reusing a cache that carries a trade past the cap. Both are guarded here,
and the scan is RECURSIVE over the whole research tree, so a future script in any
subfolder is seen. The tests directory is excluded deliberately (this file names
the keyword), as are the environment and cache folders.
"""

import io
import json
import sys
import tokenize
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import forward_window as fw

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {"tests", "venv", ".venv", "__pycache__", ".git", "output"}
KEYWORD = "uncapped=True"


def _code_only(text: str) -> str:
    """Source with every string literal and comment removed, so the scan reads code.

    GUARD FIX, 2026-09-16 (Lode). The first version stripped docstrings with the
    regex \"\"\"[^"]*\"\"\", which ends at the first double quote INSIDE a docstring, so a
    docstring holding a quoted phrase was partly scanned as code. That failed closed
    on the day it was found (a docstring's own mention of the keyword counted as a
    caller) and could fail OPEN: a real caller placed after a quoted phrase inside a
    docstring would have been eaten with the rest of the docstring and never seen.
    The tokenizer knows where every string ends, both quote styles, nested quotes
    and all; STRING and COMMENT tokens are dropped and the rest is joined. A file
    the tokenizer cannot read is returned whole, so the scan fails closed on it."""
    lines = text.splitlines(keepends=True)
    try:
        spans = [(tok.start, tok.end)
                 for tok in tokenize.generate_tokens(io.StringIO(text).readline)
                 if tok.type in (tokenize.STRING, tokenize.COMMENT)]
    except (tokenize.TokenError, SyntaxError):
        return text
    # Blank each span IN PLACE (rows are 1-based), so the code around it keeps
    # its exact text - `uncapped=True` must still read `uncapped=True`.
    for (r0, c0), (r1, c1) in spans:
        for r in range(r0, r1 + 1):
            line = lines[r - 1]
            a = c0 if r == r0 else 0
            b = c1 if r == r1 else len(line.rstrip())
            lines[r - 1] = line[:a] + " " * (b - a) + line[b:]
    return "".join(lines)


def test_the_cap_holds_every_output_to_the_day_before_the_window(tmp_path):
    window = tmp_path / "forward_window.json"
    window.write_text(json.dumps(dict(opens_on="2026-09-15")))
    days = [date(2026, 9, 10 + i) for i in range(10)]           # 09-10 .. 09-19
    assert fw.cap_day(window) == date(2026, 9, 14)
    assert fw.capped(days, path=window)[-1] == date(2026, 9, 14)
    assert fw.capped(days, path=window, uncapped=True)[-1] == date(2026, 9, 19)
    window.write_text(json.dumps(dict(opens_on=None)))
    assert fw.cap_day(window) is None and len(fw.capped(days, path=window)) == 10


def test_the_lift_by_ruling_removes_the_cap_for_every_consumer(tmp_path):
    """Lode's ruling of 2026-09-16 (ENGINE_ARCHITECTURE.md Phase 2, LATER RULING;
    pre-registered 3e77331): with `cap_lifted_on` set, cap_day is None and capped
    returns every day, uncapped or not; the opening date is untouched."""
    window = tmp_path / "forward_window.json"
    window.write_text(json.dumps(dict(opens_on="2026-09-15", cap_lifted_on="2026-09-16")))
    days = [date(2026, 9, 10 + i) for i in range(10)]           # 09-10 .. 09-19
    assert fw.cap_lifted_on(window) == date(2026, 9, 16)
    assert fw.cap_day(window) is None
    assert fw.capped(days, path=window) == days
    assert fw.capped(days, path=window, uncapped=True) == days
    assert fw.opens_on(window) == date(2026, 9, 15)


def test_without_the_lift_field_the_cap_still_holds(tmp_path):
    """The plant: the same file with the field absent, empty or null caps at the
    day before the window opens, exactly as before the ruling."""
    window = tmp_path / "forward_window.json"
    days = [date(2026, 9, 10 + i) for i in range(10)]
    for variant in (dict(opens_on="2026-09-15"),
                    dict(opens_on="2026-09-15", cap_lifted_on=None),
                    dict(opens_on="2026-09-15", cap_lifted_on="")):
        window.write_text(json.dumps(variant))
        assert fw.cap_lifted_on(window) is None
        assert fw.cap_day(window) == date(2026, 9, 14)
        assert fw.capped(days, path=window)[-1] == date(2026, 9, 14)


def test_a_quoted_phrase_inside_a_docstring_neither_hides_nor_invents_a_caller(tmp_path):
    """Both directions of the guard fix of 2026-09-16. A docstring that quotes a
    phrase and then names the keyword scans CLEAN (no false caller); the same file
    with a real caller placed after that docstring is FOUND (the docstring's inner
    quote must not swallow the code that follows it). Both quote styles."""
    for q in ('"""', "'''"):
        doc = (f"{q}The ruling is {chr(34)}LATER RULING, 2026-09-16{chr(34)} and the "
               f"phrase uncapped=True appears here in prose only.{q}\n")
        clean = tmp_path / f"clean_{len(q)}{ord(q[0])}.py"
        clean.write_text(doc + "x = 1\n", encoding="utf-8")
        assert KEYWORD not in _code_only(clean.read_text(encoding="utf-8")), q
        bypass = tmp_path / f"bypass_{ord(q[0])}.py"
        bypass.write_text(doc + "x = run_market(key, uncapped=True)\n", encoding="utf-8")
        assert _code_only(bypass.read_text(encoding="utf-8")).count(KEYWORD) == 1, q
    # And an ordinary string literal on a code line is not code either.
    s = tmp_path / "string.py"
    s.write_text("label = \"uncapped=True\"\n", encoding="utf-8")
    assert KEYWORD not in _code_only(s.read_text(encoding="utf-8"))


def test_the_tripwire_is_the_only_caller_past_the_cap_anywhere_in_the_tree():
    """Recursive. The keyword may appear in the tripwire's one call and nowhere
    else in code; forward_window.py defines the parameter and does not pass it.
    Since the lift of 2026-09-16 this guards STRUCTURE, not behaviour: with the
    cap lifted the keyword changes nothing, and the test keeps the one caller
    named for the day a future pre-registered window caps again."""
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
