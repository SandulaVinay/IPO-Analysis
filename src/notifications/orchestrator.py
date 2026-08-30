"""
Notification Orchestrator.
Coordinates alert scheduling, idempotency checks, delivery tracking, and automatic provider fallback:
Primary (WhatsApp) -> Secondary (Email) -> Backup (SMS / Console).
"""

from datetime import datetime
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.config import settings
from src.common.logging import logger
from src.common.timezone import get_current_ist_time, format_ist
from src.database.models import IPO, Alert, Notification, NotificationAttempt
from src.database.repository import IPORepository
from src.notifications.whatsapp import WhatsAppProvider
from src.notifications.email import EmailProvider
from src.notifications.sms import SMSProvider
from src.notifications.console import ConsoleProvider
from src.reporting.generator import ReportGenerator


class NotificationOrchestrator:
    """Orchestrates notification triggers, delivery tracking, and channel fallbacks."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = IPORepository(session)
        self.providers = [
            WhatsAppProvider(),
            EmailProvider(),
            SMSProvider(),
            ConsoleProvider(),
        ]

    async def trigger_t_minus_2_alert(self, ipo_id: int, analysis_data: Dict[str, Any]) -> bool:
        """Dispatches T-2 calendar day alert or immediate verified alert."""
        ipo = await self.repo.get_ipo_by_id(ipo_id)
        if not ipo:
            return False

        idempotency_key = f"T2_{ipo.symbol}_{ipo.verified_open_date}"
        alert = await self.repo.schedule_alert(
            ipo_id=ipo_id,
            alert_type="T_MINUS_2",
            scheduled_for=datetime.utcnow(),
            idempotency_key=idempotency_key,
        )

        if alert.is_dispatched:
            logger.info(f"T-2 alert already dispatched for {ipo.symbol} (Key: {idempotency_key}). Skipping duplicate.")
            return True

        subject = f"🚨 IPO Alert: {ipo.company_name} — Opens {ipo.verified_open_date} | {analysis_data.get('score_data', {}).get('verdict', 'ATTRACTIVE')}"
        content = ReportGenerator.generate_copy_mode(analysis_data)

        success = await self._dispatch_with_fallback(alert=alert, subject=subject, content=content)
        if success:
            alert.is_dispatched = True
            alert.dispatched_at = datetime.utcnow()
            await self.repo.transition_state(
                ipo_id=ipo_id,
                new_status="T_MINUS_2_ALERT_SENT",
                trigger="NOTIFICATION_ORCHESTRATOR",
                notes=f"T-2 Alert dispatched successfully on {format_ist(get_current_ist_time())}",
            )
            await self.session.commit()

        return success

    async def trigger_6_hour_reminder(self, ipo_id: int, analysis_data: Dict[str, Any]) -> bool:
        """Dispatches 6-hour follow-up reminder."""
        ipo = await self.repo.get_ipo_by_id(ipo_id)
        if not ipo:
            return False

        idempotency_key = f"REM_6HR_{ipo.symbol}_{ipo.verified_open_date}"
        alert = await self.repo.schedule_alert(
            ipo_id=ipo_id,
            alert_type="SIX_HOUR_REMINDER",
            scheduled_for=datetime.utcnow(),
            idempotency_key=idempotency_key,
        )
        if alert.is_dispatched:
            return True

        score = analysis_data.get("score_data", {}).get("overall_score")
        verdict = analysis_data.get("score_data", {}).get("verdict")
        gmp = analysis_data.get("gmp", {}).get("gmp_value", "N/A")
        subject = f"🔔 IPO Reminder: {ipo.company_name} opens in 2 days"
        content = f"""🔔 IPO REMINDER

You received an IPO analysis earlier.

{ipo.company_name} IPO opens on {ipo.verified_open_date}.

Verdict:
{verdict}

Score:
{score}/10

GMP:
₹{gmp}

