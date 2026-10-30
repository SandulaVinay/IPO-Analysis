from src.reporting.generator import ReportGenerator


def test_unverified_ipo_status_reports_never_claim_verified_confidence_or_scores():
    data = {
        "symbol": "TEST",
        "company_name": "Test Issuer Limited",
        "confidence_level": "NOT_ASSESSED",
        "source_verification_status": "NOT_VERIFIED",
        "ipo": {
            "symbol": "TEST",
            "company_name": "Test Issuer Limited",
            "verified_open_date": None,
            "verified_close_date": None,
            "min_price": None,
            "max_price": None,
            "lot_size": None,
            "issue_size_cr": None,
            "fresh_issue_cr": None,
            "ofs_cr": None,
        },
        "score_data": {
            "verdict": "UNABLE_TO_ASSESS",
            "overall_score": None,
            "pillar_scores": {},
            "horizons": {},
        },
        "gmp": {"gmp_value": None},
    }

    executive = ReportGenerator.generate_executive_summary(data)
    full = ReportGenerator.generate_full_report(data)
    copy = ReportGenerator.generate_copy_mode(data)

    assert "UNABLE_TO_ASSESS" in executive
    assert "NOT_ASSESSED" in executive
    assert "N/A" in executive
    assert "Source Verification**: NOT_VERIFIED" in full
    assert "Confidence**: NOT_ASSESSED" in full
    assert "UNABLE_TO_ASSESS" in full
    assert "UNABLE_TO_ASSESS" in copy
    assert "NOT_ASSESSED" in copy
    assert "NOT_VERIFIED" in copy
    assert "Minimum Investment:\n₹N/A" in copy
