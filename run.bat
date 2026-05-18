@echo off
setlocal

set VENV_DIR=.venv

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Venv belum ada. Jalankan setup.bat dulu.
    exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"
python main.py
endlocal
