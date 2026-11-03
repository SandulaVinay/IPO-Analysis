"""Daily IPO digest: evidence-linked status summary without unsupported recommendations."""

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from zoneinfo import ZoneInfo

from src.common.config import settings
from src.common.logging import logger
from src.notifications.email import EmailProvider
from src.notifications.whatsapp import WhatsAppProvider
from src.state.store import StateStore
from src.reporting.pdf import markdown_to_pdf
from src.reporting.email_html import digest_email_html

NSE_IPO_URL = "https://www.nseindia.com/market-data/all-upcoming-issues-ipo"
BSE_IPO_URL = "https://www.bseindia.com/markets/PublicIssues/Issuesummary.aspx"
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


def _format_ipo_date(ipo: Any, side: str) -> str:
    verified = _as_date(getattr(ipo, f"verified_{side}_date", None))
    announced = _as_date(getattr(ipo, f"announced_{side}_date", None))
    if verified:
        return f"{verified.strftime('%d %b %Y')} (official-source date)"
    if announced:
        return f"{announced.strftime('%d %b %Y')} (announced; not verified)"
    return "Not verified"


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
        return "WAIT — conflicting official-source dates or pricing metadata; verify the conflicting field before relying on it."
    return (
        "UNABLE_TO_ASSESS — verified RHP/DRHP financial inputs are not yet connected. "
        "No APPLY/AVOID or buy/sell recommendation is issued."
    )



def _verified_rating(ipo: Any) -> Dict[str, Any]:
    """Use the latest ungated analysis run; otherwise fail closed and show no numeric score."""
    runs = list(getattr(ipo, "analysis_runs", None) or [])
    runs.sort(key=lambda item: getattr(item, "run_timestamp", None) or datetime.min, reverse=True)
    listing = long_term = None
    verified = False
    if runs:
        run = runs[0]
        try:
            listing = float(getattr(run, "listing_opportunity_score"))
            long_term = float(getattr(run, "long_term_opportunity_score"))
            completeness = float(getattr(run, "data_completeness_pct", 0) or 0)
            verified_sources = int(getattr(run, "verified_sources_count", 0) or 0)
            conflicts = int(getattr(run, "conflicts_count", 0) or 0)
            verified = (
                not bool(getattr(run, "is_safety_gated", True))
                and str(getattr(run, "verdict", "UNABLE_TO_ASSESS")) != "UNABLE_TO_ASSESS"
                and completeness >= 80
                and verified_sources > 0
                and conflicts == 0
            )
        except (TypeError, ValueError, AttributeError):
            verified = False
    else:
        # Supports explicitly verified precomputed ratings without requiring an ORM analysis run.
        listing = getattr(ipo, "listing_potential_score", None)
        long_term = getattr(ipo, "long_term_quality_score", None)
        verified = bool(getattr(ipo, "rating_verified", False))
    try:
        listing = float(listing)
        long_term = float(long_term)
    except (TypeError, ValueError):
        return {"available": False}
    if not verified or not (0 <= listing <= 10 and 0 <= long_term <= 10):
        return {"available": False}
    return {
        "available": True,
        "listing": listing,
        "long_term": long_term,
        "overall": round((0.4 * listing) + (0.6 * long_term), 1),
    }


def _company_source_links(ipo: Any) -> list[tuple[str, str]]:
    """Collect source URLs attached to this issuer; never imply a generic exchange page is issuer-specific."""
    links: list[tuple[str, str]] = []
    seen = set()

    def add(label: str, url: Any) -> None:
        value = str(url or "").strip()
        if value.startswith("https://") and value not in seen:
            seen.add(value)
            links.append((label, value))

    for item in (getattr(ipo, "document_links", None) or []):
        if isinstance(item, dict):
            add(str(item.get("document_title") or item.get("document_type") or "Issuer document"), item.get("source_url") or item.get("url"))
    add("Issuer source", getattr(ipo, "source_url", None))
    for document in (getattr(ipo, "documents", None) or []):
        for version in (getattr(document, "versions", None) or []):
            add(str(getattr(document, "document_title", None) or getattr(document, "document_type", None) or "Issuer document"), getattr(version, "source_url", None))
    return links


def _latest_gmp(ipo: Any, now: datetime) -> str:
    """Display a captured GMP only when its timestamp is recent enough to be useful."""
    snapshots = list(getattr(ipo, "gmp_snapshots", None) or [])
    snapshots.sort(key=lambda item: getattr(item, "captured_at", None) or datetime.min, reverse=True)
    if not snapshots:
        return "Not available from a captured snapshot"
    snapshot = snapshots[0]
    captured = getattr(snapshot, "captured_at", None)
    if not isinstance(captured, datetime):
        return "Not verified — snapshot timestamp missing"
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=IST)
    age_hours = (now - captured.astimezone(IST)).total_seconds() / 3600
    if age_hours < 0 or age_hours > 48:
        return f"Stale snapshot ({captured.astimezone(IST).strftime('%d %b %Y, %I:%M %p IST')}); not used as current GMP"
    source = str(getattr(snapshot, "source", "") or "source not recorded")
    return f"₹{float(snapshot.gmp_value):,.2f} ({source}; captured {captured.astimezone(IST).strftime('%d %b %Y, %I:%M %p IST')})"




