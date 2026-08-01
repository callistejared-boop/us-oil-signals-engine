@echo off
cd /d "%~dp0"
echo Running the self-improvement review on your live trade journal...
where py >nul 2>nul && (py self_review.py) || (python self_review.py)
echo.
echo Done. Open self_review.html to see what actually predicts your wins.
pause >nul
