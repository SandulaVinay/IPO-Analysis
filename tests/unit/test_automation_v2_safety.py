import pytest
from types import SimpleNamespace

from src.ingestion.scrapers import _parse_official_issue_tables, PortalScraper
from src.notifications.whatsapp import WhatsAppProvider
from src.ingestion import client as client_module
from src.common.config import settings
from src.web.app import run_pipeline_for_ipo


def test_official_issue_parser_only_emits_source_values():
    html = """
    <table>
      <tr><th>Company Name</th><th>Issue Start Date</th><th>Issue End Date</th><th>Security Type</th><th>Status</th></tr>
      <tr><td>Example Industries Ltd</td><td>17-Sep-2026</td><td>21-Sep-2026</td><td>SME</td><td>Closed</td></tr>
    </table>
    """
    rows = _parse_official_issue_tables(
        html,
        source_name="NSE India",
        source_url="https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
    )
    assert len(rows) == 1
    assert rows[0]["company_name"] == "Example Industries Ltd"
    assert rows[0]["verified_open_date"] == "17-Sep-2026"
    assert rows[0]["verified_close_date"] == "21-Sep-2026"
    assert rows[0]["issue_type"] == "SME"
    assert rows[0]["source_tier"] == "TIER_1"
    assert "min_price" not in rows[0]
    assert "gmp_value" not in rows[0]


def test_official_issue_parser_returns_empty_for_unrecognized_layout():
    rows = _parse_official_issue_tables(
        "<html><body><p>Temporary maintenance</p></body></html>",
        source_name="NSE India",
        source_url="https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
    )
    assert rows == []


@pytest.mark.asyncio
async def test_whatsapp_cloud_api_posts_and_reports_acceptance(monkeypatch):
    monkeypatch.setattr(settings, "enable_whatsapp", True)
    monkeypatch.setattr(settings, "whatsapp_provider", "cloud_api")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "test-phone-id")
    monkeypatch.setattr(settings, "whatsapp_access_token", "test-token")
    monkeypatch.setattr(settings, "whatsapp_api_version", "v22.0")
    monkeypatch.setattr(settings, "whatsapp_recipient_phone", "+919999999999")

    seen = {}

    class FakeResponse:
        def json(self):
            return {"messages": [{"id": "wamid.test-message"}]}

    async def fake_post(url, *, json=None, data=None, headers=None, retry_transient=True):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(client_module.http_client, "post", fake_post)
    result = await WhatsAppProvider().send_notification(
        recipient="+919999999999",
        subject="IPO alert",
        content="Evidence-backed summary",
    )
    assert seen["url"] == "https://graph.facebook.com/v22.0/test-phone-id/messages"
    assert seen["json"]["to"] == "919999999999"
    assert seen["json"]["text"]["body"].startswith("IPO alert")
    assert seen["headers"]["Authorization"] == "Bearer test-token"
    assert result["success"] is True
    assert result["accepted"] is True
    assert result["delivered"] is False
    assert result["message_id"] == "wamid.test-message"


@pytest.mark.asyncio
async def test_production_analysis_fails_closed_without_verified_sources(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    ipo = SimpleNamespace(symbol="TEST_IPO", company_name="Test Issuer")
    result = await run_pipeline_for_ipo(ipo, session=None)
    assert result["score_data"]["verdict"] == "UNABLE_TO_ASSESS"
    assert result["score_data"]["overall_score"] == 0.0
    assert result["assessment_status"] == "UNABLE_TO_ASSESS"
    assert "No investment recommendation" in result["executive_summary"]


def test_document_ingestion_rejects_html_or_empty_content():
    from src.documents.manager import _validate_pdf_content

    with pytest.raises(ValueError, match="empty"):
        _validate_pdf_content(b"")
    with pytest.raises(ValueError, match="not a recognizable PDF"):
        _validate_pdf_content(b"<html><body>blocked by exchange</body></html>")


def test_document_ingestion_accepts_pdf_header_and_sanitizes_path_components():
    from src.documents.manager import _safe_component, _validate_pdf_content

    _validate_pdf_content(b"%PDF-1.7\\nminimal test fixture")
    assert _safe_component("../../RHP/2026", "filing") == "RHP_2026"



def test_official_issue_parser_extracts_only_labeled_prospectus_links():
    html = """
    <table>
      <tr><th>Company Name</th><th>Issue Start Date</th><th>Issue End Date</th><th>Security Type</th></tr>
      <tr>
        <td>Example Industries Ltd</td><td>17-Sep-2026</td><td>21-Sep-2026</td><td>SME</td>
        <td><a href="/corporate/example-rhp.pdf">Red Herring Prospectus</a></td>
        <td><a href="https://www.nseindia.com/quote">Quote</a></td>
      </tr>
    </table>
    """
    rows = _parse_official_issue_tables(
        html,
        source_name="NSE India",
        source_url="https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
    )
    assert len(rows) == 1
    links = rows[0]["document_links"]
    assert len(links) == 1
    assert links[0]["document_type"] == "RHP"
    assert links[0]["source_url"] == "https://www.nseindia.com/corporate/example-rhp.pdf"



@pytest.mark.asyncio
async def test_console_provider_never_claims_delivery_in_production(monkeypatch):
    from src.notifications.console import ConsoleProvider

    monkeypatch.setattr(settings, "app_env", "production")
    result = await ConsoleProvider().send_notification(
        recipient="private-recipient",
        subject="test subject",
        content="private body",
    )
    assert result["success"] is False
    assert result["delivered"] is False


@pytest.mark.asyncio
async def test_sms_stub_never_claims_delivery(monkeypatch):
    from src.notifications.sms import SMSProvider

    monkeypatch.setattr(settings, "enable_sms", True)
    result = await SMSProvider().send_notification(
        recipient="private-recipient",
        subject="test subject",
        content="private body",
    )
    assert result["success"] is False
    assert result["delivered"] is False
