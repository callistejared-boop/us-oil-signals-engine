@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul && (pythonw engine\correlation.py & pythonw engine\fundamentals_feed.py & pythonw news_bias.py & pythonw command_center.py & pythonw news_watch.py) || (python engine\correlation.py & python engine\fundamentals_feed.py & python news_bias.py & python command_center.py & python news_watch.py)
