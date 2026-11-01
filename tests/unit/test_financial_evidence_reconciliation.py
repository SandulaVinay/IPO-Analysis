from src.verification.financial_evidence import reconcile_financial_candidates


def candidate(value, source_url, *, field="revenue_from_operations", period="FY2025", basis="CONSOLIDATED"):
    return {
        "field_name": field,
        "raw_value": str(value),
        "normalized_value_inr_crore": str(value),
        "period": {"period_type": "FINANCIAL_YEAR", "label": period},
        "statement_basis": basis,
        "source_url": source_url,
        "document_hash": source_url.rsplit("/", 1)[-1].ljust(64, "0")[:64],
        "page_number": 7,
        "verification_status": "CANDIDATE_UNVERIFIED",
    }


def test_matching_values_from_distinct_urls_remain_unverified():
    result = reconcile_financial_candidates([
        candidate("100.00", "https://nse.example/filing-a.pdf"),
        candidate("100.00", "https://issuer.example/annual-report.pdf"),
    ])
    group = result["groups"][0]
    assert group["status"] == "MATCHING_CANDIDATES_UNVERIFIED"
    assert group["distinct_source_count"] == 2
    assert group["verification_status"] == "CANDIDATE_UNVERIFIED"
    assert result["assessment_eligible"] is False
    assert all(item["verification_status"] == "CANDIDATE_UNVERIFIED" for item in group["candidates"])


def test_different_values_for_same_comparable_key_are_conflicts():
    result = reconcile_financial_candidates([
        candidate("100.00", "https://nse.example/filing-a.pdf"),
        candidate("101.00", "https://issuer.example/annual-report.pdf"),
    ])
    assert result["conflict_count"] == 1
    assert result["groups"][0]["status"] == "CONFLICT"
    assert result["groups"][0]["values_inr_crore"] == ["100.00", "101.00"]


def test_single_source_does_not_count_as_independent_corroboration():
    result = reconcile_financial_candidates([
        candidate("100.00", "https://nse.example/filing-a.pdf"),
        candidate("100.00", "https://nse.example/filing-a.pdf"),
    ])
    assert result["groups"][0]["status"] == "SINGLE_SOURCE_UNCONFIRMED"
    assert result["groups"][0]["distinct_source_count"] == 1


def test_missing_period_basis_unit_or_provenance_stays_unresolved():
    item = candidate("100.00", "https://nse.example/filing-a.pdf")
    item["period"] = None
    item["statement_basis"] = None
    item["normalized_value_inr_crore"] = None
    item["document_hash"] = None
    result = reconcile_financial_candidates([item])
    assert result["unresolved_count"] == 1
    assert result["groups"] == []
    reasons = set(result["unresolved_candidates"][0]["reconciliation_reasons"])
    assert "PERIOD_MISSING_OR_AMBIGUOUS" in reasons
    assert "STATEMENT_BASIS_MISSING_OR_AMBIGUOUS" in reasons
    assert "NORMALIZED_VALUE_UNAVAILABLE" in reasons
    assert "PROVENANCE_INCOMPLETE" in reasons


def test_candidates_for_different_periods_are_never_compared_together():
    result = reconcile_financial_candidates([
        candidate("100.00", "https://nse.example/filing-a.pdf", period="FY2024"),
        candidate("120.00", "https://nse.example/filing-a.pdf", period="FY2025"),
    ])
    assert result["conflict_count"] == 0
    assert result["comparable_group_count"] == 2
    assert {group["period"] for group in result["groups"]} == {"FY2024", "FY2025"}


def test_conflicting_standalone_and_consolidated_values_are_separate_groups():
    result = reconcile_financial_candidates([
        candidate("100.00", "https://nse.example/filing-a.pdf", basis="STANDALONE"),
        candidate("150.00", "https://nse.example/filing-a.pdf", basis="CONSOLIDATED"),
    ])
    assert result["conflict_count"] == 0
    assert result["comparable_group_count"] == 2
