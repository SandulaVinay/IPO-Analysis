@echo off
echo =====================================================================
echo  Starting Indian IPO Intelligence Platform Dashboard Server
echo =====================================================================

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please create .venv and install requirements.txt.
    pause
    exit /b 1
)

echo Initializing database and starting FastAPI daemon on http://localhost:8000 ...
.venv\Scripts\python.exe -m src.cli.main serve --port 8000
pause
