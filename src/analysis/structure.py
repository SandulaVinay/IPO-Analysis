"""Evidence-gated IPO issue structure and use-of-proceeds analysis."""
from typing import Any, Dict, List
import math


class StructureAnalyzer:
    """Evaluates fresh issue versus OFS only when the complete issue split is known."""

    REQUIRED_FIELDS = ("issue_size_cr", "fresh_issue_cr", "ofs_cr")

    @staticmethod
    def analyze_structure(data: Dict[str, Any]) -> Dict[str, Any]:
        missing = [key for key in StructureAnalyzer.REQUIRED_FIELDS if key not in data or data[key] is None]
        if missing:
            reason = "Missing verified issue-structure evidence: " + ", ".join(missing)
            return {"assessment_status": "UNABLE_TO_ASSESS", "ipo_structure_score": None,
                    "fresh_issue_pct": None, "ofs_pct": None, "is_ofs_heavy": None,
                    "insights": [reason], "limitations": [reason]}
        try:
            issue_size, fresh, ofs = (float(data[k]) for k in StructureAnalyzer.REQUIRED_FIELDS)
        except (TypeError, ValueError, OverflowError):
            reason = "Issue size and fresh/OFS amounts must be numeric."
            return {"assessment_status": "UNABLE_TO_ASSESS", "ipo_structure_score": None,
                    "fresh_issue_pct": None, "ofs_pct": None, "is_ofs_heavy": None,
                    "insights": [reason], "limitations": [reason]}
        if (not all(math.isfinite(v) for v in (issue_size, fresh, ofs))
                or issue_size <= 0 or fresh < 0 or ofs < 0 or fresh + ofs > issue_size * 1.02):
            reason = "Issue size and fresh/OFS amounts are inconsistent or outside valid ranges."
            return {"assessment_status": "UNABLE_TO_ASSESS", "ipo_structure_score": None,
                    "fresh_issue_pct": None, "ofs_pct": None, "is_ofs_heavy": None,
                    "insights": [reason], "limitations": [reason]}
        fresh_pct = round(fresh / issue_size * 100, 1)
        ofs_pct = round(ofs / issue_size * 100, 1)
        score = 6.0
        insights: List[str] = []
        if fresh_pct >= 70:
            score += 2.0; insights.append(f"Majority Fresh Issue ({fresh_pct}%). Direct balance sheet strengthening.")
        elif ofs_pct >= 80:
            score -= 2.5; insights.append(f"Heavy OFS issue ({ofs_pct}%). Proceeds go to exiting shareholders.")
        elif ofs_pct >= 50:
            score -= 1.0; insights.append(f"Moderate OFS component ({ofs_pct}%).")
        capex, debt_repay = data.get("capex_growth_cr"), data.get("debt_repayment_cr")
        if capex is not None and capex > 0 and fresh > 0:
            insights.append(f"Growth-focused: {round(float(capex) / fresh * 100, 1)}% of fresh proceeds earmarked for capex/expansion.")
        if debt_repay is not None and debt_repay > 0 and fresh > 0:
            insights.append(f"Deleveraging: {round(float(debt_repay) / fresh * 100, 1)}% of fresh proceeds targeted for debt reduction.")
        return {"assessment_status": "ASSESSED", "ipo_structure_score": max(1.0, min(10.0, round(score, 1))),
                "fresh_issue_pct": fresh_pct, "ofs_pct": ofs_pct, "is_ofs_heavy": ofs_pct >= 75,
                "insights": insights, "limitations": []}
