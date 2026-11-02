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


def test_table_candidates_use_page_context_for_unit_and_consolidated_basis():
    from src.documents.extractor import extract_candidate_evidence_from_tables

    table = [
        ["Particulars", "Notes", "For the Six months ended September 30,2024", "For the Year ended March 31,2024"],
        ["Revenue from operations", "23", "1,721.50", "2,865.18"],
        ["Profit/(loss) for the period / year [A]", "", "239.34", "136.10"],
    ]
    page_context = (
        "ESDS Software Solution Limited Restated Consolidated Statement of Profit and Loss. "
        "All amounts are in Rupees million, unless otherwise stated."
    )
    evidence = extract_candidate_evidence_from_tables(
        [[table]],
        source_url="https://www.sebi.gov.in/sebi_data/attachdocs/apr-2025/1743751804884_762.pdf",
        document_hash="f" * 64,
        page_contexts=[page_context],
    )
    candidates = [
        candidate
        for item in evidence
        for candidate in item.get("financial_candidates", [])
    ]
    revenue = next(
        candidate for candidate in candidates
        if candidate["field_name"] == "revenue_from_operations"
        and candidate["raw_value"] == "2,865.18"
    )
    assert revenue["unit"] == "million"
    assert revenue["period"]["label"] == "FY2023-2024"
    assert revenue["statement_basis"] == "CONSOLIDATED"
    assert revenue["normalized_value_inr_crore"] == "286.518"
    assert revenue["verification_status"] == "CANDIDATE_UNVERIFIED"

    pat = next(
        candidate for candidate in candidates
        if candidate["field_name"] == "profit_after_tax"
        and candidate["raw_value"] == "136.10"
    )
    assert pat["period"]["label"] == "FY2023-2024"
    assert pat["normalized_value_inr_crore"] == "13.610"
    assert pat["verification_status"] == "CANDIDATE_UNVERIFIED"

    cashflow_table = [
        ["Particulars", "For the Year ended March 31,2024"],
        ["Net cash inflows/ (outflows) from operating activities", "455.77"],
    ]
    cashflow_evidence = extract_candidate_evidence_from_tables(
        [[cashflow_table]],
        source_url="https://www.sebi.gov.in/sebi_data/attachdocs/apr-2025/1743751804884_762.pdf",
        document_hash="f" * 64,
        page_contexts=[
            "ESDS Software Solution Limited Restated Consolidated Statement of Cashflow. "
            "All amounts are in Rupees million, unless otherwise stated."
        ],
    )
    cashflow_candidates = [
        candidate
        for item in cashflow_evidence
        for candidate in item.get("financial_candidates", [])
    ]
    ocf = next(
        candidate for candidate in cashflow_candidates
        if candidate["field_name"] == "operating_cash_flow"
        and candidate["raw_value"] == "455.77"
    )
    assert ocf["unit"] == "million"
    assert ocf["period"]["label"] == "FY2023-2024"
    assert ocf["statement_basis"] == "CONSOLIDATED"
    assert ocf["normalized_value_inr_crore"] == "45.577"
    assert ocf["verification_status"] == "CANDIDATE_UNVERIFIED"


def test_statement_text_fallback_maps_realistic_fy_columns_and_keeps_candidates_unverified():
    from src.documents.extractor import extract_candidate_evidence_from_statement_text

    pnl_page = """
    ESDS Software Solution Limited
    Restated Consolidated Statement of Profit and Loss
    All amounts are in Rupees million, unless otherwise stated
    For the Six months ended September 30,2024
    For the Year ended March 31,2024
    For the Year ended March 31,2023
    For the Year ended March 31,2022
    Revenue from operations 23 1,721.50 2,865.18 2,075.66 1,953.58
    Profit/(loss) for the period / year [A] 239.34 136.10 (224.60) (26.63)
    """
    cashflow_page = """
    ESDS Software Solution Limited
    Restated Consolidated Statement of Cashflow
    All amounts are in Rupees million, unless otherwise stated
    For the Six months ended September 30,2024
    For the Year ended March 31,2024
    For the Year ended March 31,2023
    For the Year ended March 31,2022
    Net cash inflows/ (outflows) from operating activities 498.30 455.77 564.54 577.70
    """
    evidence = extract_candidate_evidence_from_statement_text(
        [pnl_page, cashflow_page],
        source_url="https://www.sebi.gov.in/sebi_data/attachdocs/apr-2025/1743751804884_762.pdf",
        document_hash="b" * 64,
    )
    candidates = [
        candidate
        for item in evidence
        for candidate in item.get("financial_candidates", [])
    ]
    expected = [
        ("revenue_from_operations", "2,865.18", "286.518", 1),
        ("profit_after_tax", "136.10", "13.610", 1),
        ("operating_cash_flow", "455.77", "45.577", 2),
    ]
    for field, raw_value, normalized, page_number in expected:
        match = next(
            candidate for candidate in candidates
            if candidate["field_name"] == field and candidate["raw_value"] == raw_value
        )
        assert match["period"]["label"] == "FY2023-2024"
        assert match["unit"] == "million"
        assert match["statement_basis"] == "CONSOLIDATED"
        assert match["normalized_value_inr_crore"] == normalized
        assert match["page_number"] == page_number
        assert match["verification_status"] == "CANDIDATE_UNVERIFIED"
