"""
Entity normalization, parsing, and cleaning utilities.
Standardizes company names, symbols, dates, price bands, and issue sizes.
"""

import re
from datetime import date, datetime
from typing import Optional, Tuple, Dict, Any


class Normalizer:
    """Normalizes raw unstructured IPO data into standardized types."""

    @staticmethod
    def clean_company_name(name: str) -> str:
        """Strip suffixes and whitespace."""
        name = re.sub(r"\s+", " ", name).strip()
        # Keep legal entity title clean
        return name

    @staticmethod
    def generate_symbol(company_name: str) -> str:
        """Generate standardized symbol from company name."""
        cleaned = re.sub(r"[^A-Za-z0-9\s]", "", company_name)
        tokens = cleaned.upper().split()
        if not tokens:
            return "UNKNOWN_IPO"
        # Take first 2-3 words, join with underscore
        return "_".join(tokens[:3])

    @staticmethod
    def parse_date(date_str: Any) -> Optional[date]:
        """Parse various Indian & ISO date formats into standard date object."""
        if not date_str:
            return None
        if isinstance(date_str, date):
            return date_str
        if isinstance(date_str, datetime):
            return date_str.date()

        date_str = str(date_str).strip()
        formats = [
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%d %b %Y",
            "%d %B %Y",
            "%b %d, %Y",
            "%B %d, %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def parse_price_band(text: str) -> Tuple[Optional[float], Optional[float]]:
        """Extract min and max price from strings like '₹450 to ₹475' or '450-475'."""
        if not text:
            return None, None
        nums = re.findall(r"(\d+(?:\.\d+)?)", text)
        if len(nums) == 1:
            val = float(nums[0])
            return val, val
        elif len(nums) >= 2:
            return float(nums[0]), float(nums[1])
        return None, None

    @staticmethod
    def parse_currency_cr(text: Any) -> Optional[float]:
        """Parse currency amounts in ₹ Crores."""
        if text is None:
            return None
        if isinstance(text, (int, float)):
            return float(text)
        text_str = str(text).replace(",", "").strip()
        nums = re.findall(r"(\d+(?:\.\d+)?)", text_str)
        if nums:
            return float(nums[0])
        return None
