@echo off
REM One-click: register the hourly WTI analysis job, then run the first one now.
echo ============================================================
echo   Registering "WTI Hourly Analysis" (every 60 minutes)...
echo ============================================================
schtasks /Create /TN "WTI Hourly Analysis" /TR "\"%~dp0W_HOURLY_WTI.bat\"" /SC MINUTE /MO 60 /F /RL LIMITED
if errorlevel 1 (
  echo.
  echo Could not register the task. Try running this file as Administrator
  echo ^(right-click -^> Run as administrator^).
  pause
  exit /b 1
)
echo.
echo Registered. Running the first WTI analysis now ^(this sends to Telegram^)...
echo.
call "%~dp0W_HOURLY_WTI.bat"
echo ---------------- latest run log ----------------
type "%~dp0wti_hourly.log"
echo ------------------------------------------------
echo.
echo Done. You'll now get a WTI analysis every hour on Telegram.
pause
