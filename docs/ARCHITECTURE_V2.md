# IPO-Analysis Automation v2 — Architecture and Rollout Gates

## Purpose

A low-cost, scheduled Indian IPO and listed-company research assistant. GitHub Actions runs the jobs; Python performs deterministic calculations; official exchange/company filings are the source of truth; SMTP email is the preferred supported alert channel, while WhatsApp is deferred.

This document describes the intended architecture and the implementation status. A feature is not production-ready merely because a module exists: it must pass tests and source-level validation.

## Operating principles

1. **Evidence before conclusions.** Every factual output must link to the official source and preserve the capture time/document identity where available.
2. **Fail closed.** Missing, stale, conflicting, or unsupported data produces `UNABLE_TO_ASSESS` or `UNAVAILABLE`, not a guessed recommendation.
3. **Separate decisions.** IPO fundamentals, issue valuation, listing-day risk, and longer-term suitability are different assessments. GMP is unofficial sentiment and must never be presented as an official fact.
4. **Deterministic calculations.** Financial ratios and score arithmetic run in tested Python code. Optional AI may explain already-verified results, but cannot fill missing data or alter numeric calculations.
5. **Idempotent scheduled work.** A repeated GitHub Actions run should not send duplicate alerts for an event already accepted by a provider.
6. **No secrets in source control.** Credentials and notification recipients belong in GitHub Actions Secrets, never in this public repository or the public state branch.
7. **Transparent status.** Provider acceptance is not proof of handset delivery or inbox placement.

## Runtime architecture

```text
GitHub Actions (weekday schedule + manual dispatch)
        |
        +--> official NSE/BSE IPO discovery
        |       |
        |       +--> normalize and compare exchange evidence
        |       +--> clear verified dates on source conflict
        |       +--> persist sanitized IPO registry
        |
        +--> official financial-results filing monitor
        |       |
        |       +--> exact issuer-name matching against watchlist
        |       +--> record period, submission, audit, consolidation metadata
        |       +--> extract supported XBRL metrics only
        |       +--> write Markdown report artifact
        |
        +--> SMTP email (preferred; explicitly enabled only)\n        |\n        +--> WhatsApp (deferred; disabled by default)
        |
        +--> health checks, CI tests, sanitized state commit
                |
                +--> public `state` branch
```

## State and privacy

The `state` branch is public. It may contain only public issuer symbols/names, public IPO metadata, hashed event keys, run statuses, and source/report references. Do not store phone numbers, email addresses, API tokens, private notes, or message bodies there.

State files currently use schema version 1:

- `state/watchlist.json`: companies to monitor for financial-results filings.
- `state/ipo_registry.json`: sanitized IPO discovery registry.
- `state/processed_events.json`: event keys already accepted for notification.
- `state/notification_outbox.json`: sanitized notification status and channel metadata.
- `state/run_history.json`: bounded operational run history.
- `state/schema_version.json`: state-schema marker.

Example watchlist entry (use the exact issuer name displayed on the NSE filing page; add aliases only when you have verified them):

```json
{
  "schema_version": 1,
  "companies": [
    {
      "symbol": "RELIANCE",
      "company_name": "Reliance Industries Limited",
      "company_name_aliases": ["Reliance Industries Ltd"]
    }
  ]
}
```

**Important:** the results page can present many issuers in one table. The monitor must filter to the configured exact company name/verified aliases. A symbol alone is not sufficient to prove that a page row belongs to that issuer. If the name is missing or cannot be matched, the monitor skips that symbol and records a degraded/partial run rather than sending a potentially misattributed alert.

## Financial-results workflow

1. For NSE watchlist entries, use the official NSE `corporates-financial-results` JSON feed for quarterly and annual metadata with a cookie-bearing HTTP session. For BSE entries, query the official BSE announcement API by the configured six-digit scrip code.
2. Parse only recognized JSON announcement rows; retain the official source URL and any official attachment URL.
3. Match each row to the configured issuer name/aliases and, for BSE, require the exact scrip code.
4. Prefer the latest period end available for that issuer and prefer consolidated results when present. Preserve audit status, cumulative status, period type, submission type, and broadcast time.
5. If an XBRL instance is linked and matches supported tags/contexts/units, extract only supported revenue, PAT, EPS, and operating cash-flow facts. Compare current and prior-year matching periods when both are present.
6. If the attachment is PDF/unsupported XBRL or the period/unit mapping is ambiguous, report the filing but label metrics unavailable. Do not infer a verdict.
7. Write a Markdown report as a short-lived GitHub Actions artifact. Do not commit generated reports or issuer financial statements to the public state branch.
8. Attempt SMTP email first only when explicitly enabled and configured. WhatsApp remains deferred unless its rollout is explicitly approved and configured. Record provider acceptance, not assumed final delivery. A failed notification remains eligible for retry.

