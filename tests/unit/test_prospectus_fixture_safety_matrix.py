"""Synthetic prospectus-layout regression matrix.

These fixtures mimic common Indian IPO filing table conventions but contain
invented values and are not evidence about any real issuer.
"""
from decimal import Decimal

import pytest

from src.documents.financial_normalization import (
    build_financial_candidate,
    normalize_to_inr_crore,
    parse_numeric_value,
)
from src.verification.financial_evidence import reconcile_financial_candidates


@pytest.fixture
def synthetic_statement_rows():
    return [
        {
            "row_label": "Revenue from operations",
            "columns": [
                {"header": "FY 2023-24", "raw": "12,450.75"},
                {"header": "FY 2024-25", "raw": "14,100.00"},
            ],
            "context": "Consolidated statement of profit and loss (₹ in lakhs)",
        },
        {
            "row_label": "Profit/(loss) for the year",
            "columns": [
                {"header": "FY 2023-24", "raw": "(125.50)"},
                {"header": "FY 2024-25", "raw": "—"},
            ],
            "context": "Standalone statement of profit and loss (₹ in lakhs)",
        },
    ]


def test_synthetic_multi_year_statement_keeps_period_basis_and_units_separate(synthetic_statement_rows):
    revenue = synthetic_statement_rows[0]
    candidates = [
        build_financial_candidate(
            field_name="revenue_from_operations",
            raw_value=column["raw"],
            row_label=revenue["row_label"],
            header_context=f'{revenue["context"]} {column["header"]}',
            source_url="https://example.invalid/synthetic-rhp.pdf",
            document_hash="a" * 64,
            page_number=42,
        )
        for column in revenue["columns"]
    ]

    assert [item["period"]["label"] for item in candidates] == ["FY2023-2024", "FY2024-2025"]
    assert all(item["statement_basis"] == "CONSOLIDATED" for item in candidates)
    assert [Decimal(item["normalized_value_inr_crore"]) for item in candidates] == [
        Decimal("124.5075"),
        Decimal("141.0000"),
    ]
    assert all(item["verification_status"] == "CANDIDATE_UNVERIFIED" for item in candidates)


def test_negative_and_dash_cells_are_not_mistaken_for_positive_financial_values(synthetic_statement_rows):
    loss_row = synthetic_statement_rows[1]
    negative = normalize_to_inr_crore(loss_row["columns"][0]["raw"], loss_row["context"])
    dash = normalize_to_inr_crore(loss_row["columns"][1]["raw"], loss_row["context"])

    assert Decimal(negative["value_inr_crore"]) == Decimal("-1.2550")
    assert negative["status"] == "CANDIDATE_UNVERIFIED"
    assert dash["parsed_value"] is None
    assert dash["value_inr_crore"] is None
    assert parse_numeric_value("(125.50)") == Decimal("-125.50")


def test_ambiguous_unit_period_or_basis_stays_unresolved():
    no_unit = normalize_to_inr_crore("14,100", "Consolidated FY 2024-25 Revenue from operations")
    assert no_unit["value_inr_crore"] is None

    ambiguous = build_financial_candidate(
        field_name="revenue_from_operations",
        raw_value="14,100",
        row_label="Revenue from operations",
        header_context="FY 2024-25 financial results (₹)",
        source_url="https://example.invalid/synthetic-rhp.pdf",
        document_hash="b" * 64,
        page_number=42,
    )
    report = reconcile_financial_candidates([ambiguous])
    assert report["unresolved_count"] == 1
    assert report["groups"] == []
    assert report["assessment_eligible"] is False


def test_conflicting_synthetic_values_are_reported_without_selecting_a_winner():
    def candidate(value, url):
        return {
            "field_name": "revenue_from_operations",
            "normalized_value_inr_crore": value,
            "period": {"period_type": "FINANCIAL_YEAR", "label": "FY2024-2025"},
            "statement_basis": "CONSOLIDATED",
            "source_url": url,
            "document_hash": (url.rsplit("/", 1)[-1].replace(".pdf", "") + "0" * 64)[:64],
            "page_number": 42,
            "verification_status": "CANDIDATE_UNVERIFIED",
        }

    report = reconcile_financial_candidates([
        candidate("141.00", "https://example.invalid/source-a.pdf"),
        candidate("142.00", "https://example.invalid/source-b.pdf"),
    ])

    assert report["conflict_count"] == 1
    assert report["groups"][0]["status"] == "CONFLICT"
    assert report["assessment_eligible"] is False
    assert report["verification_status"] == "CANDIDATE_UNVERIFIED"
    assert {item["normalized_value_inr_crore"] for item in report["groups"][0]["candidates"]} == {
        "141.00", "142.00"
    }
