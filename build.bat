@echo off
setlocal

set VENV_DIR=.venv

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Venv belum ada. Jalankan setup.bat dulu.
    exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"

echo === PeakView build ===
pyinstaller PeakView.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo BUILD FAILED at pyinstaller step.
    exit /b 1
)

copy /Y dist-README.txt dist\PeakView\README.txt >nul
if errorlevel 1 (
    echo.
    echo README copy failed.
    exit /b 1
)

echo.
echo === Build complete ===
echo Output: dist\PeakView\
echo Zip for distribution:
echo   Compress-Archive dist\PeakView PeakView.zip
endlocal
