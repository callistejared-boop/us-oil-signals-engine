@echo off
cd /d "%~dp0"
echo Scheduling live news + bias refresh every 5 minutes...
schtasks /Create /TN "Signals News 5min" /TR "\"%~dp0run_news_silent.bat\"" /SC MINUTE /MO 5 /F > sched_news_result.txt 2>&1
powershell -NoProfile -Command "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable; Set-ScheduledTask -TaskName 'Signals News 5min' -Settings $s" >> sched_news_result.txt 2>&1
schtasks /Query /TN "Signals News 5min" /FO LIST /V | findstr /C:"TaskName" /C:"Status" /C:"Next Run" /C:"Repeat: Every" >> sched_news_result.txt 2>&1
echo DONE>> sched_news_result.txt
echo Done - news + bias refresh every 5 minutes. Open news_bias.html to watch. This window can be closed.
pause >nul
