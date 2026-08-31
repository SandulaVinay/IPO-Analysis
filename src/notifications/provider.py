"""
Abstract Base Class for Notification Providers.
Ensures provider-agnostic notification dispatch (WhatsApp, Email, SMS, Webhook).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class NotificationProvider(ABC):
    """Abstract interface for all notification channel implementations."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Channel identifier: WHATSAPP, EMAIL, SMS, CONSOLE."""
        pass

    @abstractmethod
    async def send_notification(
        self,
        recipient: str,
        subject: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Dispatch message to recipient.
        Returns dict: {"success": bool, "message_id": Optional[str], "error": Optional[str]}
        """
        pass
