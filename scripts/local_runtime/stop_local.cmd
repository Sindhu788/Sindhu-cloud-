@echo off
rem Stops the supervisor (if running) and whatever is listening on port 8420 (the SINDHU local app).
if exist D:\sindhu_runtime\supervisor.stop (del D:\sindhu_runtime\supervisor.stop)
echo stop> D:\sindhu_runtime\supervisor.stop
timeout /t 3 /nobreak >nul
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8420 " ^| findstr LISTENING') do taskkill /PID %%p /F
