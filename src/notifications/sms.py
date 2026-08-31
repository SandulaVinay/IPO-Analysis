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
        """Dispatch SMS via provider or console fallback."""
        target_phone = recipient or settings.sms_recipient_phone
        logger.info(f"[SMS DISPATCH] To: {target_phone} | Content: {content[:100]}...")
        return {
            "success": True,
            "message_id": f"sms_mock_{int(__import__('time').time())}",
            "error": None,
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
