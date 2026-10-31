from src.results.email_analysis import build_results_email


def test_email_has_professional_greeting_subject_and_analyst_sections():
    item = {
        "company_name": "Example Limited",
        "symbol": "EXAMPLE",
        "exchange": "NSE",
        "period_ended": "2026-09-30",
        "relating_to": "Second Quarter",
        "broadcast_time": "30-Oct-2026 18:00",
        "consolidation": "Consolidated",
        "attachment_url": "https://example.com/results.xml",
    }
    metrics = {
        "status": "EXTRACTED",
        "revenue_cr": 120.0,
        "pat_cr": 8.0,
        "eps": 2.5,
        "cfo_cr": -3.0,
        "revenue_yoy_pct": 10.0,
        "pat_yoy_pct": -20.0,
        "revenue_qoq_pct": -5.0,
        "pat_qoq_pct": -15.0,
    }

    subject, body = build_results_email(item, metrics, "https://github.com/example/run")

    assert "Financial Results Alert" in subject
    assert "Example Limited (EXAMPLE)" in subject
    assert body.startswith("Dear Investor,")
    assert "ANALYST INTERPRETATION" in body
    assert "year-on-year (YoY)" in body
    assert "quarter-on-quarter (QoQ)" in body
    assert "PAT declined YoY" in body
    assert "Revenue declined QoQ" in body
    assert "Operating cash flow is negative despite positive PAT" in body
    assert "Kind regards," in body
    assert "not a buy/sell recommendation" in body


def test_unavailable_metrics_do_not_invent_growth_or_performance_verdict():
    subject, body = build_results_email(
        {"company_name": "Example Limited", "symbol": "EXAMPLE", "source_url": "https://example.com/filing"},
        {"status": "UNAVAILABLE", "reason": "No supported XBRL facts."},
    )

    assert subject.startswith("Financial Results Alert")
    assert body.startswith("Dear Investor,")
    assert "Automated financial metrics could not be reliably extracted" in body
    assert "No growth, decline, or investment conclusion is inferred" in body
    assert "Not available" not in body
