from src.results.monitor import parse_financial_results_page


def test_financial_results_parser_extracts_metadata_and_official_attachment():
    html = """
    <table>
      <tr>
        <th>Company Name</th><th>Audited / Unaudited</th>
        <th>Consolidated / Non-Consolidated</th><th>Period</th>
        <th>Period Ended</th><th>Relating To</th><th>XBRL</th><th>Broadcast Date/Time</th>
      </tr>
      <tr>
        <td>Example Ltd</td><td>Unaudited</td><td>Consolidated</td><td>Quarterly</td>
        <td>30-Sep-2026</td><td>Second Quarter</td>
        <td><a href="https://nsearchives.nseindia.com/corporate/example_results.xml">Download</a></td>
        <td>29-Oct-2026 18:15:00</td>
      </tr>
    </table>
    """
    rows = parse_financial_results_page(
        html,
        "EXAMPLE",
        "https://www.nseindia.com/companies-listing/corporate-filings-financial-results?symbol=EXAMPLE",
    )
    assert len(rows) == 1
    assert rows[0]["symbol"] == "EXAMPLE"
    assert rows[0]["company_name"] == "Example Ltd"
    assert rows[0]["period_ended"] == "30-Sep-2026"
    assert rows[0]["relating_to"] == "Second Quarter"
    assert rows[0]["consolidation"] == "Consolidated"
    assert rows[0]["attachment_url"] == "https://nsearchives.nseindia.com/corporate/example_results.xml"
    assert rows[0]["event_key"].startswith("RESULT_")


def test_financial_results_parser_returns_empty_for_unrecognized_page():
    assert parse_financial_results_page("<html><p>maintenance</p></html>", "EXAMPLE", "https://www.nseindia.com/") == []



def test_xbrl_extraction_calculates_reported_values_and_yoy_changes():
    from src.results.monitor import extract_xbrl_metrics

    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
                xmlns:in-gaap="http://example.test/in-gaap"
                xmlns:iso4217="http://www.xbrl.org/2003/iso4217">
      <xbrli:context id="current-quarter">
        <xbrli:entity><xbrli:identifier scheme="https://example.test">EXAMPLE</xbrli:identifier></xbrli:entity>
        <xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period>
      </xbrli:context>
      <xbrli:context id="prior-quarter">
        <xbrli:entity><xbrli:identifier scheme="https://example.test">EXAMPLE</xbrli:identifier></xbrli:entity>
        <xbrli:period><xbrli:startDate>2025-07-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate></xbrli:period>
      </xbrli:context>
      <xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
      <xbrli:unit id="INRPerShare"><xbrli:measure>iso4217:INR</xbrli:measure><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>
      <in-gaap:RevenueFromOperations contextRef="current-quarter" unitRef="INR">2000000000</in-gaap:RevenueFromOperations>
      <in-gaap:RevenueFromOperations contextRef="prior-quarter" unitRef="INR">1600000000</in-gaap:RevenueFromOperations>
      <in-gaap:ProfitLossForPeriod contextRef="current-quarter" unitRef="INR">200000000</in-gaap:ProfitLossForPeriod>
      <in-gaap:ProfitLossForPeriod contextRef="prior-quarter" unitRef="INR">150000000</in-gaap:ProfitLossForPeriod>
      <in-gaap:EarningsPerShareBasic contextRef="current-quarter" unitRef="INRPerShare">5.5</in-gaap:EarningsPerShareBasic>
      <in-gaap:EarningsPerShareBasic contextRef="prior-quarter" unitRef="INRPerShare">4.1</in-gaap:EarningsPerShareBasic>
      <in-gaap:CashFlowsFromUsedInOperatingActivities contextRef="current-quarter" unitRef="INR">250000000</in-gaap:CashFlowsFromUsedInOperatingActivities>
    </xbrli:xbrl>"""
    result = extract_xbrl_metrics(xml, "30-Sep-2026", "Second Quarter")
    assert result["status"] == "EXTRACTED"
    assert result["revenue_cr"] == 200.0
    assert result["pat_cr"] == 20.0
    assert result["eps"] == 5.5
    assert result["cfo_cr"] == 25.0
    assert result["revenue_yoy_pct"] == 25.0
    assert result["pat_yoy_pct"] == 33.33



def test_watchlist_match_requires_exact_configured_company_name():
    from src.results.monitor import _matches_watchlist_company

    filing = {"company_name": "Reliance Industries Limited"}
    assert _matches_watchlist_company(
        filing,
        {"symbol": "RELIANCE", "company_name": "Reliance Industries Limited"},
    )
    assert _matches_watchlist_company(
        filing,
        {
            "symbol": "RELIANCE",
            "company_name": "Reliance Industries Ltd",
            "company_name_aliases": ["Reliance Industries Limited"],
        },
    )
    assert not _matches_watchlist_company(
        filing,
        {"symbol": "TCS", "company_name": "Tata Consultancy Services Limited"},
    )
    assert not _matches_watchlist_company(filing, {"symbol": "RELIANCE"})


def test_results_parser_keeps_cumulative_and_submission_metadata():
    html = """
    <table>
      <tr>
        <th>Company Name</th><th>Audited / Unaudited</th>
        <th>Cumulative / Non-Cumulative</th><th>Consolidated / Non-Consolidated</th>
        <th>Period</th><th>Period Ended</th><th>Relating To</th>
        <th>Type of Submission</th><th>XBRL</th><th>Broadcast Date/Time</th>
      </tr>
      <tr>
        <td>Reliance Industries Limited</td><td>Unaudited</td><td>Non-Cumulative</td>
        <td>Consolidated</td><td>Quarterly</td><td>30-SEP-2026</td>
        <td>Second Quarter</td><td>Original</td>
        <td><a href="https://nsearchives.nseindia.com/corporate/reliance.xml">XBRL</a></td>
        <td>29-OCT-2026 18:15:00</td>
      </tr>
    </table>
    """
    rows = parse_financial_results_page(html, "RELIANCE", "https://www.nseindia.com/companies-listing/corporate-filings-financial-results")
    assert len(rows) == 1
    assert rows[0]["cumulative_status"] == "Non-Cumulative"
    assert rows[0]["period_type"] == "Quarterly"
    assert rows[0]["submission_type"] == "Original"



def test_results_parser_prefers_xbrl_over_details_pdf():
    html = """
    <table>
      <tr><th>Company Name</th><th>Period Ended</th><th>Relating To</th><th>Broadcast Date/Time</th><th>Details</th><th>XBRL</th></tr>
      <tr>
        <td>Example Ltd</td><td>30-Sep-2026</td><td>Second Quarter</td><td>29-Oct-2026 18:15:00</td>
        <td><a href="https://nsearchives.nseindia.com/corporate/details.pdf">Details (100 KB)</a></td>
        <td><a href="https://nsearchives.nseindia.com/corporate/results.xml">XBRL (50 KB)</a></td>
      </tr>
    </table>
    """
    rows = parse_financial_results_page(
        html,
        "EXAMPLE",
        "https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
    )
    assert len(rows) == 1
    assert rows[0]["attachment_url"] == "https://nsearchives.nseindia.com/corporate/results.xml"
    assert rows[0]["xbrl_url"] == "https://nsearchives.nseindia.com/corporate/results.xml"
    assert rows[0]["details_url"] == "https://nsearchives.nseindia.com/corporate/details.pdf"
