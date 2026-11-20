"""Unit tests for Telegram Bot notification provider."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
import httpx

from src.common.config import settings
from src.notifications.telegram import TelegramProvider


@pytest.fixture(autouse=True)
def reset_telegram_settings(monkeypatch):
    monkeypatch.setattr(settings, "enable_telegram", False)
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")


@pytest.mark.asyncio
async def test_telegram_disabled():
    provider = TelegramProvider()
    result = await provider.send_notification("12345", "Test Subject", "Test Content")
    assert result["success"] is False
    assert "disabled" in result["error"].lower()


@pytest.mark.asyncio
async def test_telegram_missing_credentials(monkeypatch):
    monkeypatch.setattr(settings, "enable_telegram", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    provider = TelegramProvider()
    result = await provider.send_notification("12345", "Test Subject", "Test Content")
    assert result["success"] is False
    assert "must be configured" in result["error"].lower()


@pytest.mark.asyncio
async def test_telegram_send_text_success(monkeypatch):
    monkeypatch.setattr(settings, "enable_telegram", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "dummy_token_123")
    monkeypatch.setattr(settings, "telegram_chat_id", "999888")

    provider = TelegramProvider()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 42}}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        result = await provider.send_notification(
            recipient="999888",
            subject="IPO Alert",
            content="Crystal Crop opens today",
        )

        assert result["success"] is True
        assert result["accepted"] is True
        assert result["delivered"] is True
        assert result["message_id"] == "42"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert "sendMessage" in mock_post.call_args[0][0]
        assert call_kwargs["json"]["chat_id"] == "999888"
        assert "Crystal Crop" in call_kwargs["json"]["text"]


@pytest.mark.asyncio
async def test_telegram_markdown_fallback(monkeypatch):
    monkeypatch.setattr(settings, "enable_telegram", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "dummy_token_123")
    monkeypatch.setattr(settings, "telegram_chat_id", "999888")

    provider = TelegramProvider()

    # First call fails with markdown parse error (400), second call succeeds (200)
    fail_resp = MagicMock()
    fail_resp.status_code = 400
    fail_resp.text = "Bad Request: can't find end of the entity"
    fail_resp.json.return_value = {"ok": False, "description": "can't find end"}

    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.json.return_value = {"ok": True, "result": {"message_id": 43}}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=[fail_resp, ok_resp]) as mock_post:
        result = await provider.send_notification(
            recipient="999888",
            subject="Special *Chars* _Test_",
            content="Some text with odd characters [abc",
        )

        assert result["success"] is True
        assert result["message_id"] == "43"
        assert mock_post.call_count == 2
        # Second call does not have parse_mode
        second_call_json = mock_post.call_args_list[1][1]["json"]
        assert "parse_mode" not in second_call_json


@pytest.mark.asyncio
async def test_telegram_send_document_success(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "enable_telegram", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "dummy_token_123")
    monkeypatch.setattr(settings, "telegram_chat_id", "999888")

    pdf_file = tmp_path / "test_digest.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy pdf bytes")

    provider = TelegramProvider()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 99}}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        result = await provider.send_notification(
            recipient="999888",
            subject="Daily Digest",
            content="Daily summary content",
            metadata={"attachments": [str(pdf_file)]},
        )

        assert result["success"] is True
        assert result["message_id"] == "99"
        assert "sendDocument" in mock_post.call_args[0][0]
        data = mock_post.call_args[1]["data"]
        assert data["chat_id"] == "999888"


@pytest.mark.asyncio
async def test_telegram_long_text_chunking(monkeypatch):
    monkeypatch.setattr(settings, "enable_telegram", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "dummy_token_123")
    monkeypatch.setattr(settings, "telegram_chat_id", "999888")

    provider = TelegramProvider()
    long_content = "Line of text\n" * 500  # ~6500 chars

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 101}}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        result = await provider.send_notification(
            recipient="999888",
            subject="Long Text",
            content=long_content,
        )

        assert result["success"] is True
        # Long message should be split into 2 or more chunks
        assert mock_post.call_count >= 2
