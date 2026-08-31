"""
Evidence Store.
Enforces strict segregation of:
1. FACT (Directly sourced with document version and page citation)
2. CALCULATION (Deterministically derived programmatically)
3. OPINION (Structured qualitative analysis or judgment)
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class EvidenceStore:
    """Manages segregated facts, calculations, and analytical opinions."""

    def __init__(self):
        self.facts: List[Dict[str, Any]] = []
        self.calculations: List[Dict[str, Any]] = []
        self.opinions: List[Dict[str, Any]] = []

    def record_fact(
        self,
        field_name: str,
        value: Any,
        source: str,
        source_tier: str = "TIER_1",
        document_version: Optional[str] = None,
        page_number: Optional[int] = None,
        source_url: Optional[str] = None,
        confidence: str = "HIGH",
    ) -> Dict[str, Any]:
        """Store atomic verified fact."""
        fact = {
            "type": "FACT",
            "field_name": field_name,
            "value": value,
            "source": source,
            "source_tier": source_tier,
            "document_version": document_version,
            "page_number": page_number,
            "source_url": source_url,
            "confidence": confidence,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        self.facts.append(fact)
        return fact

    def record_calculation(
        self,
        calculation_name: str,
        result: Any,
        formula: str,
        input_keys: List[str],
    ) -> Dict[str, Any]:
        """Store deterministic programmatic calculation."""
        calc = {
            "type": "CALCULATION",
            "calculation_name": calculation_name,
            "result": result,
            "formula": formula,
            "input_keys": input_keys,
            "calculated_at": datetime.utcnow().isoformat(),
        }
        self.calculations.append(calc)
        return calc

    def record_opinion(
        self,
        aspect: str,
        opinion_text: str,
        supporting_calculation_names: Optional[List[str]] = None,
        supporting_fact_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Store analytical judgment with explicit supporting dependency chains."""
        opinion = {
            "type": "OPINION",
            "aspect": aspect,
            "opinion_text": opinion_text,
            "supporting_calculations": supporting_calculation_names or [],
            "supporting_facts": supporting_fact_keys or [],
            "generated_at": datetime.utcnow().isoformat(),
        }
        self.opinions.append(opinion)
        return opinion

    def get_evidence_manifest(self) -> Dict[str, Any]:
        """Return structured dump of all facts, calculations, and opinions."""
        return {
            "facts_count": len(self.facts),
            "calculations_count": len(self.calculations),
            "opinions_count": len(self.opinions),
            "facts": self.facts,
            "calculations": self.calculations,
            "opinions": self.opinions,
        }
