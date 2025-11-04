import sqlite3

conn = sqlite3.connect('instance/app.db')
cursor = conn.cursor()

print("=== Checking for triggers ===")
cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
triggers = cursor.fetchall()
for trigger in triggers:
    print(f"\nTrigger: {trigger[0]}")
    if trigger[1] and 'expenses_old' in trigger[1]:
        print("  ** REFERENCES expenses_old **")
        print(trigger[1])

print("\n\n=== Checking for views ===")
cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='view'")
views = cursor.fetchall()
for view in views:
    print(f"\nView: {view[0]}")
    if view[1] and 'expenses_old' in view[1]:
        print("  ** REFERENCES expenses_old **")
        print(view[1])

print("\n\n=== Checking all tables for foreign keys ===")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
for table in tables:
    table_name = table[0]
    cursor.execute(f"PRAGMA foreign_key_list('{table_name}')")
    fks = cursor.fetchall()
    for fk in fks:
        if 'expenses_old' in str(fk[2]):
            print(f"\n** Table {table_name} has FK to expenses_old **")
            print(fk)

print("\n\n=== Checking employee_advances table ===")
cursor.execute("SELECT sql FROM sqlite_master WHERE name='employee_advances'")
result = cursor.fetchone()
if result:
    print(result[0])

conn.close()

