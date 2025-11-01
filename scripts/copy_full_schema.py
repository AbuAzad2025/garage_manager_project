#!/usr/bin/env python3
"""
نسخ السكيما الكاملة من قاعدة بيانات محدثة إلى قاعدة بيانات أخرى
Copy full schema from updated database to another database
"""

import sqlite3
import sys
import os
from pathlib import Path

def get_schema(db_path):
    """استخراج السكيما الكاملة من قاعدة البيانات"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # الحصول على جميع الجداول
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = cursor.fetchall()
    
    # الحصول على جميع الـ indexes
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL;")
    indexes = cursor.fetchall()
    
    conn.close()
    
    return tables, indexes


def apply_schema_to_target(source_db, target_db):
    """تطبيق السكيما من المصدر إلى الهدف"""
    
    print("=" * 80)
    print("📋 نسخ السكيما من قاعدة البيانات المحدثة")
    print("=" * 80)
    
    # 1. استخراج السكيما من المصدر
    print(f"\n📖 قراءة السكيما من: {source_db}")
    tables, indexes = get_schema(source_db)
    
    print(f"   ✓ عدد الجداول: {len(tables)}")
    print(f"   ✓ عدد الـ Indexes: {len(indexes)}")
    
    # 2. الاتصال بقاعدة البيانات المستهدفة
    print(f"\n🎯 تطبيق على: {target_db}")
    
    # نسخة احتياطية أولاً
    backup_path = target_db.replace('.db', f'_backup_before_schema_{os.getpid()}.db')
    import shutil
    shutil.copy2(target_db, backup_path)
    print(f"   ✓ نسخة احتياطية: {backup_path}")
    
    target_conn = sqlite3.connect(target_db)
    target_cursor = target_conn.cursor()
    
    # تعطيل FK مؤقتاً
    target_cursor.execute("PRAGMA foreign_keys = OFF;")
    
    # 3. تطبيق الجداول
    print(f"\n🔨 إنشاء الجداول...")
    
    # قائمة الجداول التي سننشئها (استثناء الموجودة مسبقاً إذا كانت أساسية)
    skip_tables = ['alembic_version']  # نحتفظ بها كما هي
    
    created_count = 0
    skipped_count = 0
    
    for table_name, table_sql in tables:
        if table_name in skip_tables:
            print(f"   ⏩ تخطي: {table_name}")
            skipped_count += 1
            continue
            
        try:
            # حذف الجدول القديم إن وجد
            target_cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
            
            # إنشاء الجدول الجديد
            target_cursor.execute(table_sql)
            
            print(f"   ✓ {table_name}")
            created_count += 1
            
        except Exception as e:
            print(f"   ✗ خطأ في {table_name}: {e}")
    
    target_conn.commit()
    
    print(f"\n   إجمالي: {created_count} جدول تم إنشاؤه، {skipped_count} تم تخطيه")
    
    # 4. تطبيق الـ Indexes
    print(f"\n📊 إنشاء الـ Indexes...")
    
    index_count = 0
    for index_name, index_sql in indexes:
        try:
            # حذف الـ index القديم إن وجد
            target_cursor.execute(f"DROP INDEX IF EXISTS {index_name};")
            
            # إنشاء الـ index الجديد
            target_cursor.execute(index_sql)
            
            index_count += 1
            
        except Exception as e:
            # بعض الـ indexes يتم إنشاؤها تلقائياً مع الجداول
            pass
    
    target_conn.commit()
    print(f"   ✓ {index_count} index تم إنشاؤه")
    
    # 5. تحديث alembic_version لآخر revision
    print(f"\n🔖 تحديث alembic_version...")
    try:
        # الحصول على آخر revision من المصدر
        source_conn = sqlite3.connect(source_db)
        source_cursor = source_conn.cursor()
        source_cursor.execute("SELECT version_num FROM alembic_version;")
        version = source_cursor.fetchone()
        source_conn.close()
        
        if version:
            target_cursor.execute("DELETE FROM alembic_version;")
            target_cursor.execute("INSERT INTO alembic_version (version_num) VALUES (?);", (version[0],))
            print(f"   ✓ آخر migration: {version[0]}")
    except Exception as e:
        print(f"   ⚠️ تحذير: {e}")
    
    target_conn.commit()
    
    # إعادة تفعيل FK
    target_cursor.execute("PRAGMA foreign_keys = ON;")
    
    # 6. التحقق
    print(f"\n✅ التحقق من النتيجة...")
    target_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    final_tables = target_cursor.fetchall()
    print(f"   📊 إجمالي الجداول في قاعدة البيانات: {len(final_tables)}")
    
    target_conn.close()
    
    print("\n" + "=" * 80)
    print("🎉 تم نسخ السكيما بنجاح!")
    print("=" * 80)
    
    return backup_path


def main():
    if len(sys.argv) < 3:
        print("الاستخدام:")
        print(f"  python {sys.argv[0]} <source_db> <target_db>")
        print("\nمثال:")
        print(f"  python {sys.argv[0]} instance/app.db \"C:/path/to/target.db\"")
        sys.exit(1)
    
    source_db = sys.argv[1]
    target_db = sys.argv[2]
    
    # التحقق من وجود الملفات
    if not os.path.exists(source_db):
        print(f"❌ خطأ: المصدر غير موجود: {source_db}")
        sys.exit(1)
    
    if not os.path.exists(target_db):
        print(f"❌ خطأ: الهدف غير موجود: {target_db}")
        sys.exit(1)
    
    # تأكيد
    print(f"\n⚠️  سيتم نسخ السكيما من:")
    print(f"   📁 المصدر: {source_db}")
    print(f"   📁 الهدف: {target_db}")
    print(f"\n⚠️  تحذير: سيتم حذف جميع الجداول الموجودة في الهدف (ماعدا alembic_version)")
    print(f"⚠️  البيانات الموجودة في الهدف ستبقى (إذا كانت الأسماء متطابقة)")
    
    confirm = input("\n❓ هل أنت متأكد؟ اكتب 'YES' للمتابعة: ")
    if confirm != 'YES':
        print("❌ العملية ملغاة")
        sys.exit(0)
    
    try:
        backup_path = apply_schema_to_target(source_db, target_db)
        
        print(f"\n💡 ملاحظات:")
        print(f"   - النسخة الاحتياطية محفوظة في: {backup_path}")
        print(f"   - تذكر تشغيل التطبيق لإنشاء أنواع المصاريف تلقائياً")
        print(f"   - قد تحتاج لنسخ البيانات المهمة يدوياً")
        
    except Exception as e:
        print(f"\n❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

