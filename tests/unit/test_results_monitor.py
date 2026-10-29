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
