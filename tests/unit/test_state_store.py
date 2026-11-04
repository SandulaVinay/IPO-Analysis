import json
from datetime import datetime, timedelta, timezone
import pytest

from src.state.store import StateStore


def test_state_store_records_only_sanitized_event_metadata(tmp_path):
    store = StateStore(str(tmp_path))
    store.record_event(
        "T2_EXAMPLE_2026-11-10",
        event_type="T_MINUS_2",
        symbol="EXAMPLE",
        event_date="2026-11-10",
        status="ACCEPTED",
        channel="WHATSAPP",
    )
    assert store.has_processed_event("T2_EXAMPLE_2026-11-10")

    outbox = json.loads((tmp_path / "notification_outbox.json").read_text(encoding="utf-8"))
    assert len(outbox["events"]) == 1
    event = outbox["events"][0]
    assert event["symbol"] == "EXAMPLE"
    assert event["status"] == "ACCEPTED"
    assert "recipient" not in event
    assert "message_content" not in event
    assert "email" not in event
    assert "phone" not in event


def test_state_store_does_not_mark_failed_events_as_processed(tmp_path):
    store = StateStore(str(tmp_path))
    store.record_event(
        "T2_EXAMPLE_2026-11-10",
        event_type="T_MINUS_2",
        symbol="EXAMPLE",
        event_date="2026-11-10",
        status="FAILED",
        channel=None,
    )
    assert not store.has_processed_event("T2_EXAMPLE_2026-11-10")


def test_state_store_keeps_extraction_status_for_retryable_filing_events(tmp_path):
    store = StateStore(str(tmp_path))
    store.record_event(
        "RESULT_EXAMPLE",
        event_type="FINANCIAL_RESULTS_FILING",
        symbol="EXAMPLE",
        event_date="2026-11-04",
        status="ACCEPTED",
        channel="EMAIL",
        processing_status="UNAVAILABLE",
    )
    assert store.has_processed_event("RESULT_EXAMPLE")
    assert store.event_record("RESULT_EXAMPLE")["processing_status"] == "UNAVAILABLE"



def test_watchlist_symbols_are_validated_before_use(tmp_path):
    store = StateStore(str(tmp_path))
    (tmp_path / "watchlist.json").write_text(
        json.dumps({
            "schema_version": 1,
            "companies": [{"symbol": "M&M", "company_name": "Mahindra & Mahindra Limited"}],
        }),
        encoding="utf-8",
    )
    assert store.load_watchlist()[0]["symbol"] == "M&M"

    (tmp_path / "watchlist.json").write_text(
        json.dumps({"schema_version": 1, "companies": [{"symbol": "../../evil"}]}),
        encoding="utf-8",
    )
    import pytest
    with pytest.raises(RuntimeError, match="unsupported characters"):
        store.load_watchlist()



def test_document_registry_deduplicates_versions_and_rechecks_after_seven_days(tmp_path):
    store = StateStore(str(tmp_path))
    common = {
        "symbol": "EXAMPLE",
        "company_name": "Example Limited",
        "document_type": "RHP",
        "document_title": "Red Herring Prospectus",
        "source_url": "https://www.nseindia.com/example-rhp.pdf",
        "page_count": 100,
        "text_pages_extracted": 90,
        "evidence_count": 5,
        "processing_status": "PARSED",
    }
    first_label = store.record_document(**common, document_hash="a" * 64, version_label="v1")
    assert first_label == "v1"
    assert store.has_document_url(common["source_url"]) is True

    second_label = store.record_document(**common, document_hash="b" * 64, version_label="v1")
    assert second_label == "v2"
    payload = json.loads((tmp_path / "document_registry.json").read_text(encoding="utf-8"))
    assert len(payload["documents"]) == 2

    stale_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    for document in payload["documents"]:
        document["last_checked_at"] = stale_time
    (tmp_path / "document_registry.json").write_text(json.dumps(payload), encoding="utf-8")
    assert store.has_document_url(common["source_url"]) is False



