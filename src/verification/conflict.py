"""
Source Conflict Engine.
Detects disagreements across sources (e.g. NSE vs Secondary Portals on dates, price bands, or issue size).
Applies Tier-1 precedence and triggers safety gates when unresolvable conflicts exist.
"""

from typing import Dict, Any, List, Optional
from src.common.logging import logger


class SourceConflictEngine:
    """Detects and resolves discrepancies between multiple data sources."""

    TIER_RANKINGS = {
        "TIER_1": 1,  # Authoritative (SEBI, NSE, BSE, RHP)
        "TIER_2": 2,  # Reliable Secondary (Chittorgarh, Portals, Screener)
        "TIER_3": 3,  # Sentiment / Commentary (GMP, YouTube)
    }

    @classmethod
    def compare_field_values(
        cls,
        field_name: str,
        sources_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        sources_data example:
        [
            {"source_name": "NSE", "source_tier": "TIER_1", "value": "2026-09-18"},
            {"source_name": "SecondaryPortal", "source_tier": "TIER_2", "value": "2026-09-19"}
        ]
        """
        if not sources_data:
            return {"has_conflict": False, "selected_value": None, "conflict_details": None}

        # Check distinct values
        unique_values = set(str(item["value"]).strip() for item in sources_data if item.get("value") is not None)

        if len(unique_values) <= 1:
            # All agreeing
            chosen = sources_data[0]["value"] if sources_data else None
            return {"has_conflict": False, "selected_value": chosen, "conflict_details": None}

        # Disagreement detected
        # Sort by tier ranking (TIER_1 < TIER_2 < TIER_3)
        sorted_sources = sorted(
            sources_data,
            key=lambda x: cls.TIER_RANKINGS.get(x.get("source_tier", "TIER_3"), 99)
        )

        tier_1_sources = [s for s in sorted_sources if s.get("source_tier") == "TIER_1"]
        tier_1_values = set(str(s["value"]).strip() for s in tier_1_sources if s.get("value") is not None)

        # Check if multiple Tier 1 sources contradict each other
        if len(tier_1_values) > 1:
            conflict_msg = f"CRITICAL CONFLICT: Multiple Tier-1 sources disagree on {field_name}: {tier_1_sources}"
            logger.error(conflict_msg)
            return {
                "has_conflict": True,
                "is_critical_tier1_conflict": True,
                "selected_value": None,  # Refuse to guess
                "conflict_details": conflict_msg,
                "sources": sources_data,
            }

        # If Tier 1 exists, use Tier 1 but log the conflict with secondary sources
        if tier_1_sources:
            chosen = tier_1_sources[0]["value"]
            conflict_msg = f"Source Conflict resolved using Tier-1 precedence for {field_name}. Chosen: {chosen} from {tier_1_sources[0]['source_name']}"
            logger.warning(conflict_msg)
            return {
                "has_conflict": True,
                "is_critical_tier1_conflict": False,
                "selected_value": chosen,
                "conflict_details": conflict_msg,
                "sources": sources_data,
            }

        # Only secondary sources disagree
        chosen = sorted_sources[0]["value"]
        conflict_msg = f"Secondary source conflict on {field_name}. Using highest priority secondary source {sorted_sources[0]['source_name']}"
        logger.warning(conflict_msg)
        return {
            "has_conflict": True,
            "is_critical_tier1_conflict": False,
            "selected_value": chosen,
            "conflict_details": conflict_msg,
            "sources": sources_data,
        }
