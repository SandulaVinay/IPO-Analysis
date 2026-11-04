"""Bounded extraction for common exchange financial-results attachment formats.

Parsed table values are candidates for review. This module never verifies facts or
produces investment recommendations.
"""

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from zipfile import BadZipFile, ZipFile

from bs4 import BeautifulSoup
import pdfplumber
from openpyxl import load_workbook
import xlrd

from src.discovery.normalizer import Normalizer

MAX_DOCUMENT_BYTES = 15_000_000
MAX_TABLES = 100
MAX_ROWS = 5_000
MAX_COLUMNS = 100
MAX_PDF_PAGES = 40
MAX_XLSX_EXPANDED_BYTES = 100_000_000
MAX_XLS_SHEETS = 20


def detect_document_format(content: bytes, content_type: str = "", url: str = "") -> str:
    """Identify common attachment formats using file signatures before metadata."""
    if not content:
        return "unknown"
    head = content[:2_048].lstrip().lower()
    mime = (content_type or "").lower()
    path = (url or "").split("?", 1)[0].lower()
    if content.startswith(b"%PDF-"):
        return "pdf"
    if content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") or path.endswith(".xls") or "application/vnd.ms-excel" in mime:
        return "xls"
    if content.startswith(b"PK\x03\x04"):
        if path.endswith((".xlsx", ".xlsm")) or "spreadsheet" in mime or "excel" in mime:
            return "xlsx"
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist()[:2_000])
                if "xl/workbook.xml" in names:
                    return "xlsx"
        except (BadZipFile, OSError):
            pass
        return "office_zip"
    if b"<!doctype html" in head or b"<html" in head or "text/html" in mime or "xhtml" in mime or path.endswith((".html", ".htm")):
        sample = content[:250_000].lower()
        if b"nonfraction" in sample or b"nonnumeric" in sample or "ixbrl" in path:
            return "ixbrl"
        return "html"
    if b"<xbrl" in head or b":xbrl" in head or "xbrl" in mime or path.endswith((".xml", ".xbrl")):
        return "xbrl_xml"
    if path.endswith((".csv", ".tsv")) or "text/csv" in mime or "application/csv" in mime or "tab-separated" in mime:
        return "csv"
    try:
        sample_text = content[:8_192].decode("utf-8-sig")
    except UnicodeDecodeError:
        sample_text = ""
    if sample_text and "\n" in sample_text and not "\x00" in sample_text:
        try:
            csv.Sniffer().sniff(sample_text[:4_096], delimiters=",;\t|")
            return "csv"
        except csv.Error:
            pass
    return "unknown"


def _local_name(value: str) -> str:
    return str(value or "").rsplit("}", 1)[-1].split(":")[-1].lower()


def _copy_xml_node(source: Any, parent: ET.Element) -> None:
    """Copy a tiny inline-XBRL resource subtree while stripping unneeded namespaces."""
    name = _local_name(getattr(source, "name", ""))
    if not name:
        return
    attributes = {}
    if name == "context":
        context_id = source.get("id")
        if context_id:
            attributes["id"] = str(context_id)
    elif name == "unit":
        unit_id = source.get("id")
        if unit_id:
            attributes["id"] = str(unit_id)
    element = ET.SubElement(parent, name, attributes)
    for child in getattr(source, "children", []):
        if getattr(child, "name", None):
            _copy_xml_node(child, element)
        elif isinstance(child, str) and child.strip():
            element.text = (element.text or "") + child.strip()


