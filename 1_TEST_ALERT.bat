@echo off
cd /d "%~dp0"
echo Sending a test alert to your Telegram...
where py >nul 2>nul && (py send_test_alert.py) || (python send_test_alert.py)
echo.
echo Done. Check your Telegram (chat with your bot). This window can be closed.
pause >nul
