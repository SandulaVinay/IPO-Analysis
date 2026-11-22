"""
Telegram Bot Notification Provider.
Sends real-time IPO intelligence digests and financial results alerts via Telegram Bot API.
100% free and instant push notifications.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import httpx

from src.common.config import settings
from src.common.logging import logger
from src.notifications.provider import NotificationProvider


class TelegramProvider(NotificationProvider):
    """Official Telegram Bot API notification provider."""

    TELEGRAM_API_BASE = "https://api.telegram.org"
    MAX_TEXT_LENGTH = 4000
    MAX_CAPTION_LENGTH = 1000

    @property
    def channel_name(self) -> str:
        return "TELEGRAM"

    async def send_notification(
        self,
        recipient: str,
        subject: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Dispatch message and optional document to Telegram chat."""
        target_chat = (recipient or settings.telegram_chat_id).strip()
        bot_token = settings.telegram_bot_token.strip()

        if not settings.enable_telegram:
            return {
                "success": False,
                "accepted": False,
                "delivered": False,
                "mocked": False,
                "message_id": None,
                "error": "Telegram notifications are disabled",
            }

        if not bot_token or not target_chat:
            return {
                "success": False,
                "accepted": False,
                "delivered": False,
                "mocked": False,
                "message_id": None,
                "error": "Telegram bot token and chat ID must be configured",
            }

        metadata = metadata or {}
        # Resolve attachments if present
        pdf_path: Optional[Path] = None
        attachments = metadata.get("attachments") or []
        if isinstance(attachments, (list, tuple)) and attachments:
            candidate = Path(str(attachments[0])).resolve()
            if candidate.is_file():
                pdf_path = candidate
        elif metadata.get("attachment_path"):
            candidate = Path(str(metadata["attachment_path"])).resolve()
            if candidate.is_file():
                pdf_path = candidate

        full_message = f"🔔 {subject}\n\n{content}".strip()
        url_prefix = f"{self.TELEGRAM_API_BASE}/bot{bot_token}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # If an attachment exists, send via sendDocument first
                if pdf_path and pdf_path.exists():
                    file_bytes = pdf_path.read_bytes()
                    caption = f"🔔 {subject}"[: self.MAX_CAPTION_LENGTH]
                    remaining_text = full_message.strip()

                    doc_res = await client.post(
                        f"{url_prefix}/sendDocument",
                        data={
                            "chat_id": target_chat,
                            "caption": caption,
                        },
                        files={
                            "document": (pdf_path.name, file_bytes, "application/pdf")
                        },
                    )

                    doc_data = doc_res.json()
                    if not doc_data.get("ok"):
                        err_desc = doc_data.get("description", "Unknown Telegram API error")
                        logger.warning("Telegram sendDocument failed: %s", err_desc)
                        return {
                            "success": False,
                            "accepted": False,
                            "delivered": False,
                            "mocked": False,
                            "message_id": None,
                            "error": f"Telegram API error: {err_desc}",
                        }

                    message_id = str(doc_data.get("result", {}).get("message_id", ""))

                    # Send any overflow text
                    if remaining_text:
                        for chunk in self._split_text(remaining_text, self.MAX_TEXT_LENGTH):
                            await client.post(
                                f"{url_prefix}/sendMessage",
                                json={
                                    "chat_id": target_chat,
                                    "text": chunk,
                                },
                            )

                    logger.info("Telegram document successfully sent to chat %s (message ID %s)", target_chat, message_id)
                    return {
                        "success": True,
                        "accepted": True,
                        "delivered": True,
                        "mocked": False,
                        "message_id": message_id,
                        "error": None,
                    }

                # Otherwise send text message(s)
                chunks = self._split_text(full_message, self.MAX_TEXT_LENGTH)
                first_message_id = None

                for chunk in chunks:
                    res = await client.post(
                        f"{url_prefix}/sendMessage",
                        json={
                            "chat_id": target_chat,
                            "text": chunk,
                            "disable_web_page_preview": True,
                        },
                    )

                    data = res.json()
                    if not data.get("ok"):
                        err_desc = data.get("description", "Unknown Telegram API error")
                        logger.warning("Telegram sendMessage failed: %s", err_desc)
                        return {
                            "success": False,
                            "accepted": False,
                            "delivered": False,
                            "mocked": False,
                            "message_id": None,
                            "error": f"Telegram API error: {err_desc}",
                        }

                    if first_message_id is None:
                        first_message_id = str(data.get("result", {}).get("message_id", ""))

                logger.info("Telegram notification successfully sent to chat %s (message ID %s)", target_chat, first_message_id)
                return {
                    "success": True,
                    "accepted": True,
                    "delivered": True,
                    "mocked": False,
                    "message_id": first_message_id,
                    "error": None,
                }

        except Exception as exc:
            logger.warning("Telegram dispatch failed (%s).", type(exc).__name__)
            return {
                "success": False,
                "accepted": False,
                "delivered": False,
                "mocked": False,
                "message_id": None,
                "error": f"Telegram request failed: {type(exc).__name__}",
            }

    @staticmethod
    def _split_text(text: str, max_chars: int) -> List[str]:
        """Split text into chunks smaller than max_chars, preferably along line boundaries."""
        if len(text) <= max_chars:
            return [text]

        chunks = []
        current = []
        current_len = 0

        for line in text.splitlines(keepends=True):
            if current_len + len(line) > max_chars:
                if current:
                    chunks.append("".join(current))
                    current = []
                    current_len = 0
                if len(line) > max_chars:
                    # Line itself is huge, split by chars
                    while len(line) > max_chars:
                        chunks.append(line[:max_chars])
                        line = line[max_chars:]
            current.append(line)
            current_len += len(line)

        if current:
            chunks.append("".join(current))
        return chunks
