"""Generate a SYNTHETIC prospectus-layout fixture for parser tests.

This is not an official Clean Science filing. All issue parameters and financial
figures are fabricated test data. The fixture must never be cited as real issuer
financial evidence or used for investment scoring.
"""
import hashlib
import json
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def build_official_rhp_fixture(output_pdf_path: Path, manifest_path: Path) -> str:
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_pdf_path),
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleStyle", parent=styles["Title"], fontSize=18, leading=22)
    h2_style = ParagraphStyle("H2Style", parent=styles["Heading2"], fontSize=13, leading=16)
    body_style = ParagraphStyle("BodyStyle", parent=styles["Normal"], fontSize=10, leading=14)

    story = []

    # PAGE 1: Clearly label synthetic data so the generated fixture cannot be mistaken for a real filing.
    story.append(Paragraph("<b>SYNTHETIC TEST FIXTURE — NOT A REAL PROSPECTUS</b>", title_style))
    story.append(Paragraph("<b>Test-only issuer layout; all figures below are fabricated.</b>", body_style))
    story.append(Paragraph("<b>CLEAN SCIENCE-LIKE SAMPLE ISSUER (NOT THE REAL COMPANY)</b>", title_style))
    story.append(Paragraph("<b>RED HERRING PROSPECTUS</b>", h2_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Initial Public Offering of Equity Shares having Face Value of ₹ 1 each at a Price Band of "
        "₹ 450 to ₹ 475 per Equity Share. Minimum Lot Size: 31 Equity Shares. "
        "The Offer comprises a Fresh Issue of ₹ 800.00 Crore and an Offer for Sale of ₹ 400.00 Crore "
        "aggregating to Total Issue Size of ₹ 1200.00 Crore.",
        body_style,
    ))
    story.append(Spacer(1, 15))

    issue_table_data = [
        ["Parameter", "Details"],
        ["Issuer Name", "Clean Science and Technology Limited"],
        ["Price Band", "₹ 450 to ₹ 475 per Equity Share"],
        ["Lot Size", "31 Equity Shares"],
        ["Fresh Issue", "₹ 800.00 Crore"],
        ["Offer for Sale", "₹ 400.00 Crore"],
        ["Total Issue Size", "₹ 1200.00 Crore"],
        ["Objects of the Offer", "Funding capital expenditure requirements and general corporate purposes"],
    ]
    t1 = Table(issue_table_data, colWidths=[200, 320])
    t1.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t1)
    story.append(PageBreak())

    # PAGE 2: Risk Factors & Structure
    story.append(Paragraph("<b>SECTION II: RISK FACTORS AND BUSINESS OVERVIEW</b>", title_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Internal Risk Factors: Any inability to comply with environmental regulations, client concentration in top 5 customers, "
        "and foreign currency exchange fluctuations may adversely impact operations and financial condition. "
        "Objects of the Issue: The Fresh Issue proceeds will be utilized for capex growth ₹ 500 Cr and debt repayment ₹ 200 Cr.",
        body_style,
    ))
    story.append(PageBreak())

    # PAGE 3: Consolidated Statement of Profit and Loss (₹ in lakhs)
    story.append(Paragraph("<b>SECTION III: FINANCIAL INFORMATION</b>", title_style))
    story.append(Paragraph("<b>Consolidated Statement of Profit and Loss (₹ in lakhs)</b>", h2_style))
    story.append(Spacer(1, 10))

    pnl_data = [
        ["Consolidated Statement of Profit and Loss (₹ in lakhs)", "", ""],
        ["Particulars", "FY 2023-24", "FY 2024-25"],
        ["Revenue from operations", "71,450.50", "82,300.00"],
        ["Other income", "1,200.00", "1,550.00"],
        ["Total income from operations", "72,650.50", "83,850.00"],
        ["Operating expenses", "54,200.00", "61,300.00"],
        ["Profit before tax", "17,250.50", "21,000.00"],
        ["Profit after tax", "12,500.00", "14,800.00"],
        ["Basic and diluted earnings per share", "12.50", "14.80"],
    ]
    t_pnl = Table(pnl_data, colWidths=[240, 140, 140])
    t_pnl.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t_pnl)
    story.append(PageBreak())

    # PAGE 4: Consolidated Statement of Cash Flows (₹ in lakhs)
    story.append(Paragraph("<b>Consolidated Statement of Cash Flows (₹ in lakhs)</b>", title_style))
    story.append(Spacer(1, 10))

    cf_data = [
        ["Consolidated Statement of Cash Flows (₹ in lakhs)", "", ""],
        ["Particulars", "FY 2023-24", "FY 2024-25"],
        ["Net cash generated from operating activities", "9,800.00", "11,200.00"],
        ["Net cash used in investing activities", "(6,500.00)", "(7,800.00)"],
        ["Net cash used in financing activities", "(2,100.00)", "(2,400.00)"],
        ["Net increase in cash and cash equivalents", "1,200.00", "1,000.00"],
    ]
    t_cf = Table(cf_data, colWidths=[240, 140, 140])
    t_cf.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t_cf)
    story.append(PageBreak())

    # PAGE 5: Summary Statement of Assets and Liabilities (₹ in lakhs)
    story.append(Paragraph("<b>Summary Statement of Assets and Liabilities (₹ in lakhs)</b>", title_style))
    story.append(Spacer(1, 10))

    bs_data = [
        ["Consolidated Summary Statement of Assets and Liabilities (₹ in lakhs)", "", ""],
        ["Particulars", "FY 2023-24", "FY 2024-25"],
        ["Net worth", "48,000.00", "59,500.00"],
        ["Total borrowings", "0.00", "0.00"],
        ["Trade receivables", "7,500.00", "8,900.00"],
        ["Cash and cash equivalents", "4,200.00", "5,200.00"],
        ["Total assets", "56,000.00", "68,400.00"],
    ]
    t_bs = Table(bs_data, colWidths=[240, 140, 140])
    t_bs.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t_bs)

    doc.build(story)

    # Compute SHA-256
    pdf_bytes = output_pdf_path.read_bytes()
    doc_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # Manifest with reviewed expected values
    manifest = {
        "manifest_version": "1.0",
        "synthetic_fixture": True,
        "issuer": {
            "symbol": "SYNTHETIC_TEST",
            "company_name": "Synthetic test issuer — not a real filing",
            "industry": "Test data only",
            "issue_type": "MAINBOARD",
        },
        "document": {
            "document_type": "SYNTHETIC_TEST_FIXTURE",
            "document_title": "Synthetic prospectus-layout fixture (NOT OFFICIAL)",
            "source_url": "https://example.invalid/synthetic-prospectus-layout-fixture.pdf",
            "document_hash": doc_hash,
            "page_count": 5,
            "synthetic_fixture": True,
            "unit": "lakh",
            "statement_basis": "CONSOLIDATED",
        },
        "reviewed_issue_parameters": {
            "min_price": 450.0,
            "max_price": 475.0,
            "lot_size": 31,
            "issue_size_cr": 1200.0,
            "fresh_issue_cr": 800.0,
            "ofs_cr": 400.0,
        },
        "reviewed_financial_facts": [
            {
                "field_name": "revenue_from_operations",
                "canonical_field": "revenue_latest",
                "period": "FY 2024-25",
                "period_label": "FY2024-2025",
                "statement_basis": "CONSOLIDATED",
                "raw_value": "82,300.00",
                "unit": "lakh",
                "expected_normalized_inr_crore": 823.00,
                "page_number": 3,
            },
            {
                "field_name": "profit_after_tax",
                "canonical_field": "pat_latest",
                "period": "FY 2024-25",
                "period_label": "FY2024-2025",
                "statement_basis": "CONSOLIDATED",
                "raw_value": "14,800.00",
                "unit": "lakh",
                "expected_normalized_inr_crore": 148.00,
                "page_number": 3,
            },
            {
                "field_name": "operating_cash_flow",
                "canonical_field": "cfo_latest",
                "period": "FY 2024-25",
                "period_label": "FY2024-2025",
                "statement_basis": "CONSOLIDATED",
                "raw_value": "11,200.00",
                "unit": "lakh",
                "expected_normalized_inr_crore": 112.00,
                "page_number": 4,
            },
            {
                "field_name": "net_worth",
                "canonical_field": "net_worth",
                "period": "FY 2024-25",
                "period_label": "FY2024-2025",
                "statement_basis": "CONSOLIDATED",
                "raw_value": "59,500.00",
                "unit": "lakh",
                "expected_normalized_inr_crore": 595.00,
                "page_number": 5,
            },
            {
                "field_name": "borrowings",
                "canonical_field": "total_debt",
                "period": "FY 2024-25",
                "period_label": "FY2024-2025",
                "statement_basis": "CONSOLIDATED",
                "raw_value": "0.00",
                "unit": "lakh",
                "expected_normalized_inr_crore": 0.00,
                "page_number": 5,
            },
        ],
    }

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return doc_hash


if __name__ == "__main__":
    pdf_p = Path("tests/fixtures/clean_science_rhp.pdf")
    man_p = Path("tests/fixtures/official_prospectus_manifest.json")
    h = build_official_rhp_fixture(pdf_p, man_p)
    print(f"Generated official RHP fixture ({h}) and manifest successfully.")
