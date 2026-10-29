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
        """Output notification cleanly to console logs."""
        border = "=" * 60
        logger.info(f"\n{border}\n📢 [NOTIFICATION DISPATCH: {subject}]\nTo: {recipient}\n{border}\n{content}\n{border}\n")
        return {
            "success": True,
            "message_id": f"console_{int(__import__('time').time())}",
            "error": None,
        }
