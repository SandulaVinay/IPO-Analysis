"""Official WhatsApp Cloud API adapter; acceptance is not final handset delivery."""
from pathlib import Path
from typing import Dict, Any, Optional
from src.common.config import settings
from src.common.logging import logger
from src.ingestion.client import http_client
from src.notifications.provider import NotificationProvider


class WhatsAppProvider(NotificationProvider):
    """Official WhatsApp Cloud API notification provider."""
    @property
    def channel_name(self) -> str:
        return "WHATSAPP"

    async def send_notification(self, recipient: str, subject: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        target_phone = (recipient or settings.whatsapp_recipient_phone).strip()
        if not settings.enable_whatsapp or settings.whatsapp_provider == "console":
            return {"success": False, "accepted": False, "delivered": False, "mocked": False, "message_id": None, "error": "WhatsApp is disabled or configured for console mode"}
        if settings.whatsapp_provider != "cloud_api":
            return {"success": False, "accepted": False, "delivered": False, "mocked": False, "message_id": None, "error": f"Unsupported WhatsApp provider: {settings.whatsapp_provider}"}
        if not settings.whatsapp_phone_number_id or not settings.whatsapp_access_token or not target_phone:
            return {"success": False, "accepted": False, "delivered": False, "mocked": False, "message_id": None, "error": "WhatsApp Cloud API phone-number ID, access token, and recipient must be configured"}
        digits = "".join(ch for ch in target_phone if ch.isdigit())
        if len(digits) < 8:
            return {"success": False, "accepted": False, "delivered": False, "mocked": False, "message_id": None, "error": "Configured WhatsApp recipient is not a valid international phone number"}

        # Outside the 24-hour customer-service window, Meta may require an approved
        # template. Rejection is handled as a provider failure so email can be tried.
        message_body = f"{subject}\n\n{content}".strip()
        if len(message_body) > 4000:
            message_body = message_body[:3970].rstrip() + "\n\n[Shortened; see the report artifact.]"
        url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
        attachment_path = (metadata or {}).get("attachment_path")
        try:
            if attachment_path:
                path = Path(str(attachment_path)).resolve()
                report_root = Path("reports").resolve()
                if not path.is_relative_to(report_root) or path.suffix.lower() != ".pdf" or not path.is_file():
                    raise ValueError("WhatsApp attachments must be existing PDF files inside the reports directory.")
                pdf_bytes = path.read_bytes()
                if b"%PDF-" not in pdf_bytes[:1024]:
                    raise ValueError("WhatsApp attachment is not a recognizable PDF.")
                if len(pdf_bytes) > 10 * 1024 * 1024:
                    raise ValueError("WhatsApp PDF attachment exceeds the 10 MB limit.")

                media_url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/media"
                media_response = await http_client.post(
                    media_url,
                    data={"messaging_product": "whatsapp", "type": "application/pdf"},
                    files={"file": (path.name, pdf_bytes, "application/pdf")},
                    headers=headers,
                    retry_transient=False,
                )
                media_body = media_response.json()
                media_id = media_body.get("id")
                if not media_id:
                    logger.warning("WhatsApp media upload response did not contain a media ID.")
                    return {"success": False, "accepted": False, "delivered": False, "mocked": False, "message_id": None, "error": "WhatsApp media upload returned no media ID"}
                caption = message_body if len(message_body) <= 900 else message_body[:850].rstrip() + "\n\nFull report attached as PDF."
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": digits,
                    "type": "document",
                    "document": {"id": media_id, "filename": path.name, "caption": caption},
                }
            else:
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": digits,
                    "type": "text",
                    "text": {"preview_url": False, "body": message_body},
                }
            response = await http_client.post(url, json=payload, headers=headers, retry_transient=False)
            body = response.json()
            messages = body.get("messages") or []
            message_id = messages[0].get("id") if messages and isinstance(messages[0], dict) else None
            if not message_id:
                logger.warning("WhatsApp API returned success without a message ID.")
                return {"success": False, "accepted": False, "delivered": False, "mocked": False, "message_id": None, "error": "WhatsApp API response did not contain a message ID"}
            return {"success": True, "accepted": True, "delivered": False, "mocked": False, "message_id": message_id, "error": None}
        except Exception as exc:
            # Avoid logging tokens, headers, or raw provider responses.
            logger.warning("WhatsApp Cloud API request failed (%s).", type(exc).__name__)
            return {"success": False, "accepted": False, "delivered": False, "mocked": False, "message_id": None, "error": f"WhatsApp API request failed: {type(exc).__name__}"}
