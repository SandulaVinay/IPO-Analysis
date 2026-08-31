"""
Asynchronous HTTP Client with exponential backoff, rate limiting, and custom headers.
"""

import asyncio
import httpx
from typing import Optional, Dict, Any
from src.common.logging import logger

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,application/json,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class HTTPClient:
    """Resilient HTTP client with retry logic and courteous throttling."""

    def __init__(self, timeout: float = 30.0, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Execute GET request with retry backoff."""
        req_headers = {**DEFAULT_HEADERS, **(headers or {})}
        
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await client.get(url, params=params, headers=req_headers)
                    if response.status_code == 429:  # Rate limited
                        retry_after = int(response.headers.get("Retry-After", 2 * attempt))
                        logger.warning(f"Rate limited on {url}. Backing off for {retry_after}s...")
                        await asyncio.sleep(retry_after)
                        continue
                    
                    response.raise_for_status()
                    return response
                except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                    if attempt == self.max_retries:
                        logger.error(f"HTTP GET failed after {self.max_retries} attempts for {url}: {exc}")
                        raise exc
                    backoff = 2 ** attempt
                    logger.warning(f"HTTP GET attempt {attempt} failed for {url}: {exc}. Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)

        raise httpx.RequestError(f"Failed to execute GET request for {url}")

    async def download_file(self, url: str, destination_path: str) -> str:
        """Download binary file (e.g. PDF) to local filesystem."""
        response = await self.get(url)
        with open(destination_path, "wb") as f:
            f.write(response.content)
        return destination_path


# Global instance
http_client = HTTPClient()
