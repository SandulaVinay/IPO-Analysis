"""End-to-end tests for the financial-results detection-to-email path.

All exchange responses and the email transport are mocked: this verifies the full
monitor orchestration without sending a test alert to a real watchlist recipient.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest


async def test_recent_nse_results_create_email_report_and_dedupe(monkeypatch, tmp_path):
    import src.results.monitor as monitor_module

    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    announced_at = now.strftime("%d-%b-%Y %H:%M:%S")
    filing = {
        "symbol": "RELIANCE",
        "companyName": "Reliance Industries Limited",
        "toDate": "30-Sep-2026",
        "relatingTo": "Second Quarter",
        "broadCastDate": announced_at,
        "consolidated": "Consolidated",
        "period": "Quarterly",
        "format": "New",
        "xbrl": "",
        "resultDetailedDataLink": "",
    }

    class FakeResponse:
        status_code = 200

        def __init__(self, payload=None):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeNseSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, *, headers=None, params=None):
            if params is None:
                return FakeResponse({})
            if params.get("period") == "Quarterly":
                return FakeResponse({"data": [filing]})
            return FakeResponse({"data": []})

    class FakeStore:
        def __init__(self):
            self.processed = set()
            self.events = []
            self.runs = []

        def load_watchlist(self):
            return [{
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "company_name": "Reliance Industries Limited",
                "company_name_aliases": ["Reliance Industries Ltd"],
            }]

        def has_processed_event(self, event_key):
            return event_key in self.processed

        def record_event(self, event_key, **kwargs):
            self.events.append({"event_key": event_key, **kwargs})
            if kwargs.get("status") in {"ACCEPTED", "DELIVERED"}:
                self.processed.add(event_key)

        def record_run(self, **kwargs):
            self.runs.append(kwargs)

    store = FakeStore()
    email_calls = []

    class FakeEmailProvider:
        async def send_notification(self, *, recipient, subject, content, metadata=None):
            email_calls.append({
                "recipient": recipient,
                "subject": subject,
                "content": content,
                "metadata": metadata or {},
            })
            return {
                "success": True,
                "accepted": True,
                "delivered": False,
                "error": None,
            }

    class UnexpectedWhatsAppProvider:
        async def send_notification(self, **kwargs):
            raise AssertionError("WhatsApp must not be called when email is accepted")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(monitor_module, "StateStore", lambda: store)
    monkeypatch.setattr(monitor_module.httpx, "AsyncClient", lambda **kwargs: FakeNseSession())
    monkeypatch.setattr(monitor_module, "EmailProvider", FakeEmailProvider)
    monkeypatch.setattr(monitor_module, "WhatsAppProvider", UnexpectedWhatsAppProvider)

    def write_test_pdf(_markdown, output_path, **_kwargs):
        output_path.write_bytes(b"%PDF-1.4\\n% mocked test report\\n")

    monkeypatch.setattr(monitor_module, "markdown_to_pdf", write_test_pdf)

    first = await monitor_module.monitor_financial_results()

    # This fixture has no filing attachment, so delivery succeeds while
    # automated metric extraction is clearly reported as partial coverage.
    assert first["status"] == "PARTIAL"
    assert first["symbols_checked"] == 1
    assert first["new_filings"] == 1
    assert first["notifications_accepted"] == 1
    assert first["documents_unavailable"] == 1
    assert first["errors"] == 0
    assert len(email_calls) == 1
    assert email_calls[0]["subject"] == (
        "Financial Results Alert | Reliance Industries Limited (RELIANCE) | Second Quarter ended 30-Sep-2026"
    )
    assert "30-Sep-2026" in email_calls[0]["content"]
    assert "Official filing:" in email_calls[0]["content"]
    attachment = email_calls[0]["metadata"]["attachments"][0]
    assert attachment.endswith(".pdf")
    assert (tmp_path / attachment).is_file()
    assert store.events[0]["status"] == "ACCEPTED"
    assert store.events[0]["channel"] == "EMAIL"

    # The same exchange event must not send a duplicate email on the next run.
    second = await monitor_module.monitor_financial_results()
    assert second["new_filings"] == 0
    assert second["notifications_accepted"] == 0
    assert len(email_calls) == 1

    def fail_pdf(*_args, **_kwargs):
        raise RuntimeError("renderer unavailable")

    monkeypatch.setattr(monitor_module, "markdown_to_pdf", fail_pdf)
    monkeypatch.setenv("FORCE_RESEND_RESULTS", "true")
    third = await monitor_module.monitor_financial_results()
    assert third["notifications_accepted"] == 1
    assert len(email_calls) == 2
    assert email_calls[1]["metadata"]["attachments"] == []
    assert email_calls[1]["metadata"]["html_body"]


@pytest.mark.asyncio
async def test_results_monitor_retries_unavailable_attachment_and_emails_only_when_extraction_improves(tmp_path, monkeypatch):
    import src.results.monitor as monitor_module

    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    filing = {
        "symbol": "RELIANCE",
        "companyName": "Reliance Industries Limited",
        "toDate": "30-Sep-2026",
        "relatingTo": "Second Quarter",
        "broadCastDate": now.strftime("%d-%b-%Y %H:%M:%S"),
        "consolidated": "Consolidated",
        "period": "Quarterly",
        "format": "New",
        "xbrl": "",
        "resultDetailedDataLink": "https://www.nseindia.com/files/reliance.bin",
    }

    class Response:
        status_code = 200

        def __init__(self, payload=None):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class NseSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, _url, *, headers=None, params=None):
            if params is None:
                return Response({})
            return Response({"data": [filing] if params.get("period") == "Quarterly" else []})

    class Store:
        def __init__(self):
            self.events = {}
            self.runs = []

        def load_watchlist(self):
            return [{"symbol": "RELIANCE", "exchange": "NSE", "company_name": "Reliance Industries Limited"}]

        def has_processed_event(self, event_key):
            return bool(self.events.get(event_key, {}).get("status") in {"ACCEPTED", "DELIVERED"})

        def event_record(self, event_key):
            return self.events.get(event_key)

        def record_event(self, event_key, **kwargs):
            self.events[event_key] = {"event_key": event_key, **kwargs}

        def record_run(self, **kwargs):
            self.runs.append(kwargs)

    class Email:
        async def send_notification(self, **_kwargs):
            email_calls.append(1)
            return {"success": True, "accepted": True, "delivered": False, "error": None}

    store = Store()
    email_calls = []
    extraction_calls = []

    async def extract(_item, _attachment_urls):
        extraction_calls.append(1)
        if len(extraction_calls) == 1:
            return {"status": "UNAVAILABLE", "reason": "temporary source issue"}, None, ["temporary"]
        return {
            "status": "EXTRACTED",
            "period_ended": "2026-09-30",
            "period_type": "Quarterly",
            "revenue_cr": 12.0,
            "pat_cr": 1.5,
            "source_status": "CANDIDATE_UNVERIFIED",
            "assessment_eligible": False,
            "source_url": "https://www.nseindia.com/files/reliance.bin",
        }, None, []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(monitor_module, "StateStore", lambda: store)
    monkeypatch.setattr(monitor_module.httpx, "AsyncClient", lambda **_kwargs: NseSession())
    monkeypatch.setattr(monitor_module, "EmailProvider", Email)
    monkeypatch.setattr(monitor_module, "_extract_official_attachment", extract)
    monkeypatch.setattr(monitor_module, "markdown_to_pdf", lambda _markdown, output_path, **_kwargs: output_path.write_bytes(b"%PDF-1.4"))

    first = await monitor_module.monitor_financial_results()
    assert first["documents_unavailable"] == 1
    assert store.event_record(next(iter(store.events)))["processing_status"] == "UNAVAILABLE"
    assert len(email_calls) == 1

    second = await monitor_module.monitor_financial_results()
    assert second["new_filings"] == 1
    assert store.event_record(next(iter(store.events)))["processing_status"] == "EXTRACTED"
    assert len(email_calls) == 2

    third = await monitor_module.monitor_financial_results()
    assert third["new_filings"] == 0
    assert len(email_calls) == 2
