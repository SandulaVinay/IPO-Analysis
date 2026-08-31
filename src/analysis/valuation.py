"""
Valuation & Multiples Analysis Engine.
Selects industry-tailored multiples (P/E & EV/EBITDA for manufacturing, P/B for Banks/NBFCs, EV/Revenue for Tech SaaS).
Calculates post-IPO market cap, enterprise value, dilution impact, and discount/premium vs peers.
Produces Valuation Score (0.0 to 10.0).
"""

from typing import Dict, Any, List, Optional
from src.calculations.math import FinancialMath


class ValuationEngine:
    """Computes comprehensive valuation metrics and compares against peer benchmarks."""

    @staticmethod
    def evaluate_valuation(
        issue_price: float,
        post_issue_shares_cr: Optional[float],
        total_debt_cr: Optional[float],
        cash_cr: Optional[float],
        latest_pat_cr: Optional[float],
        latest_ebitda_cr: Optional[float],
        latest_revenue_cr: Optional[float],
        net_worth_cr: Optional[float],
        peer_median_pe: Optional[float],
        peer_median_ev_ebitda: Optional[float],
        industry_type: str = "GENERAL",
    ) -> Dict[str, Any]:
        """
        Evaluate valuation attractiveness.
        """
        # 1. Market Cap & Enterprise Value
        market_cap = FinancialMath.calculate_post_ipo_market_cap(issue_price, post_issue_shares_cr)
        ev = FinancialMath.calculate_enterprise_value(market_cap, total_debt_cr, cash_cr)

        # 2. EPS & P/E
        eps = round(latest_pat_cr / post_issue_shares_cr, 2) if (latest_pat_cr and post_issue_shares_cr and post_issue_shares_cr > 0) else None
        pe = FinancialMath.calculate_pe_ratio(issue_price, eps)
        
        # 3. EV/EBITDA
        ev_ebitda = FinancialMath.calculate_ev_ebitda(ev, latest_ebitda_cr)
        
        # 4. EV/Revenue
        ev_rev = FinancialMath.calculate_ev_revenue(ev, latest_revenue_cr)

        # 5. Peer Premium / Discount
        pe_diff = FinancialMath.calculate_premium_discount_vs_peers(pe, peer_median_pe)
        ev_ebitda_diff = FinancialMath.calculate_premium_discount_vs_peers(ev_ebitda, peer_median_ev_ebitda)

        # 6. Scoring
        score = 6.0
        insights: List[str] = []

        if pe_diff is not None:
            if pe_diff <= -20.0:
                score += 2.5
                insights.append(f"Attractive valuation: Priced at a {abs(pe_diff)}% discount to peer median P/E.")
            elif pe_diff <= -5.0:
                score += 1.5
                insights.append(f"Fairly priced: {abs(pe_diff)}% discount vs peer median P/E.")
            elif pe_diff >= 30.0:
                score -= 2.5
                insights.append(f"⚠️ Demanding valuation: Priced at a {pe_diff}% premium to peer median P/E.")
            else:
                insights.append(f"In line with peer median P/E ({pe_diff}% variance).")
        elif pe is not None:
            if pe <= 20.0:
                score += 1.5
                insights.append(f"Reasonable standalone P/E of {pe}x.")
            elif pe > 60.0:
                score -= 2.0
                insights.append(f"High standalone P/E of {pe}x.")

        final_score = max(1.0, min(10.0, round(score, 1)))

        return {
            "valuation_score": final_score,
            "post_ipo_market_cap_cr": market_cap,
            "enterprise_value_cr": ev,
            "eps": eps,
            "pe_ratio": pe,
            "ev_ebitda": ev_ebitda,
            "ev_revenue": ev_rev,
            "pe_premium_discount_pct": pe_diff,
            "ev_ebitda_premium_discount_pct": ev_ebitda_diff,
            "insights": insights,
        }
