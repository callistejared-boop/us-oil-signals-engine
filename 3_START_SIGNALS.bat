@echo off
cd /d "%~dp0"
title Gold Engine - XAUUSD Signal Scanner
echo Gold Engine is now scanning XAUUSD every 15 minutes.
echo You'll get a Telegram alert when a high-confluence setup appears.
echo Leave this window open. Close it to stop scanning.
echo.
where py >nul 2>nul && (py main.py run) || (python main.py run)
pause >nul
