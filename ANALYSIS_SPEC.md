# Forensic IPO Analysis Specification (`ANALYSIS_SPEC.md`)

This document details the exact methodology, analytical formulas, anomaly detection logic, and evidence provenance rules implemented in the system.

---

## 1. Core Philosophy

1. **Deterministic Primacy**: All financial, mathematical, and valuation calculations are executed programmatically in Python (`src/calculations/math.py`). LLMs are never used for arithmetic or numerical ratios.
2. **Fact, Calculation, and Opinion Separation**:
   - **FACT**: Directly extracted from official filings with document ID, version, and page citation (e.g. FY25 Revenue = ₹1,040 Cr, Page 214).
   - **CALCULATION**: Programmatically computed derived values (e.g. Revenue CAGR = 22.8%).
   - **OPINION**: Structured analytical interpretation (e.g. valuation multiple context, moat sustainability).
3. **Hard Safety Assessment Gates**: If critical financial numbers or timeline dates are missing or conflicting, the system outputs `⚪ UNABLE TO ASSESS` instead of guessing.

---

## 2. Mathematical Formulas & Financial Metrics

| Metric | Formula | Edge Case Handling |
| :--- | :--- | :--- |
| **CAGR** | $(V_{end} / V_{start})^{1/n} - 1$ | Returns `None` if $V_{start} \le 0$ or $V_{end} < 0$ or $n \le 0$. |
| **EBITDA Margin** | $(\text{EBITDA} / \text{Revenue}) \times 100$ | Returns `None` if $\text{Revenue} \le 0$. |
| **PAT Margin** | $(\text{PAT} / \text{Revenue}) \times 100$ | Returns `None` if $\text{Revenue} \le 0$. |
| **Post-IPO Shares** | $\text{Pre-IPO Shares} + \text{Fresh Shares}$ | Exact float precision in Crores. |
| **Post-IPO Market Cap** | $\text{Issue Price} \times \text{Post-IPO Shares}$ | Computed at upper price band. |
| **Enterprise Value (EV)** | $\text{Market Cap} + \text{Total Debt} - \text{Cash}$ | Cash includes cash equivalents. |
| **P/E Ratio** | $\text{Issue Price} / \text{Post-IPO Diluted EPS}$ | Returns `None` if $\text{EPS} \le 0$ (loss-making). |
| **EV / EBITDA** | $\text{Enterprise Value} / \text{EBITDA}$ | Returns `None` if $\text{EBITDA} \le 0$. |
| **Cash Conversion** | $\text{CFO} / \text{PAT}$ | Flagged if $< 0.5\times$ or negative. |
| **Estimated Listing Gain** | $(\text{GMP} / \text{Issue Price}) \times 100$ | Labeled as Unofficial Sentiment Indicator. |
| **Dilution %** | $(\text{Fresh Shares} / \text{Post-IPO Shares}) \times 100$ | Computed against total post-issue equity. |
| **Peer Dis/Premium** | $(M_{ipo} - M_{peer\_median}) / M_{peer\_median} \times 100$ | Evaluates relative valuation premium (+%) or discount (-%). |

---

## 3. Financial Anomaly & Red Flag Detection

The system automatically executes the following checks:
1. **Trade Receivables Spike**: Detects if receivables growth exceeds revenue growth by $>30\%$, indicating aggressive revenue recognition.
2. **Pre-IPO Margin Expansion**: Flags when PAT margin in the immediate pre-IPO financial year doubles relative to preceding periods.
3. **CFO vs PAT Divergence**: Flags when operating cash flow is less than $30\%$ of reported PAT or negative while reported profit is positive.
4. **Heavy OFS Ratio**: Flags when $>75\%$ of the total IPO issue size is Offer for Sale (OFS), signifying promoter/investor exits rather than company balance-sheet growth.
5. **Auditor Qualifications & Litigation**: Extracts and penalizes adverse remarks or frequent auditor resignations.

---

## 4. Multi-Horizon Rating Framework

The system computes four distinct horizon scores (0.0 to 10.0):
1. **Company Quality**: Intrinsic fundamental health (Business Moat 40%, Financial Quality 40%, Governance 20%).
2. **IPO Attractiveness**: Valuation-adjusted offering attractiveness (Company Quality 50%, Valuation Discount 35%, Risk 15%).
3. **Listing Opportunity**: Short-term listing gain potential based on valuation discount, GMP sentiment, and subscription demand.
4. **Long-Term Opportunity**: Multi-year compounding potential based on company moat, governance integrity, and capital reinvestment.
