@echo off
cd /d "%~dp0"
echo Starting the TradingView webhook receiver (needs TV_WEBHOOK_SECRET in .env)...
where py >nul 2>nul && (py tv_webhook.py) || (python tv_webhook.py)
pause >nul
