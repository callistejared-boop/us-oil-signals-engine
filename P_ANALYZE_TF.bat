@echo off
cd /d "%~dp0"
echo Running top-down 4H/1H/15m ICT analysis on live data...
where py >nul 2>nul && (py analyze_tf.py WTIUSD) || (python analyze_tf.py WTIUSD)
echo.
echo Done - see analysis_tf.txt.
pause >nul
