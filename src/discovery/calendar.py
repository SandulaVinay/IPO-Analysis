"""
IPO Calendar and timeline calculations.
Evaluates window status, listing dates, and alert dispatch deadlines in IST.
"""

from datetime import date, datetime, timedelta
from typing import Optional, Tuple
from src.common.timezone import (
    get_current_ist_date,
    get_current_ist_time,
    calculate_t_minus_target,
    days_until,
    is_trading_holiday,
)


class IPOCalendar:
    """Manages IPO scheduling, windows, and alert trigger timestamps."""

    @staticmethod
    def get_lifecycle_stage(
        open_date: Optional[date],
        close_date: Optional[date],
        listing_date: Optional[date],
    ) -> str:
        """Determine real-time lifecycle stage based on current IST date."""
        today = get_current_ist_date()

        if not open_date:
            return "IPO_DISCOVERED"

        if today < open_date:
            days_left = (open_date - today).days
            if days_left > 2:
                return "ALERT_SCHEDULED"
            elif days_left == 2:
                return "T_MINUS_2_ALERT_SENT"
            else:
                return "T_MINUS_1_REMINDER_SENT"

        if open_date <= today <= (close_date or open_date):
            return "IPO_OPENED"

        if close_date and today > close_date:
            if not listing_date or today < listing_date:
                return "ALLOTMENT_MONITORING"
            elif today == listing_date:
                return "LISTING_DAY_ANALYSIS"
            elif (today - listing_date).days <= 30:
                return "POST_LISTING_30D"
            elif (today - listing_date).days <= 90:
                return "POST_LISTING_90D"
            elif (today - listing_date).days <= 365:
                return "POST_LISTING_1Y"
            else:
                return "PERFORMANCE_EVALUATED"

        return "IPO_DISCOVERED"

    @staticmethod
    def should_trigger_t_minus_2(open_date: date) -> bool:
        """Check if T-2 alert should be dispatched now."""
        today = get_current_ist_date()
        days_diff = (open_date - today).days
        # Trigger on T-2 or immediately if verified information is available late
        return days_diff <= 2 and days_diff >= 0

    @staticmethod
    def should_trigger_t_minus_1(open_date: date) -> bool:
        """Check if T-1 day-before reminder should be dispatched."""
        today = get_current_ist_date()
        return (open_date - today).days == 1
