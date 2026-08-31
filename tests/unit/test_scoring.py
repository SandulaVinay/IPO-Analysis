"""
Unit tests for Decision Engine, Multi-Horizon Scoring, and Hard Safety Gates.
"""

import pytest
from src.scoring.engine import ScoringEngine
from src.scoring.safety_gates import SafetyGateEvaluator
from src.scoring.horizons import MultiHorizonClassifier


def test_safety_gate_triggering():
    # 1. Test missing critical data gate
    completeness_bad = {
        "missing_critical_fields": ["verified_open_date", "min_price", "pat_latest", "cfo_latest"]
    }
    is_gated, reasons = SafetyGateEvaluator.evaluate_gates(
        completeness_info=completeness_bad,
        conflict_info={"is_critical_tier1_conflict": False},
        management_info={"has_critical_governance_flag": False},
        financial_info={},
    )
    assert is_gated is True
    assert len(reasons) > 0

    # 2. Test Tier-1 conflict gate
    conflict_bad = {
        "is_critical_tier1_conflict": True,
        "conflict_details": "NSE vs BSE contradict on opening date",
    }
    is_gated2, reasons2 = SafetyGateEvaluator.evaluate_gates(
        completeness_info={"missing_critical_fields": []},
        conflict_info=conflict_bad,
        management_info={"has_critical_governance_flag": False},
        financial_info={},
    )
    assert is_gated2 is True

    # 3. Clean case (No gates triggered)
    is_gated_clean, reasons_clean = SafetyGateEvaluator.evaluate_gates(
        completeness_info={"missing_critical_fields": []},
        conflict_info={"is_critical_tier1_conflict": False},
        management_info={"has_critical_governance_flag": False},
        financial_info={},
    )
    assert is_gated_clean is False
    assert len(reasons_clean) == 0


def test_multi_horizon_classification():
    # Strong company
    horizons = MultiHorizonClassifier.classify_horizons(
        business_score=8.5,
        financial_score=8.5,
        governance_score=8.0,
        valuation_score=7.5,
        risk_score=7.5,
        gmp_gain_pct=25.0,
        subscription_times=15.0,
        is_gated=False,
    )
    assert horizons["verdict"] == "ATTRACTIVE"
    assert horizons["company_quality"] >= 8.0
    assert horizons["listing_opportunity"] >= 8.0

    # Gated company
    gated_horizons = MultiHorizonClassifier.classify_horizons(
        business_score=8.5,
        financial_score=8.5,
        governance_score=8.0,
        valuation_score=7.5,
        risk_score=7.5,
        gmp_gain_pct=25.0,
        subscription_times=15.0,
        is_gated=True,
    )
    assert gated_horizons["verdict"] == "UNABLE_TO_ASSESS"
    assert gated_horizons["overall_score"] if "overall_score" in gated_horizons else True


def test_scoring_engine_composite():
    engine = ScoringEngine()
    result = engine.compute_decision(
        business_score=9.0,
        financial_score=8.5,
        governance_score=8.0,
        structure_score=7.5,
        valuation_score=8.0,
        growth_score=8.5,
        risk_score=7.0,
        sentiment_score=8.0,
        completeness_info={"missing_critical_fields": []},
        conflict_info={"is_critical_tier1_conflict": False},
        management_info={"has_critical_governance_flag": False},
        financial_info={},
    )
    assert result["is_safety_gated"] is False
    assert result["verdict"] == "ATTRACTIVE"
    assert result["overall_score"] >= 8.0
