"""The capital ladder: one deployment report across five account sizes.

Lode, 2026-09-01: the published baseline traded in INTEGER CONTRACTS
under the refusal policy at $100k, $250k, $500k, $1M and $2M starting
capital, each section in the variant-report format -- equity, drawdown
and open-positions panes, the refused orders, and the full blotter with
the contracts taken, the ACTUAL risk each position realized and the
detailed execution cost per trade. The page opens with the contract
arsenal (every market's front contract and every verified micro, with
contract size and the min_account_1pct_stop yardstick, whole dollars)
and the MISSED-TRADE TREND across the ladder, whose top-rung verdict
is COMPUTED per variant: variant 2's $2M still misses one trade (GC
2026-02-02, $19,910 a contract against a budget January's dip left
$28 short -- the refusal gate reads LIVE equity, not starting
capital, exactly as at the broker) while variant 5's $2M misses
nothing.

ONE PAGE PER PUBLISHED CONFIGURATION since 2026-09-02 (Lode):
quickfix1m1dc_capitals_variant_02.html (the published baseline, from
the published blotter) and _05.html (the hybrid stop, from the matrix
JSON), named by the matrix's own slugs; the old single
quickfix1m1dc_capitals.html is retired and deleted on build.

THE UNIVERSE IS THE LIVE 22 FUTURES (Lode, same day: "ETF's can't be
traded with our strategy ... We only trade the 22 markets"). The
blotter's ETF and non-updated markets' trades are dropped before any
replay through research_1m_sizing.live_trades -- exact, since the
engine runs markets independently.

Money model per section: research_1m_sizing's refusal policy (floor
sizing, refuse at n=0, release as equity grows) with execution costs
per side from execution_costs.py (sourced; taxes excluded). The R of a
taken trade never moves across sections -- only which trades fit and
what they pay. Rebuilds from quickfix1m1dc_all.json and data_center's
contract_specs.json alone; no engine passes, seconds.

Output: output/quickfix1m1dc_capitals.html. Refresh step `capitals1m`.
"""

import json
from pathlib import Path

import pandas as pd

import execution_costs
import run_1m
import run_1m_matrix
import research_1m_feasibility as feas
import research_1m_sizing as sizing
from build_equity_html import CSS
from build_1m_report import (
    LIB_PATH, STUDY_BASE, REASON_TEXT, cls, daily_series, esc, held,
    money, price, replay, replay_contracts, signed, signed_money, stamp,
    streaks)

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "output"
IN_JSON = OUT_DIR / "quickfix1m1dc_all.json"
MATRIX_JSON = OUT_DIR / "quickfix1m1dc_matrix.json"
SPECS_JSON = HERE / ".." / "data_center" / "metadata" / \
    "contract_specs.json"

CAPITALS = [100_000, 250_000, 500_000, 1_000_000, 2_000_000]
RISK_PCT = 1.0
# One ladder per published configuration (Lode, 2026-09-02): the
# baseline and the hybrid stop, named by the matrix's own slugs
# (quickfix1m1dc_capitals_variant_02 / _05).
VARIANTS = [run_1m_matrix.BASELINE_NAME, "variant 5"]


def out_path(variant, micro=False):
    stem = ("quickfix1m1dc_capitals_micro_" if micro
            else "quickfix1m1dc_capitals_")
    return OUT_DIR / f"{stem}{run_1m_matrix.variant_slug(variant)}.html"


def load_variant(variant):
    """(trades, calendar, open_positions, source note). The baseline
    reads the published blotter -- the run charter's study also reads;
    any other cell reads the matrix JSON, same rule as
    build_1m_report.variant_payload."""
    if variant == run_1m_matrix.BASELINE_NAME:
        data = json.loads(IN_JSON.read_text(encoding="utf-8"))
        return (data["trades"], data.get("calendar"),
                data.get("open_positions"),
                "output/quickfix1m1dc_all.json (the published blotter)")
    m = json.loads(MATRIX_JSON.read_text(encoding="utf-8"))
    if variant not in m["trades"]:
        raise SystemExit(f"{variant} is not in the matrix "
                         f"({', '.join(m['trades'])})")
    trades = sorted(m["trades"][variant], key=lambda t: t["entry_ts"])
    return (trades, m.get("calendar"),
            m.get("open_positions", {}).get(variant),
            "output/quickfix1m1dc_matrix.json (the matrix pass)")


def cap_label(c):
    return f"${c / 1000:,.0f}k" if c < 1_000_000 else f"${c / 1e6:g}M"


# The MIC codes the definitions carry, in the venue-family form Lode
# asked the arsenal to show (2026-09-02). CME's four exchanges all
# trade on Globex, hence one family.
EXCHANGE_LABEL = {"XCME": "CME/GLBX", "XCEC": "COMEX/GLBX",
                  "XNYM": "NYMEX/GLBX", "XCBT": "CBOT/GLBX",
                  "IFUS": "ICE/IFUS", "XEUR": "Eurex"}


def open_cost(key):
    """USD cost of OPENING one contract (one side), from the sourced
    execution-cost table; None where the row has no source."""
    try:
        return execution_costs.cost_per_side(key, 1, eurusd=sizing.EURUSD)
    except (KeyError, ValueError):
        return None


# ------------------------------------------------------------- the arsenal

