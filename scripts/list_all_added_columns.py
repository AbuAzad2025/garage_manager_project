#!/usr/bin/env python3
"""قائمة بجميع الأعمدة المضافة"""

import sqlite3

conn = sqlite3.connect('instance/app.db')
cursor = conn.cursor()

tables_to_check = {
    'branches': ['manager_employee_id'],
    'sites': ['manager_employee_id'],
    'employees': ['branch_id', 'site_id', 'hire_date'],
    'expenses': ['branch_id', 'site_id'],
    'warehouses': ['branch_id'],
    'sale_return_lines': ['condition', 'liability_party'],
    'expense_types': ['code', 'fields_meta'],
}

print("=" * 80)
print("🔍 فحص الأعمدة المضافة في كل جدول")
print("=" * 80)

for table, expected_cols in tables_to_check.items():
    try:
        cursor.execute(f'PRAGMA table_info({table});')
        existing_cols = [c[1] for c in cursor.fetchall()]
        
        print(f"\n📋 {table}:")
        for col in expected_cols:
            if col in existing_cols:
                print(f"   ✅ {col}")
            else:
                print(f"   ❌ {col} (ناقص!)")
    except Exception as e:
        print(f"\n❌ {table}: {e}")

conn.close()

print("\n" + "=" * 80)

