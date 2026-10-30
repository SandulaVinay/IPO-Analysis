import pytest
from types import SimpleNamespace

from src.ingestion.scrapers import _parse_official_issue_tables, _has_recognized_issue_table, PortalScraper
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



@pytest.mark.asyncio
async def test_email_console_stub_does_not_log_recipient_or_message_body(monkeypatch, caplog):
    from src.notifications.email import EmailProvider

    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "enable_email", True)
    monkeypatch.setattr(settings, "email_provider", "console")
    result = await EmailProvider().send_notification(
        recipient="private@example.com",
        subject="private subject",
        content="private message body",
    )
    assert result["mocked"] is True
    assert "private@example.com" not in caplog.text
    assert "private message body" not in caplog.text



@pytest.mark.asyncio
async def test_email_provider_attaches_pdf_reports_only_from_reports_directory(tmp_path, monkeypatch):
    from email import message_from_string
    from src.notifications.email import EmailProvider
    import src.notifications.email as email_module

    monkeypatch.chdir(tmp_path)
    report_dir = tmp_path / "reports" / "daily"
    report_dir.mkdir(parents=True)
    pdf_path = report_dir / "digest.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test fixture")
    monkeypatch.setattr(settings, "enable_email", True)
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "sender@example.test")
    monkeypatch.setattr(settings, "smtp_password", "test-password")
    monkeypatch.setattr(settings, "email_from", "sender@example.test")
    monkeypatch.setattr(settings, "email_to", "recipient@example.test")

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=30):
            sent["host"] = host
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def ehlo(self):
            pass
        def starttls(self, context=None):
            pass
        def login(self, user, password):
            assert user == "sender@example.test"
            assert password == "test-password"
        def sendmail(self, sender, recipients, message):
            sent["message"] = message
            sent["recipients"] = recipients

    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)
    result = await EmailProvider().send_notification(
        recipient="recipient@example.test",
        subject="Daily report",
        content="See attached PDF.",
        metadata={"attachments": [str(pdf_path)]},
    )
    parsed = message_from_string(sent["message"])
    assert result["accepted"] is True
    assert parsed.get_content_type() == "multipart/mixed"
    assert any(part.get_content_type() == "application/pdf" for part in parsed.walk())


@pytest.mark.asyncio
async def test_email_provider_rejects_attachments_outside_reports_directory(tmp_path, monkeypatch):
    from src.notifications.email import EmailProvider

    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "private.pdf"
    outside.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(settings, "enable_email", True)
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "smtp_user", "sender@example.test")
    monkeypatch.setattr(settings, "smtp_password", "test-password")
    monkeypatch.setattr(settings, "email_to", "recipient@example.test")
    result = await EmailProvider().send_notification(
        recipient="recipient@example.test",
        subject="Report",
        content="body",
        metadata={"attachments": [str(outside)]},
    )
    assert result["success"] is False
    assert "inside the reports directory" in result["error"]



def test_ipo_source_layout_validation_distinguishes_empty_table_from_changed_layout():
    valid_empty_table = """
    <table>
      <tr><th>Company Name</th><th>Issue Start Date</th><th>Issue End Date</th></tr>
    </table>
    """
    assert _has_recognized_issue_table(valid_empty_table) is True
    assert _has_recognized_issue_table("<html><body>Service unavailable</body></html>") is False



@pytest.mark.asyncio
async def test_email_provider_rejects_non_pdf_content_with_pdf_extension(tmp_path, monkeypatch):
    from src.notifications.email import EmailProvider

    monkeypatch.chdir(tmp_path)
    report_dir = tmp_path / "reports" / "daily"
    report_dir.mkdir(parents=True)
    fake_pdf = report_dir / "fake.pdf"
    fake_pdf.write_text("not a PDF", encoding="utf-8")
    monkeypatch.setattr(settings, "enable_email", True)
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "smtp_user", "sender@example.test")
    monkeypatch.setattr(settings, "smtp_password", "test-password")
    monkeypatch.setattr(settings, "email_to", "recipient@example.test")
    result = await EmailProvider().send_notification(
        recipient="recipient@example.test",
        subject="Report",
        content="body",
        metadata={"attachments": [str(fake_pdf)]},
    )
    assert result["success"] is False
    assert "recognizable PDF" in result["error"]



@pytest.mark.asyncio
async def test_portal_scraper_reports_partial_when_one_official_layout_is_unrecognized(monkeypatch):
    from src.ingestion import scrapers as scraper_module

    recognized_empty_table = """
    <table>
      <tr><th>Company Name</th><th>Issue Start Date</th><th>Issue End Date</th></tr>
    </table>
    """
    responses = iter([
        SimpleNamespace(text=recognized_empty_table),
        SimpleNamespace(text="<html><body>Service unavailable</body></html>"),
    ])

    async def fake_get(url, headers=None, timeout=None):
        return next(responses)

    monkeypatch.setattr(scraper_module.http_client, "get", fake_get)
    scraper = PortalScraper()
    rows = await scraper.fetch_upcoming_ipos()
    assert rows == []
    assert scraper.last_source_status == "PARTIAL"
    assert any("UNRECOGNIZED_LAYOUT" in error for error in scraper.last_source_errors)



