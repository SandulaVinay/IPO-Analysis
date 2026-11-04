"""Tests for multi-format financial-results attachment detection and extraction."""
from src.results.document_extractors import (
    detect_document_format,
    extract_html_tables,
    extract_ixbrl_as_xbrl,
    extract_structured_document,
)


def test_detects_pdf_by_signature():
    assert detect_document_format(b"%PDF-1.7\n") == "pdf"


def test_detects_csv_and_extracts_rows():
    result = extract_structured_document(b"Metric,Sep 2026\nRevenue,100\n", "text/csv", "filing.csv")
    assert result["status"] == "EXTRACTED"
    assert result["format"] == "csv"
    assert result["rows"][1] == ["Revenue", "100"]


def test_html_tables_are_reviewable():
    result = extract_html_tables(b"<html><table><tr><th>Metric</th></tr><tr><td>Revenue</td></tr></table></html>")
    assert result["status"] == "EXTRACTED"
    assert result["tables"][0][1][0] == "Revenue"


def test_rejects_xxe_in_inline_xbrl():
    malicious = b'<!DOCTYPE html [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><html></html>'
    import pytest
    with pytest.raises(ValueError, match="prohibited DTD/entity"):
        extract_ixbrl_as_xbrl(malicious)


def test_unrecognized_payload_fails_closed():
    result = extract_structured_document(b"not a financial filing")
    assert result["status"] == "UNAVAILABLE"


def test_screener_fallback_requires_matching_issuer_and_period():
    from src.results.document_extractors import extract_screener_quarter_metrics
    html = b"""<html><head><title>Clean Science and Technology Ltd share price</title></head>
    <body><table><tr><th>Particulars</th><th>Sep 2026</th></tr>
    <tr><td>Sales</td><td>250.5</td></tr><tr><td>Net Profit</td><td>44.2</td></tr>
    <tr><td>EPS</td><td>4.5</td></tr></table></body></html>"""
    result = extract_screener_quarter_metrics(html, "Clean Science and Technology Limited", "30-Sep-2026")
    assert result["status"] == "EXTRACTED"
    assert result["source_status"] == "FALLBACK"
    assert result["revenue_cr"] == 250.5
    assert result["pat_cr"] == 44.2


def test_screener_fallback_rejects_wrong_issuer():
    from src.results.document_extractors import extract_screener_quarter_metrics
    result = extract_screener_quarter_metrics(
        b"<html><head><title>Unrelated Industries</title></head></html>",
        "Clean Science and Technology Limited", "30-Sep-2026",
    )
    assert result["status"] == "UNAVAILABLE"
