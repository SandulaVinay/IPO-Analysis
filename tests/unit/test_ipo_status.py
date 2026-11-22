from src.analysis.ipo_status import ipo_status


def _run(**overrides):
    args = dict(source_conflict=False, gmp_value=None, issue_price=100.0, overall_subscription=None)
    args.update(overrides)
    return ipo_status(**args)


def test_source_conflict_waits_regardless_of_gmp():
    assert _run(source_conflict=True, gmp_value=80, overall_subscription=50)["status"] == "WAIT"


def test_missing_gmp_is_unable_to_assess_not_neutral():
    result = _run(gmp_value=None)
    assert result["status"] == "UNABLE_TO_ASSESS"
    assert result["estimated_listing_gain_pct"] is None


def test_missing_issue_price_is_unable_to_assess():
    assert _run(gmp_value=20, issue_price=None)["status"] == "UNABLE_TO_ASSESS"


def test_negative_gmp_gain_is_avoid():
    result = _run(gmp_value=-5, overall_subscription=50)
    assert result["status"] == "AVOID"
    assert result["estimated_listing_gain_pct"] == -5.0


def test_missing_subscription_caps_strong_gain_at_neutral():
    result = _run(gmp_value=50)
    assert result["status"] == "NEUTRAL"
    assert "subscription data is not connected" in result["reasons"][0]


def test_strong_gain_and_strong_subscription_is_apply():
    result = _run(gmp_value=35, overall_subscription=12.0)
    assert result["status"] == "APPLY"
    assert result["estimated_listing_gain_pct"] == 35.0


def test_gain_below_threshold_is_neutral_even_with_strong_subscription():
    assert _run(gmp_value=5, overall_subscription=50)["status"] == "NEUTRAL"


def test_weak_subscription_is_neutral_even_with_strong_gain():
    assert _run(gmp_value=40, overall_subscription=3.0)["status"] == "NEUTRAL"


def test_every_result_is_labelled_indicative():
    assert "Indicative" in _run(gmp_value=35, overall_subscription=12.0)["label"]


def test_digest_card_shows_status_with_fresh_gmp_and_no_subscription():
    from datetime import datetime
    from types import SimpleNamespace

    from src.reporting.daily_digest import _plain_company_summary

    now = datetime(2026, 11, 22, 12, 0)
    ipo = SimpleNamespace(
        company_name="Example Ltd", symbol="EXMPL", status="IPO_DISCOVERED",
        verified_open_date=None, verified_close_date=None,
        announced_open_date=None, announced_close_date=None,
        min_price=100, max_price=100, issue_size_cr=None,
        # Stored timestamps are naive UTC; 04:30 UTC is 10:00 IST, two hours before `now`.
        gmp_snapshots=[SimpleNamespace(gmp_value=40, captured_at=datetime(2026, 11, 22, 4, 30), source="IPOWATCH")],
        subscription_snapshots=[],
        analysis_runs=[],
    )
    card = _plain_company_summary(ipo, now)
    assert "Status: NEUTRAL" in card
    assert "estimated listing gain +40.0% (unofficial GMP)" in card
    assert "subscription data is not connected" in card


def test_digest_uses_latest_nse_subscription_snapshot():
    from datetime import datetime, timedelta
    from types import SimpleNamespace

    from src.reporting.daily_digest import _latest_subscription

    now = datetime(2026, 11, 22, 12, 0)
    older = SimpleNamespace(overall_times=3.0, captured_at=datetime(2026, 11, 22, 3, 0), day_number=0)
    newer = SimpleNamespace(overall_times=11.1, captured_at=datetime(2026, 11, 22, 4, 0), day_number=0)
    ipo = SimpleNamespace(subscription_snapshots=[newer, older])
    assert _latest_subscription(ipo, now) == 11.1
    stale = SimpleNamespace(overall_times=9.0, captured_at=now - timedelta(days=3), day_number=0)
    assert _latest_subscription(SimpleNamespace(subscription_snapshots=[stale]), now) is None
