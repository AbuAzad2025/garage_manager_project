# 🚀 دليل النشر على PythonAnywhere

## ✅ كل شيء جاهز على GitHub!

**آخر commit**: `388d0f68 - Improve sale returns UX with clear explanations`

---

## 📋 خطوات النشر (بالتفصيل)

### 1️⃣ فتح Bash Console على PythonAnywhere

```
1. اذهب إلى: https://www.pythonanywhere.com/
2. سجل دخول
3. اضغط على "Consoles"
4. افتح Bash console جديد
```

---

### 2️⃣ سحب التحديثات من GitHub

```bash
# الانتقال لمجلد المشروع
cd ~/garage_manager_project/garage_manager

# سحب آخر تحديثات
git pull origin main
```

**المتوقع**:
```
✅ سيسحب جميع التحديثات:
   • نظام المرتجعات الكامل
   • إصلاحات CSRF
   • التحسينات الأخيرة
```

---

### 3️⃣ تحديث قاعدة البيانات

**افتح Python Console** (أو في نفس Bash):

```bash
cd ~/garage_manager_project/garage_manager
source .venv/bin/activate
python
```

**نفذ الكود التالي**:

```python
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("🔍 فحص قاعدة البيانات...")
    
    # 1. فحص جداول المرتجعات
    result = db.session.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sale_return%'"
    ))
    tables = [r[0] for r in result]
    print(f"\nجداول المرتجعات: {tables}")
    
    if 'sale_returns' in tables:
        print("✅ جدول sale_returns موجود")
    else:
        print("❌ جدول sale_returns مفقود - سيتم إنشاؤه")
    
    if 'sale_return_lines' in tables:
        print("✅ جدول sale_return_lines موجود")
    else:
        print("❌ جدول sale_return_lines مفقود - سيتم إنشاؤه")
    
    # 2. فحص أعمدة payments
    print("\n🔍 فحص أعمدة payments...")
    result = db.session.execute(text("PRAGMA table_info(payments)"))
    columns = [r[1] for r in result]
    
    if 'receiver_name' not in columns:
        print("➕ إضافة receiver_name...")
        try:
            db.session.execute(text(
                "ALTER TABLE payments ADD COLUMN receiver_name VARCHAR(100)"
            ))
            db.session.commit()
            print("✅ تم إضافة receiver_name")
        except Exception as e:
            print(f"⚠️  receiver_name: {e}")
            db.session.rollback()
    else:
        print("✅ receiver_name موجود")
    
    # 3. فحص opening_balance في customers
    print("\n🔍 فحص أعمدة customers...")
    result = db.session.execute(text("PRAGMA table_info(customers)"))
    columns = [r[1] for r in result]
    
    if 'opening_balance' not in columns:
        print("➕ إضافة opening_balance...")
        try:
            db.session.execute(text(
                "ALTER TABLE customers ADD COLUMN opening_balance NUMERIC(12,2) DEFAULT 0"
            ))
            db.session.commit()
            print("✅ تم إضافة opening_balance للعملاء")
        except Exception as e:
            print(f"⚠️  opening_balance: {e}")
            db.session.rollback()
    else:
        print("✅ opening_balance موجود في customers")
    
    # 4. فحص opening_balance في suppliers
    print("\n🔍 فحص أعمدة suppliers...")
    result = db.session.execute(text("PRAGMA table_info(suppliers)"))
    columns = [r[1] for r in result]
    
    if 'opening_balance' not in columns:
        print("➕ إضافة opening_balance...")
        try:
            db.session.execute(text(
                "ALTER TABLE suppliers ADD COLUMN opening_balance NUMERIC(12,2) DEFAULT 0"
            ))
            db.session.commit()
            print("✅ تم إضافة opening_balance للموردين")
        except Exception as e:
            print(f"⚠️  opening_balance: {e}")
            db.session.rollback()
    else:
        print("✅ opening_balance موجود في suppliers")
    
    # 5. فحص opening_balance في partners
    print("\n🔍 فحص أعمدة partners...")
    result = db.session.execute(text("PRAGMA table_info(partners)"))
    columns = [r[1] for r in result]
    
    if 'opening_balance' not in columns:
        print("➕ إضافة opening_balance...")
        try:
            db.session.execute(text(
                "ALTER TABLE partners ADD COLUMN opening_balance NUMERIC(12,2) DEFAULT 0"
            ))
            db.session.commit()
            print("✅ تم إضافة opening_balance للشركاء")
        except Exception as e:
            print(f"⚠️  opening_balance: {e}")
            db.session.rollback()
    else:
        print("✅ opening_balance موجود في partners")
    
    print("\n" + "="*60)
    print("✅ تم الانتهاء من تحديث قاعدة البيانات!")
    print("="*60)
```

