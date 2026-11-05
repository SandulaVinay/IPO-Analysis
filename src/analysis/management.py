"""Evidence-gated management and corporate governance analysis."""
from typing import Any, Dict, List


class ManagementAnalyzer:
    """Evaluates governance only when material indicators have explicit values."""

    REQUIRED_FIELDS = (
        "promoter_post_holding_pct", "promoter_pledge_pct", "has_auditor_qualifications",
        "frequent_auditor_changes", "rpt_revenue_pct", "has_promoter_litigation",
    )

    @staticmethod
    def analyze_management(data: Dict[str, Any]) -> Dict[str, Any]:
        missing = [key for key in ManagementAnalyzer.REQUIRED_FIELDS if key not in data or data[key] is None]
        if missing:
            reason = "Missing verified governance evidence: " + ", ".join(missing)
            return {"assessment_status": "UNABLE_TO_ASSESS", "management_governance_score": None,
                    "insights": [reason], "red_flags": [], "limitations": [reason],
                    "has_critical_governance_flag": False}
        post = float(data["promoter_post_holding_pct"])
        pledge = float(data["promoter_pledge_pct"])
        rpt = float(data["rpt_revenue_pct"])
        if (not all(math.isfinite(v) and 0 <= v <= 100 for v in (post, pledge, rpt))
                or not isinstance(data["has_auditor_qualifications"], bool)
                or not isinstance(data["frequent_auditor_changes"], bool)
                or not isinstance(data["has_promoter_litigation"], bool)):
            reason = "Promoter holding, pledge, and related-party revenue percentages must be between 0 and 100."
            return {"assessment_status": "UNABLE_TO_ASSESS", "management_governance_score": None,
                    "insights": [reason], "red_flags": [], "limitations": [reason],
                    "has_critical_governance_flag": False}
        score = 7.0
        insights: List[str] = []
        red_flags: List[str] = []
        if post >= 51:
            score += 1.0; insights.append(f"Strong post-issue promoter majority stake retained ({post}%).")
        elif post < 30:
            score -= 1.5; insights.append(f"Low post-issue promoter skin in the game ({post}%).")
        if pledge > 0:
            score -= 2.5; red_flags.append(f"Promoter shares pledged: {pledge}% of holding.")
        if data["has_auditor_qualifications"]:
            score -= 3.0; red_flags.append("Auditor qualifications/adverse remarks present in financial disclosures.")
        if data["frequent_auditor_changes"]:
            score -= 2.0; red_flags.append("Multiple auditor resignations/changes in last 3 years.")
        if rpt > 15:
            score -= 1.5; red_flags.append(f"Significant related-party transactions ({rpt}% of revenue).")
        if data["has_promoter_litigation"]:
            score -= 1.0; red_flags.append("Material criminal/tax litigation against promoters disclosed in RHP.")
        return {"assessment_status": "ASSESSED", "management_governance_score": max(1.0, min(10.0, round(score, 1))),
                "insights": insights, "red_flags": red_flags,
                "has_critical_governance_flag": bool(red_flags) and score < 4.0, "limitations": []}