def arsenal_html(payload):
    """The contract arsenal: every market's front contract, then every
    verified micro/mini, each with its size and the whole-dollar
    min_account_1pct_stop yardstick (the account at which ONE contract
    with a 1%-of-price stop risks exactly 1% of equity)."""
    markets = payload["markets"]
    by_key = {r["key"]: r for r in payload["sizing"]}
    def whole(v):
        return f"{v:,.0f}" if v else "&mdash;"

    def cost_cell(v):
        return f"{v:,.2f}" if v is not None else "&mdash;"

    def tick_cell(v):
        # plain decimals, never scientific: MJY's 0.000001 must not
        # print as 1e-06
        if v is None:
            return "&mdash;"
        return f"{v:.7f}".rstrip("0").rstrip(".") if v < 0.001 else f"{v:g}"

    rows = []
    for key in sorted(sizing.LIVE_UNIVERSE,
                      key=list(markets).index):
        s = markets[key]
        r = by_key.get(key)
        # :, .0f and not :g -- 6J's 12,500,000 JPY must not print as
        # 1.25e+07 (every live future's unit qty is a whole number).
        size = f"{s['unit_qty']:,.0f} {s['unit']}"
        rows.append(
            f'<tr><td class="l">{esc(key)}</td>'
            f'<td class="l">{esc(s["market"])}</td>'
            f'<td class="l">'
            f'{EXCHANGE_LABEL.get(s.get("exchange"), s.get("exchange"))}'
            f'</td>'
            f'<td class="l mono">{esc(r["front"]) if r else "&mdash;"}</td>'
            f'<td class="l">{size}</td>'
            f'<td class="mono">{tick_cell(s.get("tick"))}</td>'
            f'<td class="mono">{cost_cell(open_cost(key))}</td>'
            f'<td class="mono">'
            f'{whole(r["min_account_1pct_stop"]) if r else "&mdash;"}</td>'
            f'</tr>')
    micro_rows = []
    for m in payload["micros"]:
        if m.get("listed") != "VERIFIED":
            continue
        micro_rows.append(
            f'<tr><td class="l">{esc(m["parent"])}</td>'
            f'<td class="l">{esc(m["name"])}</td>'
            f'<td class="l">CME/GLBX</td>'
            f'<td class="l mono">{esc(m["symbol"])}</td>'
            f'<td class="l">{esc(m["contract_unit"])}'
            f' ({esc(m["size_vs_parent"])})</td>'
            f'<td class="mono">{tick_cell(m.get("tick"))}</td>'
            f'<td class="mono">{cost_cell(open_cost(m["symbol"]))}</td>'
            f'<td class="mono">{whole(m.get("min_account_1pct_stop"))}'
            f'</td></tr>')
    head = ('<tr><th class="l" style="width:6%">Key</th>'
            '<th class="l" style="width:25%">Market</th>'
            '<th class="l" style="width:10%">Exchange</th>'
            '<th class="l" style="width:13%">Contract</th>'
            '<th class="l" style="width:16%">Size</th>'
            '<th style="width:8%">Tick</th>'
            '<th style="width:10%">Open 1 ctr $</th>'
            '<th style="width:12%">Min acct, 1% stop $</th></tr>')
    # The 3 of the 25 currently-updated Socrates markets that are NOT
    # in the trading universe, with the reason -- same column widths as
    # the markets table below it, so the two line out (Lode,
    # 2026-09-02). The reason spans the Contract..note columns.
    excluded = [
        ("JGB", "Japanese 10 Year Bond Futures", "OSE",
         "a futures market, but outside our data: no Databento OSE"
         " coverage (the known gap; IBKR backfill later)"),
        ("URA", "Global X Uranium ETF", "NYSE Arca",
         "ETF: cannot be traded with our strategy -- a share position"
         " pays full notional with no leverage, so risking 1% locks"
         " the account"),
        ("VIXY", "ProShares VIX Short Term Futures ETF", "NYSE Arca",
         "ETF: cannot be traded with our strategy -- same full-notional"
         " lock; it holds futures but trades as a share"),
    ]
    exc_head = ('<tr><th class="l" style="width:6%">Key</th>'
                '<th class="l" style="width:25%">Market</th>'
                '<th class="l" style="width:10%">Exchange</th>'
                '<th class="l wrap" style="width:59%" colspan="5">'
                'Why it is not traded</th></tr>')
    exc_rows = "".join(
        f'<tr><td class="l">{esc(k)}</td>'
        f'<td class="l">{esc(name)}</td>'
        f'<td class="l">{esc(venue)}</td>'
        f'<td class="l wrap" colspan="5">{reason}</td></tr>'
        for k, name, venue, reason in excluded)
    return (
        '<div class="section-h">The contract arsenal</div>'
        '<p class="chartnote"><b>3 of the 25 currently-updated Socrates '
        'markets are not traded</b>, and the 22 below are the whole '
        'trading universe:</p>'
        f'<div class="tradecard"><table class="trades"><thead>{exc_head}'
        f'</thead><tbody>{exc_rows}</tbody></table></div>'
        '<p class="chartnote"><b>The 22 markets we trade</b> &mdash; '
        'the live universe: the 19 currently-updated GLBX futures, '
        'FGBL (kept despite its EUR denomination) and the two IFUS '
        'markets. Each row: the <b>front '
        'contract</b>; below them, every <b>verified micro/mini</b> '
        'in the arsenal (definitions bought and validated 2026-09-01). '
        '<b>Min acct, 1% stop</b> is the yardstick from '
        'data_center&rsquo;s spec table: the account at which one '
        'contract with a 1%-of-price stop risks exactly 1% of equity '
        '&mdash; whole dollars, front close of the sizing build. The '
        'real gate in the sections below is the trade&rsquo;s own stop, '
        'not this yardstick.</p>'
        f'<div class="tradecard"><table class="trades"><thead>{head}'
        f'</thead><tbody>{"".join(rows)}</tbody></table></div>'
        '<p class="chartnote"><b>Micros and minis in arsenal</b> &mdash; '
        'verified from GLBX definitions; none are routed to by any '
        'replay yet, the micro study decides that.</p>'
        f'<div class="tradecard"><table class="trades"><thead>{head}'
        f'</thead><tbody>{"".join(micro_rows)}</tbody></table></div>')


def costs_html(payload):
    """The execution-cost model rendered in full (Lode, 2026-09-02:
    "a detailed examen of all the costs involved and resourced, the
    actual real numbers"): every live market's per-contract per-side
    components, the round turn, the confidence flag and the sourcing
    note, straight from execution_costs.py -- the single home of the
    numbers the replays subtract."""
    markets = payload["markets"]

    def row_html(key, r, label):
        nfa = r.get("nfa", execution_costs.NFA_PER_SIDE_USD)
        per = r["commission"] + r["exchange_fee"] + nfa \
            if r["exchange_fee"] is not None else None
        cur = r["currency"]
        usd = (per * sizing.EURUSD if (per and cur == "EUR") else per)
        return (
            f'<tr><td class="l">{esc(key)}</td>'
            f'<td class="l">{label}</td>'
            f'<td class="mono">{r["commission"]:.2f}</td>'
            f'<td class="mono">'
            f'{f"{r["exchange_fee"]:.2f}" if r["exchange_fee"] is not None
               else "no source"}</td>'
            f'<td class="mono">{nfa:.2f}</td>'
            f'<td class="mono">'
            f'{f"{cur} {per:.2f}" if per is not None else "&mdash;"}</td>'
            f'<td class="mono">'
            f'{f"{2 * usd:,.2f}" if usd is not None else "&mdash;"}</td>'
            f'<td class="l gapl">{esc(r["confidence"])}</td>'
            f'<td class="l wrap">{esc(r["note"])}</td></tr>')

    rows = []
    for key in sorted(sizing.LIVE_UNIVERSE, key=list(markets).index):
        r = execution_costs.FUTURES[key]
        label = EXCHANGE_LABEL.get(markets[key].get("exchange"),
                                   markets[key].get("exchange"))
        rows.append(row_html(key, r, label))
    micro_rows = [row_html(sym, execution_costs.MICROS[sym], "CME/GLBX")
                  for sym in execution_costs.MICROS]
    head = ('<tr><th class="l" style="width:6%">Key</th>'
            '<th class="l" style="width:10%">Exchange</th>'
            '<th style="width:9%">IBKR comm.</th>'
            '<th style="width:9%">Exch. fee</th>'
            '<th style="width:7%">NFA</th>'
            '<th style="width:11%">Per side</th>'
            '<th style="width:11%">Round turn $</th>'
            '<th class="l gapl" style="width:9%">Confidence</th>'
            '<th class="l" style="width:28%">Sources / note</th></tr>')
    return (
        '<div class="section-h">Costs, in detail</div>'
        '<p class="chartnote">The execution-cost model the deployment '
        'replays subtract, per contract PER SIDE: <b>IBKR fixed-rate '
        'commission</b> ($0.85 full-size US futures, $0.25 CME micros, '
        'EUR 0.90 on Eurex) + the <b>exchange fee</b> + the <b>NFA '
        'regulatory fee</b> ($0.02; none on Eurex). A round turn pays '
        'two sides; the entry side is charged the moment the order '
        'fills. <b>Sources</b> (retrieved 2026-09-01): IBKR&rsquo;s own '
        'worked examples &mdash; 1 ES contract = $0.85 + $1.38 = $2.24 '
        'per side, 1 Eurex contract = EUR 0.90 + EUR 0.52 = EUR 1.42 '
        'per side &mdash; and the TradeStation and Trade Pro Futures '
        'exchange-fee pass-through lists (IBKR&rsquo;s and CME&rsquo;s '
        'primary pages block automated retrieval). <b>Where two sources '
        'disagree the HIGHER figure is adopted</b> &mdash; a cost model '
        'errs expensive &mdash; and both readings stay on the row; a '
        'row with no source refuses to price rather than guess. FGBL '
        f'converts at EURUSD {sizing.EURUSD} (research-grade). Taxes '
        'are excluded at all times, margin is out of scope, and '
        'slippage is a separate thing entirely: it models the FILL and '
        'is charged in R by the engine, this models the BILL in '
        'dollars. The standing instruction in execution_costs.py: '
        'replace every row with the fee lines of real IB statements '
        'once the account exists. What no cost row covers is '
        '<b>liquidity</b> &mdash; whether the size can be filled at '
        'all &mdash; which is measured separately, on the entry '
        'minutes&rsquo; own printed volume, in '
        'research_1m_liquidity.py.</p>'
        f'<div class="tradecard"><div class="tradescroll">'
        f'<table class="trades"><thead>{head}</thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div></div>'
        '<p class="chartnote"><b>Micros and minis</b> &mdash; the same '
        'model for the arsenal&rsquo;s smaller contracts; the rows '
        'marked <b>no source</b> are never priced silently and need '
        'IB&rsquo;s own numbers before any micro trades.</p>'
        f'<div class="tradecard"><div class="tradescroll">'
        f'<table class="trades"><thead>{head}</thead>'
        f'<tbody>{"".join(micro_rows)}</tbody></table></div></div>')


