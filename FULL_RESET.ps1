# ========================================
# 🔄 تنظيف شامل وبدء من الصفر
# ========================================
cd D:\karaj\garage_manager_project\garage_manager
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\.venv\Scripts\Activate.ps1

# المتغيرات
$env:APP_ENV="development"
$env:DEBUG="true"
$env:FLASK_APP="app:create_app"
$env:PYTHONUTF8="1"
$env:ALLOW_SEED_ROLES="1"
$env:SECRET_KEY="dev-"+([guid]::NewGuid().ToString("N"))

# تنظيف شامل
Write-Host "`n🧹 تنظيف شامل..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path instance\ai | Out-Null
New-Item -ItemType Directory -Force -Path instance\backups\old | Out-Null
Move-Item -Force -ErrorAction SilentlyContinue instance\ai_*.json instance\ai\
Get-ChildItem -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem instance\*_backup_*.db -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -Skip 3 | Move-Item -Destination instance\backups\old\ -ErrorAction SilentlyContinue
Remove-Item -ErrorAction SilentlyContinue -Force .\*.tmp, .\*.bak

# نسخة احتياطية
Write-Host "💾 نسخة احتياطية..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path instance\backups | Out-Null
Copy-Item -ErrorAction SilentlyContinue instance\app.db instance\backups\backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').db

# حذف القديم
Write-Host "🗑️  حذف القديم..." -ForegroundColor Yellow
Remove-Item -ErrorAction SilentlyContinue -Force .\instance\app.db
Remove-Item -ErrorAction SilentlyContinue -Recurse -Force .\migrations

# إنشاء جديد
Write-Host "📦 إنشاء قاعدة البيانات..." -ForegroundColor Cyan
python -c "from app import create_app; from extensions import db; app = create_app(); app.app_context().push(); db.create_all(); print('✅ Database created')"

Write-Host "👥 إنشاء الأدوار..." -ForegroundColor Cyan
flask seed-roles --force --reset

Write-Host "🔐 إنشاء حساب المالك..." -ForegroundColor Cyan
python setup_owner.py

# معلومات الدخول
Write-Host "`n" -NoNewline
Write-Host "="*70 -ForegroundColor Green
Write-Host "✅ النظام جاهز!" -ForegroundColor Green
Write-Host "="*70 -ForegroundColor Green
Write-Host "🔐 معلومات الدخول:" -ForegroundColor Yellow
Write-Host "  👤 Username: __OWNER__" -ForegroundColor White
Write-Host "  🔑 Password: Owner@2025!#SecurePassword" -ForegroundColor White
Write-Host "  🌐 URL: http://localhost:5000" -ForegroundColor Cyan
Write-Host "  🔒 اللوحة السرية: http://localhost:5000/security (للمالك فقط)" -ForegroundColor Magenta
Write-Host "="*70 -ForegroundColor Green
Write-Host "`nاضغط Ctrl+C لإيقاف النظام`n" -ForegroundColor Red

# تشغيل
flask run

