@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================================
REM  setup_venv.bat — создание venv для проекта
REM  Проект: ОтчетV2.ipynb (ГСМ)
REM  Требуется: Python 3.10+ в PATH
REM ============================================================

REM --- Переходим в папку, где лежит сам бат-файл ---
cd /d "%~dp0"

REM --- Имя папки для venv ---
set "VENV_DIR=%~dp0venv"
set "REQ_FILE=%~dp0requirements.txt"

echo ============================================================
echo  Разворачивание виртуального окружения
echo  Папка проекта: %~dp0
echo  Venv:          %VENV_DIR%
echo ============================================================
echo.

REM --- 1. Проверка Python ---
where python >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в PATH.
    echo Установите Python 3.10+ с python.org и отметьте
    echo   [X] Add Python to PATH
    pause
    exit /b 1
)

echo --- Версия Python ---
python --version
echo.

REM --- 2. Проверка requirements.txt ---
if not exist "%REQ_FILE%" (
    echo [ОШИБКА] Не найден файл requirements.txt:
    echo   %REQ_FILE%
    pause
    exit /b 1
)

REM --- 3. Создаём venv ---
if exist "%VENV_DIR%" (
    echo [1/4] Venv уже существует. Удаляем и пересоздаём...
    rmdir /s /q "%VENV_DIR%"
) else (
    echo [1/4] Создаём venv...
)

python -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось создать venv.
    pause
    exit /b 1
)
echo     Готово: %VENV_DIR%
echo.

REM --- 4. Обновляем pip ---
echo [2/4] Обновляем pip...
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ПРЕДУПРЕЖДЕНИЕ] Не удалось обновить pip. Продолжаем...
)
echo.

REM --- 5. Устанавливаем пакеты ---
echo [3/4] Устанавливаем пакеты из requirements.txt...
echo     Это может занять 1-3 минуты...
"%VENV_DIR%\Scripts\python.exe" -m pip install -r "%REQ_FILE%"
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Часть пакетов не установилась. Смотрите вывод выше.
    pause
    exit /b 1
)
echo.

REM --- 6. Регистрируем ядро Jupyter ---
echo [4/4] Регистрируем ядро Jupyter...
"%VENV_DIR%\Scripts\python.exe" -m ipykernel install --user --name=gsm-report --display-name="Python (ГСМ отчет)"
if errorlevel 1 (
    echo [ПРЕДУПРЕЖДЕНИЕ] Не удалось зарегистрировать ядро Jupyter.
)

echo.
echo ============================================================
echo  ГОТОВО
echo ============================================================
echo  Venv создан: %VENV_DIR%
echo.
echo  Активировать вручную:
echo      "%VENV_DIR%\Scripts\activate.bat"
echo.
echo  Или запустить ноутбук через run_jupyter.bat
echo ============================================================
pause
endlocal