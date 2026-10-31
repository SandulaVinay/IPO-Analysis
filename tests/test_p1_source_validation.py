"""Regression tests for official NSE/BSE result-source parsing and safe extraction."""

from datetime import date
import pytest

from src.results.monitor import (
    extract_pdf_text,
    extract_xbrl_metrics,
    parse_bse_financial_results_payload,
    parse_nse_financial_results_payload,
)


def test_nse_parser_requires_exact_symbol_and_issuer_name():
    company = {
        "symbol": "TCS",
        "company_name": "Tata Consultancy Services Limited",
        "company_name_aliases": ["Tata Consultancy Services Ltd"],
    }
    payload = {"data": [
        {
            "symbol": "TCS",
            "companyName": "Tata Consultancy Services Limited",
            "toDate": "30-Sep-2026",
            "relatingTo": "Quarterly",
            "broadCastDate": "-",
            "filingDate": "30-Oct-2026 18:30:00",
            "format": "XBRL",
            "xbrl": "https://www.nseindia.com/xbrl/example.xml",
        },
        {
            "symbol": "TCS",
            "companyName": "A Different Company Limited",
            "toDate": "30-Sep-2026",
            "broadCastDate": "30-Oct-2026 18:30:00",
        },
        {
            "symbol": "WRONG",
            "companyName": "Tata Consultancy Services Limited",
            "toDate": "30-Sep-2026",
            "broadCastDate": "30-Oct-2026 18:30:00",
        },
    ]}

    rows = parse_nse_financial_results_payload(payload, "TCS", company, "Quarterly")

    assert len(rows) == 1
    assert rows[0]["company_name"] == "Tata Consultancy Services Limited"
    assert rows[0]["broadcast_time"] == "30-Oct-2026 18:30:00"
    assert rows[0]["xbrl_url"] == "https://www.nseindia.com/xbrl/example.xml"


def test_bse_parser_requires_exact_scrip_and_issuer_and_builds_official_attachment_url():
    company = {
        "symbol": "RNIT",
        "company_name": "RNIT AI Solutions Limited",
        "company_name_aliases": [],
    }
    payload = {"Table": [
        {
            "SCRIP_CD": "517286",
            "SLONGNAME": "RNIT AI Solutions Limited",
            "NEWSSUB": "Financial Results for quarter ended",
            "SUBCATNAME": "Financial Results",
            "DT_TM": "30-Oct-2026 18:30:00",
            "NEWSID": "12345",
            "ATTACHMENTNAME": "sample.pdf",
            "NSURL": "https://www.bseindia.com/corporates/ann.html",
        },
        {
            "SCRIP_CD": "000001",
            "SLONGNAME": "RNIT AI Solutions Limited",
            "NEWSSUB": "Financial Results",
            "SUBCATNAME": "Financial Results",
            "NEWSID": "wrong-code",
        },
        {
            "SCRIP_CD": "517286",
            "SLONGNAME": "Another Issuer Limited",
            "NEWSSUB": "Financial Results",
            "SUBCATNAME": "Financial Results",
            "NEWSID": "wrong-name",
        },
    ]}

    rows = parse_bse_financial_results_payload(payload, "RNIT", company, "517286")

    assert len(rows) == 1
    assert rows[0]["exchange"] == "BSE"
    assert rows[0]["bse_scrip_code"] == "517286"
    assert rows[0]["attachment_url"] == (
        "https://www.bseindia.com/xml-data/corpfiling/AttachLive/sample.pdf"
    )


def test_xbrl_rejects_entity_declarations():
    with pytest.raises(ValueError, match="prohibited DTD/entity"):
        extract_xbrl_metrics(
            b'<!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><x>&xxe;</x>',
            "2026-09-30",
            "Quarterly",
        )


def test_xbrl_reports_unavailable_for_unparseable_period():
    result = extract_xbrl_metrics(b"<xbrl/>", "not-a-period", "Quarterly")
    assert result["status"] == "UNAVAILABLE"
    assert "Period end date" in result["reason"]


def test_pdf_extraction_rejects_non_pdf_attachment():
    result = extract_pdf_text(b"not a PDF")
    assert result["status"] == "UNAVAILABLE"
    assert "PDF signature" in result["reason"]
