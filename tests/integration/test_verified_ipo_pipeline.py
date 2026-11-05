"""End-to-end integration tests proving that ONLY reviewer-verified facts can yield an ungated decision.

Proves:
1. Unreviewed prospectus candidates fail closed (verdict=UNABLE_TO_ASSESS, score=0.0).
2. Partially verified financials fail closed (missing critical cfo/pat/revenue blocks assessment).
3. Reviewer-verified facts with audited provenance enable deterministic scoring and an ungated decision.
"""
from datetime import date
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import IPO, Fact
from src.database.repository import IPORepository
from src.web.app import run_pipeline_for_ipo
from src.verification.reviewer import FactReviewService


@pytest.mark.asyncio
async def test_unreviewed_prospectus_candidates_fail_closed(async_session: AsyncSession):
    repo = IPORepository(async_session)
    ipo = await repo.create_or_update_ipo(
        symbol="UNVERIFIED_CO",
        company_name="Unverified Candidate Issuer Ltd",
        verified_open_date=date(2026, 11, 10),
        verified_close_date=date(2026, 11, 14),
        min_price=100.0,
        max_price=105.0,
        lot_size=100,
        issue_size_cr=500.0,
        fresh_issue_cr=300.0,
    )
    # Add candidate facts as UNVERIFIED JSON
    await repo.add_fact(
        ipo_id=ipo.id,
        field_name="revenue_from_operations",
        value_text='{"period": {"label": "FY2025"}, "statement_basis": "CONSOLIDATED", "normalized_value_inr_crore": "800.0"}',
        value_numeric=None,
        value_type="JSON",
        source_name="PROSPECTUS_TABLE_CANDIDATE",
        source_url="https://www.sebi.gov.in/unverified.pdf",
    )
    await async_session.commit()

    result = await run_pipeline_for_ipo(ipo, async_session)
    assert result["assessment_status"] == "UNABLE_TO_ASSESS"
    assert result["score_data"]["is_safety_gated"] is True
    assert result["score_data"]["overall_score"] == 0.0
    assert result["score_data"]["verdict"] == "UNABLE_TO_ASSESS"
    assert result["source_verification_status"] == "NOT_VERIFIED"


@pytest.mark.asyncio
async def test_partially_verified_financials_fail_closed(async_session: AsyncSession):
    repo = IPORepository(async_session)
    ipo = await repo.create_or_update_ipo(
        symbol="PARTIAL_CO",
        company_name="Partially Verified Issuer Ltd",
        verified_open_date=date(2026, 11, 10),
        verified_close_date=date(2026, 11, 14),
        min_price=100.0,
        max_price=105.0,
        lot_size=100,
        issue_size_cr=500.0,
        fresh_issue_cr=300.0,
    )
    # Verify revenue and PAT, but leave CFO unverified
    rev_fact = await repo.add_fact(
        ipo_id=ipo.id,
        field_name="revenue_from_operations",
        value_text='{"period": {"label": "FY2025"}, "statement_basis": "CONSOLIDATED", "normalized_value_inr_crore": "800.0"}',
        value_numeric=None,
        value_type="JSON",
        source_name="PROSPECTUS_TABLE_CANDIDATE",
        source_url="https://www.sebi.gov.in/partial.pdf",
        page_number=10,
    )
    pat_fact = await repo.add_fact(
        ipo_id=ipo.id,
        field_name="profit_after_tax",
        value_text='{"period": {"label": "FY2025"}, "statement_basis": "CONSOLIDATED", "normalized_value_inr_crore": "90.0"}',
        value_numeric=None,
        value_type="JSON",
        source_name="PROSPECTUS_TABLE_CANDIDATE",
        source_url="https://www.sebi.gov.in/partial.pdf",
        page_number=10,
    )
    await async_session.commit()

    # Reviewer promotes revenue and PAT
    await FactReviewService.review_and_promote_fact(
        async_session,
        fact_id=rev_fact.id,
        reviewer_id="analyst_vinay",
        decision="VERIFIED",
        target_field_name="revenue_latest",
        notes="Verified against RHP Page 10",
    )
    await FactReviewService.review_and_promote_fact(
        async_session,
        fact_id=pat_fact.id,
        reviewer_id="analyst_vinay",
        decision="VERIFIED",
        target_field_name="pat_latest",
        notes="Verified against RHP Page 10",
    )
    await async_session.commit()

    # Still missing cfo_latest
    result = await run_pipeline_for_ipo(ipo, async_session)
    assert result["assessment_status"] == "UNABLE_TO_ASSESS"
    assert result["score_data"]["is_safety_gated"] is True
    assert result["score_data"]["overall_score"] == 0.0
    gate_reasons = result["score_data"]["safety_gate_reasons"]
    assert any("cfo_latest" in r for r in gate_reasons)


