"""Conservative parsing helpers for financial-statement evidence.

This module creates *candidates*, not verified facts. It deliberately refuses to
normalize amounts without an explicit unit and refuses to infer statement basis
or reporting period from a number alone. Verification/reconciliation must happen
before any output is supplied to scoring.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

CANDIDATE_STATUS = "CANDIDATE_UNVERIFIED"

# Multipliers convert explicitly stated units to INR crore.
_UNIT_TO_CRORE = {
    "rupees": Decimal("0.0000001"),
    "inr": Decimal("0.0000001"),
    "thousand": Decimal("0.0001"),
    "thousands": Decimal("0.0001"),
    "lakh": Decimal("0.01"),
    "lakhs": Decimal("0.01"),
    "lac": Decimal("0.01"),
    "lacs": Decimal("0.01"),
    "crore": Decimal("1"),
    "crores": Decimal("1"),
    "cr": Decimal("1"),
    "million": Decimal("0.1"),
    "millions": Decimal("0.1"),
    "billion": Decimal("10"),
    "billions": Decimal("10"),
}

_UNIT_PATTERNS = (
    (re.compile(r"\b(?:₹|rs\.?|inr)\s*(?:in\s*)?(?:crores?|cr)\b", re.I), "crore"),
    (re.compile(r"\b(?:₹|rs\.?|inr)\s*(?:in\s*)?lakhs?\b|\b(?:₹|rs\.?|inr)\s*(?:in\s*)?lacs?\b", re.I), "lakh"),
    (re.compile(r"\b(?:₹|rs\.?|inr)\s*(?:in\s*)?thousands?\b", re.I), "thousand"),
    (re.compile(r"\b(?:₹|rs\.?|inr)\s*(?:in\s*)?millions?\b", re.I), "million"),
    (re.compile(r"\b(?:₹|rs\.?|inr)\s*(?:in\s*)?billions?\b", re.I), "billion"),
    (re.compile(r"\b(?:amounts?\s+in|figures?\s+in|in)\s+crores?\b", re.I), "crore"),
    (re.compile(r"\b(?:amounts?\s+in|figures?\s+in|in)\s+lakhs?\b|\b(?:amounts?\s+in|figures?\s+in|in)\s+lacs?\b", re.I), "lakh"),
    (re.compile(r"\b(?:amounts?\s+in|figures?\s+in|in)\s+thousands?\b", re.I), "thousand"),
    (re.compile(r"\b(?:amounts?\s+in|figures?\s+in|in)\s+millions?\b", re.I), "million"),
    (re.compile(r"\b(?:amounts?\s+in|figures?\s+in|in)\s+billions?\b", re.I), "billion"),
)

_NUMBER_RE = re.compile(r"^\s*(?:₹|rs\.?|inr)?\s*([+-]?(?:\d[\d,]*\.?\d*|\.\d+))\s*$", re.I)


def parse_numeric_value(raw_value: Any) -> Optional[Decimal]:
    """Parse a numeric cell, including Indian comma grouping and parentheses negatives."""
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text or text.casefold() in {"-", "—", "–", "n/a", "na", "nil", "not available"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()
    match = _NUMBER_RE.fullmatch(text)
    if not match:
        return None
    numeric = match.group(1).replace(",", "")
    try:
        value = Decimal(numeric)
    except InvalidOperation:
        return None
    return -abs(value) if negative else value


def detect_explicit_unit(context: str) -> Optional[str]:
    """Return a unit only when the surrounding text explicitly names one."""
    text = str(context or "")
    for pattern, unit in _UNIT_PATTERNS:
        if pattern.search(text):
            return unit
    # Common statement headers such as '(₹ in lakhs)'.
    compact = re.sub(r"\s+", " ", text).casefold()
    if re.search(r"₹\s*(?:in\s*)?crores?\b|\bin\s+crores?\b", compact):
        return "crore"
    if re.search(r"₹\s*(?:in\s*)?lakhs?\b|\bin\s+lakhs?\b", compact):
        return "lakh"
    if re.search(r"₹\s*(?:in\s*)?thousands?\b|\bin\s+thousands?\b", compact):
        return "thousand"
    if re.search(r"₹\s*(?:in\s*)?millions?\b|\bin\s+millions?\b", compact):
        return "million"
    if re.search(r"₹\s*(?:in\s*)?billions?\b|\bin\s+billions?\b", compact):
        return "billion"
    return None


def normalize_to_inr_crore(raw_value: Any, unit_context: str) -> Dict[str, Any]:
    """Return a transparent normalization result; missing units never imply rupees/crores."""
    value = parse_numeric_value(raw_value)
    unit = detect_explicit_unit(unit_context)
    if value is None:
        return {"raw_value": None if raw_value is None else str(raw_value), "parsed_value": None,
                "unit": unit, "value_inr_crore": None, "status": CANDIDATE_STATUS,
                "reason": "Value is blank, non-numeric, or uses an unsupported numeric format."}
    if unit is None:
        return {"raw_value": str(raw_value), "parsed_value": str(value), "unit": None,
                "value_inr_crore": None, "status": CANDIDATE_STATUS,
                "reason": "Unit is not explicit; normalization withheld."}
    factor = _UNIT_TO_CRORE[unit]
    normalized = value * factor
    return {"raw_value": str(raw_value), "parsed_value": str(value), "unit": unit,
            "value_inr_crore": str(normalized), "status": CANDIDATE_STATUS,
            "reason": "Unit conversion is mechanical only; source period, basis, and reconciliation remain unverified."}


def identify_statement_basis(context: str) -> Optional[str]:
    """Identify basis only if exactly one explicit basis marker appears."""
    text = str(context or "").casefold()
    consolidated = bool(re.search(r"\bconsolidated\b", text))
    standalone = bool(re.search(r"\bstandalone\b", text))
    if consolidated == standalone:  # neither or both
        return None
    return "CONSOLIDATED" if consolidated else "STANDALONE"


def identify_financial_period(context: str) -> Optional[Dict[str, str]]:
    """Recognize explicit FY labels only; do not infer a period from a bare date/number."""
    text = str(context or "")
    match = re.search(
        r"\b(?:FY\s*)?(20\d{2})\s*[-/]\s*(?:(20\d{2})|(\d{2}))\b",
        text,
        re.I,
    )
    if match:
        start = int(match.group(1))
        end_text = match.group(2) or (f"20{match.group(3)}" if match.group(3) else "")
        if end_text:
            end = int(end_text)
            if end == start + 1:
                return {"period_type": "FINANCIAL_YEAR", "label": f"FY{start}-{end}"}
    single = re.search(r"\bFY\s*(20\d{2})\b", text, re.I)
    if single:
        year = int(single.group(1))
        return {"period_type": "FINANCIAL_YEAR", "label": f"FY{year}"}
    return None


def build_financial_candidate(
    *,
    field_name: str,
    raw_value: Any,
    row_label: str,
    header_context: str,
    source_url: str,
    document_hash: str,
    page_number: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a provenance-bearing candidate that can never claim verification."""
    context = f"{row_label} {header_context}"
    normalized = normalize_to_inr_crore(raw_value, header_context)
    period = identify_financial_period(context)
    basis = identify_statement_basis(context)
    reasons = [normalized["reason"]]
    if period is None:
        reasons.append("Reporting period is not explicit or could not be parsed.")
    if basis is None:
        reasons.append("Statement basis is missing or ambiguous.")
    return {
        "field_name": field_name,
        "raw_value": None if raw_value is None else str(raw_value),
        "parsed_value": normalized["parsed_value"],
        "normalized_value_inr_crore": normalized["value_inr_crore"],
        "unit": normalized["unit"],
        "period": period,
        "statement_basis": basis,
        "row_label": str(row_label or ""),
        "header_context": str(header_context or ""),
        "source_url": source_url,
        "document_hash": document_hash,
        "page_number": page_number,
        "verification_status": CANDIDATE_STATUS,
        "normalization_reasons": reasons,
    }
