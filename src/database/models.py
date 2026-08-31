"""
SQLAlchemy database models for the Indian IPO Intelligence System.
Normalized schema supporting complete traceability, immutable snapshots, and provenance.
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Date,
    Text,
    ForeignKey,
    JSON,
    Enum,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class IPO(Base):
    """Core IPO Entity."""
    __tablename__ = "ipos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), unique=True, index=True, nullable=False)
    company_name = Column(String(255), nullable=False, index=True)
    industry = Column(String(100), nullable=True)
    issue_type = Column(String(50), default="MAINBOARD")  # MAINBOARD / SME
    exchange = Column(String(50), default="NSE/BSE")  # NSE, BSE, NSE_SME, BSE_SME

    # Current Lifecycle State
    status = Column(String(50), default="IPO_DISCOVERED", index=True)

    # Dates
    announced_open_date = Column(Date, nullable=True)
    announced_close_date = Column(Date, nullable=True)
    verified_open_date = Column(Date, nullable=True, index=True)
    verified_close_date = Column(Date, nullable=True)
    allotment_date = Column(Date, nullable=True)
    listing_date = Column(Date, nullable=True)

    # Price & Issue Size (in ₹ / ₹ Cr)
    min_price = Column(Float, nullable=True)
    max_price = Column(Float, nullable=True)
    lot_size = Column(Integer, nullable=True)
    min_investment = Column(Float, nullable=True)
    issue_size_cr = Column(Float, nullable=True)
    fresh_issue_cr = Column(Float, nullable=True)
    ofs_cr = Column(Float, nullable=True)

    # Shares
    pre_issue_shares = Column(Float, nullable=True)  # in Cr
    post_issue_shares = Column(Float, nullable=True)  # in Cr

    # Provenance and Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    events = relationship("IPOEvent", back_populates="ipo", cascade="all, delete-orphan")
    documents = relationship("IPODocument", back_populates="ipo", cascade="all, delete-orphan")
    facts = relationship("Fact", back_populates="ipo", cascade="all, delete-orphan")
    financial_periods = relationship("FinancialPeriod", back_populates="ipo", cascade="all, delete-orphan")
    peers = relationship("Peer", back_populates="ipo", cascade="all, delete-orphan")
    risks = relationship("Risk", back_populates="ipo", cascade="all, delete-orphan")
    valuations = relationship("Valuation", back_populates="ipo", cascade="all, delete-orphan")
    gmp_snapshots = relationship("GMPSnapshot", back_populates="ipo", cascade="all, delete-orphan")
    subscription_snapshots = relationship("SubscriptionSnapshot", back_populates="ipo", cascade="all, delete-orphan")
    anchor_investors = relationship("AnchorInvestor", back_populates="ipo", cascade="all, delete-orphan")
    analysis_runs = relationship("AnalysisRun", back_populates="ipo", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="ipo", cascade="all, delete-orphan")
    youtube_videos = relationship("YouTubeVideo", back_populates="ipo", cascade="all, delete-orphan")
    performance_outcomes = relationship("PerformanceOutcome", back_populates="ipo", uselist=False, cascade="all, delete-orphan")


class IPOEvent(Base):
    """Lifecycle state machine history."""
    __tablename__ = "ipo_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    trigger = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    ipo = relationship("IPO", back_populates="events")


class IPODocument(Base):
    """Registered IPO Documents (DRHP, RHP, Addenda)."""
    __tablename__ = "ipo_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    document_type = Column(String(50), nullable=False)  # DRHP, RHP, PRICE_BAND_AD, ADDENDUM
    document_title = Column(String(255), nullable=True)
    latest_version = Column(String(20), default="v1")
    created_at = Column(DateTime, default=datetime.utcnow)

    ipo = relationship("IPO", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")


class DocumentVersion(Base):
    """Immutable document versions with cryptographic hashes."""
    __tablename__ = "document_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("ipo_documents.id"), nullable=False, index=True)
    version_label = Column(String(50), nullable=False)  # v1, v2, update_1
    source_url = Column(Text, nullable=False)
    file_path = Column(Text, nullable=True)
    document_hash = Column(String(64), nullable=False, index=True)  # SHA256
    page_count = Column(Integer, nullable=True)
    publication_date = Column(Date, nullable=True)
    downloaded_at = Column(DateTime, default=datetime.utcnow)
    processing_status = Column(String(50), default="DOWNLOADED")  # DOWNLOADED, PARSED, FAILED

    document = relationship("IPODocument", back_populates="versions")


class Source(Base):
    """Source registries with tier ranking."""
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    source_tier = Column(String(20), nullable=False)  # TIER_1, TIER_2, TIER_3
    base_url = Column(Text, nullable=True)
    confidence_weight = Column(Float, default=1.0)
    is_active = Column(Boolean, default=True)


class Fact(Base):
    """Individual sourced atomic facts with complete provenance."""
    __tablename__ = "facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    field_name = Column(String(100), nullable=False, index=True)
    value_text = Column(Text, nullable=True)
    value_numeric = Column(Float, nullable=True)
    value_type = Column(String(50), default="STRING")  # STRING, NUMBER, DATE, JSON
    
    # Provenance
    source_name = Column(String(100), nullable=False)
    source_url = Column(Text, nullable=True)
    source_tier = Column(String(20), default="TIER_1")  # TIER_1, TIER_2, TIER_3
    document_id = Column(Integer, nullable=True)
    document_version = Column(String(50), nullable=True)
    page_number = Column(Integer, nullable=True)
    
    confidence = Column(String(20), default="HIGH")  # HIGH, MEDIUM, LOW
    verification_status = Column(String(20), default="VERIFIED")  # VERIFIED, UNVERIFIED, CONFLICTED
    extracted_at = Column(DateTime, default=datetime.utcnow)

    ipo = relationship("IPO", back_populates="facts")


class Calculation(Base):
    """Derived deterministic calculations."""
    __tablename__ = "calculations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    calculation_name = Column(String(100), nullable=False, index=True)
    result_numeric = Column(Float, nullable=True)
    result_text = Column(Text, nullable=True)
    formula = Column(Text, nullable=False)
    input_fact_ids = Column(JSON, nullable=True)  # List of Fact IDs used
    calculated_at = Column(DateTime, default=datetime.utcnow)


class FinancialPeriod(Base):
    """Financial statements for a reporting period (FY22, FY23, FY24, etc.)."""
    __tablename__ = "financial_periods"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    period_name = Column(String(50), nullable=False)  # FY23, FY24, FY25, H1-FY26
    period_months = Column(Integer, default=12)
    is_restated = Column(Boolean, default=True)

    # Core Financials (in ₹ Cr)
    revenue = Column(Float, nullable=True)
    ebitda = Column(Float, nullable=True)
    ebit = Column(Float, nullable=True)
    pat = Column(Float, nullable=True)
    eps = Column(Float, nullable=True)  # in ₹
    
    # Cash Flows
    cfo = Column(Float, nullable=True)  # Operating Cash Flow
    fcf = Column(Float, nullable=True)  # Free Cash Flow
    capex = Column(Float, nullable=True)

    # Balance Sheet Items
    total_debt = Column(Float, nullable=True)
    cash_and_equivalents = Column(Float, nullable=True)
    net_debt = Column(Float, nullable=True)
    net_worth = Column(Float, nullable=True)
    working_capital = Column(Float, nullable=True)
    trade_receivables = Column(Float, nullable=True)
    inventories = Column(Float, nullable=True)
    trade_payables = Column(Float, nullable=True)

    # Margins & Ratios
    ebitda_margin_pct = Column(Float, nullable=True)
    pat_margin_pct = Column(Float, nullable=True)
    roe_pct = Column(Float, nullable=True)
    roce_pct = Column(Float, nullable=True)

    ipo = relationship("IPO", back_populates="financial_periods")


class Peer(Base):
    """Comparable listed peers."""
    __tablename__ = "peers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    peer_name = Column(String(150), nullable=False)
    ticker = Column(String(50), nullable=True)
    selection_rationale = Column(Text, nullable=True)
    similarity_score = Column(Float, nullable=True)  # 0.0 - 1.0

    # Peer Financials & Multiples
    revenue_cr = Column(Float, nullable=True)
    pe_ratio = Column(Float, nullable=True)
    pb_ratio = Column(Float, nullable=True)
    ev_ebitda = Column(Float, nullable=True)
    ev_revenue = Column(Float, nullable=True)
    roe_pct = Column(Float, nullable=True)
    roce_pct = Column(Float, nullable=True)

    ipo = relationship("IPO", back_populates="peers")


class Risk(Base):
    """Identified and quantified risk factors."""
    __tablename__ = "risks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    risk_title = Column(String(255), nullable=False)
    risk_category = Column(String(100), default="BUSINESS")  # BUSINESS, GOVERNANCE, LITIGATION, REGULATORY, FINANCIAL
    description = Column(Text, nullable=False)
    probability = Column(String(20), default="MEDIUM")  # LOW, MEDIUM, HIGH
    impact = Column(String(20), default="MEDIUM")  # LOW, MEDIUM, HIGH
    severity_score = Column(Float, default=5.0)  # 1.0 - 10.0
    evidence_citation = Column(Text, nullable=True)  # Document page / section reference

    ipo = relationship("IPO", back_populates="risks")


class Valuation(Base):
    """Computed valuation multiples and dilution impact."""
    __tablename__ = "valuations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    price_used = Column(Float, nullable=False)  # Upper price band
    
    # Valuation Metrics
    post_ipo_market_cap_cr = Column(Float, nullable=True)
    enterprise_value_cr = Column(Float, nullable=True)
    pe_ratio = Column(Float, nullable=True)
    pb_ratio = Column(Float, nullable=True)
    ev_ebitda = Column(Float, nullable=True)
    ev_revenue = Column(Float, nullable=True)
    
    # Peer Comparisons
    peer_median_pe = Column(Float, nullable=True)
    pe_premium_discount_pct = Column(Float, nullable=True)  # +% premium or -% discount
    peer_median_ev_ebitda = Column(Float, nullable=True)
    ev_ebitda_premium_discount_pct = Column(Float, nullable=True)
    
    # Dilution
    promoter_pre_holding_pct = Column(Float, nullable=True)
    promoter_post_holding_pct = Column(Float, nullable=True)
    dilution_pct = Column(Float, nullable=True)

    calculated_at = Column(DateTime, default=datetime.utcnow)

    ipo = relationship("IPO", back_populates="valuations")


class GMPSnapshot(Base):
    """Grey Market Premium time-series records."""
    __tablename__ = "gmp_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    gmp_value = Column(Float, nullable=False)
    upper_price = Column(Float, nullable=False)
    estimated_listing_price = Column(Float, nullable=False)
    potential_listing_gain_pct = Column(Float, nullable=False)
    source = Column(String(100), default="GMP Aggregator")
    captured_at = Column(DateTime, default=datetime.utcnow, index=True)
    trend = Column(String(20), default="STABLE")  # RISING, FALLING, STABLE

    ipo = relationship("IPO", back_populates="gmp_snapshots")


class SubscriptionSnapshot(Base):
    """Subscription progress throughout the bidding days."""
    __tablename__ = "subscription_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    day_number = Column(Integer, default=1)  # Day 1, 2, 3
    qib_times = Column(Float, default=0.0)
    nii_times = Column(Float, default=0.0)
    retail_times = Column(Float, default=0.0)
    employee_times = Column(Float, default=0.0)
    overall_times = Column(Float, default=0.0)
    captured_at = Column(DateTime, default=datetime.utcnow)

    ipo = relationship("IPO", back_populates="subscription_snapshots")


class AnchorInvestor(Base):
    """Anchor investor allocations."""
    __tablename__ = "anchor_investors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    investor_name = Column(String(255), nullable=False)
    shares_allocated = Column(Integer, nullable=False)
    amount_cr = Column(Float, nullable=False)
    pct_of_anchor_book = Column(Float, nullable=True)
    investor_type = Column(String(50), default="MUTUAL_FUND")  # MUTUAL_FUND, FPI, INSURANCE, PENSION, AIF
    lock_in_days = Column(Integer, default=30)  # 30 days (50%), 90 days (50%)

    ipo = relationship("IPO", back_populates="anchor_investors")


class AnalysisRun(Base):
    """Executed analysis records."""
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    run_timestamp = Column(DateTime, default=datetime.utcnow)
    version = Column(String(20), default="1.0.0")
    
    # Pillar Scores (0.0 - 10.0)
    business_quality_score = Column(Float, nullable=False)
    financial_quality_score = Column(Float, nullable=False)
    management_governance_score = Column(Float, nullable=False)
    ipo_structure_score = Column(Float, nullable=False)
    valuation_score = Column(Float, nullable=False)
    growth_industry_score = Column(Float, nullable=False)
    risk_score = Column(Float, nullable=False)
    market_sentiment_score = Column(Float, nullable=False)
    overall_score = Column(Float, nullable=False)
    
    # Multi-Horizon Ratings
    company_quality_score = Column(Float, nullable=False)
    ipo_attractiveness_score = Column(Float, nullable=False)
    listing_opportunity_score = Column(Float, nullable=False)
    long_term_opportunity_score = Column(Float, nullable=False)

    # Verification & Gates
    confidence_level = Column(String(20), default="HIGH")  # HIGH, MEDIUM, LOW
    data_completeness_pct = Column(Float, default=100.0)
    verified_sources_count = Column(Integer, default=1)
    conflicts_count = Column(Integer, default=0)
    is_safety_gated = Column(Boolean, default=False)
    safety_gate_reason = Column(Text, nullable=True)

    verdict = Column(String(50), default="ATTRACTIVE")  # ATTRACTIVE, NEUTRAL, AVOID, UNABLE_TO_ASSESS

    ipo = relationship("IPO", back_populates="analysis_runs")
    snapshots = relationship("AnalysisSnapshot", back_populates="run", cascade="all, delete-orphan")
    recommendation = relationship("Recommendation", back_populates="run", uselist=False, cascade="all, delete-orphan")


class AnalysisSnapshot(Base):
    """Immutable point-in-time state of all metrics and calculations."""
    __tablename__ = "analysis_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("analysis_runs.id"), nullable=False, index=True)
    snapshot_data = Column(JSON, nullable=False)  # Complete serialized analysis tree
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("AnalysisRun", back_populates="snapshots")


class Recommendation(Base):
    """Persisted recommendation decision."""
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("analysis_runs.id"), nullable=False, index=True)
    verdict = Column(String(50), nullable=False)  # ATTRACTIVE, NEUTRAL, AVOID, UNABLE_TO_ASSESS
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("AnalysisRun", back_populates="recommendation")
    reasons = relationship("RecommendationReason", back_populates="recommendation", cascade="all, delete-orphan")


class RecommendationReason(Base):
    """Structured breakdown of positives, risks, and catalysts."""
    __tablename__ = "recommendation_reasons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recommendation_id = Column(Integer, ForeignKey("recommendations.id"), nullable=False, index=True)
    reason_type = Column(String(20), nullable=False)  # POSITIVE, RISK, CATALYST, GATE_REASON
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    evidence_citation = Column(Text, nullable=True)

    recommendation = relationship("Recommendation", back_populates="reasons")


class Alert(Base):
    """Scheduled alert triggers (T-2, 6-hr, T-1, Opening)."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    alert_type = Column(String(50), nullable=False)  # T_MINUS_2, SIX_HOUR_REMINDER, T_MINUS_1, IPO_OPENED
    scheduled_for = Column(DateTime, nullable=False)
    is_dispatched = Column(Boolean, default=False)
    dispatched_at = Column(DateTime, nullable=True)
    idempotency_key = Column(String(100), unique=True, index=True, nullable=False)

    ipo = relationship("IPO", back_populates="alerts")
    notifications = relationship("Notification", back_populates="alert", cascade="all, delete-orphan")


