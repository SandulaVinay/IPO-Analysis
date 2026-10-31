# GPT Project Handoff — IPO-Analysis

> **Purpose:** This file is an operational handoff for a future GPT/AI coding agent. Read it before making changes. It is written so work can resume immediately without asking the user to repeat the project history.
>
> **Repository:** https://github.com/SandulaVinay/IPO-Analysis  
> **Default branch:** `main`  
> **Handoff updated:** 2026-10-31  
> **Current project progress estimate:** **62% complete**  
> **Current active workstream:** Make financial assessment fail closed on missing/unverified evidence; next implement conservative prospectus PDF financial-table extraction and verification.

---

## 1. Start here — immediate state

The latest completed code change is **PR #25**, merged into `main` after its GitHub Actions test check passed.

- PR: https://github.com/SandulaVinay/IPO-Analysis/pull/25
- Merge commit: `68772d09e9b485218b96f47b41da47f9ae0f9911`
- Tested head commit before merge: `6e14748ee1381ccb1a348d8402f76c43ae05b180`
- Test run: https://github.com/SandulaVinay/IPO-Analysis/actions/runs/41184737247
- Branch used for that change: `fix/financial-evidence-fail-closed`

PR #25:
1. Changed `src/scoring/safety_gates.py` so **any** field marked critical and missing gates the assessment; it no longer tolerates up to two missing critical fields.
2. Gates explicitly unverified financial evidence when the caller passes `verification_status` other than `VERIFIED` or `PASS`, and gates `has_unverified_critical_financials`.
3. Changed `src/analysis/financials.py` to return `UNABLE_TO_ASSESS` with null scores when history or required revenue/PAT values are missing, instead of outputting neutral-looking scores.
4. Omits the earnings-quality score when latest-period CFO is unavailable and exposes a limitation.
5. Added `tests/unit/test_financial_evidence_safety.py`.

**Immediate next action:** inspect current `main`, check the post-merge CI run, then trace the financial data path end-to-end before implementing more parsing. Do not assume PR #25 alone completes the assessment safety path; inspect all callers and data shapes.

## 2. Project objective

Build a reliable, evidence-driven Indian IPO intelligence and analysis platform that can:

- Discover upcoming IPOs and maintain a watchlist.
- Collect official issuer, exchange, prospectus, and financial-results evidence.
- Preserve provenance for facts and documents.
- Analyze financial quality, valuation, governance, and forensic risks using deterministic Python calculations.
- Produce concise Markdown/PDF reports and status digests.
- Send explicitly configured alerts, currently preferring SMTP email.
- Run scheduled checks through GitHub Actions and support local CLI/FastAPI dashboard use.

This is an evidence-backed research/decision-support tool, not a system that should invent missing data or guarantee investment outcomes.

## 3. Project progress — 62% (estimate)

This is a **workstream-weighted engineering estimate**, not a measured test-coverage or production-readiness percentage. The core automation and supporting architecture are substantially built; the most consequential production gate—verified, table-aware financial evidence flowing into real IPO scoring—is still incomplete.

| Workstream | Status | Notes |
|---|---|---|
| Repository architecture, CLI and dashboard foundations | Mostly implemented | Existing Python CLI and FastAPI dashboard; verify current code before changing. |
| IPO discovery and scheduled GitHub Actions | Implemented with limitations | Scheduled checks exist; workflow success does not prove every external source or email delivery worked. |
| Results monitoring | Partial | Conservative subset of NSE XBRL facts; BSE announcements are monitored but their financial tables are not yet normalized into the same verified model. |
| PDF text extraction and source excerpts | Partial | Bounded PDF extraction has been added; text excerpts are not equivalent to verified financial metrics. |
| Financial calculations and forensic/valuation modules | Partial | Modules exist, but inputs and evidence need end-to-end validation before real recommendations. |
| Critical-data safety gates | Improved; needs integration audit | PR #25 makes any missing critical field gate the assessment and handles explicitly unverified financial data. Confirm every production path supplies these fields correctly. |
| Prospectus financial table extraction | Not complete | Must conservatively extract candidate figures with source page, row label, period, units, and statement basis. |
| Period/unit/consolidated-vs-standalone reconciliation | Not complete | Essential before candidate figures become verified metrics. |
| Real-source end-to-end IPO scoring and validation | Not complete | Production must remain `UNABLE_TO_ASSESS` until required evidence is verified and wired into scoring. |
| Notifications | Email-first, partial | SMTP email is preferred when explicitly configured. WhatsApp is deferred; do not treat it as enabled. |
| Operations/docs/tests | Substantially implemented, ongoing | Multiple docs and CI/test improvements have been merged. Keep docs aligned with actual behavior. |

