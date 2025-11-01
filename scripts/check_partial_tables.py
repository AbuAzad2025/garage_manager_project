import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "C:/Users/AhmadGh/Desktop/locc app/app (3).db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# فحص الجداول الجزئية
tables_to_check = ['branches', 'sites', 'user_branches', 'employee_deductions', 'employee_advances']

print("الجداول الموجودة من التهجير الجزئي:")
for table in tables_to_check:
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';")
    result = cursor.fetchone()
    if result:
        cursor.execute(f"SELECT COUNT(*) FROM {table};")
        count = cursor.fetchone()[0]
        print(f"  ✓ {table} (عدد السجلات: {count})")
    else:
        print(f"  ✗ {table} (غير موجود)")

conn.close()

