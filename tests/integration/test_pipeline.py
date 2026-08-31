"""
Integration tests for the complete IPO Intelligence, Evidence, and Reporting Pipeline.
"""

import pytest
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.repository import IPORepository
from src.documents.manager import DocumentManager
from src.documents.diff import DocumentDiffEngine
from src.reporting.generator import ReportGenerator
from src.feedback.engine import FeedbackEngine
from src.web.app import run_pipeline_for_ipo


@pytest.mark.asyncio
async def test_full_pipeline_flow(async_session: AsyncSession):
    repo = IPORepository(async_session)

    # 1. Create IPO entity
    ipo = await repo.create_or_update_ipo(
        symbol="ACME_CORP",
        company_name="Acme Corporation Ltd",
        industry="Precision Engineering",
        issue_type="MAINBOARD",
        verified_open_date=date(2026, 9, 18),
        verified_close_date=date(2026, 9, 22),
        min_price=450.0,
        max_price=475.0,
        lot_size=31,
        issue_size_cr=1200.0,
        fresh_issue_cr=800.0,
        ofs_cr=400.0,
    )
    assert ipo.id is not None
    assert ipo.status == "IPO_DISCOVERED"

    # 2. Ingest Document and Compute SHA256
    doc_mgr = DocumentManager(async_session)
    doc_version = await doc_mgr.ingest_document(
        ipo_id=ipo.id,
        document_type="RHP",
        document_title="Red Herring Prospectus",
        source_url="https://example.com/rhp.pdf",
        local_content=b"%PDF-1.4 Mock Prospectus Data for Acme Corp",
    )
    assert doc_version.document_hash is not None

    # 3. Document Diff Test (e.g. price band update)
    old_params = {"min_price": 430.0, "max_price": 450.0, "issue_size_cr": 1100.0}
    new_params = {"min_price": 450.0, "max_price": 475.0, "issue_size_cr": 1200.0}
    diff = DocumentDiffEngine.compare_ipo_parameters(old_params, new_params)
    assert diff["has_changes"] is True
    assert diff["is_reanalysis_required"] is True

    # 4. Run Analysis Pipeline
    pipeline_result = await run_pipeline_for_ipo(ipo, async_session)
    assert "score_data" in pipeline_result
    assert pipeline_result["score_data"]["overall_score"] > 0
    assert pipeline_result["score_data"]["verdict"] in ("ATTRACTIVE", "NEUTRAL", "AVOID")

    # 5. Verify Multi-Format Reports
    assert len(pipeline_result["executive_summary"]) > 50
    assert len(pipeline_result["full_report"]) > 100
    assert len(pipeline_result["copy_mode"]) > 50

    # 6. Post-Listing Feedback Loop Test
    feedback_engine = FeedbackEngine(async_session)
    outcome = await feedback_engine.record_actual_listing(
        ipo_id=ipo.id,
        actual_listing_price=570.0,  # ₹570 vs ₹475 issue price (+20.0%)
        predicted_listing_gain_pct=18.0,
        verdict=pipeline_result["score_data"]["verdict"],
    )
    assert outcome.listing_gain_pct == 20.0
    assert outcome.was_recommendation_profitable is True
