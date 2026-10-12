@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo Запускаю приложение (режим отладки)...
python -m src.main
pause