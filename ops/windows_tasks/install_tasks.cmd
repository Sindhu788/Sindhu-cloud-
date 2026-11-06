@echo off
rem Master plan A23 + A25: SINDHU scheduled tasks for THIS Windows user. The OWNER runs this once (Claude does not install it).
rem Times are laptop time (Pakistan Standard Time). Remove again with remove_tasks.cmd. No task sends anything to a public group;
rem the daily report goes only to OWNER_CHAT_ID (set the user variables TELEGRAM_BOT_TOKEN and OWNER_CHAT_ID first).
set REPO=D:\sindhu_clean
set PY=D:\sindhu_venv_stable\Scripts\python.exe
set PYBT=D:\sindhu_venv_bt\Scripts\python.exe
set LOGS=D:\sindhu_runtime\tasks\logs
if not exist "%LOGS%" mkdir "%LOGS%"
schtasks /Create /F /TN "SINDHU\Daily candle update" /SC DAILY /ST 02:10 /TR "cmd /c cd /d %REPO% && %PYBT% -m data_platform.run_download --root D:\sindhu_data >> %LOGS%\candles.log 2>&1"
schtasks /Create /F /TN "SINDHU\Daily health report" /SC DAILY /ST 09:10 /TR "cmd /c cd /d %REPO% && %PY% ops\windows_tasks\daily_health_report.py --send >> %LOGS%\health_report.log 2>&1"
schtasks /Create /F /TN "SINDHU\Weekly scorecard" /SC WEEKLY /D MON /ST 10:10 /TR "cmd /c cd /d %REPO% && %PY% scripts\weekly_scorecard.py D:\sindhu_runtime\tasks\WEEKLY_SCORECARD_latest.md >> %LOGS%\scorecard.log 2>&1"
schtasks /Create /F /TN "SINDHU\Weekly backup" /SC WEEKLY /D SUN /ST 03:30 /TR "cmd /c cd /d %REPO% && %PY% ops\windows_tasks\weekly_backup.py >> %LOGS%\backup.log 2>&1"
schtasks /Create /F /TN "SINDHU\Monthly export" /SC MONTHLY /D 1 /ST 10:20 /TR "cmd /c cd /d %REPO% && %PY% ops\windows_tasks\monthly_export.py >> %LOGS%\export.log 2>&1"
schtasks /Create /F /TN "SINDHU\Local app at logon" /SC ONLOGON /TR "D:\sindhu_runtime\start_supervised.cmd"
echo.
echo Done. Check: Start menu -> "Task Scheduler" -> folder "SINDHU" (6 tasks).
