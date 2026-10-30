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
import pdfplumber

MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 1500
MAX_PAGE_TEXT = 200_000

# Patterns are intentionally broad for recall. A matching snippet is evidence to
# review, not a parsed/verified financial value.
EVIDENCE_PATTERNS = {
    "revenue_from_operations": (
        r"revenue\s+from\s+operations",
        r"revenue\s+from\s+sale[s]?\s+of\s+products",
        r"total\s+income\s+from\s+operations",
    ),
    "profit_after_tax": (
        r"profit\s*/?\s*\(?loss\)?\s+for\s+the\s+year",
        r"profit\s+after\s+tax",
        r"profit\s*/?\s*\(?loss\)?\s+for\s+the\s+period",
    ),
    "operating_cash_flow": (
        r"net\s+cash\s+(?:generated\s+from|from)\s+operating\s+activities",
        r"cash\s+flow[s]?\s+from\s+operating\s+activities",
    ),
    "earnings_per_share": (
        r"earnings\s+per\s+share",
        r"basic\s+and\s+diluted\s+earnings\s+per\s+share",
    ),
    "borrowings": (
        r"total\s+borrowings",
        r"borrowings\s+including\s+current\s+maturities",
        r"financial\s+liabilities",
    ),
    "net_worth": (
        r"net\s+worth",
        r"total\s+shareholders'?\s+equity",
    ),
    "issue_structure": (
        r"fresh\s+issue",
        r"offer\s+for\s+sale",
        r"objects\s+of\s+the\s+offer",
        r"objects\s+of\s+the\s+issue",
    ),
    "risk_factors": (
        r"risk\s+factors",
        r"litigation",
        r"contingent\s+liabilit(?:y|ies)",
    ),
}


def _normalized_lines(text: str) -> List[str]:
    lines = []
    for raw in (text or "").replace("\x00", " ").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
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


