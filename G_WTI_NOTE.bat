@echo off
cd /d "%~dp0"
echo Refreshing live fundamentals, then building + posting the WTI note...
where py >nul 2>nul && (py engine\fundamentals_feed.py) || (python engine\fundamentals_feed.py)
where py >nul 2>nul && (py wti_note.py --send) || (python wti_note.py --send)
echo.
echo Done. See wti_note.txt. This window can be closed.
pause >nul
