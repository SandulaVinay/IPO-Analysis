"""
Ingestion module exports.
"""

from src.ingestion.client import http_client, HTTPClient
from src.ingestion.scrapers import BaseScraper, PortalScraper

__all__ = ["http_client", "HTTPClient", "BaseScraper", "PortalScraper"]
