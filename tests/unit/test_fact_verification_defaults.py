import pytest

from src.database.repository import IPORepository
from src.verification.engine import VerificationEngine


@pytest.mark.asyncio
async def test_new_fact_defaults_to_unverified_and_cannot_inflate_completeness(async_session):
    repo = IPORepository(async_session)
    ipo = await repo.create_or_update_ipo(
        symbol="UNVERIFIED_FACT_TEST",
        company_name="Unverified Fact Test Ltd",
        industry="Test",
    )
    fact = await repo.add_fact(
        ipo_id=ipo.id,
        field_name="revenue_latest",
        value_text="100",
        value_numeric=100.0,
        value_type="NUMBER",
        source_name="Test source",
        source_url="https://example.com/filing.pdf",
    )
    await async_session.refresh(fact)
    assert fact.verification_status == "UNVERIFIED"

    result = VerificationEngine.evaluate_ipo_completeness(
        {"verified_open_date": None, "verified_close_date": None},
        [{
            "field_name": fact.field_name,
            "verification_status": fact.verification_status,
            "source_name": fact.source_name,
            "source_url": fact.source_url,
        }],
    )
    assert "revenue_latest" in result["missing_critical_fields"]
    assert result["verified_sources_count"] == 0
