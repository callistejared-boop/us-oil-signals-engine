@echo off
cd /d "%~dp0"
echo Refreshing live fundamentals + running WTI analysis (no Telegram send)...
where py >nul 2>nul && (py engine\fundamentals_feed.py & py wti_note.py) || (python engine\fundamentals_feed.py & python wti_note.py)
echo Done - see wti_note.txt. Close this window.
pause >nul