**Progress interpretation:** 62% reflects the current overall engineering state, not that the system is 62% safe to issue recommendations. Production recommendation readiness is **not achieved** until the financial verification pipeline is complete and tested against official real-world documents.

## 4. Important repository history / already completed work

The following work was completed and merged before this handoff. Avoid redoing it without a concrete regression or need:

- Timestamp placeholder fallback fixes and tests in the results monitor.
- End-to-end integration test coverage for the monitoring path.
- Notification workflow configuration: alert enablement is separated from SMTP smoke testing; push-triggered validation runs disable real email delivery.
- PDF report source URL wrapping and compact clickable links.
- Bounded PDF text extraction using `pypdf` in `src/results/monitor.py`: checks PDF signature, caps attachment size at 15 MB, reads at most 12 pages and 12,000 characters, and labels page excerpts. Extracted text is evidence context only, not verified financial facts.
- Email-first provider order in `src/notifications/orchestrator.py`; WhatsApp is deferred.
- README and architecture docs updated for email-first rollout and current limitations.
- Dependency updates merged: `aiosqlite >=0.22.1` and SQLAlchemy `>=2.1.6`.
- PR #25 financial evidence safety improvements described above.

Useful previous CI references:
- PR #21 PDF extraction: https://github.com/SandulaVinay/IPO-Analysis/actions/runs/41180704386
- PR #23 notification order: https://github.com/SandulaVinay/IPO-Analysis/actions/runs/41181533473
- PR #24 docs correction: https://github.com/SandulaVinay/IPO-Analysis/actions/runs/41181623654
- Pre-PR #25 main CI: https://github.com/SandulaVinay/IPO-Analysis/actions/runs/41181672922
- PR #25 safety tests: https://github.com/SandulaVinay/IPO-Analysis/actions/runs/41184737247

## 5. Current code areas to inspect first

Read these files from current `main` before editing:

- `src/results/monitor.py` — results discovery, attachment download, PDF text extraction, XBRL extraction, report text.
- `src/analysis/financials.py` — financial quality and earnings quality scoring.
- `src/scoring/safety_gates.py` — hard assessment gates.
- `src/analysis/valuation.py` — valuation and `UNABLE_TO_ASSESS` behavior.
- `src/analysis/forensics.py` — forensic checks and unavailable-evidence handling.
- `src/calculations/math.py` — deterministic formulas.
- The verification engine / completeness model / scoring orchestration (find current paths with a repository tree search; names and paths may have changed).
- `tests/unit/test_financial_evidence_safety.py` — PR #25 regression coverage.
- `tests/unit/test_results_monitor.py` and integration tests — results monitor/PDF extraction tests.
- `docs/ARCHITECTURE_V2.md`, `ANALYSIS_SPEC.md`, `SCORING_MODEL.md`, `DATA_SOURCES.md`, `README.md` — constraints and documentation.

Do not assume the exact caller/schema from this handoff. Retrieve current files and trace all call sites before changing signatures.

## 6. Next work — recommended sequence

### Task A — verify PR #25 behavior end-to-end (start here)

1. Confirm PR #25 is merged and check latest `main` Actions result.
2. Run or inspect the full CI suite, not only the new tests.
3. Search every call to `SafetyGateEvaluator.evaluate_gates` and `FinancialAnalyzer.analyze_financials`.
4. Confirm the production scoring path actually passes critical completeness data and financial verification metadata.
5. Find consumers that assume score values are always numeric; update them to handle `None` and `UNABLE_TO_ASSESS` without crashes or misleading formatting.
6. Add tests for the actual orchestration path, not only isolated class tests.
7. Inspect `FinancialMath.calculate_cagr` behavior for zero/negative starting values and ensure results are not misrepresented as normal growth.

