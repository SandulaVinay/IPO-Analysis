# Complete Deployment Guide (`DEPLOYMENT.md`)

This guide covers all deployment modes for the **Indian IPO Intelligence, Analysis, Recommendation & Notification System**:
1. **Local Background Service (FastAPI + Background Scheduler)**
2. **Containerized Deployment via Docker & Docker Compose**
3. **Automated Zero-Cost Cloud Scheduling via GitHub Actions**
4. **Cloud Web Deployment (Render / Railway Free Tiers)**

---

## 1. Local Deployment (Windows / Linux / macOS)

### 1-Click Launch (Windows)
Double-click [`start_server.bat`](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/start_server.bat) or run from terminal:
```powershell
.venv\Scripts\python.exe -m src.cli.main serve --port 8000
```
- **Web Dashboard**: Open `http://localhost:8000` in any browser.
- **REST API Docs**: Open `http://localhost:8000/docs` (Swagger UI).
- **Background Scheduler**: Automatically runs in-process, checking discovery and dispatching alerts at 09:00 IST.

---

## 2. Containerized Deployment via Docker

### Build and Run with Docker Compose
```bash
# Build & start container with volume persistence
docker compose up -d

# Check logs
docker compose logs -f

# Check container health status
docker ps
```
The application will mount `/app/storage` to a persistent Docker volume `ipo_data`, keeping your database and downloaded PDF prospectuses safe across restarts.

---

## 3. Zero-Cost Scheduled Cloud Deployment (GitHub Actions)

The repository includes a ready-to-use scheduled workflow: [`.github/workflows/ipo_scheduler.yml`](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/.github/workflows/ipo_scheduler.yml).

### Setup:
1. Push this repository to GitHub.
2. In your GitHub repository, go to **Settings > Secrets and variables > Actions**.
3. (Optional) Add your notification secrets:
   - `ENABLE_WHATSAPP`: `true` (or `false`)
   - `WHATSAPP_PHONE_NUMBER_ID`
   - `WHATSAPP_ACCESS_TOKEN`
   - `WHATSAPP_RECIPIENT_PHONE`
   - `ENABLE_EMAIL`: `true` (or `false`)
   - `SMTP_USER`
   - `SMTP_PASSWORD`
   - `EMAIL_TO`
4. The workflow automatically runs on schedule every weekday at **08:30 IST** and **14:30 IST** with **$0.00 infrastructure cost**.

---

## 4. Cloud Web Hosting (Render / Railway)

### Deploying to Render:
1. Link your GitHub repository to [Render.com](https://render.com).
2. Render automatically detects [`render.yaml`](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/render.yaml).
3. Click **Apply** to deploy as a Web Service.

### Deploying to Railway:
1. Import repository on [Railway.app](https://railway.app).
2. Railway detects [`railway.json`](file:///c:/Users/LENOVO/OneDrive/Desktop/Vinay%20Projects/IPO%20Analysis/railway.json) and starts the FastAPI service automatically.