Review the full analysis before making your decision."""
        success = await self._dispatch_with_fallback(alert=alert, subject=subject, content=content)
        if success:
            alert.is_dispatched = True
            alert.dispatched_at = datetime.utcnow()
            await self.repo.transition_state(ipo_id=ipo_id, new_status="SIX_HOUR_REMINDER_SENT", trigger="NOTIFICATION_ORCHESTRATOR", notes="6-Hour reminder dispatched")
            await self.session.commit()
        return success

    async def trigger_day_before_reminder(self, ipo_id: int, analysis_data: Dict[str, Any]) -> bool:
        """Dispatches Day-Before (T-1) reminder."""
        ipo = await self.repo.get_ipo_by_id(ipo_id)
        if not ipo:
            return False

        idempotency_key = f"T1_{ipo.symbol}_{ipo.verified_open_date}"
        alert = await self.repo.schedule_alert(ipo_id=ipo_id, alert_type="T_MINUS_1", scheduled_for=datetime.utcnow(), idempotency_key=idempotency_key)
        if alert.is_dispatched:
            return True

        score = analysis_data.get("score_data", {}).get("overall_score")
        verdict = analysis_data.get("score_data", {}).get("verdict")
        gmp = analysis_data.get("gmp", {}).get("gmp_value", "N/A")
        subject = f"🚨 IPO OPENS TOMORROW: {ipo.company_name}"
        content = f"""🚨 IPO OPENS TOMORROW

Company:
{ipo.company_name}

Price:
₹{ipo.min_price}–{ipo.max_price}

Lot:
{ipo.lot_size} shares (Min: ₹{round((ipo.min_price or 0)*(ipo.lot_size or 0), 2):,})

Assessment:
{verdict} (Score: {score}/10)

GMP:
₹{gmp}

Review the analysis before deciding."""
        success = await self._dispatch_with_fallback(alert=alert, subject=subject, content=content)
        if success:
            alert.is_dispatched = True
            alert.dispatched_at = datetime.utcnow()
            await self.repo.transition_state(ipo_id=ipo_id, new_status="T_MINUS_1_REMINDER_SENT", trigger="NOTIFICATION_ORCHESTRATOR", notes="T-1 day-before reminder dispatched")
            await self.session.commit()
        return success

    @staticmethod
    def _recipient_for_provider(provider) -> str:
        """Return a recipient valid for the provider being attempted."""
        name = provider.channel_name
        if name == "WHATSAPP":
            return settings.whatsapp_recipient_phone
        if name == "EMAIL":
            return settings.email_to
        if name == "SMS":
            return settings.sms_recipient_phone
        return settings.email_to or settings.whatsapp_recipient_phone

    async def _dispatch_with_fallback(self, alert: Alert, subject: str, content: str) -> bool:
        """Execute fallback chain: WhatsApp -> Email -> SMS -> Console."""
        notif = Notification(
            alert_id=alert.id,
            channel="MULTI_CHANNEL_FALLBACK",
            recipient=settings.email_to or settings.whatsapp_recipient_phone,
            status="QUEUED",
            message_content=content,
        )
        self.session.add(notif)
        await self.session.flush()

        for idx, provider in enumerate(self.providers, 1):
            recipient = self._recipient_for_provider(provider)
            logger.info(f"Attempting notification dispatch via {provider.channel_name} to configured recipient...")
            res = await provider.send_notification(recipient=recipient, subject=subject, content=content)

            attempt = NotificationAttempt(
                notification_id=notif.id,
                attempt_number=idx,
                status="SUCCESS" if res.get("success") and res.get("delivered", False) else ("MOCKED" if res.get("mocked") else "FAILED"),
                provider_message_id=res.get("message_id"),
                error_message=res.get("error"),
            )
            self.session.add(attempt)
            await self.session.flush()

            if res.get("success") and res.get("delivered", False):
                notif.status = "DELIVERED"
                notif.channel = provider.channel_name
                notif.recipient = recipient
                notif.delivered_at = datetime.utcnow()
                logger.info(f"Notification delivered successfully via {provider.channel_name} (Msg ID: {res.get('message_id')})")
                return True

            logger.warning(f"{provider.channel_name} dispatch did not deliver: {res.get('error') or 'mocked/not delivered'}. Falling back to next channel...")

        notif.status = "FAILED"
        await self.session.flush()
        return False