def row_cost(m):
    """A money row's round-turn cost, full-only or mixed-stack."""
    return m.get("cost_rt",
                 m.get("cost_full_rt", 0.0) + m.get("cost_micro_rt", 0.0))


def tradeoffs_html(gates, payload):
    """THE DISADVANTAGES OF THE MICROS, stated before any micro result
    is read (Lode, 2026-09-02: "The disadvantage of the micro contracts
    is what we need to put in the reports"). Three measured tables --
    the fidelity/liquidity gates with every FAIL named, the relative
    cost of micro exposure, and the tick grids -- plus the caveats no
    table carries."""
    markets = payload["markets"]
    g_rows = []
    for key in sorted(gates["candidates"]):
        for c in gates["candidates"][key]:
            verdict = ("PASS" if c["passed"]
                       else "FAIL: " + ", ".join(c["why_failed"]))
            g_rows.append(
                f'<tr><td class="l">{esc(key)}</td>'
                f'<td class="l mono">{esc(c["root"])}</td>'
                f'<td class="mono">1/{round(1 / c["fraction"])}</td>'
                f'<td class="mono">{c["n_entries"]}</td>'
                f'<td class="mono">{c["coverage"] * 100:.0f}%</td>'
                f'<td class="mono">'
                f'{c["median_diff_ticks"] if c["median_diff_ticks"]
                   is not None else "&mdash;"}</td>'
                f'<td class="mono">'
                f'{c["p90_diff_ticks"] if c["p90_diff_ticks"]
                   is not None else "&mdash;"}</td>'
                f'<td class="mono">'
                f'{f"{c["median_minute_volume"]:,.0f}"
                   if c["median_minute_volume"] is not None
                   else "&mdash;"}</td>'
                f'<td class="mono">{c["needed_volume"]:.0f}</td>'
                f'<td class="l gapl {"pos" if c["passed"] else "neg"}">'
                f'{verdict}</td></tr>')
    c_rows = []
    for key in sorted(gates["candidates"]):
        for c in gates["candidates"][key]:
            root, frac = c["root"], c["fraction"]
            try:
                m_side = execution_costs.cost_per_side(root, 1)
                p_side = execution_costs.cost_per_side(
                    key, 1, eurusd=sizing.EURUSD)
            except (KeyError, ValueError):
                continue
            mult = (m_side / frac) / p_side
            p_tick = markets[key]["tick"]
            c_rows.append(
                f'<tr><td class="l">{esc(key)}</td>'
                f'<td class="l mono">{esc(root)}</td>'
                f'<td class="mono">{p_side:,.2f}</td>'
                f'<td class="mono">{m_side:,.2f}</td>'
                f'<td class="mono">{m_side / frac:,.2f}</td>'
                f'<td class="mono neg">{mult:,.2f}x</td>'
                f'<td class="mono">{p_tick:g}</td>'
                f'<td class="mono">{c["tick"]:g}</td>'
                f'<td class="l gapl">'
                f'{"coarser -- micro stops round AWAY from entry"
                   if c["tick"] > p_tick else "same grid"}</td></tr>')
    ghead = ('<tr><th class="l" style="width:6%">Mkt</th>'
             '<th class="l" style="width:7%">Root</th>'
             '<th style="width:7%">Size</th>'
             '<th style="width:7%">Entries</th>'
             '<th style="width:9%">Coverage</th>'
             '<th style="width:9%">Med dT</th>'
             '<th style="width:9%">P90 dT</th>'
             '<th style="width:10%">Med vol</th>'
             '<th style="width:8%">Need</th>'
             '<th class="l gapl" style="width:28%">Verdict</th></tr>')
    chead = ('<tr><th class="l" style="width:6%">Mkt</th>'
             '<th class="l" style="width:7%">Root</th>'
             '<th style="width:12%">Full $/side</th>'
             '<th style="width:12%">Micro $/side</th>'
             '<th style="width:14%">Micro, full-equiv $</th>'
             '<th style="width:11%">Cost multiple</th>'
             '<th style="width:9%">Full tick</th>'
             '<th style="width:9%">Micro tick</th>'
             '<th class="l gapl" style="width:20%">Grid</th></tr>')
    return (
        '<div class="section-h">The micro trade-offs</div>'
        '<p class="chartnote"><b>The disadvantages come first, because '
        'they gate everything on this page.</b> A reversal level is a '
        'price of the underlying and every verified micro quotes in the '
        'parent&rsquo;s exact price space, so the levels themselves '
        'need no scaling &mdash; but four real costs remain. '
        '<b>(1) The drift is measured and PRICED, trade by trade</b> '
        '(Lode, 2026-09-02: take the trade and put the drift in the '
        'curve): the table below profiles the micro&rsquo;s print '
        'against the parent&rsquo;s at our actual entry minutes, in '
        'parent ticks &mdash; and instead of gating the market, each '
        'trade&rsquo;s own SIGNED basis is booked into the equity '
        'curve at entry (a cost when the micro sat on the wrong side '
        'of the parent for our direction, a credit when it sat on the '
        'right one &mdash; the blotter&rsquo;s Drift column). Part of '
        'a thin micro&rsquo;s measured gap is a STALE PRINT (its last '
        'trade in the minute is older than the parent&rsquo;s), which '
        'overstates the tradable spread; pricing it therefore errs '
        'expensive, which is the right direction to err. Per-trade '
        'liquidity rules replace the old market gate: a trade with no '
        'micro bar at its entry minute gets NO micro leg, and a top-up '
        'never exceeds half the minute&rsquo;s printed volume. '
        '<b>(2) Micro exposure costs a multiple</b>: '
        'commissions and fees per dollar of exposure run 2-4x the full '
        'contract (table below) &mdash; a stack of ten micros is the '
        'expensive way to hold one contract. <b>(3) Coarser tick grids '
        'on some roots</b>: a stop computed in the parent&rsquo;s price '
        'space may not exist on the micro&rsquo;s grid, so the '
        'micro leg&rsquo;s stop is rounded AWAY from entry (equal or '
        'wider, never tighter) and its risk is sized on that wider '
        'distance. <b>(4) Operational: two instruments per position</b> '
        '&mdash; more orders, split fills, and a stop that can trigger '
        'one tick apart between legs. Roots with unsourced fee rows '
        '(MJY, MZW, MZC, MNG, 1OZ) are excluded outright until IB '
        'statements price them.</p>'
        f'<div class="tradecard"><table class="trades"><thead>{ghead}'
        f'</thead><tbody>{"".join(g_rows)}</tbody></table></div>'
        '<p class="chartnote"><b>The cost of micro exposure</b> &mdash; '
        'per side, per full-contract-equivalent, against the parent; '
        'and the tick grids.</p>'
        f'<div class="tradecard"><table class="trades"><thead>{chead}'
        f'</thead><tbody>{"".join(c_rows)}</tbody></table></div>')


