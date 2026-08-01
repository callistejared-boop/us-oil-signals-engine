@echo off
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py
%PY% -c "import pandas,numpy;print('imports OK',pandas.__version__,numpy.__version__)" > verify_result.txt 2>&1
%PY% -c "from engine import data_loader,signals;df=data_loader.load_csv('data/XAU_15m_data.csv');s=signals.analyze(df.tail(12000));print('ENGINE_SCAN_OK bars='+str(len(df))+' signal='+('YES' if s else 'none-expected'))" >> verify_result.txt 2>&1
%PY% -m pytest tests/ -q >> verify_result.txt 2>&1
echo done >> verify_result.txt
