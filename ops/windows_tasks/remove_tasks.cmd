@echo off
rem Removes every SINDHU scheduled task created by install_tasks.cmd. Data, logs, exports and backups are kept.
for %%T in ("Daily candle update" "Daily health report" "Weekly scorecard" "Weekly backup" "Monthly export" "Local app at logon") do schtasks /Delete /F /TN "SINDHU\%%~T"
echo Removed.
