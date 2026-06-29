@echo off
setlocal

cd /d "%~dp0"

if not exist requirements.txt (
  echo ERROR: requirements.txt not found in %cd%
  pause
  exit /b 1
)

if not exist app.py (
  echo ERROR: app.py not found in %cd%
  pause
  exit /b 1
)

python -m venv .venv
if errorlevel 1 goto fail

call .venv\Scripts\activate
if errorlevel 1 goto fail

python -m pip install --upgrade pip
if errorlevel 1 goto fail

python -m pip install -r requirements.txt
if errorlevel 1 goto fail

python -m PyInstaller --onefile --windowed --name BlogWriter app.py
if errorlevel 1 goto fail

echo.
echo Build complete: dist\BlogWriter.exe
pause
exit /b 0

:fail
echo.
echo Build failed. Check the error message above.
pause
exit /b 1
