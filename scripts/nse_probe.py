"""
Read-only probe of NSE IPO endpoints, run from GitHub Actions to capture real responses.

Saves every response (status, content type, body) under the output directory so a parser
can be written against real data. Makes GET requests only. Uses no secrets.
Exit code is always 0 so the artifact is uploaded even when NSE refuses requests.
"""

import json
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

HOME = "https://www.nseindia.com"
REFERER = "https://www.nseindia.com/market-data/all-upcoming-issues-ipo"
CURRENT_ISSUES = "https://www.nseindia.com/api/ipo-current-issue"
MAX_BODY_BYTES = 200_000

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": REFERER,
}

# Candidate per-issue endpoints. Unknown paths are recorded as-is; nothing is assumed to work.
PER_ISSUE_PATHS = [
    "/api/ipo-bid-details?symbol={sym}&series=EQ",
    "/api/ipo-bid-details?symbol={sym}",
    "/api/ipo-active-category?symbol={sym}&series=EQ",
    "/api/ipo-active-category?symbol={sym}",
    "/api/ipo-subscription?symbol={sym}",
]


def _record(out: Path, name: str, response: httpx.Response) -> dict:
    body = response.content[:MAX_BODY_BYTES]
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:120]
    (out / f"{safe}.body").write_bytes(body)
    return {
        "name": name,
        "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "bytes": len(response.content),
        "file": f"{safe}.body",
        "final_url": str(response.url),
    }


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "nse_probe_out")
    out.mkdir(parents=True, exist_ok=True)
    summary: dict = {"results": [], "symbols": [], "error": None}

    try:
        with httpx.Client(timeout=30.0, follow_redirects=True, headers=HEADERS) as client:
            home = client.get(HOME)
            summary["results"].append(_record(out, "home", home))

            current = client.get(CURRENT_ISSUES)
            summary["results"].append(_record(out, "ipo-current-issue", current))
            symbols: list[str] = []
            if current.status_code == 200:
                try:
                    payload = current.json()
                    rows = payload if isinstance(payload, list) else payload.get("data", [])
                    symbols = sorted({str(r.get("symbol")) for r in rows if isinstance(r, dict) and r.get("symbol")})
                except (ValueError, AttributeError) as exc:
                    summary["error"] = f"current issues not JSON: {type(exc).__name__}"
            summary["symbols"] = symbols

            for sym in symbols[:3]:
                for template in PER_ISSUE_PATHS:
                    path = template.format(sym=quote(sym))
                    name = f"{sym}-{path.split('?')[0].split('/')[-1]}-{len(summary['results'])}"
                    resp = client.get(HOME + path)
                    summary["results"].append(_record(out, name, resp))
    except httpx.HTTPError as exc:
        summary["error"] = f"http error: {type(exc).__name__}"

    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    for r in summary["results"]:
        print(f"{r['status']}  {r['bytes']:>8}  {r['content_type'][:40]:<40}  {r['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
