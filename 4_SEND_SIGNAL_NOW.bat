@echo off
cd /d "%~dp0"
echo Running full multi-market analysis and sending the briefing to your Telegram...
echo (Research/informational read - Day 3: risk-gated the same way as live alerts.)
echo.
where py >nul 2>nul && (py hourly_briefing.py) || (python hourly_briefing.py)
echo.
echo Done. Check Telegram. This window can be closed.
pause >nul
