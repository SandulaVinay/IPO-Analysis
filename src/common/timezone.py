"""
Timezone and date calculation utilities for Indian stock markets (Asia/Kolkata).
Handles trading holidays, calendar days calculations, and UTC/IST conversions.
"""

from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Set

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")

# Standard NSE/BSE Trading Holidays list for reference & market calendar checking
NSE_HOLIDAYS_2025_2026: Set[date] = {
    date(2025, 1, 26),  # Republic Day
    date(2025, 2, 26),  # Mahashivratri
    date(2025, 3, 14),  # Holi
    date(2025, 3, 31),  # Id-Ul-Fitr
    date(2025, 4, 10),  # Mahavir Jayanti
    date(2025, 4, 14),  # Dr. Baba Saheb Ambedkar Jayanti
    date(2025, 4, 18),  # Good Friday
    date(2025, 5, 1),   # Maharashtra Day
    date(2025, 8, 15),  # Independence Day
    date(2025, 8, 27),  # Ganesh Chaturthi
    date(2025, 10, 2),  # Mahatma Gandhi Jayanti
    date(2025, 10, 21), # Diwali Laxmi Pujan
    date(2025, 10, 22), # Diwali Balipratipada
    date(2025, 11, 5),  # Gurunanak Jayanti
    date(2025, 12, 25), # Christmas
    date(2026, 1, 26),  # Republic Day
    date(2026, 3, 3),   # Holi
    date(2026, 3, 20),  # Id-Ul-Fitr
    date(2026, 4, 3),   # Good Friday
    date(2026, 4, 14),  # Ambedkar Jayanti
    date(2026, 5, 1),   # Maharashtra Day
    date(2026, 8, 15),  # Independence Day
    date(2026, 10, 2),  # Gandhi Jayanti
    date(2026, 11, 8),  # Diwali
    date(2026, 12, 25), # Christmas
}


def get_current_ist_time() -> datetime:
    """Return current datetime localized to Asia/Kolkata."""
    return datetime.now(IST)


def get_current_ist_date() -> date:
    """Return current date in Asia/Kolkata."""
    return get_current_ist_time().date()


def to_utc(dt: datetime) -> datetime:
    """Ensure datetime is converted to UTC with timezone awareness."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(UTC)


def to_ist(dt: datetime) -> datetime:
    """Convert any datetime to IST."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)


def format_ist(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M IST") -> str:
    """Format datetime as IST string."""
    if dt is None:
        return "N/A"
    return to_ist(dt).strftime(fmt)


def is_trading_holiday(d: date) -> bool:
    """Check if date is weekend or an official trading holiday."""
    if d.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return True
    return d in NSE_HOLIDAYS_2025_2026


def calculate_t_minus_target(open_date: date, days_before: int = 2) -> datetime:
    """
    Calculate the target alert dispatch time (e.g. T-2 at 09:00 IST).
    Target: 2 calendar days before open_date at 09:00 AM IST.
    """
    target_date = open_date - timedelta(days=days_before)
    target_time = time(hour=9, minute=0, second=0)
    return datetime.combine(target_date, target_time, tzinfo=IST)


def days_until(target_date: date) -> int:
    """Calculate remaining calendar days until target_date from current IST date."""
    current_date = get_current_ist_date()
    return (target_date - current_date).days