### Task B — implement conservative financial PDF table extraction

Goal: produce **candidate facts**, not automatic verification.

1. Use the existing bounded PDF download/extraction pathway; avoid duplicating unsafe download logic.
2. Inspect dependency availability (`pdfplumber` is in the project requirements) and select a table extraction strategy that can be tested.
3. Represent each candidate with fields along these lines:
   - issuer and source document URL / document hash if available
   - page number
   - raw row label and raw cell text
   - normalized metric candidate (e.g., revenue, PAT, CFO, net debt, net worth) only if mapping is unambiguous
   - reported period text (do not infer missing periods)
   - raw unit and normalized unit only if unambiguous
   - standalone/consolidated/unknown statement basis
   - source text/table excerpt
   - extraction method and parser version
   - status such as `CANDIDATE_UNVERIFIED`
   - reason for uncertainty / validation warnings
4. Preserve the raw table rows and evidence; never throw away the source representation when normalization fails.
5. Be conservative with Indian financial-statement labels, brackets/parentheses for negative values, commas, dashes, and units such as rupees, lakhs, crores, thousands, and millions.
6. Do not assume the first numeric column is the latest period. Header and period matching must be explicit.
7. Do not mix quarterly, half-year, annual, or year-to-date values without a valid reconciliation rule.
8. Do not mix standalone and consolidated values.
9. If table extraction is ambiguous, return the candidate with a warning or no normalized metric; do not guess.
10. Add synthetic fixtures for different common table layouts, including multi-line headers, missing cells, negative figures, different units, and standalone/consolidated headings. Clearly state that synthetic tests do not replace validation against official documents.

### Task C — build verification/reconciliation before scoring

1. Define a single normalized financial fact schema and its allowed statuses.
2. Validate period type, start/end dates when available, unit scale, currency, and statement basis.
3. Cross-check repeated facts against authoritative source evidence where available (official RHP/DRHP, audited statements, exchange filings/XBRL).
4. If values conflict or cannot be reconciled, keep them unverified and record a conflict.
5. Require the critical metrics and the required historical periods before calculating the corresponding score.
6. Wire verified facts into the existing financial analyzer only after the validation gate.
7. Keep `UNABLE_TO_ASSESS` if critical evidence is missing, ambiguous, stale, conflicting, or unverified.
8. Add tests for both successful verified cases and fail-closed cases.

### Task D — real-source end-to-end validation

Use a small set of official documents and keep their source URLs and page citations in test fixtures where licensing and repository policy permit. Do not commit large PDFs or confidential material unnecessarily. Validate parser behavior against actual layouts. For each test, document expected period, unit, basis, and values and why they are unambiguous.

### Task E — documentation and release readiness

Update docs only after implementation reflects reality. Make sure README clearly distinguishes:
- PDF text extraction
- candidate metric extraction
- verified normalized facts
- scoring
- investment recommendation eligibility

These are different stages and must not be conflated.

## 7. Non-negotiable safety rules

- Never invent a financial metric, period, unit, currency, or statement basis.
- Never treat a PDF excerpt as a verified metric just because text extraction succeeded.
- Never issue a positive `APPLY` / `AVOID` or other investment recommendation when critical evidence is missing, conflicting, or unverified.
- Keep `UNABLE_TO_ASSESS` as the safe outcome until all critical gates pass.
- A neutral default score such as 5/10 is not an acceptable substitute for missing evidence.
- Do not infer financial values from issuer names, news snippets, or unrelated documents.
- Keep production recommendations disabled until the verified evidence path is proven end-to-end.
- Do not enable demo analysis in production.
- Do not send real emails during tests or push-triggered validation runs.
- Do not enable WhatsApp or add credentials unless the owner explicitly requests it.
- Do not print, read aloud, commit, or expose `.env`, API keys, SMTP credentials, or repository secrets.
- Do not clear event ledgers or reset persisted notification state as a shortcut; this risks duplicate alerts.
- Never claim a workflow run proves email delivery; distinguish workflow success, provider acceptance, and actual delivery.
- Use branches and PRs for material changes; run CI and inspect failures before merging.
- Do not merge if CI fails or behavior is not understood. If a run is pending, report that honestly.

