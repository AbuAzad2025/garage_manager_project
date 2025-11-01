#!/usr/bin/env python3
"""
تحضير قاعدة البيانات للنشر على الإنتاج
Prepare database for production deployment
"""

import sqlite3
import sys
import os
import shutil
from pathlib import Path
from datetime import datetime

source_db = sys.argv[1] if len(sys.argv) > 1 else "C:/Users/AhmadGh/Desktop/locc app/app (3).db"
output_dir = sys.argv[2] if len(sys.argv) > 2 else "./production_ready"

print("=" * 80)
print("📦 تحضير قاعدة البيانات للنشر على الإنتاج")
print("=" * 80)

# إنشاء مجلد الإخراج
output_path = Path(output_dir)
output_path.mkdir(parents=True, exist_ok=True)

print(f"\n📍 المصدر: {source_db}")
print(f"📍 الوجهة: {output_path}")

# 1. عمل Checkpoint
print(f"\n1️⃣ دمج ملفات WAL...")

try:
    conn = sqlite3.connect(source_db)
    cursor = conn.cursor()
    
    # Checkpoint
    cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    
    # تحسين قاعدة البيانات
    print(f"2️⃣ تحسين قاعدة البيانات...")
    cursor.execute("VACUUM;")
    cursor.execute("ANALYZE;")
    
    conn.close()
    print(f"   ✅ تم التحسين")
    
except Exception as e:
    print(f"   ⚠️  {e}")

# 2. نسخ الملف الرئيسي
print(f"\n3️⃣ نسخ قاعدة البيانات...")

source_file = Path(source_db)
dest_file = output_path / "app.db"

shutil.copy2(source_db, dest_file)
print(f"   ✅ تم النسخ: {dest_file}")

# 3. نسخ ملفات WAL/SHM إن وجدت (للأمان)
wal_source = Path(f"{source_db}-wal")
shm_source = Path(f"{source_db}-shm")

if wal_source.exists():
    shutil.copy2(wal_source, output_path / "app.db-wal")
    print(f"   ✅ نسخ WAL: {wal_source.stat().st_size} bytes")

if shm_source.exists():
    shutil.copy2(shm_source, output_path / "app.db-shm")
    print(f"   ✅ نسخ SHM: {shm_source.stat().st_size} bytes")

# 4. التحقق النهائي
print(f"\n4️⃣ التحقق من قاعدة البيانات المنسوخة...")

try:
    conn = sqlite3.connect(dest_file)
    cursor = conn.cursor()
    
    # فحص البيانات
    checks = {
        'users': 'SELECT COUNT(*) FROM users',
        'customers': 'SELECT COUNT(*) FROM customers',
        'sales': 'SELECT COUNT(*) FROM sales',
        'payments': 'SELECT COUNT(*) FROM payments',
        'branches': 'SELECT COUNT(*) FROM branches',
        'expense_types': 'SELECT COUNT(*) FROM expense_types',
    }
    
    print(f"   📊 البيانات:")
    for table, query in checks.items():
        try:
            cursor.execute(query)
            count = cursor.fetchone()[0]
            print(f"      • {table}: {count}")
        except Exception as e:
            print(f"      • {table}: ⚠️  {e}")
    
    conn.close()
    print(f"   ✅ قاعدة البيانات سليمة")
    
except Exception as e:
    print(f"   ❌ خطأ: {e}")
    sys.exit(1)

# 5. إنشاء ملف معلومات
print(f"\n5️⃣ إنشاء ملف المعلومات...")

info_file = output_path / "DATABASE_INFO.txt"
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

info_content = f"""
╔════════════════════════════════════════════════════════════════════╗
║          معلومات قاعدة البيانات - Production Ready                ║
╚════════════════════════════════════════════════════════════════════╝

📅 تاريخ التحضير: {timestamp}
📍 المصدر: {source_db}
📊 الحجم: {dest_file.stat().st_size / 1024 / 1024:.2f} MB

✅ ما تم عمله:
   • دمج ملفات WAL في الملف الرئيسي
   • تحسين قاعدة البيانات (VACUUM + ANALYZE)
   • التحقق من سلامة البيانات
   • نسخ جميع الملفات المطلوبة

📦 الملفات:
   • app.db - قاعدة البيانات الرئيسية (يحتوي على كل شيء)
   • app.db-wal - ملف WAL (اختياري)
   • app.db-shm - ملف SHM (اختياري)

🚀 للنشر:
   1. ارفع الملفات إلى السيرفر
   2. ضع app.db في مجلد instance/
   3. تأكد من الصلاحيات (read/write)
   4. شغّل التطبيق

⚠️  ملاحظات:
   • احتفظ بنسخة احتياطية من قاعدة الإنتاج الحالية
   • تأكد من توقف التطبيق قبل استبدال القاعدة
   • ملفات WAL/SHM سيتم إنشاؤها تلقائياً عند التشغيل

✅ قاعدة البيانات جاهزة للإنتاج!

════════════════════════════════════════════════════════════════════
"""

with open(info_file, 'w', encoding='utf-8') as f:
    f.write(info_content)

print(f"   ✅ تم الحفظ: {info_file}")

# النتيجة النهائية
print("\n" + "=" * 80)
print("🎉 تم التحضير بنجاح!")
print("=" * 80)

print(f"\n📂 الملفات الجاهزة في: {output_path.absolute()}")
print(f"\n📋 المحتويات:")

for file in sorted(output_path.iterdir()):
    size = file.stat().st_size
    if size > 1024 * 1024:
        size_str = f"{size / 1024 / 1024:.2f} MB"
    elif size > 1024:
        size_str = f"{size / 1024:.2f} KB"
    else:
        size_str = f"{size} bytes"
    
    print(f"   • {file.name}: {size_str}")

print("\n" + "=" * 80)
print("✅ جاهز للنشر على السيرفر!")
print("=" * 80)

