#!/usr/bin/env python3
"""تحديث alembic_version للتهجير الشامل الجديد"""

import sqlite3

db = sqlite3.connect('instance/app.db')
cursor = db.cursor()

# الحصول على الحالة الحالية
cursor.execute("SELECT version_num FROM alembic_version;")
current = cursor.fetchone()

print(f"الحالة الحالية: {current[0] if current else 'N/A'}")

# التحديث
cursor.execute("UPDATE alembic_version SET version_num = 'all_in_one_20251031';")
db.commit()

cursor.execute("SELECT version_num FROM alembic_version;")
new = cursor.fetchone()

print(f"الحالة الجديدة: {new[0]}")

db.close()

print("\n✅ تم التحديث بنجاح!")

