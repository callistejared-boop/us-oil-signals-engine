@echo off
cd /d "%~dp0"
echo Running full WTI crude analysis (live data)...
where py >nul 2>nul && (py analyze_wti.py) || (python analyze_wti.py)
echo.
echo Done. See wti_report.txt. This window can be closed.
pause >nul
