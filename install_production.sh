#!/bin/bash

# ========================================================
# Garage Manager - Production Installation Script
# سكربت التثبيت للإنتاج - نظام إدارة الورشة
# ========================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                              ║"
    echo "║         نظام إدارة الورشة - التثبيت للإنتاج               ║"
    echo "║         Garage Manager - Production Installation            ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "\n${CYAN}==> $1${NC}"
}

print_success() {
    echo -e "    ${GREEN}[OK]${NC} $1"
}

print_error() {
    echo -e "    ${RED}[!]${NC} $1"
}

print_warning() {
    echo -e "    ${YELLOW}[*]${NC} $1"
}

# Clear screen and show header
clear
print_header

# Check Python
print_step "التحقق من Python..."
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
else
    print_error "Python غير مثبت!"
    echo -e "\nقم بتثبيت Python 3.10+ من: https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 10 ]; then
    print_success "تم العثور على Python $PYTHON_VERSION"
else
    print_error "يتطلب Python 3.10 أو أحدث. الحالي: $PYTHON_VERSION"
    exit 1
fi

# Check pip
print_step "التحقق من pip..."
if $PYTHON_CMD -m pip --version &> /dev/null; then
    print_success "pip متوفر"
else
    print_error "pip غير مثبت!"
    exit 1
fi

# Create virtual environment
print_step "إنشاء البيئة الافتراضية..."
if [ -d ".venv" ]; then
    print_warning "البيئة الافتراضية موجودة مسبقاً"
else
    $PYTHON_CMD -m venv .venv
    print_success "تم إنشاء البيئة الافتراضية"
fi

# Activate virtual environment
print_step "تفعيل البيئة الافتراضية..."
source .venv/bin/activate
print_success "تم تفعيل البيئة الافتراضية"

# Upgrade pip
print_step "تحديث pip..."
pip install --upgrade pip --quiet
print_success "تم تحديث pip"

# Install requirements
print_step "تثبيت المتطلبات (قد يستغرق بضع دقائق)..."
pip install -r requirements.txt --quiet
print_success "تم تثبيت جميع المتطلبات"

# Create .env file
print_step "إعداد ملف الإعدادات (.env)..."
if [ -f ".env" ]; then
    print_warning "ملف .env موجود مسبقاً - لن يتم التعديل"
else
    if [ -f "env.example.txt" ]; then
        cp env.example.txt .env
        
        # Generate random SECRET_KEY
        RANDOM_KEY=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 64 | head -n 1)
        sed -i "s/change-this-to-a-strong-random-secret-key-in-production/$RANDOM_KEY/" .env
        
        print_success "تم إنشاء ملف .env مع مفتاح سري عشوائي"
        print_warning "يمكنك تعديل الإعدادات في ملف .env"
    else
        print_error "ملف env.example.txt غير موجود!"
    fi
fi

# Create necessary directories
print_step "إنشاء المجلدات المطلوبة..."
mkdir -p instance/backups logs static/uploads/products
print_success "تم إنشاء المجلدات"

# Check database
print_step "التحقق من قاعدة البيانات..."
if [ -f "instance/app.db" ]; then
    DB_SIZE=$(du -h instance/app.db | cut -f1)
    print_success "قاعدة البيانات موجودة ($DB_SIZE)"
else
    print_warning "قاعدة البيانات غير موجودة - سيتم إنشاؤها عند التشغيل الأول"
fi

# Test import
print_step "اختبار استيراد التطبيق..."
if $PYTHON_CMD -c "import app" 2>&1; then
    print_success "التطبيق جاهز للعمل"
else
    print_error "خطأ في استيراد التطبيق"
    exit 1
fi

# Success message
echo -e "\n${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                              ║"
echo "║              ✅ التثبيت اكتمل بنجاح! ✅                     ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${CYAN}الخطوات التالية:${NC}\n"
echo -e "${NC}1. راجع ملف .env وعدّل الإعدادات حسب احتياجاتك${NC}"
echo -e "   ${YELLOW}nano .env${NC}\n"
echo -e "${NC}2. لتشغيل النظام:${NC}"
echo -e "   ${YELLOW}./run_production.sh${NC}\n"
echo -e "${NC}3. افتح المتصفح على:${NC}"
echo -e "   ${YELLOW}http://localhost:5000${NC}\n"
echo -e "${NC}4. معلومات الدخول:${NC}"
echo -e "   ${YELLOW}راجع ملف LOGIN_INFO.txt${NC}\n"
echo -e "   ${RED}⚠️  تذكر تغيير كلمة المرور بعد أول دخول!${NC}\n"
echo -e "${NC}للمزيد من المعلومات، راجع:${NC}"
echo -e "   - PRODUCTION_GUIDE.md"
echo -e "   - FINAL_SYSTEM_REPORT.md\n"

