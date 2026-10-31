from src.analysis.financials import FinancialAnalyzer
from src.scoring.safety_gates import SafetyGateEvaluator


def test_one_missing_critical_field_blocks_assessment():
    gated, reasons = SafetyGateEvaluator.evaluate_gates(
        completeness_info={"missing_critical_fields": ["pat_latest"]},
        conflict_info={"is_critical_tier1_conflict": False},
        management_info={"has_critical_governance_flag": False},
        financial_info={},
    )
    assert gated is True
    assert "pat_latest" in reasons[0]


def test_unverified_financial_evidence_blocks_assessment():
    gated, reasons = SafetyGateEvaluator.evaluate_gates(
        completeness_info={"missing_critical_fields": []},
        conflict_info={"is_critical_tier1_conflict": False},
        management_info={"has_critical_governance_flag": False},
        financial_info={"verification_status": "CANDIDATE_UNVERIFIED"},
    )
    assert gated is True
    assert any("not verified" in reason for reason in reasons)


def test_financial_analyzer_does_not_return_neutral_scores_without_history():
    result = FinancialAnalyzer.analyze_financials([])
    assert result["assessment_status"] == "UNABLE_TO_ASSESS"
    assert result["financial_quality_score"] is None
    assert result["earnings_quality_score"] is None


def test_financial_analyzer_requires_revenue_and_pat_for_each_period():
    result = FinancialAnalyzer.analyze_financials([
        {"period_name": "FY24", "revenue": 100.0, "pat": 10.0},
        {"period_name": "FY25", "revenue": 120.0},
    ])
    assert result["assessment_status"] == "UNABLE_TO_ASSESS"
    assert result["financial_quality_score"] is None


def test_financial_analyzer_omits_earnings_score_without_operating_cash_flow():
    result = FinancialAnalyzer.analyze_financials([
        {"period_name": "FY24", "revenue": 100.0, "pat": 10.0},
        {"period_name": "FY25", "revenue": 120.0, "pat": 12.0},
    ])
    assert result["assessment_status"] == "ASSESSED_WITH_LIMITATIONS"
    assert result["financial_quality_score"] is not None
    assert result["earnings_quality_score"] is None


def test_financial_analyzer_scores_complete_periods_and_detects_red_flags():
    result = FinancialAnalyzer.analyze_financials([
        {"period_name": "FY24", "revenue": 100.0, "pat": 10.0, "cfo": 4.0, "net_debt": 250.0, "net_worth": 100.0},
        {"period_name": "FY25", "revenue": 120.0, "pat": 12.0, "cfo": -1.0, "net_debt": 300.0, "net_worth": 100.0},
    ])
    assert result["assessment_status"] == "ASSESSED"
    assert result["earnings_quality_score"] is not None
    assert any("Negative operating cash flow" in flag for flag in result["red_flags"])
    assert any("High financial leverage" in flag for flag in result["red_flags"])
