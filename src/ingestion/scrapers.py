"""IPO data adapters. No synthetic market values are returned."""
from typing import List, Dict, Any, Optional
from src.common.logging import logger


class BaseScraper:
    source_name: str = "BaseScraper"
    source_tier: str = "TIER_2"


class PortalScraper(BaseScraper):
    """Discovery adapter fails closed until live source adapters are connected."""
    source_name = "IndianIPOAggregator"
    source_tier = "TIER_2"

    async def fetch_upcoming_ipos(self) -> List[Dict[str, Any]]:
        logger.warning("No live IPO source adapter is configured; returning zero candidates rather than synthetic data.")
        return []

    async def fetch_live_gmp(self, symbol: str) -> Optional[Dict[str, Any]]:
        logger.info("GMP unavailable: no live source adapter configured for %s.", symbol)
        return None

    async def fetch_subscription_status(self, symbol: str) -> Optional[Dict[str, Any]]:
        logger.info("Subscription data unavailable: no live source adapter configured for %s.", symbol)
        return None
