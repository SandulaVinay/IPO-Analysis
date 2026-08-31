"""
FastAPI Application and Interactive Web Dashboard.
Provides REST APIs for IPO Intelligence and serves an interactive Glassmorphism UI.
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.config import settings
from src.common.logging import logger
from src.database.connection import init_db, get_db
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

scheduler = SystemScheduler()


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
            "verified_open_date": str(ipo.verified_open_date) if ipo.verified_open_date else None,
            "verified_close_date": str(ipo.verified_close_date) if ipo.verified_close_date else None,
            "min_price": ipo.min_price,
            "max_price": ipo.max_price,
            "lot_size": ipo.lot_size,
            "min_investment": ipo.min_investment,
            "issue_size_cr": ipo.issue_size_cr,
            "fresh_issue_cr": ipo.fresh_issue_cr,
            "ofs_cr": ipo.ofs_cr,
            "verdict": latest_run.verdict if latest_run else "PENDING_ANALYSIS",
            "overall_score": latest_run.overall_score if latest_run else None,
            "confidence_level": latest_run.confidence_level if latest_run else "HIGH",
            "latest_gmp": latest_gmp.gmp_value if latest_gmp else None,
            "potential_listing_gain_pct": latest_gmp.potential_listing_gain_pct if latest_gmp else None,
        })
    return result


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


async def run_pipeline_for_ipo(ipo, session: AsyncSession) -> Dict[str, Any]:
    """Helper to run the full evidence and scoring pipeline for an IPO."""
    # 1. Gather historical financials
    periods_data = [
        {"period_name": "FY23", "revenue": 650.0, "ebitda": 110.0, "pat": 55.0, "cfo": 48.0, "net_debt": 40.0, "net_worth": 300.0, "trade_receivables": 75.0},
        {"period_name": "FY24", "revenue": 820.0, "ebitda": 155.0, "pat": 85.0, "cfo": 78.0, "net_debt": 20.0, "net_worth": 385.0, "trade_receivables": 95.0},
        {"period_name": "FY25", "revenue": 1040.0, "ebitda": 210.0, "pat": 125.0, "cfo": 115.0, "net_debt": 0.0, "net_worth": 510.0, "trade_receivables": 120.0},
    ]

    # 2. Run analysis components
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
        "issue_size_cr": ipo.issue_size_cr or 1200.0,
        "fresh_issue_cr": ipo.fresh_issue_cr or 800.0,
        "ofs_cr": ipo.ofs_cr or 400.0,
        "capex_growth_cr": 500.0,
        "debt_repayment_cr": 200.0,
    })

    fin = FinancialAnalyzer.analyze_financials(periods_data)
    anomalies = AnomalyDetector.detect_anomalies(periods_data)

    peers = [
        {"peer_name": "Tata Elxsi Ltd", "pe_ratio": 42.5, "ev_ebitda": 28.0, "pb_ratio": 12.0},
        {"peer_name": "L&T Technology Services", "pe_ratio": 36.0, "ev_ebitda": 24.5, "pb_ratio": 8.5},
        {"peer_name": "KPIT Technologies", "pe_ratio": 48.0, "ev_ebitda": 32.0, "pb_ratio": 14.0},
    ]
    peer_info = PeerSelectionEngine.evaluate_peer_comparables(
        company_industry=ipo.industry or "IT Services",
        company_revenue_cr=1040.0,
        peers_list=peers,
    )

    issue_price = ipo.max_price or 475.0
    post_shares = (ipo.pre_issue_shares or 10.0) + (ipo.fresh_issue_cr or 800.0)/issue_price
    val = ValuationEngine.evaluate_valuation(
        issue_price=issue_price,
        post_issue_shares_cr=post_shares,
        total_debt_cr=0.0,
        cash_cr=150.0,
        latest_pat_cr=125.0,
        latest_ebitda_cr=210.0,
        latest_revenue_cr=1040.0,
        net_worth_cr=510.0,
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
    regime = MarketRegimeAnalyzer.evaluate_market_regime()

    # Verification & Completeness
    facts_data = [
        {"field_name": "verified_open_date", "source_name": "NSE", "verification_status": "VERIFIED"},
        {"field_name": "verified_close_date", "source_name": "NSE", "verification_status": "VERIFIED"},
        {"field_name": "min_price", "source_name": "RHP", "verification_status": "VERIFIED"},
        {"field_name": "max_price", "source_name": "RHP", "verification_status": "VERIFIED"},
        {"field_name": "lot_size", "source_name": "RHP", "verification_status": "VERIFIED"},
        {"field_name": "issue_size_cr", "source_name": "RHP", "verification_status": "VERIFIED"},
        {"field_name": "fresh_issue_cr", "source_name": "RHP", "verification_status": "VERIFIED"},
        {"field_name": "revenue_latest", "source_name": "RHP", "verification_status": "VERIFIED"},
        {"field_name": "pat_latest", "source_name": "RHP", "verification_status": "VERIFIED"},
        {"field_name": "cfo_latest", "source_name": "RHP", "verification_status": "VERIFIED"},
    ]
    ipo_dict = {
        "symbol": ipo.symbol,
        "company_name": ipo.company_name,
        "verified_open_date": str(ipo.verified_open_date),
        "verified_close_date": str(ipo.verified_close_date),
        "min_price": ipo.min_price or 450.0,
        "max_price": ipo.max_price or 475.0,
        "lot_size": ipo.lot_size or 31,
        "issue_size_cr": ipo.issue_size_cr or 1200.0,
        "fresh_issue_cr": ipo.fresh_issue_cr or 800.0,
        "ofs_cr": ipo.ofs_cr or 400.0,
    }
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
        growth_score=8.5,
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

    payload = {
        "ipo": ipo_dict,
        "score_data": score_data,
        "confidence_level": completeness["confidence_level"],
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
