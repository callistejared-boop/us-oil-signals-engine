@echo off
cd /d "%~dp0"
echo Running full XAUUSD analysis and sending the briefing to your Telegram...
echo.
where py >nul 2>nul && (py hourly_briefing.py) || (python hourly_briefing.py)
echo.
echo Done. Check Telegram. This window can be closed.
pause >nul
