"""Evidence-gated business quality analysis."""
from typing import Any, Dict, List


class BusinessAnalyzer:
    """Evaluates business fundamentals only when all core inputs are explicit."""

    REQUIRED_FIELDS = (
        "top5_customer_concentration_pct",
        "recurring_revenue_pct",
        "has_proprietary_tech_or_moat",
        "is_cyclical",
    )

    @staticmethod
    def analyze_business(data: Dict[str, Any]) -> Dict[str, Any]:
        missing = [key for key in BusinessAnalyzer.REQUIRED_FIELDS if key not in data or data[key] is None]
        if missing:
            reason = "Missing verified business evidence: " + ", ".join(missing)
            return {"assessment_status": "UNABLE_TO_ASSESS", "business_quality_score": None,
                    "insights": [reason], "limitations": [reason], "concentration_risk": None}
        top5 = float(data["top5_customer_concentration_pct"])
        recurring = float(data["recurring_revenue_pct"])
        if (not math.isfinite(top5) or not math.isfinite(recurring)
                or not 0 <= top5 <= 100 or not 0 <= recurring <= 100
                or not isinstance(data["has_proprietary_tech_or_moat"], bool)
                or not isinstance(data["is_cyclical"], bool)):
            reason = "Customer concentration and recurring revenue must be percentages between 0 and 100."
            return {"assessment_status": "UNABLE_TO_ASSESS", "business_quality_score": None,
                    "insights": [reason], "limitations": [reason], "concentration_risk": None}

        score = 6.0
        insights: List[str] = []
        concentration_risk = False
        if top5 > 50:
            score -= 2.0; concentration_risk = True
            insights.append(f"High customer concentration: Top 5 customers account for {top5}% of revenue.")
        elif top5 > 30:
            score -= 1.0
            insights.append(f"Moderate customer concentration: Top 5 customers account for {top5}%.")
        else:
            score += 1.0
            insights.append(f"Well-diversified customer base: Top 5 customers account for {top5}%.")
        if recurring >= 60:
            score += 1.5; insights.append(f"Strong recurring revenue model ({recurring}%).")
        elif recurring < 20:
            score -= 0.5; insights.append(f"Low recurring revenue visibility ({recurring}%).")
        if data["has_proprietary_tech_or_moat"]:
            score += 1.5; insights.append("Identified proprietary technological moat / high switching costs.")
        if data["is_cyclical"]:
            score -= 1.0; insights.append("Industry operates in cyclical demand cycles.")
        return {"assessment_status": "ASSESSED", "business_quality_score": max(1.0, min(10.0, round(score, 1))),
                "insights": insights, "limitations": [], "concentration_risk": concentration_risk}
