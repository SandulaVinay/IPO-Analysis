"""
Interactive test script for Telegram Bot alerting.
Validates credentials and dispatches a test alert to your chat.
"""

import asyncio
import sys
import httpx

from src.common.config import settings
from src.notifications.telegram import TelegramProvider


async def test_telegram_connection() -> int:
    token = settings.telegram_bot_token.strip()
    chat_id = settings.telegram_chat_id.strip()

    print("========================================")
    print("Telegram Bot Connectivity & Dispatch Test")
    print("========================================")

    if not token:
        print("❌ TELEGRAM_BOT_TOKEN is missing or empty in .env")
        print("   Create a bot with @BotFather to get your token.")
        return 1

    if not chat_id:
        print("❌ TELEGRAM_CHAT_ID is missing or empty in .env")
        print("   Get your numeric user ID from @userinfobot on Telegram.")
        return 1

    # Step 1: Validate bot token with getMe
    print(f"Connecting to Telegram API...")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            data = res.json()
            if not data.get("ok"):
                print(f"❌ Invalid bot token: {data.get('description', 'Unknown error')}")
                return 1

            bot_info = data.get("result", {})
            print(f"✅ Bot Connected Successfully!")
            print(f"   Bot Name:     {bot_info.get('first_name')}")
            print(f"   Bot Username: @{bot_info.get('username')}")
            print(f"   Target Chat:  {chat_id}")
    except Exception as exc:
        print(f"❌ Failed to reach Telegram API: {type(exc).__name__}: {exc}")
        return 1

    # Step 2: Send test alert
    print("\nSending test alert message...")
    provider = TelegramProvider()
    # Temporarily ensure provider is enabled for testing
    original_enabled = settings.enable_telegram
    settings.enable_telegram = True

    try:
        result = await provider.send_notification(
            recipient=chat_id,
            subject="IPO Analysis Bot Alert Test",
            content=(
                "🚀 *Telegram Bot Setup Complete!*\n\n"
                "You will now receive:\n"
                "• Daily Indian IPO Status Digest with PDF reports\n"
                "• Real-time Corporate Quarterly Results Alerts\n"
                "• Verified Prospectus & Filing Evidence\n\n"
                "_This is a verified test dispatch from your IPO Analysis platform._"
            ),
        )

        if result.get("success"):
            print(f"✅ Test Alert Sent Successfully! (Message ID: {result.get('message_id')})")
            print("   Check your Telegram app to view the alert.")
            return 0
        else:
            print(f"❌ Failed to send alert: {result.get('error')}")
            print("   Tip: Did you click 'Start' (/start) on your bot first?")
            return 1
    finally:
        settings.enable_telegram = original_enabled


if __name__ == "__main__":
    code = asyncio.run(test_telegram_connection())
    sys.exit(code)
