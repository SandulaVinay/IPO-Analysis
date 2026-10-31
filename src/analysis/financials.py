"""Conservative financial-statement trend analysis.

Scores are emitted only when at least two periods contain revenue and PAT.
Missing evidence is represented as UNABLE_TO_ASSESS, not as a neutral score.
"""
from typing import Dict, Any, List
from src.calculations.math import FinancialMath


class FinancialAnalyzer:
    """Evaluates financial growth, balance-sheet health, and earnings quality."""

    @staticmethod
    def analyze_financials(periods: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze chronologically ordered periods with revenue/PAT in a consistent unit."""
        if not isinstance(periods, list) or len(periods) < 2:
            return FinancialAnalyzer._unable_to_assess(
                "At least two comparable financial periods are required."
            )

        first = periods[0]
        latest = periods[-1]
        required = ("revenue", "pat")
        missing = [
            f"{period.get('period_name', f'period {index + 1}')}.{field}"
            for index, period in enumerate(periods)
            for field in required
            if not isinstance(period, dict) or period.get(field) is None
        ]
        if missing:
            return FinancialAnalyzer._unable_to_assess(
                "Revenue and PAT are required for every period; missing: " + ", ".join(missing[:6]) + "."
            )

        insights: List[str] = []
        red_flags: List[str] = []
        score = 6.0
        earnings_score = 7.0
        num_years = len(periods) - 1

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

        latest_pat = latest["pat"]
        latest_cfo = latest.get("cfo")
        if latest_pat < 0:
            score -= 3.0
            red_flags.append(f"Loss-making entity in latest period (PAT: -₹{abs(latest_pat)} Cr).")
            if latest_cfo is not None and latest_cfo < 0:
                score -= 1.0
                red_flags.append(
                    f"Negative operating cash flow (CFO: -₹{abs(latest_cfo)} Cr) indicates ongoing operational cash burn."
                )

        if latest_pat > 0 and latest_cfo is not None:
            cfo_pat_ratio = FinancialMath.calculate_cash_conversion_ratio(latest_cfo, latest_pat)
            if cfo_pat_ratio is not None:
                if cfo_pat_ratio >= 0.8:
                    earnings_score += 1.5
                    insights.append(f"Healthy cash conversion: CFO/PAT ratio is {cfo_pat_ratio}x.")
                elif cfo_pat_ratio < 0.0:
                    earnings_score -= 3.5
                    red_flags.append(
                        f"Negative operating cash flow (CFO: -₹{abs(latest_cfo)} Cr) despite positive PAT."
                    )
                elif cfo_pat_ratio < 0.4:
                    earnings_score -= 2.5
                    red_flags.append(
                        f"Weak earnings quality: CFO/PAT ratio is only {cfo_pat_ratio}x (profits not translating into cash)."
                    )

        net_debt = latest.get("net_debt")
        net_worth = latest.get("net_worth")
        if net_debt is not None and net_worth is not None and net_worth > 0:
            debt_equity = round(net_debt / net_worth, 2)
            if debt_equity <= 0.0:
                score += 1.0
                insights.append("Net cash positive / zero debt company.")
            elif debt_equity > 2.0:
                score -= 2.0
                red_flags.append(f"High financial leverage: Net Debt/Equity is {debt_equity}x.")

        return {
            "assessment_status": "ASSESSED_WITH_LIMITATIONS" if latest_cfo is None else "ASSESSED",
            "financial_quality_score": max(1.0, min(10.0, round(score, 1))),
            "earnings_quality_score": (
                max(1.0, min(10.0, round(earnings_score, 1))) if latest_cfo is not None else None
            ),
            "revenue_cagr": rev_cagr,
            "pat_cagr": pat_cagr,
            "cfo_cagr": cfo_cagr,
            "insights": insights,
            "red_flags": red_flags,
            "is_loss_making": latest_pat < 0,
            "limitations": [] if latest_cfo is not None else ["Latest-period operating cash flow is unavailable; earnings-quality score omitted."],
        }

    @staticmethod
    def _unable_to_assess(reason: str) -> Dict[str, Any]:
        return {
            "assessment_status": "UNABLE_TO_ASSESS",
            "financial_quality_score": None,
            "earnings_quality_score": None,
            "revenue_cagr": None,
            "pat_cagr": None,
            "cfo_cagr": None,
            "insights": [reason],
            "red_flags": [],
            "is_loss_making": None,
            "limitations": [reason],
        }
