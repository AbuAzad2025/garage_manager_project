#!/bin/bash
# 🚀 تحديث التطبيق على PythonAnywhere

echo ""
echo "========================================"
echo "🚀 تحديث Garage Manager - PythonAnywhere"
echo "========================================"
echo ""

# 1. الانتقال للمجلد
echo "📂 الانتقال للمجلد..."
cd ~/garage_manager_project/garage_manager

# 2. Pull من GitHub
echo "📥 جلب آخر تحديث من GitHub..."
git pull origin main

if [ $? -eq 0 ]; then
    echo "✅ تم جلب التحديثات بنجاح"
else
    echo "❌ فشل جلب التحديثات"
    exit 1
fi

# 3. Reload Web App
echo ""
echo "🔄 إعادة تشغيل التطبيق..."
touch /var/www/palkaraj_pythonanywhere_com_wsgi.py

if [ $? -eq 0 ]; then
    echo "✅ تم reload التطبيق بنجاح"
else
    echo "❌ فشل reload"
    exit 1
fi

echo ""
echo "========================================"
echo "✅ التحديث اكتمل بنجاح!"
echo "========================================"
echo ""
echo "🌐 التطبيق متاح على:"
echo "   https://palkaraj.pythonanywhere.com"
echo ""