class Notification(Base):
    """Dispatched notifications across channels."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False, index=True)
    channel = Column(String(50), nullable=False)  # WHATSAPP, EMAIL, SMS, CONSOLE
    recipient = Column(String(255), nullable=False)
    status = Column(String(50), default="CREATED")  # CREATED, QUEUED, SENT, DELIVERED, FAILED, RETRYING, CANCELLED
    message_content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime, nullable=True)

    alert = relationship("Alert", back_populates="notifications")
    attempts = relationship("NotificationAttempt", back_populates="notification", cascade="all, delete-orphan")


class NotificationAttempt(Base):
    """Granular delivery attempts and telemetry."""
    __tablename__ = "notification_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    notification_id = Column(Integer, ForeignKey("notifications.id"), nullable=False, index=True)
    attempt_number = Column(Integer, default=1)
    attempted_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), nullable=False)  # SUCCESS, FAILED
    provider_message_id = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)

    notification = relationship("Notification", back_populates="attempts")


class YouTubeVideo(Base):
    """Sourced YouTube analysis videos."""
    __tablename__ = "youtube_videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), nullable=False, index=True)
    video_id = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    channel_name = Column(String(150), nullable=False)
    video_url = Column(Text, nullable=False)
    published_at = Column(DateTime, nullable=True)
    duration_str = Column(String(50), nullable=True)
    view_count = Column(Integer, default=0)
    relevance_score = Column(Float, default=1.0)
    captured_at = Column(DateTime, default=datetime.utcnow)

    ipo = relationship("IPO", back_populates="youtube_videos")


class PerformanceOutcome(Base):
    """Actual post-listing returns for model performance evaluation."""
    __tablename__ = "performance_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ipo_id = Column(Integer, ForeignKey("ipos.id"), unique=True, nullable=False)
    
    # Listing Day
    issue_price = Column(Float, nullable=False)
    listing_price = Column(Float, nullable=True)
    listing_gain_pct = Column(Float, nullable=True)
    predicted_listing_gain_pct = Column(Float, nullable=True)
    listing_error_pct = Column(Float, nullable=True)

    # Post-Listing Windows
    price_30d = Column(Float, nullable=True)
    return_30d_pct = Column(Float, nullable=True)
    price_90d = Column(Float, nullable=True)
    return_90d_pct = Column(Float, nullable=True)
    price_1y = Column(Float, nullable=True)
    return_1y_pct = Column(Float, nullable=True)

    # Recommendation Validation
    was_recommendation_profitable = Column(Boolean, nullable=True)
    is_false_positive = Column(Boolean, default=False)
    is_false_negative = Column(Boolean, default=False)

    evaluated_at = Column(DateTime, default=datetime.utcnow)

    ipo = relationship("IPO", back_populates="performance_outcomes")


class AuditLog(Base):
    """System-wide audit trail for all significant events and recommendations."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    entity_name = Column(String(100), nullable=True)
    entity_id = Column(String(100), nullable=True)
    description = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=True)
