@echo off
REM Hourly WTI-only analysis + news -> Telegram. Called by Task Scheduler.
cd /d "%~dp0"
python wti_hourly.py >> wti_hourly.log 2>&1
