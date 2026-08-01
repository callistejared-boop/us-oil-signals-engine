@echo off
cd /d "%~dp0"
echo Walk-forward validation: raw vs base-rate vs calibrated (out-of-sample)...
where py >nul 2>nul && (py -m engine.walkforward) || (python -m engine.walkforward)
echo.
pause >nul
