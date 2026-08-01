@echo off
cd /d "%~dp0"
echo Scheduling the fast entry scanner every 15 minutes...
schtasks /Create /TN "XAUUSD Entry Scan 15min" /TR "\"%~dp0run_alert_silent.bat\"" /SC MINUTE /MO 15 /F > sched_entry_result.txt 2>&1
powershell -NoProfile -Command "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable; Set-ScheduledTask -TaskName 'XAUUSD Entry Scan 15min' -Settings $s" >> sched_entry_result.txt 2>&1
schtasks /Query /TN "XAUUSD Entry Scan 15min" /FO LIST /V | findstr /C:"TaskName" /C:"Status" /C:"Next Run" /C:"Repeat: Every" >> sched_entry_result.txt 2>&1
echo DONE>> sched_entry_result.txt
echo Done - fast entry scanner runs every 15 min (fires only on NEW confirmed setups).
echo This runs alongside the 90-minute full briefing. Close this window.
pause >nul
