# GPT Handoff — IPO-Analysis

> **Purpose:** This file is an operational handoff for a future GPT/AI coding agent. Read this first, then inspect the live repository and CI before changing anything. Treat repository state and current GitHub checks as authoritative; this document is a snapshot and can become stale.
>
> **Last updated:** 2026-10-31  
> **Repository:** https://github.com/SandulaVinay/IPO-Analysis  
> **Default branch:** `main`  
> **Estimated overall project completion: 65%** — a practical engineering estimate, not a measured KPI. Core workflow and safety foundations exist, but verified financial extraction/reconciliation and production-grade IPO assessment are not complete.

---

## 1. START HERE — Current objective

**We are building a reliable IPO-analysis and monitoring system that gathers company/IPO evidence, analyzes financial quality and risk, and sends useful alerts without fabricating data or issuing recommendations from incomplete evidence.**

### Immediate next task

Implement a **conservative, test-driven financial-statement extraction and verification pipeline** for financial results and prospectus PDFs. The current monitor can extract bounded PDF text excerpts for context, but arbitrary PDF statement tables are not yet converted into verified financial metrics.

Do not jump straight to a scoring formula. First trace the current data flow, schemas, verification engine, scoring engine, and tests. Build extraction so it preserves evidence and provenance, and keep ambiguous figures unverified.

### Definition of done for the next milestone

- [ ] Extract candidate financial rows/values from PDFs with source URL, page number, row label, raw text, period label, unit text, and statement basis where identifiable.
- [ ] Normalize only when period, unit, and statement basis are explicit and unambiguous; retain raw source values and normalization metadata.
- [ ] Distinguish standalone from consolidated statements; never combine or compare unlike bases.
- [ ] Handle Indian numbering and common units (₹, ₹ lakh, ₹ crore, thousands/millions) conservatively; never guess an absent unit.
- [ ] Reconcile key values across available official source evidence and periods. Record discrepancies rather than silently choosing one value.
- [ ] Mark extracted-but-unreconciled values as candidate/unverified; do not pass them to scoring as verified facts.
- [ ] Return `UNABLE_TO_ASSESS` when critical evidence is absent, ambiguous, conflicting, or unverified.
- [ ] Add synthetic PDF/table fixtures and regression tests for ambiguous periods, units, statement basis, negative values, missing fields, and conflicting figures.
- [ ] Run relevant unit tests and full CI; use a branch and PR. Merge only after checks pass.

---

## 2. Project status and progress

| Area | Status | Notes |
|---|---|---|
| GitHub Actions / automated test workflow | In place | Always inspect the latest check run; don't infer current status from an old run. |
| Results monitoring and event/notification orchestration | In place, iteratively improved | Preserve idempotency and the event ledger. Avoid duplicate alerts. |
| Email-first notifications | Implemented | Email is preferred; WhatsApp is deferred and must not be enabled implicitly. |
| Bounded PDF text extraction | Implemented | `src/results/monitor.py` uses bounded extraction; this is not equivalent to structured financial-table extraction. |
| PDF report rendering / source URLs | Improved | Long source URLs are handled in PDF reports. |
| Verification and fail-closed assessment gates | Implemented and strengthened | Missing critical fields and explicitly unverified financial inputs now gate assessment. Continue reviewing caller integration. |
| Financial trend scoring | Partial | `src/analysis/financials.py` no longer gives neutral-looking numeric scores when required history is absent. Inputs still need reliable provenance/verification. |
| PDF financial table extraction | Not complete | Primary next engineering task. |
| Period/unit/basis reconciliation | Not complete | Required before extracted values can be treated as verified. |
| Prospectus-wide verified financial extraction | Not complete | Do not claim this is implemented. |
| Verified IPO recommendations / production decisioning | Not complete | Keep gated/fail-closed; no unsupported buy/sell recommendation. |
| End-to-end production readiness | Not complete | More integration, evidence validation, and operational tests required. |

**Overall progress: 65/100.** This reflects the existing monitoring, notifications, reporting, and safety foundation, while accounting for the still-substantial core financial extraction and verification work. Revise this estimate only when deliverables and tests justify it.

---

## 3. Latest work completed

### PR #25 — merged

**Title:** Fail closed on missing or unverified financial evidence  
**PR:** https://github.com/SandulaVinay/IPO-Analysis/pull/25  
**Merge commit:** `68772d09e9b485218b96f47b41da47f9ae0f9911`  
**CI at PR head:** https://github.com/SandulaVinay/IPO-Analysis/actions/runs/41184737247 — test job passed.

