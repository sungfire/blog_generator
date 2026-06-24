@echo off
setlocal

python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
pyinstaller --onefile --windowed --name BlogWriter app.py

echo.
echo Build complete: dist\BlogWriter.exe
pause