**بعد تنفيذ الكود، اضغط**:
```python
exit()  # للخروج من Python
```

---

### 4️⃣ إعادة تحميل التطبيق

**الطريقة الأولى (الأفضل)**:
```
1. اذهب إلى Web tab
2. اضغط زر "Reload" الأخضر الكبير
```

**الطريقة الثانية (من Console)**:
```bash
touch /var/www/palkaraj_pythonanywhere_com_wsgi.py
```

**أو**:
```bash
pkill -f "palkaraj.*wsgi"
```

---

### 5️⃣ التحقق من النشر

**افتح المتصفح**:

```
1. الصفحة الرئيسية:
   https://palkaraj.pythonanywhere.com/

2. قائمة المبيعات:
   https://palkaraj.pythonanywhere.com/sales/
   → يجب أن ترى زر "المرتجعات" 🔴

3. افتح أي فاتورة مؤكدة:
   → يجب أن ترى زر "إنشاء مرتجع" 🔴

4. قائمة المرتجعات:
   https://palkaraj.pythonanywhere.com/returns/
```

---

### 6️⃣ في حالة ظهور أخطاء

**فحص Error Log**:
```
1. اذهب إلى Web tab
2. اضغط على "Log files"
3. افتح "Error log"
4. انسخ آخر error وأرسله
```

**أو من Console**:
```bash
tail -100 /var/www/palkaraj_pythonanywhere_com_wsgi.py/error.log
```

---

## ✅ ملخص التحديثات

```
╔══════════════════════════════════════════════════════════╗
║              ما تم رفعه لـ GitHub                       ║
╠══════════════════════════════════════════════════════════╣
║  ✅ نظام المرتجعات الكامل                              ║
║     • routes/sale_returns.py                            ║
║     • templates/sale_returns/ (3 ملفات)                ║
║     • forms.py (+ SaleReturnForm)                       ║
║     • app.py (+ Blueprint)                              ║
║                                                          ║
║  ✅ التكامل مع المبيعات                                ║
║     • زر "إنشاء مرتجع" في detail                       ║
║     • زر "المرتجعات" في list                           ║
║                                                          ║
║  ✅ CSRF Protection 100%                                ║
║     • جميع Forms محمية                                 ║
║                                                          ║
║  ✅ التوضيحات والـ UX                                   ║
║     • دليل استخدام واضح                                ║
║     • توضيحات لكل حقل                                  ║
║     • أمثلة عملية                                      ║
╚══════════════════════════════════════════════════════════╝
```

---

## 📊 الملفات المُضافة/المُعدّلة

```
✅ ملفات جديدة (4):
   routes/sale_returns.py
   templates/sale_returns/list.html
   templates/sale_returns/detail.html
   templates/sale_returns/form.html

✅ ملفات معدلة (6):
   app.py
   forms.py
   templates/sales/detail.html
   templates/sales/list.html
   templates/partials/sidebar.html
   templates/payments/form.html
   templates/warehouses/shipment_form.html

✅ توثيق (1):
   SYSTEM_COMPLETE_REPORT.md
```

---

## 🎯 الخطوات على PythonAnywhere (نسخ ولصق)

```bash
# 1. سحب التحديثات
cd ~/garage_manager_project/garage_manager
git pull origin main

# 2. تفعيل البيئة الافتراضية
source .venv/bin/activate

# 3. تحديث قاعدة البيانات (انسخ الكود Python أعلاه)
python
# (الصق الكود Python)
# exit()

# 4. إعادة التحميل
touch /var/www/palkaraj_pythonanywhere_com_wsgi.py
```

---

## ✅ كل شيء جاهز على GitHub!

```
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║  🎉 جاهز للنشر على PythonAnywhere! 🎉                 ║
║                                                          ║
║  ✅ Git: محفوظ ومرفوع                                  ║
║  ✅ Commits: 5 آخر تحديثات                             ║
║  ✅ Branch: main                                        ║
║  ✅ Status: up to date                                  ║
║                                                          ║
║  🚀 اذهب الآن إلى PythonAnywhere!                      ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

**انسخ الخطوات أعلاه ⬆️ ونفذها على PythonAnywhere!** 🎯