Changes:
- `src/scoring/safety_gates.py`: any field listed in `missing_critical_fields` now gates assessment; explicitly non-verified financial evidence and an explicit unverified-critical-financials flag also gate.
- `src/analysis/financials.py`: no neutral numeric scores if history is empty or revenue/PAT is missing for a period; earnings-quality score is omitted when latest CFO is unavailable, with an explicit limitation.
- `tests/unit/test_financial_evidence_safety.py`: regression tests for missing critical fields, unverified evidence, incomplete periods, missing CFO, and complete financial periods.

**Important integration follow-up:** verify that the actual caller passes the correct `financial_info` verification fields to `SafetyGateEvaluator.evaluate_gates`, and that downstream consumers respect `assessment_status`, `None` scores, and limitations. A unit test of the gate alone does not prove every application path is gated.

### Earlier merged work (context)

The following changes were reported as merged in the prior handoff:
- Timestamp placeholder fallback and regression coverage in results monitoring.
- End-to-end integration test.
- Scheduler email alert configuration fix; push-triggered scheduler runs do not send actual emails.
- PDF report source URL wrapping.
- Bounded PDF text extraction using `pypdf` in `src/results/monitor.py`, with page-labelled excerpts and verification cautions.
- Email-first provider order; WhatsApp deferred.
- README and architecture documentation corrected to match email-first/deferred-WhatsApp behaviour.
- Dependency updates: `aiosqlite >=0.22.1` and SQLAlchemy `>=2.1.6`.

Verify current `main` and commit history before relying on these historical notes.

---

## 4. Key code areas to inspect first

- `src/results/monitor.py` — results monitoring, bounded PDF download/text extraction, report text construction.
- `src/analysis/financials.py` — financial quality / earnings quality trend analysis.
- `src/analysis/valuation.py` — valuation assessment and fail-closed status.
- `src/analysis/forensics.py` — financial/governance forensic flags.
- `src/scoring/safety_gates.py` — hard assessment safety gates.
- `src/scoring/engine.py` — scoring orchestration; trace how analysis and safety gates are invoked.
- `src/analysis/` — related domain analyzers (peer, management, risk, structure, etc.).
- `tests/unit/test_financial_evidence_safety.py` — latest safety regression tests.
- `tests/unit/test_results_monitor.py` — results/PDF monitor tests.
- `tests/unit/test_prospectus_extractor.py`, `tests/unit/test_document_extractor.py`, `tests/unit/test_verification_engine.py`, `tests/unit/test_scoring.py` — existing extraction/verification/scoring coverage.
- `tests/unit/test_automation_v2_safety.py` — safety/notification tests.
- `docs/ARCHITECTURE_V2.md` and `README.md` — documented design and operating behaviour.
- `requirements.txt` — dependencies; `pypdf`, `pdfplumber`, and `reportlab` were already present in the prior review.

Before implementation, search the repository for all callers of `FinancialAnalyzer.analyze_financials`, `SafetyGateEvaluator.evaluate_gates`, financial metric schemas, and any serialization/reporting code that assumes score fields are always numeric.

---

## 5. Financial extraction design principles

1. **Preserve evidence:** store the source URL/document identity, page, original row label, raw cell strings, parsed candidate value, raw unit, parsed unit, period, basis, extraction method, and verification status.
2. **Do not hallucinate:** no guessed units, periods, consolidated/standalone basis, missing figures, or reconciliation outcomes.
3. **Candidate is not verified:** parsing a number from a PDF only creates a candidate. Verification requires sufficient context and reconciliation.
4. **Normalize transparently:** retain original strings and record each unit conversion. Never compare values in different units without explicit conversion.
5. **Periods matter:** distinguish quarter, half-year, full financial year, and trailing twelve months. Do not annualize silently.
6. **Statement basis matters:** consolidated and standalone figures are not interchangeable. Treat unclear basis as unresolved.
7. **Conflicts must be visible:** retain both source values, source quality, and a conflict reason; do not silently select the convenient figure.
8. **Scoring must fail closed:** critical missing/unverified/conflicting data means `UNABLE_TO_ASSESS` or an appropriately limited status. A missing value must not be converted to zero or a neutral score.
9. **Official sources first:** prefer exchange filings and official company/prospectus documents; retain the exact source link and evidence.
10. **Test the ugly cases:** scanned/image-only PDFs, multi-page tables, repeated headers, negative values in parentheses, commas, dashes, multiple units, comparative columns, and tables with both standalone and consolidated sections.

