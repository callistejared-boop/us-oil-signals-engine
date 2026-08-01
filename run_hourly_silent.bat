@echo off
cd /d "%~dp0"
where pyw >nul 2>nul && ( start "" pyw "%~dp0hourly_briefing.py" & exit /b )
where pythonw >nul 2>nul && ( start "" pythonw "%~dp0hourly_briefing.py" & exit /b )
where py >nul 2>nul && ( py "%~dp0hourly_briefing.py" & exit /b )
python "%~dp0hourly_briefing.py"
