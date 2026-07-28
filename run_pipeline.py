# run_pipeline.py
#
# Regenerate EVERY output for every strategy in one go: the per-market xlsx, the shared
# account portfolio xlsx + equity JSON, the standalone HTML page, and the charter hand-off.
#
#   python run_pipeline.py            # every registered strategy
#   python run_pipeline.py quickfixwick   # just one
#
# This exists because reading the array archive is the slow part of every runner. The
# pipeline parses it ONCE (engine.run_markets) and feeds the same backtests to all four
# writers, so a full refresh costs one pass instead of four. Running the individual
# scripts still works and produces identical files -- this is only faster.

import sys

import build_equity_html
import engine as eng
import export_charter_trades
import run_all
import run_portfolio
import strategies


def main(argv):
    picked = strategies.selected(argv)
    print(f"strategies: {', '.join(s.key for s in picked)}\n")
    # The full cap grid: the pages carry a Rule 4 dial, and every position on it is a real
    # backtest. It rides along on the one archive pass, so it costs backtest time only.
    #
    # Plus anything the charter hand-off asks for that is NOT on that grid. The two lists are
    # independent by design -- CHARTER_CAPS is a chosen handful for the price charts, the grid
    # is the dial's axis -- and they stopped overlapping the moment the grid moved to tenth-R
    # steps (2.25R is on no grid this project draws). Without this the export dies on a
    # KeyError for a cap nobody backtested.
    caps = list(strategies.CAP_CHOICES)
    caps += [c for c in export_charter_trades.CHARTER_CAPS if c not in caps]
    results = eng.run_markets(picked, caps=caps)
    print()
    for s in picked:
        run_all.write(s, results)
        run_portfolio.run(s, results)
        print()
    # The charter hand-off is per OVERLAY -- a few caps plus the strategies that are not
    # caps at all (see export_charter_trades.py) -- so it is written once from the grid
    # rather than inside the per-strategy loop.
    hand_offs = export_charter_trades.hand_offs()
    for item in hand_offs:
        export_charter_trades.export(item, results)
    export_charter_trades.prune(hand_offs)
    print()
    run_portfolio.write_variants(results)
    print()
    # Built last, and always for EVERY strategy that has results: the pages read the shared
    # cap grid, so they must not be written before it exists.
    for s in picked:
        build_equity_html.build(s)
    build_equity_html.build_conclusions()
    # Always every strategy, even on a partial run: comparing a subset is not the comparison.
    build_equity_html.build_comparison()
    build_equity_html.build_report(
        [s for s in strategies.REGISTRY
         if (eng.OUT_DIR / f"_equity_{s.key}.json").exists()])


if __name__ == "__main__":
    main(sys.argv[1:])