def _plain_company_summary(ipo: Any, now: datetime) -> str:
    name = str(getattr(ipo, "company_name", getattr(ipo, "symbol", "UNKNOWN")))
    symbol = str(getattr(ipo, "symbol", "UNKNOWN"))
    rating = _verified_rating(ipo)
    rating_text = (
        f"Overall {rating['overall']:.1f}/10 (listing {rating['listing']:.1f}/10; long-term {rating['long_term']:.1f}/10)"
        if rating["available"]
        else "Overall rating unavailable — insufficient verified inputs"
    )
    source_links = _company_source_links(ipo)
    sources_text = "\n".join(f"  {label}: {url}" for label, url in source_links)
    if not sources_text:
        sources_text = "  Company-specific prospectus/source link: not captured"
    return (
        f"{name} ({symbol})\n"
        f"  {rating_text}\n"
        f"  GMP: {_latest_gmp(ipo, now)}\n"
        f"  Open: {_format_ipo_date(ipo, 'open')}; close: {_format_ipo_date(ipo, 'close')}\n"
        f"  Status: {_ipo_status(ipo)}\n"
        f"{sources_text}"
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
            "This is not proof that no IPOs are upcoming; the latest discovery run and issuer-specific source records must be checked."
            "",
        ])
    for ipo in selected[:20]:
        symbol = str(getattr(ipo, "symbol", "UNKNOWN"))
        name = str(getattr(ipo, "company_name", symbol))
        price_min = getattr(ipo, "min_price", None)
        price_max = getattr(ipo, "max_price", None)
        price_band = (
            f"₹{price_min:,.2f}–₹{price_max:,.2f}"
            if price_min is not None and price_max is not None
            else "Not available from current source adapter"
        )
        rating = _verified_rating(ipo)
        if rating["available"]:
            rating_lines = [
                f"- **Overall rating: {rating['overall']:.1f}/10** (40% listing potential + 60% long-term quality)",
                f"- Listing potential: {rating['listing']:.1f}/10",
                f"- Long-term quality: {rating['long_term']:.1f}/10",
                f"- Assessment: {'Consider further' if rating['overall'] >= 6.5 else 'High caution'}; this is a score, not a guarantee of listing gains.",
            ]
        else:
            rating_lines = [
                "- **Overall rating: Unavailable / 10** — insufficient verified inputs; no numeric rating or Apply/Avoid recommendation is issued."
            ]
        source_links = _company_source_links(ipo)
        source_lines = [f"- Company-specific source: [{label}]({url})" for label, url in source_links]
        if not source_lines:
            source_lines = ["- Company-specific prospectus/source link: Not captured yet; verify this issuer on the official exchange before acting."]
        lines.extend([
            f"### {name} ({symbol})",
            "",
            f"- Open date: {_format_ipo_date(ipo, 'open')}",
            f"- Close date: {_format_ipo_date(ipo, 'close')}",
            f"- Price band: {price_band}",
            f"- GMP (grey-market premium): {_latest_gmp(ipo, now)}",
            f"- Issue size: ₹{getattr(ipo, 'issue_size_cr', None):,.2f} Cr" if getattr(ipo, "issue_size_cr", None) is not None else "- Issue size: Not available",
            *rating_lines,
            f"- Status: {_ipo_status(ipo)}",
            *source_lines,
            "",
        ])
    if len(selected) > 20:
        lines.extend([f"_Showing 20 of {len(selected)} records._", ""])
    lines.extend([
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
        + "\n\n".join(_plain_company_summary(ipo, now) for ipo in selected[:8])
        + ("\n\nIssuer-specific source links are included under each company when available." if selected else "\n\nNo issuer-specific IPO records or source links were available in persisted state.")
    )
    run_id = os.getenv("GITHUB_RUN_ID")
    repository = os.getenv("GITHUB_REPOSITORY", "SandulaVinay/IPO-Analysis")
    artifact_link = (
        f"\n\nFull PDF report: https://github.com/{repository}/actions/runs/{run_id} "
        "(open the run and download the daily-ipo-digest artifact)."
        if run_id else ""
    )
    if len(message) + len(artifact_link) > 3500:
        keep_chars = max(2500, 3500 - len(artifact_link) - 100)
        message = message[:keep_chars].rstrip() + "\n\n[Truncated; full PDF report is in the GitHub Actions artifact.]"
    message += artifact_link
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
    markdown_to_pdf(report_text, report_path.with_suffix(".pdf"), title="Daily Indian IPO Status Digest")

    # A previous SMTP acceptance is not proof the recipient received the message.
    # Allow an explicitly requested manual resend for the current day's digest, while
    # preserving the normal once-per-day idempotency guard for scheduled runs.
    force_resend = os.getenv("FORCE_RESEND_DIGEST", "").strip().lower() in {"1", "true", "yes"}
    if store.has_processed_event(event_key) and not force_resend:
        logger.info(
            "Daily digest already accepted earlier today; skipping duplicate send. "
            "Set FORCE_RESEND_DIGEST=true only for a deliberate manual retry."
        )
        return {
            "status": "ALREADY_SENT",
            "event_key": event_key,
            "report_path": str(report_path),
            "notifications_accepted": 0,
            "resend_available": True,
        }
    if force_resend and store.has_processed_event(event_key):
        logger.warning("Manual digest resend override enabled for today's already-processed digest.")

    accepted = False
    channel = None
    whatsapp = await WhatsAppProvider().send_notification(
        recipient=settings.whatsapp_recipient_phone,
        subject=f"Daily IPO status digest — {now.strftime('%d %b %Y')}",
        content=message,
        metadata={"attachment_path": str(report_path.with_suffix(".pdf"))},
    )
    if whatsapp.get("success") and (whatsapp.get("accepted") or whatsapp.get("delivered")):
        accepted = True
        channel = "WHATSAPP"
    else:
        email = await EmailProvider().send_notification(
            recipient=settings.email_to,
            subject=f"Daily IPO status digest — {now.strftime('%d %b %Y')}",
            content=message,
            metadata={
                "attachments": [str(report_path.with_suffix(".pdf"))],
                "html_body": digest_email_html(report_text),
            },
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
