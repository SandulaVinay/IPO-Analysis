from src.documents.extractor import extract_candidate_evidence_from_tables


def test_financial_table_rows_are_candidates_not_parsed_values():
    tables_by_page = [[[
        ["Particulars", "FY 2024", "FY 2025"],
        ["Revenue from operations", "100.00", "120.00"],
        ["Profit after tax", "10.00", "12.00"],
    ]]]
    evidence = extract_candidate_evidence_from_tables(
        tables_by_page,
        source_url="https://www.nseindia.com/example-rhp.pdf",
        document_hash="a" * 64,
    )
    assert len(evidence) == 2
    revenue = next(item for item in evidence if item["field_name"] == "revenue_from_operations")
    assert "FY 2024" in revenue["evidence_text"]
    assert "100.00" in revenue["evidence_text"]
    assert "120.00" in revenue["evidence_text"]
    assert "10.00" not in revenue["evidence_text"]
    assert revenue["extraction_method"] == "TABLE_ROW_CANDIDATE"
    assert revenue["extraction_status"] == "CANDIDATE_UNVERIFIED"
    assert revenue["value"] is None



def test_pdf_extractor_adds_table_row_candidates_when_tables_are_detectable():
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
    from src.documents.extractor import extract_pdf_candidate_evidence

    buffer = BytesIO()
    document = SimpleDocTemplate(buffer)
    table = Table([
        ["Particulars", "FY 2024", "FY 2025"],
        ["Revenue from operations", "100.00", "120.00"],
        ["Profit after tax", "10.00", "12.00"],
    ])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
    ]))
    document.build([table])
    result = extract_pdf_candidate_evidence(
        buffer.getvalue(),
        source_url="https://www.nseindia.com/example-rhp.pdf",
    )
    table_candidates = [item for item in result["evidence"] if item.get("extraction_method") == "TABLE_ROW_CANDIDATE"]
    assert table_candidates
    assert all(item["extraction_status"] == "CANDIDATE_UNVERIFIED" for item in table_candidates)


def test_financial_table_candidates_normalize_explicit_units_without_verifying():
    evidence = extract_candidate_evidence_from_tables(
        [[
            [
                ["Particulars (Consolidated; ₹ in lakhs)", "FY 2024", "FY 2025"],
                ["Revenue from operations", "1,000.00", "1,250.00"],
            ]
        ]],
        source_url="https://www.nseindia.com/example-rhp.pdf",
        document_hash="c" * 64,
    )
    revenue = next(item for item in evidence if item["field_name"] == "revenue_from_operations")
    candidates = revenue["financial_candidates"]
    assert len(candidates) == 2
    fy24, fy25 = candidates
    assert fy24["period"]["label"] == "FY2024"
    assert fy25["period"]["label"] == "FY2025"
    assert fy24["statement_basis"] == "CONSOLIDATED"
    assert fy24["unit"] == "lakh"
    assert fy24["normalized_value_inr_crore"] == "10.0000"
    assert fy25["normalized_value_inr_crore"] == "12.5000"
    assert all(item["verification_status"] == "CANDIDATE_UNVERIFIED" for item in candidates)
    assert all(item["source_url"] == "https://www.nseindia.com/example-rhp.pdf" for item in candidates)


def test_financial_table_candidates_do_not_guess_missing_units():
    evidence = extract_candidate_evidence_from_tables(
        [[
            [
                ["Particulars", "FY 2024", "FY 2025"],
                ["Revenue from operations", "1,000.00", "1,250.00"],
            ]
        ]],
        source_url="https://www.nseindia.com/example-rhp.pdf",
        document_hash="d" * 64,
    )
    revenue = next(item for item in evidence if item["field_name"] == "revenue_from_operations")
    assert all(item["normalized_value_inr_crore"] is None for item in revenue["financial_candidates"])
    assert all(item["verification_status"] == "CANDIDATE_UNVERIFIED" for item in revenue["financial_candidates"])



def test_stacked_financial_headers_preserve_each_year_unit_and_basis():
    evidence = extract_candidate_evidence_from_tables(
        [[[
            ["Consolidated statement of profit and loss (₹ in lakhs)", "", ""],
            ["", "Audited", "Audited"],
            ["Particulars", "FY 2023-24", "FY 2024-25"],
            ["Revenue from operations", "12,450.75", "14,100.00"],
        ]]],
        source_url="https://www.nseindia.com/example-rhp.pdf",
        document_hash="e" * 64,
    )
    revenue = next(item for item in evidence if item["field_name"] == "revenue_from_operations")
    fy23, fy24 = revenue["financial_candidates"]

    assert fy23["period"]["label"] == "FY2023-2024"
    assert fy24["period"]["label"] == "FY2024-2025"
    assert fy23["statement_basis"] == "CONSOLIDATED"
    assert fy24["statement_basis"] == "CONSOLIDATED"
    assert fy23["unit"] == fy24["unit"] == "lakh"
    assert fy23["normalized_value_inr_crore"] == "124.5075"
    assert fy24["normalized_value_inr_crore"] == "141.0000"
    assert fy23["verification_status"] == fy24["verification_status"] == "CANDIDATE_UNVERIFIED"


def test_sebi_hosted_prospectus_kpi_layout_skips_percent_columns():
    """Regression fixture transcribed from a SEBI-hosted prospectus table layout.

    This is source-derived table text, not a bundled PDF or independent financial
    verification. The parser must separate currency columns from adjacent percentages.
    Source: https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1758005828714.pdf
    """
    evidence = extract_candidate_evidence_from_tables(
        [[[
            ["Particulars", "Financial Year", "", "", "", "", ""],
            ["", "2025", "2025", "2024", "2024", "2023", "2023"],
            ["", "(₹ in millions)", "% of Total Income", "(₹ in millions)", "% of Total Income", "(₹ in millions)", "% of Total Income"],
            ["Revenue from Operations", "9,226.80", "97.91", "7,802.30", "98.12", "7,968.25", "98.89"],
        ]]],
        source_url="https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1758005828714.pdf",
        document_hash="fixture-only-no-downloaded-pdf-hash",
    )
    revenue = next(item for item in evidence if item["field_name"] == "revenue_from_operations")
    candidates = revenue["financial_candidates"]

    assert len(candidates) == 3
    assert [item["period"]["label"] for item in candidates] == ["FY2025", "FY2024", "FY2023"]
    assert [item["raw_value"] for item in candidates] == ["9,226.80", "7,802.30", "7,968.25"]
    assert [item["unit"] for item in candidates] == ["million", "million", "million"]
    assert [item["normalized_value_inr_crore"] for item in candidates] == ["922.680", "780.230", "796.825"]
    assert all(item["statement_basis"] is None for item in candidates)
    assert all(item["verification_status"] == "CANDIDATE_UNVERIFIED" for item in candidates)
