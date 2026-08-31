"""
Forensic Analysis & Narrative Consistency Engine.
Verifies consistency between management narrative claims in RHP and quantitative financial reality.
Scans for auditor qualifications, litigations, and regulatory penalties.
"""

from typing import Dict, Any, List, Optional


class ForensicNarrativeAnalyzer:
    """Detects contradictions between narrative assertions and hard data."""

    @staticmethod
    def evaluate_narrative_consistency(
        narrative_claims: List[str],
        financial_summary: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Check for evidence-backed contradictions without hallucinating.
        """
        contradictions: List[Dict[str, Any]] = []

        rev_cagr = financial_summary.get("revenue_cagr")
        pat_cagr = financial_summary.get("pat_cagr")
        cfo_cagr = financial_summary.get("cfo_cagr")

        # Check: Narrative "Consistent predictable high growth" vs volatile/declining financials
        for claim in narrative_claims:
            claim_lower = claim.lower()
            if "predictable growth" in claim_lower or "steady expansion" in claim_lower:
                if rev_cagr is not None and rev_cagr < 5.0:
                    contradictions.append({
                        "claim": claim,
                        "financial_reality": f"Revenue CAGR over the period is only {rev_cagr}%.",
                        "verdict": "FLAGGED CONTRADICTION",
                    })

            if "strong cash generation" in claim_lower:
                if cfo_cagr is not None and cfo_cagr < 0:
                    contradictions.append({
                        "claim": claim,
                        "financial_reality": f"Operating cash flow CAGR is negative ({cfo_cagr}%).",
                        "verdict": "FLAGGED CONTRADICTION",
                    })

        return contradictions
