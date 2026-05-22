@echo off
REM Double-click this file to launch the MOZART Insta Handler app (Windows).
cd /d "%~dp0"

python -c "import flask" 2>nul
if errorlevel 1 (
  echo Installing dependencies (first run only)...
  pip install -r requirements.txt
)

echo.
echo Starting MOZART Insta Handler...
echo   The app will open in your browser at http://127.0.0.1:5050
echo   Close this window to stop the app.
echo.

python app.py
pause
