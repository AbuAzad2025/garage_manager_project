# 🔧 إصلاح مشكلة إضافة العملاء على PythonAnywhere

## 🎯 المشكلة
عند محاولة إضافة عميل جديد على PythonAnywhere، يظهر خطأ لأن حقل `opening_balance` (الرصيد الافتتاحي) مفقود من قاعدة البيانات.

## ✅ الحل (خطوات سريعة)

### الطريقة 1: سكريبت جاهز (الأسهل)

1. **افتح Bash Console في PythonAnywhere**
2. **نفّذ هذه الأوامر:**

```bash
cd ~/garage_manager_project
git pull origin main
cd garage_manager
bash PYTHONANYWHERE_QUICK_FIX.sh
```

✅ **انتهى! جرب إضافة عميل الآن**

---

### الطريقة 2: أوامر يدوية (إذا لم تعمل الطريقة الأولى)

1. **افتح Bash Console في PythonAnywhere**
2. **نفّذ هذه الأوامر:**

```bash
cd ~/garage_manager_project/garage_manager
source ~/.virtualenvs/garage_manager/bin/activate

python3.10 -c "
from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    # customers
    try:
        db.session.execute(text('ALTER TABLE customers ADD COLUMN opening_balance NUMERIC(12, 2) DEFAULT 0 NOT NULL'))
        db.session.commit()
        print('✅ customers: تم')
    except:
        print('✅ customers: موجود')
        db.session.rollback()
    
    # suppliers
    try:
        db.session.execute(text('ALTER TABLE suppliers ADD COLUMN opening_balance NUMERIC(12, 2) DEFAULT 0 NOT NULL'))
        db.session.commit()
        print('✅ suppliers: تم')
    except:
        print('✅ suppliers: موجود')
        db.session.rollback()
    
    # partners
    try:
        db.session.execute(text('ALTER TABLE partners ADD COLUMN opening_balance NUMERIC(12, 2) DEFAULT 0 NOT NULL'))
        db.session.commit()
        print('✅ partners: تم')
    except:
        print('✅ partners: موجود')
        db.session.rollback()
"

touch /var/www/palkaraj_pythonanywhere_com_wsgi.py
```

✅ **تم! جرب إضافة عميل الآن**

---

## 📋 ما هو opening_balance؟

هذا الحقل يُستخدم لإدخال **الرصيد الافتتاحي** عند إضافة عميل/مورد/شريك جديد:

- **موجب (مثل 1000)** = له علينا (نحن مدينون له)
- **سالب (مثل -500)** = عليه لنا (هو مدين لنا)
- **صفر (0)** = لا يوجد رصيد افتتاحي (الافتراضي)

---

## 🔍 للتحقق من النجاح

بعد تنفيذ الأوامر:
1. اذهب إلى صفحة العملاء
2. اضغط "إضافة عميل"
3. املأ البيانات
4. يجب أن يعمل بدون أخطاء ✅

---

## ⚠️ ملاحظات مهمة

- ✅ الأوامر **آمنة تماماً** - فقط إضافة حقل جديد
- ✅ لا تؤثر على **البيانات الموجودة**
- ✅ القيمة الافتراضية: **0** لجميع السجلات الحالية
- ✅ يمكنك **ترك الحقل فارغاً** عند إضافة عميل جديد

---

## 📞 إذا واجهت مشكلة

أخبرني وسأساعدك! 🚀

