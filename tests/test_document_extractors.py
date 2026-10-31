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
