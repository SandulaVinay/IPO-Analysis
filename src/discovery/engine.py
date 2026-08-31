"""
IPO Discovery Engine.
Orchestrates discovery across multi-tier sources, normalizes records, and registers them in the database.
"""

from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.logging import logger
from src.database.models import IPO
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
            
            open_date = Normalizer.parse_date(raw.get("verified_open_date") or raw.get("announced_open_date"))
            close_date = Normalizer.parse_date(raw.get("verified_close_date") or raw.get("announced_close_date"))

            ipo = await self.repo.create_or_update_ipo(
                symbol=symbol,
                company_name=company_name,
                industry=raw.get("industry"),
                issue_type=raw.get("issue_type", "MAINBOARD"),
                announced_open_date=open_date,
                announced_close_date=close_date,
                verified_open_date=open_date,
                verified_close_date=close_date,
                min_price=raw.get("min_price"),
                max_price=raw.get("max_price"),
                lot_size=raw.get("lot_size"),
                issue_size_cr=raw.get("issue_size_cr"),
                fresh_issue_cr=raw.get("fresh_issue_cr"),
                ofs_cr=raw.get("ofs_cr"),
            )
            discovered_entities.append(ipo)
            logger.info(f"Discovered/Updated IPO: {company_name} ({symbol}) | Dates: {open_date} to {close_date}")

        await self.session.commit()
        return discovered_entities
