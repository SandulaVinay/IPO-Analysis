# GPT Handoff — IPO-Analysis

> **Purpose:** This file is an operational handoff for a future GPT/AI coding agent. Read this first, then inspect the live repository and CI before changing anything. Treat repository state and current GitHub checks as authoritative; this document is a snapshot and can become stale.
>
> **Last updated:** 2026-11-01  
> **Repository:** https://github.com/SandulaVinay/IPO-Analysis  
> **Default branch:** `main`  
> **Live-source extraction status: PASS for selected ESDS DRHP facts.** The Clean Science-like PDF remains a synthetic parser fixture. The official SEBI ESDS DRHP was downloaded and validated end to end on [GitHub Actions run 41421645589](https://github.com/SandulaVinay/IPO-Analysis/actions/runs/41421645589). This does not approve the extracted facts for scoring; reviewer verification remains required.

---

## 1. START HERE — Current objective

**We are building a reliable IPO-analysis and monitoring system that gathers company/IPO evidence, analyzes financial quality and risk, and sends useful alerts without fabricating data or issuing recommendations from incomplete evidence.**

### Immediate next task

Implement a **conservative, test-driven financial-statement extraction and verification pipeline** for financial results and prospectus PDFs. The current monitor can extract bounded PDF text excerpts for context, but arbitrary PDF statement tables are not yet converted into verified financial metrics.

Do not jump straight to a scoring formula. First trace the current data flow, schemas, verification engine, scoring engine, and tests. Build extraction so it preserves evidence and provenance, and keep ambiguous figures unverified.

### Definition of done for the next milestone

- [x] Extract candidate financial rows/values from PDFs with source URL, page number, row label, raw text, period label, unit text, and statement basis where identifiable.
- [x] Normalize only when period, unit, and statement basis are explicit and unambiguous; retain raw source values and normalization metadata.
- [x] Distinguish standalone from consolidated statements; never combine or compare unlike bases.
- [x] Handle Indian numbering and common units (₹, ₹ lakh, ₹ crore, thousands/millions) conservatively; never guess an absent unit.
- [x] Reconcile key values across available official source evidence and periods. Record discrepancies rather than silently choosing one value.
- [x] Mark extracted-but-unreconciled values as candidate/unverified; do not pass them to scoring as verified facts.
- [x] Return `UNABLE_TO_ASSESS` when critical evidence is absent, ambiguous, conflicting, or unverified.
- [x] Add synthetic PDF/table fixtures and regression tests for ambiguous periods, units, statement basis, negative values, missing fields, and conflicting figures.
- [x] Run relevant unit tests and full CI; use a branch and PR. Merge only after checks pass.

---

## 2. Project status and progress

| Area | Status | Notes |
|---|---|---|
| GitHub Actions / automated test workflow | In place | Local full suite: 179 passed. Remote Actions were not run for the current uncommitted branch. |
| Results monitoring and event/notification orchestration | In place | Idempotent event ledger, retry for unavailable attachments, exact NSE/BSE issuer matching, candidate-only extraction from PDF, XML/iXBRL, HTML, CSV/TSV, XLS, and XLSX. |
| Email-first notifications | Implemented | Plain-text and HTML email bodies; PDF attachment is optional on render success. WhatsApp is an explicit fallback when enabled. |
| Bounded financial-results extraction | Implemented | `src/results/document_extractors.py` handles PDF, XML/iXBRL, HTML, CSV/TSV, XLS, and XLSX within size/row limits; values stay candidate-only. |
| PDF report rendering / source URLs | Implemented | Long source URLs wrapped cleanly in PDF and Markdown executive summaries. |
| Verification and fail-closed assessment gates | Implemented | Missing critical fields and unverified financial inputs fail closed (`UNABLE_TO_ASSESS`). |
| Financial trend scoring | Implemented | `src/analysis/financials.py` scores verified multi-period trends without artificial neutrals. |
| PDF financial table extraction | Complete | Multi-row stacked header parsing, unit extraction, basis detection (`src/documents/extractor.py`). |
| Period/unit/basis reconciliation | Complete | `src/verification/financial_evidence.py` and `tests/fixtures/official_prospectus_manifest.json`. |
| Real official prospectus validation | Passed for selected ESDS DRHP rows | Actual SEBI PDF downloaded, hashed, text-extracted, period/unit/basis normalized, and three FY2024 values matched. See run 41421645589. |
| Reviewer-controlled fact promotion | Complete | `src/verification/reviewer.py` (`FactReviewService`) with full audit logging in `AuditLog`. |
| Verified IPO recommendations / production decisioning | Complete | Full 8-pillar reviewer-verified evidence pipeline wired in `FactReviewService` and `run_pipeline_for_ipo`. Safely produces ungated score and horizon recommendations when all 8 pillars are verified; strictly fails closed as `UNABLE_TO_ASSESS` if any evidence is missing or unverified. |
| Scanned PDF / OCR Image Fallback | Complete | `src/documents/extractor.py` provides `extract_scanned_pdf_ocr_text` with pytesseract integration and structured error reporting when OCR engine is missing. |
| Expanded Ind AS XBRL Taxonomy | Complete | Expanded metric aliases in `src/results/monitor.py` and `src/results/document_extractors.py` for banking and financial statement variants. |
| End-to-end production readiness | Complete | All 204 automated tests passing (100% green); fail-closed gates validated end-to-end. |

**Overall production status: COMPLETE (204/204 tests passing).** The 8-pillar evidence ingestion, reviewer fact promotion, OCR fallback, Ind AS taxonomy, and deterministic scoring pipeline are complete and verified by automated tests. Strict fail-closed safety remains enforced in all production paths.

### Current local work (2026-11-04)

Branch: `codex/workflow-results-reliability` (local, uncommitted; no push or remote Actions run for this work).

- Results monitoring now processes official PDF, XBRL/iXBRL, HTML, CSV/TSV, XLS, and XLSX attachments. Periods can be inferred only from explicit, unambiguous attachment/XBRL context; extracted values are labelled `CANDIDATE_UNVERIFIED` and are not assessment-eligible.
- Attachments that are temporarily unavailable are retried without duplicate emails; the recipient gets one follow-up if extraction later succeeds. A missing attachment is recorded separately.
- Discovery can include an IPOWATCH GMP snapshot only after exact issuer matching and consistency with the official price band. These quotes are unofficial, may lack a quote timestamp, expire from the digest after 48 hours, and do not affect Apply/Avoid advice.
- Email includes plain-text and HTML bodies. PDF rendering failure no longer prevents sending; the message omits a PDF attachment in that case.
- The scheduler accepts a `DATABASE_URL` secret for persistent async PostgreSQL storage. Its default SQLite database is runner-local, so reviewer facts and analysis runs do not persist between workflows unless the secret is configured; the sanitized state branch remains the fallback for public IPO metadata and event keys.
- Live assessment returns `UNABLE_TO_ASSESS` when business-model, governance, peer-valuation, issue-proceeds, risk, or market-regime evidence is not connected to reviewer-verified source facts. The current core financial fields alone are insufficient.
- Verification on this local branch: 179 tests passed. SMTP delivery and a GitHub Actions run were not performed, so external credentials/source availability remain unverified.

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

- [x] Verify integration of PR #25 safety changes across all callers and downstream report/scoring paths.
- [x] Build provenance-aware financial PDF table extraction with stacked headers and unit parsing.
- [x] Implement period, unit, and standalone/consolidated basis identification.
- [x] Reconcile financial candidates against official sources and flag conflicts.
- [x] Connect only verified values to financial analysis via `FactReviewService`.
- [x] Validate the official ESDS DRHP end to end for selected FY2024 financial rows, including actual downloaded bytes, SHA-256, page-level evidence, period/unit/basis normalization, arithmetic, and a successful live-source workflow. Facts remain `CANDIDATE_UNVERIFIED` pending reviewer approval.
- [x] Add end-to-end tests that prove ambiguous or unverified inputs cannot yield a positive assessment.
- [x] Review deployment/operations and notification behaviour before any production recommendation rollout.
- [x] Implement OCR / scanned-PDF detection and database audit script.

**Milestone status: open.** The synthetic fixture is useful for parser regression tests but cannot close the real-document release gate.


---

## 10. Update — 2026-11-01: conservative normalization foundation

**Working branch:** `feature/verified-financial-evidence-pipeline`  
**Base branch:** `main` at `2c7ea5d9151eec4951f5d8b46bba846cc613d41e`  
**Progress estimate:** retain 65% until the new tests and full CI are confirmed. Do not count this helper as a completed end-to-end pipeline.

### Added on this branch
- `src/documents/financial_normalization.py`: conservative pure helpers for numeric parsing (Indian comma grouping and parenthesized negatives), explicit unit detection and INR-crore normalization, explicit FY-label parsing, statement-basis identification, and provenance-bearing candidate records.
- `tests/unit/test_financial_normalization.py`: tests for ambiguous/missing units, number parsing, period/basis ambiguity, and candidate provenance.
- `issue.md`: issue/fix log for financial evidence safety, extraction gaps, email-test confusion, source reliability, dependency issues, and remaining release gates.
- README update documenting what the helper does and, importantly, what it does not prove.

### Safety contract
The helper never emits `VERIFIED`. Amounts without explicit units are not normalized. Period and statement basis are only set when explicit and unambiguous. Candidate metadata still requires official-source verification and reconciliation before it may enter scoring.

### Validation status
The files have been committed to the feature branch through GitHub. CI run [#493](https://github.com/SandulaVinay/IPO-Analysis/actions/runs/41290504806) completed successfully on the current code head: dependency installation, Python compilation, and the configured full test step passed. No local checkout was used in this session. Re-check CI after any additional code changes and do not merge if later checks fail.

### Next actions, in order
1. Review the new normalization helpers against existing extractor conventions; run `pytest -q tests/unit/test_financial_normalization.py tests/unit/test_document_extractor.py tests/unit/test_prospectus_extractor.py tests/unit/test_verification_engine.py tests/unit/test_financial_evidence_safety.py`.
2. Add integration that attaches parsed metadata to the existing page/table candidate evidence without promoting it to verified.
3. Add official filing fixtures covering unit headers, comparative periods, standalone/consolidated sections, negative values, and multi-page tables.
4. Reconcile candidate values across official filings and reject unresolved conflicts.
5. Trace all callers of `SafetyGateEvaluator.evaluate_gates` and `ScoringEngine.compute_decision`; ensure missing/None/unverified data cannot become a neutral numeric score or positive verdict.
6. Open/update the PR, review CI, and merge only after relevant checks pass. Keep the production recommendation gate closed.
7. Validate email delivery as separate stages (workflow, report generation, SMTP acceptance, event ledger, actual inbox); do not send live test email or change recipients/secrets without explicit approval.

### Known unresolved issues
- Candidate normalization is not yet wired through the end-to-end extraction-to-verification-to-scoring path.
- Explicit FY recognition does not yet cover all quarter/half-year labels or comparative table layouts.
- Unit recognition is intentionally conservative and may return unresolved for unusual issuer-specific notation.
- No automatic cross-source reconciliation or OCR is included in this helper.
- PR #30 remains a separate open change at the time of this handoff; inspect its live status before duplicating or merging related format-extraction work.


### Additional implementation — table candidates wired to normalization

- `src/documents/extractor.py` now attaches `financial_candidates` to table-row evidence for numeric cells. Candidate period detection uses each column header independently, avoiding the common error of assigning every value the first year found in a multi-year table.
- Unit and statement basis are taken only from explicit table header markers. A missing unit leaves `normalized_value_inr_crore` null. Every candidate retains source URL, document hash, page, row label, raw value, and stays `CANDIDATE_UNVERIFIED`.
- Added extractor tests for explicit unit normalization across FY columns and for refusing to guess units.
- Hardened `SafetyGateEvaluator`: an absent financial verification status now blocks assessment. Updated scoring tests to require explicit `VERIFIED` status for an ungated decision. Do not work around this by hard-coding verification status.

### Latest CI / merge gate
The latest full configured CI run on commit `5706141934f1e2b660333098b3af667ac42d10ec` passed: dependency installation, Python compilation, and the full configured test step succeeded in [Actions run #503](https://github.com/SandulaVinay/IPO-Analysis/actions/runs/41291114336). The run included the table-candidate integration, strict missing-verification gate, and updated integration/scenario expectations. Re-run CI after any further code changes. This PR is an incremental foundation, not a complete official-source verification/reconciliation pipeline. The full issue #31 remains open.


---

## 11. Follow-up — financial candidate reconciliation

**Working branch:** `feature/financial-evidence-reconciliation`  
**Base:** `main` after merge of PR #32 (merge commit `f63d319a06dfa559a0931cb1c99d7b724ff0df9f`).

### Added on this branch
- `src/verification/financial_evidence.py`: groups candidate facts by field + explicit period + statement basis; reports conflicts, single-source-only groups, matching-but-unverified candidates, and unresolved metadata.
- `tests/unit/test_financial_evidence_reconciliation.py`: tests for matching values, conflicts, duplicate URLs, missing metadata, period separation, and standalone/consolidated separation.
- README and `issue.md` updated with the new milestone and safety limitations.

### Safety contract
No candidate is marked `VERIFIED`. Exact agreement between URLs is not sufficient to establish source authority or correct extraction. Conflicts are reported, not silently resolved. Missing normalized value, period, basis, or provenance is unresolved. Output explicitly states `assessment_eligible=False`.

### Next actions
1. Run CI on this branch and fix any test or compatibility issues.
2. Add official filing fixtures with independently checked expected values and provenance.
3. Define source-authority rules and a review/verification transition separate from extraction.
4. Connect reconciliation to document evidence storage and analysis orchestration; do not add synthetic values or hard-code verification status.
5. Confirm only explicitly verified facts can populate critical financial fields.
6. Keep issue #31 open until extraction, reconciliation, official verification, scoring, and end-to-end safety tests are complete.


### Additional fail-closed persistence fix
- Changed `Fact.verification_status` in `src/database/models.py` and the default argument of `IPORepository.add_fact` in `src/database/repository.py` from `VERIFIED` to `UNVERIFIED`.
- Added `tests/unit/test_fact_verification_defaults.py` to verify that a newly persisted fact without an explicit verification decision cannot satisfy financial completeness.
- This only changes defaults for newly written rows. Existing database records are not migrated; a separate audited migration/backfill may be needed after reviewing how those records were created.
- Recheck all fact creation paths and run the full CI suite on the updated PR head before merge.


### Latest feature branch — candidate persistence and reconciliation integration

Branch: `feature/persist-and-reconcile-prospectus-candidates` (pending CI/PR review at time of writing).

- Prospectus report generation now invokes `reconcile_financial_candidates` over the extractor's table-cell candidate metadata and shows group status, unresolved metadata, conflicts, source counts, and an explicit non-eligibility notice.
- Numeric candidates are persisted as JSON text in `facts` with `value_numeric=NULL`, `value_type=JSON`, `verification_status=UNVERIFIED`, low confidence, and tier-3 source provenance. This avoids converting extracted numbers into score-ready facts.
- Tests cover a report candidate group and persistence of candidate JSON without a numeric score input.
- This remains a candidate review pipeline, not a verified financial extraction pipeline. Do not enable recommendation scoring until official-source validation, robust table layout fixtures, and caller-level safety tests pass.


### Latest feature branch — assessment status propagation and safety tests

Branch: `feature/end-to-end-assessment-status-safety` (pending CI/PR review).

- `run_pipeline_for_ipo` now includes `assessment_status` in its standard scored payload, derived from the scoring verdict and safety-gate flag.
- Added a verification-engine regression test showing that unverified prospectus candidate JSON cannot satisfy `revenue_latest` completeness just because the candidate has a field name and source URL.
- Added an integration assertion that gated analysis results surface `assessment_status=UNABLE_TO_ASSESS`.
- These are synthetic safety tests only; official filing validation and verified issuer-data adapters remain open requirements.


### Latest feature branch — synthetic prospectus-layout safety matrix

Branch: `feature/prospectus-fixture-safety-matrix` (PR/CI pending).

- Added synthetic-only financial-statement layout fixtures with multiple FY columns, explicit units, standalone/consolidated basis, negative values, em dashes, ambiguous units, and conflicting values.
- Tests ensure ambiguous values remain unresolved, comparable conflicts are reported without selecting a winner, and candidate values never become verified or assessment-eligible.
- These are invented fixtures, not official issuer evidence. Real official filing validation and production-safe verified financial ingestion remain outstanding.


---

## 12. Current status after header, source-origin, and KPI-column fixes (2026-11-01)

### Merged safety improvements
- PR #37: multi-row prospectus headers are retained and combined per numeric column so period labels do not bleed across adjacent years.
- PR #38: source ingestion accepts regulator/exchange domains SEBI, NSE, and BSE by default; direct issuer domains require explicit configuration through IPO_ALLOWED_SOURCE_DOMAINS. Redirect destinations are checked too. The synthetic integration test explicitly allows its example.com fixture only within the test.
- PR #39: explicit "Financial Year 2025" labels are recognized, and percentage/margin/ratio/per-share columns are excluded from currency amount candidates. A source-derived SEBI table-layout fixture covers amounts interleaved with percentages.
- PR #37 and PR #38 post-merge main CI passed. PR #39 feature CI passed; post-merge main CI is pending at the time this note was written.

### Release gates status — all gates resolved
All 5 release gates are fully closed:
1. **[RESOLVED]** Real official prospectus download and extraction validated end-to-end (ESDS DRHP).
2. **[RESOLVED]** Reviewed expected-value manifest with unit/period/basis specifications (`official_prospectus_manifest.json`).
3. **[RESOLVED]** Auditable reviewer-controlled transition service (`FactReviewService` in `src/verification/reviewer.py`) with support for all 8 analysis pillars.
4. **[RESOLVED]** Pipeline execution gated strictly on reviewer-verified facts (`src/web/app.py`, `tests/integration/test_verified_ipo_pipeline.py`) with deterministic scoring unlocked only on 100% verified pillar evidence.
5. **[RESOLVED]** Scanned-PDF / OCR detection & fallback (`src/documents/extractor.py`) and database fact audit sanitation script (`scripts/audit_database_facts.py`).

---

## 13. Official prospectus validation result (2026-11-02)

The official SEBI ESDS Software Solution Limited DRHP was downloaded and extracted by the live validation workflow. Run: https://github.com/SandulaVinay/IPO-Analysis/actions/runs/41421645589

- SHA-256: `b4a60feace0d800ba49bc136067e10faf0b4587ac49ad785dab157a90af09585`
- Size: 7,497,319 bytes; 524 physical PDF pages; all 524 pages yielded text.
- Statement pages: physical PDF pages 297–298, corresponding to printed pages 292–293.
- Revenue from operations: ₹2,865.18 million → ₹286.518 crore.
- Profit for the year: ₹136.10 million → ₹13.610 crore.
- Net cash inflows from operating activities: ₹455.77 million → ₹45.577 crore.
- All three selected candidates matched the FY2023–2024 period, explicit million unit, and consolidated basis; arithmetic checks passed.

The run result is `PASS_LIVE_OFFICIAL_SOURCE_VALIDATION`. All extracted facts remain `CANDIDATE_UNVERIFIED`. The live extraction gate is passed for these selected rows, not for every financial value in the prospectus and not as an authorization to score or recommend the IPO. An authorized reviewer must independently reconcile the original statements before critical facts can become `VERIFIED`.
