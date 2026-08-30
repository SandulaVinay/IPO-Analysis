"""Send a real SMTP test email for GitHub Actions diagnostics."""

import asyncio
import sys

from src.common.config import settings
from src.notifications.email import EmailProvider


async def main() -> int:
    print(f"APP_ENV={settings.app_env}")
    print(f"EMAIL_ENABLED={settings.enable_email}")
    print(f"EMAIL_PROVIDER={settings.email_provider}")
    print(f"SMTP_HOST={settings.smtp_host}")
    print(f"SMTP_PORT={settings.smtp_port}")
    print(f"SMTP_USER_CONFIGURED={bool(settings.smtp_user)}")
    print(f"SMTP_PASSWORD_CONFIGURED={bool(settings.smtp_password)}")
    print(f"EMAIL_TO_CONFIGURED={bool(settings.email_to)}")

    if settings.app_env == "production" and settings.email_provider != "smtp":
        print("ERROR: production email testing requires EMAIL_PROVIDER=smtp")
        return 2

    provider = EmailProvider()
    result = await provider.send_notification(
        recipient=settings.email_to,
        subject="[IPO Analysis] Email Configuration Test",
        content=(
            "This is a real SMTP configuration test from the IPO Analysis GitHub Action.\n\n"
            "If you received this message, SMTP email delivery is configured correctly."
        ),
    )

    print(f"DELIVERED={result.get('delivered', False)}")
    print(f"MOCKED={result.get('mocked', False)}")
    print(f"MESSAGE_ID={result.get('message_id')}")
    if result.get("error"):
        print(f"ERROR={result['error']}")

    return 0 if result.get("delivered", False) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
