import sqlite3

DB_PATH = "instance/app.db"

print("=" * 80)
print("🔍 فحص قاعدة البيانات الجديدة")
print("=" * 80)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("\n📊 البيانات الأساسية:")
print("-" * 80)

try:
    cursor.execute("SELECT COUNT(*) FROM customers")
    customers_count = cursor.fetchone()[0]
    print(f"👥 العملاء: {customers_count}")
    
    if customers_count > 0:
        cursor.execute("SELECT id, name FROM customers LIMIT 5")
        print("   أول 5 عملاء:")
        for row in cursor.fetchall():
            print(f"      • [{row[0]}] {row[1]}")
except Exception as e:
    print(f"❌ خطأ في العملاء: {e}")

try:
    cursor.execute("SELECT COUNT(*) FROM products")
    products_count = cursor.fetchone()[0]
    print(f"\n📦 المنتجات: {products_count}")
except Exception as e:
    print(f"❌ خطأ في المنتجات: {e}")

try:
    cursor.execute("SELECT COUNT(*) FROM sales")
    sales_count = cursor.fetchone()[0]
    print(f"💰 المبيعات: {sales_count}")
except Exception as e:
    print(f"❌ خطأ في المبيعات: {e}")

try:
    cursor.execute("SELECT COUNT(*) FROM payments")
    payments_count = cursor.fetchone()[0]
    print(f"💵 المدفوعات: {payments_count}")
except Exception as e:
    print(f"❌ خطأ في المدفوعات: {e}")

try:
    cursor.execute("SELECT COUNT(*) FROM expenses")
    expenses_count = cursor.fetchone()[0]
    print(f"📤 المصاريف: {expenses_count}")
except Exception as e:
    print(f"❌ خطأ في المصاريف: {e}")

try:
    cursor.execute("SELECT COUNT(*) FROM checks")
    checks_count = cursor.fetchone()[0]
    print(f"📝 الشيكات: {checks_count}")
except Exception as e:
    print(f"❌ خطأ في الشيكات: {e}")

try:
    cursor.execute("SELECT COUNT(*) FROM maintenances")
    maintenances_count = cursor.fetchone()[0]
    print(f"🔧 الصيانات: {maintenances_count}")
except Exception as e:
    print(f"❌ خطأ في الصيانات: {e}")

print("\n" + "=" * 80)
print("🔖 رقم Migration:")
print("-" * 80)
try:
    cursor.execute("SELECT version_num FROM alembic_version")
    version = cursor.fetchone()[0]
    print(f"   {version}")
except Exception as e:
    print(f"   ❌ {e}")

print("\n" + "=" * 80)
print("📋 عدد الجداول:")
print("-" * 80)
cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
tables_count = cursor.fetchone()[0]
print(f"   {tables_count} جدول")

print("=" * 80)

conn.close()