The BSE adapter currently detects and reports official result-announcement metadata; it does not yet extract financial metrics from BSE attachments. The NSE XBRL extractor is deliberately conservative and currently supports only a subset of tags and period contexts. It is **not** a general-purpose parser for every Indian GAAP/Ind AS filing. A reported metric must be checked against the source filing before it is used in an investment decision.

## IPO analysis workflow

The current production analysis path must remain fail-closed until a verified RHP/DRHP ingestion pipeline is connected. That pipeline still needs:

- Official prospectus discovery and document version/hash tracking.
- Safe PDF/XBRL extraction with page/section provenance.
- Verification of revenue, profit, debt, cash flow, EPS, share count, issue size, fresh issue/OFS split, price band, and peer valuation.
- Reconciliation of consolidated vs standalone values and restated financial periods.
- Data completeness and conflict gates.
- Versioned deterministic formulas with regression fixtures and explainable component scores.
- Separate fundamental, valuation, listing-risk, and long-term assessments.

Until these gates pass, no automated `APPLY`, `AVOID`, or buy/sell conclusion should be emitted from incomplete inputs.

## Scheduling and recovery

- The workflow runs at 08:30, 11:30, 14:30, and 17:30 India Standard Time on weekdays (GitHub cron uses UTC). The daily IPO digest runs on the final weekday cycle and on manual dispatch.
- GitHub scheduled runs may be delayed or skipped during platform load. Treat schedules as at-least-once, not exact-time execution.
- Workflow concurrency prevents two scheduler runs from writing the same state branch simultaneously.
- A failed source request must be visible in run status/logs. It must not be recorded as a successful full check.
- Reports are retained as GitHub Actions artifacts for seven days.
- Keep a manual `workflow_dispatch` path for recovery.

## Notification secrets

Set only when ready to test real delivery. Use GitHub repository **Settings → Secrets and variables → Actions**. Never paste secret values into issues, commits, logs, or this chat.

