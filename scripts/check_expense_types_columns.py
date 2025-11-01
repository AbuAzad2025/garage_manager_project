import sqlite3

conn = sqlite3.connect('instance/app.db')
cursor = conn.cursor()

cursor.execute('PRAGMA table_info(expense_types);')
columns = cursor.fetchall()

print("أعمدة expense_types:")
for col in columns:
    print(f"  - {col[1]} ({col[2]})")

conn.close()

