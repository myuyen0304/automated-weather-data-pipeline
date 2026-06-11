@echo off
REM ===========================================================================
REM run_pipeline.bat
REM Windows Task Scheduler wrapper for the daily weather pipeline.
REM Runs extract, transform, load, and writes output to logs\pipeline.log.
REM
REM Create a daily 07:00 task from the project root:
REM   schtasks /Create /SC DAILY /ST 07:00 /TN WeatherPipeline ^
REM            /TR "\"%CD%\run_pipeline.bat\""
REM ===========================================================================

setlocal
cd /d "%~dp0"

if not exist "logs" mkdir "logs"

echo [%date% %time%] Bat dau pipeline >> "logs\pipeline.log"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" src\main.py --load >> "logs\pipeline.log" 2>&1
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" src\main.py --load >> "logs\pipeline.log" 2>&1
) else (
    uv --cache-dir .uv-cache run python src\main.py --load >> "logs\pipeline.log" 2>&1
)
set "PIPELINE_EXIT=%ERRORLEVEL%"
echo [%date% %time%] Ket thuc pipeline (exit=%PIPELINE_EXIT%) >> "logs\pipeline.log"
exit /b %PIPELINE_EXIT%
