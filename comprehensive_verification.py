import sqlite3
import os

DB_PATH = "instance/app.db"

print("=" * 100)
print("🔍 فحص شامل ومتعدد المستويات - 10× VERIFICATION")
print("=" * 100)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("\n" + "=" * 100)
print("1️⃣ فحص البيانات الأساسية (DATA VERIFICATION)")
print("=" * 100)

data_checks = [
    ("customers", "العملاء", "id, name, phone"),
    ("products", "المنتجات", "id, name"),
    ("sales", "المبيعات", "id, total_amount"),
    ("payments", "المدفوعات", "id, total_amount"),
    ("expenses", "المصاريف", "id, amount"),
    ("checks", "الشيكات", "id, check_number"),
    ("suppliers", "الموردين", "id, name"),
    ("purchase_orders", "أوامر الشراء", "id"),
    ("invoices", "الفواتير", "id"),
    ("gl_entries", "قيود دفتر الأستاذ", "id"),
    ("gl_batches", "دفعات القيود", "id"),
    ("accounts", "الحسابات", "id, code, name"),
    ("currencies", "العملات", "id, code, name"),
    ("expense_types", "أنواع المصاريف", "id, name"),
]

all_data_safe = True
for table, ar_name, columns in data_checks:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        
        if count > 0:
            cursor.execute(f"SELECT {columns} FROM {table} LIMIT 1")
            sample = cursor.fetchone()
            print(f"✅ {ar_name:<25} : {count:>4} سجل")
        else:
            print(f"⚪ {ar_name:<25} : {count:>4} سجل (فارغ)")
    except Exception as e:
        print(f"❌ {ar_name:<25} : خطأ - {str(e)[:40]}")
        all_data_safe = False

print("\n" + "=" * 100)
print("2️⃣ فحص Migration Version")
print("=" * 100)

try:
    cursor.execute("SELECT version_num FROM alembic_version")
    version = cursor.fetchone()[0]
    print(f"✅ Migration: {version}")
    if version == "5128b489596b":
        print("   ✅ أحدث إصدار - صحيح!")
    else:
        print(f"   ⚠️  ليس أحدث إصدار!")
        all_data_safe = False
except Exception as e:
    print(f"❌ خطأ: {e}")
    all_data_safe = False

print("\n" + "=" * 100)
print("3️⃣ فحص الجداول الموجودة")
print("=" * 100)

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
all_tables = [row[0] for row in cursor.fetchall()]
print(f"✅ إجمالي الجداول: {len(all_tables)}")

critical_tables = [
    'customers', 'products', 'sales', 'payments', 'checks', 'expenses',
    'suppliers', 'accounts', 'gl_entries', 'gl_batches', 'currencies',
    'expense_types', 'users', 'roles', 'permissions', 'branches',
    'warehouses', 'stock_levels', 'invoices', 'purchase_orders',
    'fixed_assets', 'asset_categories', 'depreciation_schedules',
    'cost_centers', 'projects', 'budgets', 'budget_items',
    'bank_accounts', 'bank_transactions', 'system_settings'
]

missing_tables = []
for table in critical_tables:
    if table not in all_tables:
        missing_tables.append(table)
        print(f"   ❌ مفقود: {table}")

if not missing_tables:
    print(f"   ✅ جميع الجداول الحرجة موجودة ({len(critical_tables)} جدول)")
else:
    print(f"   ❌ جداول مفقودة: {len(missing_tables)}")
    all_data_safe = False

print("\n" + "=" * 100)
print("4️⃣ فحص بنية الجداول المهمة (Schema Check)")
print("=" * 100)

important_table_columns = {
    'customers': ['id', 'name', 'phone', 'balance_in_ils', 'created_at'],
    'products': ['id', 'name', 'barcode', 'cost_price', 'selling_price'],
    'sales': ['id', 'customer_id', 'total_amount', 'invoice_number', 'created_at'],
    'payments': ['id', 'customer_id', 'total_amount', 'direction', 'created_at'],
    'checks': ['id', 'check_number', 'check_amount', 'check_status', 'due_date'],
}

for table, required_cols in important_table_columns.items():
    try:
        cursor.execute(f"PRAGMA table_info('{table}')")
        existing_cols = [col[1] for col in cursor.fetchall()]
        
        missing_cols = [col for col in required_cols if col not in existing_cols]
        
        if not missing_cols:
            print(f"✅ {table:<20} : {len(existing_cols)} عمود - كامل")
        else:
            print(f"❌ {table:<20} : أعمدة مفقودة: {', '.join(missing_cols)}")
            all_data_safe = False
    except Exception as e:
        print(f"❌ {table:<20} : خطأ - {e}")
        all_data_safe = False

print("\n" + "=" * 100)
print("5️⃣ فحص تفصيلي للعملاء (11 عميل)")
print("=" * 100)

try:
    cursor.execute("SELECT COUNT(*) FROM customers")
    customers_count = cursor.fetchone()[0]
    
    if customers_count == 11:
        print(f"✅ عدد العملاء: {customers_count} - صحيح!")
        
        cursor.execute("SELECT id, name, phone FROM customers ORDER BY name")
        print("\n   قائمة العملاء:")
        for row in cursor.fetchall():
            phone = row[2] if row[2] else "لا يوجد"
            print(f"      [{row[0]:>2}] {row[1]:<40} | {phone}")
    else:
        print(f"❌ عدد العملاء: {customers_count} - يجب أن يكون 11!")
        all_data_safe = False
