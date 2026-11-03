from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.common.config import settings
from src.reporting.daily_digest import _build_report, generate_daily_ipo_digest
from src.state.store import StateStore


def test_daily_digest_fails_closed_and_links_official_sources():
    ipo = SimpleNamespace(
        symbol="TEST",
        company_name="Test Issuer Limited",
        status="IPO_DISCOVERED",
        verified_open_date=date(2026, 11, 10),
        verified_close_date=date(2026, 11, 15),
        announced_open_date=None,
        announced_close_date=None,
        min_price=None,
        max_price=None,
        issue_size_cr=None,
    )
    report, message = _build_report(
        [ipo],
        now=datetime(2026, 10, 29, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        discovery_run={"status": "SUCCESS"},
    )
    assert "UNABLE_TO_ASSESS" in report
    assert "not an investment recommendation" in report.lower()
    assert "### Test Issuer Limited (TEST)" in report
    assert "Company-specific prospectus/source link: Not captured yet" in report
    assert "## Official source pages" not in report
    assert "Overall rating: Unavailable / 10" in report
    assert "GMP (grey-market premium): Not available from a captured snapshot" in report
    assert "No APPLY/AVOID" in report
    assert "Latest discovery status: SUCCESS" in message


def test_daily_digest_marks_cached_state_stale_when_discovery_failed():
    report, message = _build_report(
        [],
        now=datetime(2026, 10, 29, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        discovery_run={"status": "FAILED"},
    )
    assert "may be stale" in report
    assert "may be stale" in message


@pytest.mark.asyncio
async def test_daily_digest_creates_report_without_claiming_delivery_when_channels_disabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "enable_whatsapp", False)
    monkeypatch.setattr(settings, "enable_email", False)
    store = StateStore(root=str(tmp_path / "state"))
    ipo = SimpleNamespace(
        symbol="TEST",
        company_name="Test Issuer Limited",
        status="IPO_DISCOVERED",
        verified_open_date=date(2026, 11, 10),
        verified_close_date=date(2026, 11, 15),
        announced_open_date=None,
        announced_close_date=None,
        min_price=None,
        max_price=None,
        issue_size_cr=None,
    )
    result = await generate_daily_ipo_digest([ipo], store)
    assert result["status"] == "REPORT_ONLY"
    assert result["notifications_accepted"] == 0
    assert (tmp_path / result["report_path"]).exists()
    pdf_path = (tmp_path / result["report_path"]).with_suffix(".pdf")
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF-")



@pytest.mark.asyncio
async def test_daily_digest_uses_email_fallback_with_pdf_when_whatsapp_fails(tmp_path, monkeypatch):
    import src.reporting.daily_digest as digest_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "enable_whatsapp", True)
    monkeypatch.setattr(settings, "enable_email", True)
    captured = {}

    async def whatsapp_fail(self, recipient, subject, content, metadata=None):
        return {"success": False, "accepted": False, "delivered": False, "error": "test failure"}

    async def email_accept(self, recipient, subject, content, metadata=None):
        captured["metadata"] = metadata
        return {"success": True, "accepted": True, "delivered": False, "error": None}

    monkeypatch.setattr(digest_module.WhatsAppProvider, "send_notification", whatsapp_fail)
    monkeypatch.setattr(digest_module.EmailProvider, "send_notification", email_accept)
    store = StateStore(root=str(tmp_path / "state"))
    result = await generate_daily_ipo_digest([], store)
    assert result["status"] == "ACCEPTED"
    assert result["channel"] == "EMAIL"
    attachment = captured["metadata"]["attachments"][0]
    assert attachment.endswith(".pdf")
    assert (tmp_path / attachment).exists()



def test_daily_digest_labels_announced_dates_when_verified_dates_are_missing():
    ipo = SimpleNamespace(
        symbol="CONFLICT",
        company_name="Conflict Issuer Limited",
        status="SOURCE_CONFLICT",
        verified_open_date=None,
        verified_close_date=None,
        announced_open_date=date(2026, 11, 10),
        announced_close_date=date(2026, 11, 15),
        min_price=None,
        max_price=None,
        issue_size_cr=None,
    )
    report, _ = _build_report(
        [ipo],
        now=datetime(2026, 10, 29, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        discovery_run={"status": "SUCCESS"},
    )
    assert "announced; not verified" in report
    assert "WAIT" in report



def test_daily_digest_includes_verified_weighted_rating_and_company_specific_links():
    ipo = SimpleNamespace(
        symbol="TEST",
        company_name="Test Issuer Limited",
        status="IPO_DISCOVERED",
        verified_open_date=date(2026, 11, 10),
        verified_close_date=date(2026, 11, 15),
        announced_open_date=None,
        announced_close_date=None,
        min_price=100,
        max_price=110,
        issue_size_cr=250,
        listing_potential_score=8.0,
        long_term_quality_score=7.0,
        rating_verified=True,
        source_url="https://www.nseindia.com/company/test-issuer-rhp",
        document_links=[{"document_title": "Red Herring Prospectus", "source_url": "https://www.nseindia.com/company/test-issuer-rhp"}],
        gmp_snapshots=[],
    )
    report, message = _build_report(
        [ipo],
        now=datetime(2026, 10, 29, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        discovery_run={"status": "SUCCESS"},
    )
    assert "Overall rating: 7.4/10" in report
    assert "Listing potential: 8.0/10" in report
    assert "Long-term quality: 7.0/10" in report
    assert "[Red Herring Prospectus](https://www.nseindia.com/company/test-issuer-rhp)" in report
    assert "Official NSE:" not in message
    assert "Official BSE:" not in message


def test_daily_digest_does_not_use_old_gmp_as_current():
    from src.reporting.daily_digest import _latest_gmp

    ipo = SimpleNamespace(gmp_snapshots=[
        SimpleNamespace(
            gmp_value=35.0,
            source="test source",
            captured_at=datetime(2026, 10, 25, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        )
    ])
    now = datetime(2026, 10, 29, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert "Stale snapshot" in _latest_gmp(ipo, now)
    assert "not used as current GMP" in _latest_gmp(ipo, now)
