"""Auditable Reviewer-Controlled Verification Workflow.

Enforces that candidates extracted from documents, PDFs, or tables CANNOT be promoted
to VERIFIED status automatically or solely based on source-host allowlists.
A promotion requires explicit human/reviewer audit, provenance validation, period/basis
checks, and writes an immutable entry into the system audit log.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Fact, FinancialPeriod, AuditLog, IPO


class FactReviewService:
    """Manages audited transitions from candidate facts to VERIFIED canonical facts."""

    CRITICAL_TARGET_FIELDS = {
        "revenue_from_operations": "revenue_latest",
        "profit_after_tax": "pat_latest",
        "operating_cash_flow": "cfo_latest",
        "revenue_latest": "revenue_latest",
        "pat_latest": "pat_latest",
        "cfo_latest": "cfo_latest",
        "min_price": "min_price",
        "max_price": "max_price",
        "lot_size": "lot_size",
        "issue_size_cr": "issue_size_cr",
        "fresh_issue_cr": "fresh_issue_cr",
        "ofs_cr": "ofs_cr",
    }

    @staticmethod
    async def list_candidate_facts(
        session: AsyncSession,
        ipo_id: int,
        status: str = "UNVERIFIED",
    ) -> List[Dict[str, Any]]:
        """List candidate facts for an IPO that await reviewer evaluation."""
        stmt = (
            select(Fact)
            .where(Fact.ipo_id == ipo_id, Fact.verification_status == status)
            .order_by(Fact.id.asc())
        )
        res = await session.execute(stmt)
        facts = res.scalars().all()

        output = []
        for fact in facts:
            candidate_payload = None
            if fact.value_type == "JSON" and fact.value_text:
                try:
                    candidate_payload = json.loads(fact.value_text)
                except Exception:
                    pass

            output.append({
                "id": fact.id,
                "ipo_id": fact.ipo_id,
                "field_name": fact.field_name,
                "value_text": fact.value_text,
                "value_numeric": fact.value_numeric,
                "value_type": fact.value_type,
                "source_name": fact.source_name,
                "source_url": fact.source_url,
                "source_tier": fact.source_tier,
                "document_id": fact.document_id,
                "document_version": fact.document_version,
                "page_number": fact.page_number,
                "verification_status": fact.verification_status,
                "candidate_metadata": candidate_payload,
            })
        return output

    @classmethod
    async def review_and_promote_fact(
        cls,
        session: AsyncSession,
        *,
        fact_id: int,
        reviewer_id: str,
        decision: str,
        target_field_name: Optional[str] = None,
        verified_numeric_value: Optional[float] = None,
        notes: str = "",
        override_conflict: bool = False,
    ) -> Dict[str, Any]:
        """Review a candidate fact and transition it to VERIFIED or REJECTED with audit logging."""
        cleaned_reviewer = str(reviewer_id or "").strip()
        if not cleaned_reviewer:
            raise ValueError("Reviewer identity (reviewer_id) must be specified for auditable verification.")

        cleaned_notes = str(notes or "").strip()
        if not cleaned_notes:
            raise ValueError("Audit notes explaining verification rationale and document citation are required.")

        decision_upper = str(decision or "").strip().upper()
        if decision_upper not in {"VERIFIED", "REJECTED"}:
            raise ValueError("Decision must be either 'VERIFIED' or 'REJECTED'.")

        stmt = select(Fact).where(Fact.id == fact_id)
        res = await session.execute(stmt)
        candidate = res.scalars().first()
        if candidate is None:
            raise ValueError(f"Fact with ID {fact_id} not found.")

        now_utc = datetime.now(timezone.utc)

        if decision_upper == "REJECTED":
            candidate.verification_status = "REJECTED"
            candidate.confidence = "LOW"
            audit = AuditLog(
                timestamp=now_utc,
                event_type="FACT_REJECTION",
                entity_name="Fact",
                entity_id=str(candidate.id),
                description=f"Candidate fact #{candidate.id} rejected by {cleaned_reviewer}: {cleaned_notes}",
                metadata_json={
                    "reviewer_id": cleaned_reviewer,
                    "fact_id": candidate.id,
                    "field_name": candidate.field_name,
                    "notes": cleaned_notes,
                },
            )
            session.add(audit)
            await session.flush()
            return {
                "fact_id": candidate.id,
                "decision": "REJECTED",
                "reviewer_id": cleaned_reviewer,
                "verified_field_name": None,
                "value_numeric": None,
            }

        # Handle VERIFIED promotion
        candidate_meta: Dict[str, Any] = {}
        if candidate.value_type == "JSON" and candidate.value_text:
            try:
                candidate_meta = json.loads(candidate.value_text)
            except Exception:
                pass

        # Provenance validation
        if not candidate.source_url or not str(candidate.source_url).startswith("https://"):
            raise ValueError("Cannot verify candidate with missing or non-HTTPS source URL.")

        # If candidate metadata exists, enforce period & basis checks
        if candidate_meta:
            period = candidate_meta.get("period")
            period_label = period.get("label") if isinstance(period, dict) else None
            if not period_label:
                raise ValueError("Cannot verify candidate with missing or ambiguous financial period.")

            statement_basis = str(candidate_meta.get("statement_basis") or "").upper()
            if statement_basis not in {"CONSOLIDATED", "STANDALONE"}:
                raise ValueError("Cannot verify candidate with missing or ambiguous statement basis.")

            if verified_numeric_value is None:
                norm_str = candidate_meta.get("normalized_value_inr_crore")
                if norm_str is None:
                    raise ValueError("Cannot verify candidate lacking explicit unit or normalized INR Crore value.")
                try:
                    verified_numeric_value = float(Decimal(str(norm_str)))
                except Exception as exc:
                    raise ValueError("Normalized candidate value cannot be converted to float.") from exc

        # Determine canonical field name
        canonical = target_field_name
        if not canonical:
            canonical = cls.CRITICAL_TARGET_FIELDS.get(candidate.field_name, candidate.field_name)

        if verified_numeric_value is None and candidate.value_numeric is not None:
            verified_numeric_value = float(candidate.value_numeric)

        if verified_numeric_value is None:
            raise ValueError("A verified numeric value is required to promote a financial fact.")

        # Create the canonical VERIFIED fact
        verified_fact = Fact(
            ipo_id=candidate.ipo_id,
            field_name=canonical,
            value_text=str(verified_numeric_value),
            value_numeric=verified_numeric_value,
            value_type="NUMBER",
            source_name=f"AUDITED_REVIEWER:{cleaned_reviewer}",
            source_url=candidate.source_url,
            source_tier="TIER_1",
            document_id=candidate.document_id,
            document_version=candidate.document_version,
            page_number=candidate.page_number,
            confidence="HIGH",
            verification_status="VERIFIED",
            extracted_at=now_utc,
        )
        session.add(verified_fact)

        # Mark candidate as REVIEWED_PROMOTED to maintain historical trace
        candidate.verification_status = "REVIEWED_PROMOTED"

        # Record audit log
        audit = AuditLog(
            timestamp=now_utc,
            event_type="FACT_VERIFICATION",
            entity_name="Fact",
            entity_id=str(candidate.id),
            description=(
                f"Candidate fact #{candidate.id} promoted to VERIFIED field '{canonical}' "
                f"with value {verified_numeric_value} Cr by {cleaned_reviewer}"
            ),
            metadata_json={
                "reviewer_id": cleaned_reviewer,
                "candidate_fact_id": candidate.id,
                "original_field": candidate.field_name,
                "canonical_field": canonical,
                "verified_value_cr": verified_numeric_value,
                "source_url": candidate.source_url,
                "page_number": candidate.page_number,
                "notes": cleaned_notes,
                "override_conflict": override_conflict,
            },
        )
        session.add(audit)
        await session.flush()

        return {
            "candidate_fact_id": candidate.id,
            "verified_fact_id": verified_fact.id,
            "decision": "VERIFIED",
            "reviewer_id": cleaned_reviewer,
            "canonical_field_name": canonical,
            "verified_numeric_value": verified_numeric_value,
            "source_url": candidate.source_url,
            "audit_logged": True,
        }
