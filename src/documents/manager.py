"""
Document manager for real IPO filings with content validation, SHA-256 hashing, and version tracking.

A failed download is never replaced by a fabricated placeholder. The caller must supply a
real PDF from a verified source; otherwise ingestion fails and the analysis remains gated.
"""
import hashlib
import ipaddress
import os
from pathlib import Path
from datetime import datetime, date, timezone
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.config import settings
from src.common.logging import logger
from src.database.models import IPODocument, DocumentVersion, Fact
from src.documents.extractor import extract_pdf_candidate_evidence
from src.reporting.pdf import markdown_to_pdf
from src.ingestion.client import http_client

MAX_DOCUMENT_BYTES = 50 * 1024 * 1024


def _safe_component(value: str, fallback: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in str(value or ""))
    cleaned = cleaned.strip("._-")
    return cleaned[:100] or fallback


def _validate_public_https_url(value: str):
    parsed = urlparse(value or "")
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise ValueError("IPO filing URL must be HTTPS and must not contain embedded credentials.")
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Private/local hosts are not allowed for remote IPO documents.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Non-public IP addresses are not allowed for remote IPO documents.")
    return parsed


def _validate_pdf_content(content: bytes) -> None:
    if not content:
        raise ValueError("Downloaded document is empty.")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"Document exceeds the {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB size limit.")
    # PDFs are not required to begin at byte 0 by every producer, but a real PDF
    # header should be present near the beginning. HTML challenge pages are rejected.
    if b"%PDF-" not in content[:1024]:
        raise ValueError("Downloaded content is not a recognizable PDF; refusing to register it.")


def _write_candidate_report(
    *,
    ipo_id: int,
    document_type: str,
    document_title: str,
    source_url: str,
    document_hash: str,
    extraction: dict,
) -> None:
    """Write a review artifact; it contains candidate evidence, never a recommendation."""
    report_dir = Path("reports/prospectus")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{ipo_id}_{_safe_component(document_type, 'DOC')}_{document_hash[:12]}.md"
    lines = [
        "# Prospectus evidence candidates",
        "",
        "**Status: UNVERIFIED — not an investment recommendation.**",
        "",
        f"- IPO database ID: {ipo_id}",
        f"- Document type: {document_type}",
        f"- Document title: {document_title}",
        f"- Source URL: {source_url}",
        f"- SHA-256: {document_hash}",
        f"- Pages: {extraction['page_count']}",
        f"- Text pages extracted: {extraction['text_pages_extracted']}",
        f"- Candidate passages: {extraction['evidence_count']}",
        "",
        "## Candidate passages",
        "",
    ]
    if not extraction["evidence"]:
        lines.append("No supported text candidates were found. Scanned/image-only PDFs may require OCR.")
    for item in extraction["evidence"]:
        lines.extend([
            f"### {item['field_name']} — page {item['page_number']}",
            "",
            f"> {item['evidence_text']}",
            "",
            "Extraction status: CANDIDATE_UNVERIFIED; no numeric value has been assigned.",
            "",
        ])
    report_content = "\n".join(lines) + "\n"
    report_path.write_text(report_content, encoding="utf-8")
    markdown_to_pdf(report_content, report_path.with_suffix(".pdf"), title="Prospectus Evidence Candidates")


