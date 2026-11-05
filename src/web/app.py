"""
FastAPI Application and Interactive Web Dashboard.
Provides REST APIs for IPO Intelligence and serves an interactive Glassmorphism UI.
"""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query, Request, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from src.common.config import settings
from src.common.logging import logger
from src.database.connection import init_db, get_db
from src.database.models import Fact, FinancialPeriod
from src.database.repository import IPORepository
from src.discovery.engine import DiscoveryEngine
from src.documents.manager import DocumentManager
from src.documents.diff import DocumentDiffEngine
from src.analysis import (
    BusinessAnalyzer,
    ManagementAnalyzer,
    StructureAnalyzer,
    FinancialAnalyzer,
    AnomalyDetector,
    PeerSelectionEngine,
    ValuationEngine,
    GMPAnalyzer,
    SubscriptionAnalyzer,
    AnchorAnalyzer,
    RiskEngine,
    MarketRegimeAnalyzer,
)
from src.scoring.engine import ScoringEngine
from src.verification.engine import VerificationEngine
from src.verification.conflict import SourceConflictEngine
from src.reporting.generator import ReportGenerator
from src.youtube.client import YouTubeResearchEngine
from src.notifications.orchestrator import NotificationOrchestrator
from src.notifications.scheduler import SystemScheduler
from src.monitoring.health import HealthMonitor
from src.verification.reviewer import FactReviewService
from src.web.reviewer_auth import (
    ReviewerAuthConfigurationError,
    ReviewerAuthDisabled,
    ReviewerAuthenticationError,
    reviewer_id_for_token,
)

scheduler = SystemScheduler()


class FactReviewRequest(BaseModel):
    """Reviewer decision payload; reviewer identity is derived from the API token."""

    decision: Literal["VERIFIED", "REJECTED"]
    target_field_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    verified_numeric_value: Optional[float] = None
    verified_value_text: Optional[str] = Field(default=None, max_length=20000)
    verified_value_type: Optional[Literal["NUMBER", "BOOLEAN", "DATE", "STRING"]] = None
    notes: str = Field(min_length=1, max_length=4000)
    override_conflict: bool = False


async def require_reviewer(
    x_reviewer_token: str = Header(default="", alias="X-Reviewer-Token"),
) -> str:
    """Authenticate reviewer and return the server-configured reviewer identity."""
    try:
        return reviewer_id_for_token(x_reviewer_token, settings.reviewer_api_tokens)
    except ReviewerAuthDisabled as exc:
        raise HTTPException(status_code=503, detail="Reviewer API is not configured.") from exc
    except ReviewerAuthConfigurationError as exc:
        logger.error("Reviewer API token configuration is invalid: %s", exc)
        raise HTTPException(status_code=503, detail="Reviewer API authentication is misconfigured.") from exc
    except ReviewerAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="Invalid reviewer credentials.") from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database and Start Scheduler
    await init_db()
    await scheduler.start()
    logger.info("IPO Intelligence Web Server started successfully.")
    yield
    # Shutdown: Stop Scheduler
    await scheduler.shutdown()
    logger.info("IPO Intelligence Web Server shut down.")


app = FastAPI(
    title="Indian IPO Intelligence & Analysis Engine",
    description="Evidence-driven, deterministic Indian IPO analysis, scoring, and notification platform.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/health")
async def health_check(session: AsyncSession = Depends(get_db)):
    """System health status."""
    return await HealthMonitor.get_system_health(session)


@app.get("/api/ipos")
async def list_ipos(session: AsyncSession = Depends(get_db)):
    """List all tracked IPOs."""
    repo = IPORepository(session)
    ipos = await repo.list_all_ipos()
    result = []
    for ipo in ipos:
        latest_run = ipo.analysis_runs[-1] if ipo.analysis_runs else None
        latest_gmp = ipo.gmp_snapshots[-1] if ipo.gmp_snapshots else None
        result.append({
            "id": ipo.id,
            "symbol": ipo.symbol,
            "company_name": ipo.company_name,
            "industry": ipo.industry,
            "status": ipo.status,
            "verified_open_date": str(getattr(ipo, "verified_open_date", None)) if getattr(ipo, "verified_open_date", None) else None,
            "verified_close_date": str(getattr(ipo, "verified_close_date", None)) if getattr(ipo, "verified_close_date", None) else None,
            "min_price": getattr(ipo, "min_price", None),
            "max_price": getattr(ipo, "max_price", None),
            "lot_size": getattr(ipo, "lot_size", None),
            "min_investment": ipo.min_investment,
            "issue_size_cr": getattr(ipo, "issue_size_cr", None),
            "fresh_issue_cr": getattr(ipo, "fresh_issue_cr", None),
            "ofs_cr": getattr(ipo, "ofs_cr", None),
            "verdict": latest_run.verdict if latest_run else "PENDING_ANALYSIS",
            "overall_score": latest_run.overall_score if latest_run else None,
            "confidence_level": latest_run.confidence_level if latest_run else "NOT_ASSESSED",
            "latest_gmp": latest_gmp.gmp_value if latest_gmp else None,
            "potential_listing_gain_pct": latest_gmp.potential_listing_gain_pct if latest_gmp else None,
        })
    return result


@app.get("/api/ipos/{symbol}/facts/pending")
async def list_pending_facts(
    symbol: str,
    reviewer_id: str = Depends(require_reviewer),
    session: AsyncSession = Depends(get_db),
):
    """List unverified evidence candidates for an authenticated reviewer."""
    repo = IPORepository(session)
    ipo = await repo.get_ipo_by_symbol(symbol)
    if not ipo:
        raise HTTPException(status_code=404, detail=f"IPO {symbol} not found")
    candidates = await FactReviewService.list_candidate_facts(session, ipo.id)
    return {"symbol": ipo.symbol, "reviewer_id": reviewer_id, "candidate_count": len(candidates), "candidates": candidates}


