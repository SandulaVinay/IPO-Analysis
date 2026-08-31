"""
Post-Listing Feedback Loop & Historical Outcome Evaluation Engine.
Tracks actual listing performance, 30D, 90D, and 1Y post-listing returns.
Calculates directional accuracy, recommendation quality, false positive/negative rates, and confidence calibration.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import IPO, PerformanceOutcome
from src.database.repository import IPORepository


class FeedbackEngine:
    """Evaluates prediction error and long-term recommendation quality."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = IPORepository(session)

    @staticmethod
    def evaluate_listing_accuracy(
        issue_price: float,
        actual_listing_price: float,
        predicted_listing_gain_pct: Optional[float],
        recommendation_verdict: str,
    ) -> Dict[str, Any]:
        """
        Evaluate listing day accuracy and whether recommendation proved profitable.
        """
        actual_gain_pct = round(((actual_listing_price - issue_price) / issue_price * 100.0), 2)
        pred_gain = predicted_listing_gain_pct or 0.0
        error_pct = round(abs(actual_gain_pct - pred_gain), 2)

        # Profitable if gain > 0 for attractive, or gain <= 0 for avoid
        is_gain = actual_gain_pct > 0.0
        is_false_positive = (recommendation_verdict == "ATTRACTIVE" and not is_gain)
        is_false_negative = (recommendation_verdict == "AVOID" and actual_gain_pct > 15.0)

        was_profitable = (recommendation_verdict == "ATTRACTIVE" and is_gain) or (recommendation_verdict == "AVOID" and not is_gain)

        return {
            "issue_price": issue_price,
            "listing_price": actual_listing_price,
            "actual_listing_gain_pct": actual_gain_pct,
            "predicted_listing_gain_pct": pred_gain,
            "prediction_error_pct": error_pct,
            "was_profitable": was_profitable,
            "is_false_positive": is_false_positive,
            "is_false_negative": is_false_negative,
        }

    async def record_actual_listing(
        self,
        ipo_id: int,
        actual_listing_price: float,
        predicted_listing_gain_pct: Optional[float],
        verdict: str,
    ) -> PerformanceOutcome:
        """Persist listing outcome in database."""
        ipo = await self.repo.get_ipo_by_id(ipo_id)
        if not ipo:
            raise ValueError(f"IPO with ID {ipo_id} not found")

        issue_price = ipo.max_price or ipo.min_price or actual_listing_price
        eval_metrics = self.evaluate_listing_accuracy(
            issue_price=issue_price,
            actual_listing_price=actual_listing_price,
            predicted_listing_gain_pct=predicted_listing_gain_pct,
            recommendation_verdict=verdict,
        )

        outcome = PerformanceOutcome(
            ipo_id=ipo_id,
            issue_price=issue_price,
            listing_price=actual_listing_price,
            listing_gain_pct=eval_metrics["actual_listing_gain_pct"],
            predicted_listing_gain_pct=eval_metrics["predicted_listing_gain_pct"],
            listing_error_pct=eval_metrics["prediction_error_pct"],
            was_recommendation_profitable=eval_metrics["was_profitable"],
            is_false_positive=eval_metrics["is_false_positive"],
            is_false_negative=eval_metrics["is_false_negative"],
        )
        self.session.add(outcome)
        await self.repo.transition_state(
            ipo_id=ipo_id,
            new_status="LISTING_DAY_ANALYSIS",
            trigger="FEEDBACK_ENGINE",
            notes=f"Actual Listing Day Recorded: ₹{actual_listing_price} (+{eval_metrics['actual_listing_gain_pct']}%)",
        )
        await self.session.commit()
        return outcome
