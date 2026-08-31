"""
Anchor Investor Book Quality Analyzer.
Analyzes marquee domestic mutual funds, sovereign wealth funds, marquee FPIs, and lock-in allocations.
"""

from typing import Dict, Any, List, Optional


class AnchorAnalyzer:
    """Evaluates institutional quality of the anchor book."""

    MARQUEE_INSTITUTIONS = {
        "HDFC MUTUAL FUND",
        "ICICI PRUDENTIAL",
        "SBI MUTUAL FUND",
        "NIPPON INDIA",
        "KOTAK MAHINDRA",
        "ABU DHABI INVESTMENT AUTHORITY",
        "GOVERNMENT PENSION FUND GLOBAL",
        "SINGAPORE GOVERNMENT",
        "FIDELITY",
        "BLACKROCK",
    }

    @classmethod
    def analyze_anchor_book(cls, anchors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Evaluate anchor allocations.
        """
        if not anchors:
            return {
                "total_anchor_amount_cr": 0.0,
                "anchor_count": 0,
                "has_marquee_institutional_backing": False,
                "insights": ["Anchor allocation list not yet published or SME issue."],
            }

        total_amount = sum(a.get("amount_cr", 0.0) for a in anchors)
        marquee_found = []

        for a in anchors:
            name = a.get("investor_name", "").upper()
            for marquee in cls.MARQUEE_INSTITUTIONS:
                if marquee in name:
                    marquee_found.append(a.get("investor_name"))
                    break

        has_marquee = len(marquee_found) >= 2
        insights: List[str] = [
            f"Anchor book raised ₹{round(total_amount, 2)} Cr across {len(anchors)} institutional investors."
        ]

        if has_marquee:
            insights.append(f"Strong marquee backing: {', '.join(marquee_found[:3])}.")

        return {
            "total_anchor_amount_cr": round(total_amount, 2),
            "anchor_count": len(anchors),
            "has_marquee_institutional_backing": has_marquee,
            "marquee_investors": marquee_found,
            "insights": insights,
        }
