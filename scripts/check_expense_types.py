import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "C:/Users/AhmadGh/Desktop/locc app/app (3).db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM expense_types;')
total = cursor.fetchone()[0]

print(f"✅ أنواع المصاريف: {total}")

if total > 0:
    print("\n📋 الأنواع الموجودة:")
    cursor.execute('SELECT name, code, is_active FROM expense_types ORDER BY id;')
    for i, (name, code, is_active) in enumerate(cursor.fetchall(), 1):
        status = "✓" if is_active else "✗"
        print(f"   {i:2}. {status} {name} ({code})")

conn.close()

