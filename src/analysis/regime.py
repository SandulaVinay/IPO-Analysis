"""Evidence-gated market regime and macro sentiment analyzer."""
from typing import Any, Dict, Optional

class MarketRegimeAnalyzer:
    REQUIRED_FIELDS = ("nifty_50dma_status", "midcap_sentiment", "recent_ipos_avg_listing_gain_pct", "india_vix")

    @staticmethod
    def evaluate_market_regime(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        d = data or {}
        missing = [key for key in MarketRegimeAnalyzer.REQUIRED_FIELDS if key not in d or d[key] is None]
        if missing:
            reason = "Missing current market-regime observations: " + ", ".join(missing)
            return {"assessment_status": "UNABLE_TO_ASSESS", "market_sentiment_score": None,
                    "regime": "UNKNOWN", "insights": [reason], "limitations": [reason]}
        status, midcap = str(d["nifty_50dma_status"]).upper(), str(d["midcap_sentiment"]).upper()
        if status not in {"ABOVE", "BELOW"} or midcap not in {"BULLISH", "NEUTRAL", "BEARISH"}:
            reason = "Market trend fields contain unsupported values."
            return {"assessment_status": "UNABLE_TO_ASSESS", "market_sentiment_score": None,
                    "regime": "UNKNOWN", "insights": [reason], "limitations": [reason]}
        vix, gain = float(d["india_vix"]), float(d["recent_ipos_avg_listing_gain_pct"])
        if not math.isfinite(vix) or not math.isfinite(gain) or vix < 0:
            reason = "India VIX cannot be negative."
            return {"assessment_status": "UNABLE_TO_ASSESS", "market_sentiment_score": None,
                    "regime": "UNKNOWN", "insights": [reason], "limitations": [reason]}
        score = 6.0 + (1.0 if status == "ABOVE" else -1.0)
        score += 0.5 if midcap == "BULLISH" else (-0.5 if midcap == "BEARISH" else 0.0)
        score += 1.0 if gain >= 20 else (-1.5 if gain < 0 else 0.0)
        if vix > 22: score -= 1.5
        regime = "BEARISH_VOLATILE" if vix > 22 else ("BULLISH" if score >= 7.5 else ("BEARISH" if score <= 4.5 else "NEUTRAL"))
        return {"assessment_status": "ASSESSED", "market_sentiment_score": max(1.0, min(10.0, round(score, 1))),
                "regime": regime, "india_vix": vix, "recent_ipos_avg_listing_gain_pct": gain, "limitations": []}
