@echo off
cd /d "%~dp0"
echo Switching XAUUSD briefings to every 15 minutes...
schtasks /Delete /TN "XAUUSD Hourly Signal" /F >nul 2>&1
schtasks /Create /TN "XAUUSD Signal 15min" /TR "\"%~dp0run_hourly_silent.bat\"" /SC MINUTE /MO 15 /F > sched15_result.txt 2>&1
powershell -NoProfile -Command "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable; Set-ScheduledTask -TaskName 'XAUUSD Signal 15min' -Settings $s" >> sched15_result.txt 2>&1
schtasks /Query /TN "XAUUSD Signal 15min" /FO LIST /V | findstr /C:"TaskName" /C:"Status" /C:"Next Run" /C:"Schedule Type" /C:"Repeat: Every" >> sched15_result.txt 2>&1
echo DONE>> sched15_result.txt
echo Done - now running every 15 minutes. This window can be closed.
pause >nul
