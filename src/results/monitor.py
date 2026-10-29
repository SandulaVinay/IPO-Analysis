"""Official NSE financial-results filing monitor with conservative XBRL extraction.

The monitor reports only values found in a source filing. It never infers financial
performance from a filing title and never emits a buy/sell recommendation.
"""
import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.common.config import settings
from src.common.logging import logger
from src.discovery.normalizer import Normalizer
from src.ingestion.client import http_client
from src.notifications.email import EmailProvider
from src.notifications.whatsapp import WhatsAppProvider
from src.state.store import StateStore

NSE_RESULTS_URL = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"
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
    return re.sub(r"\\s+", " ", value or "").strip()


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


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
        consolidation_i = index_for("consolidated non consolidated", "consolidated")
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
            consolidation = _clean(cells[consolidation_i].get_text(" ", strip=True)) if consolidation_i is not None and consolidation_i < len(cells) else ""
            links = []
            for anchor in tr.find_all("a", href=True):
                href = urljoin(page_url, anchor["href"].strip())
                if href.startswith("https://") and href not in links:
                    links.append(href)
            attachment = next((link for link in links if any(ext in link.lower() for ext in (".pdf", ".xml", ".xbrl", ".xlsx")) or "/xbrl/" in link.lower()), None)
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
                "consolidation": consolidation,
                "source_url": page_url,
                "attachment_url": attachment,
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
        f"- **Period ended:** {item['period_ended']}\n"
        f"- **Period / quarter:** {item.get('relating_to') or 'Not specified in the table'}\n"
        f"- **Broadcast time:** {item['broadcast_time']}\n"
        f"- **Audited status:** {item.get('audit_status') or 'Not specified'}\n"
        f"- **Statement basis:** {item.get('consolidation') or 'Not specified'}\n"
        f"- **Official source:** {item['source_url']}\n"
        f"- **Filing attachment:** {attachment}\n\n"
        f"## Extracted financial metrics\n\n{analysis}\n{analysis_note}\n"
    )


async def monitor_financial_results() -> Dict[str, Any]:
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

    for company in watchlist:
        symbol = company["symbol"]
        checked += 1
        page_url = f"{NSE_RESULTS_URL}?symbol={symbol}"
        try:
            response = await http_client.get(
                NSE_RESULTS_URL,
                params={"symbol": symbol},
                headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-application"},
            )
            filings = parse_financial_results_page(response.text, symbol, page_url)
            if filings:
                parsed_periods = [(Normalizer.parse_date(item.get("period_ended")), item) for item in filings]
                valid_periods = [period for period, _ in parsed_periods if period is not None]
                if valid_periods:
                    latest_period = max(valid_periods)
                    filings = [item for period, item in parsed_periods if period == latest_period]
                consolidated = [item for item in filings if "consolidated" in (item.get("consolidation") or "").lower() and "non-consolidated" not in (item.get("consolidation") or "").lower()]
                if consolidated:
                    filings = consolidated
        except Exception as exc:
            errors += 1
            logger.warning("NSE results check failed for %s (%s).", symbol, type(exc).__name__)
            continue

        for item in filings:
            if store.has_processed_event(item["event_key"]):
                continue
            new_filings += 1
            metrics: Dict[str, Any] = {"status": "UNAVAILABLE", "reason": "No supported XBRL attachment was detected."}
            attachment = item.get("attachment_url") or ""
            if attachment.lower().endswith((".xml", ".xbrl")) or "/xbrl/" in attachment.lower():
                try:
                    xbrl_response = await http_client.get(attachment, headers={"Referer": "https://www.nseindia.com/"})
                    metrics = extract_xbrl_metrics(xbrl_response.content, item["period_ended"], item.get("relating_to") or "")
                except Exception as exc:
                    metrics = {"status": "UNAVAILABLE", "reason": f"XBRL extraction failed ({type(exc).__name__})."}
                    logger.warning("XBRL extraction failed for %s (%s).", symbol, type(exc).__name__)

            safe_period = re.sub(r"[^0-9A-Za-z_-]+", "_", item["period_ended"])
            report_path = report_dir / f"{symbol}_{safe_period}_{item['event_key'][-8:]}.md"
            report_path.write_text(_report_text(item, metrics), encoding="utf-8")
            subject = f"Official results filing: {item['company_name']} ({symbol})"
            content = (
                f"Official NSE financial-results filing detected.\n\n"
                f"Company: {item['company_name']} ({symbol})\n"
                f"Period ended: {item['period_ended']}\n"
                f"Period: {item.get('relating_to') or 'Not specified'}\n"
                f"Broadcast: {item['broadcast_time']}\n"
                f"Official filing: {attachment or item['source_url']}\n"
            )
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
            )
            channel = "WHATSAPP"
            success = bool(result.get("success") and (result.get("accepted") or result.get("delivered")))
            if not success:
                result = await EmailProvider().send_notification(
                    recipient=settings.email_to,
                    subject=subject,
                    content=content,
                )
                channel = "EMAIL"
                success = bool(result.get("success") and (result.get("accepted") or result.get("delivered")))
            if success:
                accepted_count += 1
                store.record_event(
                    item["event_key"],
                    event_type="FINANCIAL_RESULTS_FILING",
                    symbol=symbol,
                    event_date=item["period_ended"],
                    status="ACCEPTED",
                    channel=channel,
                )
            else:
                store.record_event(
                    item["event_key"],
                    event_type="FINANCIAL_RESULTS_FILING",
                    symbol=symbol,
                    event_date=item["period_ended"],
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
