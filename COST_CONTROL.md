# Cost Control & Zero-Cost Architecture (`COST_CONTROL.md`)

This document details how the system achieves **zero mandatory recurring infrastructure cost** through free-tier cloud allowances and local open-source components.

---

## 1. Zero-Cost Resource Allocation Matrix

| Component | Architecture Choice | Free Allowance | Expected Usage | Monthly Cost | Fallback if Pricing Changes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Compute** | GitHub Actions / Local | 2,000 mins/mo (GHA) | ~400 mins/mo | **$0.00** | Run locally via Windows Task Scheduler / Cron |
| **Database** | Asynchronous SQLite | Unlimited local disk | ~50 MB storage | **$0.00** | Supabase free 500MB tier |
| **Document Parser** | `pdfplumber` + `pypdf` | Open Source (Local CPU) | Unlimited | **$0.00** | Pure Python standard extraction |
| **Email Delivery** | SMTP (Gmail/Brevo) | 300 emails/day | ~50 emails/mo | **$0.00** | Local console logs & Markdown exports |
| **WhatsApp** | Meta Cloud API / Sandbox | 1,000 service convos/mo | ~80 alerts/mo | **$0.00** | Fallback to Email & Web Dashboard |
| **YouTube Research** | YouTube v3 Data API | 10,000 units/day | ~500 units/day | **$0.00** | Web search / RSS fallback |
| **Market Data** | Public Exchange Feeds | 100% Free Public Filings | Respectful rate limits | **$0.00** | Public registrar feeds (Link Intime, KFintech) |

---

## 2. LLM Cost Optimization

- **Zero LLM Dependency for Calculations**: All CAGRs, ratios, margins, multiples, dilution, and listing gains are calculated deterministically in Python.
- **Section-Targeted Parsing**: Only relevant extracted tables and risk sections are parsed locally.
- **Result Caching**: Completed analyses and YouTube search results are cached in the database; unchanged documents are never re-processed.
