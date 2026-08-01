@echo off
cd /d "%~dp0"
echo Registering an hourly Windows task: "XAUUSD Hourly Signal"...
schtasks /Create /TN "XAUUSD Hourly Signal" /TR "\"%~dp0run_hourly_silent.bat\"" /SC HOURLY /F > sched_result.txt 2>&1
schtasks /Query /TN "XAUUSD Hourly Signal" /FO LIST /V >> sched_result.txt 2>&1
echo DONE>> sched_result.txt
echo.
echo Hourly task registered. Details saved to sched_result.txt.
echo Your laptop will now send an XAUUSD briefing to Telegram every hour.
echo (Runs while the laptop is on and you're logged in.)
echo This window can be closed.
pause >nul
