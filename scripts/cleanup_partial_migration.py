import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "C:/Users/AhmadGh/Desktop/locc app/app (3).db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# حذف الجداول الجزئية
tables_to_drop = ['branches', 'sites', 'user_branches', 'employee_deductions', 'employee_advances']

print("🧹 تنظيف الجداول الجزئية...")
for table in tables_to_drop:
    try:
        cursor.execute(f"DROP TABLE IF EXISTS {table};")
        print(f"  ✓ حذف {table}")
    except Exception as e:
        print(f"  ✗ خطأ في حذف {table}: {e}")

conn.commit()
conn.close()

print("\n✅ تم التنظيف بنجاح!")

