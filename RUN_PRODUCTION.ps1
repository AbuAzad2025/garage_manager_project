# ========================================================
# Garage Manager - Production Run Script
# سكربت تشغيل الإنتاج - نظام إدارة الورشة
# ========================================================

$ErrorActionPreference = "Stop"

# Colors
function Write-ColorMessage {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

# Header
Clear-Host
Write-ColorMessage @"

╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║              نظام إدارة الورشة - الإنتاج                   ║
║              Garage Manager - Production                     ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

"@ "Cyan"

# Check virtual environment
if (!(Test-Path ".venv")) {
    Write-ColorMessage "`n[!] البيئة الافتراضية غير موجودة!" "Red"
    Write-ColorMessage "    قم بتشغيل INSTALL_PRODUCTION.ps1 أولاً`n" "Yellow"
    exit 1
}

# Activate virtual environment
Write-ColorMessage "`n[*] تفعيل البيئة الافتراضية..." "Yellow"
& .\.venv\Scripts\Activate.ps1

# Check .env file
if (!(Test-Path ".env")) {
    Write-ColorMessage "`n[!] ملف .env غير موجود!" "Red"
    Write-ColorMessage "    قم بنسخ .env.example إلى .env وتعديله`n" "Yellow"
    exit 1
}

# Display system info
Write-ColorMessage "`n📊 معلومات النظام:" "Cyan"
Write-ColorMessage "   🐍 Python: $(python --version)" "White"
Write-ColorMessage "   📁 المجلد: $PWD" "White"

if (Test-Path "instance/app.db") {
    $dbSize = (Get-Item "instance/app.db").Length / 1MB
    Write-ColorMessage "   💾 قاعدة البيانات: $([math]::Round($dbSize, 2)) MB" "White"
}

# Check if already running
$existingProcess = Get-Process python -ErrorAction SilentlyContinue | Where-Object {$_.Path -like "*\.venv\*"}
if ($existingProcess) {
    Write-ColorMessage "`n[!] يبدو أن النظام يعمل بالفعل!" "Yellow"
    $choice = Read-Host "`nهل تريد إيقافه وإعادة التشغيل؟ (y/n)"
    if ($choice -eq 'y') {
        $existingProcess | Stop-Process -Force
        Start-Sleep -Seconds 2
        Write-ColorMessage "    تم إيقاف النظام السابق" "Green"
    } else {
        exit 0
    }
}

# Start the application
Write-ColorMessage @"

╔══════════════════════════════════════════════════════════════╗
║              🚀 جاري تشغيل النظام...                        ║
╚══════════════════════════════════════════════════════════════╝

"@ "Green"

Write-ColorMessage "📡 النظام يعمل على: http://127.0.0.1:5000" "Yellow"
Write-ColorMessage "🔐 راجع ملف LOGIN_INFO.txt لمعلومات الدخول`n" "Yellow"
Write-ColorMessage "اضغط Ctrl+C لإيقاف النظام" "DarkGray"
Write-ColorMessage "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`n" "DarkGray"

# Run the application
try {
    python app.py
} catch {
    Write-ColorMessage "`n`n[!] حدث خطأ أثناء التشغيل:" "Red"
    Write-ColorMessage $_.Exception.Message "Red"
    exit 1
}

