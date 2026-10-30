from src.reporting.pdf import markdown_to_pdf


def test_markdown_to_pdf_creates_valid_pdf_with_links_and_unicode(tmp_path):
    output = markdown_to_pdf(
        "# Daily IPO Report\n\n"
        "**Status:** UNABLE_TO_ASSESS\n\n"
        "- Price band: ₹450–₹475\n"
        "- [Official NSE source](https://www.nseindia.com/example?x=1&y=2)\n",
        tmp_path / "daily-report.pdf",
        title="Daily IPO Report",
    )
    assert output.exists()
    assert output.read_bytes().startswith(b"%PDF-")
    assert output.stat().st_size > 500
