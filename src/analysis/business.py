"""
Business and Revenue Model Analysis Module.
Analyzes industry moats, customer/supplier concentration, recurring revenue share, and scalability.
Produces explainable Business Quality Score (0.0 to 10.0).
"""

from typing import Dict, Any, List, Optional


class BusinessAnalyzer:
    """Evaluates business fundamentals, moats, and operational dependencies."""

    @staticmethod
    def analyze_business(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate business model parameters.
        data keys:
            - industry: str
            - description: str
            - top5_customer_concentration_pct: Optional[float]
            - recurring_revenue_pct: Optional[float]
            - addressable_market_cagr: Optional[float]
            - has_proprietary_tech_or_moat: bool
            - is_cyclical: bool
        """
        score = 6.0  # baseline
        insights: List[str] = []
        concentration_risk = False

        top5_cust = data.get("top5_customer_concentration_pct")
        if top5_cust is not None:
            if top5_cust > 50.0:
                score -= 2.0
                concentration_risk = True
                insights.append(f"High customer concentration: Top 5 customers account for {top5_cust}% of revenue.")
            elif top5_cust > 30.0:
                score -= 1.0
                insights.append(f"Moderate customer concentration: Top 5 customers account for {top5_cust}%.")
            else:
                score += 1.0
                insights.append(f"Well-diversified customer base: Top 5 customers account for {top5_cust}%.")

        rec_rev = data.get("recurring_revenue_pct")
        if rec_rev is not None:
            if rec_rev >= 60.0:
                score += 1.5
                insights.append(f"Strong recurring revenue model ({rec_rev}%).")
            elif rec_rev < 20.0:
                score -= 0.5
                insights.append(f"Low recurring revenue visibility ({rec_rev}%).")

        if data.get("has_proprietary_tech_or_moat"):
            score += 1.5
            insights.append("Identified proprietary technological moat / high switching costs.")

        if data.get("is_cyclical"):
            score -= 1.0
            insights.append("Industry operates in cyclical demand cycles.")

        # Bound score between 1.0 and 10.0
        final_score = max(1.0, min(10.0, round(score, 1)))

        return {
            "business_quality_score": final_score,
            "insights": insights,
            "concentration_risk": concentration_risk,
        }
