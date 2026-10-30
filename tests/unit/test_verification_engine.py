from datetime import date

from src.verification.engine import VerificationEngine


def test_completeness_does_not_count_unverified_numeric_ipo_fields():
    ipo_data = {
        "verified_open_date": date(2026, 11, 1),
        "verified_close_date": date(2026, 11, 5),
        "min_price": 100,
        "max_price": 120,
        "lot_size": 100,
        "issue_size_cr": 500,
        "fresh_issue_cr": 300,
        "revenue_latest": 1000,
        "pat_latest": 100,
        "cfo_latest": 90,
    }
    result = VerificationEngine.evaluate_ipo_completeness(ipo_data, [])
    assert result["completeness_pct"] == 20.0
    assert result["verified_sources_count"] == 0
    assert result["confidence_level"] == "LOW"
    assert "revenue_latest" in result["missing_critical_fields"]


def test_completeness_counts_only_provenance_bearing_verified_facts():
    fields = [
        "min_price", "max_price", "lot_size", "issue_size_cr", "fresh_issue_cr",
        "revenue_latest", "pat_latest", "cfo_latest",
    ]
    facts = [
        {"field_name": field, "verification_status": "VERIFIED", "source_name": "OFFICIAL_RHP", "source_url": "https://www.sebi.gov.in/example-rhp.pdf"}
        for field in fields
    ]
    result = VerificationEngine.evaluate_ipo_completeness(
        {"verified_open_date": date(2026, 11, 1), "verified_close_date": date(2026, 11, 5)},
        facts,
    )
    assert result["completeness_pct"] == 100.0
    assert result["verified_sources_count"] == 1
    assert result["confidence_level"] == "HIGH"



def test_verified_fact_without_source_name_does_not_count_as_verified_source():
    result = VerificationEngine.evaluate_ipo_completeness(
        {},
        [{"field_name": "revenue_latest", "verification_status": "VERIFIED"}],
    )
    assert result["verified_sources_count"] == 0
    assert result["completeness_pct"] == 0.0
