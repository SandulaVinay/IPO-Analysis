"""Hard assessment safety gates.

Any missing critical field blocks a positive assessment. The caller must supply
verified provenance-bearing facts before an assessment can pass these gates.
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
        """Return (is_gated, gate_reasons)."""
        gate_reasons: List[str] = []

        # These fields are explicitly designated critical by VerificationEngine.
        # Do not tolerate a missing critical field simply because fewer than three
        # fields are absent; a single missing price/financial fact can change the result.
        missing_fields = completeness_info.get("missing_critical_fields", [])
        if missing_fields:
            preview = ", ".join(str(field) for field in missing_fields[:5])
            suffix = "…" if len(missing_fields) > 5 else ""
            gate_reasons.append(
                f"Missing critical information fields ({len(missing_fields)}): {preview}{suffix}."
            )

        if conflict_info.get("is_critical_tier1_conflict"):
            gate_reasons.append(
                f"Unresolved Tier-1 source conflict: {conflict_info.get('conflict_details')}."
            )

        if management_info.get("has_critical_governance_flag"):
            gate_reasons.append(
                "Critical corporate governance / auditor qualification flags detected."
            )

        # Explicitly reject financial evidence that has not completed verification.
        status = str(financial_info.get("verification_status", "")).upper()
        if status and status not in {"VERIFIED", "PASS"}:
            gate_reasons.append(
                f"Financial evidence is not verified (status: {status})."
            )
        if financial_info.get("has_unverified_critical_financials"):
            gate_reasons.append("One or more critical financial inputs remain unverified.")

        return bool(gate_reasons), gate_reasons
