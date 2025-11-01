#!/usr/bin/env python3
"""نقل ملفات التهجير القديمة إلى أرشيف"""

import shutil
from pathlib import Path

migrations_dir = Path("migrations/versions")
archive_dir = migrations_dir / "_archived"
archive_dir.mkdir(exist_ok=True)

# الملفات القديمة التي تم دمجها في التهجير الشامل
old_migrations = [
    "20251030_branches_sites_multibranch.py",
    "20251030_employee_enhancements.py",
    "20251030_expense_types_seed.py",
    "20251030_manager_employee.py",
    "5ee38733531c_add_branch_id_to_warehouses.py",
    "20251030_discount_to_amount.py",
    "7904e55f7ab9_add_condition_simple.py",
]

print("📦 نقل ملفات التهجير القديمة إلى الأرشيف...\n")

moved = 0
for filename in old_migrations:
    source = migrations_dir / filename
    if source.exists():
        dest = archive_dir / filename
        shutil.move(str(source), str(dest))
        print(f"   ✓ {filename}")
        moved += 1
    else:
        print(f"   ⏩ {filename} (غير موجود)")

print(f"\n✅ تم نقل {moved} ملف إلى: {archive_dir}")

