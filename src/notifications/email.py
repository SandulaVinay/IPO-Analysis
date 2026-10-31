"""
Email Notification Provider (SMTP with a local-only console stub).
Supports plain-text research reports and validated PDF attachments.
"""

import smtplib
import ssl
from pathlib import Path
from email.mime.application import MIMEApplication
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
        smtp_user = (settings.smtp_user or "").strip()
        # Google displays app passwords in four-character groups. Remove embedded
        # spaces/newlines so a copied key is submitted as the expected 16 characters.
        # App passwords are often copied with embedded whitespace. Remove all
        # whitespace characters, including tabs and non-ASCII line separators.
        smtp_password = "".join((settings.smtp_password or "").split())

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
            logger.info("Email console stub invoked locally; no email was sent.")
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
        if not smtp_user:
            missing.append("SMTP_USER")
        if not smtp_password:
            missing.append("SMTP_PASSWORD")
        if not to_addr:
            missing.append("EMAIL_TO")
        if missing:
            error = "Missing required SMTP configuration: " + ", ".join(missing)
            logger.error(error)
            return {"success": False, "delivered": False, "mocked": False, "message_id": None, "error": error}

        try:
            msg = MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"] = (settings.email_from or smtp_user).strip()
            msg["To"] = to_addr
            msg.attach(MIMEText(content, "plain", "utf-8"))

            attachments = (metadata or {}).get("attachments", [])
            if attachments and not isinstance(attachments, list):
                raise ValueError("Email attachments must be supplied as a list of report paths.")
            report_root = Path("reports").resolve()
            total_attachment_bytes = 0
            for attachment in attachments:
                path = Path(str(attachment)).resolve()
                if not path.is_relative_to(report_root) or path.suffix.lower() != ".pdf" or not path.is_file():
                    raise ValueError("Email attachments must be existing PDF files inside the reports directory.")
                total_attachment_bytes += path.stat().st_size
                if total_attachment_bytes > 10 * 1024 * 1024:
                    raise ValueError("Email report attachments exceed the 10 MB total limit.")
                attachment_bytes = path.read_bytes()
                if b"%PDF-" not in attachment_bytes[:1024]:
                    raise ValueError("Email attachment is not a recognizable PDF file.")
                part = MIMEApplication(attachment_bytes, _subtype="pdf")
                part.add_header("Content-Disposition", "attachment", filename=path.name)
                msg.attach(part)

            preferred_port = int(settings.smtp_port)
            ports = [preferred_port]
            if settings.smtp_host.strip().lower() in {"smtp.gmail.com", "smtp.googlemail.com"}:
                alternate_port = 465 if preferred_port != 465 else 587
                if alternate_port not in ports:
                    ports.append(alternate_port)

            last_failure = None
            for port_index, port in enumerate(ports):
                stage = "connect"
                try:
                    if port == 465:
                        with smtplib.SMTP_SSL(
                            settings.smtp_host,
                            port,
                            timeout=30,
                            context=ssl.create_default_context(),
                        ) as server:
                            stage = "ehlo"
                            server.ehlo()
                            stage = "login"
                            server.login(smtp_user, smtp_password)
                            stage = "sendmail"
                            refused = server.sendmail(msg["From"], [to_addr], msg.as_string())
                    else:
                        with smtplib.SMTP(settings.smtp_host, port, timeout=30) as server:
                            stage = "ehlo"
                            server.ehlo()
                            stage = "starttls"
                            server.starttls(context=ssl.create_default_context())
                            server.ehlo()
                            stage = "login"
                            server.login(smtp_user, smtp_password)
                            stage = "sendmail"
                            refused = server.sendmail(msg["From"], [to_addr], msg.as_string())

                    if refused:
                        raise smtplib.SMTPRecipientsRefused(refused)
                    last_failure = None
                    break
                except Exception as exc:
                    last_failure = (port, stage, exc)
                    logger.warning(
                        "SMTP attempt failed at stage=%s port=%s (%s).",
                        stage,
                        port,
                        type(exc).__name__,
                    )
                    # Gmail supports implicit TLS on 465 as well as STARTTLS on 587.
                    # Only retry the alternate port when the connection/auth handshake
                    # failed before message submission; never resend after sendmail starts.
                    if stage == "sendmail" or port_index == len(ports) - 1:
                        break

            if last_failure is not None:
                port, stage, exc = last_failure
                if isinstance(exc, smtplib.SMTPAuthenticationError):
                    safe_error = (
                        f"SMTP authentication was rejected by the server (code {exc.smtp_code}) "
                        "during login; verify the SMTP username and current provider app password."
                    )
                elif isinstance(exc, smtplib.SMTPServerDisconnected):
                    safe_error = (
                        f"SMTP server closed the connection during {stage} on port {port}; "
                        "the server returned no authentication status. Check provider account "
                        "security/app-password access and retry from the manual email-test workflow."
                    )
                else:
                    safe_error = (
                        f"SMTP failed during {stage} on port {port} "
                        f"({type(exc).__name__}); check TLS settings and runner network access."
                    )
                logger.error("Email dispatch failed (%s); credentials and message data were not logged.", type(exc).__name__)
                return {
                    "success": False,
                    "delivered": False,
                    "mocked": False,
                    "message_id": None,
                    "error": safe_error,
                }

            message_id = f"smtp_{int(__import__('time').time())}"
            logger.info("Email successfully accepted by SMTP server; final inbox delivery is not confirmed.")
            return {
                "success": True,
                "accepted": True,
                "delivered": False,
                "mocked": False,
                "message_id": message_id,
                "error": None,
            }
        except ValueError as exc:
            # These are fixed validation messages (for example, invalid PDF path,
            # size, or signature); they contain no credentials or recipient data.
            logger.error("Email attachment/message validation failed (ValueError).")
            return {
                "success": False,
                "delivered": False,
                "mocked": False,
                "message_id": None,
                "error": str(exc),
            }
        except Exception as exc:
            logger.error("Email dispatch failure (%s); details redacted.", type(exc).__name__)
            return {
                "success": False,
                "delivered": False,
                "mocked": False,
                "message_id": None,
                "error": f"Email message preparation failed ({type(exc).__name__}).",
            }
