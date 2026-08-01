@echo off
cd /d "%~dp0"
echo Posting market overview to your Telegram DM and channel...
where py >nul 2>nul && (py post_overview.py) || (python post_overview.py)
echo.
echo Done. Check Telegram. This window can be closed.
pause >nul
