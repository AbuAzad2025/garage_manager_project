# ========================================
# 🚀 تشغيل عادي (بدون حذف)
# ========================================
cd D:\karaj\garage_manager_project\garage_manager
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\.venv\Scripts\Activate.ps1
$env:APP_ENV="development"
$env:DEBUG="true"
$env:FLASK_APP="app:create_app"
$env:PYTHONUTF8="1"
$env:ALLOW_SEED_ROLES="1"
$env:SECRET_KEY="dev-"+([guid]::NewGuid().ToString("N"))

Write-Host "`n🚀 تشغيل النظام..." -ForegroundColor Green
Write-Host "🌐 URL: http://localhost:5000" -ForegroundColor Cyan
Write-Host "اضغط Ctrl+C لإيقاف النظام`n" -ForegroundColor Red

flask run

