# Data Sources & Ingestion Hierarchy (`DATA_SOURCES.md`)

This document defines the data source classification tiers, scraping policies, conflict resolution logic, and provenance standards.

---

## 1. Source Hierarchy & Precedence

| Tier | Source Category | Examples | Authority Level | Precedence |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | Official / Authoritative | SEBI, NSE, BSE, Official Company Investor Relations, RHP / DRHP Prospectuses | Highest | 1 (Overrides Tier 2/3) |
| **Tier 2** | Reliable Financial Portals | Chittorgarh, IPOWatch, Screener, MoneyControl, Economic Times | High | 2 (Used for cross-checking & calendar feeds) |
| **Tier 3** | Market Sentiment & Commentary | IPO GMP Aggregators, YouTube Analyst Reviews, Community Sentiment | Sentiment Only | 3 (Never overrides fundamentals) |

---

## 2. Scraping & Ingestion Policies

1. **Polite Rate Limiting**: All web requests send clear `User-Agent` headers and enforce a minimum 2.0-second delay between successive calls.
2. **Exponential Backoff**: On HTTP 429 (Rate Limited) or 5xx server errors, the client waits $2^n$ seconds with random jitter before retrying (max 3 retries).
3. **Local Caching & Cryptographic Hashing**:
   - Ingested PDF documents are hashed using SHA-256 upon download.
   - If the remote document SHA-256 matches an existing version, redundant parsing is avoided.
4. **Document Version Management**:
   - Files are stored with version labels (`v1`, `v2`, `update_1`).
   - Successive versions (DRHP v1 → DRHP v2 → RHP) are compared by `DocumentDiffEngine` to isolate parameter and risk additions.

---

## 3. Conflict Resolution Engine

1. **Tier 1 vs Tier 2 Conflict**: Tier 1 value is automatically selected (e.g. NSE opening date takes precedence over a secondary portal). An explicit `SourceConflict` warning is logged in the audit trail.
2. **Critical Tier 1 Discrepancy**: If two Tier 1 sources disagree (e.g. NSE filing vs BSE filing on price band or opening dates), the system trips the hard assessment gate, sets confidence to `LOW`, and outputs `⚪ UNABLE TO ASSESS` until verified.
