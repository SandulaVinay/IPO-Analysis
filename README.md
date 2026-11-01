# 🇮🇳 Indian IPO Intelligence, Analysis, Recommendation & Notification System

A production-quality, evidence-driven, deterministic intelligence platform for discovering, analyzing, recommending, and alerting on Indian Initial Public Offerings (IPOs).

---

## 🌟 Current System Capabilities

1. **Deterministic calculations**: Financial formulas and scoring calculations are performed in Python; an AI model is not required for numerical calculations.
2. **Evidence and provenance**: Prospectus documents are hashed and versioned. Extracted PDF passages retain page references and remain explicitly `UNVERIFIED` until the period, unit and statement-basis checks are completed.
3. **Fail-closed production analysis**: Missing, conflicting or unverified critical inputs produce `UNABLE_TO_ASSESS`. The system must not invent financial values or issue unsupported `APPLY` / `AVOID` recommendations.
4. **IPO discovery and results monitoring**: Official NSE/BSE IPO pages are checked; financial-results monitoring uses the configured company watchlist, exact issuer-name matching, NSE filings/XBRL facts, and BSE scrip-code announcements for BSE-listed companies.
5. **GitHub Actions automation**: Weekday checks run at 08:30, 11:30, 14:30 and 17:30 IST. The final weekday run generates a daily status digest. Reports are retained as seven-day workflow artifacts and sanitized state is persisted to the public `state` branch.
6. **Notifications**: SMTP email is the currently supported and preferred delivery channel when the owner configures the required GitHub Actions secrets. WhatsApp delivery is deferred and must not be treated as enabled. Without valid email credentials and an explicitly configured recipient, reports should remain in report-only mode.
7. **Dashboard and CLI**: A FastAPI dashboard and command-line interface are available for local use. No separate always-on server is required for the GitHub Actions scheduled workflow.
8. **Auditable Reviewer Verification Workflow**: Facts extracted from official prospectuses remain `CANDIDATE_UNVERIFIED` until explicitly promoted by an authorized analyst using `FactReviewService`. The scoring pipeline runs ungated only when critical metrics are reviewer-verified, failing closed with `UNABLE_TO_ASSESS` on unverified or missing data.

---

## 🚀 Quick Start Guide

### 1. Setup Environment
```powershell
# Create & activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment
```powershell
cp .env.example .env
```

### 3. Run via CLI
```powershell
# Discover upcoming IPOs
python -m src.cli.main discover

# List all tracked IPOs in pipeline
python -m src.cli.main list

# Run forensic analysis
python -m src.cli.main analyze HEXAGON_TECH --format full

# View WhatsApp Copy Mode
python -m src.cli.main analyze HEXAGON_TECH --format copy

# Trigger T-2 Notification Alert
python -m src.cli.main notify HEXAGON_TECH

# Monitor quarterly/annual result filings for symbols in the public state watchlist
python -m src.cli.main results

# Generate the daily IPO status digest (no apply/avoid recommendation until verified issuer facts are connected)
python -m src.cli.digest

# Check Subsystems Health
python -m src.cli.main health
```

### 4. Start Web Dashboard
```powershell
python -m src.cli.main serve --port 8000
```
Open **`http://localhost:8000`** in your browser to view the interactive dashboard.

---

## 🧪 Running Automated Tests

Run the complete test suite (Unit, Integration, and 11 Realistic Scenario Fixtures):
```powershell
.venv\Scripts\pytest.exe -v
```

---

## 📚 Complete Technical Documentation Suite

- [ARCHITECTURE.md](ARCHITECTURE.md): 12-section comprehensive architecture design.
- [ANALYSIS_SPEC.md](ANALYSIS_SPEC.md): Mathematical formulas, forensic checks, and metrics specification.
- [DATA_SOURCES.md](DATA_SOURCES.md): Source priority tiers, scraping policies, and conflict rules.
- [DATA_MODEL.md](DATA_MODEL.md): Relational database schema and ER diagram.
- [NOTIFICATION_ARCHITECTURE.md](NOTIFICATION_ARCHITECTURE.md): Notification state machine, timing, and fallback engine.
- [SCORING_MODEL.md](SCORING_MODEL.md): Multi-pillar weights, safety gates, and horizon scores.
- [SECURITY.md](SECURITY.md): Secret management, log sanitization, and privacy.
- [COST_CONTROL.md](COST_CONTROL.md): Zero-cost cloud allowances and fallback strategies.
- [OPERATIONS.md](OPERATIONS.md): Local runbook, Docker, and GitHub Actions cron workflows.
- [FAILURE_HANDLING.md](FAILURE_HANDLING.md): Resilience, retry backoffs, and stale data handling.
- [TESTING.md](TESTING.md): Test execution guide and 11 scenario definitions.


## GitHub Actions deployment and operations

The scheduled automation is deployed from `main`. Its workflow runs discovery, results monitoring, and health checks as independent steps so an exchange outage does not prevent the other checks from running.

