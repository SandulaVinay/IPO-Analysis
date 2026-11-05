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

from src.documents.financial_normalization import (
    build_financial_candidate,
    detect_explicit_unit,
    identify_statement_basis,
    parse_numeric_value,
)

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
        r"net\s+cash\s+inflows?\s*/?\s*\(?outflows?\)?\s+from\s+operating\s+activities",
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


_STATEMENT_PERIOD_RE = re.compile(
    r"\bFor the\s+(?P<duration>six months|year)\s+ended\s+"
    r"(?P<month>September\s+30|March\s+31),?\s*(?P<year>20\d{2})\b",
    re.I,
)
_NUMERIC_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:\(\s*[+-]?\d[\d,]*(?:\.\d+)?\s*\)|[+-]?\d[\d,]*(?:\.\d+)?|[—–-])(?![A-Za-z0-9])"
)


def extract_candidate_evidence_from_statement_text(
    pages: List[str],
    *,
    source_url: str,
    document_hash: str,
    extracted_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Extract aligned numeric candidates from text-layer financial statement rows.

    Some regulator-hosted PDFs expose the financial rows as text but pdfplumber
    cannot recover usable table cells. This fallback maps row values to explicitly
    printed date columns, while preserving candidate-only status. It intentionally
    handles only the unambiguous FY-ending-March columns for normalization.
    """
    timestamp = extracted_at or datetime.now(timezone.utc).isoformat()
    output: List[Dict[str, Any]] = []
    seen = set()
    target_fields = {"revenue_from_operations", "profit_after_tax", "operating_cash_flow"}
    compiled = {
        field: [re.compile(pattern, re.I) for pattern in patterns]
        for field, patterns in EVIDENCE_PATTERNS.items()
        if field in target_fields
    }

    for page_number, page_text in enumerate(pages, start=1):
        if not page_text:
            continue
        unit = detect_explicit_unit(page_text)
        basis = identify_statement_basis(page_text)
        if not unit or not basis:
            continue

        periods = []
        period_seen = set()
        for match in _STATEMENT_PERIOD_RE.finditer(page_text):
            duration = re.sub(r"\s+", " ", match.group("duration")).casefold()
            month = re.sub(r"\s+", " ", match.group("month")).casefold()
            year = int(match.group("year"))
            key = (duration, month, year)
            if key in period_seen:
                continue
            period_seen.add(key)
            if duration == "year" and month == "march 31":
                periods.append({
                    "column_type": "FINANCIAL_YEAR",
                    "label": f"FY{year - 1}-{year}",
                    "start": match.start(),
                })
            else:
                # Interim columns still occupy a numeric position but are not
                # promoted to FY labels by this conservative fallback.
                periods.append({
                    "column_type": "INTERIM_PERIOD",
                    "label": f"Interim ended {match.group('month')} {year}",
                    "start": match.start(),
                })
        if len(periods) < 2:
            continue

        for line in _normalized_lines(page_text[:MAX_PAGE_TEXT]):
            matched = []
            for field, patterns in compiled.items():
                match = next((pattern.search(line) for pattern in patterns if pattern.search(line)), None)
                if match:
                    matched.append((field, match))
            if not matched:
                continue

            # Only use rows with one numeric cell per explicit period. An extra
            # leading integer is accepted as a Notes-column reference (e.g. note 23).
            for field, label_match in matched:
                remainder = line[label_match.end():]
                tokens = [item.group(0).strip() for item in _NUMERIC_TOKEN_RE.finditer(remainder)]
                if len(tokens) == len(periods) + 1:
                    tokens = tokens[1:]
                if len(tokens) != len(periods):
                    continue

                for token, period in zip(tokens, periods):
                    if period["column_type"] != "FINANCIAL_YEAR":
                        continue
                    if parse_numeric_value(token) is None:
                        continue
                    context = f"{period['label']} in {unit} {basis.lower()}"
                    candidate = build_financial_candidate(
                        field_name=field,
                        raw_value=token,
                        row_label=line[:label_match.end()].strip(),
                        header_context=context,
                        source_url=source_url,
                        document_hash=document_hash,
                        page_number=page_number,
                    )
                    key = (field, page_number, line.casefold(), period["label"], token)
                    if key in seen:
                        continue
                    seen.add(key)
                    output.append({
                        "field_name": field,
                        "source_url": source_url,
                        "document_hash": document_hash,
                        "page_number": page_number,
                        "evidence_text": f"STATEMENT TEXT ROW: {line}"[:1000],
                        "extraction_status": "CANDIDATE_UNVERIFIED",
                        "extraction_method": "STATEMENT_TEXT_ROW_CANDIDATE",
                        "financial_candidates": [candidate],
                        "value": None,
                        "extracted_at": timestamp,
                    })
    return output


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


def _is_non_currency_metric_column(header: str) -> bool:
    """Exclude percentage/ratio/per-share columns from currency amount candidates."""
    text = str(header or "").casefold()
    patterns = (
        r"%",
        r"\bpercent(?:age)?\b",
        r"\bmargin\b",
        r"\bratio\b",
        r"\bper\s+share\b",
        r"\beps\b",
        r"\broe\b",
        r"\broce\b",
        r"\breturn\s+on\s+(?:equity|capital|net\s+worth)\b",
        r"\bworking\s+capital\s+days\b",
        r"\b(?:multiple|times)\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def extract_candidate_evidence_from_tables(
    tables_by_page: List[List[List[List[Optional[str]]]]],
    *,
    source_url: str,
    document_hash: str,
    page_contexts: Optional[List[str]] = None,
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
            # Some prospectuses use stacked headers (e.g. statement/basis, audit
            # label, then financial year). Find the first numeric financial row and
            # retain up to four preceding header rows instead of assuming the second
            # row contains the final year labels.
            first_financial_row = None
            for candidate_index, candidate_row in enumerate(rows):
                candidate_text = " | ".join(candidate_row)
                has_financial_label = any(
                    pattern.search(candidate_text)
                    for patterns in compiled.values()
                    for pattern in patterns
                )
                has_numeric_cell = any(
                    parse_numeric_value(cell) is not None
                    for cell in candidate_row[1:]
                )
                if has_financial_label and has_numeric_cell:
                    first_financial_row = candidate_index
                    break
            if first_financial_row is not None and first_financial_row > 0:
                header_rows = rows[max(0, first_financial_row - 4):first_financial_row]
            else:
                header_rows = rows[:1]
            header_context = " / ".join(" | ".join(row) for row in header_rows)[:800]
            page_context = page_contexts[page_number - 1] if page_contexts and page_number <= len(page_contexts) else ""
            statement_context = f"{page_context} {header_context}"
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

                # Parse each numeric table cell into provenance-bearing metadata, but
                # never treat it as a verified fact. Use only the corresponding column
                # header for period detection so adjacent FY columns cannot be confused.
                financial_candidates = []
                for cell_index, raw_cell in enumerate(row[1:], start=1):
                    if parse_numeric_value(raw_cell) is None:
                        continue
                    # Join this column's cells across stacked header rows. Period
                    # parsing sees only this column, while unit/basis detection uses
                    # the whole header context; adjacent FY columns cannot bleed together.
                    column_header = " ".join(
                        header_row[cell_index]
                        for header_row in header_rows
                        if cell_index < len(header_row) and header_row[cell_index]
                    )
                    # KPI tables interleave currency amounts with percentages for the
                    # same year. Do not normalize those percentage cells as currency.
                    if _is_non_currency_metric_column(column_header):
                        continue
                    explicit_unit = detect_explicit_unit(statement_context)
                    explicit_basis = identify_statement_basis(statement_context)
                    context_parts = [column_header]
                    # In some extracted table layouts, a spanning "Financial Year"
                    # label is not repeated in each year cell. Preserve that explicit
                    # parent header when this specific column contains a four-digit year.
                    if (
                        re.search(r"\b(?:financial|fiscal)\s+year\b", header_context, re.I)
                        and re.search(r"\b20\d{2}\b", column_header)
                    ):
                        context_parts.insert(0, "Financial Year")
                    if explicit_unit:
                        context_parts.append(f"in {explicit_unit}")
                    if explicit_basis:
                        context_parts.append(explicit_basis.lower())
                    candidate_context = " ".join(part for part in context_parts if part)
                    for field in matched_fields:
                        financial_candidates.append(
                            build_financial_candidate(
                                field_name=field,
                                raw_value=raw_cell,
                                row_label=row[0] if row else "",
                                header_context=candidate_context,
                                source_url=source_url,
                                document_hash=document_hash,
                                page_number=page_number,
                            )
                        )

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
                        "financial_candidates": financial_candidates,
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


def extract_pdf_candidate_evidence(
    pdf_bytes: bytes,
    *,
    source_url: str,
    table_page_numbers: Optional[set[int]] = None,
    enable_ocr: bool = False,
) -> Dict[str, Any]:
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
                # Full-document text evidence is always extracted. Callers validating
                # known financial-statement pages may restrict expensive layout/table
                # analysis to those 1-based physical PDF pages.
                if table_page_numbers is not None and (page_index + 1) not in table_page_numbers:
                    continue
                page_text = page_texts[page_index] if page_index < len(page_texts) else ""
                evidence_patterns = [
                    re.compile(pattern, re.IGNORECASE)
                    for field_patterns in EVIDENCE_PATTERNS.values()
                    for pattern in field_patterns
                ]
                # pypdf and pdfplumber do not always extract identical text from
                # the same PDF. Use pdfplumber's own text/word layer to decide whether
                # a page merits table analysis when pypdf's text is absent or incomplete.
                if not any(pattern.search(page_text) for pattern in evidence_patterns):
                    try:
                        layout_text = page.extract_text() or ""
                    except Exception:
                        layout_text = ""
                    if any(pattern.search(layout_text) for pattern in evidence_patterns):
                        page_text = layout_text
                    else:
                        try:
                            layout_words = page.extract_words(use_text_flow=False)
                            word_text = " ".join(str(word.get("text", "")) for word in layout_words)
                        except Exception:
                            word_text = ""
                        if not any(pattern.search(word_text) for pattern in evidence_patterns):
                            continue
                        page_text = word_text
                if page_index < len(page_texts) and not page_texts[page_index]:
                    page_texts[page_index] = page_text
                try:
                    detected_tables = page.extract_tables() or []
                except Exception:
                    detected_tables = []
                # PDF table detection differs across pdfplumber/pdfminer versions and
                # prospectuses frequently use whitespace-aligned columns without ruled
                # borders. Recover row candidates from word geometry when no table was
                # detected; only candidate evidence is emitted, never verified facts.
                # Some pdfplumber versions return a table object but fail to
                # preserve the cells/columns as usable rows. Use the geometry fallback
                # whenever the detected tables contain no recognizable financial row.
                has_candidate_row = any(
                    len(row or []) >= 2
                    and any(
                        pattern.search(" ".join(str(cell or "") for cell in row))
                        for patterns in EVIDENCE_PATTERNS.values()
                        for pattern in (re.compile(item, re.IGNORECASE) for item in patterns)
                    )
                    for table in detected_tables
                    for row in (table or [])
                )
                if not has_candidate_row:
                    geometry_tables = _extract_table_rows_from_word_positions(page)
                    if geometry_tables:
                        detected_tables.extend(geometry_tables)
                tables_by_page[page_index] = detected_tables
        table_evidence = extract_candidate_evidence_from_tables(
            tables_by_page,
            source_url=source_url,
            document_hash=document_hash,
            page_contexts=page_texts,
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

    # Fallback for regulator PDFs whose text layer preserves row values but
    # whose table geometry does not produce usable cells. Only explicit date
    # columns and known row/value alignment are accepted; all output remains unverified.
    try:
        statement_text_evidence = extract_candidate_evidence_from_statement_text(
            page_texts,
            source_url=source_url,
            document_hash=document_hash,
        )
        existing_statement_keys = {
            (item["field_name"], item["page_number"], item["evidence_text"].casefold())
            for item in evidence
        }
        for item in statement_text_evidence:
            key = (item["field_name"], item["page_number"], item["evidence_text"].casefold())
            if key not in existing_statement_keys:
                evidence.append(item)
                existing_statement_keys.add(key)
    except Exception:
        # Text-only row parsing is a best-effort fallback; preserve other evidence.
        pass

    text_pages_count = sum(bool(text.strip()) for text in page_texts)
    has_text = text_pages_count > 0
    has_images = False
    if not has_text:
        try:
            has_images = any(len(getattr(page, "images", [])) > 0 for page in reader.pages)
        except Exception:
            has_images = False

    is_scanned_image = bool(has_images and not has_text)
    ocr_required = is_scanned_image

    if is_scanned_image:
        if enable_ocr:
            ocr_res = extract_scanned_pdf_ocr_text(pdf_bytes, source_url=source_url)
            if ocr_res.get("evidence"):
                evidence.extend(ocr_res["evidence"])
                status = "CANDIDATES_FOUND"
                notice = "Candidates extracted via OCR fallback."
            elif ocr_res.get("text_pages_extracted", 0) > 0:
                status = "NO_CANDIDATES_FOUND"
                notice = "OCR executed successfully but no candidate keywords matched."
            else:
                status = "SCANNED_IMAGE_DETECTED"
                notice = ocr_res.get("notice") or (
                    "SCANNED_PDF_NEEDS_OCR: Document contains scanned/rasterized image pages without "
                    "an embedded text layer. Automated extraction requires OCR preprocessing before candidate analysis."
                )
        else:
            status = "SCANNED_IMAGE_DETECTED"
            notice = (
                "SCANNED_PDF_NEEDS_OCR: Document contains scanned/rasterized image pages without "
                "an embedded text layer. Automated extraction requires OCR preprocessing before candidate analysis."
            )
    elif evidence:
        status = "CANDIDATES_FOUND"
        notice = None
    else:
        status = "NO_CANDIDATES_FOUND"
        notice = None

    return {
        "document_hash": document_hash,
        "page_count": len(reader.pages),
        "text_pages_extracted": text_pages_count,
        "evidence_count": len(evidence),
        "evidence": evidence,
        "status": status,
        "verification_status": "UNVERIFIED",
        "is_scanned_image": is_scanned_image,
        "ocr_required": ocr_required,
        "notice": notice,
    }


def extract_scanned_pdf_ocr_text(
    pdf_bytes: bytes,
    *,
    source_url: str = "",
    max_pages: int = 10,
) -> Dict[str, Any]:
    """Fallback OCR text extractor for scanned or image-based PDF prospectuses.

    Attempts to extract embedded images from pages and process them with pytesseract
    if available. Fails gracefully if pytesseract or the Tesseract binary is not installed,
    returning structured diagnostic information without crashing or inferring synthetic values.
    """
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

    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError:
        return {
            "status": "OCR_TOOL_UNAVAILABLE",
            "ocr_available": False,
            "document_hash": document_hash,
            "page_count": len(reader.pages),
            "text_pages_extracted": 0,
            "evidence_count": 0,
            "evidence": [],
            "page_texts": [],
            "notice": "OCR engine unavailable: pytesseract is not installed in the python environment.",
        }

    page_texts: List[str] = []
    total_pages = min(len(reader.pages), max_pages)

    try:
        for idx in range(total_pages):
            page = reader.pages[idx]
            page_text_pieces: List[str] = []
            direct_text = (page.extract_text() or "").strip()
            if direct_text:
                page_text_pieces.append(direct_text)
            else:
                images = getattr(page, "images", [])
                for img_obj in images:
                    try:
                        img_bytes = img_obj.data
                        pil_img = Image.open(BytesIO(img_bytes))
                        ocr_result = pytesseract.image_to_string(pil_img)
                        if ocr_result and ocr_result.strip():
                            page_text_pieces.append(ocr_result.strip())
                    except Exception:
                        continue
            page_texts.append("\n".join(page_text_pieces)[:MAX_PAGE_TEXT])
    except Exception as exc:
        return {
            "status": "OCR_ENGINE_ERROR",
            "ocr_available": False,
            "document_hash": document_hash,
            "page_count": len(reader.pages),
            "text_pages_extracted": 0,
            "evidence_count": 0,
            "evidence": [],
            "page_texts": [],
            "notice": f"OCR extraction failed or Tesseract binary not found: {str(exc)}",
        }

    evidence = extract_candidate_evidence_from_pages(
        page_texts,
        source_url=source_url,
        document_hash=document_hash,
    )

    text_pages_count = sum(bool(text.strip()) for text in page_texts)

    return {
        "status": "OCR_EXTRACTED" if text_pages_count > 0 else "NO_TEXT_EXTRACTED",
        "ocr_available": True,
        "document_hash": document_hash,
        "page_count": len(reader.pages),
        "text_pages_extracted": text_pages_count,
        "evidence_count": len(evidence),
        "evidence": evidence,
        "page_texts": page_texts,
        "notice": None if text_pages_count > 0 else "OCR completed but no readable text was identified.",
    }
