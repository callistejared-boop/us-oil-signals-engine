@echo off
cd /d "%~dp0"
echo Running full-system audit (may take up to a minute)...
where py >nul 2>nul && (py verify_all.py) || (python verify_all.py)
echo. >> verify_all.txt
echo [10] SCHEDULED TASK >> verify_all.txt
schtasks /Query /TN "XAUUSD Hourly Signal" /FO LIST /V | findstr /C:"TaskName" /C:"Status" /C:"Next Run" /C:"Schedule Type" /C:"Repeat: Every" >> verify_all.txt 2>&1
echo. >> verify_all.txt
echo [11] KEY FILES PRESENT >> verify_all.txt
for %%F in (main.py hourly_briefing.py 3_START_SIGNALS.bat 5_SCHEDULE_HOURLY.bat .env data\XAU_15m_data.csv engine\news_guard.py engine\journal.py) do if exist "%%F" (echo   OK   %%F>> verify_all.txt) else (echo   MISSING %%F>> verify_all.txt)
echo DONE-BAT >> verify_all.txt
echo Audit finished. Results in verify_all.txt. This window can be closed.
pause >nul
