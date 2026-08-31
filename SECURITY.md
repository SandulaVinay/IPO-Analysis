# Security, Privacy & Secret Management (`SECURITY.md`)

This document outlines the security architecture, credential management, logging sanitization, and data privacy policies.

---

## 1. Secret & Credential Isolation

- **No Hard-Coded Secrets**: API tokens, database passwords, SMTP credentials, and WhatsApp keys are strictly loaded from environment variables using `pydantic-settings`.
- **`.env` Exclusion**: `.env` and all credential keys are permanently included in `.gitignore`.
- **Template Provisioning**: Complete configuration documentation is provided via `.env.example`.

---

## 2. Log Redaction & Sanitization

The system implements `RedactingFormatter` (`src/common/logging.py`) which automatically scans log records and redacts sensitive patterns:
- `Bearer <token>` → `Bearer [REDACTED]`
- `password=...` → `password=[REDACTED]`
- `token=...` → `token=[REDACTED]`
- `key=...` → `key=[REDACTED]`

---

## 3. Investor Privacy & Decision-Support Isolation

1. **No Personal Financial Data Stored**: The system does not ingest or store personal bank details, Demat account credentials, or trading credentials.
2. **Decision-Support Boundary**: The platform functions exclusively as an intelligence and decision-support tool; it contains no trading execution or transaction interfaces.
