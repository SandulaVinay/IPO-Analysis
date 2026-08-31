"""
Deterministic Mathematical & Financial Calculations Engine.
Strictly programmatic: NO LLM is used for any numerical or financial math.
"""

from typing import Optional, List, Dict, Any
import numpy as np


class FinancialMath:
    """Deterministic mathematical functions for financial and valuation analysis."""

    @staticmethod
    def calculate_cagr(start_val: Optional[float], end_val: Optional[float], periods: int) -> Optional[float]:
        """
        Compute Compound Annual Growth Rate (CAGR).
        Handles edge cases: negative starting/ending value, zero, periods <= 0.
        """
        if start_val is None or end_val is None or periods <= 0:
            return None
        if start_val <= 0:
            # CAGR is mathematically undefined or misleading with non-positive start
            return None
        if end_val < 0:
            return None

        cagr = (end_val / start_val) ** (1.0 / periods) - 1.0
        return round(float(cagr * 100.0), 2)

    @staticmethod
    def calculate_margin(numerator: Optional[float], revenue: Optional[float]) -> Optional[float]:
        """Compute profit/cost margin as a percentage of revenue."""
        if numerator is None or revenue is None or revenue <= 0:
            return None
        return round(float((numerator / revenue) * 100.0), 2)

    @staticmethod
    def calculate_post_ipo_shares(pre_shares: Optional[float], fresh_shares: Optional[float]) -> Optional[float]:
        """Total post-IPO shares in Cr."""
        if pre_shares is None:
            return None
        return round(float(pre_shares + (fresh_shares or 0.0)), 4)

    @staticmethod
    def calculate_post_ipo_market_cap(
        issue_price: Optional[float],
        post_issue_shares_cr: Optional[float],
    ) -> Optional[float]:
        """Post-IPO Market Capitalization in ₹ Crores."""
        if issue_price is None or post_issue_shares_cr is None or issue_price <= 0:
            return None
        return round(float(issue_price * post_issue_shares_cr), 2)

    @staticmethod
    def calculate_enterprise_value(
        market_cap_cr: Optional[float],
        total_debt_cr: Optional[float],
        cash_cr: Optional[float],
    ) -> Optional[float]:
        """Enterprise Value = Market Cap + Total Debt - Cash & Cash Equivalents."""
        if market_cap_cr is None:
            return None
        debt = total_debt_cr or 0.0
        cash = cash_cr or 0.0
        return round(float(market_cap_cr + debt - cash), 2)

    @staticmethod
    def calculate_pe_ratio(price: Optional[float], eps: Optional[float]) -> Optional[float]:
        """Price-to-Earnings (P/E) Ratio."""
        if price is None or eps is None or eps <= 0:
            return None
        return round(float(price / eps), 2)

    @staticmethod
    def calculate_ev_ebitda(ev_cr: Optional[float], ebitda_cr: Optional[float]) -> Optional[float]:
        """Enterprise Value to EBITDA."""
        if ev_cr is None or ebitda_cr is None or ebitda_cr <= 0:
            return None
        return round(float(ev_cr / ebitda_cr), 2)

    @staticmethod
    def calculate_pb_ratio(price: Optional[float], book_value_per_share: Optional[float]) -> Optional[float]:
        """Price-to-Book (P/B) Ratio."""
        if price is None or book_value_per_share is None or book_value_per_share <= 0:
            return None
        return round(float(price / book_value_per_share), 2)

    @staticmethod
    def calculate_ev_revenue(ev_cr: Optional[float], revenue_cr: Optional[float]) -> Optional[float]:
        """EV to Revenue."""
        if ev_cr is None or revenue_cr is None or revenue_cr <= 0:
            return None
        return round(float(ev_cr / revenue_cr), 2)

    @staticmethod
    def calculate_listing_gain_pct(issue_price: Optional[float], gmp: Optional[float]) -> Optional[float]:
        """Estimated Listing Gain Percentage = (GMP / Issue Price) * 100."""
        if issue_price is None or gmp is None or issue_price <= 0:
            return None
        return round(float((gmp / issue_price) * 100.0), 2)

    @staticmethod
    def calculate_cash_conversion_ratio(cfo: Optional[float], pat: Optional[float]) -> Optional[float]:
        """Cash Conversion = CFO / PAT."""
        if cfo is None or pat is None or pat <= 0:
            return None
        return round(float(cfo / pat), 2)

    @staticmethod
    def calculate_fcf_conversion_ratio(fcf: Optional[float], pat: Optional[float]) -> Optional[float]:
        """Free Cash Flow Conversion = FCF / PAT."""
        if fcf is None or pat is None or pat <= 0:
            return None
        return round(float(fcf / pat), 2)

    @staticmethod
    def calculate_dilution_pct(pre_shares: Optional[float], post_shares: Optional[float]) -> Optional[float]:
        """Percentage dilution in equity."""
        if not pre_shares or not post_shares or post_shares <= 0:
            return None
        dilution = (post_shares - pre_shares) / post_shares
        return round(float(dilution * 100.0), 2)

    @staticmethod
    def calculate_premium_discount_vs_peers(ipo_multiple: Optional[float], peer_median: Optional[float]) -> Optional[float]:
        """Percentage Premium (+) or Discount (-) relative to peer median multiple."""
        if ipo_multiple is None or peer_median is None or peer_median <= 0:
            return None
        diff = (ipo_multiple - peer_median) / peer_median * 100.0
        return round(float(diff), 2)
