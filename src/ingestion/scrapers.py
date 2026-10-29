"""Official-source IPO discovery adapters for NSE/BSE public-issue pages.

Only values actually present in the source HTML are emitted. If the page layout
changes or the table is not available, the adapter returns no rows rather than
manufacturing a sample IPO.
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.common.logging import logger
from src.ingestion.client import http_client


NSE_IPO_URL = "https://www.nseindia.com/market-data/all-upcoming-issues-ipo"
BSE_IPO_URL = "https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx?id=1&Type=p"


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()

def _parse_date_value(value: str):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d-%b-%y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None



def _has_recognized_issue_table(html: str) -> bool:
    """Distinguish a valid empty issue table from a changed/unrecognized page layout."""
    soup = BeautifulSoup(html, "lxml")
    company_aliases = ("company name", "name of company", "company", "issuer name", "issuer")
    open_aliases = ("issue start date", "open date", "opening date", "issue opening date", "start date")
    close_aliases = ("issue end date", "close date", "closing date", "issue closing date", "end date")
    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if header_row is None:
            continue
        headers = [_norm(cell.get_text(" ", strip=True)) for cell in header_row.find_all(["th", "td"])]
        has_company = any(any(alias in header for alias in company_aliases) for header in headers)
        has_date = any(
            any(alias in header for alias in open_aliases + close_aliases)
            for header in headers
        )
        if has_company and has_date:
            return True
    return False


def _extract_prospectus_links(row, source_url: str) -> List[Dict[str, str]]:
    """Find prospectus/addendum links from the same official exchange issue row."""
    documents: List[Dict[str, str]] = []
    seen = set()
    for anchor in row.find_all("a", href=True):
        href = urljoin(source_url, anchor["href"].strip())
        if not href.startswith("https://"):
            continue
        label = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).strip()
        descriptor = f"{label} {urlparse(href).path}".lower()
        if any(term in descriptor for term in ("draft red herring prospectus", "drhp")):
            document_type = "DRHP"
        elif any(term in descriptor for term in ("red herring prospectus", "rhp")):
            document_type = "RHP"
        elif "addendum" in descriptor or "corrigendum" in descriptor:
            document_type = "ADDENDUM"
        elif "prospectus" in descriptor:
            document_type = "PROSPECTUS"
        elif "price band" in descriptor or "price-band" in descriptor:
            document_type = "PRICE_BAND_AD"
        else:
            continue
        if href in seen:
            continue
        seen.add(href)
        documents.append({
            "document_type": document_type,
            "document_title": label or document_type,
            "source_url": href,
        })
    return documents


def _parse_official_issue_tables(html: str, *, source_name: str, source_url: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    rows: List[Dict[str, Any]] = []
    seen = set()

    company_aliases = ("company name", "name of company", "company", "issuer name", "issuer")
    open_aliases = ("issue start date", "open date", "opening date", "issue opening date", "start date")
    close_aliases = ("issue end date", "close date", "closing date", "issue closing date", "end date")
    type_aliases = ("security type", "issue type", "board", "market")
    status_aliases = ("status", "issue status")

    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if header_row is None:
            continue
        headers = [_norm(cell.get_text(" ", strip=True)) for cell in header_row.find_all(["th", "td"])]
        if not headers:
            continue

        def find_index(aliases):
            return next((i for i, header in enumerate(headers) if any(alias in header for alias in aliases)), None)

        company_idx = find_index(company_aliases)
        open_idx = find_index(open_aliases)
        close_idx = find_index(close_aliases)
        type_idx = find_index(type_aliases)
        status_idx = find_index(status_aliases)
        if company_idx is None or (open_idx is None and close_idx is None):
            continue

        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all(["td", "th"])
            if not cells or company_idx >= len(cells):
                continue
            company_name = re.sub(r"\s+", " ", cells[company_idx].get_text(" ", strip=True)).strip()
            if not company_name or _norm(company_name) in {"company name", "name of company", "company"}:
                continue
            key = _norm(company_name)
            if key in seen:
                continue

            def cell_text(index):
                return cells[index].get_text(" ", strip=True) if index is not None and index < len(cells) else ""

            issue_type_text = cell_text(type_idx).upper()
            issue_type = "SME" if "SME" in issue_type_text or "EMERGE" in issue_type_text else ("MAINBOARD" if issue_type_text else "UNKNOWN")
            row = {
                "company_name": company_name,
                "industry": None,
                "document_links": _extract_prospectus_links(tr, source_url),
                "issue_type": issue_type,
                "source_name": source_name,
                "source_tier": "TIER_1",
                "source_url": source_url,
                "captured_at": datetime.utcnow().isoformat(),
            }
            if cell_text(open_idx):
                row["announced_open_date"] = cell_text(open_idx)
                row["verified_open_date"] = cell_text(open_idx)
            if cell_text(close_idx):
                row["announced_close_date"] = cell_text(close_idx)
                row["verified_close_date"] = cell_text(close_idx)
            if cell_text(status_idx):
                row["source_status"] = cell_text(status_idx)
            seen.add(key)
            rows.append(row)

    return rows


class BaseScraper:
    source_name: str = "BaseScraper"
    source_tier: str = "TIER_1"


class PortalScraper(BaseScraper):
    """Collect IPO candidates from official exchange public-issue pages."""

    source_name = "NSE/BSE Official Public Issues"
    source_tier = "TIER_1"

    async def fetch_upcoming_ipos(self) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        successful_sources = 0
        recognized_sources = 0
        source_errors = []
        sources = (
            ("NSE India", NSE_IPO_URL),
            ("BSE India", BSE_IPO_URL),
        )
        for source_name, url in sources:
            try:
                response = await http_client.get(url, headers={"Referer": "https://www.nseindia.com/" if source_name == "NSE India" else "https://www.bseindia.com/"})
                successful_sources += 1
                if _has_recognized_issue_table(response.text):
                    recognized_sources += 1
                else:
                    source_errors.append(f"{source_name}:UNRECOGNIZED_LAYOUT")
                parsed = _parse_official_issue_tables(response.text, source_name=source_name, source_url=url)
                logger.info("Official IPO source %s yielded %s table rows.", source_name, len(parsed))
                collected.extend(parsed)
            except Exception as exc:
                # Keep the other official source available if one exchange is down.
                source_errors.append(f"{source_name}:{type(exc).__name__}")
                logger.warning("Official IPO source %s could not be retrieved or parsed (%s).", source_name, type(exc).__name__)

        if successful_sources == 0:
            raise RuntimeError("All official IPO sources failed: " + ", ".join(source_errors))
        if recognized_sources == 0:
            raise RuntimeError("No official IPO source layout was recognized: " + ", ".join(source_errors))

        deduped: Dict[str, Dict[str, Any]] = {}
        for row in collected:
            key = _norm(row["company_name"])
            if key not in deduped:
                deduped[key] = row
            else:
                # Preserve both source references for later verification.
                previous = deduped[key]
                previous["additional_source_url"] = row.get("source_url")
                previous["additional_source_name"] = row.get("source_name")
                existing_links = previous.setdefault("document_links", [])
                known_urls = {item.get("source_url") for item in existing_links if isinstance(item, dict)}
                for document in row.get("document_links", []):
                    if document.get("source_url") not in known_urls:
                        existing_links.append(document)
                        known_urls.add(document.get("source_url"))
                conflicts = previous.setdefault("source_conflicts", [])
                for date_key in ("verified_open_date", "verified_close_date"):
                    existing_value = previous.get(date_key)
                    incoming_value = row.get(date_key)
                    if existing_value and incoming_value:
                        existing_date = _parse_date_value(existing_value)
                        incoming_date = _parse_date_value(incoming_value)
                        if existing_date and incoming_date and existing_date != incoming_date:
                            conflicts.append({
                                "field": date_key,
                                "source_a": previous.get("source_name"),
                                "value_a": existing_value,
                                "source_b": row.get("source_name"),
                                "value_b": incoming_value,
                            })
                            previous.pop(date_key, None)
                        elif not existing_date and not incoming_date and str(existing_value).strip() != str(incoming_value).strip():
                            conflicts.append({
                                "field": date_key,
                                "source_a": previous.get("source_name"),
                                "value_a": existing_value,
                                "source_b": row.get("source_name"),
                                "value_b": incoming_value,
                            })
                            previous.pop(date_key, None)
                    elif incoming_value and not existing_value:
                        previous[date_key] = incoming_value
                    announced_key = date_key.replace("verified", "announced")
                    if previous.get(date_key) and not previous.get(announced_key):
                        previous[announced_key] = previous[date_key]
                if not conflicts:
                    previous.pop("source_conflicts", None)

        if not deduped:
            logger.warning("No official IPO rows were parsed. No candidate or recommendation will be fabricated.")
        return list(deduped.values())

    async def fetch_live_gmp(self, symbol: str) -> Optional[Dict[str, Any]]:
        """GMP is unofficial sentiment and is intentionally unavailable by default."""
        logger.info("GMP unavailable for %s; no verified source adapter is configured.", symbol)
        return None

    async def fetch_subscription_status(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Subscription data is unavailable until an exchange source adapter is configured."""
        logger.info("Subscription data unavailable for %s; no verified source adapter is configured.", symbol)
        return None
