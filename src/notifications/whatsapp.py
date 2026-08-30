"""
WhatsApp Business / Cloud API Notification Provider.
Policy-compliant official API integration and explicit mock handling.
"""

from typing import Dict, Any, Optional
from src.common.config import settings
from src.common.logging import logger
from src.ingestion.client import http_client
from src.notifications.provider import NotificationProvider


class WhatsAppProvider(NotificationProvider):
    """WhatsApp Cloud API and Twilio WhatsApp adapter."""

    @property
    def channel_name(self) -> str:
        return "WHATSAPP"

    async def send_notification(
        self,
        recipient: str,
        subject: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Dispatch only when a real WhatsApp provider is enabled.

        Disabled/console mode must return failure so the orchestrator can
        continue to Email/SMS instead of falsely treating a mock as delivered.
        """
        target_phone = recipient or settings.whatsapp_recipient_phone

        if not settings.enable_whatsapp or settings.whatsapp_provider == "console":
            logger.info("WhatsApp is disabled/console mode; falling back to the next notification channel.")
            return {
                "success": False,
                "delivered": False,
                "mocked": False,
                "message_id": None,
                "error": "WhatsApp is disabled or configured for console mode",
            }

        if settings.whatsapp_provider == "cloud_api":
            if not settings.whatsapp_phone_number_id or not settings.whatsapp_access_token:
                err = "WhatsApp Cloud API credentials missing (PHONE_NUMBER_ID or ACCESS_TOKEN)."
                logger.error(err)
                return {"success": False, "delivered": False, "mocked": False, "message_id": None, "error": err}

            url = f"https://graph.facebook.com/v18.0/{settings.whatsapp_phone_number_id}/messages"
            headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
            payload = {
                "messaging_product": "whatsapp",
                "to": target_phone.replace("+", ""),
                "type": "text",
                "text": {"body": content},
            }
            try:
                # The current HTTP client exposes GET only; do not claim a live
                # WhatsApp delivery until a real POST implementation is available.
                res = await http_client.get(url)
                logger.warning("WhatsApp Cloud API is not yet wired to a POST request; treating this attempt as failed.")
                return {
                    "success": False,
                    "delivered": False,
                    "mocked": False,
                    "message_id": None,
                    "error": "WhatsApp Cloud API POST delivery is not implemented yet",
                }
            except Exception as e:
                logger.error(f"WhatsApp Cloud API dispatch error: {e}")
                return {"success": False, "delivered": False, "mocked": False, "message_id": None, "error": str(e)}

        return {
            "success": False,
            "delivered": False,
            "mocked": False,
            "message_id": None,
            "error": f"Unsupported WhatsApp provider: {settings.whatsapp_provider}",
        }
