@echo off
rem Starts the local app UNDER the supervisor (health check every 30 s, restart after 3 failures, log rotation).
rem The supervisor is the only launcher: it first frees port 8420. Stop everything with stop_local.cmd.
call D:\sindhu_runtime\stop_local.cmd >nul 2>&1
start "SINDHU local supervisor" /min D:\sindhu_venv_stable\Scripts\python.exe D:\sindhu_runtime\supervise_local.py
