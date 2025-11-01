#!/usr/bin/env python3
"""
إصلاح البيانات الحالية لتتوافق مع الجداول الجديدة
Fix existing data for new schema
"""

import sqlite3
import sys
from datetime import datetime

db_path = sys.argv[1] if len(sys.argv) > 1 else "C:/Users/AhmadGh/Desktop/locc app/app (3).db"

print("=" * 80)
print("🔧 إصلاح البيانات للتوافق مع الجداول الجديدة")
print("=" * 80)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# تعطيل FK مؤقتاً
cursor.execute("PRAGMA foreign_keys = OFF;")

# 1. إنشاء فرع رئيسي
print("\n1️⃣ إنشاء الفرع الرئيسي...")

cursor.execute("SELECT COUNT(*) FROM branches;")
branch_count = cursor.fetchone()[0]

if branch_count == 0:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO branches (
            name, code, is_active, 
            address, city, 
            currency, 
            is_archived, 
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        "الفرع الرئيسي",  # name
        "MAIN",            # code
        1,                 # is_active
        "",                # address
        "",                # city
        "ILS",             # currency
        0,                 # is_archived
        now,               # created_at
        now                # updated_at
    ))
    
    branch_id = cursor.lastrowid
    print(f"   ✅ تم إنشاء الفرع الرئيسي (ID: {branch_id})")
else:
    cursor.execute("SELECT id, name FROM branches ORDER BY id LIMIT 1;")
    branch_id, branch_name = cursor.fetchone()
    print(f"   ℹ️  يوجد فرع مسبقاً: {branch_name} (ID: {branch_id})")

conn.commit()

# 2. ربط المصاريف بالفرع الرئيسي
print("\n2️⃣ ربط المصاريف بالفرع الرئيسي...")

cursor.execute("SELECT COUNT(*) FROM expenses WHERE branch_id IS NULL;")
expenses_without_branch = cursor.fetchone()[0]

if expenses_without_branch > 0:
    cursor.execute("UPDATE expenses SET branch_id = ? WHERE branch_id IS NULL;", (branch_id,))
    conn.commit()
    print(f"   ✅ تم ربط {expenses_without_branch} مصروف بالفرع الرئيسي")
else:
    print(f"   ✅ جميع المصاريف مرتبطة بفروع")

# 3. ربط المستودعات بالفرع الرئيسي
print("\n3️⃣ ربط المستودعات بالفرع الرئيسي...")

cursor.execute("SELECT COUNT(*) FROM warehouses WHERE branch_id IS NULL;")
warehouses_without_branch = cursor.fetchone()[0]

if warehouses_without_branch > 0:
    cursor.execute("UPDATE warehouses SET branch_id = ? WHERE branch_id IS NULL;", (branch_id,))
    conn.commit()
    print(f"   ✅ تم ربط {warehouses_without_branch} مستودع بالفرع الرئيسي")
else:
    print(f"   ✅ جميع المستودعات مرتبطة بفروع")

# 4. ربط المستخدمين بالفرع (إذا لزم الأمر)
print("\n4️⃣ ربط المستخدمين بالفرع الرئيسي...")

try:
    cursor.execute("SELECT COUNT(*) FROM users WHERE branch_id IS NULL;")
    users_without_branch = cursor.fetchone()[0]
    
    if users_without_branch > 0:
        cursor.execute("UPDATE users SET branch_id = ? WHERE branch_id IS NULL;", (branch_id,))
        conn.commit()
        print(f"   ✅ تم ربط {users_without_branch} مستخدم بالفرع الرئيسي")
    else:
        print(f"   ✅ جميع المستخدمين مرتبطين بفروع")
except Exception as e:
    print(f"   ℹ️  {e}")

# إعادة تفعيل FK
cursor.execute("PRAGMA foreign_keys = ON;")

# التحقق النهائي
print("\n" + "=" * 80)
print("✅ التحقق النهائي")
print("=" * 80)

# عرض الإحصائيات
print("\n📊 الإحصائيات:")

cursor.execute("SELECT COUNT(*) FROM branches;")
print(f"   • الفروع: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM expenses WHERE branch_id IS NOT NULL;")
print(f"   • مصاريف مرتبطة بفروع: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM warehouses WHERE branch_id IS NOT NULL;")
print(f"   • مستودعات مرتبطة بفروع: {cursor.fetchone()[0]}")

try:
    cursor.execute("SELECT COUNT(*) FROM users WHERE branch_id IS NOT NULL;")
    print(f"   • مستخدمين مرتبطين بفروع: {cursor.fetchone()[0]}")
except:
    pass

conn.close()

print("\n" + "=" * 80)
print("🎉 تم إصلاح البيانات بنجاح!")
print("=" * 80)

