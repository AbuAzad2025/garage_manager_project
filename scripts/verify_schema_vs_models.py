#!/usr/bin/env python3
"""
التحقق من تطابق السكيما الحالية مع Models
Verify schema matches models
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask
from extensions import db
from config import Config
from sqlalchemy import inspect

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

print("=" * 80)
print("🔍 التحقق من تطابق السكيما مع Models")
print("=" * 80)

with app.app_context():
    # استيراد جميع Models
    from models import *
    
    # الحصول على جميع Models
    models_list = [
        ('User', User),
        ('Customer', Customer),
        ('Branch', Branch),
        ('Site', Site),
        ('Employee', Employee),
        ('EmployeeDeduction', EmployeeDeduction),
        ('EmployeeAdvance', EmployeeAdvance),
        ('EmployeeAdvanceInstallment', EmployeeAdvanceInstallment),
        ('Expense', Expense),
        ('ExpenseType', ExpenseType),
        ('Warehouse', Warehouse),
        ('Sale', Sale),
        ('SaleReturnLine', SaleReturnLine),
        ('ServicePart', ServicePart),
    ]
    
    inspector = inspect(db.engine)
    
    print("\n📊 فحص الجداول والأعمدة المهمة:\n")
    
    issues = []
    
    for model_name, model_class in models_list:
        try:
            table_name = model_class.__tablename__
            
            # الحصول على الأعمدة من قاعدة البيانات
            db_columns = {col['name']: col for col in inspector.get_columns(table_name)}
            
            # الحصول على الأعمدة من Model
            model_columns = {col.name: col for col in model_class.__table__.columns}
            
            # مقارنة
            missing_in_db = set(model_columns.keys()) - set(db_columns.keys())
            extra_in_db = set(db_columns.keys()) - set(model_columns.keys())
            
            if missing_in_db or extra_in_db:
                print(f"⚠️  {model_name} ({table_name}):")
                
                if missing_in_db:
                    print(f"   ❌ أعمدة ناقصة في DB: {', '.join(missing_in_db)}")
                    issues.append(f"{table_name}: missing columns {missing_in_db}")
                
                if extra_in_db:
                    print(f"   💡 أعمدة إضافية في DB: {', '.join(extra_in_db)}")
            else:
                print(f"✅ {model_name} ({table_name})")
                
        except Exception as e:
            print(f"⚠️  {model_name}: {e}")
            issues.append(f"{model_name}: {e}")
    
    print("\n" + "=" * 80)
    
    if issues:
        print(f"⚠️  وجد {len(issues)} مشكلة في التطابق")
        print("\nالمشاكل:")
        for issue in issues:
            print(f"   • {issue}")
    else:
        print("✅ جميع Models متطابقة تماماً مع السكيما!")
    
    print("=" * 80)

