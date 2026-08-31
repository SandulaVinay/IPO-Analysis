"""
Source Verification and Confidence Scoring Engine.
Computes data completeness, verifies evidence provenance, and computes confidence levels.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.logging import logger
from src.database.models import IPO, Fact


class VerificationEngine:
    """Verifies evidence completeness, source provenance, and confidence levels."""

    CRITICAL_FIELDS = [
        "verified_open_date",
        "verified_close_date",
        "min_price",
        "max_price",
        "lot_size",
        "issue_size_cr",
        "fresh_issue_cr",
        "revenue_latest",
        "pat_latest",
        "cfo_latest",
    ]

    @classmethod
    def evaluate_ipo_completeness(cls, ipo_data: Dict[str, Any], facts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Evaluate completeness percentage, count verified sources, and compute confidence score.
        """
        available_fields = set()
        for k, v in ipo_data.items():
            if v is not None and v != "":
                available_fields.add(k)
        for f in facts:
            if f.get("field_name") and f.get("verification_status") == "VERIFIED":
                available_fields.add(f["field_name"])

        missing_critical = [f for f in cls.CRITICAL_FIELDS if f not in available_fields]
        completeness_ratio = (len(cls.CRITICAL_FIELDS) - len(missing_critical)) / len(cls.CRITICAL_FIELDS)
        completeness_pct = round(completeness_ratio * 100.0, 1)

        # Count verified distinct sources
        verified_sources = set(f.get("source_name") for f in facts if f.get("verification_status") == "VERIFIED")

        # Determine confidence
        if completeness_pct >= 90.0 and len(missing_critical) == 0:
            confidence = "HIGH"
        elif completeness_pct >= 70.0:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return {
            "completeness_pct": completeness_pct,
            "completeness_ratio": completeness_ratio,
            "missing_critical_fields": missing_critical,
            "verified_sources_count": max(len(verified_sources), 1),
            "confidence_level": confidence,
        }
