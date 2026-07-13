@echo off
rem SG Radar - fetch latest events/deals and regenerate site\index.html
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist ".venv\Scripts\python.exe" (
  echo [setup] creating virtualenv and installing dependencies...
  py -m venv .venv || python -m venv .venv
  ".venv\Scripts\python" -m pip install --quiet --disable-pip-version-check -r requirements.txt
)
".venv\Scripts\python" -m src.pipeline
if errorlevel 1 pause
