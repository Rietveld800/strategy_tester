"""Execution costs per contract per side -- documented and sourced.

THE COST OF OPENING AND CLOSING A POSITION (Lode, 2026-09-01: "the
next concern is the actual cost of executing ... these costs should be
documented and sourced well and should become part of final equity
curve. Let's keep taxes out of the equation at all times"). This
module is the ONE place that cost lives; the quantized replay layers
(research_1m_sizing, build_1m_report --contracts) subtract it per
contract per side. The fractional pages stay the research currency and
carry slippage only -- slippage models the FILL, this models the BILL,
and the two never overlap: slippage is already charged in R by the
engine, commissions are charged in dollars here.

Model: cost per side = broker commission + exchange fee + NFA fee, all
per contract. A round turn costs two sides. Taxes are excluded by
decision and stay excluded.

SOURCES (retrieved 2026-09-01):
- IBKR worked examples (primary, from interactivebrokers.com pricing):
  1 ES contract = $0.85 execution + $1.38 exchange = $2.24 per side;
  1 Eurex contract = EUR 0.90 execution + EUR 0.52 exchange = EUR 1.42
  per side. IBKR fixed-rate US futures execution is $0.85 per
  contract, micros $0.25 (interactivebrokers.com/en/pricing/
  commissions-futures.php; the site blocks automated retrieval, the
  examples were confirmed through its indexed copy).
- TradeStation exchange/clearing fee list (secondary):
  tradestation.com/pricing/exchange-execution-and-clearing-fees/
- Trade Pro Futures exchange fee list (secondary):
  tradeprofutures.com/trader-tools/exchangefees/
- CME's authoritative Non-Member Fee Finder
  (cmegroup.com/company/clearing-fees/fee-finder.html) and the fee
  schedule PDFs could not be retrieved by tooling (403/timeouts); the
  two broker lists are pass-through renderings of those schedules.

WHERE THE TWO SECONDARY SOURCES DISAGREE the HIGHER figure is adopted
(a cost model errs expensive, a wrong cheap model flatters the curve)
and both readings are recorded on the row. Rows marked
confidence="low" have one weak source; rows with exchange_fee=None
have NO source and are never silently priced -- cost_per_side raises
on them. THE STANDING INSTRUCTION: when the IB account exists, replace
this table with the fee lines of real IB statements, row by row, and
raise the confidence as each row is confirmed. Until then this is the
best documented estimate, not a measurement.

Every figure is per contract PER SIDE. NFA regulatory fee: $0.02 per
contract per side (Trade Pro Futures; TradeStation prints $0.01 --
higher adopted). Eurex has no NFA fee.
"""

NFA_PER_SIDE_USD = 0.02

# Full-size futures, keyed by the engine's market key.
# exchange_fee per side; commission is IBKR fixed-rate execution.
FUTURES = {
    "GC": dict(exchange_fee=1.65, commission=0.85, currency="USD",
               confidence="medium",
               note="TradeStation 1.65; TradeProFutures 1.55"),
    "SI": dict(exchange_fee=1.65, commission=0.85, currency="USD",
               confidence="medium",
               note="TradeStation 1.65; TradeProFutures 1.55"),
    "HG": dict(exchange_fee=1.60, commission=0.85, currency="USD",
               confidence="medium",
               note="TradeStation 1.60; TradeProFutures 1.55"),
    "PL": dict(exchange_fee=1.65, commission=0.85, currency="USD",
               confidence="medium",
               note="TradeStation 1.65; TradeProFutures 1.55"),
    "PA": dict(exchange_fee=1.60, commission=0.85, currency="USD",
               confidence="medium",
               note="TradeStation 1.60; TradeProFutures 1.55"),
    "CL": dict(exchange_fee=1.50, commission=0.85, currency="USD",
               confidence="medium", note="TradeStation"),
    "NG": dict(exchange_fee=1.60, commission=0.85, currency="USD",
               confidence="medium", note="TradeStation"),
    "ES": dict(exchange_fee=1.38, commission=0.85, currency="USD",
               confidence="high",
               note="IBKR's own worked example ($2.24 all-in);"
                    " both broker lists agree"),
    "NQ": dict(exchange_fee=1.38, commission=0.85, currency="USD",
               confidence="high", note="both broker lists agree"),
    "YM": dict(exchange_fee=1.38, commission=0.85, currency="USD",
               confidence="high", note="both broker lists agree"),
    "ZW": dict(exchange_fee=2.10, commission=0.85, currency="USD",
               confidence="medium", note="TradeProFutures"),
    "ZC": dict(exchange_fee=2.10, commission=0.85, currency="USD",
               confidence="medium", note="TradeProFutures"),
    "ZN": dict(exchange_fee=0.80, commission=0.85, currency="USD",
               confidence="high", note="both broker lists agree"),
    "ZB": dict(exchange_fee=0.87, commission=0.85, currency="USD",
               confidence="medium",
               note="TradeStation 0.87; TradeProFutures 0.80"),
    "6E": dict(exchange_fee=1.60, commission=0.85, currency="USD",
               confidence="medium", note="TradeProFutures"),
    "6J": dict(exchange_fee=1.60, commission=0.85, currency="USD",
               confidence="medium", note="TradeProFutures"),
    "LE": dict(exchange_fee=2.10, commission=0.85, currency="USD",
               confidence="high", note="both broker lists agree"),
    "SR3": dict(exchange_fee=1.25, commission=0.85, currency="USD",
                confidence="high", note="both broker lists agree"),
    "BTC": dict(exchange_fee=7.50, commission=0.85, currency="USD",
                confidence="low",
                note="TradeStation 7.50; TradeProFutures 5.00 --"
                     " large divergence, verify before trading BTC"),
    "SB": dict(exchange_fee=2.10, commission=0.85, currency="USD",
               confidence="high", note="both broker lists agree"),
    "DX": dict(exchange_fee=1.35, commission=0.85, currency="USD",
               confidence="high", note="both broker lists agree"),
    # FGBL uses IBKR's own Eurex example: EUR 0.90 execution + EUR
    # 0.52 exchange per side (the broker lists' EUR 0.20-0.22 is the
    # Eurex fee component alone, without clearing). No NFA fee.
    "FGBL": dict(exchange_fee=0.52, commission=0.90, currency="EUR",
                 confidence="high", nfa=0.0,
                 note="IBKR's own Eurex worked example (EUR 1.42"
                      " all-in per side)"),
    # CC and KC are obsolete markets (historical trades only); ICE
    # softs fees assumed at SB's rate, flagged accordingly.
    "CC": dict(exchange_fee=2.10, commission=0.85, currency="USD",
               confidence="low",
               note="assumed at SB's ICE rate; obsolete market,"
                    " historical replay only"),
    "KC": dict(exchange_fee=2.10, commission=0.85, currency="USD",
               confidence="low",
               note="assumed at SB's ICE rate; obsolete market,"
                    " historical replay only"),
}

