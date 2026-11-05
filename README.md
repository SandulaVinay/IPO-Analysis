# 🇮🇳 Indian IPO Intelligence, Analysis, Recommendation & Notification System

A production-quality, evidence-driven, deterministic intelligence platform for discovering, analyzing, recommending, and alerting on Indian Initial Public Offerings (IPOs).

---

## 🌟 Current System Capabilities

1. **Deterministic calculations**: Financial formulas and scoring calculations are performed in Python; an AI model is not required for numerical calculations.
2. **Evidence and provenance**: Prospectus documents are hashed and versioned. Extracted PDF passages retain page references and remain explicitly `UNVERIFIED` until the period, unit and statement-basis checks are completed.
3. **Fail-closed production analysis**: Missing, conflicting or unverified critical inputs produce `UNABLE_TO_ASSESS`. The system must not invent financial values or issue unsupported `APPLY` / `AVOID` recommendations.
4. **IPO discovery and results monitoring**: Official NSE/BSE IPO pages are checked. The results monitor matches configured issuers and BSE scrip codes, then reads official PDF, XML/iXBRL, HTML, CSV/TSV, XLS, and XLSX attachments. Extracted values stay `CANDIDATE_UNVERIFIED` and are never sent to scoring automatically.
5. **GitHub Actions automation**: Weekday checks run at 08:30, 11:30, 14:30 and 17:30 IST. The final weekday run generates a daily status digest. Reports are retained as seven-day workflow artifacts and sanitized state is persisted to the public `state` branch.
6. **Notifications**: SMTP email is primary when the owner configures the required GitHub Actions secrets. Messages include plain-text and HTML bodies, with a PDF attachment when rendering succeeds. WhatsApp is an optional fallback only when explicitly enabled. Without valid email credentials and an explicitly configured recipient, reports remain in report-only mode.
7. **Dashboard and CLI**: A FastAPI dashboard and command-line interface are available for local use. No separate always-on server is required for the GitHub Actions scheduled workflow.
8. **Auditable Reviewer Verification Workflow**: Facts extracted from official prospectuses remain `CANDIDATE_UNVERIFIED` until explicitly promoted by an authorized analyst using `FactReviewService`. When all 8 analysis pillars (financials, business quality, management/governance, structure, valuation, growth, risk, and market regime) are reviewer-verified, ungated scoring safely unlocks with full multi-horizon breakdown. If any pillar evidence is unverified or missing, the pipeline strictly fails closed with `UNABLE_TO_ASSESS`.
9. **Multi-Format Extraction & Scanned PDF OCR Fallback**: Supports PDF, XML/iXBRL, HTML, CSV/TSV, XLS, and XLSX. Includes automated OCR fallback (`extract_scanned_pdf_ocr_text`) for rasterized/scanned PDFs and an expanded Ind AS XBRL reporting taxonomy.

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

Run the complete test suite (205 Unit, Integration, and Scenario Fixtures):
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
- Result reports are generated as short-lived GitHub Actions artifacts. The monitor handles PDF, XBRL/iXBRL, HTML, CSV/TSV, XLS, and XLSX attachments when period, unit, and statement basis can be mapped explicitly; unsupported or ambiguous filings are reported as unavailable. Extracted figures remain candidate-only.
- The daily digest can include a recent IPOWATCH grey-market premium snapshot only after an exact issuer match and issue-price-band consistency check. GMP is unofficial, may be absent, and does not produce an application suggestion.
- `ENABLE_DEMO_ANALYSIS` defaults to `false`. Never enable demo analysis in production.
- Configure SMTP email values through GitHub repository Actions Secrets, not in files or chat. WhatsApp is an optional fallback and must be explicitly enabled. Keep recipient fields blank until a real recipient is intentionally configured to prevent accidental sends.
- For durable reviewer-verified facts and analysis runs across scheduled GitHub Actions executions, set the `DATABASE_URL` repository secret to a persistent async PostgreSQL URL such as `postgresql+asyncpg://...`. Without it, the SQLite fallback is recreated with each runner and only the sanitized registry/event files persist. Database connection logs expose only the backend type, not the URL.
- This is not yet a full investment recommendation service: verified RHP/DRHP ingestion into the live scorer and business, governance, peer-valuation, proceeds, risk, and market evidence remain rollout gates. Production analysis returns `UNABLE_TO_ASSESS` until the full evidence set is connected and verified. Results-format extraction is candidate-only and does not close those gates.


