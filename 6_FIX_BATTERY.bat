@echo off
cd /d "%~dp0"
echo Allowing the hourly task to run on battery power...
powershell -NoProfile -Command "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable; Set-ScheduledTask -TaskName 'XAUUSD Hourly Signal' -Settings $s" > battery_result.txt 2>&1
schtasks /Query /TN "XAUUSD Hourly Signal" /FO LIST /V | findstr /C:"Power Management" /C:"Status" /C:"Next Run" >> battery_result.txt 2>&1
echo DONE>> battery_result.txt
echo Done. This window can be closed.
pause >nul
