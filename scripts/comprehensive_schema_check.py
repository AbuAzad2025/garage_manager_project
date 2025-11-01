#!/usr/bin/env python3
"""
فحص شامل للتطابق بين Models وقاعدة البيانات
Comprehensive schema validation
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask
from extensions import db
from config import Config
from sqlalchemy import inspect, MetaData

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

print("=" * 80)
print("🔍 فحص شامل للتطابق بين Models وقاعدة البيانات")
print("=" * 80)

with app.app_context():
    # استيراد جميع Models
    import models
    
    # الحصول على inspector
    inspector = inspect(db.engine)
    db_tables = set(inspector.get_table_names())
    
    # الحصول على جميع Models من metadata
    model_tables = set(db.metadata.tables.keys())
    
    print(f"\n📊 الإحصائيات:")
    print(f"   • جداول في Models: {len(model_tables)}")
    print(f"   • جداول في DB: {len(db_tables)}")
    
    # الفحص الأول: جداول ناقصة في DB
    missing_in_db = model_tables - db_tables
    if missing_in_db:
        print(f"\n❌ جداول ناقصة في DB ({len(missing_in_db)}):")
        for table in sorted(missing_in_db):
            print(f"   • {table}")
    
    # الفحص الثاني: جداول إضافية في DB
    extra_in_db = db_tables - model_tables - {'alembic_version', 'sqlite_sequence'}
    if extra_in_db:
        print(f"\n💡 جداول إضافية في DB ({len(extra_in_db)}):")
        for table in sorted(extra_in_db):
            print(f"   • {table}")
    
    # الفحص الثالث: مقارنة الأعمدة لكل جدول
    print("\n" + "=" * 80)
    print("📋 فحص الأعمدة لكل جدول:")
    print("=" * 80)
    
    issues = []
    checked_tables = 0
    
    for table_name in sorted(model_tables):
        if table_name not in db_tables:
            continue
        
        checked_tables += 1
        
        # الأعمدة من Model
        model_table = db.metadata.tables[table_name]
        model_columns = {col.name: col for col in model_table.columns}
        
        # الأعمدة من DB
        db_columns = {col['name']: col for col in inspector.get_columns(table_name)}
        
        # مقارنة
        missing_cols = set(model_columns.keys()) - set(db_columns.keys())
        extra_cols = set(db_columns.keys()) - set(model_columns.keys())
        
        if missing_cols or extra_cols:
            print(f"\n⚠️  {table_name}:")
            
            if missing_cols:
                print(f"   ❌ أعمدة ناقصة في DB:")
                for col in sorted(missing_cols):
                    col_type = str(model_columns[col].type)
                    print(f"      • {col} ({col_type})")
                    issues.append(f"{table_name}.{col}")
            
            if extra_cols:
                print(f"   💡 أعمدة إضافية في DB:")
                for col in sorted(extra_cols):
                    print(f"      • {col}")
        else:
            print(f"✅ {table_name} ({len(model_columns)} أعمدة)")
    
    print("\n" + "=" * 80)
    print("📊 النتيجة النهائية")
    print("=" * 80)
    
    print(f"\n✅ تم فحص {checked_tables} جدول")
    
    if not missing_in_db and not issues:
        print("\n🎉 جميع الجداول والأعمدة متطابقة تماماً!")
        print("   ✅ Models = DB")
        print("   ✅ جاهز للإنتاج 100%")
    else:
        if missing_in_db:
            print(f"\n❌ {len(missing_in_db)} جدول ناقص")
        if issues:
            print(f"\n❌ {len(issues)} عمود ناقص")
        
        print("\n💡 يجب تطبيق التهجيرات أو إضافة الأعمدة الناقصة")
    
    print("\n" + "=" * 80)

