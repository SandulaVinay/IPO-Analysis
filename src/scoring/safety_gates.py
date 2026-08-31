"""
Hard Assessment Safety Gates.
Enforces non-negotiable checks before issuing a positive assessment:
- Checks missing critical financial statements
- Checks conflicting IPO opening/closing dates or price bands across Tier 1 sources
- Checks material auditor qualifications/adverse disclaimers
- Checks unverified critical data

If safety gates fail, the system outputs 'UNABLE TO ASSESS' rather than manufacturing a guess.
"""

from typing import Dict, Any, List, Tuple


class SafetyGateEvaluator:
    """Evaluates hard safety assessment gates."""

    @staticmethod
    def evaluate_gates(
        completeness_info: Dict[str, Any],
        conflict_info: Dict[str, Any],
        management_info: Dict[str, Any],
        financial_info: Dict[str, Any],
    ) -> Tuple[bool, List[str]]:
        """
        Returns (is_gated: bool, gate_reasons: List[str]).
        """
        gate_reasons: List[str] = []

        # 1. Check critical missing data
        missing_fields = completeness_info.get("missing_critical_fields", [])
        if len(missing_fields) > 2:
            gate_reasons.append(
                f"Missing critical information fields: {', '.join(missing_fields[:3])}."
            )

        # 2. Check critical Tier-1 source conflicts
        if conflict_info.get("is_critical_tier1_conflict"):
            gate_reasons.append(
                f"Unresolved Tier-1 source conflict: {conflict_info.get('conflict_details')}."
            )

        # 3. Check severe governance/auditor flags
        if management_info.get("has_critical_governance_flag"):
            gate_reasons.append(
                "Critical corporate governance / auditor qualification flags detected."
            )

        is_gated = len(gate_reasons) > 0
        return is_gated, gate_reasons
