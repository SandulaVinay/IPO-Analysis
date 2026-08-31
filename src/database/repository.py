"""
Database repository providing transactional helpers and data access abstractions.
"""

from datetime import datetime, date
from typing import List, Optional, Dict, Any
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    IPO,
    IPOEvent,
    IPODocument,
    DocumentVersion,
    Fact,
    Calculation,
    FinancialPeriod,
    Peer,
    Risk,
    Valuation,
    GMPSnapshot,
    SubscriptionSnapshot,
    AnchorInvestor,
    AnalysisRun,
    AnalysisSnapshot,
    Recommendation,
    RecommendationReason,
    Alert,
    Notification,
    NotificationAttempt,
    YouTubeVideo,
    PerformanceOutcome,
    AuditLog,
)


class IPORepository:
    """Repository for IPO data operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_ipo_by_symbol(self, symbol: str) -> Optional[IPO]:
        """Fetch IPO by exact symbol with all relations loaded."""
        stmt = (
            select(IPO)
            .where(IPO.symbol == symbol)
            .options(
                selectinload(IPO.events),
                selectinload(IPO.documents).selectinload(IPODocument.versions),
                selectinload(IPO.facts),
                selectinload(IPO.financial_periods),
                selectinload(IPO.peers),
                selectinload(IPO.risks),
                selectinload(IPO.valuations),
                selectinload(IPO.gmp_snapshots),
                selectinload(IPO.subscription_snapshots),
                selectinload(IPO.anchor_investors),
                selectinload(IPO.analysis_runs).selectinload(AnalysisRun.recommendation).selectinload(Recommendation.reasons),
                selectinload(IPO.youtube_videos),
                selectinload(IPO.performance_outcomes),
            )
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def get_ipo_by_id(self, ipo_id: int) -> Optional[IPO]:
        """Fetch IPO by ID with relations loaded."""
        stmt = (
            select(IPO)
            .where(IPO.id == ipo_id)
            .options(
                selectinload(IPO.events),
                selectinload(IPO.documents).selectinload(IPODocument.versions),
                selectinload(IPO.facts),
                selectinload(IPO.financial_periods),
                selectinload(IPO.peers),
                selectinload(IPO.risks),
                selectinload(IPO.valuations),
                selectinload(IPO.gmp_snapshots),
                selectinload(IPO.subscription_snapshots),
                selectinload(IPO.anchor_investors),
                selectinload(IPO.analysis_runs).selectinload(AnalysisRun.recommendation).selectinload(Recommendation.reasons),
                selectinload(IPO.youtube_videos),
                selectinload(IPO.performance_outcomes),
            )
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def list_all_ipos(self) -> List[IPO]:
        """List all IPOs ordered by verified open date or updated_at."""
        stmt = (
            select(IPO)
            .options(
                selectinload(IPO.events),
                selectinload(IPO.gmp_snapshots),
                selectinload(IPO.analysis_runs).selectinload(AnalysisRun.recommendation),
            )
            .order_by(IPO.verified_open_date.desc().nullslast(), IPO.updated_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create_or_update_ipo(
        self,
        symbol: str,
        company_name: str,
        industry: Optional[str] = None,
        issue_type: str = "MAINBOARD",
        announced_open_date: Optional[date] = None,
        announced_close_date: Optional[date] = None,
        verified_open_date: Optional[date] = None,
        verified_close_date: Optional[date] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        lot_size: Optional[int] = None,
        issue_size_cr: Optional[float] = None,
        fresh_issue_cr: Optional[float] = None,
        ofs_cr: Optional[float] = None,
    ) -> IPO:
        """Create or update core IPO entity."""
        ipo = await self.get_ipo_by_symbol(symbol)
        if not ipo:
            ipo = IPO(
                symbol=symbol,
                company_name=company_name,
                industry=industry,
                issue_type=issue_type,
                announced_open_date=announced_open_date,
                announced_close_date=announced_close_date,
                verified_open_date=verified_open_date,
                verified_close_date=verified_close_date,
                min_price=min_price,
                max_price=max_price,
                lot_size=lot_size,
                min_investment=(min_price * lot_size) if min_price and lot_size else None,
                issue_size_cr=issue_size_cr,
                fresh_issue_cr=fresh_issue_cr,
                ofs_cr=ofs_cr,
                status="IPO_DISCOVERED",
            )
            self.session.add(ipo)
            await self.session.flush()

            # Record initial state event
            event = IPOEvent(
                ipo_id=ipo.id,
                from_status=None,
                to_status="IPO_DISCOVERED",
                trigger="DISCOVERY_ENGINE",
                notes=f"Discovered {company_name} ({symbol})",
            )
            self.session.add(event)
        else:
            # Update fields if provided
            if company_name:
                ipo.company_name = company_name
            if industry:
                ipo.industry = industry
            if announced_open_date:
                ipo.announced_open_date = announced_open_date
            if announced_close_date:
                ipo.announced_close_date = announced_close_date
            if verified_open_date:
                ipo.verified_open_date = verified_open_date
            if verified_close_date:
                ipo.verified_close_date = verified_close_date
            if min_price is not None:
                ipo.min_price = min_price
            if max_price is not None:
                ipo.max_price = max_price
            if lot_size is not None:
                ipo.lot_size = lot_size
            if min_price and lot_size:
                ipo.min_investment = min_price * lot_size
            if issue_size_cr is not None:
                ipo.issue_size_cr = issue_size_cr
            if fresh_issue_cr is not None:
                ipo.fresh_issue_cr = fresh_issue_cr
            if ofs_cr is not None:
                ipo.ofs_cr = ofs_cr

        await self.session.flush()
        return ipo

    async def transition_state(self, ipo_id: int, new_status: str, trigger: str, notes: Optional[str] = None) -> None:
        """Explicitly transition IPO state and persist state event."""
        ipo = await self.get_ipo_by_id(ipo_id)
        if not ipo:
            return
        
        old_status = ipo.status
        if old_status != new_status:
            ipo.status = new_status
            event = IPOEvent(
                ipo_id=ipo_id,
                from_status=old_status,
                to_status=new_status,
                trigger=trigger,
                notes=notes,
            )
            self.session.add(event)
            await self.session.flush()

    async def add_fact(
        self,
        ipo_id: int,
        field_name: str,
        value_text: Optional[str],
        value_numeric: Optional[float],
        value_type: str,
        source_name: str,
        source_url: Optional[str] = None,
        source_tier: str = "TIER_1",
        document_id: Optional[int] = None,
        document_version: Optional[str] = None,
        page_number: Optional[int] = None,
        confidence: str = "HIGH",
        verification_status: str = "VERIFIED",
    ) -> Fact:
        """Store an atomic factual evidence record."""
        fact = Fact(
            ipo_id=ipo_id,
            field_name=field_name,
            value_text=value_text,
            value_numeric=value_numeric,
            value_type=value_type,
            source_name=source_name,
            source_url=source_url,
            source_tier=source_tier,
            document_id=document_id,
            document_version=document_version,
            page_number=page_number,
            confidence=confidence,
            verification_status=verification_status,
        )
        self.session.add(fact)
        await self.session.flush()
        return fact

    async def add_gmp(
        self,
        ipo_id: int,
        gmp_value: float,
        upper_price: float,
        source: str = "GMP Aggregator",
        trend: str = "STABLE",
    ) -> GMPSnapshot:
        """Add Grey Market Premium snapshot."""
        est_price = upper_price + gmp_value
        gain_pct = (gmp_value / upper_price * 100.0) if upper_price > 0 else 0.0
        gmp = GMPSnapshot(
            ipo_id=ipo_id,
            gmp_value=gmp_value,
            upper_price=upper_price,
            estimated_listing_price=est_price,
            potential_listing_gain_pct=gain_pct,
            source=source,
            trend=trend,
        )
        self.session.add(gmp)
        await self.session.flush()
        return gmp

    async def add_subscription(
        self,
        ipo_id: int,
        day_number: int,
        qib_times: float,
        nii_times: float,
        retail_times: float,
        employee_times: float,
        overall_times: float,
    ) -> SubscriptionSnapshot:
        """Add subscription update."""
        sub = SubscriptionSnapshot(
            ipo_id=ipo_id,
            day_number=day_number,
            qib_times=qib_times,
            nii_times=nii_times,
            retail_times=retail_times,
            employee_times=employee_times,
            overall_times=overall_times,
        )
        self.session.add(sub)
        await self.session.flush()
        return sub

    async def schedule_alert(
        self,
        ipo_id: int,
        alert_type: str,
        scheduled_for: datetime,
        idempotency_key: str,
    ) -> Alert:
        """Schedule an alert idempotently."""
        stmt = select(Alert).where(Alert.idempotency_key == idempotency_key)
        res = await self.session.execute(stmt)
        existing = res.scalars().first()
        if existing:
            return existing

        alert = Alert(
            ipo_id=ipo_id,
            alert_type=alert_type,
            scheduled_for=scheduled_for,
            idempotency_key=idempotency_key,
        )
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def log_audit(self, event_type: str, entity_name: str, entity_id: str, description: str, metadata: Optional[Dict] = None) -> None:
        """Log system audit event."""
        log_entry = AuditLog(
            event_type=event_type,
            entity_name=entity_name,
            entity_id=entity_id,
            description=description,
            metadata_json=metadata,
        )
        self.session.add(log_entry)
        await self.session.flush()
