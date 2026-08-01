@echo off
cd /d "%~dp0"
echo Disabling stale "XAUUSD Signal 90min" task (runs hourly_briefing.py, > unregister_output.txt
echo which predates the MAST confluence engine and bypasses range_guard/risk_guard/grade.py) >> unregister_output.txt
schtasks /Change /TN "XAUUSD Signal 90min" /DISABLE >> unregister_output.txt 2>&1
schtasks /Query /TN "XAUUSD Signal 90min" /FO LIST /V | findstr /C:"TaskName" /C:"Status" >> unregister_output.txt
echo DONE >> unregister_output.txt
