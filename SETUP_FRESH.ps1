# ========================================
# إعداد قاعدة بيانات جديدة تماماً
# ========================================

$line = "=" * 70

Write-Host "`nبدء الإعداد الكامل..." -ForegroundColor Yellow
Write-Host $line -ForegroundColor Yellow

# 1. نسخة احتياطية
if (Test-Path instance\app.db) {
    Write-Host "`n1 نسخ احتياطي للقاعدة الحالية..." -ForegroundColor Cyan
    Copy-Item instance\app.db instance\backups\app_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').db -ErrorAction SilentlyContinue
    Write-Host "   تم" -ForegroundColor Green
}

# 2. حذف القاعدة القديمة
Write-Host "`n2 حذف القاعدة القديمة..." -ForegroundColor Cyan
Remove-Item -Force instance\app.db -ErrorAction SilentlyContinue
Write-Host "   تم" -ForegroundColor Green

# 3. إنشاء قاعدة جديدة
Write-Host "`n3 إنشاء قاعدة البيانات..." -ForegroundColor Cyan
python create_db_properly.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nفشل إنشاء القاعدة!" -ForegroundColor Red
    exit 1
}

# 4. زرع الأدوار
Write-Host "`n4 زرع الأدوار والصلاحيات..." -ForegroundColor Cyan
flask seed-roles --force --reset
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nفشل زرع الأدوار!" -ForegroundColor Red
    exit 1
}
Write-Host "   تم" -ForegroundColor Green

# 5. إنشاء حساب المالك
Write-Host "`n5 إنشاء حساب المالك..." -ForegroundColor Cyan
python setup_owner.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nفشل إنشاء حساب المالك!" -ForegroundColor Red
    exit 1
}

Write-Host "`n"
Write-Host $line -ForegroundColor Green
Write-Host "الإعداد مكتمل!" -ForegroundColor Green
Write-Host $line -ForegroundColor Green

Write-Host "`nمعلومات الدخول:" -ForegroundColor Yellow
Write-Host "  المستخدم: __OWNER__" -ForegroundColor White
Write-Host "  كلمة المرور: Admin@2024" -ForegroundColor White
Write-Host ""
Write-Host "لتشغيل النظام:" -ForegroundColor Cyan
Write-Host "  flask run" -ForegroundColor White
Write-Host ""
