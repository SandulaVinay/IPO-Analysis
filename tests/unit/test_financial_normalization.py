from decimal import Decimal

from src.documents.financial_normalization import (
    CANDIDATE_STATUS,
    build_financial_candidate,
    detect_explicit_unit,
    identify_financial_period,
    identify_statement_basis,
    normalize_to_inr_crore,
    parse_numeric_value,
)


def test_parse_indian_number_and_parentheses_negative():
    assert parse_numeric_value("1,23,456.75") == Decimal("123456.75")
    assert parse_numeric_value("(1,234.50)") == Decimal("-1234.50")
    assert parse_numeric_value("—") is None
    assert parse_numeric_value("not-a-number") is None


def test_normalization_requires_explicit_unit():
    missing_unit = normalize_to_inr_crore("125.5", "Revenue from operations")
    assert missing_unit["value_inr_crore"] is None
    assert missing_unit["status"] == CANDIDATE_STATUS
    assert "Unit is not explicit" in missing_unit["reason"]

    lakh_value = normalize_to_inr_crore("(1,250.5)", "(₹ in lakhs)")
    assert Decimal(lakh_value["value_inr_crore"]) == Decimal("-12.505")
    assert lakh_value["unit"] == "lakh"
    assert lakh_value["status"] == CANDIDATE_STATUS


def test_unit_detector_does_not_guess_currency_scale():
    assert detect_explicit_unit("Amounts in ₹ crore") == "crore"
    assert detect_explicit_unit("₹ in millions") == "million"
    assert detect_explicit_unit("Revenue (₹)") is None


def test_statement_basis_requires_one_unambiguous_marker():
    assert identify_statement_basis("Consolidated statement of profit and loss") == "CONSOLIDATED"
    assert identify_statement_basis("Standalone financial results") == "STANDALONE"
    assert identify_statement_basis("Financial results") is None
    assert identify_statement_basis("Standalone and consolidated results") is None


def test_period_parser_only_accepts_explicit_fy_labels():
    assert identify_financial_period("For FY 2024-25") == {
        "period_type": "FINANCIAL_YEAR", "label": "FY2024-2025"
    }
    assert identify_financial_period("FY2025") == {
        "period_type": "FINANCIAL_YEAR", "label": "FY2025"
    }
    assert identify_financial_period("Year ended 31 March") is None
    assert identify_financial_period("2024-2026") is None


def test_candidate_retains_provenance_and_never_marks_verified():
    candidate = build_financial_candidate(
        field_name="revenue_from_operations",
        raw_value="12,500",
        row_label="Revenue from operations",
        header_context="FY 2024-25 consolidated (₹ in lakhs)",
        source_url="https://example.com/filing.pdf",
        document_hash="abc123",
        page_number=12,
    )
    assert candidate["source_url"] == "https://example.com/filing.pdf"
    assert candidate["document_hash"] == "abc123"
    assert candidate["page_number"] == 12
    assert candidate["period"]["label"] == "FY2024-2025"
    assert candidate["statement_basis"] == "CONSOLIDATED"
    assert candidate["normalized_value_inr_crore"] == "125.00"
    assert candidate["verification_status"] == "CANDIDATE_UNVERIFIED"
