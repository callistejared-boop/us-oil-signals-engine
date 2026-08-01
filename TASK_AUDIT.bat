@echo off
cd /d "%~dp0"
echo === ALL SCHEDULED TASKS === > task_audit_output.txt
schtasks /Query /FO LIST /V >> task_audit_output.txt 2>>&1
echo ERRORLEVEL=%errorlevel% >> task_audit_output.txt
echo DONE >> task_audit_output.txt
