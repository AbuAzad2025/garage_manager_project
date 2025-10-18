#!/bin/bash

# ========================================================
# Garage Manager - Production Run Script
# سكربت تشغيل الإنتاج - نظام إدارة الورشة
# ========================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Header
clear
echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                              ║"
echo "║              نظام إدارة الورشة - الإنتاج                   ║"
echo "║              Garage Manager - Production                     ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check virtual environment
if [ ! -d ".venv" ]; then
    echo -e "\n${RED}[!] البيئة الافتراضية غير موجودة!${NC}"
    echo -e "    ${YELLOW}قم بتشغيل ./install_production.sh أولاً${NC}\n"
    exit 1
fi

# Activate virtual environment
echo -e "\n${YELLOW}[*] تفعيل البيئة الافتراضية...${NC}"
source .venv/bin/activate

# Check .env file
if [ ! -f ".env" ]; then
    echo -e "\n${RED}[!] ملف .env غير موجود!${NC}"
    echo -e "    ${YELLOW}قم بنسخ env.example.txt إلى .env وتعديله${NC}\n"
    exit 1
fi

# Detect Python command
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
else
    PYTHON_CMD=python
fi

# Display system info
echo -e "\n${CYAN}📊 معلومات النظام:${NC}"
echo -e "   ${NC}🐍 Python: $($PYTHON_CMD --version 2>&1 | awk '{print $2}')${NC}"
echo -e "   ${NC}📁 المجلد: $(pwd)${NC}"

if [ -f "instance/app.db" ]; then
    DB_SIZE=$(du -h instance/app.db | cut -f1)
    echo -e "   ${NC}💾 قاعدة البيانات: $DB_SIZE${NC}"
fi

# Check if already running
if pgrep -f "python.*app.py" > /dev/null; then
    echo -e "\n${YELLOW}[!] يبدو أن النظام يعمل بالفعل!${NC}"
    read -p "هل تريد إيقافه وإعادة التشغيل؟ (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pkill -f "python.*app.py"
        sleep 2
        echo -e "    ${GREEN}تم إيقاف النظام السابق${NC}"
    else
        exit 0
    fi
fi

# Start the application
echo -e "\n${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              🚀 جاري تشغيل النظام...                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${YELLOW}📡 النظام يعمل على: http://127.0.0.1:5000${NC}"
echo -e "${YELLOW}🔐 راجع ملف LOGIN_INFO.txt لمعلومات الدخول${NC}\n"
echo -e "\033[90mاضغط Ctrl+C لإيقاف النظام\033[0m"
echo -e "\033[90m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n"

# Run the application
$PYTHON_CMD app.py

