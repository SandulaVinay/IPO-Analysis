"""Unit tests for the auditable reviewer-controlled verification workflow."""
import json
import pytest
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import IPO, Fact, AuditLog
from src.database.repository import IPORepository
from src.verification.reviewer import FactReviewService
from src.verification.engine import VerificationEngine


@pytest.mark.asyncio
async def test_reviewer_workflow_requires_reviewer_id_and_notes(async_session: AsyncSession):
    repo = IPORepository(async_session)
    ipo = await repo.create_or_update_ipo(
        symbol="TEST_REV1",
        company_name="Test Reviewer IPO 1",
    )
    fact = await repo.add_fact(
        ipo_id=ipo.id,
        field_name="revenue_from_operations",
        value_text='{"period": {"label": "FY2025"}, "statement_basis": "CONSOLIDATED", "normalized_value_inr_crore": "100.0"}',
        value_numeric=None,
        value_type="JSON",
        source_name="PROSPECTUS_TABLE_CANDIDATE",
        source_url="https://www.sebi.gov.in/test.pdf",
    )
    await async_session.commit()

    with pytest.raises(ValueError, match="reviewer_id"):
        await FactReviewService.review_and_promote_fact(
            async_session,
            fact_id=fact.id,
            reviewer_id="",
            decision="VERIFIED",
            notes="Some notes",
        )

    with pytest.raises(ValueError, match="notes"):
        await FactReviewService.review_and_promote_fact(
            async_session,
            fact_id=fact.id,
            reviewer_id="analyst_1",
            decision="VERIFIED",
            notes="",
        )


@pytest.mark.asyncio
async def test_reviewer_cannot_promote_candidate_with_missing_period_or_basis(async_session: AsyncSession):
    repo = IPORepository(async_session)
    ipo = await repo.create_or_update_ipo(
        symbol="TEST_REV2",
        company_name="Test Reviewer IPO 2",
    )
    # Missing statement basis
    fact_no_basis = await repo.add_fact(
        ipo_id=ipo.id,
        field_name="revenue_from_operations",
        value_text='{"period": {"label": "FY2025"}, "normalized_value_inr_crore": "100.0"}',
        value_numeric=None,
        value_type="JSON",
        source_name="PROSPECTUS_TABLE_CANDIDATE",
        source_url="https://www.sebi.gov.in/test.pdf",
    )
    await async_session.commit()

    with pytest.raises(ValueError, match="statement basis"):
        await FactReviewService.review_and_promote_fact(
            async_session,
            fact_id=fact_no_basis.id,
            reviewer_id="analyst_1",
            decision="VERIFIED",
            notes="Checked document",
        )


@pytest.mark.asyncio
async def test_reviewer_rejection_logs_audit_and_marks_rejected(async_session: AsyncSession):
    repo = IPORepository(async_session)
    ipo = await repo.create_or_update_ipo(
        symbol="TEST_REV3",
        company_name="Test Reviewer IPO 3",
    )
    fact = await repo.add_fact(
        ipo_id=ipo.id,
        field_name="borrowings",
        value_text="Unclear borrowing table row",
        value_numeric=None,
        value_type="STRING",
        source_name="PROSPECTUS_TEXT_EXTRACTION",
        source_url="https://www.sebi.gov.in/test.pdf",
    )
    await async_session.commit()

    result = await FactReviewService.review_and_promote_fact(
        async_session,
        fact_id=fact.id,
        reviewer_id="lead_analyst",
        decision="REJECTED",
        notes="Row is ambiguous and mixes short-term provisions with borrowings.",
    )
    assert result["decision"] == "REJECTED"
    assert fact.verification_status == "REJECTED"


@pytest.mark.asyncio
async def test_reviewer_successful_promotion_creates_verified_fact_and_audit(async_session: AsyncSession):
    repo = IPORepository(async_session)
    ipo = await repo.create_or_update_ipo(
        symbol="TEST_REV4",
        company_name="Test Reviewer IPO 4",
        verified_open_date=date(2026, 9, 18),
        verified_close_date=date(2026, 9, 22),
    )
    fact = await repo.add_fact(
        ipo_id=ipo.id,
        field_name="revenue_from_operations",
        value_text='{"field_name": "revenue_from_operations", "period": {"label": "FY2025"}, "statement_basis": "CONSOLIDATED", "normalized_value_inr_crore": "1040.50"}',
        value_numeric=None,
        value_type="JSON",
        source_name="PROSPECTUS_TABLE_CANDIDATE",
        source_url="https://www.sebi.gov.in/official-rhp.pdf",
        page_number=42,
    )
    await async_session.commit()

    result = await FactReviewService.review_and_promote_fact(
        async_session,
        fact_id=fact.id,
        reviewer_id="senior_analyst_vinay",
        decision="VERIFIED",
        target_field_name="revenue_latest",
        notes="Independently verified against RHP Page 42, consolidated statement of profit and loss in INR Lakhs.",
    )
    assert result["decision"] == "VERIFIED"
    assert result["canonical_field_name"] == "revenue_latest"
    assert result["verified_numeric_value"] == 1040.50
    assert result["audit_logged"] is True

    # Check fact was created and satisfies completeness
    fresh_ipo = await repo.get_ipo_by_id(ipo.id)
    verified_facts = [
        {"field_name": f.field_name, "verification_status": f.verification_status, "source_name": f.source_name, "source_url": f.source_url}
        for f in fresh_ipo.facts
    ]
    completeness = VerificationEngine.evaluate_ipo_completeness(
        {"verified_open_date": str(ipo.verified_open_date), "verified_close_date": str(ipo.verified_close_date)},
        verified_facts,
    )
    assert "revenue_latest" not in completeness["missing_critical_fields"]


