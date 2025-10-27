#!/bin/bash
# سكريبت تحديث سريع لـ PythonAnywhere

echo "╔═══════════════════════════════════════════════════╗"
echo "║                                                   ║"
echo "║   🚀 تحديث نظام إدارة الكراج - PythonAnywhere   ║"
echo "║                                                   ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""

# 1. التأكد من المسار
echo "📁 التحقق من المسار..."
if [ ! -d "~/garage_manager_project" ]; then
    echo "❌ خطأ: المسار غير موجود!"
    exit 1
fi
cd ~/garage_manager_project || exit 1
echo "✅ المسار صحيح"
echo ""

# 2. عمل Backup
echo "💾 إنشاء نسخة احتياطية..."
BACKUP_FILE="instance/app_backup_$(date +%Y%m%d_%H%M%S).db"
if [ -f "instance/app.db" ]; then
    cp instance/app.db "$BACKUP_FILE"
    echo "✅ تم إنشاء النسخة الاحتياطية: $BACKUP_FILE"
else
    echo "⚠️  لم يتم العثور على قاعدة البيانات (أول تشغيل؟)"
fi
echo ""

# 3. سحب التحديثات
echo "⬇️  سحب التحديثات من GitHub..."
git pull origin main
if [ $? -ne 0 ]; then
    echo "❌ فشل سحب التحديثات!"
    exit 1
fi
echo "✅ تم سحب التحديثات بنجاح"
echo ""

# 4. تطبيق التهجيرات
echo "🔄 تطبيق تهجيرات قاعدة البيانات..."
python3.10 -m flask db upgrade
if [ $? -ne 0 ]; then
    echo "❌ فشل تطبيق التهجيرات!"
    echo "💡 استخدم: cp $BACKUP_FILE instance/garage_manager.db"
    exit 1
fi
echo "✅ تم تطبيق التهجيرات بنجاح"
echo ""

# 5. إعادة تحميل التطبيق
echo "🔄 إعادة تحميل تطبيق الويب..."
touch /var/www/palkaraj_pythonanywhere_com_wsgi.py
echo "✅ تم إعادة تحميل التطبيق"
echo ""

# 6. فحص سريع
echo "🔍 فحص النظام..."
python3.10 -c "
from app import app
from models import db
with app.app_context():
    print('✅ النظام يعمل بشكل صحيح!')
" 2>/dev/null

if [ $? -eq 0 ]; then
    echo ""
    echo "╔═══════════════════════════════════════════════════╗"
    echo "║                                                   ║"
    echo "║   🎉 تم التحديث بنجاح! النظام جاهز للعمل       ║"
    echo "║                                                   ║"
    echo "╚═══════════════════════════════════════════════════╝"
else
    echo ""
    echo "⚠️  تحذير: قد تكون هناك مشكلة في النظام"
    echo "💡 راجع: /var/log/palkaraj.pythonanywhere.com.error.log"
fi
echo ""

