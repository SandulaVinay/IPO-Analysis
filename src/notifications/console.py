"""
Console / Terminal Notification Provider.
"""

from typing import Dict, Any, Optional
from src.common.logging import logger
from src.common.config import settings
from src.notifications.provider import NotificationProvider


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
