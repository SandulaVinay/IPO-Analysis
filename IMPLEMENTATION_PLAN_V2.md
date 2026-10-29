# IPO-Analysis Automation v2 — Implementation Blueprint

## Status

This blueprint is being implemented on the `automation-v2` branch. The `main` branch is not changed by this work. Do not enable live notifications until the verification and test gates below pass.

## Audit findings from the current repository

1. `.github/workflows/ipo_scheduler.yml` runs `discover` and `health`; it does not run a full analyze/report/dispatch cycle.
2. The scheduled workflow uses a GitHub-hosted runner and the default SQLite path `./ipo_system.db`. That file is ephemeral between runs unless explicitly restored and persisted.
3. `src/ingestion/scrapers.py` currently returns a hard-coded sample IPO and sample GMP/subscription values rather than verified live data.
4. `src/web/app.py` currently feeds hard-coded sample financial periods and company characteristics into analysis. These can produce plausible-looking but unsupported recommendations.
5. `src/notifications/whatsapp.py` does not send a Cloud API POST request; it explicitly returns failure. Real WhatsApp delivery is therefore not implemented yet.
6. `src/monitoring/health.py` currently reports several subsystems as operational without checking their actual source/provider readiness.
7. `requirements.txt` does not explicitly declare `greenlet`, although SQLAlchemy's async extension can require it.
8. The repository contains existing scoring, provenance, notification, and resilience specifications. Reuse them, but verify implementation against the docs rather than assuming documentation means a feature is live.

## Target architecture

- **Execution:** GitHub Actions only; weekday source checks every few hours, daily digest, and manual recovery/test runs. Scheduled jobs are treated as at-least-once, not exact-time execution.
- **Source of truth:** official SEBI, NSE, BSE, issuer investor-relations pages and offer documents take precedence. Secondary portals may discover candidates but cannot establish critical facts by themselves.
- **Evidence-first ingestion:** every extracted fact carries source URL, retrieval time, document hash/version where applicable, and a verification state. Invalid or conflicting critical facts are quarantined.
- **Deterministic analysis:** formulas and score calculations remain Python code. Missing evidence produces `UNABLE_TO_ASSESS`; no synthetic financial values may enter production analysis.
- **State:** a dedicated public state branch may contain only sanitized, non-personal operational JSON (schema version, public IPO identifiers/events, source cursors, processed event IDs, run metadata). No phone numbers, email addresses, credentials, message bodies, or recipient-specific state may be stored there.
- **Notifications:** WhatsApp primary, email fallback. Each channel reports whether a provider accepted the message; provider acceptance must not be described as confirmed end-user delivery unless a delivery-status callback confirms it.
- **Secrets:** all tokens, SMTP credentials, recipient phone number, and recipient email are GitHub Actions Secrets. Never commit or print them.
- **Reports:** generate Markdown and PDF reports as run artifacts with short retention. Public state stores report hashes/links only when safe; no personal recipient data.
- **Recovery:** retries with bounded exponential backoff, idempotency keys, checkpoints, atomic state updates, workflow concurrency control, and a manual replay path.
- **Observability:** structured logs with redaction; health checks report source freshness and provider configuration truthfully; a failed pipeline must exit non-zero.

## State-branch contract (proposed)

```text
state/
  schema_version.json
  ipo_registry.json
  source_cursors.json
  processed_events.json
  notification_outbox.json
  run_history.json
```

State records must be schema-versioned, size-bounded, validated before write, and updated atomically. Do not put personal recipient information or full notification bodies in these files. Because this branch is public, assume every byte stored there can be read by anyone.

## Notification behavior

1. Build a notification event only after the source/data-quality gate passes.
2. Derive a stable idempotency key from event type, IPO symbol/identifier, and verified event date/version.
3. Attempt WhatsApp only when its official provider is configured and the recipient is opted in.
4. On a confirmed provider failure, try email; never mark a console/mock attempt as delivered.
5. Store sanitized attempt status and provider error category, not tokens or recipient details.
6. If both channels fail, keep the event retryable and fail the workflow visibly.

## Required secret names

- `ENABLE_WHATSAPP`
- `WHATSAPP_PROVIDER` (initially `cloud_api` only after configured)
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_RECIPIENT_PHONE`
- `ENABLE_EMAIL`
- `SMTP_USER`
- `SMTP_PASSWORD` (an email-provider app password, never the normal account password)
- `EMAIL_FROM`
- `EMAIL_TO`

These must be added through GitHub repository Settings → Secrets and variables → Actions. The repository integration used for code changes does not provide a safe way to set these secret values on the user's behalf.

## Delivery and safety gates

- A clean CI run must pass before a workflow is enabled for scheduled production delivery.
- Unit tests cover source normalization, evidence gates, scoring, state validation, idempotency, and provider fallback.
- Integration tests use fake HTTP/provider adapters and never send real messages.
- A production analysis cannot use demo fixtures, hard-coded financials, or unverified secondary-source data as facts.
- The system must never emit `ATTRACTIVE`, `AVOID`, or `APPLY` from missing/conflicting critical inputs.
- Notification tests are manual and clearly labelled; normal CI does not send messages.
- Every scheduled run must be safe to repeat without duplicate notifications.
- No secret or personal contact detail may appear in commits, artifacts, logs, or public state.

## Implementation phases

1. **Audit and containment:** preserve the current branch; add CI; fix dependency declarations; disable fake data from production paths.
2. **Persistence and execution:** restore/write sanitized state branch data, concurrency lock, atomic state updates, bounded retries, run history and recovery.
3. **Source adapters:** implement official-source adapters with source-level tests; secondary portals only discover candidates.
4. **Analysis and reports:** connect verified evidence to deterministic calculations; mark unsupported metrics as unavailable; generate report artifacts.
5. **Notifications:** implement actual WhatsApp Cloud API POST with strict configuration validation and email fallback; test with mocked providers.
6. **Schedule and acceptance:** weekday monitoring, daily summary, manual replay, failure alerts, end-to-end tests, and documentation.

## Current rollout status

The repository audit identified critical blockers in live source ingestion, production analysis inputs, WhatsApp delivery, and persistent state. The automation must remain in safe/test mode until those blockers are fixed and CI verifies the end-to-end path.