class DocumentManager:
    """Manages downloading, cryptographic hashing, and version tracking of IPO filings."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.storage_dir = Path(settings.document_storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def calculate_sha256(file_path: str) -> str:
        """Compute SHA-256 hex digest of a document."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as file_obj:
            for byte_block in iter(lambda: file_obj.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    async def has_source_url(self, ipo_id: int, source_url: str) -> bool:
        result = await self.session.execute(
            select(DocumentVersion.id).join(IPODocument).where(
                IPODocument.ipo_id == ipo_id,
                DocumentVersion.source_url == source_url,
            ).limit(1)
        )
        return result.first() is not None

    async def ingest_document(
        self,
        ipo_id: int,
        document_type: str,
        document_title: str,
        source_url: str,
        version_label: str = "v1",
        publication_date: Optional[date] = None,
        local_content: Optional[bytes] = None,
    ) -> DocumentVersion:
        """Download/store a real PDF and register its hash and version only after validation."""
        safe_type = _safe_component(document_type, "DOCUMENT")
        safe_version = _safe_component(version_label, "v1")
        safe_title = _safe_component(document_title, "filing")
        if local_content is not None:
            content = local_content
        else:
            _validate_public_https_url(source_url)
            try:
                response = await http_client.get(source_url, headers={"Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.1"})
                _validate_public_https_url(str(response.url))
                content = response.content
            except Exception as exc:
                logger.warning("IPO document download failed (%s); no placeholder was created.", type(exc).__name__)
                raise RuntimeError("IPO document download failed; document was not registered.") from exc

        _validate_pdf_content(content)
        doc_hash = hashlib.sha256(content).hexdigest()

        # Content-hash idempotency prevents the scheduled workflow from registering
        # a new document and repeating evidence extraction for the same filing.
        existing_result = await self.session.execute(
            select(DocumentVersion)
            .join(IPODocument, DocumentVersion.document_id == IPODocument.id)
            .where(
                IPODocument.ipo_id == ipo_id,
                IPODocument.document_type == safe_type,
                DocumentVersion.document_hash == doc_hash,
            )
            .order_by(DocumentVersion.id.desc())
        )
        existing_version = existing_result.scalars().first()
        if existing_version is not None:
            return existing_version

        # Reuse the logical document record for revised filings while keeping every
        # content version in a distinct immutable file.
        document_result = await self.session.execute(
            select(IPODocument)
            .where(
                IPODocument.ipo_id == ipo_id,
                IPODocument.document_type == safe_type,
                IPODocument.document_title == document_title[:255],
            )
            .order_by(IPODocument.id.desc())
        )
        doc = document_result.scalars().first()
        if doc is not None:
            versions_result = await self.session.execute(
                select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
            )
            existing_versions = list(versions_result.scalars().all())
            used_labels = {item.version_label for item in existing_versions}
            if safe_version in used_labels:
                index = 1
                while f"v{index}" in used_labels:
                    index += 1
                safe_version = f"v{index}"
        filename = f"{int(ipo_id)}_{safe_type}_{safe_title}_{doc_hash[:12]}.pdf"
        file_path = (self.storage_dir / filename).resolve()
        if file_path.parent != self.storage_dir.resolve():
            raise ValueError("Invalid document path.")

        # Parse before persistence so a corrupt/non-PDF document is never registered
        # as a usable prospectus. Evidence is candidate-only and remains UNVERIFIED.
        extraction = extract_pdf_candidate_evidence(content, source_url=source_url)
        temporary_path = file_path.with_suffix(file_path.suffix + ".tmp")
        try:
            with open(temporary_path, "wb") as file_obj:
                file_obj.write(content)
                file_obj.flush()
                os.fsync(file_obj.fileno())
            os.replace(temporary_path, file_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

        if doc is None:
            doc = IPODocument(
                ipo_id=ipo_id,
                document_type=safe_type,
                document_title=document_title[:255],
                latest_version=safe_version,
            )
            self.session.add(doc)
            await self.session.flush()
        else:
            doc.latest_version = safe_version

        version = DocumentVersion(
            document_id=doc.id,
            version_label=safe_version,
            source_url=source_url,
            file_path=str(file_path),
            document_hash=doc_hash,
            publication_date=publication_date or datetime.now(timezone.utc).date(),
            page_count=extraction["page_count"],
            processing_status="PARSED" if extraction["text_pages_extracted"] else "NO_TEXT",
        )
        self.session.add(version)
        await self.session.flush()

        for candidate in extraction["evidence"]:
            self.session.add(Fact(
                ipo_id=ipo_id,
                field_name=candidate["field_name"],
                value_text=candidate["evidence_text"],
                value_numeric=None,
                value_type="STRING",
                source_name="PROSPECTUS_TEXT_EXTRACTION",
                source_url=source_url,
                source_tier="TIER_3",
                document_id=doc.id,
                document_version=safe_version,
                page_number=candidate["page_number"],
                confidence="LOW",
                verification_status="UNVERIFIED",
            ))
        await self.session.flush()
        _write_candidate_report(
            ipo_id=ipo_id,
            document_type=safe_type,
            document_title=document_title,
            source_url=source_url,
            document_hash=doc_hash,
            extraction=extraction,
        )
        logger.info(
            "Registered validated %s PDF version %s (SHA-256 %s...); pages=%s candidates=%s. Candidate facts remain UNVERIFIED.",
            safe_type, safe_version, doc_hash[:16], extraction["page_count"], extraction["evidence_count"],
        )
        return version
