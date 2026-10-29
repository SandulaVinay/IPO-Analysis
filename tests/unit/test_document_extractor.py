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
