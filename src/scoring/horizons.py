"""
Multi-Horizon Decision Modeling.
Separates:
1. Company Quality (How good is the underlying business?)
2. IPO Attractiveness (Is the IPO offering attractive at the given valuation?)
3. Listing Opportunity (Is there short-term listing gain potential based on demand & sentiment?)
4. Long-Term Opportunity (Does the business possess multi-year compounding potential?)
"""

from typing import Dict, Any


class MultiHorizonClassifier:
    """Computes differentiated ratings across distinct investment horizons."""

    @staticmethod
    def classify_horizons(
        business_score: float,
        financial_score: float,
        governance_score: float,
        valuation_score: float,
        risk_score: float,
        gmp_gain_pct: float,
        subscription_times: float,
        is_gated: bool,
    ) -> Dict[str, Any]:
        """
        Produce 4 distinct horizon ratings (0.0 to 10.0).
        """
        if is_gated:
            return {
                "company_quality": 0.0,
                "ipo_attractiveness": 0.0,
                "listing_opportunity": 0.0,
                "long_term_opportunity": 0.0,
                "verdict": "UNABLE_TO_ASSESS",
            }

        # 1. Company Quality (Fundamental intrinsic health)
        company_quality = round(
            (business_score * 0.40) + (financial_score * 0.40) + (governance_score * 0.20),
            1,
        )

        # 2. IPO Attractiveness (Fundamentals + Valuation + Risk)
        ipo_attractiveness = round(
            (company_quality * 0.50) + (valuation_score * 0.35) + (risk_score * 0.15),
            1,
        )

        # 3. Listing Opportunity (Valuation discount + GMP sentiment + subscription momentum)
        sentiment_boost = 0.0
        if gmp_gain_pct >= 25.0:
            sentiment_boost += 2.0
        elif gmp_gain_pct >= 10.0:
            sentiment_boost += 1.0
        elif gmp_gain_pct < 0.0:
            sentiment_boost -= 2.0

        if subscription_times >= 10.0:
            sentiment_boost += 1.0

        listing_raw = (valuation_score * 0.40) + (company_quality * 0.30) + 2.0 + sentiment_boost
        listing_opp = max(1.0, min(10.0, round(listing_raw, 1)))

        # 4. Long-Term Opportunity (Quality + Moat + Low Governance Risk)
        long_term_raw = (company_quality * 0.60) + (governance_score * 0.20) + (valuation_score * 0.20)
        long_term_opp = max(1.0, min(10.0, round(long_term_raw, 1)))

        # Overall verdict
        if ipo_attractiveness >= 7.5:
            verdict = "ATTRACTIVE"
        elif ipo_attractiveness >= 5.5:
            verdict = "NEUTRAL"
        else:
            verdict = "AVOID"

        return {
            "company_quality": company_quality,
            "ipo_attractiveness": ipo_attractiveness,
            "listing_opportunity": listing_opp,
            "long_term_opportunity": long_term_opp,
            "verdict": verdict,
        }
