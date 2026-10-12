@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo Устанавливаю библиотеки...
pip install -r requirements.txt --no-cache-dir
echo.
echo Готово!
pause