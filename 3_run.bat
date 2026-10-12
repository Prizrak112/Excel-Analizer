@echo off
cd /d "%~dp0"

REM Закрываем родительский CMD сразу после запуска
start "" "venv\Scripts\pythonw.exe" -m src.main

REM Выходим из bat-файла — CMD закрывается
exit