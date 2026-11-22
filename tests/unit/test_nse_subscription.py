import json
from pathlib import Path

from src.ingestion.nse_subscription import parse_nse_subscription_payload

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "nse_ipo_current_issue.json"


def test_parses_real_nse_response_multiples():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = parse_nse_subscription_payload(payload)
    assert set(result) == {"MAHACOAL", "WATRANA"}
    assert round(result["MAHACOAL"]["overall_times"], 2) == 0.11
    assert result["WATRANA"]["overall_times"] == 11.10
    assert result["WATRANA"]["bids"] == 39024600.0


def test_non_list_payload_gives_nothing():
    assert parse_nse_subscription_payload({"data": []}) == {}
    assert parse_nse_subscription_payload(None) == {}


def test_bad_or_missing_multiple_is_skipped_not_zero():
    payload = [
        {"symbol": "ABC", "noOfTime": "n/a"},
        {"symbol": "DEF", "noOfTime": "-3"},
        {"symbol": "", "noOfTime": "5"},
        {"symbol": "GHI"},
    ]
    assert parse_nse_subscription_payload(payload) == {}


def test_per_category_rows_do_not_overwrite_total():
    payload = [
        {"symbol": "XYZ", "category": "Total", "noOfTime": "4.5"},
        {"symbol": "XYZ", "category": "QIB", "noOfTime": "1.0"},
        {"symbol": "XYZ", "category": "Retail", "noOfTime": "9.9"},
    ]
    assert parse_nse_subscription_payload(payload)["XYZ"]["overall_times"] == 4.5