@pytest.mark.asyncio
async def test_whatsapp_provider_uploads_and_sends_pdf_document(tmp_path, monkeypatch):
    from src.notifications.whatsapp import WhatsAppProvider
    from src.ingestion import client as client_module

    monkeypatch.chdir(tmp_path)
    report_dir = tmp_path / "reports" / "daily"
    report_dir.mkdir(parents=True)
    pdf_path = report_dir / "daily-digest.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 valid test bytes")
    monkeypatch.setattr(settings, "enable_whatsapp", True)
    monkeypatch.setattr(settings, "whatsapp_provider", "cloud_api")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "test-phone-id")
    monkeypatch.setattr(settings, "whatsapp_access_token", "test-token")
    monkeypatch.setattr(settings, "whatsapp_recipient_phone", "+911234567890")
    monkeypatch.setattr(settings, "whatsapp_api_version", "v26.0")

    calls = []

    async def fake_post(url, json=None, data=None, files=None, headers=None, retry_transient=True):
        calls.append({"url": url, "json": json, "data": data, "files": files, "headers": headers})
        if url.endswith("/media"):
            return SimpleNamespace(json=lambda: {"id": "media-123"})
        return SimpleNamespace(json=lambda: {"messages": [{"id": "wamid.test-123"}]})

    monkeypatch.setattr(client_module.http_client, "post", fake_post)
    result = await WhatsAppProvider().send_notification(
        recipient="+911234567890",
        subject="Daily IPO digest",
        content="UNABLE_TO_ASSESS; full report attached.",
        metadata={"attachment_path": str(pdf_path)},
    )
    assert result["success"] is True
    assert result["accepted"] is True
    assert len(calls) == 2
    assert calls[0]["data"]["type"] == "application/pdf"
    assert calls[0]["files"]["file"][1] == b"%PDF-1.4 valid test bytes"
    assert calls[1]["json"]["type"] == "document"
    assert calls[1]["json"]["document"]["id"] == "media-123"



def test_official_issue_parser_extracts_price_band_lot_and_explicit_crore_size():
    html = """
    <table>
      <tr>
        <th>Company Name</th><th>Issue Start Date</th><th>Issue End Date</th>
        <th>Security Type</th><th>Price Band</th><th>Issue Size (INR Cr)</th>
        <th>Lot Size</th><th>Trading Symbol</th>
      </tr>
      <tr>
        <td>Example Industries Ltd</td><td>10-Nov-2026</td><td>14-Nov-2026</td>
        <td>Mainboard</td><td>₹ 90 - ₹ 95</td><td>₹ 1,200 Cr</td>
        <td>160</td><td>EXAMPLE</td>
      </tr>
    </table>
    """
    rows = _parse_official_issue_tables(
        html,
        source_name="NSE India",
        source_url="https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
    )
    assert len(rows) == 1
    assert rows[0]["min_price"] == 90.0
    assert rows[0]["max_price"] == 95.0
    assert rows[0]["issue_size_cr"] == 1200.0
    assert rows[0]["lot_size"] == 160
    assert rows[0]["symbol"] == "EXAMPLE"



@pytest.mark.asyncio
async def test_portal_scraper_clears_conflicting_price_bands_across_sources(monkeypatch):
    from src.ingestion import scrapers as scraper_module

    def table(price_band):
        return f"""
        <table>
          <tr><th>Company Name</th><th>Issue Start Date</th><th>Issue End Date</th><th>Price Band</th></tr>
          <tr><td>Example Industries Ltd</td><td>10-Nov-2026</td><td>14-Nov-2026</td><td>{price_band}</td></tr>
        </table>
        """

    responses = iter([
        SimpleNamespace(text=table("₹ 90 - ₹ 95")),
        SimpleNamespace(text=table("₹ 100 - ₹ 105")),
    ])

    async def fake_get(url, headers=None, timeout=None):
        return next(responses)

    monkeypatch.setattr(scraper_module.http_client, "get", fake_get)
    rows = await PortalScraper().fetch_upcoming_ipos()
    assert len(rows) == 1
    assert rows[0].get("min_price") is None
    assert rows[0].get("max_price") is None
    assert {item["field"] for item in rows[0]["field_conflicts"]} == {"min_price", "max_price"}



@pytest.mark.asyncio
async def test_gmail_smtp_falls_back_to_implicit_tls_on_465(tmp_path, monkeypatch):
    import smtplib
    import src.notifications.email as email_module
    from src.notifications.email import EmailProvider

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "enable_email", True)
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "sender@example.test")
    monkeypatch.setattr(settings, "smtp_password", " test-app- password ")
    monkeypatch.setattr(settings, "email_from", "sender@example.test")
    monkeypatch.setattr(settings, "email_to", "recipient@example.test")

    attempted_ports = []

    class DisconnectedSMTP:
        def __init__(self, host, port, timeout=20):
            attempted_ports.append(port)
            raise smtplib.SMTPServerDisconnected("connection closed")

    class FakeSMTPSSL:
        def __init__(self, host, port, timeout=20, context=None):
            attempted_ports.append(port)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def ehlo(self):
            pass
        def login(self, user, password):
            assert user == "sender@example.test"
            assert password == "test-app-password"
        def sendmail(self, sender, recipients, message):
            assert recipients == ["recipient@example.test"]
            return {}

    monkeypatch.setattr(email_module.smtplib, "SMTP", DisconnectedSMTP)
    monkeypatch.setattr(email_module.smtplib, "SMTP_SSL", FakeSMTPSSL)

    result = await EmailProvider().send_notification(
        recipient="recipient@example.test",
        subject="SMTP fallback test",
        content="Test message",
    )

    assert attempted_ports == [587, 465]
    assert result["success"] is True
    assert result["accepted"] is True
    assert result["delivered"] is False
