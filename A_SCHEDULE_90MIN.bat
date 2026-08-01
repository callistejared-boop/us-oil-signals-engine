@echo off
cd /d "%~dp0"
echo Setting XAUUSD briefings to every 90 minutes...
schtasks /Delete /TN "XAUUSD Signal 15min" /F >nul 2>&1
schtasks /Delete /TN "XAUUSD Hourly Signal" /F >nul 2>&1
schtasks /Create /TN "XAUUSD Signal 90min" /TR "\"%~dp0run_hourly_silent.bat\"" /SC MINUTE /MO 90 /F > sched90_result.txt 2>&1
powershell -NoProfile -Command "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable; Set-ScheduledTask -TaskName 'XAUUSD Signal 90min' -Settings $s" >> sched90_result.txt 2>&1
schtasks /Query /TN "XAUUSD Signal 90min" /FO LIST /V | findstr /C:"TaskName" /C:"Status" /C:"Next Run" /C:"Repeat: Every" >> sched90_result.txt 2>&1
echo DONE>> sched90_result.txt
echo Done - now every 90 minutes. This window can be closed.
pause >nul
