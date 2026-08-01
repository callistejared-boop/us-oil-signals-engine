@echo off
cd /d "%~dp0"
echo Building your unified Command Center (refreshes performance + self-review)...
where py >nul 2>nul && (py self_review.py) || (python self_review.py)
where py >nul 2>nul && (py performance_dashboard.py) || (python performance_dashboard.py)
where py >nul 2>nul && (py command_center.py) || (python command_center.py)
echo.
echo Done. Open command_center.html — one screen for everything.
pause >nul
