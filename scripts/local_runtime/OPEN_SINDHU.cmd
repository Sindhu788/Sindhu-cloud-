@echo off
rem Double-click to start SINDHU on this laptop (if it is not already running) and open it in the browser.
D:\sindhu_venv_stable\Scripts\python.exe D:\sindhu_runtime\launch_detached.py --wait
if %errorlevel%==0 start "" http://127.0.0.1:8420
pause
