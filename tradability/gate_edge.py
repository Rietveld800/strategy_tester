"""Section 4a's gate: our EDGE against the authors' published values.

`live_engine/FILL_CALIBRATION.md` section 4a, ruled by Lode on 2026-09-11:

    1. Reproduce the published reference on its own published input.
    2. State the agreement - the numbers, the input, and the tolerance - in that
       file, as a dated entry. Not "it matched": the figures.
    3. Only then compute anything else.

    If EDGE disagrees, STOP.

This prints the figures step 2 needs and exits non-zero on any disagreement, so a
caller cannot mistake a failure for a pass. It computes no other metric and touches
no fill model; the harness proper does not exist yet and must not until this passes.

THE EXPECTED VALUES ARE THE AUTHORS', TRANSCRIBED FROM THE SAVED README and not
from memory: `reference/PSEUDOCODE_README.md`, saved beside the two data files it
names. Transcribing them into this file is itself a place an error can enter, which
is why the README is saved rather than linked - the transcription can be checked
against the file next to it.
"""

import csv
import sys
from pathlib import Path

from edge import edge

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / "reference"

#: The authors' published expectations, per input file. Every figure is from
#: `reference/PSEUDOCODE_README.md`, section "Testing".
EXPECTED = {
    "ohlc.csv": dict(
        spread=0.0101849034905478,
        pt=0.9820982098209821,
        po=1.227922792279228,
        pc=1.2052205220522052,
        e1=0.00010702425689560482,
        e2=0.000101595812797079,
        v1=2.074215642985551e-06,
        v2=1.3461279919743572e-06,
        s2=0.00010373225911177194,
    ),
    "ohlc-miss.csv": dict(
        spread=0.01013284969780197,
        pt=0.9822078447230085,
        po=1.2272254421162134,
        pc=1.205827632480371,
        e1=0.00010337780767834583,
        e2=0.00010219271972776808,
        v1=2.0045420261850617e-06,
        v2=1.373839551967266e-06,
        s2=0.00010267464299824543,
    ),
}

#: PROPOSED, and not yet the record: relative agreement to 1e-12. The published
#: values carry ~16 significant digits and no two float implementations agree to
#: the last bit, so a tolerance is a decision and not a fact - section 4a step 2
#: requires it stated, and Lode approves the figure before it is the record.
#: 1e-12 is proposed because it is ~4 orders looser than double precision's ~1e-16
#: and ~10 orders tighter than any difference that could hide an algorithmic error:
#: a wrong mean, a missed nan or a transposed term moves these numbers in the
#: third significant digit or worse, never in the thirteenth.
PROPOSED_RTOL = 1e-12


def read_ohlc(path: Path):
    """The four columns as lists of float, an empty field becoming nan.

    `csv` rather than pandas deliberately: the file is the fixture and this reads
    it as it stands, with no type inference, no na_values list and nothing else
    between the published bytes and the estimator.
    """
    cols = {"Open": [], "High": [], "Low": [], "Close": []}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            for name in cols:
                raw = (row.get(name) or "").strip()
                cols[name].append(float(raw) if raw not in ("", "NA", "NaN", "nan") else float("nan"))
    return cols["Open"], cols["High"], cols["Low"], cols["Close"]


def check(filename: str, rtol: float) -> bool:
    path = REFERENCE / filename
    o, h, l, c = read_ohlc(path)
    got = edge(o, h, l, c)
    want = EXPECTED[filename]

    print(f"\n=== {filename} ===")
    print(f"input: {path}")
    print(f"rows: {got.nobs}")
    print(f"{'field':8} {'ours':>26} {'published':>26} {'rel diff':>12}  verdict")

    ok = True
    fields = [("spread", got.spread)] + list(got.published_fields().items())
    for name, ours in fields:
        theirs = want[name]
        rel = abs(ours - theirs) / abs(theirs) if theirs != 0 else abs(ours - theirs)
        agrees = rel <= rtol
        ok = ok and agrees
        print(f"{name:8} {ours:>26.18g} {theirs:>26.18g} {rel:>12.2e}  "
              f"{'agree' if agrees else 'DISAGREE'}")
    return ok


def main(argv=None) -> int:
    rtol = PROPOSED_RTOL
    print("FILL_CALIBRATION.md section 4a, step 1: the EDGE positive control")
    print(f"proposed relative tolerance: {rtol:g} (NOT yet approved; section 4a step 2)")
    results = {name: check(name, rtol) for name in EXPECTED}
    print()
    if all(results.values()):
        print("GATE PASSED on both published inputs. Step 2 next: the dated entry, "
              "with these figures, approved by Lode before it is the record.")
        return 0
    failed = [n for n, ok in results.items() if not ok]
    print(f"GATE FAILED on: {failed}")
    print("STOP. Section 4a: the harness is wrong and the other four metrics are "
          "not to be trusted from the same code. Compute nothing else.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
