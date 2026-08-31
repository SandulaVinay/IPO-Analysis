# Failure Handling & Resilience Guide (`FAILURE_HANDLING.md`)

This document outlines how the system gracefully handles external failures, stale data, network outages, and parsing issues.

---

## 1. External System Failure Handling

| Failure Scenario | System Response & Mitigation |
| :--- | :--- |
| **Exchange Website / Portal Down** | Uses cached snapshot if within freshness threshold; marks data `STALE`; logs warning without crashing. |
| **HTTP 429 (Rate Limited)** | Automatically triggers exponential backoff with jitter up to 3 retries. |
| **Malformed / Corrupted PDF** | Flags document status as `PARSING_FAILED`; falls back to structured portal metadata; lowers confidence score. |
| **Source Discrepancy** | `SourceConflictEngine` flags conflict; applies Tier-1 precedence; trips safety gate if critical Tier-1 disagreement. |
| **WhatsApp Provider Failure** | Seamlessly triggers fallback sequence: `WhatsApp → Email → SMS → Console`. |
| **Database Connection Failure** | Retries transaction with rollback; emits critical alert. |

---

## 2. Stale Data Handling

- **IPO Dates**: Refreshed on every discovery cycle (every 4 hours).
- **GMP**: Captured in point-in-time snapshots with explicit capture timestamps.
- **Subscription**: Monitored on active bidding days (Day 1, 2, 3).
- **Safe Fallback**: If a data point exceeds its freshness policy, it is marked `STALE` and the confidence level is downgraded.
