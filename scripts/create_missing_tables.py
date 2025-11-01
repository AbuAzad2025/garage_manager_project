#!/usr/bin/env python3
"""
إنشاء الجداول الناقصة مباشرة
Create missing tables directly
"""

import sqlite3
import sys
from datetime import datetime

db_path = sys.argv[1] if len(sys.argv) > 1 else "instance/app.db"

print("=" * 80)
print("🔧 إنشاء الجداول الناقصة")
print("=" * 80)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# تعطيل FK مؤقتاً
cursor.execute("PRAGMA foreign_keys = OFF;")

print("\n1️⃣ إنشاء جدول employee_advances...")

try:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employee_advances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            amount NUMERIC(12, 2) NOT NULL,
            currency VARCHAR(10) DEFAULT 'ILS' NOT NULL,
            advance_date DATE NOT NULL,
            reason TEXT,
            total_installments INTEGER NOT NULL DEFAULT 1,
            installments_paid INTEGER DEFAULT 0 NOT NULL,
            fully_paid BOOLEAN DEFAULT 0 NOT NULL,
            notes TEXT,
            expense_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
            FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE SET NULL
        );
    """)
    
    # إنشاء Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_employee_advances_employee_id ON employee_advances(employee_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_employee_advances_advance_date ON employee_advances(advance_date);")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_employee_advances_fully_paid ON employee_advances(fully_paid);")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_employee_advances_expense_id ON employee_advances(expense_id);")
    
    print("   ✅ تم إنشاء جدول employee_advances")
    
except Exception as e:
    print(f"   ⚠️  {e}")

print("\n2️⃣ إنشاء جدول user_branches...")

try:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            is_primary BOOLEAN DEFAULT 0 NOT NULL,
            can_manage BOOLEAN DEFAULT 0 NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE CASCADE,
            UNIQUE (user_id, branch_id)
        );
    """)
    
    # إنشاء Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_user_branches_user_id ON user_branches(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_user_branches_branch_id ON user_branches(branch_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_user_branches_is_primary ON user_branches(is_primary);")
    
    print("   ✅ تم إنشاء جدول user_branches")
    
except Exception as e:
    print(f"   ⚠️  {e}")

conn.commit()

# إعادة تفعيل FK
cursor.execute("PRAGMA foreign_keys = ON;")

# التحقق النهائي
print("\n3️⃣ التحقق من الجداول...")

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('employee_advances', 'user_branches');")
created_tables = [row[0] for row in cursor.fetchall()]

for table in ['employee_advances', 'user_branches']:
    status = "✅" if table in created_tables else "❌"
    print(f"   {status} {table}")

conn.close()

print("\n" + "=" * 80)
if len(created_tables) == 2:
    print("🎉 تم إنشاء جميع الجداول الناقصة بنجاح!")
else:
    print("⚠️  بعض الجداول لم يتم إنشاؤها")
print("=" * 80)