## 8. Automation and watchlist context

- GitHub Actions is the scheduled automation mechanism; no always-on server is required for scheduled jobs.
- Weekday checks are configured for 08:30, 11:30, 14:30, and 17:30 IST, with a daily digest on the final weekday run. Verify workflow files before changing times.
- Push-triggered scheduler/validation runs have real email disabled.
- SMTP email is the preferred notification channel when configured with repository secrets and an explicitly chosen recipient. WhatsApp is deferred.
- The public `state` branch stores sanitized watchlist/event state; avoid leaking secrets or personal information there.
- Current known watchlist:
  1. Reliance Industries Limited
  2. Tata Consultancy Services Limited (TCS)
  3. RNIT AI Solutions Limited — BSE scrip code 517286
  4. Clean Science and Technology Limited
  5. Godavari Biorefineries Limited
- For BSE entries, confirm `exchange: "BSE"`, the correct six-digit scrip code, official issuer name, and verified aliases in `state/watchlist.json`.
- Recent official RNIT BSE filing noted in prior work (verify it remains relevant before using): https://www.bseindia.com/xml-data/corpfiling/AttachLive/49b9896d-d588-4ccc-b828-48f17dc7e48b.pdf — unaudited financial results for quarter and half-year ended 2026-09-30 with limited review report.

## 9. Local development and test commands

Follow the repository's current README and CI workflow for exact setup. Common Windows commands documented by the project:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
.venv\Scripts\pytest.exe -v
```

Other documented CLI entry points include:

```powershell
python -m src.cli.main discover
python -m src.cli.main list
python -m src.cli.main analyze HEXAGON_TECH --format full
python -m src.cli.main results
python -m src.cli.digest
python -m src.cli.main health
python -m src.cli.main serve --port 8000
```

Check `--help` and current CLI code before relying on an example against the latest code.

## 10. GitHub working procedure for the next GPT

1. Fetch current `main` tree and the files relevant to the task.
2. Check open PRs, latest CI, and the current branch state; don't assume the context in this document is still the newest.
3. Make one cohesive change on a dedicated branch.
4. Add/update tests before claiming the change works.
5. Open a PR with a concise summary, safety implications, and known limitations.
6. Wait for GitHub Actions; inspect failed job logs and fix the cause.
7. Merge only when CI passes and the change is safe. If merge permissions or tools fail, leave the PR open and report the blocker.
8. After merge, verify the main branch and record the merge SHA and CI result in this file in a later handoff update.
9. Keep this `handoff.md` current as work progresses.

If using GitHub tools, discover the available tool schemas first rather than guessing arguments. Typical GitHub operations include fetching a file/tree, creating a branch, creating/updating a file, opening a PR, reading workflow checks/jobs/logs, and merging after successful validation.

## 11. Definition of done for production financial assessment

Do not call the project production-ready for real IPO recommendations until all of the following are true:

- Official issuer/prospectus documents are discovered and versioned.
- Candidate metrics preserve source provenance and page/table references.
- Period, currency, unit scale, and standalone/consolidated basis are explicit and validated.
- Critical facts are cross-checked and conflicts are detected.
- Required financial history is present and comparable.
- The complete production scoring path consumes only verified facts.
- Missing/conflicting/unverified inputs reliably produce `UNABLE_TO_ASSESS`.
- Real-source fixtures and end-to-end tests validate the behavior.
- Reports clearly explain missing evidence, sources, limitations, and why the assessment was gated.
- Scheduled automation and notification paths are tested without accidentally sending real alerts.
- Documentation and operational procedures match actual deployed behavior.

**Current status:** this definition of done is not yet met. Continue with Task A, then Tasks B and C. Do not jump straight to a heuristic parser or turn extracted text into scores.
