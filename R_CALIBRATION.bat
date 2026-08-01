@echo off
cd /d "%~dp0"
echo Confidence calibration report (predicted vs realized win rate)...
where py >nul 2>nul && (py -m engine.calibration) || (python -m engine.calibration)
echo.
pause >nul