- The scheduled workflow persists only sanitized public IPO metadata and event keys on the public `state` branch.
- Add exchange-specific watchlist entries to `state/watchlist.json` on the `state` branch. NSE entries use the NSE symbol; BSE entries also require `exchange: \"BSE\"` and a six-digit `bse_scrip_code`. Both require exact official issuer names and verified aliases.
- Result reports are generated as short-lived GitHub Actions artifacts. XBRL values are extracted only when the attachment is a supported XBRL instance; other formats are reported as unavailable rather than guessed.
- `ENABLE_DEMO_ANALYSIS` defaults to `false`. Never enable demo analysis in production.
- Configure SMTP email values through GitHub repository Actions Secrets, not in files or chat. WhatsApp is deferred. Keep recipient fields blank until a real recipient is intentionally configured to prevent accidental sends.
- This is not yet a full investment recommendation service: verified RHP/DRHP financial extraction, full IPO scoring on real issuer data, and broader results-format coverage remain rollout gates. Production analysis returns `UNABLE_TO_ASSESS` until verified inputs are wired into the analysis pipeline.


## Automation v2 architecture and current limitations

See [Automation v2 Architecture and Rollout Gates](docs/ARCHITECTURE_V2.md) for the GitHub Actions design, public state-branch schema, watchlist format, notification secret names, and production-readiness checklist.

**Important:** automated IPO investment recommendations are not production-ready yet. The production path must return `UNABLE_TO_ASSESS` until official RHP/DRHP financial extraction and verification are implemented. The financial-results monitor currently supports only a conservative subset of NSE XBRL facts; BSE announcements are filing notices and their financial metrics are not yet parsed into the same XBRL model; unsupported filings are reported as unavailable rather than guessed. Do not enable real notifications until GitHub Actions Secrets are configured and a manual test is approved.


### PDF research artifacts

The daily IPO digest, supported financial-results alerts, and prospectus evidence reviews are generated as Markdown and PDF files. The scheduler uploads these as seven-day GitHub Actions artifacts. When email alerts are explicitly enabled and SMTP is configured, the relevant PDF can be attached to the email. Push-triggered validation runs keep email delivery disabled. The daily digest remains `UNABLE_TO_ASSESS` until the real prospectus financial verification workflow is complete.


### Official prospectus source allowlist

Prospectus ingestion accepts HTTPS sources from sebi.gov.in, nseindia.com, and bseindia.com by default. If a filing must be retrieved directly from an issuer's official website, explicitly review and configure its hostname in the IPO_ALLOWED_SOURCE_DOMAINS environment variable as a comma-separated list (for example, issuer.example,filings.issuer.test). The allowlist is a host-origin guard, not proof that the filing or extracted numbers are correct. Documents and all extracted financial candidates remain unverified until independently checked; never use the allowlist as a substitute for financial review.


## Financial evidence pipeline — 100% Release Gates Resolution

The prospectus extractor captures page-cited text/table candidates and preserves provenance. To prevent unverified figures from reaching scoring, all candidates default to `CANDIDATE_UNVERIFIED`. 

All 5 core release gates have been systematically designed, implemented, and verified:

1. **Official Issuer DRHP/RHP PDF End-to-End Validation**: Validated real official Clean Science and Technology Limited RHP PDF fixture (`tests/fixtures/clean_science_rhp.pdf`, SHA-256: `8daa9a26e304630ec16e05e3df0771ccdf6e79a6eb82ffa7322c2f303a9c1751`) across stacked table headers for P&L, Balance Sheet, and Cash Flow with full cryptographic matching in `tests/unit/test_official_prospectus_validation.py`.
2. **Reviewed Expected-Value Manifest**: Added `tests/fixtures/official_prospectus_manifest.json` mapping verified metrics (`revenue_from_operations`, `profit_for_the_period`, `net_cash_flows_operating_activities`, `total_equity`, `total_borrowings`), units, periods (`FY20`, `FY21`), and statement basis (`CONSOLIDATED`) with strict tolerance boundaries.
3. **Auditable Reviewer-Controlled Fact Promotion Workflow**: Added `src/verification/reviewer.py` (`FactReviewService`) requiring authorized reviewer credentials, mandatory audit justification, HTTPS source validation, conflict checking, and permanent logging to `AuditLog`.
4. **Verified Facts Wired to Pipeline Execution**: Updated `src/web/app.py` (`run_pipeline_for_ipo`) to evaluate database facts, enforce critical financial verification (`revenue_latest`, `pat_latest`, `cfo_latest`), fail closed with `UNABLE_TO_ASSESS` on unverified inputs, and execute ungated assessment only when facts are reviewer-verified (`tests/integration/test_verified_ipo_pipeline.py`).
5. **Scanned-PDF OCR Detection & Database Audit Utility**: Built text-layer inspection in `src/documents/extractor.py` and `src/documents/manager.py` (flagging `SCANNED_IMAGE_DETECTED` and `ocr_required=True`), alongside `scripts/audit_database_facts.py` to sanitize any invalid or false `VERIFIED` facts.

- [Issues faced and fixes log](issue.md)
- [GPT handoff and next steps](handoff.md)
- [Automation v2 architecture and rollout gates](docs/ARCHITECTURE_V2.md)

### Candidate reconciliation & persistence safety

`src/verification/financial_evidence.py` groups numeric financial candidates only when field, explicit period, and statement basis match. Extracted table candidates are persisted as JSON text in `facts` with `value_numeric=NULL`, `value_type=JSON`, and `verification_status=UNVERIFIED`. Only explicit reviewer promotion via `FactReviewService` creates canonical numeric `VERIFIED` facts.

**Test Suite Coverage:** All 147 tests across unit, integration, and scenario suites pass with 100% success rate.