# Micro/mini roots (for the micro study; nothing routes to them yet).
# commission is IBKR's micro rate ($0.25) where the root is a CME
# micro; the half-size minis take the full $0.85.
MICROS = {
    "MGC": dict(exchange_fee=1.10, commission=0.25, currency="USD",
                confidence="low",
                note="TradeStation 1.10; TradeProFutures 0.50 --"
                     " large divergence"),
    "SIL": dict(exchange_fee=1.00, commission=0.25, currency="USD",
                confidence="low", note="TradeStation"),
    "MHG": dict(exchange_fee=0.70, commission=0.25, currency="USD",
                confidence="low",
                note="TradeStation 0.70; TradeProFutures 0.60"),
    "MCL": dict(exchange_fee=0.50, commission=0.25, currency="USD",
                confidence="medium", note="both broker lists agree"),
    "QG": dict(exchange_fee=0.50, commission=0.85, currency="USD",
               confidence="low", note="TradeProFutures only"),
    "QM": dict(exchange_fee=1.20, commission=0.85, currency="USD",
               confidence="low", note="TradeStation only"),
    "MES": dict(exchange_fee=0.35, commission=0.25, currency="USD",
                confidence="high", note="both broker lists agree"),
    "MNQ": dict(exchange_fee=0.35, commission=0.25, currency="USD",
                confidence="high", note="both broker lists agree"),
    "MYM": dict(exchange_fee=0.35, commission=0.25, currency="USD",
                confidence="high", note="both broker lists agree"),
    "M6E": dict(exchange_fee=0.24, commission=0.25, currency="USD",
                confidence="medium", note="both broker lists agree"),
    "MBT": dict(exchange_fee=2.50, commission=0.25, currency="USD",
                confidence="low",
                note="TradeProFutures 2.50; TradeStation 1.15 --"
                     " large divergence"),
    "XW": dict(exchange_fee=1.03, commission=0.85, currency="USD",
               confidence="low", note="TradeProFutures only"),
    "XC": dict(exchange_fee=1.03, commission=0.85, currency="USD",
               confidence="low", note="TradeProFutures only"),
    # NO SOURCE found for these; never priced silently.
    "MJY": dict(exchange_fee=None, commission=0.25, currency="USD",
                confidence="none", note="no source found; verify at IB"),
    "MZW": dict(exchange_fee=None, commission=0.25, currency="USD",
                confidence="none", note="no source found; verify at IB"),
    "MZC": dict(exchange_fee=None, commission=0.25, currency="USD",
                confidence="none", note="no source found; verify at IB"),
    "MNG": dict(exchange_fee=None, commission=0.25, currency="USD",
                confidence="none", note="no source found; verify at IB"),
    "1OZ": dict(exchange_fee=None, commission=0.25, currency="USD",
                confidence="none", note="no source found; verify at IB"),
}

# ETFs: IBKR fixed-rate US stocks, $0.005 per share, minimum $1.00 per
# order (maximum 1% of trade value -- not modelled, irrelevant at our
# prices). Flagged medium: the rate is IBKR's published fixed tier but
# was not re-retrieved today. Regulatory sell-side fees (SEC/TAF,
# fractions of a cent per share) are omitted as sub-dollar noise.
ETF_PER_SHARE_USD = 0.005
ETF_MIN_PER_ORDER_USD = 1.00


def cost_per_side(key, n, is_etf=False, eurusd=1.0):
    """USD cost of one SIDE of a position of n contracts (or shares).

    `eurusd` converts a EUR-denominated row (FGBL); pass the same
    research-grade rate the sizing layer uses. Raises on a row with no
    sourced exchange fee rather than pricing it silently.
    """
    if is_etf:
        return max(ETF_MIN_PER_ORDER_USD, ETF_PER_SHARE_USD * n)
    row = FUTURES.get(key) or MICROS.get(key)
    if row is None:
        raise KeyError(f"no execution-cost row for {key}")
    if row["exchange_fee"] is None:
        raise ValueError(f"{key}: exchange fee has no source; refuse to"
                         f" price it (see execution_costs.py)")
    per = row["commission"] + row["exchange_fee"] + \
        row.get("nfa", NFA_PER_SIDE_USD)
    if row["currency"] == "EUR":
        per *= eurusd
    return per * n


def round_turn(key, n, is_etf=False, eurusd=1.0):
    """USD cost of opening AND closing n contracts."""
    return 2.0 * cost_per_side(key, n, is_etf=is_etf, eurusd=eurusd)