def test_public_document_registry_redacts_token_like_query_parameters(tmp_path):
    store = StateStore(str(tmp_path))
    source_url = "https://nsearchives.nseindia.com/rhp.pdf?token=private-token&download=1"
    store.record_document(
        symbol="EXAMPLE",
        company_name="Example Limited",
        document_type="RHP",
        document_title="Example RHP",
        source_url=source_url,
        document_hash="c" * 64,
        version_label="v1",
        page_count=50,
        text_pages_extracted=45,
        evidence_count=2,
        processing_status="PARSED",
    )
    payload_text = (tmp_path / "document_registry.json").read_text(encoding="utf-8")
    payload = json.loads(payload_text)
    assert "private-token" not in payload_text
    assert "token=" not in payload["documents"][0]["source_url"]
    assert store.has_document_url(source_url) is True


@pytest.mark.asyncio
async def test_public_ipo_registry_persists_only_latest_unofficial_gmp_snapshot(tmp_path):
    from types import SimpleNamespace

    ipo = SimpleNamespace(
        symbol="EXAMPLE",
        company_name="Example Industries Limited",
        industry=None,
        issue_type="MAINBOARD",
        status="IPO_DISCOVERED",
        announced_open_date=None,
        announced_close_date=None,
        verified_open_date=None,
        verified_close_date=None,
        min_price=100.0,
        max_price=110.0,
        lot_size=None,
        issue_size_cr=None,
        fresh_issue_cr=None,
        ofs_cr=None,
        gmp_snapshots=[
            SimpleNamespace(
                source="IPOWATCH",
                gmp_value=15.0,
                upper_price=110.0,
                captured_at=datetime(2026, 11, 4, 10, 0),
                trend="UNKNOWN",
            ),
            SimpleNamespace(
                source="Other Source",
                gmp_value=999.0,
                upper_price=110.0,
                captured_at=datetime(2026, 11, 4, 11, 0),
                trend="UNKNOWN",
            ),
        ],
    )

    class Result:
        def scalars(self):
            return self

        def all(self):
            return [ipo]

    class Session:
        async def execute(self, _statement):
            return Result()

    store = StateStore(str(tmp_path))
    assert await store.save_ipo_registry(Session()) == 1
    payload = json.loads((tmp_path / "ipo_registry.json").read_text(encoding="utf-8"))
    snapshot = payload["ipos"][0]["gmp_snapshots"][0]
    assert snapshot["source"] == "IPOWATCH"
    assert snapshot["gmp_value"] == 15.0
    assert snapshot["upper_price"] == 110.0
    assert "Other Source" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_restore_ipo_registry_skips_gmp_from_a_different_price_band(tmp_path, async_session):
    from src.database.repository import IPORepository

    store = StateStore(str(tmp_path))
    (tmp_path / "ipo_registry.json").write_text(json.dumps({
        "schema_version": 1,
        "ipos": [{
            "symbol": "EXAMPLE",
            "company_name": "Example Limited",
            "max_price": 120.0,
            "gmp_snapshots": [{
                "gmp_value": 20.0,
                "upper_price": 110.0,
                "captured_at": "2026-11-04T10:00:00+00:00",
                "source": "IPOWATCH",
                "trend": "UNKNOWN",
            }],
        }],
    }), encoding="utf-8")

    assert await store.restore_ipo_registry(async_session) == 1
    ipo = await IPORepository(async_session).get_ipo_by_symbol("EXAMPLE")
    assert ipo.max_price == 120.0
    assert ipo.gmp_snapshots == []



def test_watchlist_accepts_bse_scrip_code_and_rejects_missing_code(tmp_path):
    import pytest

    store = StateStore(str(tmp_path))
    path = tmp_path / "watchlist.json"
    path.write_text(
        json.dumps({
            "schema_version": 1,
            "companies": [{
                "exchange": "BSE",
                "symbol": "RNITAI",
                "bse_scrip_code": "517286",
                "company_name": "RNIT AI SOLUTIONS LIMITED",
                "company_name_aliases": ["RNIT AI Solutions Ltd"],
            }],
        }),
        encoding="utf-8",
    )
    entry = store.load_watchlist()[0]
    assert entry["exchange"] == "BSE"
    assert entry["bse_scrip_code"] == "517286"

    path.write_text(
        json.dumps({
            "schema_version": 1,
            "companies": [{
                "exchange": "BSE",
                "symbol": "RNITAI",
                "company_name": "RNIT AI SOLUTIONS LIMITED",
            }],
        }),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="six-digit bse_scrip_code"):
        store.load_watchlist()
