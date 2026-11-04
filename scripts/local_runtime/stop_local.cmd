@echo off
rem Stops the supervisor (waits for it to exit, up to 60 s) and then whatever still listens on port 8420 (the SINDHU local app).
echo stop> D:\sindhu_runtime\supervisor.stop
for /l %%i in (1,1,30) do (
  if not exist D:\sindhu_runtime\supervisor.pid goto done
  timeout /t 2 /nobreak >nul
)
:done
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8420 " ^| findstr LISTENING') do taskkill /PID %%p /F
if exist D:\sindhu_runtime\supervisor.stop del D:\sindhu_runtime\supervisor.stop
