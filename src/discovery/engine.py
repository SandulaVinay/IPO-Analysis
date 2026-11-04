"""
IPO Discovery Engine.
Orchestrates discovery across multi-tier sources, normalizes records, and registers them in the database.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.logging import logger
from src.database.models import IPO, IPOEvent
from src.database.repository import IPORepository
from src.documents.manager import DocumentManager
from src.discovery.normalizer import Normalizer
from src.ingestion.scrapers import PortalScraper

IPOWATCH_GMP_SOURCE = "IPOWATCH"


def _naive_utc(value: Any) -> datetime:
    """Convert a parsed source capture time to the database's naive-UTC convention."""
    if isinstance(value, datetime):
        captured = value
    else:
        try:
            captured = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except (TypeError, ValueError):
            captured = datetime.now(timezone.utc)
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    return captured.astimezone(timezone.utc).replace(tzinfo=None)


class DiscoveryEngine:
    """Discovers and synchronizes Indian IPOs from external sources."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = IPORepository(session)
        self.scraper = PortalScraper()

    async def run_discovery(self) -> List[IPO]:
        """Execute full discovery cycle."""
        logger.info("Starting IPO discovery cycle...")
        raw_ipos = await self.scraper.fetch_upcoming_ipos()
        self.source_status = getattr(self.scraper, 'last_source_status', 'SUCCESS')
        discovered_entities: List[IPO] = []
        document_manager = None

        for raw in raw_ipos:
            symbol = raw.get("symbol") or Normalizer.generate_symbol(raw["company_name"])
            company_name = Normalizer.clean_company_name(raw["company_name"])
            
            announced_open_date = Normalizer.parse_date(raw.get("announced_open_date") or raw.get("verified_open_date"))
            announced_close_date = Normalizer.parse_date(raw.get("announced_close_date") or raw.get("verified_close_date"))
            date_conflicts = raw.get("source_conflicts") or []
            field_conflicts = raw.get("field_conflicts") or []
            conflicts = date_conflicts + field_conflicts
            verified_open_date = None if date_conflicts else Normalizer.parse_date(raw.get("verified_open_date"))
            verified_close_date = None if date_conflicts else Normalizer.parse_date(raw.get("verified_close_date"))

            ipo = await self.repo.create_or_update_ipo(
                symbol=symbol,
                company_name=company_name,
                industry=raw.get("industry"),
                issue_type=raw.get("issue_type", "UNKNOWN"),
                announced_open_date=announced_open_date,
                announced_close_date=announced_close_date,
                verified_open_date=verified_open_date,
                verified_close_date=verified_close_date,
                min_price=raw.get("min_price"),
                max_price=raw.get("max_price"),
                lot_size=raw.get("lot_size"),
                issue_size_cr=raw.get("issue_size_cr"),
                fresh_issue_cr=raw.get("fresh_issue_cr"),
                ofs_cr=raw.get("ofs_cr"),
            )
            if conflicts:
                # Clear only fields that are explicitly in conflict; never retain stale values.
                if date_conflicts:
                    ipo.verified_open_date = None
                    ipo.verified_close_date = None
                for conflict in field_conflicts:
                    field_name = conflict.get("field")
                    if field_name in {"min_price", "max_price", "lot_size", "issue_size_cr"}:
                        setattr(ipo, field_name, None)
                previous_status = ipo.status
                ipo.status = "SOURCE_CONFLICT"
                if previous_status != "SOURCE_CONFLICT":
                    self.session.add(IPOEvent(
                        ipo_id=ipo.id,
                        from_status=previous_status,
                        to_status="SOURCE_CONFLICT",
                        trigger="DISCOVERY_ENGINE",
                        notes=f"Conflicting official source fields: {conflicts[:3]}",
                    ))
                logger.warning("Official source conflict for %s (%s); conflicted fields were cleared.", company_name, symbol)
            elif ipo.status == "SOURCE_CONFLICT":
                ipo.status = "IPO_DISCOVERED"

            # GMP is an unofficial sentiment field. Match only a unique exact
            # issuer name and require the tracker band to agree with the official
            # exchange price before persisting it.
            fetch_gmp = getattr(self.scraper, "fetch_live_gmp_for_company", None)
            if fetch_gmp and ipo.status != "SOURCE_CONFLICT" and ipo.max_price:
                try:
                    quote = await fetch_gmp(company_name)
                    if quote and quote.get("gmp_value") not in (None, 0):
                        quote_upper = quote.get("max_price")
                        quote_type = str(quote.get("issue_type") or "UNKNOWN").upper()
                        ipo_type = str(ipo.issue_type or "UNKNOWN").upper()
                        if quote_upper is None or abs(float(quote_upper) - float(ipo.max_price)) > 0.01:
                            logger.info("Skipping GMP for %s because its unofficial price band does not match the official listing.", symbol)
                        elif quote_type != "UNKNOWN" and ipo_type not in {"UNKNOWN", quote_type}:
                            logger.info("Skipping GMP for %s because the tracker issue type conflicts with official discovery.", symbol)
                        else:
                            previous = await self.repo.latest_gmp_snapshot(ipo.id, source=IPOWATCH_GMP_SOURCE)
                            gmp_value = float(quote["gmp_value"])
                            trend = "UNKNOWN"
                            if previous and abs(float(previous.gmp_value) - gmp_value) > 0.0001:
                                trend = "RISING" if gmp_value > float(previous.gmp_value) else "FALLING"
                            if (
                                previous is None
                                or abs(float(previous.gmp_value) - gmp_value) > 0.0001
                                or abs(float(previous.upper_price) - float(ipo.max_price)) > 0.01
                            ):
                                await self.repo.add_gmp(
                                    ipo_id=ipo.id,
                                    gmp_value=gmp_value,
                                    upper_price=float(ipo.max_price),
                                    source=IPOWATCH_GMP_SOURCE,
                                    trend=trend,
                                    captured_at=_naive_utc(quote.get("captured_at")),
                                )
                except Exception as exc:
                    # Keep official IPO discovery available when the unofficial
                    # sentiment site is blocked, stale, or changes its layout.
                    logger.warning("GMP lookup skipped for %s (%s).", symbol, type(exc).__name__)

            # Prospectus links are optional: only real, validated PDFs are ingested.
            # A failed download never creates a placeholder and never unblocks scoring.
            for document in raw.get("document_links") or []:
                if not isinstance(document, dict):
                    continue
                source_url = document.get("source_url")
                document_type = document.get("document_type")
                document_title = document.get("document_title") or document_type or "Prospectus"
                if not source_url or not document_type:
                    continue
                try:
                    if document_manager is None:
                        document_manager = DocumentManager(self.session)
                    if await document_manager.has_source_url(ipo.id, source_url):
                        continue
                    version = await document_manager.ingest_document(
                        ipo_id=ipo.id,
                        document_type=document_type,
                        document_title=document_title,
                        source_url=source_url,
                    )
                    logger.info(
                        "Prospectus evidence ingestion completed for %s: type=%s status=%s",
                        symbol, document_type, version.processing_status,
                    )
                except Exception as exc:
                    logger.warning(
                        "Prospectus ingestion skipped for %s (%s); analysis remains gated.",
                        symbol, type(exc).__name__,
                    )

            discovered_entities.append(ipo)
            logger.info(
                "Discovered/updated IPO: %s (%s) | announced dates: %s to %s | verified dates: %s to %s",
                company_name, symbol, announced_open_date, announced_close_date,
                ipo.verified_open_date, ipo.verified_close_date,
            )

        await self.session.commit()
        return discovered_entities
