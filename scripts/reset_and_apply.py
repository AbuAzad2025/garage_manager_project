#!/usr/bin/env python3
"""الرجوع والتطبيق من جديد"""

import sqlite3

db = sqlite3.connect('instance/app.db')
cursor = db.cursor()

# الرجوع للنقطة الأصلية
print("1️⃣ الرجوع إلى a8e34bc7e6bf...")
cursor.execute("UPDATE alembic_version SET version_num = 'a8e34bc7e6bf';")
db.commit()
print("   ✓ تم")

db.close()

print("\n2️⃣ الآن نفذ: flask db upgrade all_in_one_20251031")