- `ENABLE_WHATSAPP` — `true` only after Cloud API setup is verified.
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_RECIPIENT_PHONE` — international digits with country code.
- `ENABLE_EMAIL` — `true` only after SMTP is verified.
- `SMTP_USER`
- `SMTP_PASSWORD` — use an app password if the provider requires it.
- `EMAIL_FROM`
- `EMAIL_TO`

WhatsApp availability, template requirements, and charges depend on Meta/provider terms and the account. Do not assume WhatsApp delivery is always free. Email fallback is also subject to provider limits.

## Validation checklist before enabling live alerts

- [ ] Latest CI passes on the exact PR head.
- [ ] Official NSE/BSE source adapters have been tested against live page responses and fixtures.
- [ ] No row can be attributed to a symbol without verified issuer-name matching.
- [ ] XBRL facts match the correct issuer, statement basis, period, duration, units, and reported values.
- [ ] Unsupported/missing values result in `UNAVAILABLE` / `UNABLE_TO_ASSESS`.
- [ ] Re-running the same fixture/run does not create duplicate notifications.
- [ ] WhatsApp acceptance and failure fallback are tested with non-sensitive test content.
- [ ] State-branch persistence works on successful and failed workflow paths.
- [ ] No recipient data, secrets, raw private messages, or financial report artifacts are committed.
- [ ] Live delivery is manually enabled only after the user configures secrets and approves a test.

## Current status (do not overstate)

- Implemented on `automation-v2`: official IPO-page parsing, source-date conflict handling, CI, sanitized state persistence, WhatsApp Cloud API adapter, a watchlist-based results monitor with conservative XBRL extraction, and prospectus PDF validation with page-cited candidate evidence stored as explicitly UNVERIFIED facts.
- Recent work added exact issuer-name filtering and preservation of cumulative/submission metadata.
- Still incomplete: comprehensive/live-validated RHP/DRHP link coverage, table-aware financial statement extraction and period reconciliation, a verification/reconciliation workflow for candidate facts, full production IPO scoring from verified documents, broad XBRL/PDF financial-results coverage, and a fully validated live-source scheduled run.
- The automation code is deployed on `main`; live source coverage and end-to-end notification checks remain subject to scheduled-run verification. Production investment recommendations remain disabled until the financial verification checklist is satisfied.


## Prospectus ingestion update

The discovery parser now looks for links labeled as RHP, DRHP, prospectus, addendum, corrigendum, or price-band advertisement within official IPO issue rows. When such a link is present, the discovery cycle attempts HTTPS PDF ingestion. Invalid or unavailable documents are skipped without creating placeholders. A validated PDF is hashed, deduplicated by content, versioned immutably, and scanned for page-cited candidate passages. Candidate facts are stored as `UNVERIFIED` with low confidence and never feed the production scoring engine. A review-only Markdown report is uploaded as a seven-day GitHub Actions artifact.

This is an initial adapter, not proof of complete prospectus coverage. NSE/BSE page layouts and linked PDF hosting must still be validated against live cases. Revised documents at a different URL are versioned; if an exchange overwrites the same URL in place, the current source-URL cache may defer detection until the link changes or a manual refresh is added.


## Daily IPO digest

The scheduler's final weekday run (17:30 IST) and manual dispatch now invoke `python -m src.cli.digest`. It produces a Markdown artifact listing future-dated or source-conflict IPO records, links to the official NSE/BSE issue pages, and explicitly labels each item `UNABLE_TO_ASSESS` until verified RHP/DRHP financial data is available. It includes the last discovery-run status and warns when the report is based on cached state. It sends WhatsApp first and email fallback only when the corresponding settings/secrets are configured. With both channels disabled, the report is created in report-only mode and no delivery is claimed.


## PDF reports and email attachments

Daily IPO status, supported financial-results filing reports, and prospectus evidence reports are rendered to both Markdown and PDF. PDFs are uploaded as short-lived GitHub Actions artifacts. When email fallback is enabled, the daily digest and results monitor attach the corresponding PDF, restricted to existing PDF files inside the generated `reports/` directory with a 10 MB total attachment limit. WhatsApp sends the PDF as a document with a short caption when available; the caption also links to the workflow run for artifact access.


## Source coverage status

The IPO discovery adapter now distinguishes a recognized-but-empty official issue table from an unrecognized page layout. If both exchange layouts are unrecognized or both requests fail, discovery fails instead of reporting success. If one source remains usable while another fails or changes layout, the run is recorded as `PARTIAL`; the daily digest warns that cached state may be stale or incomplete.


When a generated PDF exists, the WhatsApp adapter now uploads it through the Cloud API media endpoint and sends a document message with a short caption. The attachment must be a valid PDF inside the generated `reports/` directory and remain under 10 MB. If upload or document delivery is rejected, the email fallback receives the PDF attachment instead.


The completeness engine now counts only explicit verified date fields and provenance-bearing facts marked `VERIFIED`; non-null but unverified numeric IPO fields no longer inflate completeness or confidence. A zero count of verified sources remains zero rather than being reported as one.


## Persistent prospectus registry

The public state branch now stores only prospectus metadata (symbol, sanitized source URL, URL hash, document SHA-256, version label, page count, extraction counts, and timestamps). It deliberately does not store candidate text or notification content. The same source URL is rechecked at least daily; unchanged content retains its version, while a changed PDF gets a new version label. New content generates a page-cited Markdown/PDF review artifact and a WhatsApp document alert with email fallback. URL query parameters that look like tokens or signatures are removed from public metadata and reports.


## Prospectus table candidates

The PDF extractor now supplements linear page text with best-effort table-row extraction on pages containing financial labels. It retains the row's header context and cell values as a page-cited `TABLE_ROW_CANDIDATE`; it does not map values to years, infer units, or mark any numeric fact verified. Period/basis/unit reconciliation remains a separate production gate.
