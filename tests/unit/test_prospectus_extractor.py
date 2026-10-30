from src.documents.extractor import extract_candidate_evidence_from_pages


def test_prospectus_extractor_returns_page_cited_unverified_candidates():
    pages = [
        "RISK FACTORS\nThe issuer faces industry risk.",
        "Statement of Profit and Loss\nRevenue from operations 1,250.50\nProfit after tax 125.25\nEarnings per share 12.50",
        "Cash flow statement\nNet cash generated from operating activities 90.00",
    ]
    result = extract_candidate_evidence_from_pages(
        pages,
        source_url="https://www.nseindia.com/example-rhp.pdf",
        document_hash="a" * 64,
        extracted_at="2026-10-29T00:00:00+00:00",
    )
    fields = {item["field_name"] for item in result}
    assert "revenue_from_operations" in fields
    assert "profit_after_tax" in fields
    assert "earnings_per_share" in fields
    assert "operating_cash_flow" in fields
    revenue = next(item for item in result if item["field_name"] == "revenue_from_operations")
    assert revenue["page_number"] == 2
    assert revenue["document_hash"] == "a" * 64
    assert revenue["value"] is None
    assert revenue["extraction_status"] == "CANDIDATE_UNVERIFIED"
    assert revenue["source_url"].startswith("https://")


def test_prospectus_extractor_deduplicates_repeated_snippets():
    result = extract_candidate_evidence_from_pages(
        ["Revenue from operations 100\nRevenue from operations 100"],
        source_url="https://www.sebi.gov.in/example.pdf",
        document_hash="b" * 64,
        extracted_at="2026-10-29T00:00:00+00:00",
    )
    revenue = [item for item in result if item["field_name"] == "revenue_from_operations"]
    assert len(revenue) == 1
