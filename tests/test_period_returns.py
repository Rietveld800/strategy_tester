"""Monthly / weekly / daily performance (Lode, 2026-09-24; CLAUDE.md, the
contracts pages): the pure period aggregation the bars are drawn from."""
import build_1m_report as rep


DAYS = ["2026-08-28", "2026-08-31", "2026-09-01", "2026-09-04", "2026-09-07",
        "2026-09-08", "2026-10-01"]
EQ = [250_000.0, 252_500.0, 252_500.0, 247_450.0, 247_450.0, 250_000.0, 250_000.0]


def test_months_compound_from_the_start_balance_and_a_flat_month_reads_zero():
    rows = rep.period_returns(DAYS, EQ, 250_000.0, "month")
    assert [r[0] for r in rows] == ["Aug 2026", "Sep 2026", "Oct 2026"]
    assert rows[0][2] == 1.0                      # 250,000 -> 252,500
    assert round(rows[1][2], 4) == round((250_000 - 252_500) / 252_500 * 100, 4)
    assert rows[2][2] == 0.0                      # a market day, nothing booked


def test_weeks_are_iso_weeks_with_their_monday_under_the_bar():
    rows = rep.period_returns(DAYS, EQ, 250_000.0, "week")
    assert [(r[0], r[1]) for r in rows] == [
        ("W35", "24 Aug"), ("W36", "31 Aug"), ("W37", "07 Sep"), ("W40", "28 Sep")]
    assert rows[1][2] == round((247_450 - 250_000) / 250_000 * 100, 4)


def test_days_are_market_days_each_against_the_close_before():
    rows = rep.period_returns(DAYS, EQ, 250_000.0, "day")
    assert len(rows) == len(DAYS) and rows[0][0] == "28 Aug" and rows[0][1] == "Fri"
    assert rows[0][2] == 0.0 and rows[1][2] == 1.0
    assert rows[3][2] == round((247_450 - 252_500) / 252_500 * 100, 4)
    assert rep.period_returns([], [], 250_000.0, "day") == []


def test_the_html_carries_three_sections_with_signed_percentages_and_tones():
    html = rep.periods_html(DAYS, EQ, 250_000.0)
    for title in ("Monthly performance", "Weekly performance", "Daily performance"):
        assert f'<div class="section-h">{title}</div>' in html
    assert 'class="pcol pos"' in html and 'class="pcol neg"' in html and 'class="pcol flat"' in html
    assert "+1.0%" in html and "-2.00%" in html
    assert "<script" not in html
    assert rep.periods_html([], [], 250_000.0) == ""
