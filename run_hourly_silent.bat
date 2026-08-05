@echo off
cd /d "%~dp0"
rem Day 3 (Phase 8): hourly_briefing.py is a research/informational read that
rem never writes to the trade journal, but it can still publish a "CONFIRMED
rem SIGNAL" a human could act on. As of Day 3 it runs the same risk_guard +
rem portfolio_risk checks the production alerter uses before showing one, so
rem this scheduled path (see A_SCHEDULE_90MIN.bat) is no longer a silent
rem bypass of centralized risk validation. See RISK_SPECIFICATION.md Sec.6.
where pyw >nul 2>nul && ( start "" pyw "%~dp0hourly_briefing.py" & exit /b )
where pythonw >nul 2>nul && ( start "" pythonw "%~dp0hourly_briefing.py" & exit /b )
where py >nul 2>nul && ( py "%~dp0hourly_briefing.py" & exit /b )
python "%~dp0hourly_briefing.py"
