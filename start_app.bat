@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup_windows.bat once before starting AM master.
  pause
  exit /b 1
)
set AM_MASTER_DATA_DIR=D:\AM-master-data
set AM_MASTER_PORT=8777
start "AM master" "http://127.0.0.1:8777"
.venv\Scripts\python.exe app.py
