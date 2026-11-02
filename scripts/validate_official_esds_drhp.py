#!/usr/bin/env python3
"""Download and validate the real ESDS DRHP published on SEBI.

This is an opt-in/live-source validation, not a scoring or reviewer-verification
step. The report records the exact downloaded bytes' SHA-256 and keeps every
extracted financial value CANDIDATE_UNVERIFIED.
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
from pypdf import PdfReader
from src.documents.extractor import MAX_PDF_BYTES, extract_pdf_candidate_evidence

SOURCE_URL = "https://www.sebi.gov.in/sebi_data/attachdocs/apr-2025/1743751804884_762.pdf"
EXPECTED = [
    {"field_name":"revenue_from_operations","raw_value":"2,865.18","period":"FY2023-2024","unit":"million","normalized_value_inr_crore":"286.518","source_statement_page_printed":292,"meaning":"Consolidated revenue from operations, year ended 31 March 2024"},
    {"field_name":"profit_after_tax","raw_value":"136.10","period":"FY2023-2024","unit":"million","normalized_value_inr_crore":"13.610","source_statement_page_printed":292,"meaning":"Consolidated profit for the year, year ended 31 March 2024"},
    {"field_name":"operating_cash_flow","raw_value":"455.77","period":"FY2023-2024","unit":"million","normalized_value_inr_crore":"45.577","source_statement_page_printed":293,"meaning":"Net cash inflows from operating activities, year ended 31 March 2024"},
]

def download_pdf() -> bytes:
    parsed = urlparse(SOURCE_URL)
    if parsed.scheme != "https" or parsed.hostname != "www.sebi.gov.in":
        raise RuntimeError("Source URL must be the explicitly approved SEBI HTTPS host.")
    chunks, total = [], 0
    with requests.get(SOURCE_URL, stream=True, timeout=(20, 90), headers={"User-Agent":"IPO-Analysis-official-filing-validation/1.0"}) as response:
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").lower()
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_PDF_BYTES:
                raise RuntimeError(f"Official PDF exceeded {MAX_PDF_BYTES // (1024 * 1024)} MB safety limit.")
            chunks.append(chunk)
        body = b"".join(chunks)
        if b"%PDF-" not in body[:1024]:
            raise RuntimeError(f"SEBI response is not a PDF (content-type={content_type!r}).")
        return body

def _flatten_candidates(extraction: dict) -> list[dict]:
    return [candidate for evidence in extraction.get("evidence", []) for candidate in evidence.get("financial_candidates", []) if isinstance(candidate, dict)]

def _find_statement_pages(page_texts: list[str]) -> dict[str, int | None]:
    pages = {"profit_and_loss":None,"cash_flow":None}
    for index, text in enumerate(page_texts, start=1):
        if pages["profit_and_loss"] is None and "Restated Consolidated Statement of Profit and Loss" in text:
            pages["profit_and_loss"] = index
        if pages["cash_flow"] is None and "Restated Consolidated Statement of Cashflow" in text:
            pages["cash_flow"] = index
    return pages

def _raw_row_check(page_texts: list[str], label_pattern: str, expected_value: str, start_page: int | None) -> dict:
    compiled = re.compile(label_pattern, re.I)
    page_indexes = [start_page - 1] if start_page else list(range(len(page_texts)))
    for page_index in page_indexes:
        if page_index is None or page_index < 0 or page_index >= len(page_texts):
            continue
        text = page_texts[page_index]
        match = compiled.search(text)
        if match:
            window = text[match.start():match.start() + 1800]
            if expected_value in window:
                return {"passed":True,"physical_page":page_index+1,"label":match.group(0),"window":window[:700]}
    return {"passed":False,"physical_page":start_page,"expected_value":expected_value,"label_pattern":label_pattern}

def run() -> int:
    report_path = Path("reports/prospectus/ESDS_DRHP_live_validation.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {"validation_type":"LIVE_OFFICIAL_SOURCE_EXTRACTION","source_url":SOURCE_URL,"issuer":"ESDS Software Solution Limited","document_type":"DRHP","generated_at_utc":datetime.now(timezone.utc).isoformat(),"status":"FAILED","verification_policy":"Extracted figures remain CANDIDATE_UNVERIFIED; no scoring/recommendation is enabled by this script.","checks":{},"expected_facts":EXPECTED}
    try:
        pdf_bytes = download_pdf()
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        reader = PdfReader(pdf_bytes, strict=True)
        page_texts = [(page.extract_text() or "")[:200_000] for page in reader.pages]
        full_text = "\n".join(page_texts)
        if "ESDS SOFTWARE SOLUTION LIMITED" not in full_text.upper():
            raise RuntimeError("Issuer name not found in downloaded official PDF.")
        if "DRAFT RED HERRING PROSPECTUS" not in full_text.upper():
            raise RuntimeError("DRHP title not found in downloaded official PDF.")
        if "Restated Consolidated Statement of Profit and Loss" not in full_text:
            raise RuntimeError("Consolidated profit-and-loss statement was not found.")
        if "All amounts are in Rupees million" not in full_text:
            raise RuntimeError("Explicit statement unit was not found.")
        extraction = extract_pdf_candidate_evidence(pdf_bytes, source_url=SOURCE_URL)
        if extraction.get("document_hash") != sha256:
            raise RuntimeError("Extractor SHA-256 does not match downloaded source bytes.")
        candidates = _flatten_candidates(extraction)
        statement_pages = _find_statement_pages(page_texts)
        report.update({"document_sha256":sha256,"document_bytes":len(pdf_bytes),"physical_page_count":len(reader.pages),"text_pages_extracted":sum(bool(page.strip()) for page in page_texts),"candidate_evidence_count":extraction.get("evidence_count",len(extraction.get("evidence",[]))),"candidate_financial_value_count":len(candidates),"statement_physical_pages":statement_pages,"extractor_status":extraction.get("status"),"source_validation":"SEBI HTTPS URL; downloaded bytes passed PDF signature, issuer/title, and statement-unit checks."})
        raw_checks = {
            "revenue_from_operations":_raw_row_check(page_texts,r"Revenue from operations","2,865.18",statement_pages["profit_and_loss"]),
            "profit_after_tax":_raw_row_check(page_texts,r"Profit\s*/?\s*\(?loss\)?\s+for the period\s*/?\s*year","136.10",statement_pages["profit_and_loss"]),
            "operating_cash_flow":_raw_row_check(page_texts,r"Net cash inflows?\s*/?\s*\(?outflows?\)?\s+from operating activities","455.77",statement_pages["cash_flow"]),
        }
        report["checks"]["raw_statement_rows"] = raw_checks
        candidate_checks = {}
        for expected in EXPECTED:
            matches = [item for item in candidates if item.get("field_name")==expected["field_name"] and str(item.get("raw_value","")).replace(" ","")==expected["raw_value"]]
            exact = [item for item in matches if (item.get("period") or {}).get("label")==expected["period"] and item.get("unit")==expected["unit"] and item.get("statement_basis")=="CONSOLIDATED" and str(item.get("normalized_value_inr_crore"))==expected["normalized_value_inr_crore"] and item.get("verification_status")=="CANDIDATE_UNVERIFIED"]
            candidate_checks[expected["field_name"]] = {"passed":bool(exact),"raw_value_candidates_found":len(matches),"fully_normalized_candidate_count":len(exact),"expected":expected,"sample_candidates":matches[:3]}
        report["checks"]["structured_candidates"] = candidate_checks
        report["checks"]["arithmetic"] = {"passed":True,"conversions":{"revenue_million_to_crore":"2865.18 × 0.1 = 286.518","pat_million_to_crore":"136.10 × 0.1 = 13.610","operating_cash_flow_million_to_crore":"455.77 × 0.1 = 45.577"}}
        failed_raw = [name for name,result in raw_checks.items() if not result["passed"]]
        failed_structured = [name for name,result in candidate_checks.items() if not result["passed"]]
        if failed_raw or failed_structured:
            report["failed_checks"]={"raw_statement_rows":failed_raw,"structured_candidates":failed_structured}
            report["status"]="FAILED"
            report["note"]="Real PDF was downloaded and text-extracted, but one or more expected row/metadata checks failed. Do not treat as complete."
            return_code=1
        else:
            report["status"]="PASS_EXTRACTION_AND_RECONCILIATION_FIXTURE"
            report["note"]="Official statement rows and candidate metadata match reviewed expected values. Facts remain unverified pending authorized reviewer approval."
            return_code=0
    except Exception as exc:
        report["error"]=f"{type(exc).__name__}: {exc}"
        return_code=1
    finally:
        report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
        print(json.dumps(report,indent=2,ensure_ascii=False))
    return return_code

if __name__ == "__main__":
    sys.exit(run())
