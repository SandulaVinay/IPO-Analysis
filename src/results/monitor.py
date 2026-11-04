"""Official NSE financial-results filing monitor with conservative XBRL extraction.

The monitor reports only values found in a source filing. It never infers financial
performance from a filing title and never emits a buy/sell recommendation.
"""
import asyncio
from io import BytesIO
import hashlib
import time
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
import requests
from pypdf import PdfReader
from bs4 import BeautifulSoup

from src.common.config import settings
from src.common.logging import logger
from src.discovery.normalizer import Normalizer
from src.ingestion.client import http_client
from src.notifications.email import EmailProvider
from src.notifications.whatsapp import WhatsAppProvider
from src.state.store import StateStore
from src.reporting.pdf import markdown_to_pdf
from src.results.email_analysis import build_results_email
from src.results.email_html import results_email_html
from src.results.document_extractors import (
    MAX_DOCUMENT_BYTES,
    detect_document_format,
    extract_document,
    extract_financial_metrics_from_tables,
    infer_xbrl_reporting_period,
)

NSE_ROOT_URL = "https://www.nseindia.com/"
NSE_RESULTS_URL = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"
NSE_RESULTS_API_URL = "https://www.nseindia.com/api/corporates-financial-results"
BSE_RESULTS_API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_RESULTS_PAGE_URL = "https://www.bseindia.com/corporates/ann"
BSE_ATTACHMENT_BASE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
CRORE = 10_000_000

