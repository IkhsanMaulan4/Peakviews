@echo off
setlocal

set VENV_DIR=.venv

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo Venv sudah ada di %VENV_DIR%. Lewati create, lanjut install deps.
    goto :install
)

echo === Creating venv di %VENV_DIR% ===
py -3 -m venv "%VENV_DIR%" 2>nul
if errorlevel 1 (
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo.
        echo ERROR: Python tidak ditemukan. Install Python 3.10+ dulu dan pastikan ada di PATH.
        exit /b 1
    )
)

:install
echo === Installing deps dari requirements.txt ===
call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed.
    exit /b 1
)

echo.
echo === Setup complete ===
echo   run.bat   = jalanin app dari source
echo   build.bat = rebuild PeakView.exe ke dist\PeakView\
endlocal