@pytest.mark.asyncio
async def test_core_verified_ipo_stays_gated_without_other_live_assessment_evidence(async_session: AsyncSession):
    repo = IPORepository(async_session)
    ipo = await repo.create_or_update_ipo(
        symbol="VERIFIED_WINNER",
        company_name="Verified High Growth Tech Ltd",
        verified_open_date=date(2026, 11, 10),
        verified_close_date=date(2026, 11, 14),
        min_price=450.0,
        max_price=475.0,
        lot_size=31,
        issue_size_cr=1200.0,
        fresh_issue_cr=800.0,
        ofs_cr=400.0,
    )

    # Ingest candidate facts for all critical fields
    facts_to_create = [
        ("min_price", 450.0, "NUMBER"),
        ("max_price", 475.0, "NUMBER"),
        ("lot_size", 31.0, "NUMBER"),
        ("issue_size_cr", 1200.0, "NUMBER"),
        ("fresh_issue_cr", 800.0, "NUMBER"),
        ("revenue_latest", 1040.0, "NUMBER"),
        ("pat_latest", 125.0, "NUMBER"),
        ("cfo_latest", 115.0, "NUMBER"),
    ]
    for field, val, vtype in facts_to_create:
        c_fact = await repo.add_fact(
            ipo_id=ipo.id,
            field_name=field,
            value_text=str(val),
            value_numeric=val,
            value_type=vtype,
            source_name="PROSPECTUS_TABLE_CANDIDATE",
            source_url="https://www.sebi.gov.in/winner.pdf",
            page_number=42,
        )
        await FactReviewService.review_and_promote_fact(
            async_session,
            fact_id=c_fact.id,
            reviewer_id="lead_analyst_vinay",
            decision="VERIFIED",
            target_field_name=field,
            verified_numeric_value=val,
            notes=f"Independently verified {field} from official RHP page 42.",
        )
    await async_session.commit()

    # Core terms and financials are verified, but the live scorer does not yet
    # have verified governance, peer valuation, proceeds, risk, or market inputs.
    result = await run_pipeline_for_ipo(ipo, async_session)
    assert result["assessment_status"] == "UNABLE_TO_ASSESS"
    assert result["score_data"]["is_safety_gated"] is True
    assert result["score_data"]["verdict"] == "UNABLE_TO_ASSESS"
    assert "business-model" in result["full_report"]
    assert "no Apply/Avoid suggestion was generated" in result["full_report"]