def hardness_html(all_trades, payload):
    """What is REALLY hard to trade, measured on the strategy's own
    stops (Lode, 2026-09-01: the 1%-of-price yardstick "doesn't say
    too much because for silver 1% price movement isn't much"). Per
    market, the per-contract dollar risk of its ACTUAL historical
    setups -- rpu x point value, the same number the sizing gate reads
    -- and the account each implies at the 1% threshold: acct = 100 x
    per-contract risk. The median setup says what trading the market
    normally takes; the worst setup says what never missing one takes.
    A verified micro divides both by its size fraction. Markets with
    no trades in the window fall back to the labelled range estimate
    (0.4 x median daily range, the geometry band's midpoint)."""
    specs, _ = sizing.load_specs()
    micro_frac = {}
    for m in payload["micros"]:
        if m.get("listed") == "VERIFIED":
            frac = None
            s = m.get("size_vs_parent", "")
            if s.startswith("1/"):
                frac = 1.0 / float(s[2:])
            # keep the SMALLEST verified fraction per parent
            if frac and (m["parent"] not in micro_frac
                         or frac < micro_frac[m["parent"]][1]):
                micro_frac[m["parent"]] = (m["symbol"], frac)
    per_market = {}
    for t in all_trades:
        risk = t["rpu"] * sizing.usd_point_value(specs[t["market"]])
        per_market.setdefault(t["market"], []).append(risk)
    rows = []
    for key in sizing.LIVE_UNIVERSE:
        risks = sorted(per_market.get(key, []))
        est = None
        if risks:
            med, worst = risks[len(risks) // 2], risks[-1]
        else:
            rng = feas.median_daily_range(key)
            if rng is None:
                continue
            med = worst = feas.BAND_TYPICAL * rng \
                * sizing.usd_point_value(specs[key])
            est = True
        micro = micro_frac.get(key)
        rows.append((med, key, len(risks), worst, micro, est))
    rows.sort(reverse=True)
    body = []
    for med, key, n, worst, micro, est in rows:
        def w(v):
            return f"${v:,.0f}"
        via = (f'{micro[0]}: {w(med * micro[1] * 100)}'
               if micro else "&mdash;")
        body.append(
            f'<tr><td class="l">{esc(key)}</td>'
            f'<td class="mono">{n if n else "&mdash;"}</td>'
            f'<td class="mono">{w(med)}{" *" if est else ""}</td>'
            f'<td class="mono">{w(worst)}{" *" if est else ""}</td>'
            f'<td class="mono">{w(med * 100)}</td>'
            f'<td class="mono">{w(worst * 100)}</td>'
            f'<td class="l mono gapl">{via}</td></tr>')
    return (
        '<div class="section-h">What is hard to trade, on the '
        'strategy&rsquo;s own stops</div>'
        '<p class="chartnote">The yardstick above prices a hypothetical '
        '1%-of-price stop; the strategy&rsquo;s stops are STRUCTURAL '
        '(ladder-anchored), and for silver they run 2-4% of price. This '
        'table uses the real thing: each market&rsquo;s historical '
        'setups&rsquo; <b>per-contract dollar risk</b> (stop distance '
        '&times; point value &mdash; the exact number the sizing gate '
        'reads at order time), and the account each implies at the 1% '
        'threshold: <b>account = 100 &times; per-contract risk</b>. '
        '<b>Median setup</b> is what trading the market normally takes; '
        '<b>worst setup</b> is what never missing one takes. Sorted '
        'hardest first. Thin per-market samples &mdash; read the order '
        'of magnitude, not the third digit. Rows marked * have no '
        'trades in the window and use the 0.4-&times;-daily-range '
        'estimate instead.</p>'
        '<div class="tradecard"><table class="trades"><thead><tr>'
        '<th class="l" style="width:9%">Market</th>'
        '<th style="width:9%">Trades</th>'
        '<th style="width:14%">$/contract, median</th>'
        '<th style="width:14%">$/contract, worst</th>'
        '<th style="width:16%">Acct for median setup</th>'
        '<th style="width:16%">Acct for every setup</th>'
        '<th class="l gapl" style="width:22%">Via smallest micro '
        '(median)</th>'
        f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


# --------------------------------------------------------- the micro stack

GATES_JSON = OUT_DIR / "quickfix1m1dc_micro_gates.json"


# A micro top-up never takes more than this share of the entry
# minute's printed volume -- drift pricing answers fidelity, this
# answers liquidity, trade by trade.
PARTICIPATION_CAP = 0.5


def micro_route():
    """market -> routed micro leg spec plus the per-entry drift map,
    from the measured study (research_1m_micro.py). Since the
    drift-pricing revision (Lode, 2026-09-02) every sourced candidate
    routes; the measured drift is PRICED per trade instead of gating
    the market, and a trade with no per-entry record gets no micro
    leg."""
    gates = json.loads(GATES_JSON.read_text(encoding="utf-8"))
    route = {}
    for key, root in gates["routing"].items():
        if root is None:
            continue
        cand = next(c for c in gates["candidates"][key]
                    if c["root"] == root)
        route[key] = dict(root=root, fraction=cand["fraction"],
                          tick=cand["tick"])
    return route, gates


def rounded_micro_stop(entry, stop, tick):
    """The parent-space stop price on the MICRO's tick grid, rounded
    AWAY from entry -- a micro stop may only be equal or wider, never
    tighter, than the parent's (Lode: the stop placement on the micro
    is the critical piece; conservatism is the rule).

    Rounded on the EXCHANGE'S ABSOLUTE PRICE GRID (multiples of the
    micro tick), never on an entry-anchored offset grid: the slipped
    entry fill can sit off-grid, and an order book only accepts grid
    prices. The epsilon absorbs float dust so a stop already on the
    grid stays exactly where it is."""
    import math as _m
    steps = stop / tick
    eps = 1e-9 * max(1.0, abs(steps))
    if stop > entry:      # short: the stop sits above, round UP
        return _m.ceil(steps - eps) * tick
    return _m.floor(steps + eps) * tick


def replay_micro(trades, risk_pct, start, route, specs, per_entry):
    """The mixed-stack replay: full contracts first, then the routed
    micro tops the remainder up toward the budget. Refused only when
    even one micro does not fit (or the market has no routed micro and
    one full contract does not fit).

    Booking, precise by construction: the micro leg's RISK uses its
    own rounded stop distance (>= the parent's); a STOP exit books the
    micro leg at that wider distance (net_r scaled on its own risk
    base), any other exit books the identical per-unit price move the
    parent leg made (net_r x parent rpu x micro point value). Costs
    are charged per leg per side from the sourced table and reported
    split.

    THE DRIFT IS PRICED, NOT GATED (Lode, 2026-09-02): the measured
    signed basis of the micro's print against the parent's at THIS
    trade's entry minute is booked into the curve at entry --
    side_sign x basis x point value x contracts, a COST when the micro
    sat on the wrong side of the parent for our direction and a CREDIT
    when it sat on the right one. Per-trade liquidity rules: no micro
    bar at the entry minute means no micro leg for that trade, and the
    top-up never exceeds PARTICIPATION_CAP of the minute's printed
    volume. Exits at settlement are treated as aligned (exchange
    micro settlements track the parent's); stop exits book the micro
    leg at its own grid-rounded stop distance."""
    events = []
    for i, t in enumerate(trades):
        events.append((pd.Timestamp(t["entry_ts"]), 1, i))
        events.append((pd.Timestamp(t["exit_ts"]), 0, i))
    events.sort(key=lambda e: (e[0], e[1]))

    equity, peak, max_dd = start, start, 0.0
    open_pos, money_of, eod, refused = {}, {}, {}, {}
    for ts, kind, i in events:
        t = trades[i]
        if kind == 1:
            spec = specs[t["market"]]
            pv_full = sizing.usd_point_value(spec)
            full_risk = t["rpu"] * pv_full
            budget = equity * risk_pct / 100.0
            n = int(budget // full_risk)
            r = route.get(t["market"])
            rec = per_entry.get(
                f"{t['market']}|{t['contract']}|{t['entry_ts']}")
            k, rpu_m, pv_m, root, basis = 0, None, None, None, 0.0
            if r is not None and rec is not None and rec["volume"] > 0:
                root = r["root"]
                basis = rec["basis"]
                # The SAME risk anchor as the parent's R: level to
                # stop (entry_first), never the slipped fill -- the
                # two legs must denominate one distance, the micro's
                # merely rounded to its own grid.
                anchor = t.get("entry_first") or t["entry"]
                stop_m = rounded_micro_stop(anchor, t["stop"],
                                            r["tick"])
                rpu_m = abs(anchor - stop_m)
                pv_m = pv_full * r["fraction"]
                micro_risk = rpu_m * pv_m
                k = min(int((budget - n * full_risk) // micro_risk),
                        int(rec["volume"] * PARTICIPATION_CAP))
                k = max(k, 0)
            if n == 0 and k == 0:
                refused[i] = dict(per_unit=full_risk, equity=equity,
                                  budget=budget)
                continue
            side = execution_costs.cost_per_side(
                t["market"], n, eurusd=sizing.EURUSD) if n else 0.0
            side_m = execution_costs.cost_per_side(
                root, k, eurusd=sizing.EURUSD) if k else 0.0
            # the measured entry drift, signed against our side: a
            # long pays a micro printing above the parent, a short is
            # paid by it
            side_sign = 1.0 if t["side"] == "long" else -1.0
            drift = (side_sign * basis * pv_m * k) if k else 0.0
            equity -= side + side_m + drift
            risk_usd = n * full_risk + (k * rpu_m * pv_m if k else 0.0)
            m = dict(n=n, k=k, root=root, rpu_m=rpu_m, pv_m=pv_m,
                     full_risk=full_risk, risk_usd=risk_usd,
                     risk_pct=risk_usd
                     / (equity + side + side_m + drift) * 100.0,
                     cost_full_rt=2.0 * side, cost_micro_rt=2.0 * side_m,
                     drift_usd=drift)
            open_pos[i] = m
        else:
            m = open_pos.pop(i, None)
            if m is None:
                continue
            pnl_full = t["net_r"] * m["n"] * m["full_risk"]
            if m["k"]:
                if t["reason"] == "stop":
                    # the micro leg is stopped at ITS OWN rounded stop:
                    # the loss per unit is its wider distance
                    pnl_micro = t["net_r"] * m["k"] * m["rpu_m"] * m["pv_m"]
                else:
                    # any other exit fills both legs at the same price,
                    # so the per-unit move is the parent's
                    pnl_micro = t["net_r"] * t["rpu"] * m["pv_m"] * m["k"]
            else:
                pnl_micro = 0.0
            pnl = (pnl_full + pnl_micro
                   - m["cost_full_rt"] / 2.0 - m["cost_micro_rt"] / 2.0)
            equity += pnl
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
            money_of[i] = dict(
                m, pnl_usd=pnl_full + pnl_micro
                - m["cost_full_rt"] - m["cost_micro_rt"]
                - m["drift_usd"],
                balance=equity)
            worst = max(eod.get(ts.date(), (0.0, 0.0, 0.0))[2],
                        (peak - equity) / peak * 100.0)
            eod[ts.date()] = (equity, peak, worst)
    return money_of, eod, equity, max_dd, refused


# ------------------------------------------------------------- the sections

def run_ladder(all_trades, route=None, specs=None, per_entry=None):
    """One refusal-policy replay per capital; with `route`, the
    mixed-stack micro replay instead."""
    out = []
    for cap in CAPITALS:
        if route is None:
            money_of, eod, final, max_dd, refused = replay_contracts(
                all_trades, RISK_PCT, float(cap))
        else:
            money_of, eod, final, max_dd, refused = replay_micro(
                all_trades, RISK_PCT, float(cap), route, specs,
                per_entry or {})
        _, _, ideal_final, ideal_dd = replay(all_trades, RISK_PCT,
                                             float(cap))
        out.append(dict(cap=cap, money_of=money_of, eod=eod, final=final,
                        max_dd=max_dd, refused=refused,
                        ideal_final=ideal_final, ideal_dd=ideal_dd))
    return out


def trend_html(ladder, n_all, all_trades):
    # The top rung's verdict is COMPUTED, never asserted: variant 2's
    # $2M still misses one trade (GC 2026-02-02 by $28 after January's
    # dip) while variant 5's misses none, and a hardcoded sentence
    # would lie on one of the two pages.
    top = ladder[-1]
    if top["refused"]:
        worst = min(top["refused"].items(),
                    key=lambda kv: kv[1]["budget"] - kv[1]["per_unit"])
        t, r = all_trades[worst[0]], worst[1]
        top_note = (
            f'Even {cap_label(top["cap"])} misses '
            f'{len(top["refused"])}, and honestly so: {esc(t["market"])} '
            f'{t["entry_date"]} costs {money(r["per_unit"])} a contract '
            f'and the budget at that moment was {money(r["budget"])} '
            f'&mdash; short by {money(r["per_unit"] - r["budget"])}. The '
            f'gate reads live equity, not starting capital, exactly as '
            f'it would at the broker. ')
    else:
        top_note = (
            f'At {cap_label(top["cap"])} nothing is missed: every '
            f'blotter entry fit at least one contract inside the 1% '
            f'budget at its moment. The gate reads live equity, not '
            f'starting capital, exactly as it would at the broker. ')
    rows = []
    for r in ladder:
        taken = len(r["money_of"])
        missed = len(r["refused"])
        costs = sum(row_cost(m) for m in r["money_of"].values())
        rows.append(
            f'<tr><td class="l mono">{cap_label(r["cap"])}</td>'
            f'<td class="mono">{taken}</td>'
            f'<td class="mono {"neg" if missed else "pos"}">{missed}</td>'
            f'<td class="mono">{100 * missed / n_all:.0f}%</td>'
            f'<td class="mono">{money(r["final"])}</td>'
            f'<td class="mono {cls(r["final"] / r["cap"] - 1)}">'
            f'{signed(100 * (r["final"] / r["cap"] - 1), 1)}%</td>'
            f'<td class="mono">{r["max_dd"]:.2f}%</td>'
            f'<td class="mono">{money(costs)}</td>'
            f'<td class="mono">'
            f'{100 * (r["final"] / r["ideal_final"] - 1):+.2f}%</td>'
            f'</tr>')
    return (
        '<div class="section-h">The missed-trade trend</div>'
        '<p class="chartnote">The whole ladder in one table: how many of '
        f'the {n_all} blotter trades each starting capital could take '
        'inside the 1% threshold, and what the missed ones cost. A '
        'missed trade is an order REFUSED at placement because one '
        'contract risked more than 1% of equity <b>at that moment</b> '
        '&mdash; never forced &mdash; and the refusals thin out as '
        'capital grows. ' + top_note +
        '<b>vs ideal</b> is the distance to the frictionless fractional '
        'replay at the same capital (quantization + refusals + '
        'execution costs together).</p>'
        '<div class="tradecard"><table class="trades"><thead><tr>'
        '<th class="l" style="width:11%">Start capital</th>'
        '<th style="width:10%">Taken</th>'
        '<th style="width:10%">Missed</th>'
        '<th style="width:10%">Missed %</th>'
        '<th style="width:14%">Final</th>'
        '<th style="width:11%">Return</th>'
        '<th style="width:11%">Max DD</th>'
        '<th style="width:12%">Exec costs</th>'
        '<th style="width:11%">vs ideal</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def refused_section_html(all_trades, refused, links_full):
    if not refused:
        return ('<p class="chartnote"><b>No trade missed at this '
                'capital.</b> Every blotter entry fit at least one '
                'contract inside the 1% budget.</p>')
    rows = []
    for i in sorted(refused, key=lambda i: all_trades[i]["entry_ts"]):
        t, r = all_trades[i], refused[i]
        link = links_full.get(t["market"])
        name = esc(t["market"])
        if link:
            name = (f'<a href="{link[0]}&amp;t={link[1][i]}" '
                    f'target="_blank">{name}</a>')
        rows.append(
            f'<tr><td class="l">{name}</td>'
            f'<td class="l">{t["side"]}</td>'
            f'<td class="l mono">{stamp(t["entry_ts"])}</td>'
            f'<td class="mono neg">{money(r["per_unit"])}</td>'
            f'<td class="mono">{money(r["budget"])}</td>'
            f'<td class="mono {cls(t["net_r"])}">{signed(t["net_r"])}'
            f'</td></tr>')
    return (
        f'<p class="chartnote"><b>{len(refused)} trades missed</b>: one '
        'contract risked more than the 1% budget at order time. '
        '<b>R (not taken)</b> is what the blotter&rsquo;s trade went on '
        'to do &mdash; release information, not booked money.</p>'
        '<div class="tradecard"><table class="trades"><thead><tr>'
        '<th class="l" style="width:14%">Market</th>'
        '<th class="l" style="width:9%">Side</th>'
        '<th class="l" style="width:20%">In (UTC)</th>'
        '<th style="width:19%">1 contract $</th>'
        '<th style="width:19%">Budget $</th>'
        '<th style="width:19%">R (not taken)</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def blotter_section_html(all_trades, money_of_full, links_full,
                         micro=False):
    """The taken trades of one capital: contracts, ACTUAL risk %, and
    the detailed execution cost, attributed per trade. In micro mode
    the position is a STACK (n full + k micro), shown as such, with
    the full leg's and the micro leg's round-turn costs in their own
    columns (Lode: the costs of adding micro contracts detailed per
    trade, with a clear view of the open contract positions)."""
    rows = []
    for i in sorted(money_of_full, key=lambda i: all_trades[i]["entry_ts"]):
        t, m = all_trades[i], money_of_full[i]
        mins = ((pd.Timestamp(t["exit_ts"]) - pd.Timestamp(t["entry_ts"]))
                .total_seconds() / 60.0)
        link = links_full.get(t["market"])
        name = esc(t["market"])
        if link:
            name = (f'<a href="{link[0]}&amp;t={link[1][i]}" '
                    f'target="_blank">{name}</a>')
        common_a = (
            f'<tr><td class="l" data-s="{esc(t["market"])}">{name}</td>'
            f'<td class="l" data-s="{t["side"]}">{t["side"]}</td>'
            f'<td class="l mono" data-s="{t["entry_ts"]}">'
            f'{stamp(t["entry_ts"])}</td>'
            f'<td class="mono" data-s="{mins:.0f}">{held(mins)}</td>')
        common_b = (
            f'<td class="mono" data-s="{m["risk_pct"]:.3f}">'
            f'{m["risk_pct"]:.2f}%</td>'
            f'<td class="mono {cls(t["net_r"])}" data-s="{t["net_r"]}">'
            f'{signed(t["net_r"])}</td>')
        common_c = (
            f'<td class="mono {cls(m["pnl_usd"])}"'
            f' data-s="{m["pnl_usd"]:.2f}">'
            f'{signed_money(m["pnl_usd"])}</td>'
            f'<td class="mono" data-s="{m["balance"]:.2f}">'
            f'{money(m["balance"])}</td>'
            f'<td class="l gapl" data-s="{t["reason"]}">'
            f'{REASON_TEXT.get(t["reason"], t["reason"])}</td></tr>')
        if micro:
            stack = " + ".join(
                ([f'{m["n"]} {t["market"]}'] if m["n"] else [])
                + ([f'{m["k"]} {m["root"]}'] if m["k"] else []))
            tip = (f'micro stop rounded to {m["root"]}\'s grid: risk '
                   f'{m["rpu_m"]:g}/unit vs parent {t["rpu"]:g}'
                   if m["k"] else "no micro leg")
            drift = m.get("drift_usd", 0.0)
            rows.append(
                common_a
                + f'<td class="l mono" data-s="{m["n"] * 1000 + m["k"]}"'
                  f' title="{tip}">{stack}</td>'
                + f'<td class="mono" data-s="{m["risk_usd"]:.0f}">'
                  f'{money(m["risk_usd"])}</td>'
                + common_b
                + f'<td class="mono neg" data-s="{m["cost_full_rt"]:.2f}">'
                  f'{money(m["cost_full_rt"])}</td>'
                + f'<td class="mono neg" data-s="{m["cost_micro_rt"]:.2f}">'
                  f'{money(m["cost_micro_rt"])}</td>'
                + f'<td class="mono {cls(-drift)}" data-s="{drift:.2f}"'
                  f' title="measured micro-vs-parent print at the entry'
                  f' minute, signed against the side: positive = paid,'
                  f' negative = received">'
                  f'{signed_money(-drift) if drift else "&mdash;"}</td>'
                + common_c)
        else:
            rows.append(
                common_a
                + f'<td class="mono" data-s="{m["n"]}">{m["n"]:,}</td>'
                + f'<td class="mono" data-s="{m["risk_usd"]:.0f}"'
                  f' title="${m["per_unit"]:,.0f} per contract">'
                  f'{money(m["risk_usd"])}</td>'
                + common_b
                + f'<td class="mono neg" data-s="{m["cost_rt"]:.2f}">'
                  f'{money(m["cost_rt"])}</td>'
                + common_c)
    if micro:
        cols = [("Market", "l", 8), ("Side", "l", 4.5),
                ("In (UTC)", "l", 10.5), ("Held", "", 4.5),
                ("Stack", "l", 10.5), ("Risk $", "", 7),
                ("Risk %", "", 5.5), ("R", "", 4.5),
                ("Full cost $", "", 6.5), ("Micro cost $", "", 6.5),
                ("Drift $", "", 6.5),
                ("P&amp;L $", "", 8), ("Balance", "", 8),
                ("Reason", "l gapl", 9.5)]
        note = (
            '<p class="chartnote">Every trade this capital took, in '
            'entry order. <b>Stack</b> is the open position&rsquo;s '
            'composition &mdash; full contracts of the parent plus the '
            'routed micro&rsquo;s top-up (hover a stacked row for the '
            'micro leg&rsquo;s rounded stop distance). <b>Risk %</b> is '
            'what the whole stack ACTUALLY risked of equity at entry; '
            '<b>Full cost $</b> and <b>Micro cost $</b> are each '
            'leg&rsquo;s round turn of commission + exchange + NFA '
            '(sourced in execution_costs.py; taxes excluded). '
            '<b>Drift $</b> is the MEASURED micro-vs-parent print at '
            'this trade&rsquo;s entry minute, signed against the side '
            '&mdash; red is a cost paid for the micro sitting on the '
            'wrong side of the parent, green a credit for the right '
            'one. All three are already inside P&amp;L and '
            'Balance.</p>')
    else:
        cols = [("Market", "l", 9.5), ("Side", "l", 5),
                ("In (UTC)", "l", 12), ("Held", "", 5.5), ("Ctr", "", 5),
                ("Risk $", "", 8), ("Risk %", "", 6.5), ("R", "", 6),
                ("Costs $", "", 7), ("P&amp;L $", "", 9.5),
                ("Balance", "", 9.5), ("Reason", "l gapl", 16.5)]
        note = (
            '<p class="chartnote">Every trade this capital took, in entry '
            'order. <b>Ctr</b> is whole contracts, '
            '<b>Risk %</b> the risk the opened position ACTUALLY took of '
            'equity at entry (floor sizing keeps it at or under 1%), '
            '<b>Costs $</b> the trade&rsquo;s full round turn of '
            'commission + exchange + NFA fees (sourced in '
            'execution_costs.py; taxes excluded), already inside '
            'P&amp;L and Balance.</p>')
    head = "".join(f'<th class="{c}" style="width:{w}%">{lab}</th>'
                   for lab, c, w in cols)
    return (
        note
        + '<div class="tradecard"><div class="tradescroll">'
        f'<table class="trades"><thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div></div>')


def tile(k, v, s, tone=""):
    return (f'<div class="kpi"><div class="k">{k}</div>'
            f'<div class="v{" " + tone if tone else ""}">{v}</div>'
            f'<div class="sub">{s}</div></div>')


def section_html(idx, r, all_trades, calendar, links_full, n_open=None,
                 micro=False):
    cap = r["cap"]
    taken_idx = sorted(r["money_of"])
    taken = [all_trades[i] for i in taken_idx]
    days, eq, dd, ddc, openpos = daily_series(
        taken, r["eod"], calendar, float(cap))
    costs = sum(row_cost(m) for m in r["money_of"].values())

    # The variant reports' full metric set, per section (Lode,
    # 2026-09-02) -- computed on the TAKEN trades, since those are the
    # only ones this account traded.
    wins = [t for t in taken if t["net_r"] > 0]
    losses = [t for t in taken if t["net_r"] <= 0]
    net_r = sum(t["net_r"] for t in taken)
    gross_win = sum(t["net_r"] for t in wins)
    gross_loss = -sum(t["net_r"] for t in losses)
    pf = gross_win / gross_loss if gross_loss else None
    run_w, run_l = streaks(taken)
    holds = [(pd.Timestamp(t["exit_ts"]) - pd.Timestamp(t["entry_ts"])
              ).total_seconds() / 60.0 for t in taken]
    # The KPI row is an auto-fit grid (never leaves a gap); .stats4 is
    # a strict 3-column grid, so its tile count must be a multiple of
    # three -- Win rate and Net R live in the KPI row and the stats
    # grid carries exactly twelve tiles (Lode, 2026-09-02: no empty
    # gray field).
    kpis = "".join([
        tile("Start capital", money(cap), "this section's account"),
        tile("Final capital", money(r["final"]),
             f"{signed(100 * (r['final'] / cap - 1), 1)}% return",
             cls(r["final"] - cap)),
        tile("Max drawdown", f"{r['max_dd']:.2f}%",
             "worst reached intraday"),
        tile("Max drawdown on closes", f"{max(ddc):.2f}%",
             "daily closing balances"),
        tile("Taken / missed", f"{len(taken)} / {len(r['refused'])}",
             f"of {len(all_trades)} blotter trades",
             "neg" if r["refused"] else "pos"),
        tile("Win rate", f"{100 * len(wins) / len(taken):.1f}%",
             f"{len(wins)} won, {len(losses)} lost"),
        tile("Net R", signed(net_r, 2), "after slippage, taken trades",
             cls(net_r)),
        (tile("Micro top-ups",
              f"{sum(m.get('k', 0) for m in r['money_of'].values()):,}"
              f" ctr",
              f"on {sum(1 for m in r['money_of'].values()
                        if m.get('k'))} of {len(taken)} trades;"
              f" ${sum(m.get('cost_micro_rt', 0.0)
                       for m in r['money_of'].values()):,.2f} of the"
              f" costs")
         if micro else ""),
        (tile("Micro drift, net",
              signed_money(-sum(m.get("drift_usd", 0.0)
                                for m in r["money_of"].values())),
              "measured entry prints, signed against the side;"
              " in the curve",
              cls(-sum(m.get("drift_usd", 0.0)
                       for m in r["money_of"].values())))
         if micro else ""),
        tile("Execution costs", money(costs),
             "both sides, in the curve", "neg"),
        tile("vs frictionless ideal",
             f"{100 * (r['final'] / r['ideal_final'] - 1):+.2f}%",
             f"ideal {money(r['ideal_final'])} at"
             f" {r['ideal_dd']:.2f}% DD",
             cls(r["final"] - r["ideal_final"])),
    ])
    # Twelve tiles in three rows of four (Lode, 2026-09-02): the
    # winner/loser pair and the best/worst pair share the middle row.
    stats = "".join([
        tile("Expectancy", signed(net_r / len(taken)) + "R",
             "per taken trade", cls(net_r)),
        tile("Profit factor", f"{pf:.2f}" if pf else "&mdash;",
             f"{gross_win:.1f}R won against {gross_loss:.1f}R lost"),
        tile("Longest winning run", f"{run_w}",
             "positions, in entry order"),
        tile("Longest losing run", f"{run_l}",
             "positions, in entry order"),
        tile("Average winner",
             signed(gross_win / len(wins)) + "R" if wins else "&mdash;",
             f"{len(wins)} trades", "pos"),
        tile("Average loser",
             signed(-gross_loss / len(losses)) + "R" if losses
             else "&mdash;",
             f"{len(losses)} trades", "neg"),
        tile("Best trade", signed(max(t["net_r"] for t in taken)) + "R",
             "net of slippage"),
        tile("Worst trade", signed(min(t["net_r"] for t in taken)) + "R",
             "a gapped or slipped stop can cost more than 1R"),
        tile("Average hold", held(sum(holds) / len(holds)),
             "entry to exit"),
        tile("Max concurrent", f"{max(openpos)}",
             "positions open at once"),
        tile("Currently open",
             f"{n_open}" if n_open is not None else "&mdash;",
             "strategy-level, at the window end; the sizing gate is"
             " not replayed for open entries"),
        tile("Time in market",
             f"{100 * sum(1 for o in openpos if o) / len(openpos):.0f}%",
             "of market days with a position open"),
    ])
    return (
        f'<div class="section-h" id="cap{idx}">'
        f'Starting capital {cap_label(cap)}</div>'
        f'<div class="kpis">{kpis}</div>'
        f'<div class="stats4">{stats}</div>'
        f'<div class="card">'
        f'<div class="charthead"><div class="t">One shared account, '
        f'{cap_label(cap)} start</div>'
        f'<div class="s">{len(taken)} trades taken, {days[0]} to '
        f'{days[-1]}, integer contracts at the 1% budget, refusal '
        f'policy, execution costs in the curve. Step lines on market '
        f'days, like every curve in this project.</div></div>'
        f'<div class="panelbl">Equity</div><div id="eq{idx}" class="pane-eq"></div>'
        f'<div class="panelbl">Drawdown &middot; on daily closes</div>'
        f'<div id="ddc{idx}" class="pane-ddc"></div>'
        f'<div class="panelbl">Open positions</div>'
        f'<div id="op{idx}" class="pane-op"></div>'
        f'</div>'
        + refused_section_html(all_trades, r["refused"], links_full)
        + blotter_section_html(all_trades, r["money_of"], links_full,
                               micro)
    ), days, eq, ddc, openpos


PAGE_JS = r"""<script>
(function () {
  function cssv(n) {
    return getComputedStyle(document.documentElement)
      .getPropertyValue(n).trim();
  }
  function opts() {
    return {
      layout: { background: { color: cssv('--surface') },
                textColor: cssv('--ink2'), attributionLogo: false },
      grid: { vertLines: { color: cssv('--grid') },
              horzLines: { color: cssv('--grid') } },
      rightPriceScale: { borderColor: cssv('--border') },
      timeScale: { borderColor: cssv('--border') },
    };
  }
  function pct(v) { return v.toFixed(2) + '%'; }
  var STEP = LightweightCharts.LineType.WithSteps;
  var SECTIONS = __SECTIONS__;
  var allCharts = [];
  SECTIONS.forEach(function (sec, si) {
    var panes = [];
    function mk(id, data, add) {
      var el = document.getElementById(id + si);
      var c = LightweightCharts.createChart(el, Object.assign(
        { width: el.clientWidth, height: el.clientHeight - 18 }, opts()));
      var s = add(c);
      s.setData(data.map(function (p) {
        return { time: p[0], value: p[1] };
      }));
      panes.push({ el: el, chart: c });
      allCharts.push({ el: el, chart: c });
    }
    mk('eq', sec.eq, function (c) {
      return c.addLineSeries({ color: cssv('--accent-line'),
        lineWidth: 2, lineType: STEP });
    });
    mk('ddc', sec.ddc, function (c) {
      return c.addLineSeries({ color: cssv('--neg'), lineWidth: 1,
        lineType: STEP,
        priceFormat: { type: 'custom', formatter: pct } });
    });
    mk('op', sec.op, function (c) {
      return c.addHistogramSeries({ color: cssv('--bars') });
    });
    // One label column per SECTION so its three time axes align.
    var w = 0;
    panes.forEach(function (p) {
      w = Math.max(w, p.chart.priceScale('right').width());
    });
    panes.forEach(function (p) {
      p.chart.applyOptions({ rightPriceScale: { minimumWidth: w } });
      p.chart.timeScale().fitContent();
    });
    panes.forEach(function (p) {
      p.chart.timeScale().subscribeVisibleLogicalRangeChange(function (r) {
        if (!r) return;
        panes.forEach(function (q) {
          if (q !== p) q.chart.timeScale().setVisibleLogicalRange(r);
        });
      });
    });
  });
  function resize() {
    allCharts.forEach(function (p) {
      p.chart.resize(p.el.clientWidth, p.el.clientHeight - 18);
    });
  }
  window.addEventListener('resize', resize);
  function retheme() {
    allCharts.forEach(function (p) { p.chart.applyOptions(opts()); });
  }
  window.addEventListener('beforeprint', retheme);
  window.addEventListener('afterprint', retheme);
})();
</script>"""


PAGE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>quickfix1m1dc [__VNAME__] &mdash; the capital ladder</title>
__CSS__
<style>
.pane-eq{height:300px}.pane-ddc{height:130px}.pane-op{height:110px}
.pane-eq,.pane-ddc,.pane-op{margin-bottom:4px}
.panelbl{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink3);font-weight:600;margin:10px 2px 4px}
table.trades td a{color:var(--accent);text-decoration:none;font-weight:600}
table.trades td a:hover{text-decoration:underline}
/* The shared stylesheet caps .chartnote at 78ch, which reads as cut
   off beside full-width tables (Lode, 2026-09-02): on this page the
   notes run the full column like the lede does. */
