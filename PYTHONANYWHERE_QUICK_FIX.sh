#!/bin/bash
# إصلاح سريع لمشكلة opening_balance على PythonAnywhere

cd ~/garage_manager_project/garage_manager
source ~/.virtualenvs/garage_manager/bin/activate

echo "================================================================"
echo "بدء إصلاح قاعدة البيانات..."
echo "================================================================"
echo ""

python3.10 << 'PYTHON_SCRIPT'
from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    print("🔍 فحص جدول customers...")
    try:
        result = db.session.execute(text("PRAGMA table_info(customers)")).fetchall()
        columns = [row[1] for row in result]
        
        if 'opening_balance' not in columns:
            print("⏳ إضافة opening_balance...")
            db.session.execute(text(
                "ALTER TABLE customers ADD COLUMN opening_balance NUMERIC(12, 2) DEFAULT 0 NOT NULL"
            ))
            db.session.commit()
            print("✅ تمت الإضافة بنجاح")
        else:
            print("✅ الحقل موجود بالفعل")
    except Exception as e:
        print(f"❌ خطأ في customers: {e}")
        db.session.rollback()
    
    print("")
    print("🔍 فحص جدول suppliers...")
    try:
        result = db.session.execute(text("PRAGMA table_info(suppliers)")).fetchall()
        columns = [row[1] for row in result]
        
        if 'opening_balance' not in columns:
            print("⏳ إضافة opening_balance...")
            db.session.execute(text(
                "ALTER TABLE suppliers ADD COLUMN opening_balance NUMERIC(12, 2) DEFAULT 0 NOT NULL"
            ))
            db.session.commit()
            print("✅ تمت الإضافة بنجاح")
        else:
            print("✅ الحقل موجود بالفعل")
    except Exception as e:
        print(f"❌ خطأ في suppliers: {e}")
        db.session.rollback()
    
    print("")
    print("🔍 فحص جدول partners...")
    try:
        result = db.session.execute(text("PRAGMA table_info(partners)")).fetchall()
        columns = [row[1] for row in result]
        
        if 'opening_balance' not in columns:
            print("⏳ إضافة opening_balance...")
            db.session.execute(text(
                "ALTER TABLE partners ADD COLUMN opening_balance NUMERIC(12, 2) DEFAULT 0 NOT NULL"
            ))
            db.session.commit()
            print("✅ تمت الإضافة بنجاح")
        else:
            print("✅ الحقل موجود بالفعل")
    except Exception as e:
        print(f"❌ خطأ في partners: {e}")
        db.session.rollback()
    
    print("")
    print("================================================================")
    print("✅ اكتمل الإصلاح!")
    print("================================================================")
PYTHON_SCRIPT

echo ""
echo "⏳ إعادة تحميل التطبيق..."
touch /var/www/palkaraj_pythonanywhere_com_wsgi.py

echo ""
echo "================================================================"
echo "✅ تم! جرب إضافة عميل الآن"
echo "================================================================"

