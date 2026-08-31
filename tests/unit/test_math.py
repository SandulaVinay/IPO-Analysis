"""
Unit tests for Deterministic Financial Math Engine.
Verifies CAGRs, margin calculations, enterprise value, multiples, dilution, and edge cases.
"""

import pytest
from src.calculations.math import FinancialMath


def test_calculate_cagr():
    # Standard 3-year CAGR: 100 to 172.8 is exactly 20.0%
    cagr = FinancialMath.calculate_cagr(100.0, 172.8, 3)
    assert cagr == 20.0

    # 2-year CAGR: 500 to 720
    cagr2 = FinancialMath.calculate_cagr(500.0, 720.0, 2)
    assert cagr2 == 20.0

    # Edge cases
    assert FinancialMath.calculate_cagr(None, 200.0, 2) is None
    assert FinancialMath.calculate_cagr(100.0, None, 2) is None
    assert FinancialMath.calculate_cagr(100.0, 200.0, 0) is None
    assert FinancialMath.calculate_cagr(-50.0, 100.0, 2) is None  # Negative start
    assert FinancialMath.calculate_cagr(100.0, -20.0, 2) is None  # Negative end


def test_calculate_margins_and_multiples():
    # Margin
    assert FinancialMath.calculate_margin(20.0, 100.0) == 20.0
    assert FinancialMath.calculate_margin(None, 100.0) is None

    # Post-IPO Shares
    assert FinancialMath.calculate_post_ipo_shares(10.0, 2.0) == 12.0

    # Market Cap: Issue price 475, shares 12 Cr -> ₹5,700 Cr
    assert FinancialMath.calculate_post_ipo_market_cap(475.0, 12.0) == 5700.0

    # Enterprise Value: MC 5700 + Debt 300 - Cash 200 -> ₹5,800 Cr
    assert FinancialMath.calculate_enterprise_value(5700.0, 300.0, 200.0) == 5800.0

    # P/E Ratio: Price 475, EPS 19 -> 25.0x
    assert FinancialMath.calculate_pe_ratio(475.0, 19.0) == 25.0
    assert FinancialMath.calculate_pe_ratio(475.0, 0.0) is None

    # EV/EBITDA: EV 5800, EBITDA 580 -> 10.0x
    assert FinancialMath.calculate_ev_ebitda(5800.0, 580.0) == 10.0

    # Dilution: Pre 10 Cr, Post 12 Cr -> (12-10)/12 = 16.67%
    assert FinancialMath.calculate_dilution_pct(10.0, 12.0) == 16.67

    # Listing Gain: Price 475, GMP 95 -> 20.0%
    assert FinancialMath.calculate_listing_gain_pct(475.0, 95.0) == 20.0

    # Cash Conversion: CFO 80, PAT 100 -> 0.8x
    assert FinancialMath.calculate_cash_conversion_ratio(80.0, 100.0) == 0.8