.chartnote{max-width:none}
/* The shared .kpis is an auto-fit GRID, which leaves gray cells
   whenever the tile count does not fill the last row. Flex with
   stretching tiles fills every row whatever the count (same Lode
   note: no empty gray fields). */
.kpis{display:flex;flex-wrap:wrap}
.kpis .kpi{flex:1 1 150px}
/* Breathing room where a right-aligned number column meets a
   left-aligned text column -- the two contents otherwise meet in the
   middle with 14px between them (Lode, 2026-09-02: "a bit of space
   between the columns ... visually unclear"). */
table.trades td.gapl,table.trades th.gapl{padding-left:30px}
/* Twelve stat tiles as 3 rows x 4 columns (Lode, 2026-09-02), the
   winner/loser and best/worst pairs sharing one row; the shared
   stylesheet's narrow-screen 2-column rule stays in force below
   641px. */
@media(min-width:641px){.stats4{grid-template-columns:repeat(4,1fr)}}
@media print{.pane-eq{height:260px}.pane-ddc,.pane-op{height:110px}}
</style></head><body>
<div class="wrap">
<header>
  <div class="eyebrow">1-minute workstream &middot; deployment</div>
  <h1>quickfix1m1dc [__VNAME__] &mdash; the capital ladder</h1>
  <p class="lede">__LEDE__</p>
