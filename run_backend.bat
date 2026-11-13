@echo off
echo =====================================================================
echo  SmartCity Insight AI - Backend Django Channels & REST API (8000)
echo =====================================================================
cd /d "%~dp0"
if exist ".\venv\Scripts\activate.bat" (
    call .\venv\Scripts\activate.bat
)
python -m daphne -b 127.0.0.1 -p 8000 config.asgi:application
pause
