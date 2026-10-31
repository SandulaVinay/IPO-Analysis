"""Send a real SMTP test email using the financial-results email template."""

import asyncio
import sys

from src.common.config import settings
from src.notifications.email import EmailProvider
from src.results.email_analysis import build_results_email
from src.results.email_html import results_email_html


async def main() -> int:
    print(f"APP_ENV={settings.app_env}")
    print(f"EMAIL_ENABLED={settings.enable_email}")
    print(f"EMAIL_PROVIDER={settings.email_provider}")
    print(f"SMTP_HOST={settings.smtp_host}")
    print(f"SMTP_PORT={settings.smtp_port}")
    print(f"SMTP_USER_CONFIGURED={bool(settings.smtp_user)}")
    normalized_password = "".join((settings.smtp_password or "").split())
    print(f"SMTP_PASSWORD_CONFIGURED={bool(normalized_password)}")
    print(f"SMTP_PASSWORD_LENGTH_AFTER_NORMALIZATION={len(normalized_password)}")
    print(f"EMAIL_TO_CONFIGURED={bool(settings.email_to)}")

    if not settings.email_to:
        print("ERROR: EMAIL_TO is not configured; refusing to send.")
        return 2
    if settings.app_env == "production" and settings.email_provider != "smtp":
        print("ERROR: production email testing requires EMAIL_PROVIDER=smtp")
        return 2
    if not settings.enable_email:
        print("ERROR: email delivery is disabled; refusing to send.")
        return 2

    item = {
        "company_name": "Sample Listed Company (TEST DATA ONLY)",
        "symbol": "SAMPLETEST",
        "exchange": "NSE (SIMULATED)",
        "period_ended": "30-Sep-2026",
        "relating_to": "Quarterly Results - SYNTHETIC TEST",
        "broadcast_time": "Workflow template test",
        "audit_status": "Not applicable - synthetic test",
        "consolidation": "Illustrative sample; not verified",
        "attachment_url": "No real filing - synthetic test only",
        "headline": "TEST ONLY: fictional company and financial figures",
    }
    metrics = {
        "status": "EXTRACTED",
        "revenue_cr": 1200.0,
        "pat_cr": 95.0,
        "eps": 12.4,
        "cfo_cr": -18.0,
        "revenue_yoy_pct": -4.2,
        "pat_yoy_pct": -12.5,
        "revenue_qoq_pct": -3.1,
        "pat_qoq_pct": -8.6,
    }
    subject, body = build_results_email(item, metrics)
    subject = "[TEST ONLY - SYNTHETIC FIGURES] " + subject
    body = (
        "TEST EMAIL - SYNTHETIC DATA ONLY. The company and all figures are fictional; "
        "this is not an actual financial filing.\n\n" + body
    )

    result = await EmailProvider().send_notification(
        recipient=settings.email_to,
        subject=subject,
        content=body,
        metadata={"html_body": results_email_html(body)},
    )
    print(f"TEST_SUBJECT={subject}")
    print(f"TEST_BODY_CHARACTERS={len(body)}")
    print(f"ACCEPTED={result.get('accepted', False)}")
    print(f"DELIVERED={result.get('delivered', False)}")
    print(f"MOCKED={result.get('mocked', False)}")
    print(f"MESSAGE_ID={result.get('message_id')}")
    if result.get("error"):
        print(f"ERROR={result['error']}")
    return 0 if result.get("accepted", False) or result.get("delivered", False) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
