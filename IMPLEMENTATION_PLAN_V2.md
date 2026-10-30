# IPO-Analysis Automation v2 — Implementation and Deployment Status

## Current deployment target

The project uses GitHub Actions only for scheduled execution. It stores sanitized operational state on the public `state` branch, generates reports as short-lived workflow artifacts, and uses WhatsApp Cloud API first with SMTP email fallback when the owner configures the required secrets.

The `main` branch is kept separate from the `automation-v2` implementation branch until code review, CI and deployment checks pass.

## Implemented on `automation-v2`

- Python application modules for IPO discovery, financial-results monitoring, PDF ingestion/evidence capture, state persistence, reporting and notifications.
- Official NSE/BSE IPO public-issue page adapters with recognized-layout checks and source-conflict handling. A source outage or page-layout change is reported as partial/degraded rather than silently treated as complete coverage.
- Prospectus PDF validation, SHA-256 hashing, immutable document-version metadata, and page-cited candidate passages. Extracted passages remain explicitly `UNVERIFIED`.
- Watchlist-based NSE corporate-results filing monitor. The monitor requires an exact official company-name match, extracts only a conservative subset of XBRL facts, and labels unsupported/ambiguous metrics unavailable.
- Production analysis safety gate: missing or unverified issuer financial facts produce `UNABLE_TO_ASSESS`; demo financial inputs are not permitted in production.
- Daily Markdown/PDF IPO status digest and financial-results/prospectus review reports.
- WhatsApp Cloud API and SMTP provider adapters, WhatsApp-first/email-fallback behavior, and provider-acceptance tracking.
- Sanitized public state branch with schema version, IPO registry, document metadata, source cursors, processed event keys, notification outbox, run history and a watchlist file.
- GitHub Actions weekday schedule, manual recovery entry point, state persistence, report artifacts, and CI tests.
- Explicit `greenlet` and PDF-generation dependencies.

## Verification completed

On 2026-10-30, the CI workflow on the `automation-v2` branch completed successfully after fixing PDF table-evidence extraction fallback. The successful runs compiled the Python modules and passed all 72 automated tests.

CI success is a code-level gate only. It does not prove that live NSE/BSE pages will always retain their current layout, that an issuer's filing is complete, or that a configured messaging provider has accepted a real message.

## Current scheduled behavior

The GitHub Actions workflow checks IPO discovery, the configured company-results watchlist and subsystem health four times per weekday (08:30, 11:30, 14:30 and 17:30 IST). The final weekday run also generates the daily IPO digest. The workflow uploads report artifacts and commits only sanitized JSON state to the public `state` branch.

It does not currently run an automated T-2 / six-hour / T-1 / IPO-opened alert lifecycle. The embedded APScheduler is disabled by default because the agreed deployment model is GitHub Actions, not a permanently running web server.

## Remaining production gates

1. **Company watchlist:** `state/watchlist.json` is empty. The owner must add each NSE symbol, its exact official company name and verified aliases. This branch is public; the list must contain only information the owner is comfortable exposing.
2. **Notification credentials:** the owner must configure GitHub Actions secrets for WhatsApp and/or SMTP. Without secrets, the system remains in report-only mode. WhatsApp costs and eligibility depend on the provider/Meta account.
3. **Live source validation:** verify NSE/BSE page layouts against live responses and keep parser fixtures current. GitHub Actions scheduled runs can be delayed.
4. **IPO financial verification:** complete table-aware prospectus extraction, financial-period and unit mapping, restated-period handling, consolidated/standalone reconciliation, and issuer-fact verification.
5. **Results coverage:** expand beyond the current conservative NSE/XBRL subset; unsupported PDF/XBRL layouts must remain unavailable rather than guessed.
6. **Live notification test:** after secrets are configured, approve a non-sensitive test and verify provider acceptance and email fallback behavior.
7. **Post-merge scheduled run:** verify at least one real scheduled workflow on `main`, including state-branch persistence and expected report artifacts.

## Safety and cost boundaries

- Do not enable `ENABLE_DEMO_ANALYSIS` in production.
- Do not issue `APPLY`, `AVOID`, or buy/sell conclusions until prospectus facts are verified and the deterministic analysis pipeline consumes those verified facts.
- Never store phone numbers, email addresses, credentials, access tokens, private message text or financial statements in the public state branch.
- GitHub-hosted Actions and open-source Python libraries avoid a separate server and mandatory AI API. GitHub quotas, SMTP provider limits, and WhatsApp provider charges/eligibility still apply.
- A provider's accepted response is not proof that the person received the message.