@pytest.mark.asyncio
async def test_fully_verified_ipo_with_all_pillars_produces_ungated_score_and_recommendation(async_session: AsyncSession):
    repo = IPORepository(async_session)
    ipo = await repo.create_or_update_ipo(
        symbol="FULL_VERIFIED_HERO",
        company_name="Fully Verified Hero Tech Ltd",
        verified_open_date=date(2026, 11, 10),
        verified_close_date=date(2026, 11, 14),
        min_price=450.0,
        max_price=475.0,
        lot_size=31,
        issue_size_cr=1200.0,
        fresh_issue_cr=800.0,
        ofs_cr=400.0,
    )

    facts_to_create = [
        ("min_price", 450.0, "NUMBER", "450.0"),
        ("max_price", 475.0, "NUMBER", "475.0"),
        ("lot_size", 31.0, "NUMBER", "31"),
        ("issue_size_cr", 1200.0, "NUMBER", "1200.0"),
        ("fresh_issue_cr", 800.0, "NUMBER", "800.0"),
        ("ofs_cr", 400.0, "NUMBER", "400.0"),
        ("revenue_latest", 1040.0, "NUMBER", "1040.0"),
        ("pat_latest", 125.0, "NUMBER", "125.0"),
        ("cfo_latest", 115.0, "NUMBER", "115.0"),
        # Business
        ("top5_customer_concentration_pct", 24.5, "NUMBER", "24.5"),
        ("recurring_revenue_pct", 72.0, "NUMBER", "72.0"),
        ("has_proprietary_tech_or_moat", 1.0, "BOOLEAN", "true"),
        ("is_cyclical", 0.0, "BOOLEAN", "false"),
        # Governance
        ("promoter_pre_holding_pct", 82.0, "NUMBER", "82.0"),
        ("promoter_post_holding_pct", 65.0, "NUMBER", "65.0"),
        ("promoter_pledge_pct", 0.0, "NUMBER", "0.0"),
        ("has_auditor_qualifications", 0.0, "BOOLEAN", "false"),
        ("frequent_auditor_changes", 0.0, "BOOLEAN", "false"),
        ("rpt_revenue_pct", 3.2, "NUMBER", "3.2"),
        ("has_promoter_litigation", 0.0, "BOOLEAN", "false"),
        # Structure
        ("capex_growth_cr", 500.0, "NUMBER", "500.0"),
        ("debt_repayment_cr", 200.0, "NUMBER", "200.0"),
        # Valuation / Peers
        ("peer_median_pe", 38.5, "NUMBER", "38.5"),
        ("peer_median_ev_ebitda", 22.0, "NUMBER", "22.0"),
        ("cash_cr", 120.0, "NUMBER", "120.0"),
        # Risk register
        ("risk_register", None, "JSON", '[{"risk_title": "Customer Concentration", "severity": "MEDIUM", "probability": "MEDIUM", "impact": "MEDIUM", "evidence_citation": "Page 40"}]'),
        # Market Regime
        ("nifty_50dma_status", None, "STRING", "ABOVE"),
        ("midcap_sentiment", None, "STRING", "BULLISH"),
        ("recent_ipos_avg_listing_gain_pct", 25.0, "NUMBER", "25.0"),
        ("india_vix", 13.5, "NUMBER", "13.5"),
    ]

    for field, val, vtype, text_val in facts_to_create:
        c_fact = await repo.add_fact(
            ipo_id=ipo.id,
            field_name=field,
            value_text=text_val,
            value_numeric=val,
            value_type=vtype,
            source_name="PROSPECTUS_OFFICIAL",
            source_url="https://www.sebi.gov.in/hero.pdf",
            page_number=15,
        )
        await FactReviewService.review_and_promote_fact(
            async_session,
            fact_id=c_fact.id,
            reviewer_id="lead_analyst_vinay",
            decision="VERIFIED",
            target_field_name=field,
            verified_numeric_value=val,
            verified_value_text=text_val,
            verified_value_type=vtype,
            notes=f"Independently verified {field} from official prospectus.",
        )
    await async_session.commit()

    result = await run_pipeline_for_ipo(ipo, async_session)
    assert result["assessment_status"] == "ASSESSED"
    assert result["source_verification_status"] == "VERIFIED"
    assert result["score_data"]["is_safety_gated"] is False
    assert result["score_data"]["overall_score"] > 0.0
    assert result["score_data"]["verdict"] in ("ATTRACTIVE", "NEUTRAL", "AVOID")
    pillars = result["score_data"]["pillar_scores"]
    assert len(pillars) == 8
    for p_name, p_score in pillars.items():
        assert p_score is not None
        assert 0.0 <= p_score <= 10.0
