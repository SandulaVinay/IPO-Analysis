"""
Risk Scoring and Quantification Engine.
Computes composite risk score (0.0 to 10.0, where 10.0 is safest/lowest risk)
based on identified probabilities, impacts, and material litigation severity.
"""

from typing import Dict, Any, List, Optional


class RiskEngine:
    """Evaluates and quantifies operational, regulatory, and financial risk exposures."""

    SEVERITY_WEIGHTS = {
        "CRITICAL": 3.0,
        "HIGH": 2.0,
        "MEDIUM": 1.0,
        "LOW": 0.5,
    }

    @classmethod
    def evaluate_risks(cls, risks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        risks items:
            - risk_title: str
            - probability: LOW, MEDIUM, HIGH
            - impact: LOW, MEDIUM, HIGH
            - severity: CRITICAL, HIGH, MEDIUM, LOW
            - evidence_citation: str
        """
        if not risks:
            return {
                "risk_score": 6.5,
                "total_risk_count": 0,
                "high_severity_count": 0,
                "top_risks": [],
            }

        total_penalty = 0.0
        high_severity = 0
        structured_risks: List[Dict[str, Any]] = []

        for r in risks:
            sev = r.get("severity", "MEDIUM").upper()
            prob = r.get("probability", "MEDIUM").upper()
            impact = r.get("impact", "MEDIUM").upper()

            weight = cls.SEVERITY_WEIGHTS.get(sev, 1.0)
            total_penalty += weight

            if sev in ("CRITICAL", "HIGH"):
                high_severity += 1

            structured_risks.append({
                "title": r.get("risk_title"),
                "category": r.get("risk_category", "BUSINESS"),
                "probability": prob,
                "impact": impact,
                "severity": sev,
                "citation": r.get("evidence_citation", "RHP Section IV"),
            })

        # Higher penalty => Lower safety score
        base_score = 9.0
        calculated_score = max(1.0, min(10.0, round(base_score - (total_penalty * 0.7), 1)))

        return {
            "risk_score": calculated_score,
            "total_risk_count": len(risks),
            "high_severity_count": high_severity,
            "top_risks": structured_risks[:5],
        }
