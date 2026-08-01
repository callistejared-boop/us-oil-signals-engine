@echo off
cd /d "%~dp0"
echo Installing the engine's data libraries (one-time, ~1-2 min)...
echo.
where py >nul 2>nul && (py -m pip install --user -r requirements.txt) || (python -m pip install --user -r requirements.txt)
echo.
echo Install finished. If you see errors above, tell Claude. Press any key to close.
pause >nul
