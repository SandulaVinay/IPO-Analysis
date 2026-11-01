# Issues Faced and Fixes — IPO-Analysis

> This is a living engineering log. “Fixed” means a code or configuration change was made; it does not automatically mean the complete production workflow or external delivery has been proven. Re-check the linked PRs, current code, and latest Actions runs before relying on any status.

## 1. Financial evidence and assessment safety

### Problem
Financial analysis could appear more complete than the evidence justified when critical fields or comparable historical periods were missing. Candidate values extracted from documents could also be mistaken for verified facts.

### Fix implemented
- Added/strengthened fail-closed safety gates so any missing critical field blocks a positive assessment.
- Explicitly unverified financial evidence and unresolved critical flags block assessment.
- Financial trend analysis returns `UNABLE_TO_ASSESS` when comparable periods or required revenue/PAT values are missing.
- Earnings-quality score is omitted when latest operating cash flow (CFO) is missing, with a visible limitation.
- Added regression tests for these cases.

**Reference:** [PR #25 — Fail closed on missing or unverified financial evidence](https://github.com/SandulaVinay/IPO-Analysis/pull/25) (merged).

### Still pending
Trace all live callers and report/API serialization to prove no caller replaces missing scores with zero/neutral values or ignores `assessment_status`. End-to-end tests must prove an unverified filing cannot result in a positive recommendation.

## 2. Prospectus PDF text is not the same as structured financial extraction

### Problem
PDF text extraction can capture a revenue/PAT line but does not reliably determine which number belongs to which financial year, unit, comparative column, or standalone/consolidated statement. PDF layouts and multi-page tables can vary.

### Fix implemented
- Bounded PDF extraction preserves document hash, source URL, page number, and candidate evidence text.
- Table-row candidates are marked `CANDIDATE_UNVERIFIED`; no candidate is automatically promoted to `VERIFIED`.
- A new feature branch adds conservative normalization helpers and tests for explicit units, Indian number grouping, negative values in parentheses, explicit FY labels, statement basis, and provenance.
- The normalizer deliberately withholds normalization when unit context is absent and does not verify a fact.

**Reference:** [Prospectus extractor](https://github.com/SandulaVinay/IPO-Analysis/blob/main/src/documents/extractor.py), [new normalization module on the feature branch](https://github.com/SandulaVinay/IPO-Analysis/blob/feature/verified-financial-evidence-pipeline/src/documents/financial_normalization.py).

### Still pending
Integrate candidate parsing into the ingestion/extraction pipeline; validate against representative official filing fixtures; reconcile values across official sources; support more table layouts; handle scanned PDFs/OCR separately; and only then provide verified facts to scoring.

## 3. Multiple filing formats and fallback-source risk

### Problem
Exchange attachments can be PDF, HTML/iXBRL, XBRL XML, CSV, or spreadsheet formats. Treating every attachment as a PDF or using a secondary website as if it were an official exchange fact risks missing data or misrepresenting provenance.

### Fix proposed in open PR
PR #30 adds format detection and bounded extraction for several formats plus a guarded secondary-source fallback. The PR description states that fallback values are not exchange-verified, PDF table extraction remains limited, and OCR/spreadsheet normalization remain follow-up work.

**Reference:** [PR #30 — Add multi-format financial results extraction and Screener fallback](https://github.com/SandulaVinay/IPO-Analysis/pull/30) (status must be checked live; do not assume merged).

### Still pending
Check the latest PR and CI status, review fallback eligibility and provenance, normalize supported formats consistently, and keep unsupported or conflicting data unavailable/unverified.

## 4. SMTP email tests sent synthetic/test content instead of a real alert

### Problem
The owner reported receiving a synthetic test email rather than the intended production report, and later reported not receiving an email after a trigger. A workflow's green status does not prove an email reached the inbox.

### Fix implemented
- Removed synthetic figures from the email test path.
- Removed the scheduler SMTP smoke test that could produce confusing test messages.
- Added a manual daily-digest resend option to the workflow.
- Kept push-triggered validation from sending live email.

### Operational distinction
These are separate checkpoints:
1. The workflow step ran.
2. The application created the intended report/event.
3. SMTP accepted the message.
4. The event ledger recorded the intended status.
5. The message arrived in the intended inbox (and was not filtered).

Only the final inbox check confirms delivery. Do not send live tests, alter recipients, clear event ledgers, or expose SMTP credentials without explicit authorization.

**References:** [Repository Actions](https://github.com/SandulaVinay/IPO-Analysis/actions), [latest main commit](https://github.com/SandulaVinay/IPO-Analysis/commit/2c7ea5d9151eec4951f5d8b46bba846cc613d41e).

## 5. Exchange source reliability and issuer matching

### Problems reported
- NSE requests timed out.
- BSE IPO page layout was not recognized by the parser.
- A combined discovery failure could prevent results monitoring from running.
- SMTP disconnected during a send attempt.
- Company names and exchange symbols/scrip codes must be matched carefully to avoid cross-issuer results.

### Fixes reported in prior engineering work
- Discovery, results monitoring, and health checks were separated into independent workflow steps so one exchange outage should not automatically suppress other checks.
- Exchange-specific parsing and BSE scrip-code support were added/iterated.
- Results monitoring uses exact issuer-name matching and configured BSE scrip codes.
- SMTP diagnostics and explicit email enablement were improved.

### Still pending
Verify each behaviour against the current workflow and recent logs. Add or retain fixture tests for source layout changes, timeouts, retries, duplicate events, and issuer mismatches. Never interpret a source outage as “no IPOs/no results”.

## 6. SQLAlchemy async dependency failure

### Problem
A prior run failed because the SQLAlchemy async stack required the `greenlet` package.

### Fix implemented/reported
`greenlet` was added to `requirements.txt`; SQLAlchemy and aiosqlite dependency versions were also updated.

### Still pending
Run a clean environment install and the full test suite in CI to verify dependency compatibility rather than relying on a requirements-file change alone.

## 7. Production-readiness gap

### Problem
Discovery, monitoring, reports, and notification infrastructure existed before the verified financial-data pipeline was complete. That can create an impression that automated investment recommendations are ready when core evidence is not.

### Fix implemented
README and architecture docs state that production recommendations are gated and that `UNABLE_TO_ASSESS` is the correct result until official-source financial extraction and verification are complete.

### Remaining release gates
- [ ] Candidate extraction wired into actual issuer analysis.
- [ ] Period, unit, and statement-basis validation.
- [ ] Official-source reconciliation and conflict reporting.
- [ ] Scoring consumes only verified facts.
- [ ] End-to-end negative tests prove ambiguous evidence cannot produce a positive verdict.
- [ ] Full CI passes on the final PR head.
- [ ] Notification workflow validated without synthetic content; actual delivery checked separately.
- [ ] README, handoff, and operations docs updated to match the merged code.

## Engineering rule

Never describe a fix as production-complete just because a helper, unit test, or workflow exists. Record the exact code change, test evidence, and remaining limitation separately.


## 8. Missing financial verification status could bypass a safety gate

### Problem found during review
The scoring safety gate rejected a non-empty verification status when it was not `VERIFIED`/`PASS`, but an absent/empty status did not itself add a gate reason. This meant a caller supplying otherwise-complete metadata and an empty financial object could be treated as a clean case by the gate unit test.

### Fix made on the feature branch
- Changed the gate to fail closed unless `financial_info.verification_status` is explicitly `VERIFIED` or `PASS`.
- Updated tests so a missing status is expected to block assessment and a clean score requires explicit verification.
- This is deliberately stricter; callers that do not yet pass verified status will now return `UNABLE_TO_ASSESS` rather than an attractive verdict.

### Validation
The updated unit tests are part of the current PR CI run. Confirm the latest run succeeds before merging. If an application caller relies on an empty `financial_info`, update it to pass a genuine verification result only after official-source validation; do not insert a hard-coded `VERIFIED` value to make tests pass.


### Follow-up found by full-suite CI
The first full-suite run after tightening the gate exposed two tests that still expected synthetic/demo financial inputs to produce an attractive or positive score. Those expectations contradicted the fail-closed rule.

**Fix:** the strong-IPO scenario now explicitly declares its fixture evidence verified; the end-to-end pipeline test now expects synthetic demo inputs to return `UNABLE_TO_ASSESS`, a zero score, and no profitable recommendation classification. The next full CI run must confirm these changes.


## 9. Financial candidate reconciliation across sources

### Problem
Extracted numeric candidates from different periods, statement bases, or source documents must not be compared as if they describe the same fact. Matching values also do not, by themselves, prove that either source is authoritative or that the extraction mapped the correct column.

### Fix implemented on the follow-up branch
- Added `src/verification/financial_evidence.py` to group candidates only by field, explicit period, and statement basis.
- Conflicting normalized values for the same comparable key are flagged as `CONFLICT`.
- One URL is labelled `SINGLE_SOURCE_UNCONFIRMED`; matching values from multiple URLs are labelled `MATCHING_CANDIDATES_UNVERIFIED`.
- Missing value/unit normalization, period, basis, or provenance stays unresolved.
- The module always preserves `CANDIDATE_UNVERIFIED` and sets `assessment_eligible=False`; it never selects a winning value or upgrades evidence to verified.
- Added tests for conflicts, same-value candidates, duplicate source URLs, missing metadata, separate periods, and standalone/consolidated separation.

### Still pending
Wire reconciliation into the document/Fact storage and analysis orchestration without bypassing official-source validation; add real official filing fixtures; define a reviewed source authority policy; and only allow scoring from independently verified facts. Full issue #31 remains open.


## 10. New database facts defaulted to VERIFIED

### Problem found during follow-up review
The `Fact` ORM model and repository helper defaulted `verification_status` to `VERIFIED`. A caller that omitted the status could therefore create a fact that the completeness engine later counted as verified, despite no explicit verification step.

### Fix implemented on the follow-up branch
- Changed the ORM model default and `IPORepository.add_fact` argument default to `UNVERIFIED`.
- Added an async regression test that stores a fact without passing verification status and confirms it does not satisfy critical financial completeness.
- Callers must now explicitly set a verified status only after the relevant official-source review has actually succeeded.

### Remaining check
Review all fact-creation paths for explicit status assignments and ensure none blindly labels scraped or extracted candidate values as `VERIFIED`. Existing databases may already contain incorrectly verified records; this code change does not migrate or reclassify existing rows.


## 8. Prospectus financial candidate persistence and reconciliation integration

### Implemented on the current feature branch
- Connects the table extractor's `financial_candidates` to the reconciliation helper when generating the prospectus review report.
- The report now summarizes comparable groups, unresolved metadata, conflicts, represented source URLs, and the explicit `assessment eligible: no` safety statement.
- Persists each extracted table-cell candidate as JSON text in a `Fact` record with `value_type=JSON`, `value_numeric=NULL`, low confidence, tier-3 provenance, and `verification_status=UNVERIFIED`.
- Adds regression coverage for report reconciliation and safe candidate persistence.

### Safety boundary
This is evidence storage and review only. Matching values do not become verified, JSON candidates do not populate numeric scoring inputs, and no live financial recommendation is enabled. The branch must pass CI and the current database/schema path must be tested before merge.
