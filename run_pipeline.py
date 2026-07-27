# run_pipeline.py
#
# Regenerate EVERY output for every strategy in one go: the per-market xlsx, the shared
# account portfolio xlsx + equity JSON, the standalone HTML page, and the charter hand-off.
#
#   python run_pipeline.py            # every registered strategy
#   python run_pipeline.py slowfix    # just one
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
    results = eng.run_markets(picked)
    print()
    for s in picked:
        run_all.write(s, results)
        run_portfolio.run(s, results)
        export_charter_trades.export(s, results)
        print()
    run_portfolio.write_variants(results)
    print()
    # Built last, and always for EVERY strategy that has results: the pages read the shared
    # cap grid, so they must not be written before it exists.
    for s in picked:
        build_equity_html.build(s)
    build_equity_html.build_conclusions()
    build_equity_html.build_report(
        [s for s in strategies.REGISTRY
         if (eng.OUT_DIR / f"_equity_{s.key}.json").exists()])


if __name__ == "__main__":
    main(sys.argv[1:])
