#!/usr/bin/env python3
"""
دمج ملفات WAL و SHM في قاعدة البيانات الرئيسية
Sync WAL and checkpoint to main database file
"""

import sqlite3
import sys
import os
from pathlib import Path

db_path = sys.argv[1] if len(sys.argv) > 1 else "C:/Users/AhmadGh/Desktop/locc app/app (3).db"

print("=" * 80)
print("🔄 دمج ملفات WAL و SHM في قاعدة البيانات الرئيسية")
print("=" * 80)

# التحقق من الملفات
print(f"\n📍 قاعدة البيانات: {db_path}")

db_file = Path(db_path)
wal_file = Path(f"{db_path}-wal")
shm_file = Path(f"{db_path}-shm")

print(f"\n📋 فحص الملفات:")
print(f"   • {db_file.name}: {'✅ موجود' if db_file.exists() else '❌ غير موجود'} ({db_file.stat().st_size if db_file.exists() else 0} bytes)")
print(f"   • {wal_file.name}: {'✅ موجود' if wal_file.exists() else '❌ غير موجود'} ({wal_file.stat().st_size if wal_file.exists() else 0} bytes)")
print(f"   • {shm_file.name}: {'✅ موجود' if shm_file.exists() else '❌ غير موجود'} ({shm_file.stat().st_size if shm_file.exists() else 0} bytes)")

# الاتصال وعمل checkpoint
print(f"\n🔧 عمل Checkpoint...")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # عمل WAL checkpoint لدمج جميع التغييرات
    cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    result = cursor.fetchone()
    
    print(f"   ✅ Checkpoint ناجح")
    print(f"   📊 النتيجة: {result}")
    
    # التحقق من حالة WAL
    cursor.execute("PRAGMA journal_mode;")
    journal_mode = cursor.fetchone()[0]
    print(f"   📋 Journal mode: {journal_mode}")
    
    conn.close()
    
    print(f"\n📋 حالة الملفات بعد Checkpoint:")
    print(f"   • {db_file.name}: {db_file.stat().st_size if db_file.exists() else 0} bytes")
    print(f"   • {wal_file.name}: {'✅ موجود' if wal_file.exists() else '❌ تم الدمج'} ({wal_file.stat().st_size if wal_file.exists() else 0} bytes)")
    print(f"   • {shm_file.name}: {'✅ موجود' if shm_file.exists() else '❌ تم الحذف'} ({shm_file.stat().st_size if shm_file.exists() else 0} bytes)")
    
except Exception as e:
    print(f"   ❌ خطأ: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("📝 ملاحظات مهمة:")
print("=" * 80)
print("""
ℹ️  ملفات WAL و SHM:
   • هذه الملفات جزء من نظام WAL (Write-Ahead Logging) في SQLite
   • تحسن الأداء والموثوقية
   • يجب نسخها مع قاعدة البيانات للحفاظ على التغييرات الأخيرة

✅ بعد Checkpoint:
   • جميع التغييرات تم دمجها في الملف الرئيسي (.db)
   • يمكن نسخ الملف الرئيسي بأمان الآن
   • ملفات WAL و SHM سيتم إعادة إنشائها تلقائياً عند الاستخدام

💡 للنشر على سيرفر:
   1. عمل checkpoint (هذا السكريبت)
   2. نسخ الملف الرئيسي (.db) فقط
   3. أو نسخ الثلاثة ملفات معاً للأمان الكامل
""")

print("=" * 80)
print("🎉 تم الانتهاء!")
print("=" * 80)

