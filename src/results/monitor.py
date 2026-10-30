"""Official NSE financial-results filing monitor with conservative XBRL extraction.

The monitor reports only values found in a source filing. It never infers financial
performance from a filing title and never emits a buy/sell recommendation.
"""
import hashlib
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.common.config import settings
from src.common.logging import logger
from src.discovery.normalizer import Normalizer
from src.ingestion.client import http_client
from src.notifications.email import EmailProvider
from src.notifications.whatsapp import WhatsAppProvider
from src.state.store import StateStore
from src.reporting.pdf import markdown_to_pdf

NSE_ROOT_URL = "https://www.nseindia.com/"
NSE_RESULTS_URL = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"
NSE_RESULTS_API_URL = "https://www.nseindia.com/api/corporates-financial-results"
BSE_RESULTS_API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_RESULTS_PAGE_URL = "https://www.bseindia.com/corporates/ann.html"
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


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _matches_watchlist_company(filing: Dict[str, Any], company: Dict[str, Any]) -> bool:
    """Match only an explicitly configured issuer name/alias; never infer symbol from a page-wide table."""
    expected = [company.get("company_name"), *(company.get("company_name_aliases") or [])]
    expected_keys = {_key(value) for value in expected if isinstance(value, str) and value.strip()}
    return bool(expected_keys and _key(str(filing.get("company_name", ""))) in expected_keys)


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
        broadcast = _clean(str(row.get("broadCastDate") or row.get("broadcastDate") or row.get("filingDate") or ""))
        relating = _clean(str(row.get("relatingTo") or row.get("relating_to") or period_type))
        xbrl_value = str(row.get("xbrl") or row.get("xbrlUrl") or "").strip()
        details_value = str(row.get("resultDetailedDataLink") or row.get("detailsUrl") or "").strip()
        xbrl_url = urljoin(NSE_RESULTS_URL, xbrl_value) if xbrl_value else None
        details_url = urljoin(NSE_RESULTS_URL, details_value) if details_value else None
        attachment = xbrl_url or details_url
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
            "xbrl_url": xbrl_url,
            "details_url": details_url,
        })
    return output


def bse_api_headers() -> Dict[str, str]:
    """Browser-like headers required by BSE's public announcement endpoint."""
    return {
        "Host": "api.bseindia.com",
        "Referer": "https://www.bseindia.com/",
        "Origin": "https://www.bseindia.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
        "Sec-CH-UA": '"Google Chrome";v="155", "Chromium";v="155", "Not?A_Brand";v="99"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "DNT": "1",
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }


def bse_results_request_params(page_no: int, scrip_code: str, from_date, to_date) -> Dict[str, Any]:
    """Build the minimal BSE financial-announcement query; Result/Financial Results are defaults."""
    return {
        "pageno": page_no,
        "strCat": "-1",
        "subcategory": "-1",
        "strPrevDate": from_date.strftime("%Y%m%d"),
        "strToDate": to_date.strftime("%Y%m%d"),
        "strSearch": "P",
        "strscrip": scrip_code,
        "strType": "C",
    }


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
            details_attachment = next((
                item["url"] for item in links
                if "details" in item["label"].lower()
                or item["url"].lower().split("?")[0].endswith(".pdf")
            ), None)
            attachment = xbrl_attachment or details_attachment or next(
                (item["url"] for item in links if item["url"].lower().split("?")[0].endswith(".xlsx")),
                None,
            )
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
        broadcast = _clean(str(row.get("DT_TM") or row.get("NEWS_DT") or row.get("News_submission_dt") or ""))
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
            "xbrl_url": None,
            "details_url": None,
            "headline": headline,
            "bse_scrip_code": str(scrip_code),
        })
    return output


def _format_metric(value: Optional[float], suffix: str = "") -> str:
    return "Not available" if value is None else f"{value:,.2f}{suffix}"


