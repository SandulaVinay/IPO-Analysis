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
async def test_fully_reviewer_verified_ipo_yields_ungated_assessment(async_session: AsyncSession):
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

    # Run analysis pipeline
    result = await run_pipeline_for_ipo(ipo, async_session)
    assert result["assessment_status"] == "ASSESSED"
    assert result["score_data"]["is_safety_gated"] is False
    assert result["score_data"]["overall_score"] > 5.0
    assert result["score_data"]["verdict"] in {"ATTRACTIVE", "NEUTRAL", "AVOID"}
    assert result["confidence_level"] == "HIGH"
    assert result["source_verification_status"] == "VERIFIED"
    assert len(result["full_report"]) > 100
