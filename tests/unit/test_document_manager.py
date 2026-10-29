from io import BytesIO

import pytest
from pypdf import PdfWriter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.common.config import settings
from src.database.models import Base, IPO, IPODocument, DocumentVersion
from src.documents.manager import DocumentManager


def _blank_pdf(width: float) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=72)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.asyncio
async def test_document_ingestion_is_idempotent_and_keeps_revisions_immutable(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(settings, "document_storage_dir", tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            ipo = IPO(symbol="TEST_IPO", company_name="Test Issuer")
            session.add(ipo)
            await session.flush()

            manager = DocumentManager(session)
            original = _blank_pdf(72)
            first = await manager.ingest_document(
                ipo_id=ipo.id,
                document_type="RHP",
                document_title="Red Herring Prospectus",
                source_url="https://www.nseindia.com/test-rhp.pdf",
                local_content=original,
            )
            duplicate = await manager.ingest_document(
                ipo_id=ipo.id,
                document_type="RHP",
                document_title="Red Herring Prospectus",
                source_url="https://www.nseindia.com/test-rhp.pdf",
                local_content=original,
            )
            revised = await manager.ingest_document(
                ipo_id=ipo.id,
                document_type="RHP",
                document_title="Red Herring Prospectus",
                source_url="https://www.nseindia.com/test-rhp.pdf",
                local_content=_blank_pdf(73),
            )
            assert first.id == duplicate.id
            assert revised.id != first.id
            assert first.document_hash != revised.document_hash
            assert first.file_path != revised.file_path

            documents = (await session.execute(select(IPODocument))).scalars().all()
            versions = (await session.execute(select(DocumentVersion).order_by(DocumentVersion.id))).scalars().all()
            assert len(documents) == 1
            assert len(versions) == 2
            assert [item.version_label for item in versions] == ["v1", "v2"]
            assert all(__import__("pathlib").Path(item.file_path).exists() for item in versions)
    finally:
        await engine.dispose()



def test_document_url_validation_rejects_local_and_insecure_targets():
    from src.documents.manager import _validate_public_https_url

    assert _validate_public_https_url("https://www.nseindia.com/example.pdf").hostname == "www.nseindia.com"
    with pytest.raises(ValueError, match="HTTPS"):
        _validate_public_https_url("http://www.nseindia.com/example.pdf")
    with pytest.raises(ValueError, match="Private/local"):
        _validate_public_https_url("https://localhost/example.pdf")
    with pytest.raises(ValueError, match="Non-public IP"):
        _validate_public_https_url("https://127.0.0.1/example.pdf")
    with pytest.raises(ValueError, match="credentials"):
        _validate_public_https_url("https://user:pass@www.nseindia.com/example.pdf")



def test_candidate_report_is_explicitly_unverified_and_contains_page_citation(tmp_path, monkeypatch):
    from src.documents.manager import _write_candidate_report

    monkeypatch.chdir(tmp_path)
    _write_candidate_report(
        ipo_id=7,
        document_type="RHP",
        document_title="Example RHP",
        source_url="https://www.nseindia.com/example.pdf",
        document_hash="c" * 64,
        extraction={
            "page_count": 10,
            "text_pages_extracted": 8,
            "evidence_count": 1,
            "evidence": [{
                "field_name": "revenue_from_operations",
                "page_number": 4,
                "evidence_text": "Revenue from operations 100",
            }],
        },
    )
    report_path = tmp_path / "reports" / "prospectus" / ("7_RHP_" + "c" * 12 + ".md")
    content = report_path.read_text(encoding="utf-8")
    assert "UNVERIFIED" in content
    assert "revenue_from_operations — page 4" in content
    assert "not an investment recommendation" in content



@pytest.mark.asyncio
async def test_prospectus_notification_is_idempotent_by_document_hash(tmp_path, monkeypatch):
    from src.documents.manager import _notify_new_document
    from src.state.store import StateStore
    import src.documents.manager as manager_module

    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(settings, "enable_whatsapp", True)
    monkeypatch.setattr(settings, "enable_email", False)
    report_dir = tmp_path / "reports" / "prospectus"
    report_dir.mkdir(parents=True)
    report_pdf = report_dir / "evidence.pdf"
    report_pdf.write_bytes(b"%PDF-1.4 test")
    calls = []

    async def fake_send(self, recipient, subject, content, metadata=None):
        calls.append(metadata)
        return {"success": True, "accepted": True, "delivered": False, "message_id": "wamid.test"}

    monkeypatch.setattr(manager_module.WhatsAppProvider, "send_notification", fake_send)
    store = StateStore(root=str(tmp_path / "state"))
    kwargs = {
        "store": store,
        "symbol": "EXAMPLE",
        "company_name": "Example Limited",
        "document_type": "RHP",
        "document_title": "Example RHP",
        "source_url": "https://www.nseindia.com/example-rhp.pdf",
        "document_hash": "a" * 64,
        "version_label": "v1",
        "page_count": 100,
        "evidence_count": 3,
        "report_pdf": report_pdf,
    }
    await _notify_new_document(**kwargs)
    await _notify_new_document(**kwargs)
    assert len(calls) == 1



def test_public_prospectus_source_urls_redact_token_like_query_parameters():
    from src.documents.manager import _safe_public_source_url

    public_url = _safe_public_source_url(
        "https://nsearchives.nseindia.com/rhp.pdf?token=secret-value&download=1&signature=abc"
    )
    assert "secret-value" not in public_url
    assert "signature=abc" not in public_url
    assert "download=1" in public_url