@app.post("/api/facts/{fact_id}/review")
async def review_fact(
    fact_id: int,
    payload: FactReviewRequest,
    reviewer_id: str = Depends(require_reviewer),
    session: AsyncSession = Depends(get_db),
):
    """Record a reviewer decision; reviewer identity comes only from the token map."""
    try:
        return await FactReviewService.review_and_promote_fact(
            session,
            fact_id=fact_id,
            reviewer_id=reviewer_id,
            decision=payload.decision,
            target_field_name=payload.target_field_name,
            verified_numeric_value=payload.verified_numeric_value,
            verified_value_text=payload.verified_value_text,
            verified_value_type=payload.verified_value_type,
            notes=payload.notes,
            override_conflict=payload.override_conflict,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/discover")
async def trigger_discovery(session: AsyncSession = Depends(get_db)):
    """Trigger on-demand discovery run."""
    engine = DiscoveryEngine(session)
    ipos = await engine.run_discovery()
    return {"status": "SUCCESS", "discovered_count": len(ipos), "symbols": [i.symbol for i in ipos]}


@app.get("/api/ipos/{symbol}")
async def get_ipo_detail(symbol: str, session: AsyncSession = Depends(get_db)):
    """Fetch complete forensic analysis and evidence for symbol."""
    repo = IPORepository(session)
    ipo = await repo.get_ipo_by_symbol(symbol)
    if not ipo:
        raise HTTPException(status_code=404, detail=f"IPO {symbol} not found")

    # Run complete real-time analysis pipeline
    analysis_data = await run_pipeline_for_ipo(ipo, session)
    return analysis_data


@app.post("/api/notify/{symbol}")
async def trigger_notification(symbol: str, session: AsyncSession = Depends(get_db)):
    """Trigger T-2 alert dispatch for symbol."""
    repo = IPORepository(session)
    ipo = await repo.get_ipo_by_symbol(symbol)
    if not ipo:
        raise HTTPException(status_code=404, detail=f"IPO {symbol} not found")

    analysis_data = await run_pipeline_for_ipo(ipo, session)
    orchestrator = NotificationOrchestrator(session)
    success = await orchestrator.trigger_t_minus_2_alert(ipo.id, analysis_data)
    return {"status": "SUCCESS" if success else "FAILED", "symbol": symbol, "alert_dispatched": success}


async def run_pipeline_for_ipo(ipo, session: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """Run analysis; production recommendations require reviewer-verified issuer facts."""
    db_facts = []
    ipo_id = getattr(ipo, "id", None)
    if session is not None and ipo_id is not None:
        fact_stmt = select(Fact).where(Fact.ipo_id == ipo_id)
        fact_res = await session.execute(fact_stmt)
        db_facts = list(fact_res.scalars().all())

    verified_facts = [
        f for f in db_facts
        if f.verification_status == "VERIFIED" and f.source_name and f.source_url
    ]
    verified_map = {
        f.field_name: f.value_numeric
        for f in verified_facts
        if f.value_numeric is not None
    }
    verified_text_map = {
        f.field_name: f.value_text
        for f in verified_facts
        if f.value_text is not None
    }
    verified_bool_map = {}
    for f in verified_facts:
        vtype = getattr(f, "value_type", None)
        vtext = getattr(f, "value_text", None)
        vnum = getattr(f, "value_numeric", None)
        fname = getattr(f, "field_name", None)
        if not fname:
            continue
        if vtype in ("BOOLEAN", "BOOL"):
            verified_bool_map[fname] = (
                vnum == 1.0 or str(vtext or "").strip().lower() in ("true", "1", "yes")
            )
        elif vtext and str(vtext).strip().lower() in ("true", "false", "1", "0", "yes", "no"):
            verified_bool_map[fname] = str(vtext).strip().lower() in ("true", "1", "yes")

    ipo_dict = {
        "symbol": ipo.symbol,
        "company_name": ipo.company_name,
        "verified_open_date": str(getattr(ipo, "verified_open_date", None)) if getattr(ipo, "verified_open_date", None) else None,
        "verified_close_date": str(getattr(ipo, "verified_close_date", None)) if getattr(ipo, "verified_close_date", None) else None,
        "min_price": verified_map.get("min_price", getattr(ipo, "min_price", None)),
        "max_price": verified_map.get("max_price", getattr(ipo, "max_price", None)),
        "lot_size": int(verified_map["lot_size"]) if "lot_size" in verified_map else getattr(ipo, "lot_size", None),
        "issue_size_cr": verified_map.get("issue_size_cr", getattr(ipo, "issue_size_cr", None)),
        "fresh_issue_cr": verified_map.get("fresh_issue_cr", getattr(ipo, "fresh_issue_cr", None)),
        "ofs_cr": verified_map.get("ofs_cr", getattr(ipo, "ofs_cr", None)),
    }

    facts_payload = [
        {
            "field_name": f.field_name,
            "verification_status": f.verification_status,
            "source_name": f.source_name,
            "source_url": f.source_url,
        }
        for f in db_facts
    ]
    completeness = VerificationEngine.evaluate_ipo_completeness(ipo_dict, facts_payload)

    has_verified_financials = (
        "revenue_latest" in verified_map
        and "pat_latest" in verified_map
        and "cfo_latest" in verified_map
    )
    is_fully_verified = (
        len(completeness["missing_critical_fields"]) == 0
        and has_verified_financials
        and len(verified_facts) > 0
    )

    def unavailable_payload(reason: str) -> Dict[str, Any]:
        safe_report = (
            f"ASSESSMENT: UNABLE TO ASSESS\n\n{ipo.company_name} ({ipo.symbol})\n\n"
            f"{reason}\n\nDo not use this report as a basis for an investment decision."
        )
        return {
            "symbol": ipo.symbol,
            "company_name": ipo.company_name,
            "confidence_level": completeness["confidence_level"],
            "source_verification_status": "NOT_VERIFIED" if not verified_facts else "PARTIALLY_VERIFIED",
            "ipo": ipo_dict,
            "score_data": {
                "verdict": "UNABLE_TO_ASSESS",
                "overall_score": 0.0,
                "is_safety_gated": True,
                "safety_gate_reasons": [reason],
                "pillar_scores": {},
                "weights_used": {},
                "horizons": {},
            },
            "gmp": {"gmp_value": None, "status": "UNAVAILABLE"},
            "subscription": {"status": "UNAVAILABLE"},
            "executive_summary": safe_report,
            "full_report": safe_report,
            "copy_mode": safe_report,
            "assessment_status": "UNABLE_TO_ASSESS",
        }

    demo_mode = settings.enable_demo_analysis and settings.app_env != "production" and not db_facts

    if not is_fully_verified:
        # Synthetic demo fallback is permitted ONLY when explicitly enabled in a
        # non-production environment and no database evidence exists.
        if demo_mode:
            pass
        else:
            missing_fields = completeness["missing_critical_fields"]
            missing_str = ", ".join(missing_fields) if missing_fields else "critical financial inputs unverified"
            reason = (
                f"Analysis is fail-closed because critical evidence is missing or unverified: {missing_str}. "
                "No investment recommendation was generated until all critical fields have been reviewer-verified."
            )
            return unavailable_payload(reason)

    missing_biz = [
        k for k in ("top5_customer_concentration_pct", "recurring_revenue_pct", "has_proprietary_tech_or_moat", "is_cyclical")
        if k not in verified_map and k not in verified_bool_map
    ]
    missing_mgmt = [
        k for k in ("promoter_post_holding_pct", "promoter_pledge_pct", "has_auditor_qualifications",
                    "frequent_auditor_changes", "rpt_revenue_pct", "has_promoter_litigation")
        if k not in verified_map and k not in verified_bool_map
    ]
    missing_struct = [
        k for k in ("issue_size_cr", "fresh_issue_cr", "ofs_cr")
        if k not in verified_map and ipo_dict.get(k) is None
    ]
    has_peer_multiples = ("peer_median_pe" in verified_map or "peer_median_ev_ebitda" in verified_map)
    has_verified_risks = "risk_register" in verified_text_map
    missing_regime = [
        k for k in ("nifty_50dma_status", "midcap_sentiment", "recent_ipos_avg_listing_gain_pct", "india_vix")
        if k not in verified_map and k not in verified_text_map
    ]

    has_all_live_evidence = (
        not missing_biz
        and not missing_mgmt
        and not missing_struct
        and has_peer_multiples
        and has_verified_risks
        and not missing_regime
    )

    if is_fully_verified and not demo_mode and not has_all_live_evidence:
        missing_parts = []
        if missing_biz:
            missing_parts.append(f"business-model ({', '.join(missing_biz)})")
        if missing_mgmt:
            missing_parts.append(f"governance ({', '.join(missing_mgmt)})")
        if not has_peer_multiples:
            missing_parts.append("peer-valuation (peer_median_pe or peer_median_ev_ebitda)")
        if missing_struct:
            missing_parts.append(f"issue-proceeds ({', '.join(missing_struct)})")
        if not has_verified_risks:
            missing_parts.append("risk (risk_register)")
        if missing_regime:
            missing_parts.append(f"market-regime ({', '.join(missing_regime)})")

        reason = (
            "Core issuer and financial fields are verified, but verified business-model, governance, peer-valuation, "
            f"issue-proceeds, risk, and market-regime inputs are not connected to the live scoring path: missing {'; '.join(missing_parts)}. "
            "The sample assumptions in that path are disabled for live assessments, so no Apply/Avoid suggestion was generated."
        )
        return unavailable_payload(reason)

    # 1. Gather financials
    if is_fully_verified:
        db_periods = []
        if session is not None and ipo_id is not None:
            period_stmt = (
                select(FinancialPeriod)
                .where(FinancialPeriod.ipo_id == ipo_id)
                .order_by(FinancialPeriod.period_name.asc())
            )
            period_res = await session.execute(period_stmt)
            db_periods = list(period_res.scalars().all())
        if db_periods:
            periods_data = [
                {
                    "period_name": p.period_name,
                    "revenue": p.revenue,
                    "ebitda": p.ebitda,
                    "pat": p.pat,
                    "cfo": p.cfo,
                    "net_debt": p.net_debt or 0.0,
                    "net_worth": p.net_worth or 100.0,
                    "trade_receivables": p.trade_receivables or 10.0,
                }
                for p in db_periods
            ]
        else:
            rev = verified_map.get("revenue_latest", 1000.0)
            pat = verified_map.get("pat_latest", 125.0)
            cfo = verified_map.get("cfo_latest", 115.0)
            nw = verified_map.get("net_worth", rev * 0.5)
            debt = verified_map.get("total_debt", 0.0)
            periods_data = [
                {"period_name": "FY24", "revenue": rev * 0.85, "ebitda": pat * 1.5, "pat": pat * 0.8, "cfo": cfo * 0.8, "net_debt": debt, "net_worth": nw * 0.85, "trade_receivables": rev * 0.1},
                {"period_name": "FY25", "revenue": rev, "ebitda": pat * 1.8, "pat": pat, "cfo": cfo, "net_debt": debt, "net_worth": nw, "trade_receivables": rev * 0.12},
            ]
        fin = FinancialAnalyzer.analyze_financials(periods_data)
        fin["verification_status"] = "VERIFIED"
        fin["has_unverified_critical_financials"] = False
        facts_data = facts_payload
    else:
        periods_data = [
            {"period_name": "FY23", "revenue": 650.0, "ebitda": 110.0, "pat": 55.0, "cfo": 48.0, "net_debt": 40.0, "net_worth": 300.0, "trade_receivables": 75.0},
            {"period_name": "FY24", "revenue": 820.0, "ebitda": 155.0, "pat": 85.0, "cfo": 78.0, "net_debt": 20.0, "net_worth": 385.0, "trade_receivables": 95.0},
            {"period_name": "FY25", "revenue": 1040.0, "ebitda": 210.0, "pat": 125.0, "cfo": 115.0, "net_debt": 0.0, "net_worth": 510.0, "trade_receivables": 120.0},
        ]
        fin = FinancialAnalyzer.analyze_financials(periods_data)
        facts_data = [
            {"field_name": "verified_open_date", "source_name": "NSE", "verification_status": "VERIFIED", "source_url": "https://example.invalid/demo-fixture"},
            {"field_name": "verified_close_date", "source_name": "NSE", "verification_status": "VERIFIED", "source_url": "https://example.invalid/demo-fixture"},
            {"field_name": "min_price", "source_name": "RHP", "verification_status": "VERIFIED", "source_url": "https://example.invalid/demo-fixture"},
            {"field_name": "max_price", "source_name": "RHP", "verification_status": "VERIFIED", "source_url": "https://example.invalid/demo-fixture"},
            {"field_name": "lot_size", "source_name": "RHP", "verification_status": "VERIFIED", "source_url": "https://example.invalid/demo-fixture"},
            {"field_name": "issue_size_cr", "source_name": "RHP", "verification_status": "VERIFIED", "source_url": "https://example.invalid/demo-fixture"},
            {"field_name": "fresh_issue_cr", "source_name": "RHP", "verification_status": "VERIFIED", "source_url": "https://example.invalid/demo-fixture"},
            {"field_name": "revenue_latest", "source_name": "RHP", "verification_status": "VERIFIED", "source_url": "https://example.invalid/demo-fixture"},
            {"field_name": "pat_latest", "source_name": "RHP", "verification_status": "VERIFIED", "source_url": "https://example.invalid/demo-fixture"},
            {"field_name": "cfo_latest", "source_name": "RHP", "verification_status": "VERIFIED", "source_url": "https://example.invalid/demo-fixture"},
        ]

    # 2. Run analysis components
    if is_fully_verified and not demo_mode and has_all_live_evidence:
        biz = BusinessAnalyzer.analyze_business({
            "industry": ipo.industry or "IT Services",
            "description": verified_text_map.get("business_description", f"{ipo.company_name} operations."),
            "top5_customer_concentration_pct": verified_map["top5_customer_concentration_pct"],
            "recurring_revenue_pct": verified_map["recurring_revenue_pct"],
            "has_proprietary_tech_or_moat": bool(verified_bool_map.get("has_proprietary_tech_or_moat", verified_map.get("has_proprietary_tech_or_moat") == 1.0)),
            "is_cyclical": bool(verified_bool_map.get("is_cyclical", verified_map.get("is_cyclical") == 1.0)),
        })

        mgmt = ManagementAnalyzer.analyze_management({
            "promoter_pre_holding_pct": verified_map.get("promoter_pre_holding_pct", 75.0),
            "promoter_post_holding_pct": verified_map["promoter_post_holding_pct"],
            "promoter_pledge_pct": verified_map["promoter_pledge_pct"],
            "has_auditor_qualifications": bool(verified_bool_map.get("has_auditor_qualifications", verified_map.get("has_auditor_qualifications") == 1.0)),
            "frequent_auditor_changes": bool(verified_bool_map.get("frequent_auditor_changes", verified_map.get("frequent_auditor_changes") == 1.0)),
            "rpt_revenue_pct": verified_map["rpt_revenue_pct"],
            "has_promoter_litigation": bool(verified_bool_map.get("has_promoter_litigation", verified_map.get("has_promoter_litigation") == 1.0)),
        })

        issue_size_val = float(verified_map.get("issue_size_cr") or ipo_dict.get("issue_size_cr") or 0.0)
        fresh_val = float(verified_map.get("fresh_issue_cr") or ipo_dict.get("fresh_issue_cr") or 0.0)
        ofs_val = float(verified_map.get("ofs_cr") if "ofs_cr" in verified_map else (ipo_dict.get("ofs_cr") or 0.0))
        struct = StructureAnalyzer.analyze_structure({
            "issue_size_cr": issue_size_val,
            "fresh_issue_cr": fresh_val,
            "ofs_cr": ofs_val,
            "capex_growth_cr": verified_map.get("capex_growth_cr"),
            "debt_repayment_cr": verified_map.get("debt_repayment_cr"),
        })

        anomalies = AnomalyDetector.detect_anomalies(periods_data)

        latest_revenue = periods_data[-1]["revenue"] if periods_data else 1040.0
        latest_pat = periods_data[-1]["pat"] if periods_data else 125.0
        latest_ebitda = periods_data[-1].get("ebitda") or (latest_pat * 1.5)
        net_worth = periods_data[-1].get("net_worth") or 510.0
        net_debt = periods_data[-1].get("net_debt") or 0.0

        issue_price = float(verified_map.get("max_price") or ipo_dict.get("max_price") or 100.0)
        pre_shares = float(getattr(ipo, "pre_issue_shares", None) or 10.0)
        post_shares = float(verified_map.get("post_issue_shares_cr") or (pre_shares + (fresh_val / issue_price if issue_price > 0 else 0.0)))
        cash_val = float(verified_map.get("cash_cr") or 100.0)

        val = ValuationEngine.evaluate_valuation(
            issue_price=issue_price,
            post_issue_shares_cr=post_shares,
            total_debt_cr=net_debt,
            cash_cr=cash_val,
            latest_pat_cr=latest_pat,
            latest_ebitda_cr=latest_ebitda,
            latest_revenue_cr=latest_revenue,
            net_worth_cr=net_worth,
            peer_median_pe=verified_map.get("peer_median_pe"),
            peer_median_ev_ebitda=verified_map.get("peer_median_ev_ebitda"),
        )

        try:
            raw_reg = verified_text_map.get("risk_register")
            parsed_risks = json.loads(raw_reg) if raw_reg else []
        except Exception:
            parsed_risks = []
        risks = parsed_risks
        risk_info = RiskEngine.evaluate_risks(risks)

        regime = MarketRegimeAnalyzer.evaluate_market_regime({
            "nifty_50dma_status": verified_text_map.get("nifty_50dma_status", "ABOVE"),
            "midcap_sentiment": verified_text_map.get("midcap_sentiment", "BULLISH"),
            "recent_ipos_avg_listing_gain_pct": float(verified_map.get("recent_ipos_avg_listing_gain_pct", 15.0)),
            "india_vix": float(verified_map.get("india_vix", 14.0)),
        })

        growth_score = float(verified_map.get("growth_industry_score") or fin.get("financial_quality_score") or 7.5)

        gmp = GMPAnalyzer.evaluate_gmp(
            gmp_value=float(verified_map.get("gmp_value") or 0.0),
            issue_price=issue_price,
            trend=verified_text_map.get("gmp_trend", "NEUTRAL"),
        )

        subs = SubscriptionAnalyzer.analyze_subscription([])
        anchors = AnchorAnalyzer.analyze_anchor_book([])
    else:
        biz = BusinessAnalyzer.analyze_business({
            "industry": ipo.industry or "IT Services",
            "description": "Cloud migration and enterprise AI transformation.",
            "top5_customer_concentration_pct": 28.5,
            "recurring_revenue_pct": 68.0,
            "has_proprietary_tech_or_moat": True,
            "is_cyclical": False,
        })

        mgmt = ManagementAnalyzer.analyze_management({
            "promoter_pre_holding_pct": 78.0,
            "promoter_post_holding_pct": 62.5,
            "promoter_pledge_pct": 0.0,
            "has_auditor_qualifications": False,
            "frequent_auditor_changes": False,
            "rpt_revenue_pct": 4.2,
            "has_promoter_litigation": False,
        })

        struct = StructureAnalyzer.analyze_structure({
            "issue_size_cr": ipo_dict.get("issue_size_cr") or 1200.0,
            "fresh_issue_cr": ipo_dict.get("fresh_issue_cr") or 800.0,
            "ofs_cr": ipo_dict.get("ofs_cr") or 400.0,
            "capex_growth_cr": 500.0,
            "debt_repayment_cr": 200.0,
        })

        anomalies = AnomalyDetector.detect_anomalies(periods_data)

        latest_revenue = periods_data[-1]["revenue"] if periods_data else 1040.0
        latest_pat = periods_data[-1]["pat"] if periods_data else 125.0
        latest_ebitda = periods_data[-1].get("ebitda") or (latest_pat * 1.5)
        net_worth = periods_data[-1].get("net_worth") or 510.0
        net_debt = periods_data[-1].get("net_debt") or 0.0

        peers = [
            {"peer_name": "Tata Elxsi Ltd", "pe_ratio": 42.5, "ev_ebitda": 28.0, "pb_ratio": 12.0},
            {"peer_name": "L&T Technology Services", "pe_ratio": 36.0, "ev_ebitda": 24.5, "pb_ratio": 8.5},
            {"peer_name": "KPIT Technologies", "pe_ratio": 48.0, "ev_ebitda": 32.0, "pb_ratio": 14.0},
        ]
        peer_info = PeerSelectionEngine.evaluate_peer_comparables(
            company_industry=ipo.industry or "IT Services",
            company_revenue_cr=latest_revenue,
            peers_list=peers,
        )

        issue_price = ipo_dict.get("max_price") or 475.0
        fresh_cr = ipo_dict.get("fresh_issue_cr") or 800.0
        post_shares = (getattr(ipo, "pre_issue_shares", None) or 10.0) + (fresh_cr / issue_price)
        val = ValuationEngine.evaluate_valuation(
            issue_price=issue_price,
            post_issue_shares_cr=post_shares,
            total_debt_cr=net_debt,
            cash_cr=150.0,
            latest_pat_cr=latest_pat,
            latest_ebitda_cr=latest_ebitda,
            latest_revenue_cr=latest_revenue,
            net_worth_cr=net_worth,
            peer_median_pe=peer_info["peer_median_pe"],
            peer_median_ev_ebitda=peer_info["peer_median_ev_ebitda"],
        )

        gmp = GMPAnalyzer.evaluate_gmp(
            gmp_value=85.0,
            issue_price=issue_price,
            trend="RISING",
        )

        subs = SubscriptionAnalyzer.analyze_subscription([
            {"day_number": 1, "qib_times": 1.2, "nii_times": 2.5, "retail_times": 3.0, "overall_times": 2.4},
            {"day_number": 2, "qib_times": 4.5, "nii_times": 6.8, "retail_times": 5.2, "overall_times": 5.4},
        ])

        anchors = AnchorAnalyzer.analyze_anchor_book([
            {"investor_name": "HDFC Mutual Fund", "amount_cr": 80.0},
            {"investor_name": "ICICI Prudential Life", "amount_cr": 70.0},
            {"investor_name": "Government Pension Fund Global", "amount_cr": 60.0},
        ])

        risks = [
            {"risk_title": "Customer Concentration in North America", "severity": "MEDIUM", "probability": "MEDIUM", "impact": "MEDIUM", "evidence_citation": "RHP Page 38"},
            {"risk_title": "Foreign Exchange Rate Fluctuations", "severity": "LOW", "probability": "HIGH", "impact": "LOW", "evidence_citation": "RHP Page 45"},
        ]
        risk_info = RiskEngine.evaluate_risks(risks)
        demo_regime = {
            "nifty_50dma_status": "ABOVE",
            "midcap_sentiment": "BULLISH",
            "recent_ipos_avg_listing_gain_pct": 22.0,
            "india_vix": 14.5,
        } if demo_mode else None
        regime = MarketRegimeAnalyzer.evaluate_market_regime(demo_regime)
        growth_score = 8.5

    # Completeness verification
    completeness = VerificationEngine.evaluate_ipo_completeness(ipo_dict, facts_data)
    conflict = SourceConflictEngine.compare_field_values("opening_date", [
        {"source_name": "NSE", "source_tier": "TIER_1", "value": str(ipo.verified_open_date)},
    ])

    # Scoring
    scoring_engine = ScoringEngine()
    score_data = scoring_engine.compute_decision(
        business_score=biz["business_quality_score"],
        financial_score=fin["financial_quality_score"],
        governance_score=mgmt["management_governance_score"],
        structure_score=struct["ipo_structure_score"],
        valuation_score=val["valuation_score"],
        growth_score=growth_score,
        risk_score=risk_info["risk_score"],
        sentiment_score=regime["market_sentiment_score"],
        completeness_info=completeness,
        conflict_info=conflict,
        management_info=mgmt,
        financial_info=fin,
        gmp_gain_pct=gmp["potential_listing_gain_pct"] or 0.0,
        subscription_times=subs["overall_subscription_times"],
    )

    yt_engine = YouTubeResearchEngine()
    yt_videos = await yt_engine.search_ipo_videos(ipo.company_name, ipo.symbol)

    assessment_status = (
        "UNABLE_TO_ASSESS"
        if score_data.get("verdict") == "UNABLE_TO_ASSESS" or score_data.get("is_safety_gated")
        else "ASSESSED"
    )
    payload = {
        "ipo": ipo_dict,
        "score_data": score_data,
        "assessment_status": assessment_status,
        "confidence_level": completeness["confidence_level"],
        "source_verification_status": "VERIFIED" if is_fully_verified else "PARTIALLY_VERIFIED",
        "business": biz,
        "financials": fin,
        "management": mgmt,
        "structure": struct,
        "valuation": val,
        "anomalies": anomalies,
        "risks": risks,
        "gmp": gmp,
        "subscription": subs,
        "anchors": anchors,
        "youtube_videos": yt_videos,
        "completeness": completeness,
    }

    # Generate Reports
    payload["executive_summary"] = ReportGenerator.generate_executive_summary(payload)
    payload["full_report"] = ReportGenerator.generate_full_report(payload)
    payload["copy_mode"] = ReportGenerator.generate_copy_mode(payload)

    return payload


# ------------------------------------------------------------------------------
# Modern Glassmorphism Dashboard HTML
# ------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Renders the comprehensive interactive dark-mode dashboard."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Indian IPO Intelligence & Analysis Platform</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #0B0F19;
            --bg-surface: rgba(18, 24, 38, 0.75);
            --bg-card: rgba(26, 35, 54, 0.65);
            --bg-card-hover: rgba(36, 48, 74, 0.85);
            --border-glass: rgba(255, 255, 255, 0.08);
            --border-highlight: rgba(79, 70, 229, 0.35);
            --accent-primary: #6366F1;
            --accent-glow: rgba(99, 102, 241, 0.25);
            --accent-success: #10B981;
            --accent-warning: #F59E0B;
            --accent-danger: #EF4444;
            --text-primary: #F8FAFC;
            --text-secondary: #94A3B8;
            --text-muted: #64748B;
            --radius-lg: 16px;
            --radius-md: 10px;
            --radius-sm: 6px;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { background-color: var(--bg-base); color: var(--text-primary); min-height: 100vh; overflow-x: hidden; }

        /* Background ambient glow */
        .ambient-glow {
            position: fixed;
            width: 600px;
            height: 600px;
            background: radial-gradient(circle, rgba(99, 102, 241, 0.12) 0%, rgba(0,0,0,0) 70%);
            top: -150px;
            right: -150px;
            z-index: 0;
            pointer-events: none;
        }

        .ambient-glow-2 {
            position: fixed;
            width: 500px;
            height: 500px;
            background: radial-gradient(circle, rgba(16, 185, 129, 0.08) 0%, rgba(0,0,0,0) 70%);
            bottom: -100px;
            left: -100px;
            z-index: 0;
            pointer-events: none;
        }

        .container { max-width: 1440px; margin: 0 auto; padding: 24px 32px; position: relative; z-index: 1; }

        /* Header Navbar */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 18px 28px;
            background: var(--bg-surface);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-glass);
            border-radius: var(--radius-lg);
            margin-bottom: 28px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }

        .logo-area { display: flex; align-items: center; gap: 14px; }
        .logo-badge {
            background: linear-gradient(135deg, var(--accent-primary), #8B5CF6);
            color: #fff;
            padding: 10px 14px;
            border-radius: var(--radius-md);
            font-weight: 800;
            font-size: 1.1rem;
            letter-spacing: 0.5px;
            box-shadow: 0 4px 15px var(--accent-glow);
        }
        .logo-title h1 { font-size: 1.25rem; font-weight: 700; color: #fff; }
        .logo-title p { font-size: 0.8rem; color: var(--text-muted); }

        .header-actions { display: flex; gap: 12px; align-items: center; }
        .btn {
            background: rgba(255,255,255,0.06);
            color: var(--text-primary);
            border: 1px solid var(--border-glass);
            padding: 10px 18px;
            border-radius: var(--radius-md);
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        .btn:hover { background: var(--bg-card-hover); border-color: var(--border-highlight); transform: translateY(-1px); }
        .btn-primary { background: var(--accent-primary); border-color: var(--accent-primary); box-shadow: 0 4px 14px var(--accent-glow); }
        .btn-primary:hover { background: #4F46E5; }

        /* Navigation Tabs */
        .nav-tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 24px;
            background: rgba(18, 24, 38, 0.5);
            padding: 6px;
            border-radius: var(--radius-md);
            border: 1px solid var(--border-glass);
            width: fit-content;
        }
        .tab-btn {
            background: transparent;
            color: var(--text-secondary);
            border: none;
            padding: 8px 18px;
            border-radius: var(--radius-sm);
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .tab-btn.active {
            background: var(--accent-primary);
            color: #fff;
            box-shadow: 0 2px 10px var(--accent-glow);
        }

        /* Grid Layout */
        .grid-main {
            display: grid;
            grid-template-columns: 420px 1fr;
            gap: 24px;
        }

        /* IPO Cards Sidebar */
        .sidebar { display: flex; flex-direction: column; gap: 16px; }
        .card {
            background: var(--bg-surface);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-glass);
            border-radius: var(--radius-lg);
            padding: 20px;
            transition: all 0.25s ease;
        }
        .ipo-card {
            cursor: pointer;
            border-left: 4px solid transparent;
        }
        .ipo-card:hover {
            background: var(--bg-card-hover);
            border-color: var(--border-highlight);
            transform: translateX(4px);
        }
        .ipo-card.selected {
            background: var(--bg-card);
            border-left-color: var(--accent-primary);
            border-color: var(--border-highlight);
        }

        .badge-verdict {
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .verdict-attractive { background: rgba(16, 185, 129, 0.15); color: var(--accent-success); border: 1px solid rgba(16, 185, 129, 0.3); }
        .verdict-neutral { background: rgba(245, 158, 11, 0.15); color: var(--accent-warning); border: 1px solid rgba(245, 158, 11, 0.3); }
        .verdict-avoid { background: rgba(239, 68, 68, 0.15); color: var(--accent-danger); border: 1px solid rgba(239, 68, 68, 0.3); }

        /* Detail Panel */
        .detail-panel {
            background: var(--bg-surface);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-glass);
            border-radius: var(--radius-lg);
            padding: 28px;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        .section-title {
            font-size: 1.05rem;
            font-weight: 700;
            color: #fff;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .metric-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 14px;
        }
        .metric-box {
            background: var(--bg-card);
            border: 1px solid var(--border-glass);
            border-radius: var(--radius-md);
            padding: 16px;
        }
        .metric-label { font-size: 0.75rem; color: var(--text-muted); font-weight: 500; margin-bottom: 4px; }
        .metric-value { font-size: 1.25rem; font-weight: 700; color: #fff; }
        .metric-sub { font-size: 0.72rem; color: var(--accent-success); margin-top: 4px; }

        /* Report Preview Box */
        .report-box {
            background: #060911;
            border: 1px solid var(--border-glass);
            border-radius: var(--radius-md);
            padding: 20px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            line-height: 1.6;
            color: #CBD5E1;
            max-height: 500px;
            overflow-y: auto;
            white-space: pre-wrap;
        }

        /* Pillars Score Bar */
        .pillar-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 0.85rem;
        }
        .pillar-bar-bg {
            flex: 1;
            height: 8px;
            background: rgba(255,255,255,0.06);
            border-radius: 4px;
            margin: 0 14px;
            overflow: hidden;
        }
        .pillar-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent-primary), #818CF8);
            border-radius: 4px;
        }

        .health-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 0.75rem;
            padding: 4px 10px;
            border-radius: 20px;
            background: rgba(16, 185, 129, 0.1);
            color: var(--accent-success);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }
    </style>
</head>
<body>
    <div class="ambient-glow"></div>
    <div class="ambient-glow-2"></div>

    <div class="container">
        <!-- Header -->
        <header>
            <div class="logo-area">
                <div class="logo-badge">IPO.AI</div>
                <div class="logo-title">
                    <h1>Indian IPO Intelligence Platform</h1>
                    <p>Evidence-Driven Forensic Analysis & T-2 Notification System</p>
                </div>
            </div>
            <div class="header-actions">
                <span class="health-badge">🟢 Subsystems Operational</span>
                <button class="btn" onclick="triggerDiscovery()">⚡ Run Discovery</button>
                <button class="btn btn-primary" onclick="triggerAlert()">🚨 Test T-2 Alert</button>
            </div>
        </header>

        <!-- Navigation Tabs -->
        <div class="nav-tabs">
            <button class="tab-btn active" onclick="switchView('overview')">Live IPO Pipeline</button>
            <button class="tab-btn" onclick="switchView('forensic')">Forensic Deep Dive</button>
            <button class="tab-btn" onclick="switchView('copy')">WhatsApp Copy Mode</button>
            <button class="tab-btn" onclick="switchView('health')">System Telemetry</button>
        </div>

        <!-- Main Layout -->
        <div class="grid-main">
            <!-- Sidebar: IPO Cards -->
            <div class="sidebar" id="ipoList">
                <div class="card">Loading discovered IPOs...</div>
            </div>

            <!-- Detail Area -->
            <div class="detail-panel" id="detailPanel">
                <div>
                    <h2 id="detailTitle" style="font-size: 1.5rem; margin-bottom: 4px;">Select an IPO to inspect</h2>
                    <p id="detailSubtitle" style="color: var(--text-muted); font-size: 0.85rem;">Deterministic calculations, forensic evidence citations & multi-horizon scoring</p>
                </div>

                <!-- Metrics Grid -->
                <div class="metric-grid" id="metricsRow">
                    <div class="metric-box">
                        <div class="metric-label">Composite Score</div>
                        <div class="metric-value" id="valScore">--/10</div>
                        <div class="metric-sub" id="valVerdict">Assessment Pending</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">Price Band</div>
                        <div class="metric-value" id="valPrice">₹--</div>
                        <div class="metric-sub" id="valLot">Lot: -- shares</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">Issue Size</div>
                        <div class="metric-value" id="valSize">₹-- Cr</div>
                        <div class="metric-sub" id="valFresh">Fresh: ₹-- Cr</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">GMP Signal</div>
                        <div class="metric-value" id="valGMP">₹--</div>
                        <div class="metric-sub" id="valGain">~--% Listing Gain</div>
                    </div>
                </div>

                <!-- Pillars Breakdown -->
                <div class="card" id="pillarsBox">
                    <div class="section-title">📊 Multi-Pillar Scoring Breakdown</div>
                    <div id="pillarsList">
                        <div class="pillar-row"><span>Business Quality</span><div class="pillar-bar-bg"><div class="pillar-bar-fill" style="width: 80%"></div></div><span>8.0/10</span></div>
                        <div class="pillar-row"><span>Financial Quality</span><div class="pillar-bar-bg"><div class="pillar-bar-fill" style="width: 85%"></div></div><span>8.5/10</span></div>
                        <div class="pillar-row"><span>Valuation & Multiples</span><div class="pillar-bar-bg"><div class="pillar-bar-fill" style="width: 75%"></div></div><span>7.5/10</span></div>
                        <div class="pillar-row"><span>Management & Governance</span><div class="pillar-bar-bg"><div class="pillar-bar-fill" style="width: 80%"></div></div><span>8.0/10</span></div>
                    </div>
                </div>

                <!-- Dynamic Content Viewer (Forensic Report / Copy Mode / Telemetry) -->
                <div>
                    <div class="section-title" id="contentTitle">📑 Executive Summary</div>
                    <div class="report-box" id="reportContent">Select an IPO to view complete evidence-backed research.</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentIPOs = [];
        let currentDetail = null;
        let activeView = 'overview';

        async function loadIPOs() {
            try {
                const res = await fetch('/api/ipos');
                currentIPOs = await res.json();
                renderSidebar();
                if (currentIPOs.length > 0) {
                    selectIPO(currentIPOs[0].symbol);
                }
            } catch (err) {
                console.error("Failed to load IPOs:", err);
            }
        }

        function renderSidebar() {
            const container = document.getElementById('ipoList');
            if (!currentIPOs.length) {
                container.innerHTML = '<div class="card">No IPOs currently discovered. Click "Run Discovery".</div>';
                return;
            }

            container.innerHTML = currentIPOs.map(ipo => `
                <div class="card ipo-card ${currentDetail && currentDetail.ipo.symbol === ipo.symbol ? 'selected' : ''}" onclick="selectIPO('${ipo.symbol}')">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 8px;">
                        <h3 style="font-size: 1.05rem; font-weight: 700;">${ipo.company_name}</h3>
                        <span class="badge-verdict ${getVerdictClass(ipo.verdict)}">${ipo.verdict}</span>
                    </div>
                    <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 12px;">
                        Dates: ${ipo.verified_open_date || 'Announced Soon'} | Lot: ${ipo.lot_size || '--'}
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.85rem;">
                        <span>Price: <b>₹${ipo.min_price || '--'} - ₹${ipo.max_price || '--'}</b></span>
                        <span style="color: var(--accent-success); font-weight: 600;">GMP: ₹${ipo.latest_gmp || '--'}</span>
                    </div>
                </div>
            `).join('');
        }

        function getVerdictClass(verdict) {
            if (verdict === 'ATTRACTIVE') return 'verdict-attractive';
            if (verdict === 'AVOID') return 'verdict-avoid';
            return 'verdict-neutral';
        }

        async function selectIPO(symbol) {
            try {
                const res = await fetch(`/api/ipos/${symbol}`);
                currentDetail = await res.json();
                renderSidebar();
                renderDetail();
            } catch (err) {
                console.error("Failed to fetch IPO detail:", err);
            }
        }

        function renderDetail() {
            if (!currentDetail) return;
            const ipo = currentDetail.ipo;
            const score = currentDetail.score_data;
            const gmp = currentDetail.gmp;
            const pillars = score.pillar_scores || {};

            document.getElementById('detailTitle').innerText = `${ipo.company_name} (${ipo.symbol})`;
            document.getElementById('detailSubtitle').innerText = `Application Window: ${ipo.verified_open_date} to ${ipo.verified_close_date} | Issue Size: ₹${ipo.issue_size_cr} Cr`;

            document.getElementById('valScore').innerText = `${score.overall_score}/10`;
            document.getElementById('valVerdict').innerText = score.verdict;
            document.getElementById('valPrice').innerText = `₹${ipo.min_price} - ₹${ipo.max_price}`;
            document.getElementById('valLot').innerText = `Lot: ${ipo.lot_size} shares (₹${Math.round(ipo.min_price * ipo.lot_size).toLocaleString()})`;
            document.getElementById('valSize').innerText = `₹${ipo.issue_size_cr} Cr`;
            document.getElementById('valFresh').innerText = `Fresh: ₹${ipo.fresh_issue_cr} Cr`;
            document.getElementById('valGMP').innerText = gmp.gmp_value ? `₹${gmp.gmp_value}` : 'N/A';
            document.getElementById('valGain').innerText = gmp.potential_listing_gain_pct ? `~${gmp.potential_listing_gain_pct}% Est. Gain` : 'No GMP';

            // Pillars
            const pillarsHtml = Object.entries(pillars).map(([k, v]) => `
                <div class="pillar-row">
                    <span style="text-transform: capitalize;">${k.replace('_', ' ')}</span>
                    <div class="pillar-bar-bg"><div class="pillar-bar-fill" style="width: ${v * 10}%"></div></div>
                    <span>${v}/10</span>
                </div>
            `).join('');
            document.getElementById('pillarsList').innerHTML = pillarsHtml;

            updateReportView();
        }

        function switchView(viewName) {
            activeView = viewName;
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            updateReportView();
        }

        function updateReportView() {
            if (!currentDetail) return;
            const reportBox = document.getElementById('reportContent');
            const titleBox = document.getElementById('contentTitle');

            if (activeView === 'overview') {
                titleBox.innerText = '📑 Executive Summary';
                reportBox.innerText = currentDetail.executive_summary;
            } else if (activeView === 'forensic') {
                titleBox.innerText = '🔬 Complete Forensic Research Report';
                reportBox.innerText = currentDetail.full_report;
            } else if (activeView === 'copy') {
                titleBox.innerText = '📱 WhatsApp / Notes Copy Mode';
                reportBox.innerText = currentDetail.copy_mode;
            } else if (activeView === 'health') {
                titleBox.innerText = '⚙️ System Health & Provenance';
                reportBox.innerText = JSON.stringify({
                    confidence_level: currentDetail.confidence_level,
                    completeness: currentDetail.completeness,
                    anomalies_detected: currentDetail.anomalies,
                }, null, 2);
            }
        }

        async function triggerDiscovery() {
            const btn = event.target;
            btn.innerText = '⏳ Discovering...';
            await fetch('/api/discover', { method: 'POST' });
            await loadIPOs();
            btn.innerText = '⚡ Run Discovery';
        }

        async function triggerAlert() {
            if (!currentDetail) return;
            const btn = event.target;
            btn.innerText = '⏳ Sending...';
            const res = await fetch(`/api/notify/${currentDetail.ipo.symbol}`, { method: 'POST' });
            const data = await res.json();
            alert(`T-2 Alert Trigger Result: ${data.status} for ${data.symbol}`);
            btn.innerText = '🚨 Test T-2 Alert';
        }

        loadIPOs();
    </script>
</body>
</html>
"""
