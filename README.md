# 🇮🇳 Indian IPO Intelligence, Analysis, Recommendation & Notification System

A production-quality, evidence-driven, deterministic intelligence platform for discovering, analyzing, recommending, and alerting on Indian Initial Public Offerings (IPOs).

---

## 🌟 Current System Capabilities

1. **Deterministic calculations**: Financial formulas and scoring calculations are performed in Python; an AI model is not required for numerical calculations.
2. **Evidence and provenance**: Prospectus documents are hashed and versioned. Extracted PDF passages retain page references and remain explicitly `UNVERIFIED` until the period, unit and statement-basis checks are completed.
3. **Fail-closed production analysis**: Missing, conflicting or unverified critical inputs produce `UNABLE_TO_ASSESS`. The system must not invent financial values or issue unsupported `APPLY` / `AVOID` recommendations.
4. **IPO discovery and results monitoring**: Official NSE/BSE IPO pages are checked; financial-results monitoring uses the configured company watchlist and a conservative subset of NSE/XBRL filing data.
5. **GitHub Actions automation**: Weekday checks run at 08:30, 11:30, 14:30 and 17:30 IST. The final weekday run generates a daily status digest. Reports are retained as seven-day workflow artifacts and sanitized state is persisted to the public `state` branch.
6. **Notifications**: WhatsApp Cloud API is primary and SMTP email is the fallback when the owner configures the required GitHub Actions secrets. Without credentials, reports are generated in report-only mode. WhatsApp eligibility and charges depend on provider terms.
7. **Dashboard and CLI**: A FastAPI dashboard and command-line interface are available for local use. No separate always-on server is required for the GitHub Actions scheduled workflow.

**Production limitation:** full automated IPO investment recommendations are not yet enabled. Table-aware prospectus financial extraction, period/unit reconciliation, consolidated-versus-standalone verification, and a fully validated live-source pipeline remain open gates. The safe result is `UNABLE_TO_ASSESS` until those checks are complete.

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

- [ARCHITECTURE.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/ARCHITECTURE.md): 12-section comprehensive architecture design.
- [ANALYSIS_SPEC.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/ANALYSIS_SPEC.md): Mathematical formulas, forensic checks, and metrics specification.
- [DATA_SOURCES.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/DATA_SOURCES.md): Source priority tiers, scraping policies, and conflict rules.
- [DATA_MODEL.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/DATA_MODEL.md): Relational database schema and ER diagram.
- [NOTIFICATION_ARCHITECTURE.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/NOTIFICATION_ARCHITECTURE.md): Notification state machine, timing, and fallback engine.
- [SCORING_MODEL.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/SCORING_MODEL.md): Multi-pillar weights, safety gates, and horizon scores.
- [SECURITY.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/SECURITY.md): Secret management, log sanitization, and privacy.
- [COST_CONTROL.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/COST_CONTROL.md): Zero-cost cloud allowances and fallback strategies.
- [OPERATIONS.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/OPERATIONS.md): Local runbook, Docker, and GitHub Actions cron workflows.
- [FAILURE_HANDLING.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/FAILURE_HANDLING.md): Resilience, retry backoffs, and stale data handling.
- [TESTING.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/TESTING.md): Test execution guide and 11 scenario definitions.


## Automation v2 rollout notes

The `automation-v2` branch and draft pull request are being used to validate the safer scheduled architecture before anything is merged into `main`.

- The scheduled workflow persists only sanitized public IPO metadata and event keys on the public `state` branch.
- Add NSE symbols to `state/watchlist.json` on the `state` branch to monitor official financial-results filings. The list is intentionally empty by default.
- Result reports are generated as short-lived GitHub Actions artifacts. XBRL values are extracted only when the attachment is a supported XBRL instance; other formats are reported as unavailable rather than guessed.
- `ENABLE_DEMO_ANALYSIS` defaults to `false`. Never enable demo analysis in production.
- Configure WhatsApp and email values through GitHub repository Actions Secrets, not in files or chat. The application defaults recipient fields to blank to prevent accidental sends.
- This is not yet a full investment recommendation service: verified RHP/DRHP financial extraction, full IPO scoring on real issuer data, and broader results-format coverage remain rollout gates. Production analysis returns `UNABLE_TO_ASSESS` until verified inputs are wired into the analysis pipeline.


## Automation v2 architecture and current limitations

See [Automation v2 Architecture and Rollout Gates](docs/ARCHITECTURE_V2.md) for the GitHub Actions design, public state-branch schema, watchlist format, notification secret names, and production-readiness checklist.

**Important:** automated IPO investment recommendations are not production-ready yet. The production path must return `UNABLE_TO_ASSESS` until official RHP/DRHP financial extraction and verification are implemented. The financial-results monitor currently supports only a conservative subset of XBRL facts; unsupported filings are reported as unavailable rather than guessed. Do not enable real notifications until GitHub Actions Secrets are configured and a manual test is approved.


### PDF research artifacts

The daily IPO digest, supported financial-results alerts, and prospectus evidence reviews are generated as Markdown and PDF files. The scheduler uploads these as seven-day GitHub Actions artifacts. WhatsApp messages link to the workflow run; when email fallback is used, the relevant PDF is attached. The daily digest remains `UNABLE_TO_ASSESS` until the real prospectus financial verification workflow is complete.
