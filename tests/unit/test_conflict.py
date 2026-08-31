"""
Unit tests for Source Conflict Engine and Tier-1 Precedence.
"""

from src.verification.conflict import SourceConflictEngine


def test_source_conflict_resolution():
    # 1. Tier 1 vs Tier 2 disagreement (e.g. NSE says 18 Sep, Secondary portal says 19 Sep)
    sources = [
        {"source_name": "NSE", "source_tier": "TIER_1", "value": "2026-09-18"},
        {"source_name": "SecondaryPortal", "source_tier": "TIER_2", "value": "2026-09-19"},
    ]
    res = SourceConflictEngine.compare_field_values("opening_date", sources)
    assert res["has_conflict"] is True
    assert res["is_critical_tier1_conflict"] is False
    assert res["selected_value"] == "2026-09-18"  # Tier 1 used

    # 2. Critical disagreement between two Tier 1 sources (e.g. NSE vs BSE)
    tier1_conflict = [
        {"source_name": "NSE", "source_tier": "TIER_1", "value": "2026-09-18"},
        {"source_name": "BSE", "source_tier": "TIER_1", "value": "2026-09-20"},
    ]
    res2 = SourceConflictEngine.compare_field_values("opening_date", tier1_conflict)
    assert res2["has_conflict"] is True
    assert res2["is_critical_tier1_conflict"] is True
    assert res2["selected_value"] is None  # Refuse to guess

    # 3. Complete Agreement
    sources_agree = [
        {"source_name": "NSE", "source_tier": "TIER_1", "value": "475"},
        {"source_name": "RHP", "source_tier": "TIER_1", "value": "475"},
        {"source_name": "Portal", "source_tier": "TIER_2", "value": "475"},
    ]
    res3 = SourceConflictEngine.compare_field_values("max_price", sources_agree)
    assert res3["has_conflict"] is False
    assert res3["selected_value"] == "475"
