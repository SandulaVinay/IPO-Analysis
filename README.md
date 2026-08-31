# 🇮🇳 Indian IPO Intelligence, Analysis, Recommendation & Notification System

A production-quality, evidence-driven, deterministic intelligence platform for discovering, analyzing, recommending, and alerting on Indian Initial Public Offerings (IPOs).

---

## 🌟 Key System Capabilities

1. **Deterministic Primacy**: All financial, mathematical, and valuation calculations are executed in deterministic code. The LLM is **never** used for numerical math.
2. **Evidence & Provenance Hierarchy**: Segregates **FACTS** (with document version, page number, extraction timestamp), **CALCULATIONS**, and **OPINIONS**.
3. **Hard Safety Assessment Gates**: If critical financial numbers or timeline dates are missing or conflicting across Tier 1 sources, the system outputs `⚪ UNABLE TO ASSESS` rather than guessing.
4. **Multi-Horizon Decision Modeling**: Evaluates Company Quality, IPO Attractiveness, Listing Opportunity, and Long-Term Opportunity separately.
5. **Proactive T-2 Notification Orchestrator**: Dispatches alerts 2 calendar days before IPO opening (Asia/Kolkata timezone awareness, market holidays), with a 6-hour reminder, T-1 reminder, and opening alert across `WhatsApp → Email → SMS → Console` with automated fallback.
6. **Zero Mandatory Recurring Cost**: Runs locally, via cron, or on GitHub Actions with zero recurring infrastructure expenses.
7. **Interactive Web Dashboard & Rich CLI**: Modern dark-mode Glassmorphism dashboard and terminal console tool.

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
