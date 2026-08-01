@echo off
cd /d "%~dp0"
where pyw >nul 2>nul && ( start "" pyw "%~dp0alert_signals.py" & exit /b )
where pythonw >nul 2>nul && ( start "" pythonw "%~dp0alert_signals.py" & exit /b )
where py >nul 2>nul && ( py "%~dp0alert_signals.py" & exit /b )
python "%~dp0alert_signals.py"
