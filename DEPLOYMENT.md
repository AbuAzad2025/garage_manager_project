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

## 💰 النظام المحاسبي الآلي - Auto Accounting System

### ✅ ما تم تطبيقه:
1. **GLBatch تلقائي للمبيعات** (`after_insert`, `after_update`, `after_delete`)
2. **GLBatch تلقائي للدفعات** (`after_insert`, `after_update`, `after_delete`)
3. **GLBatch تلقائي للمصروفات** (`after_insert`, `after_update`, `after_delete`)
4. **GLBatch للرصيد الافتتاحي** (عملاء، موردين، شركاء)
5. **حذف GLBatch تلقائياً** عند الحذف القوي أو العادي

### 📊 دليل الحسابات (Chart of Accounts):
- `1000_CASH`: النقدية - الصندوق
- `1010_BANK`: البنك - الحساب الجاري
- `1020_CARD_CLEARING`: مقاصة البطاقات
- `1100_AR`: حسابات العملاء - المدينون
- `1200_INVENTORY`: المخزون
- `1205_INV_EXCHANGE`: مخزون العهدة
- `2000_AP`: حسابات الموردين - الدائنون
- `2100_VAT_PAYABLE`: ضريبة القيمة المضافة
- `3000_EQUITY`: رأس المال
- `3100_RETAINED_EARNINGS`: الأرباح المحتجزة
- `4000_SALES`: إيرادات المبيعات
- `4100_SERVICE_REVENUE`: إيرادات الصيانة
- `5000_EXPENSES`: المصروفات العامة
- `5100_COGS`: تكلفة البضاعة المباعة
- `5105_COGS_EXCHANGE`: تكلفة بضاعة العهدة المباعة

### 🚀 إنشاء الحسابات على PythonAnywhere (مرة واحدة فقط):

**الخطوة 1: إصلاح payment_method إذا كانت بحروف كبيرة:**
```bash
cd ~/garage_manager_project
python3.10 << 'EOF'
from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    # إصلاح payment_method - تحويل الحروف الكبيرة لصغيرة
    result = db.session.execute(text("""
        UPDATE payments 
        SET method = LOWER(method)
        WHERE method IN ('CARD', 'BANK', 'CASH', 'CHEQUE', 'ONLINE')
    """))
    db.session.commit()
    print(f'✅ تم إصلاح {result.rowcount} دفعة')
EOF
```

**الخطوة 2: إنشاء دليل الحسابات:**
```bash
python3.10 << 'EOF'
from app import create_app
from models import Account, db

app = create_app()
with app.app_context():
    accounts = [
        {"code": "1000_CASH", "name": "النقدية - الصندوق", "type": "ASSET", "is_active": True},
        {"code": "1010_BANK", "name": "البنك - الحساب الجاري", "type": "ASSET", "is_active": True},
        {"code": "1020_CARD_CLEARING", "name": "مقاصة البطاقات", "type": "ASSET", "is_active": True},
        {"code": "1100_AR", "name": "حسابات العملاء - المدينون", "type": "ASSET", "is_active": True},
        {"code": "1200_INVENTORY", "name": "المخزون", "type": "ASSET", "is_active": True},
        {"code": "1205_INV_EXCHANGE", "name": "مخزون العهدة", "type": "ASSET", "is_active": True},
        {"code": "2000_AP", "name": "حسابات الموردين - الدائنون", "type": "LIABILITY", "is_active": True},
        {"code": "2100_VAT_PAYABLE", "name": "ضريبة القيمة المضافة", "type": "LIABILITY", "is_active": True},
        {"code": "3000_EQUITY", "name": "رأس المال", "type": "EQUITY", "is_active": True},
        {"code": "3100_RETAINED_EARNINGS", "name": "الأرباح المحتجزة", "type": "EQUITY", "is_active": True},
        {"code": "4000_SALES", "name": "إيرادات المبيعات", "type": "REVENUE", "is_active": True},
        {"code": "4100_SERVICE_REVENUE", "name": "إيرادات الصيانة", "type": "REVENUE", "is_active": True},
        {"code": "5000_EXPENSES", "name": "المصروفات العامة", "type": "EXPENSE", "is_active": True},
        {"code": "5100_COGS", "name": "تكلفة البضاعة المباعة", "type": "EXPENSE", "is_active": True},
        {"code": "5105_COGS_EXCHANGE", "name": "تكلفة بضاعة العهدة المباعة", "type": "EXPENSE", "is_active": True},
    ]
    
    for acc_data in accounts:
        existing = Account.query.filter_by(code=acc_data['code']).first()
        if not existing:
            acc = Account(**acc_data)
            db.session.add(acc)
    
    db.session.commit()
    total = Account.query.filter_by(is_active=True).count()
    print(f'✅ دليل الحسابات جاهز ({total} حساب)')
EOF

touch /var/www/palkaraj_pythonanywhere_com_wsgi.py
```

### 🔍 الرصيد الافتتاحي:
- ✅ يظهر في كشف الحساب (أول سطر)
- ✅ يظهر في التسويات الذكية
- ✅ يُنشئ GLBatch تلقائياً
- ✅ يؤثر على جميع التقارير المحاسبية

---

## 📊 الملخص التقني
- **الملفات المعدلة**: 
  - `models.py` (+ accounting listeners)
  - `routes/customers.py` (+ opening_balance في كشف الحساب)
  - `routes/vendors.py` (+ opening_balance للموردين والشركاء)
  - `routes/supplier_settlements.py` (+ opening_balance في التسويات)
  - `routes/partner_settlements.py` (+ opening_balance في التسويات)
  - `services/hard_delete_service.py` (+ حذف GLBatch للدفعات)
  - `templates` (+ badges للرصيد الافتتاحي)
- **Accounting Listeners**: 9 (Sale, Payment, Expense, Customer OB, Supplier OB, Partner OB + موجود مسبقاً: Service, Shipment, Exchange)
- **GLBatch Auto-Create**: ✅ تلقائي 100%
- **GLBatch Auto-Update**: ✅ عند التعديل
- **GLBatch Auto-Delete**: ✅ عند الحذف
- **التهجيرات المطلوبة**: لا يوجد ❌ (فقط إنشاء دليل الحسابات مرة واحدة)

---

**✅ النظام المحاسبي مكتمل وجاهز للنشر!**

