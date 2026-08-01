@echo off
cd /d "%~dp0"
echo Building the WTI ICT/SMC chart (installs the chart library if needed)...
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m pip install --user plotly -q 2>nul
%PY% chart_wti.py
echo.
echo Done. Open wti_chart.html in this folder. This window can be closed.
pause >nul
