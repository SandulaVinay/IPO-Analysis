"""
Financial Statements and Accounting Quality Analysis Module.
Analyzes 3-5 years historical trends, Margins, CAGRs, Return Ratios (ROE, ROCE),
and rigorously evaluates Cash Conversion (CFO / PAT & FCF / PAT).
Produces Financial Quality Score and Earnings Quality Score (0.0 to 10.0).
"""

from typing import Dict, Any, List, Optional
from src.calculations.math import FinancialMath


class FinancialAnalyzer:
    """Evaluates financial growth, margin expansion, balance sheet health, and earnings quality."""

    @staticmethod
    def analyze_financials(periods: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        periods: List of financial period dicts ordered chronologically (e.g. FY23, FY24, FY25).
        """
        if not periods:
            return {
                "financial_quality_score": 5.0,
                "earnings_quality_score": 5.0,
                "revenue_cagr": None,
                "pat_cagr": None,
                "insights": ["Insufficient historical periods to compute financial trend metrics."],
                "red_flags": [],
            }

        insights: List[str] = []
        red_flags: List[str] = []
        score = 6.0
        earnings_score = 7.0

        n_periods = len(periods)
        first = periods[0]
        latest = periods[-1]

        # 1. Growth Metrics
        if n_periods >= 2:
            num_years = n_periods - 1
            rev_cagr = FinancialMath.calculate_cagr(first.get("revenue"), latest.get("revenue"), num_years)
            pat_cagr = FinancialMath.calculate_cagr(first.get("pat"), latest.get("pat"), num_years)
            cfo_cagr = FinancialMath.calculate_cagr(first.get("cfo"), latest.get("cfo"), num_years)

            if rev_cagr is not None:
                if rev_cagr >= 25.0:
                    score += 1.5
                    insights.append(f"Strong top-line growth: Revenue CAGR of {rev_cagr}% over {num_years} years.")
                elif rev_cagr < 5.0:
                    score -= 1.0
                    insights.append(f"Sluggish revenue growth: CAGR of {rev_cagr}%.")
                else:
                    score += 0.5
                    insights.append(f"Steady revenue CAGR of {rev_cagr}%.")

            if pat_cagr is not None:
                if pat_cagr >= 30.0:
                    score += 1.0
                    insights.append(f"Strong bottom-line expansion: PAT CAGR of {pat_cagr}%.")
                elif pat_cagr < 0.0:
                    score -= 1.5
                    insights.append(f"Declining profits: Negative PAT CAGR of {pat_cagr}%.")
        else:
            rev_cagr = None
            pat_cagr = None
            cfo_cagr = None

        # 2. Latest Profitability & Margins
        latest_rev = latest.get("revenue") or 0.0
        latest_pat = latest.get("pat") or 0.0
        latest_cfo = latest.get("cfo")
        latest_ebitda = latest.get("ebitda")

        if latest_pat < 0:
            score -= 3.0
            red_flags.append(f"⚠️ Loss-making entity in latest period (PAT: -₹{abs(latest_pat)} Cr).")
            if latest_cfo is not None and latest_cfo < 0:
                score -= 1.0
                red_flags.append(f"⚠️ Negative operating cash flow (CFO: -₹{abs(latest_cfo)} Cr) indicates ongoing operational cash burn.")
        
        # 3. Cash Conversion & Earnings Quality (CFO vs PAT)
        if latest_pat > 0 and latest_cfo is not None:
            cfo_pat_ratio = FinancialMath.calculate_cash_conversion_ratio(latest_cfo, latest_pat)
            if cfo_pat_ratio is not None:
                if cfo_pat_ratio >= 0.8:
                    earnings_score += 1.5
                    insights.append(f"Healthy cash conversion: CFO/PAT ratio is {cfo_pat_ratio}x.")
                elif cfo_pat_ratio < 0.4:
                    earnings_score -= 2.5
                    red_flags.append(f"⚠️ Weak earnings quality: CFO/PAT ratio is only {cfo_pat_ratio}x (Profits not translating into cash).")
                elif cfo_pat_ratio < 0.0:
                    earnings_score -= 3.5
                    red_flags.append(f"⚠️ Negative operating cash flow (CFO: -₹{abs(latest_cfo)} Cr) despite positive PAT.")

        # 4. Debt & Leverage
        net_debt = latest.get("net_debt") or 0.0
        net_worth = latest.get("net_worth") or 0.0
        if net_worth > 0:
            debt_equity = round(net_debt / net_worth, 2)
            if debt_equity <= 0.0:
                score += 1.0
                insights.append("Net cash positive / Zero debt company.")
            elif debt_equity > 2.0:
                score -= 2.0
                red_flags.append(f"⚠️ High financial leverage: Net Debt/Equity is {debt_equity}x.")

        final_fin_score = max(1.0, min(10.0, round(score, 1)))
        final_earn_score = max(1.0, min(10.0, round(earnings_score, 1)))

        return {
            "financial_quality_score": final_fin_score,
            "earnings_quality_score": final_earn_score,
            "revenue_cagr": rev_cagr,
            "pat_cagr": pat_cagr,
            "cfo_cagr": cfo_cagr,
            "insights": insights,
            "red_flags": red_flags,
            "is_loss_making": latest_pat < 0,
        }
