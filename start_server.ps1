# تشغيل نظام Garage Manager على البورت 5000
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "🚀 بدء تشغيل نظام Garage Manager" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

# الانتقال إلى مجلد المشروع
$projectPath = "D:\karaj\garage_manager_project\garage_manager"
Set-Location $projectPath

Write-Host "`n📂 المجلد الحالي: $projectPath" -ForegroundColor Yellow

# التحقق من وجود البيئة الافتراضية
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "✅ تم العثور على البيئة الافتراضية" -ForegroundColor Green
    .\.venv\Scripts\Activate.ps1
} else {
    Write-Host "❌ لم يتم العثور على البيئة الافتراضية" -ForegroundColor Red
    Write-Host "⚙️  إنشاء بيئة افتراضية جديدة..." -ForegroundColor Yellow
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    Write-Host "📦 تثبيت المتطلبات..." -ForegroundColor Yellow
    pip install -r requirements.txt
}

# تعيين متغيرات البيئة
$env:APP_ENV = "development"
$env:DEBUG = "true"
$env:FLASK_APP = "app:create_app"
$env:PYTHONUTF8 = "1"
$env:ALLOW_SEED_ROLES = "1"

Write-Host "`n🌐 تشغيل النظام على:" -ForegroundColor Cyan
Write-Host "   → http://localhost:5000" -ForegroundColor Green
Write-Host "   → http://127.0.0.1:5000" -ForegroundColor Green
Write-Host "`n⚠️  اضغط Ctrl+C لإيقاف الخادم" -ForegroundColor Yellow
Write-Host "========================================`n" -ForegroundColor Cyan

# تشغيل Flask
python app.py



