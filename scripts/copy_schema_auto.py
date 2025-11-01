#!/usr/bin/env python3
"""نسخ السكيما بدون تأكيد - للاستخدام التلقائي"""

import sqlite3
import sys
import os
import shutil

source_db = sys.argv[1] if len(sys.argv) > 1 else "instance/app.db"
target_db = sys.argv[2] if len(sys.argv) > 2 else "C:/Users/AhmadGh/Desktop/locc app/app (3).db"

print("=" * 80)
print("📋 نسخ السكيما التلقائي")
print("=" * 80)
print(f"المصدر: {source_db}")
print(f"الهدف: {target_db}")

# نسخة احتياطية
backup_path = target_db.replace('.db', f'_backup_schema_{os.getpid()}.db')
shutil.copy2(target_db, backup_path)
print(f"\n✅ نسخة احتياطية: {backup_path}")

# استخراج السكيما من المصدر
source_conn = sqlite3.connect(source_db)
source_cursor = source_conn.cursor()

source_cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
tables = source_cursor.fetchall()

source_cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL;")
indexes = source_cursor.fetchall()

# الحصول على آخر migration
try:
    source_cursor.execute("SELECT version_num FROM alembic_version;")
    version = source_cursor.fetchone()
except:
    version = None

source_conn.close()

print(f"\n📊 السكيما المستخرجة:")
print(f"   - {len(tables)} جدول")
print(f"   - {len(indexes)} index")
print(f"   - Migration: {version[0] if version else 'N/A'}")

# تطبيق على الهدف
target_conn = sqlite3.connect(target_db)
target_cursor = target_conn.cursor()

target_cursor.execute("PRAGMA foreign_keys = OFF;")

print(f"\n🔨 تطبيق الجداول...")

skip_tables = ['alembic_version']
created = 0

for table_name, table_sql in tables:
    if table_name in skip_tables:
        continue
    
    try:
        target_cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
        target_cursor.execute(table_sql)
        print(f"   ✓ {table_name}")
        created += 1
    except Exception as e:
        print(f"   ✗ {table_name}: {e}")

target_conn.commit()
print(f"\n   ✅ {created} جدول")

# Indexes
print(f"\n📊 تطبيق Indexes...")
index_count = 0

for index_name, index_sql in indexes:
    try:
        target_cursor.execute(f"DROP INDEX IF EXISTS {index_name};")
        target_cursor.execute(index_sql)
        index_count += 1
    except:
        pass

target_conn.commit()
print(f"   ✅ {index_count} index")

# تحديث alembic_version
if version:
    print(f"\n🔖 تحديث Migration...")
    try:
        target_cursor.execute("DELETE FROM alembic_version;")
        target_cursor.execute("INSERT INTO alembic_version (version_num) VALUES (?);", (version[0],))
        target_conn.commit()
        print(f"   ✅ {version[0]}")
    except Exception as e:
        print(f"   ⚠️ {e}")

target_cursor.execute("PRAGMA foreign_keys = ON;")

# التحقق النهائي
target_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
final_tables = target_cursor.fetchall()

target_conn.close()

print("\n" + "=" * 80)
print(f"🎉 تم النسخ بنجاح!")
print(f"📊 إجمالي الجداول: {len(final_tables)}")
print(f"💾 النسخة الاحتياطية: {backup_path}")
print("=" * 80)

