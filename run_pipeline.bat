@echo off
REM ===========================================================================
REM run_pipeline.bat
REM Wrapper để Windows Task Scheduler chạy pipeline hằng ngày (thay cho Cron).
REM Tự kích hoạt virtualenv, chạy extract -> transform -> load, ghi log ra file.
REM
REM Tạo task lịch (chạy 7:00 sáng mỗi ngày), từ thư mục project:
REM   schtasks /Create /SC DAILY /ST 07:00 /TN WeatherPipeline ^
REM            /TR "\"%CD%\run_pipeline.bat\""
REM ===========================================================================

setlocal
cd /d "%~dp0"

REM Kích hoạt virtualenv nếu có (hỗ trợ cả "venv" và ".venv").
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

if not exist "logs" mkdir "logs"

echo [%date% %time%] Bat dau pipeline >> "logs\pipeline.log"
python src\main.py --load >> "logs\pipeline.log" 2>&1
echo [%date% %time%] Ket thuc pipeline (exit=%ERRORLEVEL%) >> "logs\pipeline.log"

endlocal
