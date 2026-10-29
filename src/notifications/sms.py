"""
SMS and Console Notification Providers.
"""

from typing import Dict, Any, Optional
from src.common.config import settings
from src.common.logging import logger
from src.notifications.provider import NotificationProvider


class SMSProvider(NotificationProvider):
    """SMS Notification Provider Adapter."""

    @property
    def channel_name(self) -> str:
        return "SMS"

    async def send_notification(
        self,
        recipient: str,
        subject: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fail closed until a real SMS provider adapter is implemented."""
        if not settings.enable_sms:
            return {
                "success": False,
                "delivered": False,
                "mocked": False,
                "message_id": None,
                "error": "SMS is disabled",
            }
        logger.warning("SMS is not implemented as a real delivery provider; no message was sent.")
        return {
            "success": False,
            "delivered": False,
            "mocked": False,
            "message_id": None,
            "error": "SMS provider adapter is not implemented",
        }


class ConsoleProvider(NotificationProvider):
    """Standard Terminal Console & Webhook Provider Adapter."""

    @property
    def channel_name(self) -> str:
        return "CONSOLE"

    async def send_notification(
        self,
        recipient: str,
        subject: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Never treat console logging as notification delivery."""
        if settings.app_env == "production":
            logger.warning("Console notifications are disabled in production; no message was sent.")
            return {"success": False, "delivered": False, "mocked": False, "message_id": None, "error": "Console notifications are disabled in production"}
        logger.info("Console notification provider is a local-only stub; no message was sent.")
        return {"success": False, "delivered": False, "mocked": True, "message_id": None, "error": "Console provider does not deliver messages"}
