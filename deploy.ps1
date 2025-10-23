# سكريبت رفع التحديثات إلى GitHub
# استخدمه بعد كل تعديل

Write-Host "`n════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  📤 رفع التحديثات إلى GitHub" -ForegroundColor Yellow
Write-Host "════════════════════════════════════════`n" -ForegroundColor Cyan

# 1. عرض التغييرات
Write-Host "📊 التغييرات:" -ForegroundColor Yellow
git status --short

# 2. إضافة التغييرات
Write-Host "`n➕ إضافة التغييرات..." -ForegroundColor Green
git add -A

# 3. Commit
$commitMsg = Read-Host "`n💬 اكتب رسالة الـ commit (أو اضغط Enter لاستخدام 'update')"
if ([string]::IsNullOrWhiteSpace($commitMsg)) {
    $commitMsg = "update"
}

git commit -m $commitMsg

# 4. Push
Write-Host "`n🚀 رفع إلى GitHub..." -ForegroundColor Green
git push origin main

Write-Host "`n✅ تم الرفع بنجاح!" -ForegroundColor Green
Write-Host "`n📝 الآن على PythonAnywhere نفذ:" -ForegroundColor Yellow
Write-Host "   cd ~/garage_manager_project && source .venv/bin/activate && git pull origin main" -ForegroundColor Cyan
Write-Host "`n════════════════════════════════════════`n" -ForegroundColor Cyan

