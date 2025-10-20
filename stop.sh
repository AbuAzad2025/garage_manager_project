#!/bin/bash
# ========================================
# 🛑 سكريبت إيقاف النظام
# ========================================

# ألوان للطباعة
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}🛑 إيقاف نظام Garage Manager${NC}"
echo -e "${YELLOW}========================================${NC}"

# المنفذ - يمكن تمريره كمعامل
PORT="${1:-8001}"

# البحث عن العمليات على المنفذ المحدد
PIDS=$(lsof -ti:$PORT 2>/dev/null)

if [ -z "$PIDS" ]; then
    echo -e "${YELLOW}⚠️  لا توجد عمليات تعمل على المنفذ $PORT${NC}"
else
    echo -e "${RED}🔍 تم العثور على العمليات التالية:${NC}"
    echo "$PIDS"
    echo ""
    echo -e "${RED}🛑 إيقاف العمليات...${NC}"
    echo "$PIDS" | xargs kill -9 2>/dev/null
    echo -e "${GREEN}✅ تم إيقاف جميع العمليات على المنفذ $PORT${NC}"
fi

# إيقاف جميع عمليات gunicorn و python app.py
echo ""
echo -e "${YELLOW}🔍 البحث عن عمليات Gunicorn...${NC}"
GUNICORN_PIDS=$(pgrep -f "gunicorn.*app:app" 2>/dev/null)

if [ -z "$GUNICORN_PIDS" ]; then
    echo -e "${YELLOW}⚠️  لا توجد عمليات Gunicorn${NC}"
else
    echo -e "${RED}🛑 إيقاف عمليات Gunicorn...${NC}"
    echo "$GUNICORN_PIDS" | xargs kill -9 2>/dev/null
    echo -e "${GREEN}✅ تم إيقاف Gunicorn${NC}"
fi

# إيقاف عمليات python app.py
echo ""
echo -e "${YELLOW}🔍 البحث عن عمليات Python (app.py)...${NC}"
PYTHON_PIDS=$(pgrep -f "python.*app.py" 2>/dev/null)

if [ -z "$PYTHON_PIDS" ]; then
    echo -e "${YELLOW}⚠️  لا توجد عمليات Python${NC}"
else
    echo -e "${RED}🛑 إيقاف عمليات Python...${NC}"
    echo "$PYTHON_PIDS" | xargs kill -9 2>/dev/null
    echo -e "${GREEN}✅ تم إيقاف Python${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ تم إيقاف جميع العمليات بنجاح${NC}"
echo -e "${GREEN}========================================${NC}"






