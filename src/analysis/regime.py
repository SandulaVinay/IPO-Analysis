"""
Market Regime and Macro Sentiment Context Analyzer.
Tracks broader Nifty trend, Mid/Small-cap market heat, and recent IPO listing performance.
Informs short-term expectations without overriding company fundamentals.
"""

from typing import Dict, Any, List, Optional


class MarketRegimeAnalyzer:
    """Evaluates macro secondary market environment."""

    @staticmethod
    def evaluate_market_regime(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        data keys:
            - nifty_50dma_status: ABOVE / BELOW
            - midcap_sentiment: BULLISH / NEUTRAL / BEARISH
            - recent_ipos_avg_listing_gain_pct: float
            - india_vix: float
        """
        d = data or {}
        vix = d.get("india_vix", 14.5)
        gain_avg = d.get("recent_ipos_avg_listing_gain_pct", 22.0)
        nifty_above = d.get("nifty_50dma_status", "ABOVE") == "ABOVE"

        score = 6.0
        if nifty_above:
            score += 1.5
        if gain_avg >= 20.0:
            score += 1.5
        elif gain_avg < 0.0:
            score -= 2.0

        if vix > 22.0:
            score -= 1.5
            regime = "BEARISH_VOLATILE"
        elif score >= 7.5:
            regime = "BULLISH"
        elif score <= 4.5:
            regime = "BEARISH"
        else:
            regime = "NEUTRAL"

        final_score = max(1.0, min(10.0, round(score, 1)))

        return {
            "market_sentiment_score": final_score,
            "regime": regime,
            "india_vix": vix,
            "recent_ipos_avg_listing_gain_pct": gain_avg,
        }