## Automation v2 architecture and current limitations

See [Automation v2 Architecture and Rollout Gates](docs/ARCHITECTURE_V2.md) for the GitHub Actions design, public state-branch schema, watchlist format, notification secret names, and production-readiness checklist.

**Important:** automated IPO investment recommendations are not production-ready yet. The production path must return `UNABLE_TO_ASSESS` until the full evidence set is connected and verified. Results attachments can be parsed in several formats, including BSE attachments, but those extracted values are candidates for review only. Unsupported or ambiguous filings are reported as unavailable rather than guessed. Do not enable real notifications until GitHub Actions Secrets are configured and a manual test is approved.


### PDF research artifacts

The daily IPO digest, financial-results alerts, and prospectus evidence reviews are generated as Markdown reports and PDF files when rendering succeeds. The scheduler uploads these as seven-day GitHub Actions artifacts. When PDF rendering fails, email still sends its plain-text and HTML body without the attachment. Push-triggered validation runs keep email delivery disabled. The daily digest remains `UNABLE_TO_ASSESS` until the full live evidence pipeline is complete.


### Official prospectus source allowlist

Prospectus ingestion accepts HTTPS sources from sebi.gov.in, nseindia.com, and bseindia.com by default. If a filing must be retrieved directly from an issuer's official website, explicitly review and configure its hostname in the IPO_ALLOWED_SOURCE_DOMAINS environment variable as a comma-separated list (for example, issuer.example,filings.issuer.test). The allowlist is a host-origin guard, not proof that the filing or extracted numbers are correct. Documents and all extracted financial candidates remain unverified until independently checked; never use the allowlist as a substitute for financial review.


## Financial evidence pipeline — real-source validation status

The extractor stores provenance-bearing financial candidates and never marks them verified automatically. Reviewer approval remains a separate gate.

**Important validation correction:** `tests/fixtures/clean_science_rhp.pdf` is a synthetic parser fixture generated by `scripts/generate_official_rhp_fixture.py`; it is not a real Clean Science prospectus and its fabricated figures must not be used for issuer analysis. The fixture manifest now labels it as synthetic.

A live validation script and GitHub Actions workflow target the official ESDS Software Solution Limited DRHP published on SEBI:

- Official source: https://www.sebi.gov.in/sebi_data/attachdocs/apr-2025/1743751804884_762.pdf
- Script: `scripts/validate_official_esds_drhp.py`
- Workflow: `.github/workflows/official-drhp-validation.yml`
- Output artifact: `ESDS_DRHP_live_validation.json`
- Checks include downloaded PDF signature and identity, actual SHA-256, page-level statement extraction, selected consolidated FY2024 figures, rupees-million to INR-crore conversion, period and statement-basis metadata, and candidate-only verification status.

**Live-source extraction validation: PASS** on [GitHub Actions run 41421645589](https://github.com/SandulaVinay/IPO-Analysis/actions/runs/41421645589). The downloaded SEBI DRHP SHA-256 is `b4a60feace0d800ba49bc136067e10faf0b4587ac49ad785dab157a90af09585` (7,497,319 bytes; 524 physical pages). The script validated revenue ₹2,865.18 million → ₹286.518 crore, profit for the year ₹136.10 million → ₹13.610 crore, and operating cash inflow ₹455.77 million → ₹45.577 crore for FY2023–2024, consolidated basis. The statement pages are physical PDF pages 297–298 (printed pages 292–293).

This proves extraction and normalization for these selected rows only. Extracted facts remain `CANDIDATE_UNVERIFIED` until an authorized reviewer independently confirms the original statements. Production scoring must continue to fail closed with `UNABLE_TO_ASSESS` when critical evidence is missing, conflicting, or unverified.

### Candidate reconciliation & persistence safety

`src/verification/financial_evidence.py` groups numeric financial candidates only when field, explicit period, and statement basis match. Extracted table candidates are persisted as JSON text in `facts` with `value_numeric=NULL`, `value_type=JSON`, and `verification_status=UNVERIFIED`. Only explicit reviewer promotion via `FactReviewService` creates canonical numeric `VERIFIED` facts.
