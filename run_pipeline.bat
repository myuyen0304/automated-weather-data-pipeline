@echo off
REM ===========================================================================
REM run_pipeline.bat
REM Manual Windows wrapper for the same PowerShell entrypoint used by Task
REM Scheduler. Keep automation logic in scripts\run_pipeline_task.ps1 so manual
REM runs and scheduled runs do not drift.
REM ===========================================================================

setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_pipeline_task.ps1" %*
exit /b %ERRORLEVEL%
