@echo off
echo ========================================
echo Starting Flask Server with Debug Mode
echo ========================================
echo.
echo Server will run on: http://localhost:5000
echo Debug mode: ENABLED
echo Auto-reload: ENABLED
echo.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

cd /d "%~dp0"
set FLASK_APP=app.py
set FLASK_ENV=development
set FLASK_DEBUG=1
set PYTHONIOENCODING=utf-8

python app.py

pause

