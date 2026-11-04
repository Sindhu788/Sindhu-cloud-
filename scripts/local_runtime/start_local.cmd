@echo off
rem SINDHU local web app (branch recovery/clean) - SAFE MODE: pages and manual backtests only.
rem No schedulers, no paper engine, no Telegram. Public signals are hard-blocked on this machine (three independent switches below).
rem Runs from the permanent venv D:\sindhu_venv_stable (a copy of the venv that Windows Smart App Control lets load; see docs/RUNBOOK.md section 11).
rem Stop with: D:\sindhu_runtime\stop_local.cmd.  Auto-restart on crash: D:\sindhu_runtime\start_supervised.cmd
set SINDHU_DATA_DIR=D:/sindhu/data
set SINDHU_SAFE_START=1
set SINDHU_OPEN_BROWSER=0
set SINDHU_PUBLIC_SIGNAL_OWNER=disabled
set SINDHU_TELEGRAM_DRY_RUN=1
set SINDHU_STRATEGY_LIBRARY_DIR=D:/sindhu_runtime/strategy_library
if not exist D:\sindhu_venv_stable\Scripts\python.exe (
  echo ERROR: D:\sindhu_venv_stable is missing. See docs\RUNBOOK.md section 11.
  exit /b 1
)
cd /d D:\sindhu_clean
D:\sindhu_venv_stable\Scripts\python.exe web_main.py >> D:\sindhu_runtime\server.log 2>&1