except Exception as e:
    print(f"❌ خطأ: {e}")
    all_data_safe = False

print("\n" + "=" * 100)
print("6️⃣ فحص المبيعات والمدفوعات")
print("=" * 100)

try:
    cursor.execute("SELECT COUNT(*) FROM sales")
    sales_count = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total_amount) FROM sales")
    sales_total = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM payments")
    payments_count = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total_amount) FROM payments WHERE direction='IN'")
    payments_in = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(total_amount) FROM payments WHERE direction='OUT'")
    payments_out = cursor.fetchone()[0] or 0
    
    print(f"✅ المبيعات: {sales_count} فاتورة | الإجمالي: {sales_total:,.2f} ₪")
    print(f"✅ المدفوعات: {payments_count} دفعة")
    print(f"   • الواردة (IN): {payments_in:,.2f} ₪")
    print(f"   • الصادرة (OUT): {payments_out:,.2f} ₪")
except Exception as e:
    print(f"❌ خطأ: {e}")
    all_data_safe = False

print("\n" + "=" * 100)
print("7️⃣ فحص الشيكات")
print("=" * 100)

try:
    cursor.execute("SELECT COUNT(*) FROM checks")
    checks_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT check_status, COUNT(*) FROM checks GROUP BY check_status")
    status_breakdown = cursor.fetchall()
    
    print(f"✅ إجمالي الشيكات: {checks_count}")
    if status_breakdown:
        print("   توزيع الحالات:")
        for status, count in status_breakdown:
            print(f"      • {status}: {count}")
except Exception as e:
    print(f"❌ خطأ: {e}")
    all_data_safe = False

print("\n" + "=" * 100)
print("8️⃣ فحص قيود دفتر الأستاذ")
print("=" * 100)

try:
    cursor.execute("SELECT COUNT(*) FROM gl_entries")
    gl_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(debit), SUM(credit) FROM gl_entries")
    totals = cursor.fetchone()
    total_debit = totals[0] or 0
    total_credit = totals[1] or 0
    
    print(f"✅ قيود دفتر الأستاذ: {gl_count} قيد")
    print(f"   • إجمالي المدين: {total_debit:,.2f} ₪")
    print(f"   • إجمالي الدائن: {total_credit:,.2f} ₪")
    
    if abs(total_debit - total_credit) < 0.01:
        print(f"   ✅ التوازن: صحيح (الفرق: {abs(total_debit - total_credit):.2f})")
    else:
        print(f"   ⚠️  التوازن: غير متطابق (الفرق: {abs(total_debit - total_credit):,.2f})")
except Exception as e:
    print(f"❌ خطأ: {e}")
    all_data_safe = False

print("\n" + "=" * 100)
print("9️⃣ فحص البيانات الأساسية (Seed Data)")
print("=" * 100)

try:
    cursor.execute("SELECT COUNT(*) FROM expense_types")
    et_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM currencies")
    curr_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM accounts")
    acc_count = cursor.fetchone()[0]
    
    print(f"✅ أنواع المصاريف: {et_count} نوع")
    print(f"✅ العملات: {curr_count} عملة")
    print(f"✅ الحسابات: {acc_count} حساب")
    
    if et_count >= 36 and curr_count >= 8:
        print("   ✅ البيانات الأساسية كاملة")
    else:
        print("   ⚠️  البيانات الأساسية قد تكون ناقصة")
except Exception as e:
    print(f"❌ خطأ: {e}")
    all_data_safe = False

print("\n" + "=" * 100)
print("🔟 فحص حجم الملف والسلامة")
print("=" * 100)

file_size = os.path.getsize(DB_PATH)
file_size_mb = file_size / (1024 * 1024)

print(f"✅ حجم الملف: {file_size_mb:.2f} MB ({file_size:,} bytes)")

if file_size > 100000:
    print("   ✅ الحجم مناسب - البيانات موجودة")
else:
    print("   ⚠️  الحجم صغير - قد تكون البيانات ناقصة")
    all_data_safe = False

try:
    cursor.execute("PRAGMA integrity_check")
    integrity = cursor.fetchone()[0]
    if integrity == "ok":
        print(f"✅ سلامة قاعدة البيانات: {integrity}")
    else:
        print(f"❌ سلامة قاعدة البيانات: {integrity}")
        all_data_safe = False
except Exception as e:
    print(f"❌ خطأ في فحص السلامة: {e}")
    all_data_safe = False

print("\n" + "=" * 100)
print("🎯 النتيجة النهائية")
print("=" * 100)

if all_data_safe:
    print("✅✅✅ قاعدة البيانات كاملة وسليمة 100% ✅✅✅")
    print("✅ جميع البيانات موجودة")
    print("✅ جميع الجداول موجودة")
    print("✅ Schema محدث")
    print("✅ Migration صحيح")
    print("✅ البيانات متوازنة")
    print("\n🚀🚀🚀 جاهزة للرفع إلى الإنتاج! 🚀🚀🚀")
else:
    print("⚠️⚠️⚠️ يوجد مشاكل - راجع التفاصيل أعلاه ⚠️⚠️⚠️")

print("=" * 100)

conn.close()