def extract_ixbrl_as_xbrl(content: bytes) -> bytes:
    """Convert inline XBRL contexts, units, and numeric facts into a safe XML instance."""
    if not content or len(content) > 10_000_000:
        raise ValueError("iXBRL content is empty or exceeds the 10 MB safety limit.")
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ValueError("iXBRL contains a prohibited DTD/entity declaration.")
    soup = BeautifulSoup(content, "lxml")
    resources = soup.find(lambda tag: getattr(tag, "name", "").split(":")[-1].lower() == "resources")
    if resources is None:
        raise ValueError("No inline-XBRL resources block was found.")
    root = ET.Element("xbrl")
    for node in resources.find_all(recursive=True):
        if _local_name(node.name) in {"context", "unit"}:
            _copy_xml_node(node, root)
    continuations = {
        str(node.get("id")): node.get_text("", strip=True)
        for node in soup.find_all(lambda tag: getattr(tag, "name", "").split(":")[-1].lower() == "continuation")
        if node.get("id")
    }
    count = 0
    for fact in soup.find_all(lambda tag: getattr(tag, "name", "").split(":")[-1].lower() == "nonfraction"):
        fact_name = fact.get("name")
        context_ref = fact.get("contextref")
        raw = fact.get_text("", strip=True)
        continuation_id = fact.get("continuedat")
        if continuation_id:
            raw += continuations.get(str(continuation_id), "")
        if not fact_name or not context_ref or not raw or fact.get("xsi:nil") == "true":
            continue
        raw = re.sub(r"\s+", "", raw).replace(",", "")
        if raw.startswith("(") and raw.endswith(")"):
            raw = "-" + raw[1:-1]
        if fact.get("sign") == "-":
            raw = raw[1:] if raw.startswith("-") else "-" + raw
        try:
            value = Decimal(raw) * (Decimal(10) ** int(fact.get("scale") or "0"))
        except (InvalidOperation, ValueError, OverflowError):
            continue
        if not value.is_finite():
            continue
        element = ET.SubElement(
            root,
            fact_name.split(":")[-1],
            {"contextRef": str(context_ref)},
        )
        unit_ref = fact.get("unitref")
        if unit_ref:
            element.set("unitRef", str(unit_ref))
        element.text = str(value)
        count += 1
    if not count:
        raise ValueError("No usable inline-XBRL numeric facts were found.")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _bounded_table(rows: Iterable[Sequence[Any]]) -> List[List[str]]:
    output: List[List[str]] = []
    for row in rows:
        if len(output) >= MAX_ROWS:
            break
        output.append([_cell_text(value) for value in list(row)[:MAX_COLUMNS]])
    return output


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return re.sub(r"\s+", " ", str(value)).strip()


def _read_html_table(table: Any) -> List[List[str]]:
    """Read basic HTML tables and preserve colspan/rowspan alignment."""
    rows: List[List[str]] = []
    occupied: Dict[Tuple[int, int], str] = {}
    for row_index, tr in enumerate(table.find_all("tr")[:MAX_ROWS]):
        cells: List[str] = []
        col = 0
        for cell in tr.find_all(["th", "td"], recursive=False)[:MAX_COLUMNS]:
            while (row_index, col) in occupied:
                cells.append(occupied[(row_index, col)])
                col += 1
            value = _cell_text(cell.get_text(" ", strip=True))
            try:
                colspan = max(1, min(20, int(cell.get("colspan", 1))))
                rowspan = max(1, min(20, int(cell.get("rowspan", 1))))
            except (TypeError, ValueError):
                colspan = rowspan = 1
            for offset in range(colspan):
                cells.append(value if offset == 0 else "")
                for row_offset in range(1, rowspan):
                    occupied[(row_index + row_offset, col + offset)] = value if offset == 0 else ""
            col += colspan
        while (row_index, col) in occupied and col < MAX_COLUMNS:
            cells.append(occupied[(row_index, col)])
            col += 1
        if cells:
            rows.append(cells[:MAX_COLUMNS])
    return rows


