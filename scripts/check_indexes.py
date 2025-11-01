#!/usr/bin/env python3
"""
فحص الفهرسة (Indexes) - مقارنة Models مع DB
Check indexes comparison
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
print("🔍 فحص الفهرسة (Indexes)")
print("=" * 80)

with app.app_context():
    inspector = inspect(db.engine)
    
    # الجداول المهمة للفحص
    important_tables = [
        'branches', 'sites', 'user_branches',
        'employees', 'expenses', 'warehouses',
        'employee_deductions', 'employee_advances', 'employee_advance_installments',
        'expense_types', 'customers', 'sales', 'payments',
        'saas_plans', 'saas_subscriptions', 'saas_invoices',
    ]
    
    print(f"\n📊 فحص الفهرسة لـ {len(important_tables)} جدول مهم:\n")
    
    total_indexes = 0
    
    for table_name in important_tables:
        try:
            # الحصول على indexes من DB
            db_indexes = inspector.get_indexes(table_name)
            
            # الحصول على indexes من Model
            if table_name in db.metadata.tables:
                model_table = db.metadata.tables[table_name]
                model_indexes = [idx for idx in model_table.indexes]
                
                # عد الـ indexes
                index_count = len(db_indexes)
                total_indexes += index_count
                
                if index_count > 0:
                    print(f"✅ {table_name:<35} - {index_count} indexes")
                    # عرض التفاصيل
                    for idx in db_indexes[:3]:  # أول 3 فقط
                        cols = ', '.join(idx['column_names'])
                        unique = "unique" if idx.get('unique') else "non-unique"
                        print(f"   • {idx['name'][:40]:<40} ({cols}) [{unique}]")
                    if len(db_indexes) > 3:
                        print(f"   ... و {len(db_indexes) - 3} indexes أخرى")
                else:
                    print(f"⚠️  {table_name:<35} - لا توجد indexes")
            else:
                print(f"⚠️  {table_name:<35} - غير موجود في Models")
                
        except Exception as e:
            print(f"❌ {table_name:<35} - {e}")
    
    print("\n" + "=" * 80)
    print(f"📊 الإجمالي: {total_indexes} index")
    print("=" * 80)
    
    # فحص indexes المهمة المحددة
    print("\n🔍 فحص Indexes المهمة:\n")
    
    critical_indexes = {
        'branches': ['ix_branches_code', 'ix_branches_is_active'],
        'sites': ['ix_sites_branch_id', 'ix_sites_is_active'],
        'employees': ['ix_employees_branch_id', 'ix_employees_hire_date'],
        'expenses': ['ix_expenses_branch_id', 'ix_expenses_date'],
        'warehouses': ['ix_warehouses_branch_id'],
        'payments': ['ix_payments_payment_date', 'ix_payments_customer_id'],
        'expense_types': ['ix_expense_types_code'],
        'employee_deductions': ['ix_employee_deductions_employee_id', 'ix_employee_deductions_start_date'],
        'employee_advances': ['ix_employee_advances_employee_id', 'ix_employee_advances_advance_date'],
    }
    
    for table, expected_indexes in critical_indexes.items():
        try:
            db_indexes = inspector.get_indexes(table)
            db_index_names = [idx['name'] for idx in db_indexes]
            
            print(f"{table}:")
            for idx_name in expected_indexes:
                if idx_name in db_index_names:
                    print(f"   ✅ {idx_name}")
                else:
                    print(f"   ❌ {idx_name} (ناقص!)")
        except:
            print(f"{table}: ⚠️  غير موجود")
    
    print("\n" + "=" * 80)

