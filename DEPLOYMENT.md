# 🚀 دليل النشر - Garage Manager System

## 📋 نشر على PythonAnywhere

### 🔄 تحديث الملفات فقط (بدون تهجيرات)
```bash
cd ~/garage_manager_project
git pull origin main
touch /var/www/palkaraj_pythonanywhere_com_wsgi.py
```

### 🔄 تحديث مع المتطلبات (requirements)
```bash
cd ~/garage_manager_project
git pull origin main
python3.10 -m pip install --user -r requirements.txt --upgrade
touch /var/www/palkaraj_pythonanywhere_com_wsgi.py
```

### 🗄️ تحديث قاعدة البيانات SQLite (نادر)
```bash
cd ~/garage_manager_project
python3.10 << 'EOF'
from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    # مثال: إضافة عمود
    db.session.execute(text("ALTER TABLE table_name ADD COLUMN column_name TYPE"))
    db.session.commit()
    print('✅ تم!')
EOF

touch /var/www/palkaraj_pythonanywhere_com_wsgi.py
```

---

## ✨ نظام الحذف القوي - Hard Delete System

### 🎯 الوحدات المدعومة (8)
1. ✅ العملاء (Customers)
2. ✅ الموردين (Suppliers) + العميل المرتبط
3. ✅ الشركاء (Partners) + العميل المرتبط + الحصص
4. ✅ المبيعات (Sales)
5. ✅ الدفعات (Payments)
6. ✅ المصاريف (Expenses)
7. ✅ الصيانة (Service Requests) - يرجع قطع الغيار
8. ✅ الشيكات (Checks)

### 🔒 الأمان
- ✅ صفحة تأكيد لكل عملية
- ✅ سبب الحذف إجباري
- ✅ تسجيل كامل في DeletionLog
- ✅ إمكانية الاستعادة
- ✅ العمليات العكسية التلقائية

### 📦 العمليات العكسية
- إرجاع/سحب المخزون تلقائياً
- عكس القيود المحاسبية (GLBatch)
- حذف العميل المرتبط (موردين/شركاء)
- حذف الحصص والتسويات
- try-except شامل - لا توقف عند الأخطاء

### 🔗 الاستعادة
- `/hard-delete/logs` - سجل جميع العمليات
- زر "استعادة" لكل عملية مكتملة
- استعادة بسيطة (الكيان الرئيسي فقط)

---

## 🔕 الإشعارات
- ✅ جميع الرسائل ثابتة
- ✅ لا إخفاء تلقائي
- ✅ المستخدم يغلقها يدوياً بـ ×

---

## 📊 الملخص التقني
- **الملفات المعدلة**: services/hard_delete_service.py, routes/hard_delete.py, models.py, templates
- **عدد دوال الحذف**: 8
- **عدد دوال الاستعادة**: 6
- **DeletionType Enum**: 10 أنواع
- **try-except**: شامل في كل عملية
- **التهجيرات المطلوبة**: لا يوجد ❌

---

**✅ النظام مكتمل وجاهز للنشر!**

