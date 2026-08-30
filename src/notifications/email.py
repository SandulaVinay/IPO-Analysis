"""
Email Notification Provider (SMTP / Resend / Brevo).
Dispatches rich HTML and clean plain-text research reports directly to user inbox.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
from src.common.config import settings
from src.common.logging import logger
from src.notifications.provider import NotificationProvider


class EmailProvider(NotificationProvider):
    """SMTP & Email Dispatch Adapter."""

    @property
    def channel_name(self) -> str:
        return "EMAIL"

    async def send_notification(
        self,
        recipient: str,
        subject: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Dispatch email via SMTP. Mock mode is explicit and never reports delivery."""
        to_addr = (recipient or settings.email_to).strip()

        # Email is disabled: this is a normal no-op, not a successful delivery.
        if not settings.enable_email:
            logger.info("Email notifications are disabled; no email was sent.")
            return {
                "success": False,
                "delivered": False,
                "mocked": False,
                "message_id": None,
                "error": "Email notifications are disabled",
            }

        # Console provider is development/test only. Never silently mock in production.
        if settings.email_provider == "console":
            if settings.app_env == "production":
                error = "Production email cannot use the console/mock provider; set EMAIL_PROVIDER=smtp."
                logger.error(error)
                return {
                    "success": False,
                    "delivered": False,
                    "mocked": False,
                    "message_id": None,
                    "error": error,
                }
            logger.info(f"[EMAIL MOCK DISPATCH] To: {to_addr} Subject: {subject}")
            return {
                "success": True,
                "delivered": False,
                "mocked": True,
                "message_id": f"email_mock_{int(__import__('time').time())}",
                "error": None,
            }

        if settings.email_provider != "smtp":
            error = f"Unsupported email provider: {settings.email_provider}"
            logger.error(error)
            return {"success": False, "delivered": False, "mocked": False, "message_id": None, "error": error}

        missing = []
        if not settings.smtp_host:
            missing.append("SMTP_HOST")
        if not settings.smtp_user:
            missing.append("SMTP_USER")
        if not settings.smtp_password:
            missing.append("SMTP_PASSWORD")
        if not to_addr:
            missing.append("EMAIL_TO")
        if missing:
            error = "Missing required SMTP configuration: " + ", ".join(missing)
            logger.error(error)
            return {"success": False, "delivered": False, "mocked": False, "message_id": None, "error": error}

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.email_from or settings.smtp_user
            msg["To"] = to_addr
            msg.attach(MIMEText(content, "plain", "utf-8"))

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(settings.smtp_user, settings.smtp_password)
                server.sendmail(msg["From"], [to_addr], msg.as_string())

            message_id = f"smtp_{int(__import__('time').time())}"
            logger.info(f"Email successfully accepted by SMTP server for {to_addr}")
            return {
                "success": True,
                "delivered": True,
                "mocked": False,
                "message_id": message_id,
                "error": None,
            }
        except Exception as e:
            logger.error(f"Email dispatch failure: {type(e).__name__}: {e}")
            return {
                "success": False,
                "delivered": False,
                "mocked": False,
                "message_id": None,
                "error": str(e),
            }
