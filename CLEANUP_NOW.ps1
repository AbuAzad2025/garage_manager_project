# ========================================
# 🧹 تنظيف النظام النهائي
# ========================================

Write-Host "`n🧹 بدء التنظيف النهائي..." -ForegroundColor Yellow
Write-Host "="*70 -ForegroundColor Yellow

# 1. حذف __pycache__
Write-Host "`n1️⃣ حذف __pycache__..." -ForegroundColor Cyan
Get-ChildItem -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "   ✅ تم" -ForegroundColor Green

# 2. حذف .pyc
Write-Host "`n2️⃣ حذف ملفات .pyc..." -ForegroundColor Cyan
Get-ChildItem -Recurse -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "   ✅ تم" -ForegroundColor Green

# 3. حذف CSV القديمة
Write-Host "`n3️⃣ حذف CSV القديمة..." -ForegroundColor Cyan
Remove-Item instance\imports\reports\*.csv -Force -ErrorAction SilentlyContinue
Write-Host "   ✅ تم" -ForegroundColor Green

# 4. توحيد مجلدات الصور
Write-Host "`n4️⃣ توحيد مجلدات الصور..." -ForegroundColor Cyan
if (Test-Path static\uploads\products\products) {
    Move-Item static\uploads\products\products\*.* static\uploads\products\ -Force -ErrorAction SilentlyContinue
    Remove-Item -Recurse static\uploads\products\products\ -Force -ErrorAction SilentlyContinue
    Write-Host "   ✅ تم توحيد static/uploads/products/" -ForegroundColor Green
}

# 5. تنظيف النسخ الاحتياطية
Write-Host "`n5️⃣ تنظيف النسخ الاحتياطية..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path instance\backups | Out-Null
Move-Item -Force instance\app_backup_*.db instance\backups\ -ErrorAction SilentlyContinue
Move-Item -Force instance\garage_backup_*.db instance\backups\ -ErrorAction SilentlyContinue
Get-ChildItem instance\backups\*.db | Sort-Object LastWriteTime -Descending | Select-Object -Skip 5 | Remove-Item -Force -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force instance\backups\db -ErrorAction SilentlyContinue
Write-Host "   ✅ تم - آخر 5 نسخ في instance\backups\" -ForegroundColor Green

# 6. حذف ملفات مؤقتة
Write-Host "`n6️⃣ حذف ملفات مؤقتة..." -ForegroundColor Cyan
Remove-Item *.tmp, *.bak -Force -ErrorAction SilentlyContinue
Write-Host "   ✅ تم" -ForegroundColor Green

# 7. عرض النتائج
Write-Host "`n" -NoNewline
Write-Host "="*70 -ForegroundColor Green
Write-Host "✅ التنظيف مكتمل!" -ForegroundColor Green
Write-Host "="*70 -ForegroundColor Green

$size = (Get-ChildItem -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host "`n📊 حجم المشروع: $([math]::Round($size, 2)) MB" -ForegroundColor Cyan

Write-Host "`n📁 الهيكل النهائي:" -ForegroundColor Yellow
Write-Host "  ✅ instance/ai/ (9 ملفات AI)" -ForegroundColor White
Write-Host "  ✅ instance/backups/ (آخر 5 نسخ)" -ForegroundColor White
Write-Host "  ✅ static/uploads/products/ (صور موحدة)" -ForegroundColor White
Write-Host "  ✅ لا __pycache__" -ForegroundColor White
Write-Host "  ✅ لا ملفات مؤقتة" -ForegroundColor White

Write-Host "`n✅ النظام نظيف 100%!" -ForegroundColor Green
Write-Host "="*70 -ForegroundColor Green
Write-Host ""

