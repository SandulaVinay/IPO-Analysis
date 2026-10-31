"""Safe external-service connectivity diagnostics for GitHub Actions.

This script checks DNS/TCP reachability only. It never reads, prints, or tests
credentials, and it does not send messages or modify repository state.
"""
import os
import socket
import sys
from urllib.parse import urlparse

import httpx

TARGETS = [
    ("Gmail SMTP submission (587)", "smtp.gmail.com", 587),
    ("Gmail SMTP implicit TLS (465)", "smtp.gmail.com", 465),
    ("NSE website HTTPS", "www.nseindia.com", 443),
    ("BSE website HTTPS", "www.bseindia.com", 443),
]


def check_tcp(label: str, host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=8):
            print(f"TCP_REACHABLE {label} host={host} port={port}")
            return True
    except (OSError, socket.timeout) as exc:
        print(f"TCP_UNREACHABLE {label} host={host} port={port} error={type(exc).__name__}")
        return False


def main() -> int:
    failures = 0
    for label, host, port in TARGETS:
        if not check_tcp(label, host, port):
            failures += 1

    # Verify HTTPS can return a response, without logging response bodies/cookies.
    for label, url in [
        ("NSE homepage", "https://www.nseindia.com/"),
        ("BSE announcements", "https://www.bseindia.com/corporates/ann"),
    ]:
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                response = client.get(url, headers={"User-Agent": "Mozilla/5.0 IPO-Analysis diagnostics"})
            print(f"HTTPS_RESPONSE {label} status={response.status_code}")
            if response.status_code >= 500:
                failures += 1
        except Exception as exc:
            print(f"HTTPS_FAILED {label} error={type(exc).__name__}")
            failures += 1

    print(f"DIAGNOSTICS_FAILURES={failures}")
    # Diagnostic failures are informative and should not hide the main workflow
    # result. The dedicated SMTP test step remains responsible for email status.
    return 0


if __name__ == "__main__":
    sys.exit(main())
