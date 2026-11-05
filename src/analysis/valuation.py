"""Evidence-gated valuation and peer-multiple analysis."""
from typing import Any, Dict, List, Optional
import math
from src.calculations.math import FinancialMath


class ValuationEngine:
    """Computes valuation metrics only with complete financial and peer evidence."""

    @staticmethod
    def evaluate_valuation(
        issue_price: float, post_issue_shares_cr: Optional[float], total_debt_cr: Optional[float],
        cash_cr: Optional[float], latest_pat_cr: Optional[float], latest_ebitda_cr: Optional[float],
        latest_revenue_cr: Optional[float], net_worth_cr: Optional[float], peer_median_pe: Optional[float],
        peer_median_ev_ebitda: Optional[float], industry_type: str = "GENERAL",
    ) -> Dict[str, Any]:
        required = {
            "issue_price": issue_price, "post_issue_shares_cr": post_issue_shares_cr,
            "total_debt_cr": total_debt_cr, "cash_cr": cash_cr, "latest_pat_cr": latest_pat_cr,
            "latest_ebitda_cr": latest_ebitda_cr, "latest_revenue_cr": latest_revenue_cr,
            "net_worth_cr": net_worth_cr,
        }
        missing = [k for k, v in required.items() if v is None]
        if peer_median_pe is None and peer_median_ev_ebitda is None:
            missing.append("peer_median_pe_or_peer_median_ev_ebitda")
        if missing:
            reason = "Missing verified valuation evidence: " + ", ".join(missing)
            return {"assessment_status": "UNABLE_TO_ASSESS", "valuation_score": None,
                    "insights": [reason], "limitations": [reason]}
        try:
            numeric = [float(v) for v in required.values()]
        except (TypeError, ValueError, OverflowError):
            reason = "Valuation inputs must be numeric."
            return {"assessment_status": "UNABLE_TO_ASSESS", "valuation_score": None,
                    "insights": [reason], "limitations": [reason]}
        if any(not math.isfinite(v) for v in numeric) or float(issue_price) <= 0 or float(post_issue_shares_cr) <= 0:
            reason = "Valuation inputs must be finite and issue price/share count must be positive."
            return {"assessment_status": "UNABLE_TO_ASSESS", "valuation_score": None,
                    "insights": [reason], "limitations": [reason]}
        market_cap = FinancialMath.calculate_post_ipo_market_cap(issue_price, post_issue_shares_cr)
        ev = FinancialMath.calculate_enterprise_value(market_cap, total_debt_cr, cash_cr)
        eps = round(latest_pat_cr / post_issue_shares_cr, 2) if latest_pat_cr and post_issue_shares_cr > 0 else None
        pe = FinancialMath.calculate_pe_ratio(issue_price, eps)
        ev_ebitda = FinancialMath.calculate_ev_ebitda(ev, latest_ebitda_cr)
        ev_rev = FinancialMath.calculate_ev_revenue(ev, latest_revenue_cr)
        pe_diff = FinancialMath.calculate_premium_discount_vs_peers(pe, peer_median_pe)
        ev_ebitda_diff = FinancialMath.calculate_premium_discount_vs_peers(ev_ebitda, peer_median_ev_ebitda)
        score = 6.0
        insights: List[str] = []
        if pe_diff is not None:
            if pe_diff <= -20: score += 2.5; insights.append(f"Attractive valuation: {abs(pe_diff)}% discount to peer median P/E.")
            elif pe_diff <= -5: score += 1.5; insights.append(f"Fairly priced: {abs(pe_diff)}% discount vs peer median P/E.")
            elif pe_diff >= 30: score -= 2.5; insights.append(f"Demanding valuation: {pe_diff}% premium to peer median P/E.")
            else: insights.append(f"In line with peer median P/E ({pe_diff}% variance).")
        elif pe is not None:
            if pe <= 20: score += 1.5; insights.append(f"Reasonable standalone P/E of {pe}x.")
            elif pe > 60: score -= 2.0; insights.append(f"High standalone P/E of {pe}x.")
        return {"assessment_status": "ASSESSED", "valuation_score": max(1.0, min(10.0, round(score, 1))),
                "post_ipo_market_cap_cr": market_cap, "enterprise_value_cr": ev, "eps": eps,
                "pe_ratio": pe, "ev_ebitda": ev_ebitda, "ev_revenue": ev_rev,
                "pe_premium_discount_pct": pe_diff, "ev_ebitda_premium_discount_pct": ev_ebitda_diff,
                "insights": insights, "limitations": []}
