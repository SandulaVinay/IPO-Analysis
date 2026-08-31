# Relational Data Model Specification (`DATA_MODEL.md`)

This document outlines the normalized relational database schema (24 core tables) used for storing IPOs, evidence, calculations, forensic runs, alerts, and performance outcomes.

---

## 1. Entity-Relationship Overview

```
[ipos]
  ├── (1:N) ──> [ipo_events] (Lifecycle State Transitions)
  ├── (1:N) ──> [ipo_documents] ── (1:N) ──> [document_versions] (SHA256 Files)
  ├── (1:N) ──> [facts] (Atomic Provenance-Linked Facts)
  ├── (1:N) ──> [calculations] (Deterministic Programmatic Math)
  ├── (1:N) ──> [financial_periods] (P&L, Balance Sheet, Cash Flow Ratios)
  ├── (1:N) ──> [peers] (Comparable Listed Companies)
  ├── (1:N) ──> [risks] (Quantified Risks & Page Citations)
  ├── (1:N) ──> [valuations] (Post-IPO Multiples & Dilution)
  ├── (1:N) ──> [gmp_snapshots] (Grey Market Premium Time-Series)
  ├── (1:N) ──> [subscription_snapshots] (Day 1/2/3 Bidding Demand)
  ├── (1:N) ──> [anchor_investors] (Anchor Book Quality & Lock-in)
  ├── (1:N) ──> [analysis_runs]
  │               ├── (1:N) ──> [analysis_snapshots] (Point-in-Time Frozen State)
  │               └── (1:1) ──> [recommendations] ── (1:N) ──> [recommendation_reasons]
  ├── (1:N) ──> [alerts]
  │               └── (1:N) ──> [notifications] ── (1:N) ──> [notification_attempts]
  ├── (1:N) ──> [youtube_videos] (Curated Video Research)
  └── (1:1) ──> [performance_outcomes] (Post-Listing Actuals & Error Calibration)

[sources] (Authoritative Source Registry)
[audit_log] (Immutable System Audit Trail)
```

---

## 2. Table Schemas & Foreign Keys

### `ipos`
- `id` (INT PK Auto-increment)
- `symbol` (VARCHAR(50) UNIQUE INDEX)
- `company_name` (VARCHAR(255) INDEX)
- `industry` (VARCHAR(100))
- `issue_type` (VARCHAR(50) Default 'MAINBOARD')
- `status` (VARCHAR(50) INDEX)
- `verified_open_date` (DATE INDEX), `verified_close_date` (DATE)
- `min_price` (FLOAT), `max_price` (FLOAT), `lot_size` (INT), `min_investment` (FLOAT)
- `issue_size_cr` (FLOAT), `fresh_issue_cr` (FLOAT), `ofs_cr` (FLOAT)

### `facts`
- `id` (INT PK)
- `ipo_id` (INT FK -> `ipos.id` INDEX)
- `field_name` (VARCHAR(100) INDEX)
- `value_text` (TEXT), `value_numeric` (FLOAT), `value_type` (VARCHAR(50))
- `source_name` (VARCHAR(100)), `source_url` (TEXT), `source_tier` (VARCHAR(20))
- `document_id` (INT), `document_version` (VARCHAR(50)), `page_number` (INT)
- `confidence` (VARCHAR(20)), `verification_status` (VARCHAR(20))

### `calculations`
- `id` (INT PK)
- `ipo_id` (INT FK -> `ipos.id` INDEX)
- `calculation_name` (VARCHAR(100) INDEX)
- `result_numeric` (FLOAT), `result_text` (TEXT)
- `formula` (TEXT), `input_fact_ids` (JSON)

### `analysis_runs` & `analysis_snapshots`
- Complete immutability: each analysis execution produces a new run ID and an immutable snapshot of all metrics, formulas, and weights used.
- History is never rewritten when post-listing actuals arrive.
