@echo off
rem Master plan V2 R9: runs the 48-hour soak monitor once, starting now (owner installs).
rem Remove with: schtasks /Delete /TN SINDHU_Soak /F
schtasks /Create /TN SINDHU_Soak /SC ONCE /ST 00:00 /SD 01/01/2000 /F /TR "D:\sindhu_venv_stable\Scripts\python.exe D:\sindhu_clean\ops\soak\soak_monitor.py --hours 48"
schtasks /Run /TN SINDHU_Soak