def _report_text(item: Dict[str, Any], metrics: Dict[str, Any]) -> str:
    attachment = item.get("attachment_url") or item["source_url"]
    if metrics.get("status") == "EXTRACTED":
        analysis = (
            f"- **Revenue from operations:** ₹{_format_metric(metrics.get('revenue_cr'))} Cr\n"
            f"- **Profit after tax (PAT):** ₹{_format_metric(metrics.get('pat_cr'))} Cr\n"
            f"- **EPS:** ₹{_format_metric(metrics.get('eps'))}\n"
            f"- **Operating cash flow:** ₹{_format_metric(metrics.get('cfo_cr'))} Cr\n"
            f"- **Revenue YoY change:** {_format_metric(metrics.get('revenue_yoy_pct'), '%')}\n"
            f"- **PAT YoY change:** {_format_metric(metrics.get('pat_yoy_pct'), '%')}\n"
        )
        analysis_note = "Metrics above were extracted from the linked XBRL instance. Validate the original filing before making an investment decision."
    else:
        analysis = "- **Automated metrics:** Not available from the detected attachment format.\n"
        analysis_note = "No financial-performance conclusion or investment recommendation is generated from filing metadata alone."
    return (
        f"# Official financial-results filing: {item['company_name']} ({item['symbol']})\n\n"
        f"- **Exchange:** {item.get('exchange') or 'NSE'}\n"
        f"- **Period ended:** {item.get('period_ended') or 'Not specified in the filing notice'}\n"
        f"- **Period / quarter:** {item.get('relating_to') or 'Not specified in the table'}\n"
        f"- **Broadcast time:** {item['broadcast_time']}\n"
        f"- **Audited status:** {item.get('audit_status') or 'Not specified'}\n"
        f"- **Statement basis:** {item.get('consolidation') or 'Not specified'}\n"
        f"- **Official source:** {item['source_url']}\n"
        f"- **Filing attachment:** {attachment}\n"
        f"- **Details / PDF attachment:** {item.get('details_url') or 'Not available'}\n\n"
        f"## Extracted financial metrics\n\n{analysis}\n{analysis_note}\n"
    )


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
                            response = await session.get(
                                NSE_RESULTS_API_URL,
                                params={"index": "equities", "period": period_type, "symbol": symbol},
                                headers=nse_headers,
                            )
                            response.raise_for_status()
                            parsed = parse_nse_financial_results_payload(
                                response.json(), symbol, company, period_type
                            )
                            if parsed:
                                dates = [
                                    (Normalizer.parse_date(item.get("period_ended")), item)
                                    for item in parsed
                                ]
                                valid_dates = [period for period, _ in dates if period is not None]
                                if valid_dates:
                                    latest_period = max(valid_dates)
                                    parsed = [item for period, item in dates if period == latest_period]
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
                nse_rows_by_symbol[str(company.get("symbol") or "").strip().upper()] = []

    bse_rows_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    if bse_companies:
        bse_headers = bse_api_headers()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(35.0, connect=15.0),
                follow_redirects=True,
            ) as session:
                # Prime BSE cookies from a public issues page known to respond in
                # discovery before querying the corporate-announcement API.
                bse_landing = await session.get(
                    "https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx?id=1&Type=p",
                    headers={
                        **bse_headers,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Dest": "document",
                    },
                )
                bse_landing.raise_for_status()

                for company in bse_companies:
                    symbol = str(company.get("symbol") or "").strip().upper()
                    scrip_code = str(company.get("bse_scrip_code") or "").strip()
                    if not symbol or not company.get("company_name") or not re.fullmatch(r"\d{6}", scrip_code):
                        errors += 1
                        logger.warning("Skipping BSE watchlist entry %s: company_name and six-digit bse_scrip_code are required.", symbol or "(missing)")
                        continue
                    try:
                        today_ist = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).date()
                        from_date = today_ist - timedelta(days=7)
                        raw_rows: List[Dict[str, Any]] = []
                        for page_no in range(1, 6):
                            response = await session.get(
                                BSE_RESULTS_API_URL,
                                params=bse_results_request_params(page_no, scrip_code, from_date, today_ist),
                                headers=bse_headers,
                            )
                            response.raise_for_status()
                            response_payload = response.json()
                            if not isinstance(response_payload, dict) or not isinstance(response_payload.get("Table"), list):
                                raise ValueError("BSE results API response did not contain a Table list.")
                            page_rows = response_payload["Table"]
                            raw_rows.extend(row for row in page_rows if isinstance(row, dict))
                            total_rows = 0
                            table1 = response_payload.get("Table1")
                            if isinstance(table1, list) and table1 and isinstance(table1[0], dict):
                                try:
                                    total_rows = int(table1[0].get("ROWCNT") or 0)
                                except (TypeError, ValueError):
                                    total_rows = 0
                            if not page_rows or (total_rows and len(raw_rows) >= total_rows) or len(page_rows) < 50:
                                break
                        bse_rows_by_symbol[symbol] = parse_bse_financial_results_payload(
                            {"Table": raw_rows}, symbol, company, scrip_code
                        )
                        logger.info(
                            "BSE announcement feed checked for %s (scrip %s); exact results announcements matched=%s.",
                            symbol,
                            scrip_code,
                            len(bse_rows_by_symbol[symbol]),
                        )
                    except Exception as exc:
                        errors += 1
                        status_code = getattr(getattr(exc, "response", None), "status_code", None)
                        logger.warning(
                            "BSE results API failed for %s (HTTP %s; %s).",
                            symbol,
                            status_code if status_code is not None else "n/a",
                            type(exc).__name__,
                        )
                        bse_rows_by_symbol[symbol] = []
        except Exception as exc:
            errors += 1
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            logger.warning(
                "BSE session bootstrap failed (HTTP %s; %s).",
                status_code if status_code is not None else "n/a",
                type(exc).__name__,
            )
            for company in bse_companies:
                bse_rows_by_symbol[str(company.get("symbol") or "").strip().upper()] = []

    for company in watchlist:
        symbol = str(company.get("symbol") or "").strip().upper()
        checked += 1
        exchange = str(company.get("exchange", "NSE")).upper()
        filings = (
            bse_rows_by_symbol.get(symbol, [])
            if exchange == "BSE"
            else nse_rows_by_symbol.get(symbol, [])
        )

        for item in filings:
            if store.has_processed_event(item["event_key"]):
                continue
            new_filings += 1
            metrics: Dict[str, Any] = {"status": "UNAVAILABLE", "reason": "No supported XBRL attachment was detected."}
            attachment = item.get("xbrl_url") or item.get("attachment_url") or ""
            if attachment.lower().endswith((".xml", ".xbrl")) or "/xbrl/" in attachment.lower():
                try:
                    xbrl_response = await http_client.get(
                        attachment,
                        headers={"Referer": "https://www.nseindia.com/"},
                        timeout=30.0,
                    )
                    if item.get("period_ended"):
                        metrics = extract_xbrl_metrics(
                            xbrl_response.content, item["period_ended"], item.get("relating_to") or ""
                        )
                except Exception as exc:
                    metrics = {"status": "UNAVAILABLE", "reason": f"XBRL extraction failed ({type(exc).__name__})."}
                    logger.warning("XBRL extraction failed for %s (%s).", symbol, type(exc).__name__)

            safe_period_value = item.get("period_ended") or item.get("broadcast_time") or "filing"
            safe_period = re.sub(r"[^0-9A-Za-z_-]+", "_", str(safe_period_value))
            safe_symbol = re.sub(r"[^0-9A-Za-z_-]+", "_", symbol)
            report_path = report_dir / f"{safe_symbol}_{safe_period}_{item['event_key'][-8:]}.md"
            report_content = _report_text(item, metrics)
            report_path.write_text(report_content, encoding="utf-8")
            markdown_to_pdf(report_content, report_path.with_suffix(".pdf"), title=f"Financial Results - {symbol}")
            subject = f"Official results filing: {item['company_name']} ({symbol})"
            content = (
                f"Official {exchange} financial-results filing detected.\n\n"
                f"Company: {item['company_name']} ({symbol})\n"
                f"Exchange: {exchange}\n"
                f"Period ended: {item.get('period_ended') or 'Not disclosed in the filing notice'}\n"
                f"Period/category: {item.get('relating_to') or 'Not specified'}\n"
                f"Broadcast: {item.get('broadcast_time') or 'Not specified'}\n"
                f"Official filing: {attachment or item['source_url']}\n"
                + (f"Details PDF: {item['details_url']}\n" if item.get("details_url") else "")
            )
            if item.get("headline"):
                content += f"Announcement: {item['headline']}\n"
            run_id = os.getenv("GITHUB_RUN_ID")
            repository = os.getenv("GITHUB_REPOSITORY", "SandulaVinay/IPO-Analysis")
            if run_id:
                content += f"\nFull PDF report artifact: https://github.com/{repository}/actions/runs/{run_id}\n"
            if metrics.get("status") == "EXTRACTED":
                content += (
                    f"Revenue: ₹{_format_metric(metrics.get('revenue_cr'))} Cr\n"
                    f"PAT: ₹{_format_metric(metrics.get('pat_cr'))} Cr\n"
                    f"EPS: ₹{_format_metric(metrics.get('eps'))}\n"
                    f"Revenue YoY: {_format_metric(metrics.get('revenue_yoy_pct'), '%')}\n"
                    f"PAT YoY: {_format_metric(metrics.get('pat_yoy_pct'), '%')}\n"
                )
            else:
                content += "Automated financial metrics were unavailable for this filing; no performance verdict is implied.\n"

            result = await WhatsAppProvider().send_notification(
                recipient=settings.whatsapp_recipient_phone,
                subject=subject,
                content=content,
                metadata={"attachment_path": str(report_path.with_suffix(".pdf"))},
            )
            channel = "WHATSAPP"
            success = bool(result.get("success") and (result.get("accepted") or result.get("delivered")))
            if not success:
                result = await EmailProvider().send_notification(
                    recipient=settings.email_to,
                    subject=subject,
                    content=content,
                    metadata={"attachments": [str(report_path.with_suffix(".pdf"))]},
                )
                channel = "EMAIL"
                success = bool(result.get("success") and (result.get("accepted") or result.get("delivered")))
            if success:
                accepted_count += 1
                store.record_event(
                    item["event_key"],
                    event_type="FINANCIAL_RESULTS_FILING",
                    symbol=symbol,
                    event_date=str(item.get("period_ended") or item.get("broadcast_time") or ""),
                    status="ACCEPTED",
                    channel=channel,
                )
            else:
                store.record_event(
                    item["event_key"],
                    event_type="FINANCIAL_RESULTS_FILING",
                    symbol=symbol,
                    event_date=str(item.get("period_ended") or item.get("broadcast_time") or ""),
                    status="FAILED",
                    channel=None,
                )

    status = "PARTIAL" if errors else "SUCCESS"
    store.record_run(
        command="results",
        status=status,
        detail=f"symbols_checked={checked}; new_filings={new_filings}; notifications_accepted={accepted_count}; errors={errors}",
    )
    return {
        "status": status,
        "watchlist_size": len(watchlist),
        "symbols_checked": checked,
        "new_filings": new_filings,
        "notifications_accepted": accepted_count,
        "errors": errors,
        "reports_dir": str(report_dir),
    }
