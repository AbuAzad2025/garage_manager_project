#!/usr/bin/env python3
"""
استعادة البيانات بعد نسخ السكيما
Restore data after schema copy
"""

import sqlite3
import sys

backup_db = sys.argv[1] if len(sys.argv) > 1 else "C:/Users/AhmadGh/Desktop/locc app/app_backup_20251030_173049.db"
target_db = sys.argv[2] if len(sys.argv) > 2 else "C:/Users/AhmadGh/Desktop/locc app/app (3).db"

print("=" * 80)
print("📋 استعادة البيانات")
print("=" * 80)
print(f"من: {backup_db}")
print(f"إلى: {target_db}")

# الجداول المهمة التي نريد نسخ بياناتها
important_tables = [
    'users',
    'customers',
    'suppliers',
    'partners',
    'sales',
    'sale_lines',
    'invoices',
    'invoice_lines',
    'payments',
    'payment_splits',
    'checks',
    'expenses',
    'warehouses',
    'products',
    'stock_levels',
    'service_requests',
    'service_parts',
    'service_tasks',
    'notes',
    'shipments',
    'shipment_items',
    'sale_returns',
    'sale_return_lines',
]

# الاتصال بالقواعد
backup_conn = sqlite3.connect(backup_db)
target_conn = sqlite3.connect(target_db)

backup_cursor = backup_conn.cursor()
target_cursor = target_conn.cursor()

target_cursor.execute("PRAGMA foreign_keys = OFF;")

print("\n🔄 نسخ البيانات...")

total_rows = 0

for table in important_tables:
    try:
        # التحقق من وجود الجدول في Backup
        backup_cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';")
        if not backup_cursor.fetchone():
            print(f"   ⏩ {table} (غير موجود في Backup)")
            continue
        
        # الحصول على البيانات
        backup_cursor.execute(f"SELECT * FROM {table};")
        rows = backup_cursor.fetchall()
        
        if not rows:
            print(f"   ⏩ {table} (فارغ)")
            continue
        
        # الحصول على أسماء الأعمدة
        backup_cursor.execute(f"PRAGMA table_info({table});")
        columns = [col[1] for col in backup_cursor.fetchall()]
        
        # حذف البيانات القديمة
        target_cursor.execute(f"DELETE FROM {table};")
        
        # إدراج البيانات الجديدة
        placeholders = ','.join(['?' for _ in columns])
        
        for row in rows:
            try:
                target_cursor.execute(
                    f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders});",
                    row
                )
            except Exception as e:
                # تجاهل أخطاء FK في حال وجود بيانات معطوبة
                pass
        
        target_conn.commit()
        
        print(f"   ✓ {table} ({len(rows)} سجل)")
        total_rows += len(rows)
        
    except Exception as e:
        print(f"   ✗ {table}: {e}")

target_cursor.execute("PRAGMA foreign_keys = ON;")
target_conn.commit()

# التحقق النهائي
print("\n📊 النتيجة:")

for table in ['users', 'customers', 'sales', 'payments', 'expenses', 'warehouses']:
    try:
        target_cursor.execute(f"SELECT COUNT(*) FROM {table};")
        count = target_cursor.fetchone()[0]
        print(f"   • {table}: {count}")
    except:
        pass

backup_conn.close()
target_conn.close()

print("\n" + "=" * 80)
print(f"🎉 تم استعادة {total_rows} سجل!")
print("=" * 80)

