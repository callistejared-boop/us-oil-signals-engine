@echo off
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py
%PY% -c "from engine import data_loader,config; s=config.load(); df=data_loader.fetch_live(s); print('LIVE_FETCH_OK bars='+str(len(df))+' last='+str(df.index[-1])+' price='+str(round(float(df['Close'].iloc[-1]),2)))" > live_result.txt 2>&1
echo done >> live_result.txt
