@echo off
cd /d "%~dp0"
echo Refreshing live news for all pairs and opening the interface...
where py >nul 2>nul && (py engine\fundamentals_feed.py & py news_bias.py) || (python engine\fundamentals_feed.py & python news_bias.py)
start "" news_bias.html
echo Done. This window can be closed.
pause >nul
