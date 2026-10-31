import pytest

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



def test_bse_results_parser_requires_exact_company_and_normalizes_attachment():
    from src.results.monitor import parse_bse_financial_results_payload

    payload = {
        "Table": [
            {
                "NEWSID": "event-123",
                "SCRIP_CD": 517286,
                "SLONGNAME": "RNIT AI SOLUTIONS LIMITED",
                "NEWSSUB": "RNIT AI SOLUTIONS LIMITED - Unaudited Financial Results",
                "SUBCATNAME": "Financial Results",
                "DT_TM": "2026-10-30T16:30:00",
                "ATTACHMENTNAME": "event-123.pdf",
                "NSURL": "https://www.bseindia.com/stock-share-price/rnit/517286/",
            },
            {
                "NEWSID": "wrong-company",
                "SCRIP_CD": 517286,
                "SLONGNAME": "OTHER COMPANY LIMITED",
                "NEWSSUB": "Other Company Financial Results",
                "DT_TM": "2026-10-30T16:31:00",
                "ATTACHMENTNAME": "other.pdf",
            },
            {
                "NEWSID": "missing-code",
                "SLONGNAME": "RNIT AI SOLUTIONS LIMITED",
                "NEWSSUB": "RNIT AI SOLUTIONS LIMITED - Financial Results",
                "DT_TM": "2026-10-30T16:32:00",
                "ATTACHMENTNAME": "missing-code.pdf",
            },
        ]
    }
    company = {
        "symbol": "RNITAI",
        "exchange": "BSE",
        "bse_scrip_code": "517286",
        "company_name": "RNIT AI SOLUTIONS LIMITED",
        "company_name_aliases": ["RNIT AI Solutions Ltd"],
    }
    rows = parse_bse_financial_results_payload(payload, "RNITAI", company, "517286")

    assert len(rows) == 1
    assert rows[0]["exchange"] == "BSE"
    assert rows[0]["company_name"] == "RNIT AI SOLUTIONS LIMITED"
    assert rows[0]["period_ended"] is None
    assert rows[0]["attachment_url"] == "https://www.bseindia.com/xml-data/corpfiling/AttachLive/event-123.pdf"
    assert rows[0]["event_key"].startswith("RESULT_")


def test_nse_results_layout_recognition_uses_required_headers():
    from src.results.monitor import has_recognized_financial_results_table

    valid = """
    <table>
      <tr><th>Company Name</th><th>Period Ended</th><th>Broadcast Date/Time</th></tr>
    </table>
    """
    assert has_recognized_financial_results_table(valid) is True
    assert has_recognized_financial_results_table("<html><p>Access denied</p></html>") is False



def test_nse_json_results_parser_requires_symbol_and_exact_issuer_name():
    from src.results.monitor import parse_nse_financial_results_payload

    company = {
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries Limited",
        "company_name_aliases": ["Reliance Industries Ltd"],
    }
    payload = [
        {
            "symbol": "RELIANCE",
            "companyName": "Reliance Industries Limited",
            "toDate": "30-Sep-2026",
            "relatingTo": "Second Quarter",
            "broadCastDate": "29-Oct-2026 18:15:00",
            "audited": "Un-Audited",
            "cumulative": "Non-cumulative",
            "consolidated": "Consolidated",
            "period": "Quarterly",
            "format": "New",
            "xbrl": "https://nsearchives.nseindia.com/corporate/reliance.xml",
        },
        {
            "symbol": "TCS",
            "companyName": "Reliance Industries Limited",
            "toDate": "30-Sep-2026",
            "relatingTo": "Second Quarter",
            "broadCastDate": "29-Oct-2026 18:16:00",
        },
        {
            "symbol": "RELIANCE",
            "companyName": "Different Issuer Limited",
            "toDate": "30-Sep-2026",
            "relatingTo": "Second Quarter",
            "broadCastDate": "29-Oct-2026 18:17:00",
        },
    ]

    rows = parse_nse_financial_results_payload(payload, "RELIANCE", company, "Quarterly")

    assert len(rows) == 1
    assert rows[0]["symbol"] == "RELIANCE"
    assert rows[0]["company_name"] == "Reliance Industries Limited"
    assert rows[0]["period_ended"] == "30-Sep-2026"
    assert rows[0]["xbrl_url"] == "https://nsearchives.nseindia.com/corporate/reliance.xml"
    assert rows[0]["consolidation"] == "Consolidated"
    assert rows[0]["event_key"].startswith("RESULT_")


def test_bse_api_request_uses_browser_headers_and_default_result_filters():
    from datetime import date
    from src.results.monitor import bse_api_headers, bse_results_request_params

    headers = bse_api_headers()
    params = bse_results_request_params(1, "517286", date(2026, 10, 23), date(2026, 10, 30))

    assert headers["Host"] == "api.bseindia.com"
    assert headers["Origin"] == "https://www.bseindia.com"
    assert headers["Referer"] == "https://www.bseindia.com/corporates/ann.html"
    assert headers["Sec-Fetch-Site"] == "same-site"
    assert params == {
        "pageno": 1,
        "strPrevDate": "20261023",
        "strToDate": "20261030",
        "strCat": "-1",
        "subcategory": "-1",
        "strSearch": "P",
        "strscrip": "517286",
        "strType": "C",
    }



@pytest.mark.asyncio
async def test_bse_api_is_attempted_when_optional_announcement_page_returns_403(tmp_path, monkeypatch):
    import httpx
    import src.results.monitor as monitor_module

    requested_urls = []
    recorded_runs = []

    class FakeStore:
        def load_watchlist(self):
            return [{
                "symbol": "EXAMPLE",
                "exchange": "BSE",
                "bse_scrip_code": "123456",
                "company_name": "Example Industries Limited",
            }]

        def has_processed_event(self, event_key):
            return False

        def record_run(self, **kwargs):
            recorded_runs.append(kwargs)

        def record_event(self, *args, **kwargs):
            raise AssertionError("No events should be recorded for an empty API response.")

    class FakeResponse:
        def __init__(self, url, status_code=200, payload=None):
            self.url = url
            self.status_code = status_code
            self._payload = payload or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                request = httpx.Request("GET", self.url)
                response = httpx.Response(self.status_code, request=request)
                raise httpx.HTTPStatusError("HTTP error", request=request, response=response)

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            requested_urls.append(url)
            if url == monitor_module.BSE_RESULTS_PAGE_URL:
                return FakeResponse(url, status_code=403)
            if url == monitor_module.BSE_RESULTS_API_URL:
                return FakeResponse(url, payload={"Table": []})
            raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(monitor_module, "StateStore", FakeStore)
    monkeypatch.setattr(monitor_module.httpx, "AsyncClient", FakeAsyncClient)

    result = await monitor_module.monitor_financial_results()

    assert monitor_module.BSE_RESULTS_PAGE_URL in requested_urls
    assert monitor_module.BSE_RESULTS_API_URL in requested_urls
    assert result["status"] == "SUCCESS"
    assert result["errors"] == 0
    assert recorded_runs[-1]["status"] == "SUCCESS"
