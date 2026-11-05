"""Auditable Reviewer-Controlled Verification Workflow.

Enforces that candidates extracted from documents, PDFs, or tables CANNOT be promoted
to VERIFIED status automatically or solely based on source-host allowlists.
A promotion requires explicit human/reviewer audit, provenance validation, period/basis
checks, and writes an immutable entry into the system audit log.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Fact, FinancialPeriod, AuditLog, IPO


class FactReviewService:
    """Manages audited transitions from candidate facts to VERIFIED canonical facts."""

    FINANCIAL_STATEMENT_FIELDS = {
        "revenue_from_operations",
        "profit_after_tax",
        "operating_cash_flow",
        "revenue_latest",
        "pat_latest",
        "cfo_latest",
        "ebitda_latest",
        "net_worth",
        "total_debt",
    }

    CRITICAL_TARGET_FIELDS = {
        # Core financial statement metrics
        "revenue_from_operations": "revenue_latest",
        "profit_after_tax": "pat_latest",
        "operating_cash_flow": "cfo_latest",
        "revenue_latest": "revenue_latest",
        "pat_latest": "pat_latest",
        "cfo_latest": "cfo_latest",
        "ebitda_latest": "ebitda_latest",
        "net_worth": "net_worth",
        "total_debt": "total_debt",

        # Core issue terms
        "min_price": "min_price",
        "max_price": "max_price",
        "lot_size": "lot_size",
        "issue_size_cr": "issue_size_cr",
        "fresh_issue_cr": "fresh_issue_cr",
        "ofs_cr": "ofs_cr",
        "verified_open_date": "verified_open_date",
        "verified_close_date": "verified_close_date",

        # Business Quality
        "top5_customer_concentration_pct": "top5_customer_concentration_pct",
        "recurring_revenue_pct": "recurring_revenue_pct",
        "has_proprietary_tech_or_moat": "has_proprietary_tech_or_moat",
        "is_cyclical": "is_cyclical",
        "business_description": "business_description",

        # Governance & Management
        "promoter_pre_holding_pct": "promoter_pre_holding_pct",
        "promoter_post_holding_pct": "promoter_post_holding_pct",
        "promoter_pledge_pct": "promoter_pledge_pct",
        "has_auditor_qualifications": "has_auditor_qualifications",
        "frequent_auditor_changes": "frequent_auditor_changes",
        "rpt_revenue_pct": "rpt_revenue_pct",
        "has_promoter_litigation": "has_promoter_litigation",

        # Structure & Proceeds
        "capex_growth_cr": "capex_growth_cr",
        "debt_repayment_cr": "debt_repayment_cr",

        # Valuation & Peers
        "peer_median_pe": "peer_median_pe",
        "peer_median_ev_ebitda": "peer_median_ev_ebitda",
        "post_issue_shares_cr": "post_issue_shares_cr",
        "cash_cr": "cash_cr",

        # Risk & Market
        "risk_register": "risk_register",
        "nifty_50dma_status": "nifty_50dma_status",
        "midcap_sentiment": "midcap_sentiment",
        "recent_ipos_avg_listing_gain_pct": "recent_ipos_avg_listing_gain_pct",
        "india_vix": "india_vix",
    }

    @staticmethod
    async def list_candidate_facts(
        session: AsyncSession,
        ipo_id: int,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List candidate facts for an IPO that await reviewer evaluation."""
        stmt = select(Fact).where(Fact.ipo_id == ipo_id)
        if status is None:
            stmt = stmt.where(Fact.verification_status.in_(
                ("UNVERIFIED", "CANDIDATE_UNVERIFIED", "CONFLICTED")
            ))
        else:
            stmt = stmt.where(Fact.verification_status == status.upper())
        stmt = stmt.order_by(Fact.id.asc())
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
        verified_value_text: Optional[str] = None,
        verified_value_type: Optional[str] = None,
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

        stmt = select(Fact).where(Fact.id == fact_id).with_for_update()
        res = await session.execute(stmt)
        candidate = res.scalars().first()
        if candidate is None:
            raise ValueError(f"Fact with ID {fact_id} not found.")

        current_status = str(candidate.verification_status or "").upper()
        if current_status not in {"UNVERIFIED", "CANDIDATE_UNVERIFIED", "CONFLICTED"}:
            raise ValueError(
                f"Candidate fact cannot be reviewed from status {current_status or 'UNKNOWN'}; "
                "only pending candidates may be reviewed."
            )

        now_utc = datetime.now(timezone.utc)

        if decision_upper == "REJECTED":
            claim = await session.execute(
                update(Fact)
                .where(
                    Fact.id == candidate.id,
                    Fact.verification_status == candidate.verification_status,
                )
                .values(verification_status="REJECTED", confidence="LOW")
            )
            if claim.rowcount != 1:
                raise ValueError("Candidate was already reviewed by another request; reload before retrying.")
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
                parsed_meta = json.loads(candidate.value_text)
            except (TypeError, ValueError) as exc:
                raise ValueError("Candidate JSON metadata is malformed and cannot be verified.") from exc
            if isinstance(parsed_meta, dict):
                candidate_meta = parsed_meta
            elif isinstance(parsed_meta, list):
                if candidate.field_name in cls.FINANCIAL_STATEMENT_FIELDS:
                    raise ValueError("Candidate JSON metadata must be an object.")
                candidate_meta = {}
            else:
                raise ValueError("Candidate JSON metadata must be an object.")

        # Provenance validation
        if not candidate.source_url or not str(candidate.source_url).startswith("https://"):
            raise ValueError("Cannot verify candidate with missing or non-HTTPS source URL.")

        # Resolve the canonical field before comparing evidence. Different extraction
        # labels can map to the same production field and must share one conflict domain.
        canonical = str(target_field_name or cls.CRITICAL_TARGET_FIELDS.get(
            candidate.field_name, candidate.field_name
        )).strip()
        if not canonical:
            raise ValueError("A canonical target field name is required.")

        # If candidate metadata exists, enforce period & basis checks for financial statements
        if candidate_meta:
            period = candidate_meta.get("period")
            period_label = period.get("label") if isinstance(period, dict) else None
            statement_basis = str(candidate_meta.get("statement_basis") or "").upper()

            if canonical in cls.FINANCIAL_STATEMENT_FIELDS:
                if not period_label:
                    raise ValueError("Cannot verify candidate with missing or ambiguous financial period.")
                if statement_basis not in {"CONSOLIDATED", "STANDALONE"}:
                    raise ValueError("Cannot verify candidate with missing or ambiguous statement basis.")

            if verified_numeric_value is None:
                norm_str = candidate_meta.get("normalized_value_inr_crore")
                if norm_str is not None:
                    try:
                        verified_numeric_value = float(Decimal(str(norm_str)))
                    except Exception as exc:
                        raise ValueError("Normalized candidate value cannot be converted to float.") from exc
                elif canonical in cls.FINANCIAL_STATEMENT_FIELDS:
                    raise ValueError("Cannot verify candidate lacking explicit unit or normalized INR Crore value.")
                elif candidate.value_numeric is not None:
                    verified_numeric_value = candidate.value_numeric
                elif "value_numeric" in candidate_meta:
                    try:
                        verified_numeric_value = float(Decimal(str(candidate_meta["value_numeric"])))
                    except Exception:
                        pass

        # Compare independent evidence from all statuses except explicitly rejected
        # candidates. REVIEWED_PROMOTED rows are deliberately included: their JSON
        # payload preserves period/basis/value and prevents later reviewers from
        # silently contradicting an already verified source.
        conflict_details: List[Dict[str, Any]] = []
        if candidate_meta and verified_numeric_value is not None:
            period = candidate_meta.get("period")
            period_label = period.get("label") if isinstance(period, dict) else None
            statement_basis = str(candidate_meta.get("statement_basis") or "").upper()
            reviewed_decimal = Decimal(str(verified_numeric_value))
            if not reviewed_decimal.is_finite():
                raise ValueError("A verified finite numeric value is required to compare financial evidence.")
            peer_stmt = select(Fact).where(
                Fact.ipo_id == candidate.ipo_id,
                Fact.id != candidate.id,
            )
            peer_res = await session.execute(peer_stmt)
            for peer in peer_res.scalars().all():
                peer_status = str(peer.verification_status or "").upper()
                if peer_status == "REJECTED":
                    continue
                peer_canonical = cls.CRITICAL_TARGET_FIELDS.get(peer.field_name, peer.field_name)
                if peer_canonical != canonical:
                    continue

                same_source_url = (
                    str(peer.source_url or "").strip().rstrip("/")
                    == str(candidate.source_url or "").strip().rstrip("/")
                )
                same_document = (
                    peer.document_id == candidate.document_id
                    if peer.document_id is not None or candidate.document_id is not None
                    else True
                )
                if same_source_url and same_document:
                    continue

                if peer.value_type != "JSON" or not peer.value_text:
                    continue
                try:
                    peer_meta = json.loads(peer.value_text)
                except (TypeError, ValueError):
                    continue
                if not isinstance(peer_meta, dict):
                    continue
                peer_period = peer_meta.get("period")
                peer_period_label = peer_period.get("label") if isinstance(peer_period, dict) else None
                peer_basis = str(peer_meta.get("statement_basis") or "").upper()
                if canonical in cls.FINANCIAL_STATEMENT_FIELDS:
                    if peer_period_label != period_label or peer_basis != statement_basis:
                        continue
                peer_value = peer_meta.get("normalized_value_inr_crore", peer_meta.get("value_numeric"))
                if peer_value is None:
                    continue
                try:
                    peer_decimal = Decimal(str(peer_value))
                except Exception:
                    continue
                if peer_decimal.is_finite() and peer_decimal != reviewed_decimal:
                    conflict_details.append({
                        "fact_id": peer.id,
                        "verification_status": peer_status,
                        "field_name": peer.field_name,
                        "canonical_field_name": peer_canonical,
                        "source_url": peer.source_url,
                        "normalized_value_inr_crore": str(peer_decimal),
                    })

        if conflict_details and not override_conflict:
            raise ValueError(
                "Conflicting evidence exists for the same canonical field, period, and statement basis. "
                "Resolve the conflict or explicitly set override_conflict=True with an audit rationale."
            )

        if verified_value_type:
            value_type = str(verified_value_type).strip().upper()
        elif candidate_meta or candidate.value_numeric is not None or verified_numeric_value is not None:
            value_type = "NUMBER"
        else:
            value_type = str(candidate.value_type or "STRING").strip().upper()

        value_numeric: Optional[float] = None
        if value_type in {"NUMBER", "NUMERIC", "FLOAT"}:
            raw_numeric: Any = verified_numeric_value
            if raw_numeric is None and candidate_meta:
                raw_numeric = candidate_meta.get("normalized_value_inr_crore")
            if raw_numeric is None:
                raw_numeric = candidate.value_numeric
            if raw_numeric is None:
                raw_numeric = verified_value_text if verified_value_text is not None else candidate.value_text
            try:
                value_numeric = float(Decimal(str(raw_numeric)))
            except Exception as exc:
                raise ValueError("A verified finite numeric value is required to promote this fact.") from exc
            if not math.isfinite(value_numeric):
                raise ValueError("A verified finite numeric value is required to promote this fact.")
            value_type = "NUMBER"
            value_text = str(value_numeric)
        elif value_type in {"BOOLEAN", "BOOL"}:
            raw_boolean: Any = verified_value_text if verified_value_text is not None else candidate.value_text
            if verified_numeric_value is not None:
                raw_boolean = verified_numeric_value
            elif candidate.value_numeric is not None:
                raw_boolean = candidate.value_numeric
            if isinstance(raw_boolean, bool):
                parsed_boolean = raw_boolean
            elif isinstance(raw_boolean, (int, float)):
                if raw_boolean in (1, 1.0):
                    parsed_boolean = True
                elif raw_boolean in (0, 0.0):
                    parsed_boolean = False
                else:
                    raise ValueError("Boolean facts must be explicitly reviewed as true/false or 1/0.")
            else:
                normalized_boolean = str(raw_boolean or "").strip().lower()
                if normalized_boolean in {"true", "1", "1.0", "yes", "present"}:
                    parsed_boolean = True
                elif normalized_boolean in {"false", "0", "0.0", "no", "absent"}:
                    parsed_boolean = False
                else:
                    raise ValueError("Boolean facts must be explicitly reviewed as true/false or 1/0.")
            value_type = "BOOLEAN"
            value_numeric = 1.0 if parsed_boolean else 0.0
            value_text = "true" if parsed_boolean else "false"
        elif value_type == "DATE":
            raw_date = str(verified_value_text if verified_value_text is not None else candidate.value_text or "").strip()
            try:
                value_text = date.fromisoformat(raw_date[:10]).isoformat()
            except ValueError as exc:
                raise ValueError("Date facts must be reviewed in ISO YYYY-MM-DD format.") from exc
        elif value_type in {"STRING", "TEXT"}:
            value_text = str(verified_value_text if verified_value_text is not None else candidate.value_text or "").strip()
            if not value_text:
                raise ValueError("A non-empty reviewed text value is required to promote this fact.")
            value_type = "STRING"
        elif value_type == "JSON":
            value_text = str(verified_value_text if verified_value_text is not None else candidate.value_text or "").strip()
            if not value_text:
                raise ValueError("A non-empty reviewed JSON value is required to promote this fact.")
            try:
                json.loads(value_text)
            except Exception as exc:
                raise ValueError("JSON facts must be valid JSON.") from exc
            value_type = "JSON"
            value_numeric = None
        else:
            raise ValueError("Verified fact type must be NUMBER, BOOLEAN, DATE, STRING, or JSON.")

        # Optimistic compare-and-set protects against concurrent reviewer requests.
        # The row lock above serializes this on PostgreSQL; the conditional UPDATE
        # also protects databases that do not implement SELECT FOR UPDATE.
        claim = await session.execute(
            update(Fact)
            .where(
                Fact.id == candidate.id,
                Fact.verification_status == current_status,
            )
            .values(verification_status="REVIEWED_PROMOTED")
        )
        if claim.rowcount != 1:
            raise ValueError("Candidate was already reviewed by another request; reload before retrying.")
        candidate.verification_status = "REVIEWED_PROMOTED"

        # Create the canonical VERIFIED fact
        verified_fact = Fact(
            ipo_id=candidate.ipo_id,
            field_name=canonical,
            value_text=value_text,
            value_numeric=value_numeric,
            value_type=value_type,
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

        # Record audit log
        audit = AuditLog(
            timestamp=now_utc,
            event_type="FACT_VERIFICATION",
            entity_name="Fact",
            entity_id=str(candidate.id),
            description=(
                f"Candidate fact #{candidate.id} promoted to VERIFIED field '{canonical}' "
                f"with reviewed value '{value_text}' by {cleaned_reviewer}"
            ),
            metadata_json={
                "reviewer_id": cleaned_reviewer,
                "candidate_fact_id": candidate.id,
                "original_field": candidate.field_name,
                "canonical_field": canonical,
                "period_label": (candidate_meta.get("period") or {}).get("label") if isinstance(candidate_meta.get("period"), dict) else None,
                "statement_basis": str(candidate_meta.get("statement_basis") or "").upper() or None,
                "verified_numeric_value": value_numeric,
                "verified_value_text": value_text,
                "verified_value_type": value_type,
                "source_url": candidate.source_url,
                "page_number": candidate.page_number,
                "notes": cleaned_notes,
                "override_conflict": override_conflict,
                "conflict_details": conflict_details,
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
            "verified_numeric_value": value_numeric,
            "verified_value_text": value_text,
            "verified_value_type": value_type,
            "source_url": candidate.source_url,
            "audit_logged": True,
        }
