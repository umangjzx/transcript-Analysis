@echo off
REM Start the AuraSafety backend.
REM - Changes to the backend directory
REM - Activates the virtual environment
REM - Installs watchfiles if missing (needed for --reload-exclude to work)
REM - Starts uvicorn watching only *.py files so large uploads don't trigger a reload

cd /d "%~dp0"

call venv\Scripts\activate.bat

pip show watchfiles >nul 2>&1
if errorlevel 1 (
    echo Installing watchfiles...
    pip install watchfiles==1.0.5 --quiet
)

uvicorn app:app ^
  --host 0.0.0.0 ^
  --port 8000 ^
  --reload ^
  --reload-include "*.py" ^
  --reload-exclude "uploads/*" ^
  --reload-exclude "reports/*" ^
  --reload-exclude "logs/*" ^
  --reload-exclude "vectors/*" ^
  --reload-exclude "*.db" ^
  --reload-exclude "*.log"
