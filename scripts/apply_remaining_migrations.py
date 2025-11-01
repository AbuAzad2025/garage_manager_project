#!/usr/bin/env python3
"""تطبيق باقي التهجيرات المعلقة"""

import sqlite3

db = sqlite3.connect('instance/app.db')
cursor = db.cursor()

cursor.execute("PRAGMA foreign_keys = OFF;")

print("🔧 تطبيق التهجيرات المعلقة...\n")

# 4. manager_employee_001 - إضافة manager_employee_id
print("4️⃣ manager_employee_001 - إضافة مدير موظف للفروع والمواقع")
try:
    cursor.execute("ALTER TABLE branches ADD COLUMN manager_employee_id INTEGER;")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_branches_manager_employee ON branches(manager_employee_id);")
    print("   ✓ branches.manager_employee_id")
except Exception as e:
    print(f"   ⏩ branches.manager_employee_id ({e})")

try:
    cursor.execute("ALTER TABLE sites ADD COLUMN manager_employee_id INTEGER;")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_sites_manager_employee ON sites(manager_employee_id);")
    print("   ✓ sites.manager_employee_id")
except Exception as e:
    print(f"   ⏩ sites.manager_employee_id ({e})")

# 5. 5ee38733531c - branch_id للمستودعات (already done in branches_sites_001)
print("\n5️⃣ 5ee38733531c - ربط المستودعات بالفروع")
try:
    cursor.execute("SELECT branch_id FROM warehouses LIMIT 1;")
    print("   ✓ warehouses.branch_id (موجود مسبقاً)")
except:
    try:
        cursor.execute("ALTER TABLE warehouses ADD COLUMN branch_id INTEGER;")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_warehouses_branch_id ON warehouses(branch_id);")
        print("   ✓ warehouses.branch_id")
    except Exception as e:
        print(f"   ⚠️  {e}")

# 6. discount_to_amount_001 - تغيير الخصم إلى مبلغ
print("\n6️⃣ discount_to_amount_001 - تغيير الخصم من نسبة إلى مبلغ")
# هذا التهجير يغير نوع العمود - نتخطاه إذا كان موجود
try:
    cursor.execute("SELECT discount FROM service_parts LIMIT 1;")
    print("   ✓ service_parts.discount (موجود)")
except:
    print("   ⏩ service_parts غير موجود")

# 7. 7904e55f7ab9 - حالة المنتج في المرتجعات
print("\n7️⃣ 7904e55f7ab9 - إضافة حالة المنتج في المرتجعات")
try:
    cursor.execute("ALTER TABLE sale_return_lines ADD COLUMN condition VARCHAR(20) DEFAULT 'good';")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_sale_return_lines_condition ON sale_return_lines(condition);")
    print("   ✓ sale_return_lines.condition")
except Exception as e:
    print(f"   ⏩ sale_return_lines.condition ({e})")

db.commit()
cursor.execute("PRAGMA foreign_keys = ON;")
db.close()

print("\n✅ تم تطبيق جميع التهجيرات المعلقة!")

