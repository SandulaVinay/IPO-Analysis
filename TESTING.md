# Testing Strategy & Test Scenarios (`TESTING.md`)

This document outlines the testing methodology, unit test suites, integration tests, and the 11 realistic market scenarios.

---

## 1. Test Execution

Run the complete test suite:
```powershell
.venv\Scripts\pytest.exe -v
```

---

## 2. Test Architecture

- `tests/unit/test_math.py`: Validates deterministic CAGR math (and negative/zero edge cases), margins, post-IPO shares, market cap, enterprise value, P/E, EV/EBITDA, dilution %, and cash conversion.
- `tests/unit/test_scoring.py`: Validates composite pillar weighting, multi-horizon classification, and safety gate triggers.
- `tests/unit/test_safety_gates.py`: Verifies hard assessment safety gates (missing data, conflicting dates, auditor issues).
- `tests/unit/test_timezone.py`: Validates IST datetime math, NSE trading holidays, and T-2 target calculation.
- `tests/unit/test_conflict.py`: Validates Tier-1 precedence rules and multi-source conflict resolution.
- `tests/integration/test_pipeline.py`: Validates complete database persistence, document hashing, version diffing, report generation, and post-listing feedback loop.

---

## 3. The 11 Realistic Scenario Fixtures (`tests/scenarios/test_all_scenarios.py`)

1. **Strong IPO**: High growth, net cash positive, reasonable valuation → Verdict: `ATTRACTIVE`.
2. **Expensive IPO**: Excessive P/E multiple vs peers → Penalized valuation score.
3. **OFS-Heavy IPO**: $>75\%$ OFS exit → Penalized structure score.
4. **Loss-Making Tech IPO**: Negative PAT & cash burn → Financial score penalizes cash burn.
5. **Financial Services (Bank/NBFC) IPO**: Uses appropriate banking multiples (P/B, ROE).
6. **Manufacturing IPO**: Evaluates EV/EBITDA and strong operating cash flow.
7. **Technology SaaS IPO**: High recurring revenue and strong moats.
8. **Conflicting Sources IPO**: Resolves via Tier-1 precedence.
9. **Missing Financial Data IPO**: Trips hard safety gate → Verdict: `⚪ UNABLE TO ASSESS`.
10. **Changed Price Band IPO**: `DocumentDiffEngine` detects change and triggers re-analysis.
11. **Changed Opening Date IPO**: `DocumentDiffEngine` identifies date shift.
