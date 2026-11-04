from io import BytesIO

from openpyxl import Workbook

from src.results.document_extractors import (
    detect_document_format,
    extract_document,
    extract_financial_metrics_from_tables,
    extract_ixbrl_as_xbrl,
    infer_xbrl_reporting_period,
)


def _annual_item():
    return {
        "period_ended": "31-Mar-2025",
        "period_type": "Annual",
        "relating_to": "Year ended",
        "consolidation": "Consolidated",
    }


def test_annual_csv_metrics_require_explicit_period_unit_and_basis():
    content = (
        "Consolidated Statement of Profit and Loss\n"
        "Particulars,Year ended 31 March 2025,Year ended 31 March 2024\n"
        "Unit,INR in Crores,INR in Crores\n"
        "Revenue from operations,125.50,110.00\n"
        "Profit for the year,12.50,10.00\n"
        "Net cash flows from operating activities,18.25,-4.00\n"
    ).encode()
    parsed = extract_document(content, "text/csv", "https://www.nseindia.com/files/results.csv")
    metrics = extract_financial_metrics_from_tables(
        parsed["tables"], document_text="", item=_annual_item(), document_format=parsed["format"]
    )
    assert parsed["format"] == "csv"
    assert metrics["status"] == "EXTRACTED"
    assert metrics["revenue_cr"] == 125.5
    assert metrics["pat_cr"] == 12.5
    assert metrics["cfo_cr"] == 18.25
    assert metrics["statement_basis"] == "CONSOLIDATED"
    assert metrics["source_status"] == "CANDIDATE_UNVERIFIED"
    assert metrics["assessment_eligible"] is False


def test_quarterly_html_metrics_normalize_lakhs_and_keep_negative_values():
    html = """<!doctype html><html><body>
    <h2>Standalone Financial Results (INR in Lakhs)</h2>
    <table>
      <tr><th>Particulars</th><th>3 months ended 30 September 2026</th><th>3 months ended 30 September 2025</th></tr>
      <tr><td>Revenue from operations</td><td>₹1,234.00</td><td>1,100.00</td></tr>
      <tr><td>Profit for the period</td><td>−125.00</td><td>110.00</td></tr>
    </table></body></html>""".encode("utf-8")
    parsed = extract_document(html, "text/html", "https://www.bseindia.com/result.html")
    item = {
        "period_ended": "30-Sep-2026",
        "period_type": "Quarterly",
        "relating_to": "Second Quarter",
        "consolidation": "Standalone",
    }
    metrics = extract_financial_metrics_from_tables(
        parsed["tables"], document_text=parsed["text"], item=item, document_format=parsed["format"]
    )
    assert parsed["format"] == "html"
    assert metrics["status"] == "EXTRACTED"
    assert metrics["unit"] == "INR_LAKHS"
    assert metrics["revenue_cr"] == 12.34
    assert metrics["pat_cr"] == -1.25
    assert metrics["statement_basis"] == "STANDALONE"


def test_bse_attachment_period_is_read_from_statement_header_and_tables_are_merged():
    tables = [
        {
            "name": "Profit and loss",
            "context": "Standalone financial results (INR in Lakhs)",
            "rows": [
                ["Particulars", "3 months ended 30 September 2026", "3 months ended 30 September 2025"],
                ["Revenue from operations", "1,234.00", "1,100.00"],
            ],
        },
        {
            "name": "Cash flow and PAT",
            "context": "Standalone financial results (INR in Lakhs)",
            "rows": [
                ["Particulars", "3 months ended 30 September 2026", "3 months ended 30 September 2025"],
                ["Profit for the period", "(125.00)", "110.00"],
                ["Net cash flows from operating activities", "220.00", "175.00"],
            ],
        },
    ]
    item = {
        "period_ended": None,
        "period_type": None,
        "relating_to": "Financial Results",
        "headline": "Unaudited results for the quarter ended 30 September 2026",
        "consolidation": None,
    }
    metrics = extract_financial_metrics_from_tables(
        tables, document_text="", item=item, document_format="pdf"
    )

    assert metrics["status"] == "EXTRACTED"
    assert metrics["period_ended"] == "2026-09-30"
    assert metrics["period_type"] == "Quarterly"
    assert metrics["period_provenance"] == "EXPLICIT_ATTACHMENT_HEADER"
    assert metrics["revenue_cr"] == 12.34
    assert metrics["pat_cr"] == -1.25
    assert metrics["cfo_cr"] == 2.2
    assert metrics["statement_basis"] == "STANDALONE"


