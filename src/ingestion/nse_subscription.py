"""
Parser for NSE's IPO current-issue feed (subscription multiple per issue).

Source: https://www.nseindia.in/api/ipo-current-issue (official NSE site, owner-confirmed).
Field meanings (observed in a real response):
  noOfTime        overall subscription multiple, NSE bids only, across all categories
  noOfsharesBid   shares bid so far
  noOfSharesOffered  shares offered
These figures are the latest reported for the issue. They are not a final Day 3 figure
while bidding is still open. Parsing is pure: no network access here.
"""

from typing import Any, Dict, Optional

NSE_SUBSCRIPTION_URL = "https://www.nseindia.in/api/ipo-current-issue"


def _number(value: Any) -> Optional[float]:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if number != number or number < 0:  # NaN or negative
        return None
    return number


def parse_nse_subscription_payload(payload: Any) -> Dict[str, Dict[str, Any]]:
    """Return {symbol: {overall_times, bids, offered, issue_end_date}} for rows with a usable multiple."""
    if not isinstance(payload, list):
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        # Only the whole-issue row. Some feeds add per-category rows; they must not overwrite it.
        category = str(item.get("category") or "Total").strip().lower()
        if category != "total":
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        overall = _number(item.get("noOfTime"))
        if not symbol or overall is None:
            continue
        result[symbol] = {
            "overall_times": overall,
            "bids": _number(item.get("noOfsharesBid")),
            "offered": _number(item.get("noOfSharesOffered")),
            "issue_end_date": item.get("issueEndDate"),
        }
    return result
