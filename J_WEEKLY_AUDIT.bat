@echo off
cd /d "%~dp0"
echo Posting your weekly self-audit to your Telegram DM...
where py >nul 2>nul && (py weekly_audit.py --send) || (python weekly_audit.py --send)
echo.
echo Done. Check your Telegram DM. This window can be closed.
pause >nul
