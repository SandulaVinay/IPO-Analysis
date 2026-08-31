"""
Document Comparator and Change Detection Engine.
Detects differences between DRHP v1, DRHP v2, RHP, and Addenda.
Highlights modifications in price band, dates, issue size, OFS sellers, and risk factors.
"""

from typing import Dict, Any, List, Optional
from src.common.logging import logger


class DocumentDiffEngine:
    """Detects material differences between successive filings and versions."""

    @staticmethod
    def compare_ipo_parameters(old_params: Dict[str, Any], new_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare two parameter dictionaries (e.g. from DRHP vs RHP) and return a structured diff.
        """
        changes: List[Dict[str, Any]] = []
        material_change_keys = [
            ("min_price", "Minimum Price Band"),
            ("max_price", "Maximum Price Band"),
            ("issue_size_cr", "Total Issue Size (₹ Cr)"),
            ("fresh_issue_cr", "Fresh Issue (₹ Cr)"),
            ("ofs_cr", "Offer For Sale (₹ Cr)"),
            ("verified_open_date", "Opening Date"),
            ("verified_close_date", "Closing Date"),
            ("lot_size", "Market Lot Size"),
        ]

        for key, label in material_change_keys:
            old_val = old_params.get(key)
            new_val = new_params.get(key)
            if old_val != new_val and (old_val is not None or new_val is not None):
                changes.append({
                    "field": key,
                    "label": label,
                    "old_value": old_val,
                    "new_value": new_val,
                    "is_material": True,
                })

        # Check risk differences
        old_risks = set(old_params.get("risks", []))
        new_risks = set(new_params.get("risks", []))
        added_risks = list(new_risks - old_risks)
        removed_risks = list(old_risks - new_risks)

        is_reanalysis_required = len(changes) > 0 or len(added_risks) > 0

        diff_summary = {
            "has_changes": len(changes) > 0 or len(added_risks) > 0,
            "is_reanalysis_required": is_reanalysis_required,
            "parameter_changes": changes,
            "new_risks_added": added_risks,
            "risks_removed": removed_risks,
        }

        if is_reanalysis_required:
            logger.info(f"Material document changes detected! {len(changes)} parameter changes, {len(added_risks)} new risks.")

        return diff_summary
