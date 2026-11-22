from datetime import date, datetime, timezone
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
    assert "Discovery status: SUCCESS" in message
    assert "Timing: Opens 10 Nov 2026" in message
    assert "Status: UNABLE_TO_ASSESS" in message
    assert "Upcoming/unresolved" not in message


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
async def test_daily_digest_sends_pdf_by_email_when_whatsapp_is_enabled(tmp_path, monkeypatch):
    import src.reporting.daily_digest as digest_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "enable_whatsapp", True)
    monkeypatch.setattr(settings, "enable_email", True)
    captured = {}

    async def email_accept(self, recipient, subject, content, metadata=None):
        captured["metadata"] = metadata
        return {"success": True, "accepted": True, "delivered": False, "error": None}

    monkeypatch.setattr(digest_module.EmailProvider, "send_notification", email_accept)
    store = StateStore(root=str(tmp_path / "state"))
    result = await generate_daily_ipo_digest([], store)
    assert result["status"] == "ACCEPTED"
    assert result["channel"] == "EMAIL"
    attachment = captured["metadata"]["attachments"][0]
    assert attachment.endswith(".pdf")
    assert (tmp_path / attachment).exists()


@pytest.mark.asyncio
async def test_daily_digest_sends_html_and_plain_email_when_pdf_rendering_fails(tmp_path, monkeypatch):
    import src.reporting.daily_digest as digest_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "enable_email", True)
    monkeypatch.setattr(settings, "enable_whatsapp", False)
    captured = {}

    def fail_pdf(*_args, **_kwargs):
        raise RuntimeError("renderer unavailable")

    async def email_accept(self, recipient, subject, content, metadata=None):
        captured.update({"content": content, "metadata": metadata})
        return {"success": True, "accepted": True, "delivered": False, "error": None}

    monkeypatch.setattr(digest_module, "markdown_to_pdf", fail_pdf)
    monkeypatch.setattr(digest_module.EmailProvider, "send_notification", email_accept)
    result = await generate_daily_ipo_digest([], StateStore(root=str(tmp_path / "state")))

    assert result["status"] == "ACCEPTED"
    assert result["pdf_available"] is False
    assert captured["content"]
    assert captured["metadata"]["attachments"] == []
    assert captured["metadata"]["html_body"]



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