METRIC_TAGS = {
    "revenue_cr": [
        "RevenueFromOperations",
        "RevenueFromOperationsIncludingExciseDuty",
        "RevenueFromOperationsExcludingOtherIncome",
        "RevenueFromOperationsFromContinuingOperations",
    ],
    "pat_cr": [
        "ProfitLossForPeriod",
        "ProfitLossForPeriodAttributableToOwnersOfParent",
        "ProfitLossFromContinuingOperations",
        "ProfitLoss",
    ],
    "eps": ["EarningsPerShareBasic", "EarningsPerShareDiluted"],
    "cfo_cr": [
        "CashFlowsFromUsedInOperatingActivities",
        "NetCashFlowsFromUsedInOperatingActivities",
        "CashGeneratedFromUsedInOperatingActivities",
    ],
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def is_official_attachment_url(url: str, exchange: str) -> bool:
    """Accept only HTTPS attachment URLs hosted by the selected official exchange."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not host:
        return False
    exchange_name = str(exchange or "").upper()
    if exchange_name not in {"BSE", "NSE"}:
        return False
    official_domain = "bseindia.com" if exchange_name == "BSE" else "nseindia.com"
    return host == official_domain or host.endswith("." + official_domain)


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _matches_watchlist_company(filing: Dict[str, Any], company: Dict[str, Any]) -> bool:
    """Match only an explicitly configured issuer name/alias; never infer symbol from a page-wide table."""
    expected = [company.get("company_name"), *(company.get("company_name_aliases") or [])]
    expected_keys = {_key(value) for value in expected if isinstance(value, str) and value.strip()}
    return bool(expected_keys and _key(str(filing.get("company_name", ""))) in expected_keys)


def parse_result_lookback_hours(value: Any, default: int = 72) -> int:
    """Parse a bounded workflow lookback value without crashing module import."""
    try:
        hours = int(str(value).strip())
    except (TypeError, ValueError):
        hours = default
    return min(720, max(1, hours))


RESULT_LOOKBACK_HOURS = parse_result_lookback_hours(os.getenv("RESULT_LOOKBACK_HOURS", "72"))
IST = ZoneInfo("Asia/Kolkata")


def _parse_broadcast_datetime(value: Any) -> Optional[datetime]:
    """Parse an exchange announcement timestamp; unparseable timestamps are not treated as recent."""
    if not value:
        return None
    raw = _clean(str(value))
    if raw.lower() in {"-", "--", "—", "n/a", "na", "null", "none", "not available", "not provided by nse", "not provided by bse"} or raw.lower().startswith("not provided"):
        return None
    normalized = raw.replace(" UTC", "+00:00").replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)
    except ValueError:
        pass

    for fmt in (
        "%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M",
        "%d-%b-%y %H:%M:%S", "%d-%b-%y %H:%M",
        "%d %b %Y %H:%M:%S", "%d %b %Y %H:%M",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%d-%b-%Y", "%d %b %Y", "%d/%m/%Y", "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def _is_recent_filing(item: Dict[str, Any], *, now: datetime) -> bool:
    """Keep only filings announced within the configured rolling lookback window."""
    announced_at = _parse_broadcast_datetime(item.get("broadcast_time"))
    if announced_at is None:
        logger.warning(
            "Skipping %s filing because exchange announcement time could not be parsed: %s",
            item.get("symbol", "UNKNOWN"),
            item.get("broadcast_time", "missing"),
        )
        return False
    cutoff = now - timedelta(hours=RESULT_LOOKBACK_HOURS)
    if announced_at > now + timedelta(minutes=15):
        logger.warning("Skipping %s filing with a future announcement timestamp.", item.get("symbol", "UNKNOWN"))
        return False
    return cutoff <= announced_at <= now


def parse_nse_financial_results_payload(
    payload: Any,
    symbol: str,
    company: Dict[str, Any],
    period_type: str,
) -> List[Dict[str, Any]]:
    """Normalize NSE's JSON financial-results feed using exact symbol and issuer-name checks."""
    if isinstance(payload, dict):
        rows = payload.get("data")
        if rows is None:
            rows = payload.get("results")
    else:
        rows = payload
    if not isinstance(rows, list):
        raise ValueError("NSE financial-results API response was not a list of filings.")

    output: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_symbol = str(row.get("symbol") or row.get("Symbol") or "").strip().upper()
        if row_symbol != symbol.strip().upper():
            continue

        company_name = _clean(str(row.get("companyName") or row.get("company_name") or ""))
        if not company_name or not _matches_watchlist_company({"company_name": company_name}, company):
            continue

        period_ended = _clean(str(row.get("toDate") or row.get("periodEnded") or ""))
        # Exchange feeds may provide "-" in the first timestamp field while a
        # later fallback field contains the actual announcement time.
        broadcast = next(
            (
                value for value in (
                    row.get("broadCastDate"),
                    row.get("broadcastDate"),
                    row.get("filingDate"),
                    row.get("broadcast_time"),
                )
                if (
                    _clean(str(value or "")).lower() not in {"", "-", "--", "—", "n/a", "na", "null", "none"}
                    and not _clean(str(value or "")).lower().startswith("not provided")
                )
            ),
            "",
        )
        broadcast = _clean(str(broadcast))
        relating = _clean(str(row.get("relatingTo") or row.get("relating_to") or period_type))
        xbrl_value = str(row.get("xbrl") or row.get("xbrlUrl") or "").strip()
        details_value = str(row.get("resultDetailedDataLink") or row.get("detailsUrl") or "").strip()
        xbrl_url = urljoin(NSE_RESULTS_URL, xbrl_value) if xbrl_value else None
        details_url = urljoin(NSE_RESULTS_URL, details_value) if details_value else None
        attachment = xbrl_url or details_url
        attachments = []
        for candidate in (xbrl_url, details_url):
            if candidate and all(entry["url"] != candidate for entry in attachments):
                attachments.append({"url": candidate, "label": "XBRL" if candidate == xbrl_url else "Details"})
        event_material = "|".join([
            row_symbol, period_ended, relating, broadcast,
            str(row.get("consolidated") or ""), str(row.get("format") or ""),
            attachment or NSE_RESULTS_URL,
        ])
        event_key = "RESULT_" + hashlib.sha256(event_material.encode("utf-8")).hexdigest()[:32]
        if event_key in seen:
            continue
        seen.add(event_key)
        output.append({
            "event_key": event_key,
            "symbol": row_symbol,
            "exchange": "NSE",
            "company_name": company_name,
            "period_ended": period_ended or None,
            "relating_to": relating,
            "broadcast_time": broadcast or "Not provided by NSE",
            "audit_status": _clean(str(row.get("audited") or "")),
            "cumulative_status": _clean(str(row.get("cumulative") or "")),
            "period_type": _clean(str(row.get("period") or period_type)),
            "submission_type": _clean(str(row.get("format") or row.get("oldNewFlag") or "")),
            "consolidation": _clean(str(row.get("consolidated") or "")),
            "source_url": NSE_RESULTS_URL,
            "attachment_url": attachment,
            "attachments": attachments,
            "xbrl_url": xbrl_url,
            "details_url": details_url,
        })
    return output


def bse_api_headers() -> Dict[str, str]:
    """Return the browser fingerprint measured to pass BSE's Akamai gate."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.5",
        "Origin": "https://www.bseindia.com",
        "Referer": BSE_RESULTS_PAGE_URL,
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "sec-ch-ua": '"Chromium";v="153", "Not(A:Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        # Accept-Encoding is intentionally left to requests.Session; BSE's
        # Akamai rule has been observed to reject clients omitting that header.
    }


def bse_results_request_params(page_no: int, scrip_code: str, from_date, to_date) -> Dict[str, Any]:
    """Build the BSE financial-results query using its exact public parameter names."""
    return {
        "pageno": page_no,
        "strCat": "Result",
        "subcategory": "-1",
        "strPrevDate": from_date.strftime("%Y%m%d"),
        "strToDate": to_date.strftime("%Y%m%d"),
        "strSearch": "P",
        "strScrip": scrip_code,
        "strType": "C",
    }


def _fetch_bse_results_sync(
    companies: List[Dict[str, Any]],
    today_ist,
) -> tuple[Dict[str, List[Dict[str, Any]]], int]:
    """Fetch BSE result announcements with requests' measured Akamai-compatible transport.

    This blocking helper runs in a worker thread so it does not stall the async
    NSE monitor. A single requests.Session is reused for sequential BSE calls.
    """
    rows_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    errors = 0
    lookback_days = max(7, (RESULT_LOOKBACK_HOURS + 23) // 24 + 1)
    from_date = today_ist - timedelta(days=lookback_days)

    with requests.Session() as session:
        session.headers.update(bse_api_headers())
        for company in companies:
            symbol = str(company.get("symbol") or "").strip().upper()
            scrip_code = str(company.get("bse_scrip_code") or "").strip()
            if not symbol or not company.get("company_name") or not re.fullmatch(r"\d{6}", scrip_code):
                errors += 1
                logger.warning(
                    "Skipping BSE watchlist entry %s: company_name and six-digit bse_scrip_code are required.",
                    symbol or "(missing)",
                )
                continue

            try:
                raw_rows: List[Dict[str, Any]] = []
                for page_no in range(1, 6):
                    params = bse_results_request_params(page_no, scrip_code, from_date, today_ist)
                    payload = None
                    for attempt in range(1, 4):
                        try:
                            response = session.get(
                                BSE_RESULTS_API_URL,
                                params=params,
                                timeout=(15.0, 45.0),
                            )
                            response.raise_for_status()
                            payload = response.json()
                            break
                        except requests.RequestException as exc:
                            status_code = getattr(getattr(exc, "response", None), "status_code", None)
                            retryable = status_code in {403, 408, 425, 429, 500, 502, 503, 504} or status_code is None
                            if attempt < 3 and retryable:
                                delay = 3.0 * attempt
                                logger.warning(
                                    "BSE results request for %s failed (HTTP %s; %s); retrying in %.0fs.",
                                    symbol,
                                    status_code if status_code is not None else "n/a",
                                    type(exc).__name__,
                                    delay,
                                )
                                time.sleep(delay)
                                continue
                            raise

                    if not isinstance(payload, dict) or not isinstance(payload.get("Table"), list):
                        raise ValueError("BSE results API response did not contain a Table list.")
                    page_rows = payload["Table"]
                    raw_rows.extend(row for row in page_rows if isinstance(row, dict))
                    total_rows = 0
                    table1 = payload.get("Table1")
                    if isinstance(table1, list) and table1 and isinstance(table1[0], dict):
                        try:
                            total_rows = int(table1[0].get("ROWCNT") or 0)
                        except (TypeError, ValueError):
                            total_rows = 0
                    if not page_rows or (total_rows and len(raw_rows) >= total_rows) or len(page_rows) < 50:
                        break

                rows_by_symbol[symbol] = parse_bse_financial_results_payload(
                    {"Table": raw_rows}, symbol, company, scrip_code
                )
                logger.info(
                    "BSE announcement feed checked for %s (scrip %s); exact results announcements matched=%s.",
                    symbol,
                    scrip_code,
                    len(rows_by_symbol[symbol]),
                )
            except Exception as exc:
                errors += 1
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                logger.warning(
                    "BSE results API failed for %s after retries (HTTP %s; %s).",
                    symbol,
                    status_code if status_code is not None else "n/a",
                    type(exc).__name__,
                )
                rows_by_symbol[symbol] = []

    return rows_by_symbol, errors


def has_recognized_financial_results_table(html: str) -> bool:
    """Return True only when the NSE response contains the expected filing columns."""
    soup = BeautifulSoup(html, "lxml")
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if not first_row:
            continue
        headers = [_key(cell.get_text(" ", strip=True)) for cell in first_row.find_all(["th", "td"])]
        company_ok = any("company name" in header or header == "company" for header in headers)
        period_ok = any("period ended" in header or "period end" in header for header in headers)
        broadcast_ok = any("broadcast date" in header or "broadcast time" in header for header in headers)
        if company_ok and period_ok and broadcast_ok:
            return True
    return False


def parse_financial_results_page(html: str, symbol: str, page_url: str) -> List[Dict[str, Any]]:
    """Extract filing metadata and attachment links from the official NSE results table."""
    soup = BeautifulSoup(html, "lxml")
    output = []
    seen = set()
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if not first_row:
            continue
        headers = [_key(cell.get_text(" ", strip=True)) for cell in first_row.find_all(["th", "td"])]
        if not headers:
            continue

        def index_for(*aliases):
            return next((i for i, header in enumerate(headers) if any(alias in header for alias in aliases)), None)

        company_i = index_for("company name", "company")
        period_i = index_for("period ended", "period end")
        relating_i = index_for("relating to", "relating")
        broadcast_i = index_for("broadcast date", "broadcast")
        audit_i = index_for("audited unaudited", "audited")
        cumulative_i = index_for("cumulative non cumulative", "cumulative")
        consolidation_i = index_for("consolidated non consolidated", "consolidated")
        period_type_i = index_for("period")
        submission_i = index_for("type of submission", "submission")
        if period_i is None or broadcast_i is None:
            continue

        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all(["td", "th"])
            if max(period_i, broadcast_i) >= len(cells):
                continue
            period_end = _clean(cells[period_i].get_text(" ", strip=True))
            broadcast = _clean(cells[broadcast_i].get_text(" ", strip=True))
            if not period_end or not broadcast:
                continue
            company = _clean(cells[company_i].get_text(" ", strip=True)) if company_i is not None and company_i < len(cells) else ""
            relating = _clean(cells[relating_i].get_text(" ", strip=True)) if relating_i is not None and relating_i < len(cells) else ""
            audit = _clean(cells[audit_i].get_text(" ", strip=True)) if audit_i is not None and audit_i < len(cells) else ""
            cumulative = _clean(cells[cumulative_i].get_text(" ", strip=True)) if cumulative_i is not None and cumulative_i < len(cells) else ""
            consolidation = _clean(cells[consolidation_i].get_text(" ", strip=True)) if consolidation_i is not None and consolidation_i < len(cells) else ""
            period_type = _clean(cells[period_type_i].get_text(" ", strip=True)) if period_type_i is not None and period_type_i < len(cells) else ""
            submission_type = _clean(cells[submission_i].get_text(" ", strip=True)) if submission_i is not None and submission_i < len(cells) else ""
            links = []
            for anchor in tr.find_all("a", href=True):
                href = urljoin(page_url, anchor["href"].strip())
                label = _clean(anchor.get_text(" ", strip=True))
                if href.startswith("https://") and all(item["url"] != href for item in links):
                    links.append({"url": href, "label": label})
            xbrl_attachment = next((
                item["url"] for item in links
                if "xbrl" in item["label"].lower()
                or any(ext in item["url"].lower() for ext in (".xml", ".xbrl"))
                or "/xbrl/" in item["url"].lower()
            ), None)
            supported_extensions = (".xml", ".xbrl", ".html", ".htm", ".pdf", ".csv", ".tsv", ".xlsx", ".xlsm", ".xls")
            document_links = [
                link for link in links
                if link["url"].lower().split("?")[0].endswith(supported_extensions)
                or "details" in link["label"].lower()
            ]
            rank = lambda link: (
                0 if link["url"] == xbrl_attachment else
                1 if link["url"].lower().split("?")[0].endswith((".html", ".htm", ".csv", ".tsv", ".xlsx", ".xlsm", ".xls")) else
                2 if link["url"].lower().split("?")[0].endswith(".pdf") else 3
            )
            document_links.sort(key=rank)
            details_attachment = next((link["url"] for link in document_links if link["url"] != xbrl_attachment), None)
            attachment = xbrl_attachment or (document_links[0]["url"] if document_links else None)
            event_material = "|".join([symbol.upper(), period_end, relating, broadcast, consolidation, attachment or page_url])
            event_key = "RESULT_" + hashlib.sha256(event_material.encode("utf-8")).hexdigest()[:32]
            if event_key in seen:
                continue
            seen.add(event_key)
            output.append({
                "event_key": event_key,
                "symbol": symbol.upper(),
                "company_name": company or symbol.upper(),
                "period_ended": period_end,
                "relating_to": relating,
                "broadcast_time": broadcast,
                "audit_status": audit,
                "cumulative_status": cumulative,
                "period_type": period_type,
                "submission_type": submission_type,
                "consolidation": consolidation,
                "source_url": page_url,
                "attachment_url": attachment,
                "attachments": document_links,
                "xbrl_url": xbrl_attachment,
                "details_url": details_attachment,
            })
    return output


def extract_xbrl_metrics(xml_content: bytes, period_ended: str, relating_to: str = "") -> Dict[str, Any]:
    """Extract a conservative subset of quarterly/annual metrics from an XBRL instance."""
    if len(xml_content) > 10_000_000:
        raise ValueError("XBRL attachment exceeds the 10 MB safety limit.")
    xml_upper = xml_content.upper()
    if b"<!DOCTYPE" in xml_upper or b"<!ENTITY" in xml_upper:
        raise ValueError("XBRL document contains a prohibited DTD/entity declaration.")

    root = ET.fromstring(xml_content)
    contexts: Dict[str, Dict[str, Any]] = {}
    units: Dict[str, str] = {}

    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    for node in root.iter():
        name = local_name(node.tag)
        if name == "context":
            context_id = node.attrib.get("id")
            if not context_id:
                continue
            start_value = next((child.text for child in node.iter() if local_name(child.tag) == "startdate" and child.text), None)
            end_value = next((child.text for child in node.iter() if local_name(child.tag) in {"enddate", "instant"} and child.text), None)
            dimensioned = any(local_name(child.tag) in {"explicitmember", "typedmember"} for child in node.iter())
            start_date = Normalizer.parse_date(start_value)
            end_date = Normalizer.parse_date(end_value)
            duration = (end_date - start_date).days + 1 if start_date and end_date else 0
            contexts[context_id] = {
                "start": start_date,
                "end": end_date,
                "duration": duration,
                "dimensioned": dimensioned,
            }
        elif name == "unit":
            unit_id = node.attrib.get("id")
            if unit_id:
                units[unit_id] = " ".join((child.text or "") for child in node.iter() if local_name(child.tag) == "measure").lower()

    target = Normalizer.parse_date(period_ended)
    if target is None:
        return {"status": "UNAVAILABLE", "reason": "Period end date could not be parsed."}
    try:
        prior_target = target.replace(year=target.year - 1)
    except ValueError:
        prior_target = target.replace(year=target.year - 1, day=28)

    is_quarter = "quarter" in (relating_to or "").lower()
    min_days, max_days = (60, 125) if is_quarter else (300, 400)
    values: Dict[str, Dict[str, Any]] = {"current": {}, "prior_year": {}}
    priorities: Dict[str, Dict[str, int]] = {"current": {}, "prior_year": {}}

    for node in root.iter():
        tag = local_name(node.tag)
        context_ref = node.attrib.get("contextRef")
        unit_ref = node.attrib.get("unitRef")
        if not context_ref or context_ref not in contexts or not node.text:
            continue
        context = contexts[context_ref]
        if context["dimensioned"] or not (min_days <= context["duration"] <= max_days):
            continue
        if context["end"] == target:
            period_key = "current"
        elif context["end"] == prior_target:
            period_key = "prior_year"
        else:
            continue
        try:
            numeric = float(node.text.strip().replace(",", ""))
        except (ValueError, AttributeError):
            continue

        for metric, aliases in METRIC_TAGS.items():
            normalized_aliases = [alias.lower() for alias in aliases]
            if tag not in normalized_aliases:
                continue
            priority = normalized_aliases.index(tag)
            unit_name = units.get(unit_ref or "", "")
            if metric == "eps" and "inr" not in unit_name:
                continue
            if metric != "eps":
                if "inr" not in unit_name:
                    continue
                numeric = numeric / CRORE
            if metric not in priorities[period_key] or priority < priorities[period_key][metric]:
                values[period_key][metric] = numeric
                priorities[period_key][metric] = priority

    current = values["current"]
    prior = values["prior_year"]
    result: Dict[str, Any] = {
        "status": "EXTRACTED" if current else "UNAVAILABLE",
        "period_ended": target.isoformat(),
        "revenue_cr": current.get("revenue_cr"),
        "pat_cr": current.get("pat_cr"),
        "eps": current.get("eps"),
        "cfo_cr": current.get("cfo_cr"),
        "prior_year_revenue_cr": prior.get("revenue_cr"),
        "prior_year_pat_cr": prior.get("pat_cr"),
    }
    for metric, current_key, prior_key in (
        ("revenue_yoy_pct", "revenue_cr", "revenue_cr"),
        ("pat_yoy_pct", "pat_cr", "pat_cr"),
    ):
        previous = prior.get(prior_key)
        now = current.get(current_key)
        result[metric] = round((now - previous) / abs(previous) * 100, 2) if now is not None and previous not in (None, 0) else None
    if not current:
        result["reason"] = "No matching non-dimensional XBRL facts were found for the selected period."
    return result


def parse_bse_financial_results_payload(
    payload: Dict[str, Any],
    symbol: str,
    company: Dict[str, Any],
    scrip_code: str,
) -> List[Dict[str, Any]]:
    """Normalize BSE result-category announcements for a precisely matched watchlist issuer."""
    if not isinstance(payload, dict) or not isinstance(payload.get("Table"), list):
        raise ValueError("BSE results API response did not contain a Table list.")

    output: List[Dict[str, Any]] = []
    for row in payload["Table"]:
        if not isinstance(row, dict):
            continue
        row_code = str(row.get("SCRIP_CD") or row.get("SCRIPCODE") or "").strip()
        # The source query is filtered by scrip code, but still verify every row
        # carries that exact identifier before matching the issuer name.
        if row_code != str(scrip_code):
            continue

        company_name = _clean(str(row.get("SLONGNAME") or row.get("COMPANYNAME") or ""))
        if not company_name or not _matches_watchlist_company({"company_name": company_name}, company):
            continue

        headline = _clean(str(row.get("NEWSSUB") or row.get("HEADLINE") or ""))
        category = _clean(str(row.get("SUBCATNAME") or row.get("CATEGORYNAME") or ""))
        if "result" not in f"{category} {headline}".lower():
            continue
        if not headline:
            headline = "Financial results filing"
        if not category:
            category = "Financial results"
        broadcast = next(
            (
                value for value in (
                    row.get("DT_TM"),
                    row.get("NEWS_DT"),
                    row.get("News_submission_dt"),
                    row.get("NEWS_DT_TIME"),
                )
                if _clean(str(value or "")).lower() not in {"", "-", "--", "—", "n/a", "na", "null", "none"}
            ),
            "",
        )
        broadcast = _clean(str(broadcast))
        news_id = str(row.get("NEWSID") or row.get("XML_NAME") or "").strip()
        attachment_name = str(row.get("ATTACHMENTNAME") or "").strip()
        attachment_url = None
        if attachment_name:
            attachment_url = attachment_name if attachment_name.lower().startswith("https://") else urljoin(
                BSE_ATTACHMENT_BASE_URL, attachment_name.lstrip("/")
            )

        source_url = str(row.get("NSURL") or BSE_RESULTS_PAGE_URL).strip()
        if not source_url.startswith("https://"):
            source_url = BSE_RESULTS_PAGE_URL
        event_material = "|".join([
            str(scrip_code), news_id, broadcast, headline, attachment_url or source_url
        ])
        event_key = "RESULT_" + hashlib.sha256(event_material.encode("utf-8")).hexdigest()[:32]
        output.append({
            "event_key": event_key,
            "symbol": symbol.upper(),
            "exchange": "BSE",
            "company_name": company_name,
            "period_ended": None,
            "relating_to": category,
            "broadcast_time": broadcast or "Not provided by BSE",
            "audit_status": None,
            "cumulative_status": None,
            "period_type": None,
            "submission_type": None,
            "consolidation": None,
            "source_url": source_url,
            "attachment_url": attachment_url,
            "attachments": ([{"url": attachment_url, "label": "BSE results attachment"}] if attachment_url else []),
            "xbrl_url": None,
            "details_url": None,
            "headline": headline,
            "bse_scrip_code": str(scrip_code),
        })
    return output


def _format_metric(value: Optional[float], suffix: str = "") -> str:
    return "Not available" if value is None else f"{value:,.2f}{suffix}"


def extract_pdf_text(pdf_content: bytes, *, max_pages: int = 12, max_chars: int = 12000) -> Dict[str, Any]:
    """Extract a bounded, page-labelled text excerpt from a filing PDF.

    This is source transcription for review, not financial metric extraction. It
    deliberately does not interpret tables or infer financial values.
    """
    if not pdf_content:
        return {"status": "UNAVAILABLE", "reason": "The PDF attachment was empty."}
    if len(pdf_content) > 15_000_000:
        return {"status": "UNAVAILABLE", "reason": "The PDF exceeds the 15 MB extraction safety limit."}
    if not pdf_content.startswith(b"%PDF-"):
        return {"status": "UNAVAILABLE", "reason": "The attachment did not have a PDF signature."}
    try:
        reader = PdfReader(BytesIO(pdf_content), strict=False)
        pages = []
        chars_left = max_chars
        for index, page in enumerate(reader.pages[:max_pages], start=1):
            if chars_left <= 0:
                break
            try:
                page_text = _clean(page.extract_text() or "")
            except Exception:
                page_text = ""
            if not page_text:
                continue
            excerpt = page_text[:chars_left]
            pages.append(f"[Page {index}]\n{excerpt}")
            chars_left -= len(excerpt)
        if not pages:
            return {
                "status": "UNAVAILABLE",
                "reason": "No selectable text was found; the PDF may be scanned or image-only.",
            }
        return {
            "status": "EXTRACTED",
            "text": "\n\n".join(pages),
            "pages_extracted": len(pages),
            "truncated": len(reader.pages) > max_pages or chars_left <= 0,
        }
    except Exception as exc:
        return {
            "status": "UNAVAILABLE",
            "reason": f"PDF text extraction failed ({type(exc).__name__}).",
        }



def extract_pdf_financial_metrics(document_text: Dict[str, Any], period_ended: str, relating_to: str = "") -> Dict[str, Any]:
    """Extract explicitly labelled rows from a supported INR-lakh PDF statement."""
    if document_text.get("status") != "EXTRACTED":
        return {"status": "UNAVAILABLE", "reason": "Readable PDF text is unavailable."}
    source = str(document_text.get("text") or "")
    if not re.search(r"(?:rs\.?|inr|₹)\s*in\s*lakhs", source, re.IGNORECASE):
        return {"status": "UNAVAILABLE", "reason": "PDF table unit is not explicitly identified as INR lakhs."}
    target = Normalizer.parse_date(period_ended)
    if target is None:
        return {"status": "UNAVAILABLE", "reason": "PDF reporting period could not be parsed."}
    date_ok = (
        target.strftime("%d.%m.%Y") in source
        or target.strftime("%d-%m-%Y") in source
        or target.strftime("%d-%b-%Y").lower() in source.lower()
        or target.strftime("%d %B %Y").lower() in source.lower()
        or target.strftime("%d %b %Y").lower() in source.lower()
        or (target.strftime("%d") in source and target.strftime("%B").lower() in source.lower() and target.strftime("%Y") in source)
    )
    if not date_ok:
        return {"status": "UNAVAILABLE", "reason": "Target reporting date not confirmed inside the PDF."}

    flat = re.sub(r"\s+", " ", source)
    # Require exactly six labelled cells, permitting whitespace/newline differences between cells.
    number = r"\(?-?\d[\d,]*(?:\.\d+)?\)?|-"

    def row_values(label_pattern: str) -> Optional[List[float]]:
        label_match = re.search(label_pattern, flat, re.IGNORECASE)
        if not label_match:
            return None
        tail = flat[label_match.end():label_match.end() + 180]
        tokens = re.findall(number, tail)
        if len(tokens) < 6:
            return None
        # Do not take cells after another textual label; capture only the first six tokens
        # if there is no alphabetic content between them (the header labels may be before row).
        first_six = tokens[:6]
        try:
            return [0.0 if token == "-" else float(token.replace(",", "").replace("(", "-").replace(")", "")) for token in first_six]
        except ValueError:
            return None

    revenue = row_values(r"Revenue from operations")
    pat = row_values(r"Net Profit\s*/\s*\(loss\)\s+for the period")
    eps = row_values(r"Basic\s*\(Amount in Rs\.\)")
    if revenue is None or pat is None:
        return {"status": "UNAVAILABLE", "reason": "Required labelled revenue/PAT rows could not be mapped to six numeric cells."}

    rev_now, rev_q_prev, rev_y_prev = revenue[:3]
    pat_now, pat_q_prev, pat_y_prev = pat[:3]
    result: Dict[str, Any] = {
        "status": "EXTRACTED",
        "extraction_method": "PDF_LABELLED_TABLE",
        "unit": "INR_LAKHS",
        "period_ended": target.isoformat(),
        "period_type": "QUARTER_AND_HALF_YEAR",
        "revenue_lakh": rev_now,
        "revenue_cr": round(rev_now / 100, 4),
        "pat_lakh": pat_now,
        "pat_cr": round(pat_now / 100, 4),
        "revenue_yoy_pct": round((rev_now - rev_y_prev) / abs(rev_y_prev) * 100, 2) if rev_y_prev else None,
        "pat_yoy_pct": round((pat_now - pat_y_prev) / abs(pat_y_prev) * 100, 2) if pat_y_prev else None,
        "revenue_qoq_pct": round((rev_now - rev_q_prev) / abs(rev_q_prev) * 100, 2) if rev_q_prev else None,
        "pat_qoq_pct": round((pat_now - pat_q_prev) / abs(pat_q_prev) * 100, 2) if pat_q_prev else None,
        "reason": "Quarterly figures transcribed from labelled PDF rows; verify against the original filing.",
    }
    if eps:
        result["eps"] = eps[0]
    return result


async def _extract_official_attachment(
    item: Dict[str, Any],
    attachment_urls: List[str],
) -> tuple[Dict[str, Any], Optional[Dict[str, Any]], List[str]]:
    """Try every official attachment in preference order; keep extracted values unverified."""
    exchange = str(item.get("exchange") or "NSE").upper()
    metrics: Dict[str, Any] = {
        "status": "UNAVAILABLE",
        "reason": "No supported official financial-results attachment was detected.",
    }
    document_info: Optional[Dict[str, Any]] = None
    failures: List[str] = []
    seen = set()
    for attachment_url in attachment_urls:
        attachment_url = str(attachment_url or "").strip()
        if not attachment_url or attachment_url in seen:
            continue
        seen.add(attachment_url)
        try:
            if not is_official_attachment_url(attachment_url, exchange):
                raise ValueError("Attachment URL is not an approved official exchange HTTPS URL.")
            response = await http_client.get(
                attachment_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/156.0.0.0 Safari/537.36",
                    "Accept": "application/pdf,application/xml,text/xml,text/html,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": BSE_RESULTS_PAGE_URL if exchange == "BSE" else NSE_RESULTS_URL,
                },
                timeout=45.0,
            )
            response.raise_for_status()
            final_url = str(getattr(response, "url", attachment_url) or attachment_url)
            if not is_official_attachment_url(final_url, exchange):
                raise ValueError("Attachment redirected outside the approved exchange domain.")
            content = bytes(response.content or b"")
            if len(content) > MAX_DOCUMENT_BYTES:
                raise ValueError("Attachment exceeds the 15 MB safety limit.")
            headers = getattr(response, "headers", {}) or {}
            content_type = str(headers.get("content-type", ""))
            document = extract_document(content, content_type, final_url)
            document["source_url"] = final_url
            document_info = document
            document_format = document.get("format") or detect_document_format(content, content_type, final_url)
            if document.get("status") != "EXTRACTED":
                metrics = {"status": "UNAVAILABLE", "reason": document.get("reason", "Attachment could not be parsed."), "format": document_format}
                failures.append(f"{document_format}:unavailable")
                continue

            if document_format in {"xbrl_xml", "ixbrl"}:
                xbrl_xml = document.get("xbrl_xml") or content
                parse_item = dict(item)
                period_provenance = "EXCHANGE_ANNOUNCEMENT"
                if not parse_item.get("period_ended"):
                    inferred_period = infer_xbrl_reporting_period(xbrl_xml, item)
                    if inferred_period is None:
                        parsed_metrics = {
                            "status": "UNAVAILABLE",
                            "reason": "Filing period end is missing and XBRL contexts do not identify one unambiguous quarterly or annual period.",
                        }
                    else:
                        period_date, period_kind = inferred_period
                        parse_item["period_ended"] = period_date.isoformat()
                        parse_item["period_type"] = "Annual" if period_kind == "annual" else "Quarterly"
                        period_provenance = "XBRL_CONTEXT"
                        parsed_metrics = extract_xbrl_metrics(
                            xbrl_xml,
                            parse_item["period_ended"],
                            parse_item.get("relating_to") or parse_item.get("period_type") or "",
                        )
                else:
                    parsed_metrics = extract_xbrl_metrics(
                        xbrl_xml,
                        parse_item["period_ended"],
                        parse_item.get("relating_to") or parse_item.get("period_type") or "",
                    )
                if parsed_metrics.get("status") == "EXTRACTED":
                    parsed_metrics.update({
                        "source_status": "CANDIDATE_UNVERIFIED",
                        "assessment_eligible": False,
                        "extraction_method": "IXBRL" if document_format == "ixbrl" else "XBRL",
                        "statement_basis": item.get("consolidation") or "UNRESOLVED",
                        "unit": "INR (XBRL instance unit)",
                        "period_type": parse_item.get("period_type") or item.get("period_type"),
                        "period_provenance": period_provenance,
                    })
                metrics = parsed_metrics
            else:
                document_text = str(document.get("text") or "")
                parsed_metrics = extract_financial_metrics_from_tables(
                    document.get("tables") or [],
                    document_text=document_text,
                    item=item,
                    document_format=document_format,
                )
                if document_format == "pdf" and parsed_metrics.get("status") != "EXTRACTED":
                    excerpt = extract_pdf_text(content)
                    legacy_metrics = extract_pdf_financial_metrics(
                        excerpt,
                        str(item.get("period_ended") or ""),
                        str(item.get("relating_to") or item.get("headline") or ""),
                    ) if item.get("period_ended") else {"status": "UNAVAILABLE"}
                    if legacy_metrics.get("status") == "EXTRACTED":
                        legacy_metrics.update({
                            "source_status": "CANDIDATE_UNVERIFIED",
                            "assessment_eligible": False,
                            "statement_basis": item.get("consolidation") or "UNRESOLVED",
                        })
                        parsed_metrics = legacy_metrics
                    document["text"] = excerpt.get("text", document_text)
                    document["truncated"] = excerpt.get("truncated", False)
                    document["status"] = excerpt.get("status", document.get("status"))
                    if excerpt.get("status") != "EXTRACTED":
                        document["reason"] = excerpt.get("reason")
                metrics = parsed_metrics
            if metrics.get("status") == "EXTRACTED":
                metrics.setdefault("source_status", "CANDIDATE_UNVERIFIED")
                metrics["assessment_eligible"] = False
                metrics["source_url"] = final_url
                metrics["format"] = document_format
                return metrics, document, failures
            reason = metrics.get("reason") or "Attachment parsed, but the target financial values could not be mapped safely."
            failures.append(f"{document_format}:{reason}")
        except Exception as exc:
            failures.append(type(exc).__name__)
            attachment_host = urlparse(attachment_url).hostname or "unknown-host"
            logger.warning(
                "Financial-results attachment could not be parsed for %s from %s (%s).",
                item.get("symbol", "UNKNOWN"), attachment_host, type(exc).__name__,
            )
    if failures and metrics.get("status") != "EXTRACTED":
        metrics["reason"] = "No attachment yielded safely mapped metrics. " + "; ".join(failures[:3])
    return metrics, document_info, failures


def _report_text(item: Dict[str, Any], metrics: Dict[str, Any], document_text: Optional[Dict[str, Any]] = None) -> str:
    attachment = metrics.get("source_url") or item.get("attachment_url") or item["source_url"]
    if metrics.get("status") == "EXTRACTED":
        analysis = (
            f"- **Revenue from operations:** ₹{_format_metric(metrics.get('revenue_cr'))} Cr\n"
            f"- **Profit after tax (PAT):** ₹{_format_metric(metrics.get('pat_cr'))} Cr\n"
            f"- **EPS:** ₹{_format_metric(metrics.get('eps'))}\n"
            f"- **Operating cash flow:** ₹{_format_metric(metrics.get('cfo_cr'))} Cr\n"
            f"- **Revenue YoY change:** {_format_metric(metrics.get('revenue_yoy_pct'), '%')}\n"
            f"- **PAT YoY change:** {_format_metric(metrics.get('pat_yoy_pct'), '%')}\n"
        )
        if metrics.get("missing_metrics"):
            analysis += f"- **Other required metrics not mapped:** {', '.join(metrics['missing_metrics'])}\n"
        analysis_note = (
            f"These are {metrics.get('source_status', 'CANDIDATE_UNVERIFIED')} values parsed from {metrics.get('extraction_method') or metrics.get('format') or 'the attachment'}. "
            "They have not been independently reconciled and are not eligible for scoring or an Apply/Avoid recommendation."
        )
    else:
        analysis = "- **Automated metrics:** Not available from the detected attachment format.\n"
        analysis_note = "No financial-performance conclusion or investment recommendation is generated from filing metadata alone."
    return (
        f"# Official financial-results filing: {item['company_name']} ({item['symbol']})\n\n"
        f"- **Exchange:** {item.get('exchange') or 'NSE'}\n"
        f"- **Period ended:** {item.get('period_ended') or metrics.get('period_ended') or 'Not specified in the filing notice or attachment header'}\n"
        f"- **Period / quarter:** {item.get('relating_to') or item.get('period_type') or 'Not specified in the table'}\n"
        f"- **Submission period type:** {metrics.get('period_type') or item.get('period_type') or 'Not specified'}\n"
        f"- **Period evidence:** {metrics.get('period_provenance') or 'Exchange announcement'}\n"
        f"- **Metric extraction method:** {metrics.get('extraction_method') or ('XBRL' if metrics.get('status') == 'EXTRACTED' else 'Not available')}\n"
        f"- **Broadcast time:** {item['broadcast_time']}\n"
        f"- **Audited status:** {item.get('audit_status') or 'Not specified'}\n"
        f"- **Statement basis:** {item.get('consolidation') or 'Not specified'}\n"
        f"- **Extracted statement basis:** {metrics.get('statement_basis') or 'Not established'}\n"
        f"- **Verification status:** {metrics.get('source_status') or 'UNAVAILABLE'}\n"
        f"- **Reported unit:** {metrics.get('unit') or 'Not established'}\n"
        f"- **Official source:** {item['source_url']}\n"
        f"- **Filing attachment:** {attachment}\n"
        f"- **Details / PDF attachment:** {item.get('details_url') or 'Not available'}\n"
        f"- **Announcement:** {item.get('headline') or 'Not provided'}\n\n"
        f"## Extracted financial metrics\n\n{analysis}\n{analysis_note}\n"
        + _pdf_text_section(document_text)
    )


def _pdf_text_section(document_text: Optional[Dict[str, Any]]) -> str:
    if not document_text:
        return ""
    if document_text.get("status") != "EXTRACTED":
        return (
            "\n## Source attachment review\n\n"
            f"Text extraction unavailable: {document_text.get('reason', 'No readable PDF text was found.')}\n"
            "The official filing link above remains the authoritative source.\n"
        )
    document_format = str(
        document_text.get("format") or ("pdf" if document_text.get("pages_extracted") else "document")
    ).upper()
    content = str(document_text.get("text") or "")
    if not content and document_text.get("tables"):
        preview_rows = []
        for table in document_text["tables"][:3]:
            preview_rows.append(str(table.get("name") or "Table"))
            preview_rows.extend(" | ".join(str(cell) for cell in row[:12]) for row in (table.get("rows") or [])[:12])
        content = "\n".join(preview_rows)[:6_000]
    if not content:
        return "\n## Source attachment review\n\nThe attachment format was recognized, but no readable text excerpt is available.\n"
    suffix = "\n\n*Excerpt only; verify figures, units, statement basis, and reporting period against the original filing.*"
    if document_text.get("truncated"):
        suffix += " The excerpt was truncated to keep the report readable."
    title = (
        "Source document text (page-labelled excerpt)"
        if document_format == "PDF"
        else f"Source attachment review ({document_format}; excerpt)"
    )
    return f"\n## {title}\n\n````text\n{content[:6_000]}\n````{suffix}\n"


async def monitor_financial_results() -> Dict[str, Any]:
    """Monitor NSE JSON filings and BSE result announcements independently."""
    store = StateStore()
    watchlist = store.load_watchlist()
    if not watchlist:
        store.record_run(command="results", status="SKIPPED", detail="Company watchlist is empty.")
        logger.info("Financial-results monitor skipped because state/watchlist.json has no company symbols.")
        return {"status": "SKIPPED", "watchlist_size": 0, "new_filings": 0, "notifications_accepted": 0}

    report_dir = Path("reports/results")
    report_dir.mkdir(parents=True, exist_ok=True)
    checked = 0
    new_filings = 0
    accepted_count = 0
    notification_failures = 0
    notification_skipped = 0
    documents_unavailable = 0
    errors = 0

    nse_companies = [company for company in watchlist if str(company.get("exchange", "NSE")).upper() == "NSE"]
    bse_companies = [company for company in watchlist if str(company.get("exchange", "NSE")).upper() == "BSE"]
    nse_rows_by_symbol: Dict[str, List[Dict[str, Any]]] = {}

    # Bootstrap through the IPO page first: GitHub runners have received 403
    # from the NSE homepage, while the IPO page is the known-working public landing URL.
    if nse_companies:
        nse_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": NSE_RESULTS_URL,
            "Origin": "https://www.nseindia.com",
            "X-Requested-With": "XMLHttpRequest",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(45.0, connect=15.0),
                follow_redirects=True,
            ) as session:
                landing = await session.get(
                    "https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
                    headers={**nse_headers, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
                )
                landing.raise_for_status()
                # Visit the exact UI page before its JSON feed so any route-specific
                # cookies and anti-CSRF context are retained in the same session.
                results_page = await session.get(
                    NSE_RESULTS_URL,
                    headers={**nse_headers, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
                )
                results_page.raise_for_status()

                for company in nse_companies:
                    symbol = str(company.get("symbol") or "").strip().upper()
                    if not symbol or not company.get("company_name"):
                        errors += 1
                        logger.warning("Skipping NSE watchlist entry with a missing symbol or exact company_name.")
                        continue

                    company_filings: List[Dict[str, Any]] = []
                    try:
                        for period_type in ("Quarterly", "Annual"):
                            response = None
                            last_error = None
                            # Retry transient exchange failures per period; a single
                            # feed failure must not discard already fetched filings.
                            for attempt in range(3):
                                try:
                                    candidate = await session.get(
                                        NSE_RESULTS_API_URL,
                                        params={"index": "equities", "period": period_type, "symbol": symbol},
                                        headers=nse_headers,
                                    )
                                    if candidate.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                                        await asyncio.sleep(0.5 * (2 ** attempt))
                                        continue
                                    candidate.raise_for_status()
                                    response = candidate
                                    break
                                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                                    last_error = exc
                                    if attempt < 2:
                                        await asyncio.sleep(0.5 * (2 ** attempt))
                                        continue
                                    raise
                            if response is None:
                                if last_error:
                                    raise last_error
                                raise RuntimeError("NSE results request failed after retries.")
                            parsed = parse_nse_financial_results_payload(
                                response.json(), symbol, company, period_type
                            )
                            if parsed:
                                # Keep every recent announcement, including amended filings for
                                # earlier periods; freshness is determined by broadcast time below.
                                consolidated = [
                                    item for item in parsed
                                    if "consolidated" in (item.get("consolidation") or "").lower()
                                    and "non-consolidated" not in (item.get("consolidation") or "").lower()
                                    and "standalone" not in (item.get("consolidation") or "").lower()
                                ]
                                if consolidated:
                                    parsed = consolidated
                            company_filings.extend(parsed)
                        nse_rows_by_symbol[symbol] = company_filings
                        logger.info(
                            "NSE financial-results feed checked for %s; exact issuer filings matched=%s.",
                            symbol,
                            len(company_filings),
                        )
                    except Exception as exc:
                        errors += 1
                        status_code = getattr(getattr(exc, "response", None), "status_code", None)
                        logger.warning(
                            "NSE results API failed for %s (HTTP %s; %s).",
                            symbol,
                            status_code if status_code is not None else "n/a",
                            type(exc).__name__,
                        )
                        nse_rows_by_symbol[symbol] = []
        except Exception as exc:
            errors += 1
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            logger.warning(
                "NSE IPO/results session bootstrap failed (HTTP %s; %s).",
                status_code if status_code is not None else "n/a",
                type(exc).__name__,
            )
            for company in nse_companies:
                symbol = str(company.get("symbol") or "").strip().upper()
                # Preserve any issuer filings already fetched before a later
                # issuer/feed error; don't erase valid partial results.
                nse_rows_by_symbol.setdefault(symbol, [])

    bse_rows_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    if bse_companies:
        try:
            today_ist = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).date()
            bse_rows_by_symbol, bse_errors = await asyncio.to_thread(
                _fetch_bse_results_sync,
                bse_companies,
                today_ist,
            )
            errors += bse_errors
        except Exception as exc:
            errors += len(bse_companies)
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            logger.warning(
                "BSE results client failed before completing the watchlist (HTTP %s; %s).",
                status_code if status_code is not None else "n/a",
                type(exc).__name__,
            )
            for company in bse_companies:
                bse_rows_by_symbol[str(company.get("symbol") or "").strip().upper()] = []

    now_ist = datetime.now(IST)
    for company in watchlist:
        symbol = str(company.get("symbol") or "").strip().upper()
        checked += 1
        exchange = str(company.get("exchange", "NSE")).upper()
        filings = (
            bse_rows_by_symbol.get(symbol, [])
            if exchange == "BSE"
            else nse_rows_by_symbol.get(symbol, [])
        )
        recent_filings = [item for item in filings if _is_recent_filing(item, now=now_ist)]
        logger.info(
            "%s results monitor: %s fetched, %s within the last %s hours.",
            symbol, len(filings), len(recent_filings), RESULT_LOOKBACK_HOURS,
        )

        force_resend_results = os.getenv("FORCE_RESEND_RESULTS", "").strip().lower() in {"1", "true", "yes"}
        for item in recent_filings:
            was_processed = store.has_processed_event(item["event_key"])
            get_event_record = getattr(store, "event_record", None)
            prior_record = get_event_record(item["event_key"]) if callable(get_event_record) else None
            attachment_entries = item.get("attachments") or []
            attachment_urls = [
                str(entry.get("url") if isinstance(entry, dict) else entry)
                for entry in attachment_entries
            ]
            attachment_urls.extend(
                str(item.get(key)) for key in ("xbrl_url", "attachment_url", "details_url") if item.get(key)
            )
            retry_incomplete = bool(
                was_processed
                and prior_record
                and prior_record.get("processing_status") == "UNAVAILABLE"
                and attachment_urls
            )
            if was_processed and not force_resend_results and not retry_incomplete:
                continue
            if force_resend_results and was_processed:
                logger.warning("Manual results resend override enabled for already-processed filing %s.", item.get("event_key"))
            new_filings += 1
            metrics, document_text, attachment_failures = await _extract_official_attachment(item, attachment_urls)
            if metrics.get("status") != "EXTRACTED":
                documents_unavailable += 1
            processing_status = (
                "EXTRACTED" if metrics.get("status") == "EXTRACTED"
                else "UNAVAILABLE" if attachment_urls
                else "NO_ATTACHMENT"
            )
            if attachment_failures and metrics.get("status") == "EXTRACTED":
                logger.info("A fallback attachment yielded usable candidate metrics for %s.", symbol)

            safe_period_value = item.get("period_ended") or item.get("broadcast_time") or "filing"
            safe_period = re.sub(r"[^0-9A-Za-z_-]+", "_", str(safe_period_value))
            safe_symbol = re.sub(r"[^0-9A-Za-z_-]+", "_", symbol)
            report_path = report_dir / f"{safe_symbol}_{safe_period}_{item['event_key'][-8:]}.md"
            report_content = _report_text(item, metrics, document_text)
            report_path.write_text(report_content, encoding="utf-8")
            pdf_path = report_path.with_suffix(".pdf")
            pdf_attachments = []
            try:
                markdown_to_pdf(report_content, pdf_path, title=f"Financial Results - {symbol}")
                if pdf_path.is_file():
                    pdf_attachments = [str(pdf_path)]
            except Exception as exc:
                logger.warning("Results PDF rendering failed for %s (%s); sending the email body without an attachment.", symbol, type(exc).__name__)
            run_id = os.getenv("GITHUB_RUN_ID")
            repository = os.getenv("GITHUB_REPOSITORY", "SandulaVinay/IPO-Analysis")
            report_url = f"https://github.com/{repository}/actions/runs/{run_id}" if run_id else None
            subject, content = build_results_email(item, metrics, report_url=report_url)

            # Don't duplicate a filing email while retrying a previously
            # unavailable attachment. Send one update if extraction later works.
            prior_notified = bool(
                prior_record and prior_record.get("status") in {"ACCEPTED", "DELIVERED"}
            )
            should_notify = (
                force_resend_results
                or not prior_notified
                or (prior_record and prior_record.get("processing_status") == "UNAVAILABLE" and processing_status == "EXTRACTED")
            )
            channel = "EMAIL"
            email_accepted = False
            success = False
            if should_notify:
                # Email is primary; WhatsApp is an explicit fallback only.
                result = await EmailProvider().send_notification(
                    recipient=settings.email_to,
                    subject=subject,
                    content=content,
                    metadata={
                        "attachments": pdf_attachments,
                        "html_body": results_email_html(content),
                    },
                )
                email_accepted = bool(result.get("success") and (result.get("accepted") or result.get("delivered")))
                success = email_accepted
                if not email_accepted and settings.enable_whatsapp:
                    result = await WhatsAppProvider().send_notification(
                        recipient=settings.whatsapp_recipient_phone,
                        subject=subject,
                        content=content,
                        metadata={"attachment_path": pdf_attachments[0] if pdf_attachments else None},
                    )
                    channel = "WHATSAPP"
                    success = bool(result.get("success") and (result.get("accepted") or result.get("delivered")))
            elif prior_notified:
                success = True
                channel = str(prior_record.get("channel") or "EMAIL")
            if should_notify and settings.enable_email and not email_accepted:
                notification_failures += 1
            if success:
                accepted_count += 1
                store.record_event(
                    item["event_key"],
                    event_type="FINANCIAL_RESULTS_FILING",
                    symbol=symbol,
                    event_date=str(item.get("period_ended") or item.get("broadcast_time") or ""),
                    status="ACCEPTED",
                    channel=channel,
                    processing_status=processing_status,
                )
            else:
                if not settings.enable_email:
                    notification_skipped += 1
                store.record_event(
                    item["event_key"],
                    event_type="FINANCIAL_RESULTS_FILING",
                    symbol=symbol,
                    event_date=str(item.get("period_ended") or item.get("broadcast_time") or ""),
                    status="FAILED",
                    channel=None,
                    processing_status=processing_status,
                )

    status = "PARTIAL" if errors or documents_unavailable or notification_failures else (
        "REPORT_ONLY" if notification_skipped else "SUCCESS"
    )
    store.record_run(
        command="results",
        status=status,
        detail=(
            f"symbols_checked={checked}; new_filings={new_filings}; "
            f"notifications_accepted={accepted_count}; notification_failures={notification_failures}; "
            f"notification_skipped={notification_skipped}; documents_unavailable={documents_unavailable}; errors={errors}"
        ),
    )
    return {
        "status": status,
        "watchlist_size": len(watchlist),
        "symbols_checked": checked,
        "new_filings": new_filings,
        "notifications_accepted": accepted_count,
        "notification_failures": notification_failures,
        "notification_skipped": notification_skipped,
        "documents_unavailable": documents_unavailable,
        "errors": errors,
        "reports_dir": str(report_dir),
    }
