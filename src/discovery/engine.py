"""
IPO Discovery Engine.
Orchestrates discovery across multi-tier sources, normalizes records, and registers them in the database.
"""

from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.logging import logger
from src.database.models import IPO, IPOEvent
from src.database.repository import IPORepository
from src.discovery.normalizer import Normalizer
from src.ingestion.scrapers import PortalScraper


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
        discovered_entities: List[IPO] = []

        for raw in raw_ipos:
            symbol = raw.get("symbol") or Normalizer.generate_symbol(raw["company_name"])
            company_name = Normalizer.clean_company_name(raw["company_name"])
            
            announced_open_date = Normalizer.parse_date(raw.get("announced_open_date") or raw.get("verified_open_date"))
            announced_close_date = Normalizer.parse_date(raw.get("announced_close_date") or raw.get("verified_close_date"))
            conflicts = raw.get("source_conflicts") or []
            verified_open_date = None if conflicts else Normalizer.parse_date(raw.get("verified_open_date"))
            verified_close_date = None if conflicts else Normalizer.parse_date(raw.get("verified_close_date"))

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
                # Clear previously verified dates so stale data cannot survive a new source conflict.
                ipo.verified_open_date = None
                ipo.verified_close_date = None
                previous_status = ipo.status
                ipo.status = "SOURCE_CONFLICT"
                if previous_status != "SOURCE_CONFLICT":
                    self.session.add(IPOEvent(
                        ipo_id=ipo.id,
                        from_status=previous_status,
                        to_status="SOURCE_CONFLICT",
                        trigger="DISCOVERY_ENGINE",
                        notes=f"Conflicting official source dates: {conflicts[:3]}",
                    ))
                logger.warning("Official source conflict for %s (%s); verified dates cleared.", company_name, symbol)
            elif ipo.status == "SOURCE_CONFLICT":
                ipo.status = "IPO_DISCOVERED"
            discovered_entities.append(ipo)
            logger.info(
                "Discovered/updated IPO: %s (%s) | announced dates: %s to %s | verified dates: %s to %s",
                company_name, symbol, announced_open_date, announced_close_date,
                ipo.verified_open_date, ipo.verified_close_date,
            )

        await self.session.commit()
        return discovered_entities
