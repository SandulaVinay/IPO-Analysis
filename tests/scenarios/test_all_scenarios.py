"""
Comprehensive Scenario Tests covering all 11 realistic Indian IPO market fixtures:
1. Strong High-Growth IPO
2. Expensive Valuation IPO
3. OFS-Heavy (Exit money) IPO
4. Loss-Making Tech IPO
5. Financial Services (Bank/NBFC) IPO
6. Manufacturing Asset-Heavy IPO
7. Technology SaaS IPO
8. IPO with Conflicting Sources
9. IPO with Missing Financial Data (Safety Gate Triggered)
10. IPO with Changed Price Band (Diff Engine Triggered)
11. IPO with Changed Opening Date (Diff Engine Triggered)
"""

import pytest
from datetime import date
from src.analysis import (
    BusinessAnalyzer,
    ManagementAnalyzer,
    StructureAnalyzer,
    FinancialAnalyzer,
    ValuationEngine,
    PeerSelectionEngine,
    AnomalyDetector,
    RiskEngine,
)
from src.scoring.engine import ScoringEngine
from src.scoring.safety_gates import SafetyGateEvaluator
from src.documents.diff import DocumentDiffEngine
from src.verification.conflict import SourceConflictEngine
from src.verification.engine import VerificationEngine


# Scenario 1: Strong High-Growth IPO
def test_scenario_1_strong_ipo():
    periods = [
        {"period_name": "FY23", "revenue": 500.0, "pat": 50.0, "cfo": 45.0, "net_debt": 0.0, "net_worth": 200.0},
        {"period_name": "FY24", "revenue": 700.0, "pat": 85.0, "cfo": 80.0, "net_debt": 0.0, "net_worth": 285.0},
        {"period_name": "FY25", "revenue": 1000.0, "pat": 140.0, "cfo": 135.0, "net_debt": 0.0, "net_worth": 425.0},
    ]
    fin = FinancialAnalyzer.analyze_financials(periods)
    biz = BusinessAnalyzer.analyze_business({"top5_customer_concentration_pct": 20.0, "recurring_revenue_pct": 70.0, "has_proprietary_tech_or_moat": True})
    struct = StructureAnalyzer.analyze_structure({"issue_size_cr": 1000.0, "fresh_issue_cr": 800.0, "ofs_cr": 200.0})
    val = ValuationEngine.evaluate_valuation(issue_price=400.0, post_issue_shares_cr=10.0, total_debt_cr=0.0, cash_cr=100.0, latest_pat_cr=140.0, latest_ebitda_cr=220.0, latest_revenue_cr=1000.0, net_worth_cr=425.0, peer_median_pe=38.0, peer_median_ev_ebitda=24.0)
    
    scoring = ScoringEngine()
    res = scoring.compute_decision(
        business_score=biz["business_quality_score"],
        financial_score=fin["financial_quality_score"],
        governance_score=8.5,
        structure_score=struct["ipo_structure_score"],
        valuation_score=val["valuation_score"],
        growth_score=9.0,
        risk_score=8.0,
        sentiment_score=8.0,
        completeness_info={"missing_critical_fields": []},
        conflict_info={"is_critical_tier1_conflict": False},
        management_info={"has_critical_governance_flag": False},
        financial_info=fin,
    )
    assert res["verdict"] == "ATTRACTIVE"
    assert res["overall_score"] >= 8.0


# Scenario 2: Expensive Valuation IPO
def test_scenario_2_expensive_ipo():
    val = ValuationEngine.evaluate_valuation(
        issue_price=950.0, post_issue_shares_cr=10.0, total_debt_cr=100.0, cash_cr=20.0,
        latest_pat_cr=50.0, latest_ebitda_cr=90.0, latest_revenue_cr=600.0, net_worth_cr=300.0,
        peer_median_pe=30.0, peer_median_ev_ebitda=18.0
    )
    assert val["pe_ratio"] > 100.0  # Excessive P/E
    assert val["pe_premium_discount_pct"] > 50.0
    assert val["valuation_score"] <= 4.0


# Scenario 3: OFS-Heavy IPO
def test_scenario_3_ofs_heavy_ipo():
    struct = StructureAnalyzer.analyze_structure({"issue_size_cr": 2000.0, "fresh_issue_cr": 200.0, "ofs_cr": 1800.0})
    assert struct["is_ofs_heavy"] is True
    assert struct["ofs_pct"] == 90.0
    assert struct["ipo_structure_score"] <= 4.0


