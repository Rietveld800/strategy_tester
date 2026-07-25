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
    results = eng.run_markets(picked)
    print()
    for s in picked:
        run_all.write(s, results)
        run_portfolio.run(s, results)
        export_charter_trades.export(s, results)
        build_equity_html.build(s)
        print()


if __name__ == "__main__":
    main(sys.argv[1:])
