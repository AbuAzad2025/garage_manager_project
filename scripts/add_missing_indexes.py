#!/usr/bin/env python3
"""إضافة Indexes ناقصة"""

import sqlite3

conn = sqlite3.connect('instance/app.db')
cursor = conn.cursor()

print("🔧 إضافة Indexes للأداء...\n")

indexes = [
    ("ix_branches_code", "branches", "code"),
    ("ix_branches_name", "branches", "name"),
    ("ix_sites_code", "sites", "code"),
    ("ix_sites_name", "sites", "name"),
    ("ix_user_branches_user_id", "user_branches", "user_id"),
    ("ix_user_branches_branch_id", "user_branches", "branch_id"),
    ("ix_employee_deductions_deduction_type", "employee_deductions", "deduction_type"),
    ("ix_employee_deductions_is_active", "employee_deductions", "is_active"),
    ("ix_employee_advances_fully_paid", "employee_advances", "fully_paid"),
    ("ix_employee_advance_installments_due_date", "employee_advance_installments", "due_date"),
    ("ix_employee_advance_installments_paid", "employee_advance_installments", "paid"),
]

created = 0
for idx_name, table, column in indexes:
    try:
        cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column});")
        created += 1
        print(f"   ✓ {idx_name}")
    except Exception as e:
        print(f"   ⏩ {idx_name}: {e}")

conn.commit()
conn.close()

print(f"\n✅ تم إنشاء/التحقق من {created} index!")

