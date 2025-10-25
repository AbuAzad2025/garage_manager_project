@echo off
cd /d D:\karaj\garage_manager_project\garage_manager
echo ═══════════════════════════════════════════════════════════
echo 🚀 تشغيل Flask Server - Advanced Debug Mode
echo ═══════════════════════════════════════════════════════════
echo.
echo 📍 المجلد: %CD%
echo 🌐 العنوان: http://localhost:5000
echo.
echo ═══════════════════════════════════════════════════════════
echo 📝 Logs مباشرة:
echo ═══════════════════════════════════════════════════════════
echo.

set FLASK_APP=app.py
set FLASK_ENV=development
set FLASK_DEBUG=1

python -m flask run --host=0.0.0.0 --port=5000 --reload

pause

