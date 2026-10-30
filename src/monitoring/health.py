"""
System Observability, Diagnostics, and Health Monitoring.
Tracks component health: IPO Discovery, Source Verification, Analysis Engine, Database, Notifications, YouTube.
"""

from typing import Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from src.database.models import IPO, AnalysisRun, Notification
from src.common.config import settings
from src.state.store import StateStore


class HealthMonitor:
    """Computes real-time health telemetry across all subsystems."""

    @staticmethod
    async def get_system_health(session: AsyncSession) -> Dict[str, Any]:
        """Returns health status report for dashboard and monitoring."""
        try:
            # 1. Database Health Check
            stmt_ipo = select(IPO)
            res_ipo = await session.execute(stmt_ipo)
            total_ipos = len(list(res_ipo.scalars().all()))
            db_status = "HEALTHY"
        except Exception as e:
            return {
                "system_status": "DEGRADED",
                "database": "ERROR",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

        # 2. Analysis Runs Count
        stmt_runs = select(AnalysisRun)
        res_runs = await session.execute(stmt_runs)
        total_runs = len(list(res_runs.scalars().all()))

        # 3. Notification Status
        stmt_notif = select(Notification)
        res_notif = await session.execute(stmt_notif)
        total_notifs = len(list(res_notif.scalars().all()))

        store = StateStore()
        latest_discovery = store.latest_run("discover")
        latest_results = store.latest_run("results")
        if latest_discovery is None:
            discovery_status = "NOT_RUN"
        elif latest_discovery.get("status") == "SUCCESS":
            discovery_status = "CHECKED"
        else:
            discovery_status = "DEGRADED"

        analysis_safe_mode = settings.app_env == "production" or not settings.enable_demo_analysis
        if analysis_safe_mode:
            analysis_status = "SAFE_MODE"
        else:
            analysis_status = "DEMO_ONLY"

        whatsapp_ready = bool(
            settings.enable_whatsapp
            and settings.whatsapp_provider == "cloud_api"
            and settings.whatsapp_phone_number_id
            and settings.whatsapp_access_token
            and settings.whatsapp_recipient_phone
        )
        email_ready = bool(
            settings.enable_email
            and settings.email_provider == "smtp"
            and settings.smtp_user
            and settings.smtp_password
            and settings.email_to
        )
        notification_status = "CONFIGURED" if (whatsapp_ready or email_ready) else "DISABLED"
        youtube_status = "CONFIGURED" if settings.youtube_api_key else "OPTIONAL_DISABLED"

        system_status = "DEGRADED" if discovery_status == "DEGRADED" else ("SAFE_MODE" if analysis_safe_mode else "HEALTHY")
        return {
            "system_status": system_status,
            "timestamp": datetime.utcnow().isoformat(),
            "subsystems": {
                "ipo_discovery": {"status": discovery_status, "badge": "🟢 CHECKED" if discovery_status == "CHECKED" else ("🔴 DEGRADED" if discovery_status == "DEGRADED" else "🟡 NOT RUN")},
                "source_verification": {"status": "NOT_CONNECTED", "badge": "🟡 NOT CONNECTED"},
                "analysis_engine": {"status": analysis_status, "badge": "🟡 SAFE MODE" if analysis_safe_mode else "🟡 DEMO ONLY"},
                "deterministic_math": {"status": "AVAILABLE", "badge": "🟢 AVAILABLE"},
                "database": {"status": db_status, "badge": "🟢 HEALTHY", "total_ipos_tracked": total_ipos},
                "notifications": {"status": notification_status, "badge": "🟢 CONFIGURED" if notification_status == "CONFIGURED" else "🟡 DISABLED"},
                "financial_results": {"status": latest_results.get("status", "NOT_RUN") if latest_results else "NOT_RUN", "badge": "🟢 CHECKED" if latest_results and latest_results.get("status") == "SUCCESS" else "🟡 NOT RUN"},
                "youtube_research": {"status": youtube_status, "badge": "🟢 CONFIGURED" if youtube_status == "CONFIGURED" else "🟡 OPTIONAL"},
            },
            "metrics": {
                "total_ipos": total_ipos,
                "total_analyses_completed": total_runs,
                "total_notifications_recorded": total_notifs,
            }
        }
