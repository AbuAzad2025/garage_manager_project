#!/usr/bin/env python3
"""حذف ملفات التهجير القديمة نهائياً"""

import os
from pathlib import Path

migrations_dir = Path("migrations/versions")

# الملفات القديمة المدمجة في التهجير الشامل
old_migrations = [
    "20251030_branches_sites_multibranch.py",
    "20251030_employee_enhancements.py",
    "20251030_expense_types_seed.py",
    "20251030_manager_employee.py",
    "5ee38733531c_add_branch_id_to_warehouses.py",
    "20251030_discount_to_amount.py",
    "7904e55f7ab9_add_condition_simple.py",
]

print("🗑️  حذف ملفات التهجير القديمة...\n")
print("⚠️  تحذير: هذا حذف نهائي!\n")

confirm = input("هل أنت متأكد؟ اكتب 'YES' للمتابعة: ")
if confirm != 'YES':
    print("❌ العملية ملغاة")
    exit(0)

deleted = 0
for filename in old_migrations:
    filepath = migrations_dir / filename
    if filepath.exists():
        os.remove(filepath)
        print(f"   ✓ حذف {filename}")
        deleted += 1
    else:
        print(f"   ⏩ {filename} (غير موجود)")

print(f"\n✅ تم حذف {deleted} ملف")

