#!/usr/bin/env python3
"""
فحص الجداول الناقصة في قاعدة البيانات
Check missing tables in database
"""

import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "instance/app.db"

print("=" * 80)
print("🔍 فحص الجداول في قاعدة البيانات")
print("=" * 80)

# الجداول المتوقعة (من السكيما الكاملة)
expected_tables = [
    'alembic_version',
    'accounts',
    'archives',
    'audit_logs',
    'auth_audit',
    'branches',  # جديد
    'checks',
    'currencies',
    'customer_loyalty',
    'customer_loyalty_points',
    'customers',
    'deletion_logs',
    'employee_advance_installments',  # جديد
    'employee_advances',  # جديد
    'employee_deductions',  # جديد
    'employees',
    'equipment_types',
    'exchange_rates',
    'exchange_transactions',
    'expense_types',
    'expenses',
    'gl_batches',
    'gl_entries',
    'import_runs',
    'invoice_lines',
    'invoices',
    'notes',
    'online_cart_items',
    'online_carts',
    'online_payments',
    'online_preorder_items',
    'online_preorders',
    'partner_settlement_lines',
    'partner_settlements',
    'partners',
    'payment_splits',
    'payments',
    'permissions',
    'preorders',
    'product_categories',
    'product_partners',
    'product_rating_helpful',
    'product_ratings',
    'product_supplier_loans',
    'products',
    'role_permissions',
    'roles',
    'saas_invoices',  # جديد
    'saas_plans',  # جديد
    'saas_subscriptions',  # جديد
    'sale_lines',
    'sale_return_lines',
    'sale_returns',
    'sales',
    'service_parts',
    'service_requests',
    'service_tasks',
    'shipment_items',
    'shipment_partners',
    'shipments',
    'sites',  # جديد
    'stock_adjustment_items',
    'stock_adjustments',
    'stock_levels',
    'supplier_loan_settlements',
    'supplier_settlement_lines',
    'supplier_settlements',
    'suppliers',
    'system_settings',
    'transfers',
    'user_branches',  # جديد
    'user_permissions',
    'users',
    'utility_accounts',
    'warehouse_partner_shares',
    'warehouses',
]

# قراءة الجداول الموجودة
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
existing_tables = [row[0] for row in cursor.fetchall()]

conn.close()

print(f"\n📊 الإحصائيات:")
print(f"   • الجداول المتوقعة: {len(expected_tables)}")
print(f"   • الجداول الموجودة: {len(existing_tables)}")

# البحث عن الجداول الناقصة
missing_tables = [t for t in expected_tables if t not in existing_tables]

# البحث عن جداول إضافية (غير متوقعة)
extra_tables = [t for t in existing_tables if t not in expected_tables and not t.startswith('_alembic') and not t.startswith('sqlite_')]

print("\n" + "=" * 80)

if missing_tables:
    print(f"⚠️  الجداول الناقصة ({len(missing_tables)}):")
    for i, table in enumerate(missing_tables, 1):
        # تحديد إذا كان الجدول جديد (من التحديثات)
        is_new = table in ['branches', 'sites', 'user_branches', 'employee_deductions', 
                          'employee_advances', 'employee_advance_installments',
                          'saas_plans', 'saas_subscriptions', 'saas_invoices']
        marker = "🆕" if is_new else "⚠️ "
        print(f"   {i:2}. {marker} {table}")
else:
    print("✅ جميع الجداول المتوقعة موجودة!")

if extra_tables:
    print(f"\n💡 جداول إضافية (غير متوقعة) ({len(extra_tables)}):")
    for i, table in enumerate(extra_tables, 1):
        print(f"   {i:2}. {table}")

print("\n" + "=" * 80)
print("📋 الجداول الجديدة المهمة:")
print("=" * 80)

important_new_tables = {
    'branches': 'نظام الفروع',
    'sites': 'نظام المواقع',
    'user_branches': 'ربط المستخدمين بالفروع',
    'employee_deductions': 'خصومات الموظفين',
    'employee_advances': 'سلف الموظفين',
    'employee_advance_installments': 'أقساط السلف',
    'saas_plans': 'خطط SaaS',
    'saas_subscriptions': 'اشتراكات SaaS',
    'saas_invoices': 'فواتير SaaS',
}

for table, desc in important_new_tables.items():
    status = "✅" if table in existing_tables else "❌"
    print(f"   {status} {table:<35} - {desc}")

print("\n" + "=" * 80)

if missing_tables:
    new_missing = [t for t in missing_tables if t in important_new_tables]
    if new_missing:
        print("🔧 يجب تطبيق التهجيرات لإضافة الجداول الناقصة")
        print("   استخدم: flask db upgrade")
    sys.exit(1)
else:
    print("🎉 قاعدة البيانات محدثة بالكامل!")
    sys.exit(0)

