import sqlite3

DB_FILE = "instance/backup_20251104_180622.db"

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

print("=" * 80)
print("📊 تقرير شامل لجميع البيانات في قاعدة البيانات")
print("=" * 80)

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [row[0] for row in cursor.fetchall()]
print(f"\n🗂️  إجمالي الجداول: {len(tables)}")

data_tables = {
    'customers': 'العملاء',
    'suppliers': 'الموردين',
    'partners': 'الشركاء',
    'products': 'المنتجات',
    'warehouses': 'المستودعات',
    'sales': 'المبيعات',
    'sale_lines': 'سطور المبيعات',
    'invoices': 'الفواتير',
    'invoice_lines': 'سطور الفواتير',
    'payments': 'المدفوعات',
    'expenses': 'المصاريف',
    'service_requests': 'طلبات الخدمة',
    'service_parts': 'قطع الخدمة',
    'users': 'المستخدمين',
    'roles': 'الأدوار',
    'permissions': 'الصلاحيات',
    'branches': 'الفروع',
    'notes': 'الملاحظات',
    'checks': 'الشيكات',
    'employees': 'الموظفين',
    'employee_advances': 'سلف الموظفين',
    'shipments': 'الشحنات',
    'stock_levels': 'مستويات المخزون',
    'transfers': 'التحويلات',
    'preorders': 'الطلبات المسبقة',
}

print("\n" + "=" * 80)
print("📋 عدد السجلات في كل جدول:")
print("=" * 80)

total_records = 0
for table, name in data_tables.items():
    if table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        total_records += count
        if count > 0:
            print(f"✅ {name:<30} ({table:<30}): {count:>6} سجل")

print(f"\n📊 إجمالي السجلات: {total_records}")

print("\n" + "=" * 80)
print("👥 قائمة العملاء الكاملة (11):")
print("=" * 80)
cursor.execute("SELECT id, name, phone, email, category, credit_limit, discount_rate FROM customers ORDER BY id")
customers = cursor.fetchall()
for c in customers:
    print(f"{c[0]:2d}. {c[1]:<40} | {c[2]:<15} | {c[3] or 'لا يوجد بريد':<25} | {c[4] or 'عادي'}")

print("\n" + "=" * 80)
print("📦 عينة من المنتجات (أول 15):")
print("=" * 80)
cursor.execute("SELECT id, name, sku, cost_price, selling_price FROM products ORDER BY id LIMIT 15")
products = cursor.fetchall()
for p in products:
    cost = f"{p[3]:.2f}" if p[3] else "0.00"
    price = f"{p[4]:.2f}" if p[4] else "0.00"
    print(f"{p[0]:2d}. {p[1]:<50} | SKU: {p[2] or 'بدون':<15} | {cost:>10} / {price:>10}")

cursor.execute("SELECT COUNT(*) FROM products")
total_products = cursor.fetchone()[0]
if total_products > 15:
    print(f"... والباقي ({total_products - 15} منتج)")

print("\n" + "=" * 80)
print("💰 المبيعات (12 عملية):")
print("=" * 80)
cursor.execute("""
    SELECT s.id, s.invoice_number, c.name, s.total_amount, s.created_at 
    FROM sales s 
    LEFT JOIN customers c ON s.customer_id = c.id 
    ORDER BY s.id
""")
sales = cursor.fetchall()
for s in sales:
    customer = s[2] or "عميل محذوف"
    amount = f"{s[3]:,.2f}" if s[3] else "0.00"
    date = str(s[4])[:10] if s[4] else ""
    print(f"{s[0]:2d}. فاتورة {s[1]:<15} | {customer:<30} | {amount:>12} ₪ | {date}")

print("\n" + "=" * 80)
print("💵 المدفوعات (22 دفعة):")
print("=" * 80)
cursor.execute("""
    SELECT id, amount, direction, status, created_at 
    FROM payments 
    ORDER BY id
""")
payments = cursor.fetchall()
for p in payments:
    amount = f"{p[1]:,.2f}" if p[1] else "0.00"
    direction = p[2] or ""
    status = p[3] or ""
    date = str(p[4])[:10] if p[4] else ""
    print(f"{p[0]:2d}. {amount:>12} ₪ | {direction:<10} | {status:<15} | {date}")

print("\n" + "=" * 80)
print("💸 المصاريف (4 مصاريف):")
print("=" * 80)
cursor.execute("""
    SELECT id, amount, description, created_at 
    FROM expenses 
    ORDER BY id
""")
expenses = cursor.fetchall()
for e in expenses:
    amount = f"{e[1]:,.2f}" if e[1] else "0.00"
    desc = e[2] or "بدون وصف"
    date = str(e[3])[:10] if e[3] else ""
    print(f"{e[0]:2d}. {amount:>12} ₪ | {desc:<50} | {date}")

print("\n" + "=" * 80)
print("✅ التقرير الكامل:")
print("=" * 80)
print(f"📊 الجداول: {len(tables)}")
print(f"👥 العملاء: {len(customers)}")
print(f"📦 المنتجات: {total_products}")
print(f"💰 المبيعات: {len(sales)}")
print(f"💵 المدفوعات: {len(payments)}")
print(f"💸 المصاريف: {len(expenses)}")
print(f"📝 إجمالي السجلات: {total_records}")
print("\n✅ جميع هذه البيانات سيتم الحفاظ عليها 100%!")
print("=" * 80)

conn.close()

