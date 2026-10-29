import json
from datetime import datetime, timedelta, timezone

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
