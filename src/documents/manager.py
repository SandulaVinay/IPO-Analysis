"""
Document manager for real IPO filings with content validation, SHA-256 hashing, and version tracking.

A failed download is never replaced by a fabricated placeholder. The caller must supply a
real PDF from a verified source; otherwise ingestion fails and the analysis remains gated.
"""
import hashlib
import os
from pathlib import Path
from datetime import datetime, date
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from src.common.config import settings
from src.common.logging import logger
from src.database.models import IPODocument, DocumentVersion
from src.ingestion.client import http_client

MAX_DOCUMENT_BYTES = 50 * 1024 * 1024


def _safe_component(value: str, fallback: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in str(value or ""))
    cleaned = cleaned.strip("._-")
    return cleaned[:100] or fallback


def _validate_pdf_content(content: bytes) -> None:
    if not content:
        raise ValueError("Downloaded document is empty.")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"Document exceeds the {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB size limit.")
    # PDFs are not required to begin at byte 0 by every producer, but a real PDF
    # header should be present near the beginning. HTML challenge pages are rejected.
    if b"%PDF-" not in content[:1024]:
        raise ValueError("Downloaded content is not a recognizable PDF; refusing to register it.")


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
        filename = f"{int(ipo_id)}_{safe_type}_{safe_version}_{safe_title}.pdf"
        file_path = (self.storage_dir / filename).resolve()
        if file_path.parent != self.storage_dir.resolve():
            raise ValueError("Invalid document path.")

        if local_content is not None:
            content = local_content
        else:
            parsed = urlparse(source_url or "")
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("IPO filing URL must be a valid HTTPS URL without embedded credentials.")
            try:
                response = await http_client.get(source_url, headers={"Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.1"})
                final_url = urlparse(str(response.url))
                if final_url.scheme != "https" or not final_url.hostname or final_url.username or final_url.password:
                    raise ValueError("Filing download redirected to an invalid URL.")
                content = response.content
            except Exception as exc:
                logger.warning("IPO document download failed (%s); no placeholder was created.", type(exc).__name__)
                raise RuntimeError("IPO document download failed; document was not registered.") from exc

        _validate_pdf_content(content)
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

        doc_hash = self.calculate_sha256(str(file_path))
        doc = IPODocument(
            ipo_id=ipo_id,
            document_type=safe_type,
            document_title=document_title[:255],
            latest_version=safe_version,
        )
        self.session.add(doc)
        await self.session.flush()

        version = DocumentVersion(
            document_id=doc.id,
            version_label=safe_version,
            source_url=source_url,
            file_path=str(file_path),
            document_hash=doc_hash,
            publication_date=publication_date or datetime.utcnow().date(),
            processing_status="DOWNLOADED",
        )
        self.session.add(version)
        await self.session.flush()
        logger.info("Registered validated %s PDF version %s (SHA-256 %s...).", safe_type, safe_version, doc_hash[:16])
        return version
