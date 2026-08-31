"""
Grey Market Premium (GMP) Signal Analysis Engine.
IMPORTANT: Strictly labels GMP as an 'Unofficial Market Sentiment Indicator'.
GMP never dominates fundamental ratings, but informs short-term listing expectations.
"""

from typing import Dict, Any, List, Optional
from src.calculations.math import FinancialMath


class GMPAnalyzer:
    """Evaluates unofficial Grey Market Premium signals and listing gain estimates."""

    @staticmethod
    def evaluate_gmp(
        gmp_value: Optional[float],
        issue_price: Optional[float],
        trend: str = "STABLE",
    ) -> Dict[str, Any]:
        """
        Evaluate estimated listing gain from GMP.
        """
        if gmp_value is None or issue_price is None or issue_price <= 0:
            return {
                "gmp_value": None,
                "potential_listing_gain_pct": None,
                "estimated_listing_price": None,
                "gmp_signal": "NO_DATA",
                "disclaimer": "⚠️ Unofficial market sentiment indicator. Not an official exchange price.",
            }

        est_listing_price = round(issue_price + gmp_value, 2)
        gain_pct = FinancialMath.calculate_listing_gain_pct(issue_price, gmp_value)

        if gain_pct is not None:
            if gain_pct >= 30.0:
                signal = "STRONG_LISTING_DEMAND"
            elif gain_pct >= 10.0:
                signal = "MODERATE_LISTING_DEMAND"
            elif gain_pct >= 0.0:
                signal = "FLAT_LISTING_EXPECTATION"
            else:
                signal = "DISCOUNT_LISTING_RISK"
        else:
            signal = "NO_DATA"

        return {
            "gmp_value": gmp_value,
            "estimated_listing_price": est_listing_price,
            "potential_listing_gain_pct": gain_pct,
            "gmp_signal": signal,
            "trend": trend,
            "disclaimer": "⚠️ Unofficial market sentiment indicator. Subject to high volatility prior to listing.",
        }
