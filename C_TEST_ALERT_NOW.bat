@echo off
cd /d "%~dp0"
echo Running the entry alerter once (sends ONLY if a NEW confirmed setup exists)...
echo.
where py >nul 2>nul && (py alert_signals.py) || (python alert_signals.py)
echo.
echo Done. See alert_heartbeat.txt for the result. Close this window.
pause >nul
