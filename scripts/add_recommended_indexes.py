#!/usr/bin/env python3
"""
إضافة Indexes موصى بها للأعمدة المهمة
Add recommended indexes for critical columns
"""

import sqlite3

conn = sqlite3.connect('instance/app.db')
cursor = conn.cursor()

print("=" * 80)
print("🔧 إضافة Indexes موصى بها للأداء الأمثل")
print("=" * 80)

# Indexes موصى بها للأعمدة المهمة
recommended_indexes = [
    # الجداول الصغيرة المهمة
    ("ix_currencies_code", "currencies", "code"),
    ("ix_currencies_is_active", "currencies", "is_active"),
    
    ("ix_saas_plans_is_active", "saas_plans", "is_active"),
    ("ix_saas_plans_is_popular", "saas_plans", "is_popular"),
    ("ix_saas_plans_sort_order", "saas_plans", "sort_order"),
    
    ("ix_saas_subscriptions_status", "saas_subscriptions", "status"),
    ("ix_saas_subscriptions_start_date", "saas_subscriptions", "start_date"),
    ("ix_saas_subscriptions_end_date", "saas_subscriptions", "end_date"),
    
    ("ix_saas_invoices_status", "saas_invoices", "status"),
    ("ix_saas_invoices_due_date", "saas_invoices", "due_date"),
    ("ix_saas_invoices_paid_at", "saas_invoices", "paid_at"),
    
    # الجداول المهمة
    ("ix_customers_name", "customers", "name"),
    ("ix_customers_phone", "customers", "phone"),
    ("ix_customers_email", "customers", "email"),
    ("ix_customers_is_active", "customers", "is_active"),
    
    ("ix_suppliers_name", "suppliers", "name"),
    ("ix_suppliers_phone", "suppliers", "phone"),
    ("ix_suppliers_email", "suppliers", "email"),
    
    ("ix_users_is_active", "users", "is_active"),
    ("ix_users_username", "users", "username"),
    
    ("ix_warehouses_is_active", "warehouses", "is_active"),
    ("ix_warehouses_parent_id", "warehouses", "parent_id"),
    ("ix_warehouses_supplier_id", "warehouses", "supplier_id"),
    ("ix_warehouses_partner_id", "warehouses", "partner_id"),
    
    ("ix_expense_types_is_active", "expense_types", "is_active"),
    
    ("ix_partners_phone_number", "partners", "phone_number"),
    ("ix_partners_is_active", "partners", "is_active"),
    
    # الأداء
    ("ix_products_is_active", "products", "is_active"),
    ("ix_products_vehicle_type_id", "products", "vehicle_type_id"),
    ("ix_products_commercial_name", "products", "commercial_name"),
    
    ("ix_sales_customer_date", "sales", "customer_id, sale_date"),
    ("ix_sales_is_paid", "sales", "is_paid"),
    
    ("ix_payments_entity", "payments", "entity_type, status"),
    
    ("ix_expenses_employee_date", "expenses", "employee_id, date"),
    ("ix_expenses_type_status", "expenses", "type_id, status"),
]

print("\n📦 إضافة Indexes...\n")

created = 0
skipped = 0
errors = 0

for idx_name, table, columns in recommended_indexes:
    try:
        cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({columns});")
        created += 1
        print(f"   ✅ {idx_name}")
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'duplicate' in error_msg:
            skipped += 1
            print(f"   ⏩ {idx_name} (موجود مسبقاً)")
        elif 'no such table' in error_msg:
            skipped += 1
            print(f"   ⏩ {idx_name} (جدول غير موجود)")
        else:
            errors += 1
            print(f"   ❌ {idx_name}: {e}")

conn.commit()
conn.close()

print("\n" + "=" * 80)
print("📊 النتيجة:")
print("=" * 80)
print(f"   ✅ تم الإنشاء: {created}")
print(f"   ⏩ تم التخطي: {skipped}")
if errors > 0:
    print(f"   ❌ أخطاء: {errors}")

print("\n" + "=" * 80)
print("🎉 تم تحسين الفهرسة!")
print("=" * 80)

