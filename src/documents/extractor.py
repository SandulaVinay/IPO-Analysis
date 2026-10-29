"""Conservative prospectus evidence extraction.

This module finds page-cited candidate passages in a real PDF. It does not guess
which number belongs to which financial year and never marks a fact VERIFIED.
Those decisions require a dedicated table/period reconciliation step.
"""
import hashlib
import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional

from pypdf import PdfReader

MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 1500
MAX_PAGE_TEXT = 200_000

# Patterns are intentionally broad for recall. A matching snippet is evidence to
# review, not a parsed/verified financial value.
EVIDENCE_PATTERNS = {
    "revenue_from_operations": (
        r"revenue\\s+from\\s+operations",
        r"revenue\\s+from\\s+sale[s]?\\s+of\\s+products",
        r"total\\s+income\\s+from\\s+operations",
    ),
    "profit_after_tax": (
        r"profit\\s*/?\\s*\\(?loss\\)?\\s+for\\s+the\\s+year",
        r"profit\\s+after\\s+tax",
        r"profit\\s*/?\\s*\\(?loss\\)?\\s+for\\s+the\\s+period",
    ),
    "operating_cash_flow": (
        r"net\\s+cash\\s+(?:generated\\s+from|from)\\s+operating\\s+activities",
        r"cash\\s+flow[s]?\\s+from\\s+operating\\s+activities",
    ),
    "earnings_per_share": (
        r"earnings\\s+per\\s+share",
        r"basic\\s+and\\s+diluted\\s+earnings\\s+per\\s+share",
    ),
    "borrowings": (
        r"total\\s+borrowings",
        r"borrowings\\s+including\\s+current\\s+maturities",
        r"financial\\s+liabilities",
    ),
    "net_worth": (
        r"net\\s+worth",
        r"total\\s+shareholders'?\\s+equity",
    ),
    "issue_structure": (
        r"fresh\\s+issue",
        r"offer\\s+for\\s+sale",
        r"objects\\s+of\\s+the\\s+offer",
        r"objects\\s+of\\s+the\\s+issue",
    ),
    "risk_factors": (
        r"risk\\s+factors",
        r"litigation",
        r"contingent\\s+liabilit(?:y|ies)",
    ),
}


def _normalized_lines(text: str) -> List[str]:
    lines = []
    for raw in (text or "").replace("\\x00", " ").splitlines():
        line = re.sub(r"\\s+", " ", raw).strip()
        if line:
            lines.append(line)
    return lines


def extract_candidate_evidence_from_pages(
    pages: List[str],
    *,
    source_url: str,
    document_hash: str,
    extracted_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return deduplicated, page-cited evidence snippets explicitly marked unverified."""
    timestamp = extracted_at or datetime.now(timezone.utc).isoformat()
    output: List[Dict[str, Any]] = []
    seen = set()
    compiled = {
        field: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
        for field, patterns in EVIDENCE_PATTERNS.items()
    }

    for page_index, text in enumerate(pages, start=1):
        if not text:
            continue
        lines = _normalized_lines(text[:MAX_PAGE_TEXT])
        for index, line in enumerate(lines):
            matched_fields = [
                field
                for field, patterns in compiled.items()
                if any(pattern.search(line) for pattern in patterns)
            ]
            if not matched_fields:
                continue
            start = max(0, index - 1)
            end = min(len(lines), index + 3)
            snippet = " | ".join(lines[start:end])[:1000]
            for field in matched_fields:
                key = (field, page_index, snippet.casefold())
                if key in seen:
                    continue
                seen.add(key)
                output.append({
                    "field_name": field,
                    "source_url": source_url,
                    "document_hash": document_hash,
                    "page_number": page_index,
                    "evidence_text": snippet,
                    "extraction_status": "CANDIDATE_UNVERIFIED",
                    "value": None,
                    "extracted_at": timestamp,
                })
    return output


def extract_pdf_candidate_evidence(pdf_bytes: bytes, *, source_url: str) -> Dict[str, Any]:
    """Extract candidate passages from a validated PDF byte stream with strict limits."""
    if not pdf_bytes:
        raise ValueError("PDF content is empty.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds the 50 MB extraction limit.")
    if b"%PDF-" not in pdf_bytes[:1024]:
        raise ValueError("Content is not a recognizable PDF.")

    document_hash = hashlib.sha256(pdf_bytes).hexdigest()
    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=True)
    except Exception as exc:
        raise ValueError("PDF could not be parsed safely.") from exc

    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported for automated extraction.")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError(f"PDF exceeds the {MAX_PDF_PAGES}-page extraction limit.")

    page_texts = []
    for page in reader.pages:
        try:
            page_texts.append((page.extract_text() or "")[:MAX_PAGE_TEXT])
        except Exception:
            # Preserve page position; a failed page is not silently skipped.
            page_texts.append("")

    evidence = extract_candidate_evidence_from_pages(
        page_texts,
        source_url=source_url,
        document_hash=document_hash,
    )
    return {
        "document_hash": document_hash,
        "page_count": len(reader.pages),
        "text_pages_extracted": sum(bool(text.strip()) for text in page_texts),
        "evidence_count": len(evidence),
        "evidence": evidence,
        "status": "CANDIDATES_FOUND" if evidence else "NO_CANDIDATES_FOUND",
        "verification_status": "UNVERIFIED",
    }
