"""
Decision and Scoring Engine.
Computes weighted composite score across 8 standardized pillars using configurable settings.
Integrates Hard Safety Gates and Multi-Horizon Decision outputs.
"""

from typing import Dict, Any, List, Optional
import math
from src.common.config import settings
from src.scoring.safety_gates import SafetyGateEvaluator
from src.scoring.horizons import MultiHorizonClassifier


class ScoringEngine:
    """Computes transparent, explainable scores across all dimensions."""

    def __init__(self):
        self.weights = {
            "business_quality": settings.weight_business_quality,
            "financial_quality": settings.weight_financial_quality,
            "management_governance": settings.weight_management_governance,
            "ipo_structure": settings.weight_ipo_structure,
            "valuation": settings.weight_valuation,
            "growth_industry": settings.weight_growth_industry,
            "risk": settings.weight_risk,
            "market_sentiment": settings.weight_market_sentiment,
        }

    def compute_decision(
        self,
        business_score: Optional[float],
        financial_score: Optional[float],
        governance_score: Optional[float],
        structure_score: Optional[float],
        valuation_score: Optional[float],
        growth_score: Optional[float],
        risk_score: Optional[float],
        sentiment_score: Optional[float],
        completeness_info: Dict[str, Any],
        conflict_info: Dict[str, Any],
        management_info: Dict[str, Any],
        financial_info: Dict[str, Any],
        gmp_gain_pct: float = 0.0,
        subscription_times: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Evaluate full decision model.
        """
        # 1. Evaluate Hard Safety Gates
        is_gated, gate_reasons = SafetyGateEvaluator.evaluate_gates(
            completeness_info=completeness_info,
            conflict_info=conflict_info,
            management_info=management_info,
            financial_info=financial_info,
        )

        # A missing/non-finite pillar is missing evidence, never a neutral score.
        raw_scores = {
            "business_quality": business_score,
            "financial_quality": financial_score,
            "management_governance": governance_score,
            "ipo_structure": structure_score,
            "valuation": valuation_score,
            "growth_industry": growth_score,
            "risk": risk_score,
            "market_sentiment": sentiment_score,
        }
        missing_scores = [
            name for name, value in raw_scores.items()
            if value is None or not isinstance(value, (int, float)) or not math.isfinite(float(value))
        ]
        if missing_scores:
            is_gated = True
            gate_reasons = list(gate_reasons) + [
                "Pillar assessment unavailable due to missing/non-finite evidence: " + ", ".join(missing_scores) + "."
            ]
        safe_scores = {name: float(value) if name not in missing_scores else 0.0
                       for name, value in raw_scores.items()}

        # 2. Weighted Overall Score
        overall_weighted = sum(
            safe_scores[name] * self.weights[name] for name in safe_scores
        )
        overall_score = round(overall_weighted, 1)

        # 3. Multi-Horizon Breakdown
        horizons = MultiHorizonClassifier.classify_horizons(
            business_score=safe_scores["business_quality"],
            financial_score=safe_scores["financial_quality"],
            governance_score=safe_scores["management_governance"],
            valuation_score=safe_scores["valuation"],
            risk_score=safe_scores["risk"],
            gmp_gain_pct=gmp_gain_pct,
            subscription_times=subscription_times,
            is_gated=is_gated,
        )

        verdict = "UNABLE_TO_ASSESS" if is_gated else horizons["verdict"]

        return {
            "is_safety_gated": is_gated,
            "safety_gate_reasons": gate_reasons,
            "overall_score": overall_score if not is_gated else 0.0,
            "verdict": verdict,
            "pillar_scores": raw_scores,
            "weights_used": self.weights,
            "horizons": horizons,
        }
