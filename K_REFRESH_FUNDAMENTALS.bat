@echo off
cd /d "%~dp0"
echo Refreshing live WTI fundamentals from news feeds...
where py >nul 2>nul && (py engine\fundamentals_feed.py) || (python engine\fundamentals_feed.py)
echo.
echo Done. fundamentals.json updated. This window can be closed.
pause >nul
