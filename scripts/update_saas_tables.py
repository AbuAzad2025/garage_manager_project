#!/usr/bin/env python3
"""تحديث جداول SaaS لتطابق Models"""

import sqlite3

conn = sqlite3.connect('instance/app.db')
cursor = conn.cursor()

cursor.execute("PRAGMA foreign_keys = OFF;")

print("🔧 تحديث جداول SaaS...\n")

# 1. saas_plans
print("1️⃣ تحديث saas_plans...")
cursor.execute("DROP TABLE IF EXISTS saas_plans;")
cursor.execute("""
CREATE TABLE saas_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    price_monthly NUMERIC(10,2) NOT NULL,
    price_yearly NUMERIC(10,2),
    currency VARCHAR(10) DEFAULT 'USD' NOT NULL,
    max_users INTEGER,
    max_invoices INTEGER,
    storage_gb INTEGER,
    features TEXT,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    is_popular BOOLEAN DEFAULT 0 NOT NULL,
    sort_order INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
);
""")
print("   ✓ saas_plans")

# 2. saas_subscriptions
print("\n2️⃣ تحديث saas_subscriptions...")
cursor.execute("DROP TABLE IF EXISTS saas_subscriptions;")
cursor.execute("""
CREATE TABLE saas_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    plan_id INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'trial' NOT NULL,
    start_date DATETIME NOT NULL,
    end_date DATETIME,
    trial_end_date DATETIME,
    auto_renew BOOLEAN DEFAULT 1 NOT NULL,
    cancelled_at DATETIME,
    cancelled_by INTEGER,
    cancellation_reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES saas_plans(id) ON DELETE RESTRICT,
    FOREIGN KEY (cancelled_by) REFERENCES users(id) ON DELETE SET NULL
);
""")
cursor.execute("CREATE INDEX ix_saas_subscriptions_customer_id ON saas_subscriptions(customer_id);")
cursor.execute("CREATE INDEX ix_saas_subscriptions_plan_id ON saas_subscriptions(plan_id);")
print("   ✓ saas_subscriptions")

# 3. saas_invoices
print("\n3️⃣ تحديث saas_invoices...")
cursor.execute("DROP TABLE IF EXISTS saas_invoices;")
cursor.execute("""
CREATE TABLE saas_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number VARCHAR(50) NOT NULL UNIQUE,
    subscription_id INTEGER NOT NULL,
    amount NUMERIC(10,2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'USD' NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    due_date DATETIME,
    paid_at DATETIME,
    payment_method VARCHAR(50),
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (subscription_id) REFERENCES saas_subscriptions(id) ON DELETE CASCADE
);
""")
cursor.execute("CREATE INDEX ix_saas_invoices_invoice_number ON saas_invoices(invoice_number);")
cursor.execute("CREATE INDEX ix_saas_invoices_subscription_id ON saas_invoices(subscription_id);")
print("   ✓ saas_invoices")

conn.commit()
cursor.execute("PRAGMA foreign_keys = ON;")
conn.close()

print("\n✅ تم تحديث جميع جداول SaaS بنجاح!")

