"""
Unit tests for Timezone, Calendar Days, and Trading Holiday calculations.
"""

from datetime import date, datetime
from src.common.timezone import (
    to_ist,
    to_utc,
    is_trading_holiday,
    calculate_t_minus_target,
    days_until,
    IST,
)


def test_timezone_conversions():
    # 09:00 IST is 03:30 UTC
    dt_ist = datetime(2026, 9, 18, 9, 0, 0, tzinfo=IST)
    dt_utc = to_utc(dt_ist)
    assert dt_utc.hour == 3
    assert dt_utc.minute == 30

    # Convert back to IST
    back_ist = to_ist(dt_utc)
    assert back_ist.hour == 9
    assert back_ist.minute == 0


def test_trading_holidays_and_weekends():
    # Weekend Saturday
    sat = date(2026, 9, 19)
    assert sat.weekday() == 5
    assert is_trading_holiday(sat) is True

    # Republic Day (Jan 26)
    rep_day = date(2026, 1, 26)
    assert is_trading_holiday(rep_day) is True


def test_calculate_t_minus_target():
    open_date = date(2026, 9, 18)
    t2_target = calculate_t_minus_target(open_date, days_before=2)
    assert t2_target.date() == date(2026, 9, 16)
    assert t2_target.hour == 9
    assert t2_target.minute == 0
