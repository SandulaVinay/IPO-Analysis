"""
Configuration management using Pydantic Settings.
Loads configuration from environment variables and provides strict types and defaults.
"""

from pathlib import Path
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General App Settings
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    timezone: str = "Asia/Kolkata"

    # Server Settings
    port: int = 8000
    host: str = "0.0.0.0"

    # Database URL
    database_url: str = "sqlite+aiosqlite:///./ipo_system.db"

    # Alert Timing & Scheduling (in calendar days / hours)
    t_minus_days_target: int = 2
    reminder_hours_after_alert: int = 6
    final_reminder_days_before: int = 1
    enable_automated_scheduler: bool = True

    # Scoring Model Weights (Must sum to 1.0)
    weight_business_quality: float = 0.20
    weight_financial_quality: float = 0.20
    weight_management_governance: float = 0.10
    weight_ipo_structure: float = 0.10
    weight_valuation: float = 0.20
    weight_growth_industry: float = 0.10
    weight_risk: float = 0.05
    weight_market_sentiment: float = 0.05

    # Safety Gate Thresholds
    min_data_completeness_ratio: float = 0.70
    max_permissible_conflicts: int = 0

    # WhatsApp Provider Settings
    enable_whatsapp: bool = False
    whatsapp_provider: Literal["cloud_api", "twilio", "console"] = "console"
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_recipient_phone: str = "+919876543210"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "+14155238886"

    # Email Provider Settings
    enable_email: bool = False
    email_provider: Literal["smtp", "resend", "console"] = "console"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "alerts@ipointelligence.local"
    email_to: str = "investor@example.com"

    # SMS Provider Settings
    enable_sms: bool = False
    sms_provider: Literal["twilio", "console"] = "console"
    sms_recipient_phone: str = "+919876543210"

    # YouTube API Key
    youtube_api_key: str = ""

    # Storage Paths
    document_storage_dir: Path = Field(default=Path("./storage/documents"))
    snapshot_storage_dir: Path = Field(default=Path("./storage/snapshots"))


# Singleton settings instance
settings = Settings()
