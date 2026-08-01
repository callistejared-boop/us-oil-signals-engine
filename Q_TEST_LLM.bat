@echo off
cd /d "%~dp0"
echo Testing the Claude news analyst (uses your ANTHROPIC_API_KEY + credits)...
where py >nul 2>nul && (py engine\llm_news.py) || (python engine\llm_news.py)
echo.
pause >nul
