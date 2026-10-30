"""Asynchronous HTTP client with bounded retries and safe request handling."""
import asyncio
from typing import Optional, Dict, Any
import httpx
from src.common.logging import logger

DEFAULT_HEADERS = {
    "User-Agent": "IPO-Analysis/2.0 (+https://github.com/SandulaVinay/IPO-Analysis)",
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

class HTTPClient:
    """HTTP adapter with bounded retries for transient failures."""
    def __init__(self, timeout: float = 30.0, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    async def _request(self, method: str, url: str, *, params=None, json=None, data=None, files=None, headers=None, retry_transient: bool = True, timeout: Optional[float] = None):
        req_headers = {**DEFAULT_HEADERS, **(headers or {})}
        attempts = self.max_retries if retry_transient else 1
        async with httpx.AsyncClient(timeout=timeout or self.timeout, follow_redirects=True) as client:
            for attempt in range(1, attempts + 1):
                try:
                    response = await client.request(method, url, params=params, json=json, data=data, files=files, headers=req_headers)
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt == attempts:
                            response.raise_for_status()
                        retry_after = response.headers.get("Retry-After")
                        try:
                            delay = min(60, max(1, int(retry_after))) if retry_after else 2 ** attempt
                        except ValueError:
                            delay = 2 ** attempt
                        logger.warning("Transient HTTP %s status %s; retrying in %ss.", method, response.status_code, delay)
                        await asyncio.sleep(delay)
                        continue
                    response.raise_for_status()
                    return response
                except httpx.RequestError as exc:
                    if attempt == attempts:
                        logger.error("HTTP %s failed after %s attempts (%s).", method, self.max_retries, type(exc).__name__)
                        raise
                    delay = min(30, 2 ** attempt)
                    logger.warning("HTTP %s network error (%s); retrying in %ss.", method, type(exc).__name__, delay)
                    await asyncio.sleep(delay)
        raise httpx.RequestError(f"{method} exhausted retries")

    async def get(self, url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, timeout: Optional[float] = None) -> httpx.Response:
        """Execute GET with transient-error retries and an optional per-source timeout."""
        return await self._request("GET", url, params=params, headers=headers, timeout=timeout)

    async def post(self, url: str, *, json: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None, files=None, headers: Optional[Dict[str, str]] = None, retry_transient: bool = True) -> httpx.Response:
        """Execute POST, optionally multipart; disable retries for non-idempotent provider requests."""
        return await self._request("POST", url, json=json, data=data, files=files, headers=headers, retry_transient=retry_transient)

    async def download_file(self, url: str, destination_path: str) -> str:
        """Download binary content to a local path."""
        response = await self.get(url)
        with open(destination_path, "wb") as file_obj:
            file_obj.write(response.content)
        return destination_path

http_client = HTTPClient()
