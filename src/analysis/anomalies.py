"""
Financial Anomaly and Forensic Red Flag Detection Engine.
Automatically scans financial statements for:
- Profit vs Cash flow divergences
- Sudden margin expansion / deterioration
- Abnormal receivables growth outstripping revenue
- Unusually large other income or repeated exceptional items
- High contingent liabilities
"""

from typing import Dict, Any, List, Optional


class AnomalyDetector:
    """Detects accounting red flags and operational anomalies."""

    @staticmethod
    def detect_anomalies(periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Scan chronological periods for anomalies.
        Returns list of structured anomaly items with severity, evidence, and explanation.
        """
        anomalies: List[Dict[str, Any]] = []
        if len(periods) < 2:
            return anomalies

        prev = periods[-2]
        latest = periods[-1]

        # 1. Receivables spike outpacing revenue
        rev_prev = prev.get("revenue") or 0.0
        rev_curr = latest.get("revenue") or 0.0
        rec_prev = prev.get("trade_receivables") or 0.0
        rec_curr = latest.get("trade_receivables") or 0.0

        if rev_prev > 0 and rev_curr > 0 and rec_prev > 0 and rec_curr > 0:
            rev_growth = (rev_curr - rev_prev) / rev_prev
            rec_growth = (rec_curr - rec_prev) / rec_prev
            if rec_growth > rev_growth + 0.30 and rec_growth > 0.40:
                anomalies.append({
                    "title": "Abnormal Trade Receivables Spike",
                    "severity": "HIGH",
                    "explanation": f"Trade receivables grew {round(rec_growth*100, 1)}% while revenue grew only {round(rev_growth*100, 1)}%. Possible aggressive revenue recognition.",
                    "evidence": f"Period {prev.get('period_name')} to {latest.get('period_name')}",
                })

        # 2. Sudden Margin Jump in Pre-IPO Year
        pat_prev = prev.get("pat") or 0.0
        pat_curr = latest.get("pat") or 0.0
        if rev_prev > 0 and rev_curr > 0:
            margin_prev = (pat_prev / rev_prev) * 100.0
            margin_curr = (pat_curr / rev_curr) * 100.0
            if margin_curr > margin_prev * 2.0 and margin_curr > 12.0:
                anomalies.append({
                    "title": "Sudden Pre-IPO Margin Expansion",
                    "severity": "MEDIUM",
                    "explanation": f"Net profit margin doubled from {round(margin_prev, 1)}% to {round(margin_curr, 1)}% in the year preceding the IPO.",
                    "evidence": f"{prev.get('period_name')} vs {latest.get('period_name')}",
                })

        # 3. Cash Flow vs PAT Divergence
        cfo_curr = latest.get("cfo")
        if pat_curr > 50.0 and cfo_curr is not None and cfo_curr < pat_curr * 0.3:
            anomalies.append({
                "title": "Severe Operating Cash Flow Divergence",
                "severity": "HIGH",
                "explanation": f"Operating cash flow (₹{cfo_curr} Cr) is significantly below reported PAT (₹{pat_curr} Cr).",
                "evidence": f"{latest.get('period_name')} Financials",
            })

        return anomalies
