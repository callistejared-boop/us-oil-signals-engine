@echo off
REM One-shot: rename the Telegram channel title to "US Oil Signals" and push a
REM fresh US Oil analysis to Telegram (also proves the rebrand end-to-end).
cd /d "%~dp0"
echo ============================================================
echo   1/2  Renaming Telegram channel title to "US Oil Signals"
echo ============================================================
python set_channel_title.py > rebrand_log.txt 2>&1
type rebrand_log.txt
echo.
echo ============================================================
echo   2/2  Sending fresh US Oil analysis to Telegram...
echo ============================================================
python wti_hourly.py >> rebrand_log.txt 2>&1
echo ---------------- run log ----------------
type wti_hourly.log
echo -----------------------------------------
echo.
echo Done. Check Telegram: channel title + a fresh US Oil report.
pause
