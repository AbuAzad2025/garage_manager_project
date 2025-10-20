#!/bin/bash
# ========================================
# 🚀 تشغيل النظام في الخلفية (Background)
# ========================================

set -e

# ألوان للطباعة
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}🚀 تشغيل النظام في الخلفية${NC}"
echo -e "${CYAN}========================================${NC}"

# الانتقال إلى مجلد المشروع
cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)

# تفعيل البيئة الافتراضية
if [ -d "venv" ]; then
    echo -e "${GREEN}✅ تفعيل البيئة الافتراضية...${NC}"
    source venv/bin/activate
else
    echo -e "${RED}❌ البيئة الافتراضية غير موجودة${NC}"
    exit 1
fi

# تعيين متغيرات البيئة
export APP_ENV="production"
export DEBUG="false"
export FLASK_APP="app:create_app"
export PYTHONUTF8="1"
export ALLOW_SEED_ROLES="0"

if [ -z "$SECRET_KEY" ]; then
    export SECRET_KEY="prod-$(openssl rand -hex 32)"
fi

# المنفذ
PORT="${1:-8001}"

# فحص إذا كان المنفذ مستخدم
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${YELLOW}⚠️  المنفذ $PORT مستخدم${NC}"
    echo -e "${RED}❌ قم بإيقاف العملية أولاً باستخدام: bash stop.sh $PORT${NC}"
    exit 1
fi

# إنشاء مجلد السجلات
mkdir -p logs

# ملفات السجلات
LOG_FILE="logs/app.log"
PID_FILE="logs/app.pid"

echo -e "${GREEN}🚀 تشغيل النظام على المنفذ $PORT...${NC}"

# تشغيل في الخلفية
nohup gunicorn app:app \
    --bind 0.0.0.0:$PORT \
    --workers 4 \
    --threads 2 \
    --worker-class gthread \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log \
    --log-level info \
    --capture-output \
    --pid $PID_FILE \
    --daemon 2>&1 | tee -a $LOG_FILE &

# الانتظار قليلاً للتأكد من التشغيل
sleep 3

# فحص إذا كانت العملية تعمل
if [ -f "$PID_FILE" ]; then
    PID=$(cat $PID_FILE)
    if ps -p $PID > /dev/null 2>&1; then
        echo ""
        echo -e "${GREEN}✅ تم تشغيل النظام بنجاح!${NC}"
        echo -e "${CYAN}🌐 URL: http://0.0.0.0:$PORT${NC}"
        echo -e "${CYAN}📍 أو: http://$(hostname -I | awk '{print $1}'):$PORT${NC}"
        echo -e "${CYAN}📝 السجلات: $LOG_FILE${NC}"
        echo -e "${CYAN}🔢 PID: $PID${NC}"
        echo ""
        echo -e "${YELLOW}لإيقاف النظام استخدم: bash stop.sh $PORT${NC}"
        echo -e "${YELLOW}لمراقبة السجلات: tail -f $LOG_FILE${NC}"
    else
        echo -e "${RED}❌ فشل التشغيل. تحقق من السجلات: $LOG_FILE${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ فشل التشغيل. لم يتم إنشاء ملف PID${NC}"
    exit 1
fi