@pytest.mark.asyncio
async def test_reviewer_can_promote_qualitative_evidence_as_text_or_boolean(async_session: AsyncSession):
    repo = IPORepository(async_session)
    ipo = await repo.create_or_update_ipo(
        symbol="TEST_REV5",
        company_name="Test Reviewer IPO 5",
    )
    text_candidate = await repo.add_fact(
        ipo_id=ipo.id,
        field_name="business_model_summary",
        value_text="Candidate description from the prospectus",
        value_numeric=None,
        value_type="STRING",
        source_name="PROSPECTUS_TEXT_EXTRACTION",
        source_url="https://www.sebi.gov.in/test.pdf",
        page_number=8,
    )
    boolean_candidate = await repo.add_fact(
        ipo_id=ipo.id,
        field_name="auditor_qualification_candidate",
        value_text="qualification identified for review",
        value_numeric=None,
        value_type="BOOLEAN",
        source_name="PROSPECTUS_TEXT_EXTRACTION",
        source_url="https://www.sebi.gov.in/test.pdf",
        page_number=92,
    )
    await async_session.commit()

    text_result = await FactReviewService.review_and_promote_fact(
        async_session,
        fact_id=text_candidate.id,
        reviewer_id="lead_analyst",
        decision="VERIFIED",
        target_field_name="business_model_summary",
        verified_value_text="Subscription-based enterprise software services.",
        verified_value_type="STRING",
        notes="Confirmed against the business overview on RHP page 8.",
    )
    boolean_result = await FactReviewService.review_and_promote_fact(
        async_session,
        fact_id=boolean_candidate.id,
        reviewer_id="lead_analyst",
        decision="VERIFIED",
        target_field_name="has_auditor_qualifications",
        verified_value_text="false",
        verified_value_type="BOOLEAN",
        notes="Reviewed the auditor report on RHP page 92; no qualification is disclosed.",
    )
    await async_session.commit()

    assert text_result["verified_value_type"] == "STRING"
    assert text_result["verified_value_text"] == "Subscription-based enterprise software services."
    assert boolean_result["verified_value_type"] == "BOOLEAN"
    assert boolean_result["verified_value_text"] == "false"
    assert boolean_result["verified_numeric_value"] == 0.0
    fresh_ipo = await repo.get_ipo_by_id(ipo.id)
    promoted = {fact.field_name: fact for fact in fresh_ipo.facts if fact.verification_status == "VERIFIED"}
    assert promoted["business_model_summary"].value_type == "STRING"
    assert promoted["has_auditor_qualifications"].value_type == "BOOLEAN"


@pytest.mark.asyncio
async def test_reviewer_cannot_reopen_rejected_or_already_promoted_candidate(async_session: AsyncSession):
    repo = IPORepository(async_session)
    ipo = await repo.create_or_update_ipo(symbol="TEST_REV6", company_name="Review State Guard Ltd")
    fact = await repo.add_fact(
        ipo_id=ipo.id,
        field_name="revenue_from_operations",
        value_text='{"period": {"label": "FY2025"}, "statement_basis": "CONSOLIDATED", "normalized_value_inr_crore": "100.0"}',
        value_numeric=None,
        value_type="JSON",
        source_name="PROSPECTUS_TABLE_CANDIDATE",
        source_url="https://www.sebi.gov.in/review-state.pdf",
    )
    await async_session.commit()

    await FactReviewService.review_and_promote_fact(
        async_session, fact_id=fact.id, reviewer_id="analyst_1", decision="VERIFIED",
        notes="Checked against the official statement and page citation.",
    )
    with pytest.raises(ValueError, match="only pending candidates"):
        await FactReviewService.review_and_promote_fact(
            async_session, fact_id=fact.id, reviewer_id="analyst_1", decision="VERIFIED",
            notes="Attempted second promotion.",
        )


@pytest.mark.asyncio
async def test_reviewer_blocks_comparable_conflicts_unless_audited_override(async_session: AsyncSession):
    repo = IPORepository(async_session)
    ipo = await repo.create_or_update_ipo(symbol="TEST_REV7", company_name="Review Conflict Guard Ltd")
    payload = lambda value: json.dumps({
        "period": {"label": "FY2025"},
        "statement_basis": "CONSOLIDATED",
        "normalized_value_inr_crore": str(value),
    })
    first = await repo.add_fact(
        ipo_id=ipo.id, field_name="revenue_from_operations", value_text=payload("100.0"),
        value_numeric=None, value_type="JSON", source_name="PROSPECTUS_CANDIDATE",
        source_url="https://www.sebi.gov.in/first.pdf",
    )
    await repo.add_fact(
        ipo_id=ipo.id, field_name="revenue_from_operations", value_text=payload("101.0"),
        value_numeric=None, value_type="JSON", source_name="EXCHANGE_CANDIDATE",
        source_url="https://www.nseindia.com/second.pdf",
    )
    await async_session.commit()

    with pytest.raises(ValueError, match="Conflicting candidates exist"):
        await FactReviewService.review_and_promote_fact(
            async_session, fact_id=first.id, reviewer_id="senior_analyst", decision="VERIFIED",
            notes="Checked original filing.",
        )

    result = await FactReviewService.review_and_promote_fact(
        async_session, fact_id=first.id, reviewer_id="senior_analyst", decision="VERIFIED",
        notes="Override after checking the issuer's signed consolidated statement; second source uses a different comparative column.",
        override_conflict=True,
    )
    assert result["decision"] == "VERIFIED"
    audits = (await async_session.execute(select(AuditLog).where(AuditLog.event_type == "FACT_VERIFICATION"))).scalars().all()
    assert len(audits) == 1
    assert audits[0].metadata_json["override_conflict"] is True
    assert audits[0].metadata_json["conflict_details"][0]["normalized_value_inr_crore"] == "101.0"
