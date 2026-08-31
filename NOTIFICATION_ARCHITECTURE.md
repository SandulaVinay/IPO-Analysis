# Notification Architecture & Dispatch Pipeline (`NOTIFICATION_ARCHITECTURE.md`)

This document details the multi-stage alert lifecycle, delivery tracking, and provider-agnostic fallback engine (`WhatsApp → Email → SMS → Console`).

---

## 1. Alert Schedule & Timing Hierarchy

All scheduling strictly respects **Indian Standard Time (`Asia/Kolkata`)** and the NSE/BSE market trading holidays calendar:

1. **Target T-2 Alert (09:00 IST, 2 Calendar Days Prior to Opening)**:
   - Contains executive summary, price band, lot size, fresh vs OFS split, key positives/risks, and YouTube analyst links.
   - If verified information becomes available after T-2, the alert is **dispatched immediately**.
2. **6-Hour Follow-Up Reminder (6 Hours post T-2 Alert)**:
   - Sent through secondary channel to ensure visibility without duplicate spam.
3. **Day-Before Reminder (T-1, 10:00 IST)**:
   - Concise summary with price band, lot size, minimum investment, and current GMP signal.
4. **IPO Opened Alert (Opening Day, 09:30 IST)**:
   - Application window open alert with real-time bidding category updates.

---

## 2. Multi-Channel Fallback Flow

```
Trigger Alert Event
       ↓
Check Idempotency Key (Skip if already dispatched)
       ↓
Primary Channel: WhatsApp (Cloud API / Twilio)
       ├── SUCCESS ──> Mark DELIVERED & End
       └── FAILED / UNCONFIGURED
              ↓
Secondary Channel: Email (SMTP / Resend)
       ├── SUCCESS ──> Mark DELIVERED & End
       └── FAILED / UNCONFIGURED
              ↓
Backup Channel: SMS / Webhook / Console
       ├── SUCCESS ──> Mark DELIVERED & End
       └── FAILED ──> Log Error in Audit Trail
```

---

## 3. Idempotency & Delivery Guarantees

- **Idempotency Keys**: Formatted as `{ALERT_TYPE}_{SYMBOL}_{VERIFIED_OPEN_DATE}` (e.g. `T2_HEXAGON_TECH_2026-09-18`).
- Running discovery or scheduler multiple times will **never** send duplicate alerts.
- Every attempt is logged in `notification_attempts` with timestamp, provider message ID, and error payloads.
