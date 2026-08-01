@echo off
cd /d "%~dp0"
echo Setting signal alerts to HOURLY (was every 15 minutes)...
schtasks /Delete /TN "XAUUSD Entry Scan 15min" /F >nul 2>&1
schtasks /Delete /TN "XAUUSD Signal 15min" /F >nul 2>&1
schtasks /Create /TN "Signals Entry Scan 60min" /TR "\"%~dp0run_alert_silent.bat\"" /SC MINUTE /MO 60 /F > sched_hourly_result.txt 2>&1
powershell -NoProfile -Command "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable; Set-ScheduledTask -TaskName 'Signals Entry Scan 60min' -Settings $s" >> sched_hourly_result.txt 2>&1
schtasks /Query /TN "Signals Entry Scan 60min" /FO LIST /V | findstr /C:"TaskName" /C:"Status" /C:"Next Run" /C:"Repeat: Every" >> sched_hourly_result.txt 2>&1
echo DONE>> sched_hourly_result.txt
echo Done - signal alerts now fire every 60 minutes. Close this window.
pause >nul
