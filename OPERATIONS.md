# Operations, Deployment & Runbook (`OPERATIONS.md`)

This runbook explains how to configure, run, operate, and monitor the Indian IPO Intelligence System.

---

## 1. Quick Start (Local Execution)

### Activate Virtual Environment
```powershell
.venv\Scripts\activate
```

### Run CLI Commands
```powershell
# 1. Run IPO Discovery
python -m src.cli.main discover

# 2. List all tracked IPOs
python -m src.cli.main list

# 3. Run Full Forensic Analysis
python -m src.cli.main analyze HEXAGON_TECH --format full

# 4. View WhatsApp Copy Mode
python -m src.cli.main analyze HEXAGON_TECH --format copy

# 5. Trigger T-2 Alert Dispatch
python -m src.cli.main notify HEXAGON_TECH

# 6. Check Subsystems Health
python -m src.cli.main health
```

### Start Web Dashboard Server
```powershell
python -m src.cli.main serve --port 8000
```
*Access interactive dark-mode dashboard at `http://localhost:8000`.*

---

## 2. GitHub Actions Scheduled Automation (Zero-Cost)

Create `.github/workflows/ipo_scheduler.yml`:
```yaml
name: IPO Discovery & Alert Dispatch

on:
  schedule:
    - cron: '0 3,9 * * 1-5' # 08:30 IST and 14:30 IST on weekdays
  workflow_dispatch:

jobs:
  run-pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run Discovery & Notifications
        run: |
          python -m src.cli.main discover
          python -m src.cli.main health
```

---

## 3. How to Replace Notification Providers

All notification channels implement the `NotificationProvider` interface (`src/notifications/provider.py`).
To swap in a custom provider (e.g. Telegram or Discord):
1. Subclass `NotificationProvider` in `src/notifications/`.
2. Implement `send_notification(self, recipient, subject, content)`.
3. Add the provider instance to `NotificationOrchestrator.providers` list.
