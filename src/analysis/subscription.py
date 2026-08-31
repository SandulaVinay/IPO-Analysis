"""
Subscription Momentum & Anchor Investor Quality Analysis Module.
Monitors bidding progression across Retail, NII, QIB, and Employee categories during open days.
Tracks Anchor investor tier quality and lock-in windows.
"""

from typing import Dict, Any, List, Optional


class SubscriptionAnalyzer:
    """Evaluates bidding demand dynamics across categories (Retail, NII, QIB)."""

    @staticmethod
    def analyze_subscription(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        snapshots: list of category subscription updates across Day 1, 2, 3.
        """
        if not snapshots:
            return {
                "overall_subscription_times": 0.0,
                "qib_times": 0.0,
                "nii_times": 0.0,
                "retail_times": 0.0,
                "momentum_signal": "PRE_BIDDING",
                "insights": ["Bidding window not yet opened."],
            }

        latest = snapshots[-1]
        overall = latest.get("overall_times") or 0.0
        qib = latest.get("qib_times") or 0.0
        nii = latest.get("nii_times") or 0.0
        retail = latest.get("retail_times") or 0.0
        day = latest.get("day_number", 1)

        insights: List[str] = []
        if overall >= 20.0:
            momentum = "HIGH_DEMAND"
            insights.append(f"Heavy oversubscription ({overall}x) across investor categories.")
        elif overall >= 3.0:
            momentum = "HEALTHY_DEMAND"
            insights.append(f"Healthy subscription ({overall}x on Day {day}).")
        elif overall >= 1.0:
            momentum = "FULLY_SUBSCRIBED"
            insights.append(f"Issue fully subscribed ({overall}x).")
        else:
            momentum = "UNDERSUBSCRIBED"
            insights.append(f"⚠️ Undersubscribed so far ({overall}x on Day {day}).")

        if qib >= 10.0:
            insights.append(f"Strong institutional validation: QIB subscribed {qib}x.")

        return {
            "day_number": day,
            "overall_subscription_times": overall,
            "qib_times": qib,
            "nii_times": nii,
            "retail_times": retail,
            "momentum_signal": momentum,
            "insights": insights,
        }
