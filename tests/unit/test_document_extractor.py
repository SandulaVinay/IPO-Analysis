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
