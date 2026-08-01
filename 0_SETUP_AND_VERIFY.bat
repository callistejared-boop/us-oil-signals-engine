@echo off
cd /d "%~dp0"
echo Setting up and verifying the engine. This can take 1-3 minutes...
echo (You can watch progress in setup_log.txt)
set PY=python
where py >nul 2>nul && set PY=py
(
  echo === PYTHON ===
  %PY% -V
  echo === PIP INSTALL ===
  %PY% -m pip install --user -r requirements.txt
  echo === IMPORT CHECK ===
  %PY% -c "import pandas,numpy,requests; print('imports OK', pandas.__version__, numpy.__version__)"
  echo === LIVE SCAN ===
  %PY% main.py scan --live
) > setup_log.txt 2>&1
echo.
echo Finished. Results saved to setup_log.txt. This window can be closed.
pause >nul
