"""Daily IPO digest: evidence-linked status summary without unsupported recommendations."""

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from zoneinfo import ZoneInfo

from src.common.config import settings
from src.notifications.email import EmailProvider
from src.notifications.whatsapp import WhatsAppProvider
from src.state.store import StateStore

NSE_IPO_URL = "https://www.nseindia.com/market-data/all-upcoming-issues-ipo"
BSE_IPO_URL = "https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx?id=1&Type=p"
IST = ZoneInfo("Asia/Kolkata")


def _as_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _format_date(value: Any) -> str:
    parsed = _as_date(value)
    return parsed.strftime("%d %b %Y") if parsed else "Not verified"


def _include_ipo(ipo: Any, today: date) -> bool:
    if getattr(ipo, "status", "") == "SOURCE_CONFLICT":
        return True
    close_date = _as_date(getattr(ipo, "verified_close_date", None)) or _as_date(
        getattr(ipo, "announced_close_date", None)
    )
    open_date = _as_date(getattr(ipo, "verified_open_date", None)) or _as_date(
        getattr(ipo, "announced_open_date", None)
    )
    return bool((close_date and close_date >= today) or (open_date and open_date >= today))


def _ipo_status(ipo: Any) -> str:
    if getattr(ipo, "status", "") == "SOURCE_CONFLICT":
        return "WAIT — conflicting official-source dates; do not rely on the timeline until resolved."
    return (
        "UNABLE_TO_ASSESS — verified RHP/DRHP financial inputs are not yet connected. "
        "No APPLY/AVOID or buy/sell recommendation is issued."
    )


def _build_report(ipos: Iterable[Any], *, now: datetime, discovery_run: Optional[Dict[str, Any]]) -> tuple[str, str]:
    today = now.date()
    discovery_status = discovery_run.get("status", "UNKNOWN") if discovery_run else "NOT_RUN"
    selected = [ipo for ipo in ipos if _include_ipo(ipo, today)]
    selected.sort(key=lambda item: (
        _as_date(getattr(item, "verified_open_date", None))
        or _as_date(getattr(item, "announced_open_date", None))
        or date.max,
        str(getattr(item, "company_name", "")),
    ))
    lines = [
        "# Daily Indian IPO status digest",
        "",
        f"- **Generated (IST):** {now.strftime('%d %b %Y, %I:%M %p')}",
        f"- **Latest discovery run status:** {discovery_status}",
        "- **Assessment policy:** no investment recommendation is generated from incomplete or unverified issuer financials.",
        "",
        "## Upcoming / unresolved IPO records",
        "",
    ]
    if discovery_status != "SUCCESS":
        lines.extend([
            "**Warning:** the latest discovery run did not complete successfully. Any listed records are cached state and may be stale; verify the official source pages before acting.",
            "",
        ])
    if not selected:
        lines.extend([
            "No future-dated IPO records or date-conflict records are currently present in persisted state.",
            "This is not proof that no IPOs are upcoming; verify the official exchange pages below and check the latest discovery run status.",
            "",
        ])
    for ipo in selected[:20]:
        symbol = str(getattr(ipo, "symbol", "UNKNOWN"))
        name = str(getattr(ipo, "company_name", symbol))
        open_date = getattr(ipo, "verified_open_date", None) or getattr(ipo, "announced_open_date", None)
        close_date = getattr(ipo, "verified_close_date", None) or getattr(ipo, "announced_close_date", None)
        price_min = getattr(ipo, "min_price", None)
        price_max = getattr(ipo, "max_price", None)
        price_band = (
            f"₹{price_min:,.2f}–₹{price_max:,.2f}"
            if price_min is not None and price_max is not None
            else "Not available from current source adapter"
        )
        lines.extend([
            f"### {name} ({symbol})",
            "",
            f"- Open date: {_format_date(open_date)}",
            f"- Close date: {_format_date(close_date)}",
            f"- Price band: {price_band}",
            f"- Issue size: ₹{getattr(ipo, 'issue_size_cr', None):,.2f} Cr" if getattr(ipo, "issue_size_cr", None) is not None else "- Issue size: Not available",
            f"- Status: {_ipo_status(ipo)}",
            "",
        ])
    if len(selected) > 20:
        lines.extend([f"_Showing 20 of {len(selected)} records._", ""])
    lines.extend([
        "## Official source pages",
        "",
        f"- [NSE upcoming IPO issues]({NSE_IPO_URL})",
        f"- [BSE public issues]({BSE_IPO_URL})",
        "",
        "## Important limitation",
        "",
        "This discovery/status digest is not an investment recommendation or personalized financial advice. Prospectus candidate passages remain UNVERIFIED until financial periods, units, consolidated/standalone basis, and source evidence are reconciled. Do not apply based on this digest alone.",
        "",
    ])
    message = (
        f"Daily IPO status digest — {now.strftime('%d %b %Y')} (IST)\n"
        f"Upcoming/unresolved records: {len(selected)}\n"
        f"Latest discovery status: {discovery_status}\n"
        + ("WARNING: discovery data may be stale. " if discovery_status != "SUCCESS" else "")
        + "\n"
        + "\n\n".join(
            f"{getattr(ipo, 'company_name', getattr(ipo, 'symbol', 'UNKNOWN'))} "
            f"({getattr(ipo, 'symbol', 'UNKNOWN')}): {_ipo_status(ipo)} "
            f"Open {_format_date(getattr(ipo, 'verified_open_date', None) or getattr(ipo, 'announced_open_date', None))}; "
            f"close {_format_date(getattr(ipo, 'verified_close_date', None) or getattr(ipo, 'announced_close_date', None))}."
            for ipo in selected[:8]
        )
        + f"\n\nOfficial NSE: {NSE_IPO_URL}\nOfficial BSE: {BSE_IPO_URL}"
    )
    if len(message) > 3500:
        message = message[:3450].rstrip() + "\n\n[Truncated; full report is in the GitHub Actions artifact.]"
    return "\n".join(lines), message


