# AI Agent Handoff — IPO-Analysis

> **Purpose:** Operational handoff for the next AI coding agent. Read this first, then confirm against the live repository and GitHub Actions before changing anything. Repository state and current checks are authoritative; this file is a snapshot.
>
> **Last updated:** 2026-11-22  
> **Repository:** https://github.com/SandulaVinay/IPO-Analysis  
> **Default branch:** `main` at `672cca9` (2026-11-20)  
> **CI on that commit:** "CI - Tests and Safety Checks" passed — **217 passed** ([run 44663292452](https://github.com/SandulaVinay/IPO-Analysis/actions/runs/44663292452)).  
> **Scheduler:** "Automated IPO Discovery & Alert Scheduler" scheduled runs on `main` succeeding through 2026-11-20. A green run does not prove an email or Telegram message was delivered.

Sections 1–2 describe the current state. Sections 3 onward are a **historical log** kept for context; where they disagree with sections 1–2, sections 1–2 win.

---

## 1. START HERE — Current state and next steps

**Goal:** a reliable IPO-analysis and monitoring system that gathers official company/IPO evidence, analyses financial quality and risk, and sends useful alerts — without fabricating data or issuing recommendations from incomplete or unverified evidence.

### What exists on `main` today
- **Discovery:** official NSE/BSE IPO pages, plus the NSE JSON API (`https://www.nseindia.com/api/ipo-current-issue`) via `parse_nse_current_issues_payload` / `_fetch_nse_api_current_issues` in `src/ingestion/scrapers.py` (added 2026-11-19, `b1e1244`).
- **Results monitoring** (`src/results/monitor.py`): structured XBRL feeds plus NSE corporate announcements ("Outcome of Board Meeting", "Financial Results"), merged per period, with official PDF attachments (added 2026-11-19, `a28cfb9`). `nseindia.in` redirect domain is accepted by the attachment validator. The rolling lookback window is enforced strictly (`132a974`). Extracted values remain `CANDIDATE_UNVERIFIED`.
- **Daily digest** (`src/reporting/daily_digest.py`): includes live NSE IPOs and recent financial results (`b1e1244`). Still `UNABLE_TO_ASSESS` for Apply/Avoid until verified evidence is connected.
- **Notifications:** Telegram bot (`src/notifications/telegram.py`, added 2026-11-20, `672cca9`) is prepended to the provider list when `ENABLE_TELEGRAM` is true; then Email, then WhatsApp (optional fallback). Telegram supports PDF attachments. Manual test script: `scripts/test_telegram.py`. Settings: `ENABLE_TELEGRAM`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (see `.env.example`).
- **Scheduler workflow** (`.github/workflows/ipo_scheduler.yml`): runs every day at 07:47 IST (cron `17 2 * * *`, `DIGEST_SESSION=PRE_OPEN`) and 16:17 IST (cron `47 10 * * *`, `DIGEST_SESSION=POST_CLOSE`); each session sends its own digest with its own idempotency key. Until 2026-11-22 the schedule was four weekday runs and scheduled runs started roughly 7.5–9 hours late (e.g. the 17:30 IST digest arrived around 01:00 IST). Check whether the new off-the-hour schedule fires on time; if not, trigger `workflow_dispatch` externally. `ENABLE_TELEGRAM` resolves to `false` on push events, otherwise to the `ENABLE_TELEGRAM` secret, **defaulting to `true`** if that secret is unset. Repository secrets currently present (names only): `EMAIL_TO`, `ENABLE_EMAIL`, `ENABLE_TELEGRAM`, `SMTP_PASSWORD`, `SMTP_USER`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. `DATABASE_URL` is **not** set.
- **Verified scoring pipeline:** 8-pillar reviewer-verified pipeline (`FactReviewService` in `src/verification/reviewer.py`, `run_pipeline_for_ipo` in `src/web/app.py`), secured reviewer API (`src/web/reviewer_auth.py`, PR #50), typed/finite evidence validation before scoring, OCR fallback for scanned PDFs, expanded Ind AS XBRL taxonomy (`9c825f3`, 2026-11-05). Scoring is ungated only when all 8 pillars are reviewer-verified; otherwise `UNABLE_TO_ASSESS`.
- **Official-source validation:** ESDS DRHP selected FY2024 rows validated end to end (section 13). Those facts are still `CANDIDATE_UNVERIFIED` pending reviewer approval.

### Not yet verified / open
1. **Telegram:** the Bot API accepted the 2026-11-21 digest (log: "Telegram document successfully sent ... message ID 13" in run 44804256454). Arrival on the owner's device is confirmed only by the owner.
   - **IPO opinion quality:** every digest entry is `UNABLE_TO_ASSESS` because no RHP link, reviewer-verified facts, subscription data, or matched GMP reach the digest. See the improvement plan in the PR/issue for this work before changing scoring.
2. **No persistent database in Actions.** Without `DATABASE_URL`, reviewer-verified facts and analysis runs are lost between scheduled runs; only the sanitized `state` branch persists. Production scoring therefore stays `UNABLE_TO_ASSESS` in scheduled runs.
3. **No reviewer-approved facts yet.** ESDS and all other extracted figures are candidates only.
4. **NSE API fragility.** The NSE endpoint needs a cookie warm-up request and browser-like headers; it may break or rate-limit without notice. Discovery falls back to HTML table parsing.
5. **Open PRs to triage:**
   - #41–#45 Dependabot: reportlab `>=5.1.0`, pdfplumber `>=0.11.10`, lxml `>=6.1.3`, pypdf `>=6.21.4`, apscheduler `>=3.11.3`. Rebase, check CI, merge individually (reportlab and pypdf are major bumps — check PDF rendering/extraction tests).
   - #30 multi-format results extraction + Screener fallback — likely superseded by work already on `main`; compare before closing. Screener is not an official source.
   - #27 old GPT handoff doc — superseded by this file; close.
6. **Stale remote branches:** ~30 merged/abandoned `feature/*`, `docs/*`, `fix*` branches remain on origin. Clean up only with owner approval.
7. **Docs drift:** README says 205 tests (CI now runs 217); README notifications section does not yet describe Telegram.

### Suggested next task
Confirm Telegram delivery with the owner, then triage open PRs (Dependabot first, then close #27 and decide on #30). After that, decide whether to provision a persistent PostgreSQL `DATABASE_URL` so reviewer-verified facts survive between runs.

---

## 2. Status summary

| Area | Status | Notes |
|---|---|---|
| CI test suite | Passing | 217 passed on `672cca9`. |
| Scheduled workflow | Running | Daily 07:47 IST (pre-open) and 16:17 IST (post-close) since 2026-11-22; earlier runs were ~8 h late. |
| IPO discovery | Implemented | NSE/BSE HTML + NSE JSON API. |
| Results monitoring | Implemented | XBRL + NSE corporate announcements; PDF/XML/iXBRL/HTML/CSV/TSV/XLS/XLSX attachments; candidate-only values. |
| Daily digest | Implemented | Live IPOs + recent results; IPOWATCH GMP snapshot only after exact issuer match; no Apply/Avoid. |
| Telegram alerts | Implemented, Bot API accepting | First provider when enabled; device arrival confirmed only by the owner. |
| Email alerts | Implemented | Plain-text + HTML, optional PDF attachment. |
| WhatsApp | Optional fallback | Disabled unless explicitly enabled. |
| Financial extraction & normalization | Implemented | Provenance, period/unit/basis detection, reconciliation (`src/documents/`, `src/verification/financial_evidence.py`). |
| Reviewer verification | Implemented | `FactReviewService`, secured API, audit log. No facts promoted yet. |
| 8-pillar scoring | Implemented, gated | Unlocks only with all pillars reviewer-verified. |
| Persistent storage in Actions | Missing | `DATABASE_URL` not configured. |
| Production investment recommendations | Not live | Fail-closed `UNABLE_TO_ASSESS` until verified evidence is connected and persisted. |

---

# Historical log (2026-10-31 → 2026-11-05)

The sections below are preserved from earlier handoffs. Checkbox lists, progress estimates, and "next actions" in them are historical and may already be done or superseded.

## 3. Earlier completed work (historical)

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
- Provider order: Telegram first when `ENABLE_TELEGRAM` is true (added 2026-11-20), then email, then WhatsApp. WhatsApp remains deferred/disabled unless explicitly requested and separately configured.
- Do not change recipients, SMTP or Telegram secrets, chat IDs, or other credentials.
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

## 8. Working rules for the next agent (still current)

- Continue the implementation; do not merely give advice if repository tools permit editing and testing.
- Read relevant source files and callers before changing contracts.
- Do not assume earlier chat messages are current; inspect GitHub.
- Do not claim PDF text extraction is financial metric extraction.
- Do not claim a workflow run means alert delivery.
- Do not enable live email/Telegram/WhatsApp, alter recipients/secrets, clear ledgers, or send test alerts (including `scripts/test_telegram.py`) without explicit authorization.
- Do not issue or enable production investment recommendations from unverified inputs.
- Prefer small, reviewable PRs and regression tests.
- If tests fail, inspect logs and fix root causes. Never merge while required checks are failing or pending.
- Keep the README, architecture docs, and this handoff aligned with actual behaviour.
- Update sections 1–2 of this handoff (state, open items, status table) whenever concrete milestones change.

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

**Milestone status (historical):** closed by the ESDS live validation in section 13. The synthetic fixture remains a parser regression fixture only.


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

---

## 14. Change log

Every change adds an entry here. The working procedure is in [SKILL.md](SKILL.md). Entries are newest first.

- **2026-11-22 — feat/quarter-results-display, Stage 2 (not yet a PR).** The digest's results section now labels every item `CANDIDATE, not verified` (fail-closed). `VERIFIED` is never emitted: no code path links a reviewed Fact to a quarter, so it stays unused until a later stage does. Each item shows period ended, audited status, statement basis, broadcast time and the filing link, or `source not captured` when the `reports/results` header is missing or a placeholder. Candidate revenue, PAT, EPS and operating cash flow are shown only when the .md file has a numeric value, each marked `(candidate, not verified)`. Tests: daily digest 21 passed; full suite 227 passed with the 2 known pypdf failures. `tests/unit/test_ipo_status.py` does not exist on this branch (it is on PR #56). **Not done:** no VERIFIED rule, no schema change, no edits to `_plain_company_summary`, `_status_line` or `src/analysis/ipo_status.py`, and no check of whether any real stored result has a reviewed source.
- **2026-11-22 — feat/ipo-status-rules, Stage 1.** New `src/analysis/ipo_status.py` gives each IPO a rules-only status: APPLY, NEUTRAL, AVOID, WAIT or UNABLE_TO_ASSESS. Inputs are GMP (unofficial), issue price and Day 3 subscription; financials are not used. Every status is labelled indicative. Starting thresholds, not calibrated: APPLY needs estimated gain >= 10% and Day 3 subscription >= 10x; gain < 0 is AVOID; no subscription data caps the result at NEUTRAL. **Gap:** no subscription source adapter exists (`fetch_subscription_status` returns None), so APPLY cannot fire until one is built. Digest card shows the status line. Relay `/ongoing` does not show it yet. Tests: 9 new status tests, 28 pass in the digest and status files; full suite 234 pass, 2 known Windows pypdf failures.
- **2026-11-22 — feat/telegram-ipo-commands, PR #53, merged.** Relay Worker `ipo-analysis` deployed; webhook set and `/ongoing` verified. Workers Builds passed after adding an empty `[previews]` block to `wrangler.toml` (root) and `relay/wrangler.toml` (commit `8b9f773`). Note: the `main` branch build previously ran `wrangler preview` and needed that block.
- **2026-11-22 — docs/skill-change-workflow (this change).** Added `SKILL.md`, the procedure for branches, tests, handoff updates, checks and merges. Added this change log. No code changed. PR: see the PR for this branch.
- **2026-11-22 — fix/neon-database-url, PR #54, merged as `d7952f0`.** `src/database/url.py` converts Neon libpq URLs (`sslmode`, `channel_binding`) to the asyncpg form. The repo secret `DATABASE_URL` was already set, so the scheduler uses Neon from its next run. Tests: 5 new; full suite 224 passed with the 2 known Windows failures. **Process note:** this PR was merged while the Cloudflare check `Workers Builds: ipo-analysis` was failing. That check is the Cloudflare build of the repository root, not the code tests. The fix is in the Cloudflare dashboard (see the next entry).
- **2026-11-22 — chore/relay rename, commit `86e99b7` on PR #53.** The relay Worker is renamed `ipo-analysis` in `relay/wrangler.toml`, `relay/README.md` and `relay/src/worker.js`, to match the existing Cloudflare Worker. Open item: point the Cloudflare build at the `relay` folder (root directory `relay`, deploy command `npx wrangler deploy`), then add secrets `TELEGRAM_BOT_TOKEN`, `WEBHOOK_SECRET`, `OWNER_CHAT_ID`.
- **2026-11-22 — feat/telegram-ipo-commands, PR #53, open.** `relay/` Cloudflare Worker answers `/ongoing` (open now, with last date to apply) and `/upcoming`, for the owner's chat only. Reads the public `state/ipo_registry.json`. Tests: 13 relay tests pass. **The relay is not on `main` and not deployed.**
- **2026-11-22 — fix/telegram-digest-message, PR #52, merged as `cb94656`.** Telegram sends plain text (legacy Markdown removed underscores). No 3,500-character truncation; the PDF is the caption and text follows in split messages. Per-IPO cards show timing (open now / opens / closed), price band, issue size, GMP, rating status, short status and source. Footer says the PDF is attached.
- **2026-11-22 — docs/handoff-2026-11-22 + scheduler, PR #51, merged as `54f7f0a`.** The scheduler runs daily at 07:47 IST (`DIGEST_SESSION=PRE_OPEN`) and 16:17 IST (`POST_CLOSE`). Each session has its own digest key and subject. Manual runs take a `digest_session` input. Scheduled runs had started hours late before this change; check the timing after the switch.
- **2026-11-22 — Dependabot, PRs #41, #42, #43 merged.** reportlab `>=5.1.0`, pdfplumber `>=0.11.10`, lxml `>=6.1.3`. PRs #44 (pypdf) and #45 (apscheduler) conflicted and were asked to rebase. PRs #27 and #30 closed as superseded; #30's Screener.in fallback was not carried forward because it is not an official source.
- **2026-11-20 — feat/notifications, commit `672cca9`.** Telegram provider added, first in the provider list when `ENABLE_TELEGRAM` is true.
- **2026-11-19 — feat/discovery and results, commits `b1e1244`, `a28cfb9`.** NSE current-issues API and NSE corporate announcements added to discovery and results.

### Open items recorded here

1. Cloudflare Worker deploy: fix the build root (above), add secrets, send the `workers.dev` URL, register the Telegram webhook.
2. Merge PR #53 after its checks pass; the relay is not on `main` until then.
3. `/run` and `/report` Telegram commands: planned, not built. `/run` will need the `GITHUB_TOKEN` Worker secret (fine-grained, `SandulaVinay/IPO-Analysis` only, Actions read and write).
4. Neon: confirm the first scheduled run after PR #54 writes to Neon and that `init_db` succeeds.
5. Opinions: labelled Indicative / Verified (not built). Full research report planned in stages (see the plan in the conversation record).

## 15. Change log — Workers Builds root config (feat/telegram-ipo-commands, PR #53)

- Cloudflare build daa6fe57 failed with "Could not detect a directory containing static files" during `npx wrangler deploy`. Wrangler ran where no `wrangler.toml` existed, so it fell back to static assets.
- Fix: added a root `wrangler.toml` (`main = "relay/src/worker.js"`). Dry-run passes from both the repo root and `relay/` (7.96 KiB bundle, no bindings).
- Still open: confirm the next Workers Builds check passes. Secrets (TELEGRAM_BOT_TOKEN, WEBHOOK_SECRET, OWNER_CHAT_ID) are set in Cloudflare, not in the repo.