def extract_candidate_evidence_from_tables(
    tables_by_page: List[List[List[List[Optional[str]]]]],
    *,
    source_url: str,
    document_hash: str,
    extracted_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Capture financial table rows as review candidates without assigning values to periods."""
    timestamp = extracted_at or datetime.now(timezone.utc).isoformat()
    output: List[Dict[str, Any]] = []
    seen = set()
    compiled = {
        field: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
        for field, patterns in EVIDENCE_PATTERNS.items()
    }
    for page_number, tables in enumerate(tables_by_page, start=1):
        for table_index, table in enumerate(tables or [], start=1):
            rows = [
                [re.sub(r"\s+", " ", str(cell or "")).strip() for cell in (row or [])]
                for row in (table or [])
            ]
            rows = [row for row in rows if any(row)]
            if not rows:
                continue
            header_rows = rows[:1]
            if len(rows) > 1:
                second_row_text = " | ".join(rows[1])
                second_row_is_data = any(
                    pattern.search(second_row_text)
                    for patterns in compiled.values()
                    for pattern in patterns
                )
                if not second_row_is_data:
                    header_rows = rows[:2]
            header_context = " / ".join(" | ".join(row) for row in header_rows)[:400]
            for row_index, row in enumerate(rows):
                row_text = " | ".join(row).strip()
                if len(row) < 2 or not row_text:
                    continue
                matched_fields = [
                    field for field, patterns in compiled.items()
                    if any(pattern.search(row_text) for pattern in patterns)
                ]
                if not matched_fields:
                    continue
                snippet = f"TABLE {table_index}; HEADER: {header_context}; ROW: {row_text}"[:1000]
                for field in matched_fields:
                    key = (field, page_number, snippet.casefold())
                    if key in seen:
                        continue
                    seen.add(key)
                    output.append({
                        "field_name": field,
                        "source_url": source_url,
                        "document_hash": document_hash,
                        "page_number": page_number,
                        "evidence_text": snippet,
                        "extraction_status": "CANDIDATE_UNVERIFIED",
                        "extraction_method": "TABLE_ROW_CANDIDATE",
                        "table_row_index": row_index + 1,
                        "value": None,
                        "extracted_at": timestamp,
                    })
    return output


def _extract_table_rows_from_word_positions(page) -> List[List[str]]:
    """Recover likely table rows from PDF word geometry when ruled-table detection fails.

    Financial labels and values are kept on the same visual line. Large horizontal
    gaps form cell boundaries; ordinary spaces within a label do not. This fallback
    creates review candidates only and never assigns values to periods.
    """
    try:
        words = page.extract_words(x_tolerance=2, y_tolerance=3, use_text_flow=False)
    except Exception:
        return []
    if not words:
        return []

    line_groups: List[Dict[str, Any]] = []
    for word in sorted(words, key=lambda item: (float(item.get("top", 0)), float(item.get("x0", 0)))):
        top = float(word.get("top", 0))
        if line_groups and abs(top - line_groups[-1]["top"]) <= 2.5:
            line_groups[-1]["words"].append(word)
            line_groups[-1]["top"] = (
                line_groups[-1]["top"] * (len(line_groups[-1]["words"]) - 1) + top
            ) / len(line_groups[-1]["words"])
        else:
            line_groups.append({"top": top, "words": [word]})

    rows: List[List[str]] = []
    for line in line_groups:
        ordered = sorted(line["words"], key=lambda item: float(item.get("x0", 0)))
        cells: List[str] = []
        current: List[str] = []
        previous_x1: Optional[float] = None
        for word in ordered:
            x0 = float(word.get("x0", 0))
            if current and previous_x1 is not None and x0 - previous_x1 >= 8:
                cells.append(" ".join(current))
                current = []
            current.append(str(word.get("text", "")))
            previous_x1 = float(word.get("x1", x0))
        if current:
            cells.append(" ".join(current))
        if len(cells) >= 2 and any(cell.strip() for cell in cells):
            rows.append(cells)
    return [rows] if rows else []


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
    # Table extraction is best-effort and still candidate-only. Restrict it to pages whose
    # text contains a relevant label to avoid expensive layout analysis across every page.
    try:
        tables_by_page = [[] for _ in page_texts]
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page_index, page in enumerate(pdf.pages):
                page_text = page_texts[page_index] if page_index < len(page_texts) else ""
                if not page_text or not any(
                    pattern.search(page_text)
                    for patterns in (
                        re.compile(pattern, re.IGNORECASE)
                        for field_patterns in EVIDENCE_PATTERNS.values()
                        for pattern in field_patterns
                    )
                ):
                    continue
                try:
                    detected_tables = page.extract_tables() or []
                except Exception:
                    detected_tables = []
                # PDF table detection differs across pdfplumber/pdfminer versions and
                # prospectuses frequently use whitespace-aligned columns without ruled
                # borders. Recover row candidates from word geometry when no table was
                # detected; only candidate evidence is emitted, never verified facts.
                if not detected_tables:
                    detected_tables = _extract_table_rows_from_word_positions(page)
                tables_by_page[page_index] = detected_tables
        table_evidence = extract_candidate_evidence_from_tables(
            tables_by_page,
            source_url=source_url,
            document_hash=document_hash,
        )
        existing_keys = {
            (item["field_name"], item["page_number"], item["evidence_text"].casefold())
            for item in evidence
        }
        for item in table_evidence:
            key = (item["field_name"], item["page_number"], item["evidence_text"].casefold())
            if key not in existing_keys:
                evidence.append(item)
                existing_keys.add(key)
    except Exception:
        # Linear page text remains available if table-layout extraction fails.
        pass
    return {
        "document_hash": document_hash,
        "page_count": len(reader.pages),
        "text_pages_extracted": sum(bool(text.strip()) for text in page_texts),
        "evidence_count": len(evidence),
        "evidence": evidence,
        "status": "CANDIDATES_FOUND" if evidence else "NO_CANDIDATES_FOUND",
        "verification_status": "UNVERIFIED",
    }
