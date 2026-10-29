import json

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
