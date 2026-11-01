"""Conservative reconciliation of financial extraction candidates.

Agreement between extracted values is not proof of truth. This module groups
comparable candidates and reports missing metadata/conflicts, but never upgrades
a candidate to VERIFIED. Official-source validation and human/rule-based review
remain separate release gates.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple

VALID_BASES = {"STANDALONE", "CONSOLIDATED"}


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() else None


def _candidate_key(candidate: Dict[str, Any]) -> Tuple[str, str, str]:
    period = candidate.get("period")
    period_label = period.get("label") if isinstance(period, dict) else None
    basis = str(candidate.get("statement_basis") or "").upper()
    return (
        str(candidate.get("field_name") or "").strip(),
        str(period_label or "").strip(),
        basis,
    )


def reconcile_financial_candidates(candidates: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Group comparable candidates and flag conflicts without verifying any value.

    Candidates lacking a field, explicit period, valid statement basis, or
    normalized INR-crore value are returned as unresolved and excluded from
    comparison groups. Values are compared exactly as Decimals: the module does
    not invent a rounding tolerance or choose a winner.
    """
    groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    unresolved: List[Dict[str, Any]] = []
    candidate_count = 0

    for original in candidates or []:
        candidate_count += 1
        item = dict(original or {})
        field_name, period_label, basis = _candidate_key(item)
        value = _decimal(item.get("normalized_value_inr_crore"))
        reasons: List[str] = []
        if not field_name:
            reasons.append("FIELD_MISSING")
        if not period_label:
            reasons.append("PERIOD_MISSING_OR_AMBIGUOUS")
        if basis not in VALID_BASES:
            reasons.append("STATEMENT_BASIS_MISSING_OR_AMBIGUOUS")
        if value is None:
            reasons.append("NORMALIZED_VALUE_UNAVAILABLE")
        if not item.get("source_url") or not item.get("document_hash"):
            reasons.append("PROVENANCE_INCOMPLETE")

        item["reconciliation_status"] = "UNRESOLVED_METADATA" if reasons else "PENDING_COMPARISON"
        item["reconciliation_reasons"] = reasons
        item["verification_status"] = "CANDIDATE_UNVERIFIED"
        if reasons:
            unresolved.append(item)
            continue
        item["_comparison_value"] = value
        groups[(field_name, period_label, basis)].append(item)

    results: List[Dict[str, Any]] = []
    for (field_name, period_label, basis), items in sorted(groups.items()):
        values = {item["_comparison_value"] for item in items}
        distinct_sources = {
            str(item.get("source_url")).strip()
            for item in items
            if item.get("source_url")
        }
        if len(values) > 1:
            status = "CONFLICT"
            reasons = ["Comparable candidates contain different normalized values."]
        elif len(distinct_sources) < 2:
            status = "SINGLE_SOURCE_UNCONFIRMED"
            reasons = ["Only one distinct source URL is represented; independent corroboration is absent."]
        else:
            status = "MATCHING_CANDIDATES_UNVERIFIED"
            reasons = [
                "Values agree across source URLs, but source authority and original statements have not been independently verified."
            ]

        public_items = []
        for item in items:
            cleaned = {key: value for key, value in item.items() if key != "_comparison_value"}
            cleaned["reconciliation_status"] = status
            cleaned["reconciliation_reasons"] = list(reasons)
            cleaned["verification_status"] = "CANDIDATE_UNVERIFIED"
            public_items.append(cleaned)

        results.append({
            "field_name": field_name,
            "period": period_label,
            "statement_basis": basis,
            "status": status,
            "candidate_count": len(items),
            "distinct_source_count": len(distinct_sources),
            "values_inr_crore": sorted(str(value) for value in values),
            "reasons": reasons,
            "candidates": public_items,
            "verification_status": "CANDIDATE_UNVERIFIED",
        })

    return {
        "candidate_count": candidate_count,
        "comparable_group_count": len(results),
        "unresolved_count": len(unresolved),
        "conflict_count": sum(1 for group in results if group["status"] == "CONFLICT"),
        "groups": results,
        "unresolved_candidates": unresolved,
        "verification_status": "CANDIDATE_UNVERIFIED",
        "assessment_eligible": False,
        "notice": "Reconciliation organizes evidence only; no candidate is verified or eligible for scoring.",
    }