def test_daily_digest_interprets_naive_database_gmp_timestamp_as_utc():
    from src.reporting.daily_digest import _latest_gmp

    ipo = SimpleNamespace(gmp_snapshots=[
        SimpleNamespace(
            gmp_value=15.0,
            source="IPOWATCH",
            captured_at=datetime(2026, 11, 2, 15, 0),
        )
    ])
    now = datetime(2026, 11, 4, 14, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    display = _latest_gmp(ipo, now)
    assert "15.00" in display
    assert "quote timestamp unavailable" in display


def test_daily_digest_sorts_mixed_timezone_gmp_snapshots_safely():
    from src.reporting.daily_digest import _latest_gmp

    ipo = SimpleNamespace(gmp_snapshots=[
        SimpleNamespace(gmp_value=10.0, source="older", captured_at=datetime(2026, 11, 3, 10, 0)),
        SimpleNamespace(gmp_value=18.0, source="IPOWATCH", captured_at=datetime(2026, 11, 4, 4, 0, tzinfo=timezone.utc)),
    ])
    now = datetime(2026, 11, 4, 11, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

    display = _latest_gmp(ipo, now)
    assert "18.00" in display



def test_empty_digest_explains_incomplete_discovery_without_claiming_no_ipos():
    report, _ = _build_report(
        [],
        now=datetime(2026, 11, 3, 11, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        discovery_run={"status": "PARTIAL"},
        recent_results=[],
    )
    assert "IPO discovery is incomplete" in report
    assert "Do not interpret this empty section as confirmation" in report
    assert "No future-dated IPO records or date-conflict records are currently present" not in report


def test_daily_digest_includes_recent_corporate_financial_results():
    recent = [
        {
            "company_name": "Godavari Biorefineries Limited",
            "symbol": "GODAVARIB",
            "period_ended": "30-Sep-2026",
            "broadcast_time": "04-Nov-2026 19:53:23",
            "statement_basis": "Consolidated",
            "audited_status": "Un-Audited",
            "filing_url": "https://nsearchives.nseindia.in/corporate/godavari_results.pdf",
        }
    ]
    report, message = _build_report(
        [],
        now=datetime(2026, 11, 19, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        discovery_run={"status": "SUCCESS"},
        recent_results=recent,
    )
    assert "## Latest corporate financial results" in report
    assert "Godavari Biorefineries Limited (GODAVARIB)" in report
    assert "Period ended: 30-Sep-2026" in report
    assert "Audited status: Un-Audited" in report
    assert "Statement basis: Consolidated" in report
    assert "https://nsearchives.nseindia.in/corporate/godavari_results.pdf" in report
    assert "Latest corporate financial results (CANDIDATE, not verified):" in message
    assert "GODAVARIB" in message


def test_parse_nse_current_issues_payload():
    from src.ingestion.scrapers import parse_nse_current_issues_payload

    payload = [
        {
            "companyName": "Crystal Crop Protection Limited",
            "symbol": "CRYSTALCP",
            "series": "Equity",
            "issueStartDate": "18-Nov-2026",
            "issueEndDate": "20-Nov-2026",
            "issuePrice": "Rs.259 to Rs.272",
            "noOfSharesOffered": "12170076",
            "status": "Active",
        },
        {
            "companyName": "Watrana Rentals Limited",
            "symbol": "WATRANA",
            "series": "SME",
            "issueStartDate": "19-Nov-2026",
            "issueEndDate": "23-Nov-2026",
            "issuePrice": "Rs.232 to Rs.245",
            "noOfSharesOffered": "3516000",
            "status": "Active",
        },
        {
            "companyName": "offered/ reserved",
            "symbol": "OFFERED",
            "series": "Equity",
        },
    ]
    parsed = parse_nse_current_issues_payload(payload)
    assert len(parsed) == 2
    assert parsed[0]["symbol"] == "CRYSTALCP"
    assert parsed[0]["min_price"] == 259.0
    assert parsed[0]["max_price"] == 272.0
    assert parsed[0]["issue_type"] == "MAINBOARD"
    assert parsed[0]["issue_size_cr"] == 331.03
    assert parsed[1]["symbol"] == "WATRANA"
    assert parsed[1]["issue_type"] == "SME"


def test_collect_recent_financial_reports_reads_results_dir(tmp_path):
    from src.reporting.daily_digest import _collect_recent_financial_reports

    report_file = tmp_path / "CLEAN_30-Sep-2026_1234.md"
    report_file.write_text(
        "# Official financial-results filing: Clean Science and Technology Limited (CLEAN)\n\n"
        "- **Exchange:** NSE\n"
        "- **Period ended:** 30-Sep-2026\n"
        "- **Broadcast time:** 31-Oct-2026 14:33:48\n"
        "- **Audited status:** Un-Audited\n"
        "- **Statement basis:** Consolidated\n"
        "- **Filing attachment:** https://nsearchives.nseindia.in/corporate/clean.pdf\n",
        encoding="utf-8",
    )
    records = _collect_recent_financial_reports(tmp_path)
    assert len(records) == 1
    assert records[0]["symbol"] == "CLEAN"
    assert records[0]["company_name"] == "Clean Science and Technology Limited"
    assert records[0]["period_ended"] == "30-Sep-2026"
    assert records[0]["filing_url"] == "https://nsearchives.nseindia.in/corporate/clean.pdf"


@pytest.mark.asyncio
async def test_daily_digest_sends_pre_open_and_post_close_sessions_separately(tmp_path, monkeypatch):
    import src.reporting.daily_digest as digest_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "enable_whatsapp", False)
    monkeypatch.setattr(settings, "enable_telegram", False)
    monkeypatch.setattr(settings, "enable_email", True)
    monkeypatch.delenv("FORCE_RESEND_DIGEST", raising=False)
    subjects = []

    async def email_accept(self, recipient, subject, content, metadata=None):
        subjects.append(subject)
        return {"success": True, "accepted": True, "delivered": False, "error": None}

    monkeypatch.setattr(digest_module.EmailProvider, "send_notification", email_accept)
    store = StateStore(root=str(tmp_path / "state"))

    monkeypatch.setenv("DIGEST_SESSION", "PRE_OPEN")
    morning = await generate_daily_ipo_digest([], store)
    morning_repeat = await generate_daily_ipo_digest([], store)
    monkeypatch.setenv("DIGEST_SESSION", "post_close")
    evening = await generate_daily_ipo_digest([], store)

    assert morning["status"] == "ACCEPTED"
    assert morning["event_key"].endswith("_PRE_OPEN")
    assert morning["report_path"].endswith("_pre_open.md")
    assert morning_repeat["status"] == "ALREADY_SENT"
    assert evening["status"] == "ACCEPTED"
    assert evening["event_key"].endswith("_POST_CLOSE")
    assert len(subjects) == 2
    assert subjects[0].startswith("Pre-market IPO status digest")
    assert subjects[1].startswith("Post-market IPO status digest")


@pytest.mark.asyncio
async def test_daily_digest_without_session_keeps_single_daily_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "enable_whatsapp", False)
    monkeypatch.setattr(settings, "enable_telegram", False)
    monkeypatch.setattr(settings, "enable_email", False)
    monkeypatch.delenv("DIGEST_SESSION", raising=False)
    result = await generate_daily_ipo_digest([], StateStore(root=str(tmp_path / "state")))
    assert result["event_key"].startswith("IPO_DAILY_DIGEST_")
    assert result["event_key"].count("_") == 3


def test_ipo_timing_labels_open_now_upcoming_and_closed():
    from src.reporting.daily_digest import _ipo_timing

    today = date(2026, 11, 22)
    open_now = SimpleNamespace(
        verified_open_date=date(2026, 11, 19), verified_close_date=date(2026, 11, 23),
        announced_open_date=None, announced_close_date=None,
    )
    upcoming = SimpleNamespace(
        verified_open_date=date(2026, 11, 25), verified_close_date=date(2026, 11, 27),
        announced_open_date=None, announced_close_date=None,
    )
    closed = SimpleNamespace(
        verified_open_date=date(2026, 11, 10), verified_close_date=date(2026, 11, 12),
        announced_open_date=None, announced_close_date=None,
    )
    unverified = SimpleNamespace(
        verified_open_date=None, verified_close_date=None,
        announced_open_date=date(2026, 11, 25), announced_close_date=date(2026, 11, 27),
    )
    assert _ipo_timing(open_now, today) == "Open now, closes 23 Nov 2026"
    assert _ipo_timing(upcoming, today) == "Opens 25 Nov 2026, closes 27 Nov 2026"
    assert _ipo_timing(closed, today) == "Closed 12 Nov 2026; listing date pending"
    assert _ipo_timing(unverified, today).endswith("(dates announced, not verified)")


def test_digest_footer_points_to_pdf_or_run_without_claiming_delivery(monkeypatch):
    from src.reporting.daily_digest import _digest_footer

    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    assert _digest_footer(True) == "Full report: the attached PDF. Not investment advice."
    footer = _digest_footer(False)
    assert "actions/runs/123" in footer and "PDF not available this run" in footer
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    assert "actions/runs" not in _digest_footer(False)


def _results_section(report: str) -> str:
    start = report.index("## Latest corporate financial results")
    end = report.index("## Important limitation")
    return report[start:end]


def test_results_entries_are_labelled_candidate_not_verified_and_never_verified():
    recent = [
        {
            "company_name": "Godavari Biorefineries Limited",
            "symbol": "GODAVARIB",
            "period_ended": "30-Sep-2026",
            "broadcast_time": "04-Nov-2026 19:53:23",
            "statement_basis": "Consolidated",
            "audited_status": "Un-Audited",
            "filing_url": "https://nsearchives.nseindia.in/corporate/godavari_results.pdf",
            "candidate_figures": [("Revenue from operations", "₹1,234.56 Cr")],
        }
    ]
    report, message = _build_report(
        [],
        now=datetime(2026, 11, 19, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        discovery_run={"status": "SUCCESS"},
        recent_results=recent,
    )
    section = _results_section(report)
    assert "CANDIDATE, not verified" in section
    assert "VERIFIED" not in section
    assert "VERIFIED" not in message
    assert "CANDIDATE, not verified" in message
    assert "Revenue from operations: ₹1,234.56 Cr (candidate, not verified)" in section
    assert "Revenue from operations: ₹1,234.56 Cr (candidate, not verified)" in message


def test_results_missing_source_fields_are_shown_as_source_not_captured():
    recent = [
        {
            "company_name": "Clean Science and Technology Limited",
            "symbol": "CLEAN",
            "period_ended": "",
            "broadcast_time": "",
            "statement_basis": "",
            "audited_status": "",
            "filing_url": "",
            "candidate_figures": [],
        }
    ]
    report, message = _build_report(
        [],
        now=datetime(2026, 11, 19, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        discovery_run={"status": "SUCCESS"},
        recent_results=recent,
    )
    section = _results_section(report)
    assert "Period ended: source not captured" in section
    assert "Source: source not captured" in section
    assert "Audited status: source not captured" in section
    assert "Broadcast time: source not captured" in section
    assert "Not linked" not in section
    assert "Period ended source not captured" not in message
    assert "source not captured" in message
    assert "Not linked" not in message


def test_collector_reads_only_present_candidate_figures_and_treats_placeholders_as_missing(tmp_path):
    from src.reporting.daily_digest import _collect_recent_financial_reports

    (tmp_path / "ABC_30-Sep-2026_1.md").write_text(
        "# Official financial-results filing: Alpha Limited (ALPHA)\n\n"
        "- **Period ended:** Not specified in the filing notice or attachment header\n"
        "- **Broadcast time:** 31-Oct-2026 10:00:00\n"
        "- **Audited status:** Not specified\n"
        "- **Statement basis:** Not specified\n"
        "- **Filing attachment:** Not available\n\n"
        "## Extracted financial metrics\n\n"
        "- **Revenue from operations:** ₹1,234.56 Cr\n"
        "- **Profit after tax (PAT):** Not available\n"
        "- **EPS:** ₹12.00\n"
        "- **Operating cash flow:** Not available\n",
        encoding="utf-8",
    )
    records = _collect_recent_financial_reports(tmp_path)
    assert len(records) == 1
    record = records[0]
    assert record["period_ended"] == ""
    assert record["audited_status"] == ""
    assert record["statement_basis"] == ""
    assert record["filing_url"] == ""
    assert record["candidate_figures"] == [
        ("Revenue from operations", "₹1,234.56 Cr"),
        ("EPS", "₹12.00"),
    ]


def _subscription_card(snapshots):
    from src.reporting.daily_digest import _plain_company_summary

    ipo = SimpleNamespace(
        company_name="Test Co",
        symbol="TESTCO",
        min_price=100.0,
        max_price=110.0,
        issue_size_cr=250.0,
        subscription_snapshots=snapshots,
    )
    now = datetime(2026, 11, 23, 10, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    return _plain_company_summary(ipo, now).splitlines()


def test_card_shows_fresh_nse_subscription_as_line_directly_under_price_band():
    lines = _subscription_card([
        SimpleNamespace(overall_times=11.1, captured_at=datetime(2026, 11, 23, 4, 0)),
    ])
    price_index = next(i for i, line in enumerate(lines) if line.strip().startswith("Price band:"))
    assert lines[price_index + 1] == "  Subscription: 11.10x (NSE bids, latest, not final)"


def test_card_shows_not_available_when_no_subscription_snapshot():
    lines = _subscription_card([])
    assert "  Subscription: not available from NSE feed" in lines


def test_card_subscription_ignores_stale_snapshot_and_formats_two_decimals():
    lines = _subscription_card([
        SimpleNamespace(overall_times=0.1, captured_at=datetime(2026, 11, 20, 4, 0)),
    ])
    assert "  Subscription: not available from NSE feed" in lines

    lines = _subscription_card([
        SimpleNamespace(overall_times=0.11, captured_at=datetime(2026, 11, 23, 3, 0)),
    ])
    assert "  Subscription: 0.11x (NSE bids, latest, not final)" in lines
