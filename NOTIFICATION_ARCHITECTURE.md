# Notification Architecture & Current Deployment Behavior

This document describes the notification paths that are implemented in the deployed `main` branch. It intentionally distinguishes scheduled behavior from reminder features that are not yet connected to the GitHub Actions workflow.

## 1. Scheduled events

The GitHub Actions workflow runs official-source checks on weekdays at approximately:

| India time | Job |
|---|---|
| 08:30 | IPO discovery, financial-results monitor, health checks |
| 11:30 | IPO discovery, financial-results monitor, health checks |
| 14:30 | IPO discovery, financial-results monitor, health checks |
| 17:30 | IPO discovery, financial-results monitor, health checks, daily IPO digest |

GitHub may delay scheduled runs. The workflow is designed for repeatable, at-least-once execution, not exact-time delivery.

The financial-results monitor checks the public `state/watchlist.json` list. NSE entries use an NSE symbol and the official NSE corporate financial-results JSON feed (quarterly and annual metadata). BSE entries must also include `exchange: \"BSE\"` and a six-digit `bse_scrip_code`, and are checked through BSE's announcement API. All entries require an exact official issuer name (plus verified aliases where required).

## 2. Current notification chain

Only two real channels are part of the production workflow:

1. **WhatsApp Cloud API** — primary channel, only when explicitly enabled and configured.
2. **SMTP email** — fallback when WhatsApp is disabled, unconfigured, or rejected. Gmail uses STARTTLS on port 587 by default and retries implicit TLS on port 465 if the connection/handshake fails before message submission.

A successful provider API response means the provider accepted the request. It does not prove that the message reached the user's handset or inbox. Final delivery requires provider delivery-status evidence, which is not currently wired into this project.

If both channels are disabled or unconfigured, reports are still generated and uploaded as GitHub Actions artifacts. The system must not log or report that a notification was sent. Gmail app-password whitespace is normalized before SMTP authentication; both STARTTLS/587 and implicit TLS/465 are attempted when appropriate.

WhatsApp use, template requirements, eligibility and charges depend on Meta/provider terms. Do not assume it is free. Gmail SMTP generally requires an app password rather than an account password.

## 3. Idempotency and recovery

- Stable event keys prevent the same accepted event from being notified repeatedly.
- Failed notification events remain eligible for a later retry.
- Public state stores only sanitized event keys, event type, public symbol, event date, status and channel.
- Recipient phone numbers, email addresses, tokens and message bodies must never be written to the public state branch.
- State JSON is written through temporary files and atomic replacement.
- The workflow serializes state-writing runs with a concurrency group.
- Reports are uploaded as seven-day GitHub Actions artifacts.

## 4. Not yet enabled

The code contains notification methods for T-2, six-hour and T-1 alerts, but the scheduled GitHub Actions workflow does not currently invoke these methods as an automated lifecycle. IPO-opened alerts and listing-day market-price monitoring are also not part of the current scheduled workflow.

Do not describe these reminders as deployed until their triggers, schedule, verified input gates, deduplication and end-to-end tests are connected.

## 5. Required GitHub Actions secrets

Add these in **Repository → Settings → Secrets and variables → Actions**. Never paste secret values into chat, source files, issues or logs.

| Secret | Purpose |
|---|---|
| `ENABLE_WHATSAPP` | Set to `true` only after WhatsApp is ready |
| `WHATSAPP_PHONE_NUMBER_ID` | Meta Cloud API phone-number ID |
| `WHATSAPP_ACCESS_TOKEN` | Meta access token |
| `WHATSAPP_RECIPIENT_PHONE` | Opted-in recipient in international format |
| `ENABLE_EMAIL` | Set to `true` only after SMTP is ready |
| `SMTP_USER` | SMTP account |
| `SMTP_PASSWORD` | SMTP app password / credential |
| `EMAIL_FROM` | Sender address |
| `EMAIL_TO` | Recipient address |

After adding secrets, enable one channel and run a manually approved test. Confirm provider acceptance from the workflow result; do not treat acceptance as final handset delivery.

## 6. Investment-safety rule

The production IPO-analysis path remains fail-closed. Prospectus passages are candidate evidence and have not yet been fully reconciled for financial period, units, restatement, and consolidated-versus-standalone basis. Until those verification steps are implemented and tested, the system must issue `UNABLE_TO_ASSESS` instead of `APPLY`, `AVOID`, or a buy/sell recommendation.