async def generate_daily_ipo_digest(ipos: Iterable[Any], store: Optional[StateStore] = None) -> Dict[str, Any]:
    """Create a daily artifact and send WhatsApp-first/email-fallback if configured."""
    store = store or StateStore()
    ipos = list(ipos)
    now = datetime.now(IST)
    event_key = f"IPO_DAILY_DIGEST_{now.strftime('%Y-%m-%d')}"
    report_dir = Path("reports/daily")
    report_dir.mkdir(parents=True, exist_ok=True)
    discovery_run = store.latest_run("discover")
    report_text, message = _build_report(ipos, now=now, discovery_run=discovery_run)
    report_path = report_dir / f"ipo_digest_{now.strftime('%Y%m%d')}.md"
    report_path.write_text(report_text, encoding="utf-8")

    if store.has_processed_event(event_key):
        return {
            "status": "ALREADY_SENT",
            "event_key": event_key,
            "report_path": str(report_path),
            "notifications_accepted": 0,
        }

    accepted = False
    channel = None
    whatsapp = await WhatsAppProvider().send_notification(
        recipient=settings.whatsapp_recipient_phone,
        subject=f"Daily IPO status digest — {now.strftime('%d %b %Y')}",
        content=message,
    )
    if whatsapp.get("success") and (whatsapp.get("accepted") or whatsapp.get("delivered")):
        accepted = True
        channel = "WHATSAPP"
    else:
        email = await EmailProvider().send_notification(
            recipient=settings.email_to,
            subject=f"Daily IPO status digest — {now.strftime('%d %b %Y')}",
            content=message + f"\n\nFull Markdown report: {report_path}",
        )
        if email.get("success") and (email.get("accepted") or email.get("delivered")):
            accepted = True
            channel = "EMAIL"

    if accepted:
        store.record_event(
            event_key,
            event_type="DAILY_IPO_DIGEST",
            symbol="ALL",
            event_date=now.strftime("%Y-%m-%d"),
            status="ACCEPTED",
            channel=channel,
        )
        status = "ACCEPTED"
    elif settings.enable_whatsapp or settings.enable_email:
        store.record_event(
            event_key,
            event_type="DAILY_IPO_DIGEST",
            symbol="ALL",
            event_date=now.strftime("%Y-%m-%d"),
            status="FAILED",
            channel=None,
        )
        status = "FAILED"
    else:
        status = "REPORT_ONLY"

    store.record_run(
        command="digest",
        status=status,
        detail=f"records={sum(1 for ipo in ipos if _include_ipo(ipo, now.date()))}; channel={channel or 'NONE'}",
    )
    return {
        "status": status,
        "event_key": event_key,
        "report_path": str(report_path),
        "notifications_accepted": int(accepted),
        "channel": channel,
    }
