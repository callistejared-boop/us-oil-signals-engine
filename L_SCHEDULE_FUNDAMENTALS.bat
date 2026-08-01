@echo off
cd /d "%~dp0"
echo Scheduling a daily live-fundamentals refresh at 06:00...
schtasks /Create /TN "WTI Fundamentals Refresh" /TR "\"%~dp0run_fundamentals_silent.bat\"" /SC DAILY /ST 06:00 /F > sched_fund_result.txt 2>&1
powershell -NoProfile -Command "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable; Set-ScheduledTask -TaskName 'WTI Fundamentals Refresh' -Settings $s" >> sched_fund_result.txt 2>&1
schtasks /Query /TN "WTI Fundamentals Refresh" /FO LIST /V | findstr /C:"TaskName" /C:"Status" /C:"Next Run" >> sched_fund_result.txt 2>&1
echo DONE>> sched_fund_result.txt
echo Done - fundamentals refresh daily at 6am. This window can be closed.
pause >nul
