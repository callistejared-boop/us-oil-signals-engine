@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul && (pythonw engine\fundamentals_feed.py) || (python engine\fundamentals_feed.py)
