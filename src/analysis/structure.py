"""
IPO Issue Structure and Use of Proceeds Analysis Module.
Distinguishes Fresh Issue (growth/debt repayment capital to company) from Offer For Sale (OFS exit money to selling shareholders).
Produces Capital Deployment Quality Score (0.0 to 10.0).
"""

from typing import Dict, Any, List, Optional


class StructureAnalyzer:
    """Evaluates the composition of the IPO issue and intended capital deployment."""

    @staticmethod
    def analyze_structure(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        data keys:
            - issue_size_cr: Optional[float]
            - fresh_issue_cr: Optional[float]
            - ofs_cr: Optional[float]
            - debt_repayment_cr: Optional[float]
            - capex_growth_cr: Optional[float]
            - general_corporate_cr: Optional[float]
        """
        issue_size = data.get("issue_size_cr") or 0.0
        fresh = data.get("fresh_issue_cr") or 0.0
        ofs = data.get("ofs_cr") or 0.0

        if issue_size == 0.0 and (fresh > 0 or ofs > 0):
            issue_size = fresh + ofs

        fresh_pct = round((fresh / issue_size * 100.0), 1) if issue_size > 0 else 0.0
        ofs_pct = round((ofs / issue_size * 100.0), 1) if issue_size > 0 else 0.0

        score = 6.0
        insights: List[str] = []

        if fresh_pct >= 70.0:
            score += 2.0
            insights.append(f"Majority Fresh Issue ({fresh_pct}%). Direct balance sheet strengthening.")
        elif ofs_pct >= 80.0:
            score -= 2.5
            insights.append(f"⚠️ Heavy OFS issue ({ofs_pct}%). Money goes to exiting shareholders, not the company.")
        elif ofs_pct >= 50.0:
            score -= 1.0
            insights.append(f"Moderate OFS component ({ofs_pct}%).")

        # Capital deployment intent
        capex = data.get("capex_growth_cr") or 0.0
        debt_repay = data.get("debt_repayment_cr") or 0.0
        if capex > 0 and fresh > 0:
            capex_pct = round(capex / fresh * 100.0, 1)
            insights.append(f"Growth-focused: {capex_pct}% of fresh proceeds earmarked for Capex/Expansion.")
        if debt_repay > 0 and fresh > 0:
            debt_pct = round(debt_repay / fresh * 100.0, 1)
            insights.append(f"Deleveraging: {debt_pct}% of fresh proceeds targeted for debt reduction.")

        final_score = max(1.0, min(10.0, round(score, 1)))

        return {
            "ipo_structure_score": final_score,
            "fresh_issue_pct": fresh_pct,
            "ofs_pct": ofs_pct,
            "is_ofs_heavy": ofs_pct >= 75.0,
            "insights": insights,
        }