# Scenario 4: Loss-Making Tech IPO
def test_scenario_4_loss_making_ipo():
    periods = [
        {"period_name": "FY23", "revenue": 200.0, "pat": -80.0, "cfo": -70.0},
        {"period_name": "FY24", "revenue": 350.0, "pat": -110.0, "cfo": -95.0},
        {"period_name": "FY25", "revenue": 550.0, "pat": -140.0, "cfo": -120.0},
    ]
    fin = FinancialAnalyzer.analyze_financials(periods)
    assert fin["is_loss_making"] is True
    assert fin["financial_quality_score"] <= 4.5


# Scenario 5: Financial Services (Bank/NBFC) IPO
def test_scenario_5_bank_nbfc_ipo():
    val = ValuationEngine.evaluate_valuation(
        issue_price=250.0, post_issue_shares_cr=20.0, total_debt_cr=5000.0, cash_cr=800.0,
        latest_pat_cr=400.0, latest_ebitda_cr=600.0, latest_revenue_cr=1800.0, net_worth_cr=3500.0,
        peer_median_pe=18.0, peer_median_ev_ebitda=12.0, industry_type="BANKING_NBFC"
    )
    assert val["pe_ratio"] <= 15.0  # Reasonable banking multiple


# Scenario 6: Manufacturing Asset-Heavy IPO
def test_scenario_6_manufacturing_ipo():
    periods = [
        {"period_name": "FY23", "revenue": 1200.0, "pat": 90.0, "cfo": 85.0, "net_debt": 400.0, "net_worth": 800.0},
        {"period_name": "FY24", "revenue": 1400.0, "pat": 115.0, "cfo": 110.0, "net_debt": 350.0, "net_worth": 915.0},
        {"period_name": "FY25", "revenue": 1650.0, "pat": 145.0, "cfo": 140.0, "net_debt": 250.0, "net_worth": 1060.0},
    ]
    fin = FinancialAnalyzer.analyze_financials(periods)
    assert fin["revenue_cagr"] is not None
    assert fin["earnings_quality_score"] >= 8.0  # Strong CFO conversion


# Scenario 7: Technology SaaS IPO
def test_scenario_7_tech_saas_ipo():
    biz = BusinessAnalyzer.analyze_business({
        "industry": "Enterprise Software SaaS",
        "recurring_revenue_pct": 88.0,
        "has_proprietary_tech_or_moat": True,
        "top5_customer_concentration_pct": 14.0,
    })
    assert biz["business_quality_score"] >= 8.5


# Scenario 8: Conflicting Sources IPO
def test_scenario_8_conflicting_sources():
    sources = [
        {"source_name": "NSE", "source_tier": "TIER_1", "value": "2026-09-18"},
        {"source_name": "Portal_A", "source_tier": "TIER_2", "value": "2026-09-20"},
    ]
    conf = SourceConflictEngine.compare_field_values("open_date", sources)
    assert conf["has_conflict"] is True
    assert conf["selected_value"] == "2026-09-18"  # Tier-1 precedence resolved


# Scenario 9: Missing Financial Data IPO (Safety Gate Triggered)
def test_scenario_9_missing_data_gated():
    completeness = {
        "missing_critical_fields": ["revenue_latest", "pat_latest", "cfo_latest", "min_price"],
    }
    is_gated, reasons = SafetyGateEvaluator.evaluate_gates(
        completeness_info=completeness,
        conflict_info={"is_critical_tier1_conflict": False},
        management_info={"has_critical_governance_flag": False},
        financial_info={},
    )
    assert is_gated is True
    assert "Missing critical information" in reasons[0]

    scoring = ScoringEngine()
    res = scoring.compute_decision(
        business_score=6.0, financial_score=0.0, governance_score=6.0, structure_score=6.0,
        valuation_score=0.0, growth_score=0.0, risk_score=5.0, sentiment_score=5.0,
        completeness_info=completeness, conflict_info={"is_critical_tier1_conflict": False},
        management_info={"has_critical_governance_flag": False}, financial_info={},
    )
    assert res["is_safety_gated"] is True
    assert res["verdict"] == "UNABLE_TO_ASSESS"


# Scenario 10: Changed Price Band IPO
def test_scenario_10_changed_price_band():
    old_p = {"min_price": 400.0, "max_price": 425.0}
    new_p = {"min_price": 450.0, "max_price": 475.0}
    diff = DocumentDiffEngine.compare_ipo_parameters(old_p, new_p)
    assert diff["has_changes"] is True
    assert diff["is_reanalysis_required"] is True
    assert len(diff["parameter_changes"]) == 2


# Scenario 11: Changed Opening Date IPO
def test_scenario_11_changed_opening_date():
    old_p = {"verified_open_date": "2026-09-10"}
    new_p = {"verified_open_date": "2026-09-18"}
    diff = DocumentDiffEngine.compare_ipo_parameters(old_p, new_p)
    assert diff["has_changes"] is True
    assert diff["is_reanalysis_required"] is True
