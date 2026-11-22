"""
Rules-only IPO status (Stage 1): APPLY, NEUTRAL, AVOID, WAIT or UNABLE_TO_ASSESS.

Inputs are only GMP (unofficial), issue price and Day 3 subscription. Financials are
NOT used here, so every status is labelled "Indicative". Thresholds are starting
values, not calibrated; they stay labelled until the Stage 4 backtest is done.

Rules, checked in order:
  1. Official sources disagree (SOURCE_CONFLICT)            -> WAIT
  2. No GMP or no issue price                               -> UNABLE_TO_ASSESS
  3. Estimated listing gain below 0%                        -> AVOID
  4. Subscription not available                             -> NEUTRAL (capped; never APPLY)
  5. Estimated gain >= 30% AND Day 3 subscription >= 10x    -> APPLY
  6. Anything else                                          -> NEUTRAL
"""

from typing import Any, Dict, List, Optional

from src.calculations.math import FinancialMath

LABEL = "Indicative (GMP and subscription only; financials not verified)"

APPLY_MIN_GAIN_PCT = 30.0
APPLY_MIN_SUBSCRIPTION_TIMES = 10.0


def ipo_status(
    *,
    source_conflict: bool,
    gmp_value: Optional[float],
    issue_price: Optional[float],
    overall_subscription: Optional[float],
) -> Dict[str, Any]:
    """Return the status, the estimated listing gain and the reasons behind it."""
    reasons: List[str] = []
    gain: Optional[float] = None
    if gmp_value is not None and issue_price and issue_price > 0:
        gain = FinancialMath.calculate_listing_gain_pct(issue_price, gmp_value)

    if source_conflict:
        status = "WAIT"
        reasons.append("official sources disagree on dates or price; verify before relying on any status")
    elif gain is None:
        status = "UNABLE_TO_ASSESS"
        reasons.append("no usable GMP or issue price, so no listing-gain estimate")
    elif gain < 0:
        status = "AVOID"
        reasons.append(f"grey market trades below issue price (estimated {gain:.1f}%)")
    elif overall_subscription is None:
        status = "NEUTRAL"
        reasons.append(f"estimated listing gain {gain:.1f}%, but subscription data is not connected, so no APPLY")
    elif gain >= APPLY_MIN_GAIN_PCT and overall_subscription >= APPLY_MIN_SUBSCRIPTION_TIMES:
        status = "APPLY"
        reasons.append(
            f"estimated listing gain {gain:.1f}% and Day 3 subscription {overall_subscription:.1f}x "
            f"meet the starting thresholds ({APPLY_MIN_GAIN_PCT:.0f}% and {APPLY_MIN_SUBSCRIPTION_TIMES:.0f}x)"
        )
    else:
        status = "NEUTRAL"
        reasons.append(
            f"estimated listing gain {gain:.1f}% and subscription {overall_subscription:.1f}x "
            f"do not both meet the starting thresholds"
        )

    return {
        "status": status,
        "label": LABEL,
        "estimated_listing_gain_pct": None if gain is None else round(gain, 1),
        "reasons": reasons,
    }
