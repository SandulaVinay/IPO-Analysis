# Scoring Methodology & Assessment Gates (`SCORING_MODEL.md`)

This document outlines the multi-pillar weighting formula, horizon classification thresholds, and hard assessment safety gates.

---

## 1. Multi-Pillar Scoring Weights

The composite IPO score (0.0 to 10.0) is calculated via deterministic weighted aggregation:

$$\text{Overall Score} = \sum (S_i \times W_i)$$

| Pillar | Default Weight | Key Inputs Analyzed |
| :--- | :--- | :--- |
| **Business Quality** | **20%** | Industry moat, customer concentration, recurring revenue share, scalability |
| **Financial Quality** | **20%** | 3-year revenue/PAT CAGRs, EBITDA margins, Cash Conversion (CFO/PAT), Net Debt/Equity |
| **Valuation & Multiples** | **20%** | Post-IPO P/E, EV/EBITDA, P/B vs Peer Median, Dilution % |
| **Management & Governance** | **10%** | Promoter post-holding, pledge %, RPT %, auditor qualifications |
| **IPO Issue Structure** | **10%** | Fresh issue % vs OFS %, debt repayment vs capex growth deployment |
| **Growth & Industry Moat** | **10%** | Addressable TAM growth, market share momentum |
| **Risk Factors** | **5%** | Quantified severity of litigation, regulatory, and operational risks |
| **Market Sentiment** | **5%** | Secondary market regime, Nifty trend, recent IPO listing performance |
| **Total** | **100%** | **Composite Scale: 0.0 – 10.0** |

*All weights are fully configurable via `.env` or `Pydantic Settings`.*

---

## 2. Hard Assessment Safety Gates

Before calculating a positive verdict, the system evaluates three safety gates:
1. **Missing Data Gate**: Triggered if $>2$ critical financial statement or timeline fields are absent.
2. **Conflict Gate**: Triggered if two Tier 1 sources (e.g. NSE vs BSE) contradict on opening dates or price bands.
3. **Forensic Gate**: Triggered if material adverse auditor qualifications or active criminal litigation are detected.

**Safety Gate Action**: The recommendation is immediately set to `⚪ UNABLE TO ASSESS` and overall score is suppressed to `0.0` with explicit explanatory reasons.
