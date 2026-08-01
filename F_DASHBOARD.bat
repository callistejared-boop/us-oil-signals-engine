@echo off
cd /d "%~dp0"
echo Building your live performance dashboard...
where py >nul 2>nul && (py performance_dashboard.py) || (python performance_dashboard.py)
echo.
echo Done. Open dashboard.html. This window can be closed.
pause >nul
