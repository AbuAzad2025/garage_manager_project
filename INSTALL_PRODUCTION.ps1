# ========================================================
# Garage Manager - Production Installation Script
# سكربت التثبيت للإنتاج - نظام إدارة الورشة
# ========================================================

$ErrorActionPreference = "Stop"

function Write-ColorMessage {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Write-Step {
    param([string]$Message)
    Write-ColorMessage "`n==> $Message" "Cyan"
}

function Write-Success {
    param([string]$Message)
    Write-ColorMessage "    [OK] $Message" "Green"
}

function Write-Error {
    param([string]$Message)
    Write-ColorMessage "    [!] $Message" "Red"
}

# Header
Clear-Host
Write-ColorMessage @"

╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║         نظام إدارة الورشة - التثبيت للإنتاج               ║
║         Garage Manager - Production Installation            ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

"@ "Cyan"

# Check Python
Write-Step "التحقق من Python..."
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python (\d+)\.(\d+)") {
        $major = [int]$matches[1]
        $minor = [int]$matches[2]
        if ($major -ge 3 -and $minor -ge 10) {
            Write-Success "تم العثور على $pythonVersion"
        } else {
            Write-Error "يتطلب Python 3.10 أو أحدث. الحالي: $pythonVersion"
            exit 1
        }
    }
} catch {
    Write-Error "Python غير مثبت أو غير موجود في PATH"
    Write-ColorMessage "`nقم بتثبيت Python من: https://www.python.org/downloads/" "Yellow"
    exit 1
}

# Create virtual environment
Write-Step "إنشاء البيئة الافتراضية..."
if (Test-Path ".venv") {
    Write-ColorMessage "    البيئة الافتراضية موجودة مسبقاً..." "Yellow"
} else {
    python -m venv .venv
    Write-Success "تم إنشاء البيئة الافتراضية"
}

# Activate virtual environment
Write-Step "تفعيل البيئة الافتراضية..."
& .\.venv\Scripts\Activate.ps1
Write-Success "تم تفعيل البيئة الافتراضية"

# Upgrade pip
Write-Step "تحديث pip..."
python -m pip install --upgrade pip --quiet
Write-Success "تم تحديث pip"

# Install requirements
Write-Step "تثبيت المتطلبات (قد يستغرق بضع دقائق)..."
pip install -r requirements.txt --quiet
Write-Success "تم تثبيت جميع المتطلبات"

# Create .env file
Write-Step "إعداد ملف الإعدادات (.env)..."
if (Test-Path ".env") {
    Write-ColorMessage "    ملف .env موجود مسبقاً - لن يتم التعديل" "Yellow"
} else {
    Copy-Item ".env.example" ".env"
    
    # Generate random SECRET_KEY
    $randomKey = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 64 | ForEach-Object {[char]$_})
    (Get-Content ".env") -replace "change-this-to-a-strong-random-secret-key-in-production", $randomKey | Set-Content ".env"
    
    Write-Success "تم إنشاء ملف .env مع مفتاح سري عشوائي"
    Write-ColorMessage "    يمكنك تعديل الإعدادات في ملف .env" "Yellow"
}

# Create necessary directories
Write-Step "إنشاء المجلدات المطلوبة..."
$directories = @("instance", "instance/backups", "logs", "static/uploads", "static/uploads/products")
foreach ($dir in $directories) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}
Write-Success "تم إنشاء المجلدات"

# Check database
Write-Step "التحقق من قاعدة البيانات..."
if (Test-Path "instance/app.db") {
    $dbSize = (Get-Item "instance/app.db").Length / 1MB
    Write-Success "قاعدة البيانات موجودة ($([math]::Round($dbSize, 2)) MB)"
} else {
    Write-ColorMessage "    قاعدة البيانات غير موجودة - سيتم إنشاؤها عند التشغيل الأول" "Yellow"
}

# Test import
Write-Step "اختبار استيراد التطبيق..."
try {
    python -c "import app" 2>&1 | Out-Null
    Write-Success "التطبيق جاهز للعمل"
} catch {
    Write-Error "خطأ في استيراد التطبيق"
    Write-ColorMessage $_.Exception.Message "Red"
    exit 1
}

# Success message
Write-ColorMessage @"

╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║              ✅ التثبيت اكتمل بنجاح! ✅                     ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

"@ "Green"

Write-ColorMessage "الخطوات التالية:" "Cyan"
Write-ColorMessage ""
Write-ColorMessage "1. راجع ملف .env وعدّل الإعدادات حسب احتياجاتك" "White"
Write-ColorMessage "   nano .env" "Gray"
Write-ColorMessage ""
Write-ColorMessage "2. لتشغيل النظام:" "White"
Write-ColorMessage "   .\RUN_PRODUCTION.ps1" "Gray"
Write-ColorMessage ""
Write-ColorMessage "3. افتح المتصفح على:" "White"
Write-ColorMessage "   http://localhost:5000" "Yellow"
Write-ColorMessage ""
Write-ColorMessage "4. معلومات الدخول:" "White"
Write-ColorMessage "   راجع ملف LOGIN_INFO.txt" "Yellow"
Write-ColorMessage ""
Write-ColorMessage "   ⚠️  تذكر تغيير كلمة المرور بعد أول دخول!" "Red"
Write-ColorMessage ""
Write-ColorMessage "للمزيد من المعلومات، راجع:" "White"
Write-ColorMessage "   - PRODUCTION_GUIDE.md" "Gray"
Write-ColorMessage "   - FINAL_SYSTEM_REPORT.md" "Gray"
Write-ColorMessage ""

# Pause
Write-ColorMessage "اضغط أي مفتاح للخروج..." "DarkGray"
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