</header>
__ARSENAL__
__TREND__
__SECTIONS__
<footer>__FOOTER__</footer>
</div>
<script>__LIB__</script>
__JS__
</body></html>"""


def build(variant=run_1m_matrix.BASELINE_NAME, micro=False):
    trades_in, calendar, open_positions, source = load_variant(variant)
    payload = json.loads(SPECS_JSON.read_text(encoding="utf-8"))
    route, gates, specs = {}, None, None
    if micro:
        route, gates = micro_route()
        specs, _ = sizing.load_specs()
    # THE LIVE UNIVERSE ONLY (Lode, 2026-09-01): the blotter's ETF and
    # non-updated markets are not traded, so their trades leave before
    # any replay -- exact, the engine runs markets independently.
    all_trades = sizing.live_trades(trades_in)
    calendar = calendar or run_1m.calendar_fallback(all_trades)

    # Charter links numbered against the FULL blotter (the list the 1m
    # study holds), shared by every section.
    by_market = {}
    for i, t in enumerate(all_trades):
        by_market.setdefault(t["market"], []).append(i)
    links_full = {}
    for key, idxs in by_market.items():
        try:
            folder = run_1m.market_info(key)["array_dir"]
        except (KeyError, StopIteration):
            continue
        order = sorted(idxs, key=lambda i: all_trades[i]["entry_ts"])
        links_full[key] = (f"{STUDY_BASE}?m={folder}",
                           {i: n + 1 for n, i in enumerate(order)}, folder)

    n_open = (None if open_positions is None else
              sum(1 for o in open_positions
                  if o["market"] in sizing.LIVE_UNIVERSE))

    ladder = run_ladder(all_trades, route if micro else None, specs,
                        gates.get("per_entry") if micro else None)
    sections, series = [], []
    for idx, r in enumerate(ladder):
        html, days, eq, ddc, openpos = section_html(
            idx, r, all_trades, calendar, links_full, n_open, micro)
        sections.append(html)
        series.append(dict(eq=[[d, v] for d, v in zip(days, eq)],
                           ddc=[[d, v] for d, v in zip(days, ddc)],
                           op=[[d, v] for d, v in zip(days, openpos)]))

    is_base = variant == run_1m_matrix.BASELINE_NAME
    micro_lede = (
        " <b>THE MICRO LADDER</b>: every position is topped up toward "
        "the full 1% with contracts of the routed micro ("
        + esc(", ".join(f"{k}->{r['root']}"
                        for k, r in sorted(route.items()))
              or "none")
        + "; sourced execution costs only). The measured "
        "micro-vs-parent DRIFT at each trade's own entry minute is "
        "PRICED into the curve, signed against the side -- a cost or "
        "a credit, never a gate (see The micro trade-offs); a trade "
        "with no micro bar at its entry minute gets no micro leg, and "
        "a top-up never exceeds half the minute's printed volume. A "
        "refused entry here means even ONE MICRO did not fit the "
        "budget."
        if micro else "")
    lede = (
        f"<b>{esc(variant)}</b>"
        + (" (the published baseline, 4th/5th stop, band 000-060)"
           if is_base else " (the hybrid stop, band 020-060)"
           if variant == "variant 5" else "")
        + micro_lede
        + f": its {len(all_trades)} live-universe "
        f"trades (the 22 futures we trade; ETF and non-updated markets "
        f"dropped before the replay), "
        f"deployed in integer contracts at five starting capitals "
        f"({', '.join(cap_label(c) for c in CAPITALS)}), all under the "
        f"refusal policy: an order whose single contract risks more "
        f"than 1% of equity at that moment is refused, never forced, "
        f"and released as the account grows. Execution costs "
        f"(commission + exchange + NFA, both sides; taxes excluded) are "
        f"in every curve. A taken trade&rsquo;s R never changes down "
        f"the ladder &mdash; only which trades fit, what they risked "
        f"and what they paid.")
    footer = (
        f"quickfix1m1dc capital ladder for {esc(variant)}, built from "
        f"{source} and data_center's "
        f"contract_specs.json by build_1m_capital_report.py; sizing "
        f"policy and costs: research_1m_sizing.py / execution_costs.py "
        f"(sourced 2026-09-01). All times UTC. Rebuilt by refresh step "
        f"capitals1m.")

    out_html = out_path(variant, micro)
    html = (PAGE
            .replace("__VNAME__", esc(variant)
                     + (" &middot; micro stacks" if micro else ""))
            .replace("__CSS__", CSS)
            .replace("__LEDE__", lede)
            .replace("__ARSENAL__", arsenal_html(payload)
                     + (tradeoffs_html(gates, payload) if micro else "")
                     + costs_html(payload)
                     + hardness_html(all_trades, payload))
            .replace("__TREND__", trend_html(ladder, len(all_trades),
                                             all_trades))
            .replace("__SECTIONS__", "".join(sections))
            .replace("__FOOTER__", footer)
            .replace("__LIB__", LIB_PATH.read_text(encoding="utf-8"))
            .replace("__JS__", PAGE_JS.replace(
                "__SECTIONS__",
                json.dumps(series, separators=(",", ":")))))
    out_html.write_text(html, encoding="utf-8")
    print(f"{variant}{' [micro]' if micro else ''}:")
    for r in ladder:
        print(f"  {cap_label(r['cap']):>6}: {len(r['money_of'])} taken, "
              f"{len(r['refused'])} missed, final ${r['final']:,.0f}, "
              f"DD {r['max_dd']:.2f}%")
    print(f"capital ladder -> {out_html.name} "
          f"({out_html.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    # One page per published configuration; the old single-variant
    # filename is retired (renamed to _variant_02, Lode 2026-09-02).
    stale = OUT_DIR / "quickfix1m1dc_capitals.html"
    if stale.exists():
        stale.unlink()
        print(f"removed stale {stale.name} (renamed to "
              f"{out_path(run_1m_matrix.BASELINE_NAME).name})")
    for v in VARIANTS:
        build(v)
    # The micro ladders need the measured gates; without them the
    # micro pages are SKIPPED with a note, never built on assumptions.
    if GATES_JSON.exists():
        for v in VARIANTS:
            build(v, micro=True)
    else:
        print("micro ladders skipped: no "
              f"{GATES_JSON.name} (run research_1m_micro.py)")
