@echo off
REM ===========================================================================
REM run_pipeline.bat
REM Windows Task Scheduler wrapper for the daily weather pipeline.
REM Starts local PostgreSQL, runs extract/transform/load, and writes output to
REM logs\pipeline.log.
REM
REM Create or update a daily 08:30 task:
REM   schtasks /Create /SC DAILY /ST 08:30 /TN WeatherPipeline ^
REM            /TR D:\automated-weather-data-pipeline\run_pipeline.bat /F
REM ===========================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

if not exist "logs" mkdir "logs"

echo [%date% %time%] Bat dau pipeline >> "logs\pipeline.log"
echo [%date% %time%] Kiem tra PostgreSQL Docker container >> "logs\pipeline.log"
docker compose up -d >> "logs\pipeline.log" 2>&1
if errorlevel 1 (
    echo [%date% %time%] Khong the khoi dong PostgreSQL bang docker compose. Kiem tra Docker Desktop. >> "logs\pipeline.log"
    exit /b 1
)

set "PG_HEALTH="
for /L %%I in (1,1,12) do (
    for /F "delims=" %%H in ('docker inspect --format="{{.State.Health.Status}}" weather_postgres 2^>nul') do set "PG_HEALTH=%%H"
    if /I "!PG_HEALTH!"=="healthy" goto postgres_ready
    echo [%date% %time%] Cho PostgreSQL healthy... current=!PG_HEALTH! >> "logs\pipeline.log"
    timeout /t 5 /nobreak >nul
)

echo [%date% %time%] PostgreSQL chua healthy sau khi cho. Dung pipeline. >> "logs\pipeline.log"
exit /b 1

:postgres_ready
echo [%date% %time%] PostgreSQL healthy, bat dau chay ETL >> "logs\pipeline.log"

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
