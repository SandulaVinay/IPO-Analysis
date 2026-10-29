"""Official NSE financial-results filing monitor.

This module reports filing metadata only. It deliberately does not infer revenue,
profit, growth, or an investment verdict from a filing title or an unparsed PDF.
"""
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.common.config import settings
from src.ingestion.client import http_client
from src.notifications.email import EmailProvider
from src.notifications.whatsapp import WhatsAppProvider
from src.state.store import StateStore
from src.common.logging import logger
from src.discovery.normalizer import Normalizer

NSE_RESULTS_URL = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


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
                label = _clean(anchor.get_text(" ", strip=True))
                if href.startswith("https://") and href not in links:
                    links.append(href)
            attachment = next((link for link in links if any(ext in link.lower() for ext in (".pdf", ".xml", ".xlsx"))), None)
            canonical_source = attachment or page_url
            event_material = "|".join([symbol.upper(), period_end, relating, broadcast, consolidation, canonical_source])
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


def _report_text(item: Dict[str, Any]) -> str:
    attachment = item.get("attachment_url") or item["source_url"]
    return (
        f"# Official financial-results filing: {item['company_name']} ({item['symbol']})\n\n"
        f"- **Period ended:** {item['period_ended']}\n"
        f"- **Period / quarter:** {item.get('relating_to') or 'Not specified in the table'}\n"
        f"- **Broadcast time:** {item['broadcast_time']}\n"
        f"- **Audited status:** {item.get('audit_status') or 'Not specified'}\n"
        f"- **Statement basis:** {item.get('consolidation') or 'Not specified'}\n"
        f"- **Official source:** {item['source_url']}\n"
        f"- **Filing attachment:** {attachment}\n\n"
        "## Analysis status\n\n"
        "This is a verified-filing alert, not a financial-performance verdict. Automated extraction of the "
        "filing's revenue, profit, EPS, cash flow, and year-over-year / quarter-over-quarter changes is not "
        "yet enabled for this filing format. No apply/avoid or buy/sell recommendation is generated from this metadata.\n"
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
            safe_period = re.sub(r"[^0-9A-Za-z_-]+", "_", item["period_ended"])
            report_path = report_dir / f"{symbol}_{safe_period}_{item['event_key'][-8:]}.md"
            report_path.write_text(_report_text(item), encoding="utf-8")
            subject = f"Official quarterly/annual results filing: {item['company_name']} ({symbol})"
            content = (
                f"New official NSE financial-results filing detected.\n\n"
                f"Company: {item['company_name']} ({symbol})\n"
                f"Period ended: {item['period_ended']}\n"
                f"Period: {item.get('relating_to') or 'Not specified'}\n"
                f"Broadcast: {item['broadcast_time']}\n"
                f"Official filing: {item.get('attachment_url') or item['source_url']}\n\n"
                "This alert confirms a filing only; automated financial-statement analysis is pending. "
                "No investment recommendation is implied."
            )
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
