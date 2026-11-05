"""Evidence-gated risk scoring and quantification."""
from typing import Any, Dict, List

class RiskEngine:
    SEVERITY_WEIGHTS = {"CRITICAL": 3.0, "HIGH": 2.0, "MEDIUM": 1.0, "LOW": 0.5}
    VALID_PROBABILITY_IMPACT = {"LOW", "MEDIUM", "HIGH"}

    @classmethod
    def evaluate_risks(cls, risks: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not risks:
            reason = "No verified risk register was supplied; absence of records is not evidence of low risk."
            return {"assessment_status": "UNABLE_TO_ASSESS", "risk_score": None, "total_risk_count": 0,
                    "high_severity_count": 0, "top_risks": [], "limitations": [reason]}
        required = ("risk_title", "severity", "probability", "impact", "evidence_citation")
        for index, risk in enumerate(risks):
            if not isinstance(risk, dict):
                reason = f"Risk item {index + 1} must be an object with explicit evidence fields."
                return {"assessment_status": "UNABLE_TO_ASSESS", "risk_score": None, "total_risk_count": len(risks),
                        "high_severity_count": 0, "top_risks": [], "limitations": [reason]}
            missing = [key for key in required if not risk.get(key)]
            severity, probability, impact = (str(risk.get(k, "")).upper() for k in ("severity", "probability", "impact"))
            if missing or severity not in cls.SEVERITY_WEIGHTS or probability not in cls.VALID_PROBABILITY_IMPACT or impact not in cls.VALID_PROBABILITY_IMPACT:
                reason = f"Risk item {index + 1} is incomplete or has unsupported classifications; missing: {', '.join(missing) or 'valid severity/probability/impact'}."
                return {"assessment_status": "UNABLE_TO_ASSESS", "risk_score": None, "total_risk_count": len(risks),
                        "high_severity_count": 0, "top_risks": [], "limitations": [reason]}
        penalty = sum(cls.SEVERITY_WEIGHTS[str(r["severity"]).upper()] for r in risks)
        high = sum(str(r["severity"]).upper() in {"CRITICAL", "HIGH"} for r in risks)
        structured = [{"title": r["risk_title"], "category": r.get("risk_category", "BUSINESS"),
                       "probability": str(r["probability"]).upper(), "impact": str(r["impact"]).upper(),
                       "severity": str(r["severity"]).upper(), "citation": r["evidence_citation"]} for r in risks]
        return {"assessment_status": "ASSESSED", "risk_score": max(1.0, min(10.0, round(9.0 - penalty * 0.7, 1))),
                "total_risk_count": len(risks), "high_severity_count": high, "top_risks": structured[:5], "limitations": []}