def test_period_inference_fails_closed_when_attachment_header_has_multiple_latest_period_kinds():
    table = {
        "context": "Financial results for quarter and year ended",
        "rows": [
            ["Particulars", "Quarter ended 31 March 2025", "Year ended 31 March 2025"],
            ["Revenue from operations", "100", "400"],
            ["Profit for the year", "10", "40"],
        ],
    }
    result = extract_financial_metrics_from_tables(
        [table], document_text="", item={"period_ended": None}, document_format="html"
    )
    assert result["status"] == "UNAVAILABLE"
    assert "uniquely established" in result["reason"]


def test_table_metrics_fail_closed_when_unit_is_missing_or_period_is_ambiguous():
    table = {
        "rows": [
            ["Consolidated financial results", "Year ended 31 March 2025"],
            ["Particulars", "Amount"],
            ["Revenue from operations", "100"],
            ["Profit after tax", "10"],
        ]
    }
    result = extract_financial_metrics_from_tables(
        [table], document_text="", item=_annual_item(), document_format="csv"
    )
    assert result["status"] == "UNAVAILABLE"
    assert "unit" in result["reason"].lower() or "period" in result["reason"].lower()


def test_xlsx_workbook_is_read_as_bounded_tables_and_parsed():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Annual Results"
    sheet.append(["Consolidated Statement of Profit and Loss", "INR in Crores"])
    sheet.append(["Particulars", "Year ended 31 March 2025", "Year ended 31 March 2024"])
    sheet.append(["Revenue from operations", 125.5, 110.0])
    sheet.append(["Profit for the year", 12.5, 10.0])
    output = BytesIO()
    workbook.save(output)
    parsed = extract_document(
        output.getvalue(),
        "application/octet-stream",
        "https://www.bseindia.com/attachment.bin",
    )
    metrics = extract_financial_metrics_from_tables(
        parsed["tables"], document_text="", item=_annual_item(), document_format=parsed["format"]
    )
    assert parsed["format"] == "xlsx"
    assert metrics["status"] == "EXTRACTED"
    assert metrics["revenue_cr"] == 125.5
    assert metrics["pat_cr"] == 12.5


def test_inline_xbrl_is_converted_without_dtd_or_entity_processing():
    source = b"""<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:xbrli="http://www.xbrl.org/2003/instance">
      <body><ix:resources>
        <xbrli:context id="FY25"><xbrli:entity><xbrli:identifier>EXAMPLE</xbrli:identifier></xbrli:entity>
          <xbrli:period><xbrli:startDate>2024-04-01</xbrli:startDate><xbrli:endDate>2025-03-31</xbrli:endDate></xbrli:period>
        </xbrli:context>
        <xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
      </ix:resources>
      <ix:nonFraction name="in-gaap:RevenueFromOperations" contextRef="FY25" unitRef="INR" scale="7">125.5</ix:nonFraction>
      </body></html>"""
    output = extract_ixbrl_as_xbrl(source)
    assert b"RevenueFromOperations" in output
    assert b"1255000000" in output

    try:
        extract_ixbrl_as_xbrl(b"<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///secret'>]><html></html>")
    except ValueError as exc:
        assert "DTD/entity" in str(exc)
    else:
        raise AssertionError("DTD and entity declarations must be rejected")


def test_xbrl_period_inference_uses_duration_and_fails_closed_on_same_end_date_ambiguity():
    xml = b"""<xbrl>
      <context id="FY"><period><startDate>2025-04-01</startDate><endDate>2026-03-31</endDate></period></context>
      <context id="Q4"><period><startDate>2026-01-01</startDate><endDate>2026-03-31</endDate></period></context>
    </xbrl>"""
    annual = infer_xbrl_reporting_period(
        xml,
        {"period_type": "Annual", "broadcast_time": "31-May-2026 10:00:00"},
    )
    ambiguous = infer_xbrl_reporting_period(
        xml,
        {"period_type": None, "relating_to": "Financial Results", "broadcast_time": "31-May-2026 10:00:00"},
    )
    assert annual[0].isoformat() == "2026-03-31"
    assert annual[1] == "annual"
    assert ambiguous is None


def test_format_detection_uses_signature_before_misleading_url_extension():
    assert detect_document_format(b"%PDF-1.7", "text/plain", "https://exchange/file.csv") == "pdf"
    assert detect_document_format(b"<html><table></table></html>", "", "https://exchange/file.bin") == "html"