Avoid implementing a broad regex parser and calling it production-ready. Use PDF table extraction where useful, but treat layout-dependent parsing as fallible and preserve the original evidence.

---

## 6. Watchlist and alerting context

Watchlist items recorded in prior work:
1. Reliance Industries Limited
2. Tata Consultancy Services Limited (TCS)
3. RNIT AI Solutions Limited — BSE scrip 517286
4. Clean Science and Technology Limited
5. Godavari Biorefineries Limited

Prior official RNIT filing example:
`https://www.bseindia.com/xml-data/corpfiling/AttachLive/49b9896d-d588-4ccc-b828-48f17dc7e48b.pdf`  
Described as unaudited financial results for the quarter and half year ended September 30, 2026, together with the limited review report.

Alerting rules:
- Email-first; WhatsApp remains deferred/disabled unless explicitly requested and separately configured.
- Do not change recipients, SMTP secrets, or other credentials.
- Do not clear the event ledger or generate duplicate alerts during testing.
- A successful workflow run does not prove an email was delivered.
- Push-triggered scheduler runs are configured to disable real email sending; test with the intended safe workflow and report the distinction clearly.
- Never print, commit, or expose secrets or `.env` contents.

---

## 7. Recommended immediate execution plan

### Step 1 — establish live state
- Fetch current `main` SHA, open PRs, latest workflow run/check status, and tree.
- Confirm PR #25 is merged and verify the merge commit on `main`.
- Run/read tests around the new safety behaviour and inspect every call site.

### Step 2 — trace current data contracts
- Map monitor → document/PDF extractor → candidate metrics → verification → analysis → scoring/safety gate → report/notification.
- Document current metric field names and types before adding anything.
- Find where extraction provenance and verification status are represented, or identify the gap.

### Step 3 — implement a small conservative vertical slice
- Start with one well-defined official financial results PDF table type, not arbitrary prospectuses.
- Extract raw candidate rows and attach provenance.
- Add explicit unit/period/basis parsing only when unambiguous.
- Mark unsupported/ambiguous layouts as unverified and preserve the excerpt for review.

### Step 4 — tests first, then expand
- Create synthetic PDF fixtures with `reportlab` and table fixtures supported by the chosen parser.
- Test normal, ambiguous, conflicting, and malformed inputs.
- Ensure no candidate data can bypass verification and safety gates.
- Expand supported layouts only after repeatable tests.

### Step 5 — branch, PR, CI, merge
- Create a feature branch from latest `main`.
- Make small commits with focused tests.
- Open a PR describing what is and is not supported.
- Inspect CI and logs; fix failures rather than bypassing checks.
- Merge only when the relevant tests pass.
- Update this handoff with the new commit, tests, known limitations, and progress estimate.

---

## 8. Working rules for the next GPT

- Continue the implementation; do not merely give advice if repository tools permit editing and testing.
- Read relevant source files and callers before changing contracts.
- Do not assume earlier chat messages are current; inspect GitHub.
- Do not claim PDF text extraction is financial metric extraction.
- Do not claim a workflow run means alert delivery.
- Do not enable live emails/WhatsApp, alter recipients/secrets, clear ledgers, or send test alerts without explicit authorization.
- Do not issue or enable production investment recommendations from unverified inputs.
- Prefer small, reviewable PRs and regression tests.
- If tests fail, inspect logs and fix root causes. Never merge while required checks are failing or pending.
- Keep the README, architecture docs, and this handoff aligned with actual behaviour.
- Update the **65%** estimate only when concrete milestones change.

## 9. Current open work

- [ ] Verify integration of PR #25 safety changes across all callers and downstream report/scoring paths.
- [ ] Build provenance-aware financial PDF table extraction.
- [ ] Implement period, unit, and standalone/consolidated basis identification.
- [ ] Reconcile financial candidates against official sources and flag conflicts.
- [ ] Connect only verified values to financial analysis.
- [ ] Validate prospectus extraction and IPO scoring end to end.
- [ ] Add end-to-end tests that prove ambiguous or unverified inputs cannot yield a positive assessment.
- [ ] Review deployment/operations and notification behaviour before any production recommendation rollout.

**Resume from Section 1 and execute Step 1 first.**
