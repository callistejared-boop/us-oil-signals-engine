@echo off
REM Forward-test scoreboard -> screen + your private Telegram DM.
cd /d "%~dp0"
python forward_report.py --send
pause
