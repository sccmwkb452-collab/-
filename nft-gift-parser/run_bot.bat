@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv || (echo Установите Python с python.org и отметьте "Add to PATH" & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
if "%BOT_TOKEN%"=="" set /p BOT_TOKEN=Вставьте токен бота и нажмите Enter: 
python bot.py
pause
