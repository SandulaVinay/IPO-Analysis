"""
Management, Promoter, and Corporate Governance Forensic Analysis Module.
Analyzes promoter shareholding pre/post IPO, dilution, promoter pledges, related-party transactions (RPTs),
auditor modifications, and founder integrity.
Produces Management/Governance Score and Ownership Risk Score (0.0 to 10.0).
"""

from typing import Dict, Any, List, Optional


class ManagementAnalyzer:
    """Evaluates promoter background, governance integrity, and shareholding alignment."""

    @staticmethod
    def analyze_management(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        data keys:
            - promoter_pre_holding_pct: Optional[float]
            - promoter_post_holding_pct: Optional[float]
            - promoter_pledge_pct: Optional[float]
            - has_auditor_qualifications: bool
            - frequent_auditor_changes: bool
            - rpt_revenue_pct: Optional[float]
            - has_promoter_litigation: bool
            - pe_vc_exit_ratio_pct: Optional[float]
        """
        gov_score = 7.0  # baseline
        insights: List[str] = []
        red_flags: List[str] = []

        post_holding = data.get("promoter_post_holding_pct")
        if post_holding is not None:
            if post_holding >= 51.0:
                gov_score += 1.0
                insights.append(f"Strong post-issue promoter majority stake retained ({post_holding}%).")
            elif post_holding < 30.0:
                gov_score -= 1.5
                insights.append(f"Low post-issue promoter skin in the game ({post_holding}%).")

        pledge = data.get("promoter_pledge_pct") or 0.0
        if pledge > 0.0:
            gov_score -= 2.5
            red_flags.append(f"⚠️ Promoter shares pledged: {pledge}% of holding.")

        if data.get("has_auditor_qualifications"):
            gov_score -= 3.0
            red_flags.append("⚠️ Auditor qualifications/adverse remarks present in financial disclosures.")

        if data.get("frequent_auditor_changes"):
            gov_score -= 2.0
            red_flags.append("⚠️ Multiple auditor resignations/changes in last 3 years.")

        rpt = data.get("rpt_revenue_pct") or 0.0
        if rpt > 15.0:
            gov_score -= 1.5
            red_flags.append(f"Significant related-party transactions ({rpt}% of revenue).")

        if data.get("has_promoter_litigation"):
            gov_score -= 1.0
            red_flags.append("Material criminal/tax litigation against promoters disclosed in RHP.")

        final_score = max(1.0, min(10.0, round(gov_score, 1)))

        return {
            "management_governance_score": final_score,
            "insights": insights,
            "red_flags": red_flags,
            "has_critical_governance_flag": len(red_flags) > 0 and gov_score < 4.0,
        }
