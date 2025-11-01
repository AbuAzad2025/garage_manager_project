#!/usr/bin/env python3
"""
فحص شامل لجميع الفهارس في قاعدة البيانات
Complete index audit
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask
from extensions import db
from config import Config
from sqlalchemy import inspect
import sqlite3

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

print("=" * 80)
print("🔍 فحص شامل للفهرسة في قاعدة البيانات")
print("=" * 80)

with app.app_context():
    inspector = inspect(db.engine)
    
    # الحصول على جميع الجداول
    all_tables = sorted(inspector.get_table_names())
    
    print(f"\n📊 الإحصائيات:")
    print(f"   • عدد الجداول: {len(all_tables)}")
    
    # فحص مفصل لكل جدول
    print("\n" + "=" * 80)
    print("📋 الفهرسة لكل جدول:")
    print("=" * 80)
    
    total_indexes = 0
    tables_without_indexes = []
    critical_missing = []
    
    # الأعمدة المهمة التي يجب أن تكون مفهرسة
    critical_columns = {
        # Foreign Keys
        '_id': 'FK index',
        # التواريخ
        'date': 'Date index',
        'created_at': 'Timestamp index',
        'start_date': 'Date index',
        'due_date': 'Date index',
        # الحالة
        'status': 'Status index',
        'is_active': 'Active flag index',
        'is_archived': 'Archive flag index',
        # البحث
        'code': 'Code index',
        'name': 'Name index',
        'email': 'Email index',
        'phone': 'Phone index',
    }
    
    for table_name in all_tables:
        if table_name in ['sqlite_sequence', 'alembic_version']:
            continue
        
        try:
            # الحصول على الأعمدة
            columns = inspector.get_columns(table_name)
            column_names = [col['name'] for col in columns]
            
            # الحصول على الـ indexes
            indexes = inspector.get_indexes(table_name)
            
            # جمع الأعمدة المفهرسة
            indexed_columns = set()
            for idx in indexes:
                for col in idx['column_names']:
                    indexed_columns.add(col)
            
            # فحص الأعمدة المهمة
            missing_important = []
            for col_name in column_names:
                # التحقق من الأعمدة المهمة
                for pattern, desc in critical_columns.items():
                    if pattern in col_name.lower():
                        if col_name not in indexed_columns:
                            missing_important.append((col_name, desc))
            
            # عرض النتيجة
            index_count = len(indexes)
            total_indexes += index_count
            
            if index_count > 0:
                status = "✅"
                if missing_important:
                    status = "⚠️ "
                
                print(f"\n{status} {table_name} ({index_count} indexes)")
                
                # عرض الـ indexes الموجودة
                for idx in indexes[:5]:  # أول 5
                    cols = ', '.join(idx['column_names'])
                    unique = " [UNIQUE]" if idx.get('unique') else ""
                    print(f"   ✓ {idx['name'][:50]:<50} ({cols}){unique}")
                
                if len(indexes) > 5:
                    print(f"   ... و {len(indexes) - 5} indexes أخرى")
                
                # عرض الأعمدة المهمة الناقصة
                if missing_important:
                    print(f"   💡 أعمدة مهمة بدون index:")
                    for col, desc in missing_important[:3]:
                        print(f"      • {col} ({desc})")
                        critical_missing.append(f"{table_name}.{col}")
            
            else:
                tables_without_indexes.append(table_name)
                print(f"\n⚠️  {table_name} - لا توجد indexes!")
                
        except Exception as e:
            print(f"\n❌ {table_name} - خطأ: {e}")
    
    # النتيجة النهائية
    print("\n" + "=" * 80)
    print("📊 الملخص النهائي")
    print("=" * 80)
    
    print(f"\n✅ إجمالي الـ Indexes: {total_indexes}")
    print(f"   • الجداول المفهرسة: {len(all_tables) - len(tables_without_indexes) - 2}")
    print(f"   • الجداول بدون indexes: {len(tables_without_indexes)}")
    
    if tables_without_indexes:
        print(f"\n⚠️  جداول بدون indexes ({len(tables_without_indexes)}):")
        for t in tables_without_indexes[:10]:
            print(f"   • {t}")
    
    if critical_missing:
        print(f"\n💡 أعمدة مهمة بدون indexes ({len(critical_missing)}):")
        for c in critical_missing[:15]:
            print(f"   • {c}")
        if len(critical_missing) > 15:
            print(f"   ... و {len(critical_missing) - 15} أخرى")
    
    # توصيات
    print("\n" + "=" * 80)
    print("💡 التوصيات:")
    print("=" * 80)
    
    if total_indexes >= 150:
        print("✅ الفهرسة ممتازة - النظام محسّن للأداء")
    elif total_indexes >= 100:
        print("✅ الفهرسة جيدة - يمكن إضافة المزيد للتحسين")
    else:
        print("⚠️  الفهرسة قليلة - يُنصح بإضافة المزيد")
    
    if len(critical_missing) > 0:
        print(f"💡 يُنصح بإضافة {len(critical_missing)} index للأعمدة المهمة")
    
    print("\n" + "=" * 80)