def _extract_csv_tables(content: bytes, url: str = "") -> List[Dict[str, Any]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1252")
    delimiter = "\t" if (url or "").lower().split("?", 1)[0].endswith(".tsv") else ","
    try:
        dialect = csv.Sniffer().sniff(text[:8_192], delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        pass
    rows = list(csv.reader(StringIO(text), delimiter=delimiter))
    return [{"name": "CSV", "rows": _bounded_table(rows)}] if rows else []


def _extract_xlsx_tables(content: bytes) -> List[Dict[str, Any]]:
    try:
        with ZipFile(BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > 2_000 or sum(member.file_size for member in members) > MAX_XLSX_EXPANDED_BYTES:
                raise ValueError("Workbook expands beyond the spreadsheet safety limit.")
            if any(member.flag_bits & 0x1 for member in members):
                raise ValueError("Encrypted workbooks are not supported.")
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False)
        tables = []
        try:
            for sheet in workbook.worksheets[:20]:
                rows = _bounded_table(sheet.iter_rows(max_row=MAX_ROWS, max_col=MAX_COLUMNS, values_only=True))
                if rows:
                    tables.append({"name": sheet.title, "rows": rows})
        finally:
            workbook.close()
        return tables
    except BadZipFile as exc:
        raise ValueError("Spreadsheet attachment is not a valid XLSX workbook.") from exc


def _extract_xls_tables(content: bytes) -> List[Dict[str, Any]]:
    """Read legacy XLS workbooks with bounded sheet, row, and column counts."""
    try:
        workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
        tables = []
        try:
            for sheet in workbook.sheets()[:MAX_XLS_SHEETS]:
                rows = []
                for row_index in range(min(sheet.nrows, MAX_ROWS)):
                    row = []
                    for column_index in range(min(sheet.ncols, MAX_COLUMNS)):
                        cell = sheet.cell(row_index, column_index)
                        value = cell.value
                        if cell.ctype == xlrd.XL_CELL_DATE:
                            try:
                                value = xlrd.xldate.xldate_as_datetime(value, workbook.datemode)
                            except (ValueError, OverflowError):
                                value = ""
                        row.append(value)
                    rows.append(row)
                bounded = _bounded_table(rows)
                if bounded:
                    tables.append({"name": sheet.name, "rows": bounded})
        finally:
            workbook.release_resources()
        return tables
    except Exception as exc:
        raise ValueError("Legacy XLS workbook is invalid or could not be read safely.") from exc


def extract_document(content: bytes, content_type: str = "", url: str = "") -> Dict[str, Any]:
    """Extract safe table candidates or XML facts from a bounded source document."""
    if not content:
        return {"status": "UNAVAILABLE", "format": "unknown", "reason": "Attachment is empty."}
    if len(content) > MAX_DOCUMENT_BYTES:
        return {"status": "UNAVAILABLE", "format": "unknown", "reason": "Attachment exceeds the 15 MB limit."}
    document_format = detect_document_format(content, content_type, url)
    if document_format == "ixbrl":
        try:
            return {"status": "EXTRACTED", "format": document_format, "xbrl_xml": extract_ixbrl_as_xbrl(content)}
        except ValueError as exc:
            return {"status": "UNAVAILABLE", "format": document_format, "reason": str(exc)}
    if document_format == "xbrl_xml":
        if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
            return {"status": "UNAVAILABLE", "format": document_format, "reason": "XML contains a prohibited DTD/entity declaration."}
        try:
            ET.fromstring(content)
        except ET.ParseError:
            return {"status": "UNAVAILABLE", "format": document_format, "reason": "Malformed XML attachment."}
        return {"status": "EXTRACTED", "format": document_format, "xbrl_xml": content}
    if document_format == "csv":
        try:
            tables = _extract_csv_tables(content, url)
        except (csv.Error, UnicodeError, ValueError) as exc:
            return {"status": "UNAVAILABLE", "format": document_format, "reason": f"CSV parsing failed ({type(exc).__name__})."}
        return {"status": "EXTRACTED" if tables else "UNAVAILABLE", "format": document_format, "tables": tables}
    if document_format in {"xlsx", "xls"}:
        try:
            tables = _extract_xlsx_tables(content) if document_format == "xlsx" else _extract_xls_tables(content)
        except Exception as exc:
            return {"status": "UNAVAILABLE", "format": document_format, "reason": f"Workbook parsing failed ({type(exc).__name__})."}
        return {"status": "EXTRACTED" if tables else "UNAVAILABLE", "format": document_format, "tables": tables}
    if document_format == "html":
        try:
            soup = BeautifulSoup(content, "lxml")
            tables = [
                {
                    "name": f"HTML table {index + 1}",
                    "rows": _read_html_table(table),
                    "context": _cell_text(
                        " ".join(
                            node.get_text(" ", strip=True)
                            for node in [table.find_previous(["h1", "h2", "h3", "h4", "p", "caption"])]
                            if node is not None
                        )
                    ),
                }
                for index, table in enumerate(soup.find_all("table")[:MAX_TABLES])
                if table.find_all("tr")
            ]
            text = _cell_text(soup.get_text(" ", strip=True))[:120_000]
        except Exception as exc:
            return {"status": "UNAVAILABLE", "format": document_format, "reason": f"HTML parsing failed ({type(exc).__name__})."}
        return {"status": "EXTRACTED" if tables else "UNAVAILABLE", "format": document_format, "tables": tables, "text": text}
    if document_format == "pdf":
        tables: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        try:
            with pdfplumber.open(BytesIO(content)) as pdf:
                for page_number, page in enumerate(pdf.pages[:MAX_PDF_PAGES], start=1):
                    page_text = page.extract_text() or ""
                    if page_text and sum(map(len, text_parts)) < 120_000:
                        text_parts.append(f"[Page {page_number}] {page_text[:120_000]}")
                    for table_index, rows in enumerate(page.extract_tables() or []):
                        if rows and len(tables) < MAX_TABLES:
                            tables.append({
                                "name": f"PDF page {page_number} table {table_index + 1}",
                                "rows": _bounded_table(rows),
                                "context": page_text or "",
                            })
        except Exception as exc:
            return {"status": "UNAVAILABLE", "format": document_format, "reason": f"PDF table extraction failed ({type(exc).__name__})."}
        if not text_parts and not tables:
            return {"status": "UNAVAILABLE", "format": document_format, "reason": "No selectable PDF text or tables; the file may be scanned."}
        return {
            "status": "EXTRACTED",
            "format": document_format,
            "tables": tables,
            "text": "\n".join(text_parts)[:120_000],
            "table_count": len(tables),
        }
    reason = "Legacy XLS workbooks require conversion to XLSX; this format is unsupported."
    if document_format == "unknown":
        reason = "Unsupported or unrecognized attachment format."
    return {"status": "UNAVAILABLE", "format": document_format, "reason": reason}


def _normalized_text(value: str) -> str:
    value = str(value or "").lower()
    value = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _date_aliases(target: date) -> set[str]:
    variants = {
        target.isoformat(),
        target.strftime("%d-%m-%Y"),
        target.strftime("%d/%m/%Y"),
        target.strftime("%d.%m.%Y"),
        target.strftime("%d-%b-%Y"),
        target.strftime("%d-%b-%y"),
        target.strftime("%d %b %Y"),
        target.strftime("%d %B %Y"),
        target.strftime("%b %d, %Y"),
        target.strftime("%B %d, %Y"),
    }
    return {_normalized_text(value) for value in variants}


def _contains_target_date(value: str, target: date) -> bool:
    normalized = _normalized_text(value)
    return any(alias and alias in normalized for alias in _date_aliases(target))


def _period_kind_hint(item: Dict[str, Any]) -> str:
    hint = _normalized_text(" ".join(str(item.get(key) or "") for key in ("period_type", "relating_to", "headline")))
    if any(word in hint for word in ("annual", "year ended", "yearly", "full year")):
        return "annual"
    if any(word in hint for word in ("quarter", "3 months", "three months")):
        return "quarter"
    return ""


def _period_kind_matches(header: str, kind: str) -> bool:
    normalized = _normalized_text(header)
    if kind == "annual":
        if any(word in normalized for word in ("half year", "six months", "quarter", "3 months", "three months")):
            return False
        return any(word in normalized for word in ("year ended", "annual", "12 months", "twelve months", "financial year"))
    if kind == "quarter":
        if any(word in normalized for word in ("half year", "six months", "year ended", "annual")):
            return False
        return any(word in normalized for word in ("quarter", "3 months", "three months"))
    return True


_MONTH_NAME = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"


def _dates_in_text(value: str) -> List[date]:
    """Find only complete calendar dates in a table header."""
    source = str(value or "")
    patterns = (
        r"\b20\d{2}-\d{1,2}-\d{1,2}\b",
        r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",
        rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH_NAME}\s+\d{{4}}\b",
        rf"\b{_MONTH_NAME}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b",
    )
    output = set()
    for pattern in patterns:
        for match in re.finditer(pattern, source, re.IGNORECASE):
            candidate = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", match.group(0), flags=re.IGNORECASE)
            parsed = Normalizer.parse_date(candidate)
            if parsed:
                output.add(parsed)
    return sorted(output)


def _infer_period_from_tables(
    tables: Sequence[Dict[str, Any]], item: Dict[str, Any]
) -> Optional[Tuple[date, str]]:
    """Use one uniquely newest, explicitly labelled period from the attachment tables."""
    requested_kind = _period_kind_hint(item)
    candidates = set()
    for table in tables[:MAX_TABLES]:
        raw_rows = table.get("rows") or []
        rows = [_bounded_table([row])[0] for row in raw_rows[:MAX_ROWS] if isinstance(row, (list, tuple))]
        if not rows:
            continue
        date_rows = [
            index for index, row in enumerate(rows[: min(12, len(rows))])
            if any(_dates_in_text(cell) for cell in row)
        ]
        if not date_rows:
            continue
        header_end = max(date_rows)
        width = min(MAX_COLUMNS, max((len(row) for row in rows), default=0))
        table_context = " ".join(
            str(cell)
            for row in rows[: min(len(rows), header_end + 2)]
            for cell in row
        )
        context = f"{table.get('name', '')} {table.get('context', '')} {table_context}"
        for column in range(1, width):
            header = " ".join(
                rows[row_index][column]
                for row_index in range(header_end + 1)
                if column < len(rows[row_index])
            )
            dates = _dates_in_text(header)
            if not dates:
                continue
            combined = f"{header} {context}"
            explicit_quarter = _period_kind_matches(combined, "quarter")
            explicit_annual = _period_kind_matches(combined, "annual")
            kinds = []
            if explicit_quarter:
                kinds.append("quarter")
            if explicit_annual:
                kinds.append("annual")
            if requested_kind:
                kinds = [kind for kind in kinds if kind == requested_kind]
            for period_date in dates:
                for kind in kinds:
                    candidates.add((period_date, kind))

    if not candidates:
        return None
    newest_date = max(period_date for period_date, _ in candidates)
    newest = {(period_date, kind) for period_date, kind in candidates if period_date == newest_date}
    if len(newest) != 1:
        return None
    period_date, period_kind = next(iter(newest))
    return period_date, period_kind


def infer_xbrl_reporting_period(content: bytes, item: Dict[str, Any]) -> Optional[Tuple[date, str]]:
    """Select one unambiguous non-dimensional quarterly or annual XBRL context."""
    if not content or len(content) > 10_000_000:
        return None
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        return None
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    requested_kind = _period_kind_hint(item)
    announced_dates = _dates_in_text(str(item.get("broadcast_time") or ""))
    cutoff = max(announced_dates) if announced_dates else None
    candidates = set()
    for node in root.iter():
        if _local_name(node.tag) != "context":
            continue
        dimensioned = any(_local_name(child.tag) in {"explicitmember", "typedmember"} for child in node.iter())
        if dimensioned:
            continue
        start_value = next(
            (child.text for child in node.iter() if _local_name(child.tag) == "startdate" and child.text), None
        )
        end_value = next(
            (child.text for child in node.iter() if _local_name(child.tag) in {"enddate", "instant"} and child.text), None
        )
        start_date = Normalizer.parse_date(start_value)
        end_date = Normalizer.parse_date(end_value)
        if not start_date or not end_date or (cutoff and end_date > cutoff):
            continue
        days = (end_date - start_date).days + 1
        kind = "quarter" if 60 <= days <= 125 else "annual" if 300 <= days <= 400 else ""
        if kind and (not requested_kind or requested_kind == kind):
            candidates.add((end_date, kind))
    if not candidates:
        return None
    newest_date = max(period_date for period_date, _ in candidates)
    newest = {(period_date, kind) for period_date, kind in candidates if period_date == newest_date}
    if len(newest) != 1:
        return None
    return next(iter(newest))


def _unit_matches(text: str) -> List[Tuple[str, float]]:
    text = str(text or "").replace("\u20b9", " INR ")
    normalized = re.sub(r"[(),]", " ", str(text or "").replace("₹", " INR "))
    normalized = re.sub(r"\s+", " ", normalized).lower()
    patterns = (
        ("INR_CRORES", 1.0, r"(?:inr|rs\.?|rupees?)\s*(?:in\s*)?crores?\b|(?:inr|rs\.?|rupees?)\s+in\s+cr\b"),
        ("INR_LAKHS", 0.01, r"(?:inr|rs\.?|rupees?)\s*(?:in\s*)?lakhs?\b|(?:inr|rs\.?|rupees?)\s*(?:in\s*)?lacs?\b"),
        ("INR_MILLIONS", 0.1, r"(?:inr|rs\.?|rupees?)\s*(?:in\s*)?millions?\b"),
        ("INR_THOUSANDS", 0.0001, r"(?:inr|rs\.?|rupees?)\s*(?:in\s*)?thousands?\b"),
    )
    found = []
    for unit, factor, pattern in patterns:
        if re.search(pattern, normalized, re.IGNORECASE):
            found.append((unit, factor))
    return found


def _parse_money_cell(value: str) -> Optional[Decimal]:
    value = str(value or "").replace("\u20b9", "").replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    raw = str(value or "").strip().replace("−", "-").replace("–", "-").replace("—", "-")
    if raw.lower() in {"", "-", "--", "na", "n a", "n a", "not available", "nil"}:
        return None
    if "%" in raw or re.search(r"\b(?:times|ratio|per share)\b", raw, re.IGNORECASE):
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    if negative:
        raw = raw[1:-1]
    raw = raw.replace(",", "").replace("₹", "").strip()
    raw = re.sub(r"^(?:INR|Rs\.?|Rupees?)\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*(?:INR|Rs\.?|Rupees?)$", "", raw, flags=re.IGNORECASE)
    raw = raw.replace(" ", "")
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    if negative:
        number = -abs(number)
    return number if number.is_finite() else None


def _basis(item: Dict[str, Any], text: str) -> str:
    metadata = _normalized_text(str(item.get("consolidation") or ""))
    if metadata in {"standalone", "non consolidated", "nonconsolidated"}:
        return "STANDALONE"
    if metadata == "consolidated":
        return "CONSOLIDATED"
    normalized = _normalized_text(text)
    consolidated = bool(re.search(r"\bconsolidated\b", normalized))
    standalone = bool(re.search(r"\bstandalone\b|\bnon consolidated\b", normalized))
    if consolidated and not standalone:
        return "CONSOLIDATED"
    if standalone and not consolidated:
        return "STANDALONE"
    return "UNRESOLVED"


def _metric_for_label(label: str) -> Optional[str]:
    key = _normalized_text(label)
    if not key:
        return None
    if "earnings per share" in key or key.startswith("eps"):
        return "eps"
    if any(word in key for word in ("percentage", "margin", "growth", "basic", "diluted")):
        return None
    if "revenue from operations" in key and "other income" not in key:
        return "revenue_cr"
    if any(phrase in key for phrase in (
        "profit for the period", "profit for the year", "profit after tax",
        "profit loss after tax", "net profit for the period", "net profit for the year",
        "profit loss for period", "profit loss for year",
    )):
        if "before tax" not in key:
            return "pat_cr"
    if any(phrase in key for phrase in (
        "net cash flows from operating activities", "net cash flows used in operating activities",
        "cash flows from used in operating activities", "net cash generated from operating activities",
    )):
        return "cfo_cr"
    return None


def extract_financial_metrics_from_tables(
    tables: Sequence[Dict[str, Any]],
    *,
    document_text: str = "",
    item: Dict[str, Any],
    document_format: str,
) -> Dict[str, Any]:
    """Map only rows with an explicit target-period column and rupee unit to candidates."""
    target = Normalizer.parse_date(item.get("period_ended"))
    period_provenance = "EXCHANGE_ANNOUNCEMENT"
    if target is None:
        inferred = _infer_period_from_tables(tables, item)
        if inferred is None:
            return {"status": "UNAVAILABLE", "reason": "Filing period end is missing and could not be uniquely established from an explicitly labelled attachment header."}
        target, inferred_kind = inferred
        period_provenance = "EXPLICIT_ATTACHMENT_HEADER"
        if not _period_kind_hint(item):
            item = {**item, "period_type": "Annual" if inferred_kind == "annual" else "Quarterly"}
    kind = _period_kind_hint(item)
    candidates: List[Dict[str, Any]] = []
    saw_target_date = False
    saw_unit = False
    for table in tables[:MAX_TABLES]:
        raw_rows = table.get("rows") or []
        rows = [_bounded_table([row])[0] for row in raw_rows[:MAX_ROWS] if isinstance(row, (list, tuple))]
        if not rows:
            continue
        width = min(MAX_COLUMNS, max((len(row) for row in rows), default=0))
        header_limit = min(12, len(rows))
        date_rows = [
            index for index, row in enumerate(rows[:header_limit])
            if any(_contains_target_date(cell, target) for cell in row)
        ]
        header_end = max(date_rows, default=-1)
        if header_end < 0:
            continue
        header_by_column = [
            " ".join(rows[row_index][column] for row_index in range(header_end + 1) if column < len(rows[row_index]))
            for column in range(width)
        ]
        matching_columns = []
        for column, header in enumerate(header_by_column):
            if column == 0 or not _contains_target_date(header, target):
                continue
            if kind and not _period_kind_matches(header, kind):
                continue
            matching_columns.append(column)
        if not matching_columns:
            # The filing date exists but is not mapped to an unambiguous period column.
            saw_target_date = True
            continue
        if len(matching_columns) != 1:
            saw_target_date = True
            continue
        current_column = matching_columns[0]
        saw_target_date = True
        table_context = " ".join(
            cell for row in rows[: min(len(rows), header_end + 2)] for cell in row
        )
        scoped_context = str(table.get("context") or "")
        unit_matches = _unit_matches(f"{table_context} {scoped_context}")
        if not unit_matches:
            continue
        unique_units = set(unit_matches)
        if len(unique_units) != 1:
            continue
        unit_name, factor = next(iter(unique_units))
        saw_unit = True
        basis = _basis(item, f"{table_context} {scoped_context}")
        found: Dict[str, Any] = {}
        raw_values: Dict[str, str] = {}
        for row in rows[header_end + 1 :]:
            if len(row) <= current_column:
                continue
            metric = _metric_for_label(row[0])
            if metric is None or metric in found:
                continue
            raw_value = row[current_column]
            number = _parse_money_cell(raw_value)
            if number is None:
                continue
            if metric == "eps":
                # EPS is already rupees per share; unit conversions do not apply.
                found[metric] = float(number)
            else:
                found[metric] = float(number * Decimal(str(factor)))
            raw_values[metric] = raw_value
        if found:
            candidates.append({
                "metrics": found,
                "raw_values": raw_values,
                "unit": unit_name,
                "basis": basis,
                "table": str(table.get("name") or "financial statement table"),
            })

    if not candidates:
        if saw_target_date and not saw_unit:
            reason = "Target reporting period was found, but the rupee unit is absent or ambiguous."
        elif saw_target_date:
            reason = "Target period is present, but required labelled metric rows could not be mapped safely."
        else:
            reason = "No table column explicitly matched the filing period end."
        return {"status": "UNAVAILABLE", "reason": reason, "extraction_method": f"{document_format.upper()}_TABLE"}

    units = {candidate["unit"] for candidate in candidates}
    bases = {candidate["basis"] for candidate in candidates}
    if len(units) != 1 or len(bases) != 1:
        return {
            "status": "UNAVAILABLE",
            "reason": "Matched statement tables disagree on unit or standalone/consolidated basis.",
            "extraction_method": f"{document_format.upper()}_TABLE",
        }
    metrics: Dict[str, Any] = {}
    raw_values: Dict[str, str] = {}
    for candidate in candidates:
        for metric, value in candidate["metrics"].items():
            if metric in metrics and metrics[metric] != value:
                return {
                    "status": "UNAVAILABLE",
                    "reason": f"Multiple matched statement tables disagree on {metric}; the filing is ambiguous.",
                    "extraction_method": f"{document_format.upper()}_TABLE",
                }
            metrics[metric] = value
            raw_values[metric] = candidate["raw_values"][metric]
    missing = [name for name in ("revenue_cr", "pat_cr") if name not in metrics]
    if len(missing) == 2:
        return {"status": "UNAVAILABLE", "reason": "Revenue and PAT rows were not both present in the matched financial table."}
    period_type = item.get("period_type") or ("Annual" if kind == "annual" else "Quarterly" if kind == "quarter" else "Unspecified")
    return {
        "status": "EXTRACTED",
        "source_status": "CANDIDATE_UNVERIFIED",
        "assessment_eligible": False,
        "extraction_method": f"{document_format.upper()}_TABLE",
        "period_ended": target.isoformat(),
        "period_type": period_type,
        "period_provenance": period_provenance,
        "unit": next(iter(units)),
        "statement_basis": next(iter(bases)),
        "tables": [candidate["table"] for candidate in candidates],
        "revenue_cr": metrics.get("revenue_cr"),
        "pat_cr": metrics.get("pat_cr"),
        "cfo_cr": metrics.get("cfo_cr"),
        "eps": metrics.get("eps"),
        "raw_values": raw_values,
        "missing_metrics": missing,
        "reason": "Values are unverified candidates transcribed from an official filing table; check the source before use.",
    }
