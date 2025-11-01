import sqlite3

target = sqlite3.connect('instance/app.db')
cursor = target.cursor()

cursor.execute("PRAGMA foreign_keys = OFF;")

# إنشاء جداول SaaS
print("🔨 إنشاء جداول SaaS...")

# 1. saas_plans
cursor.execute("""
CREATE TABLE IF NOT EXISTS saas_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    price NUMERIC(12,2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'ILS' NOT NULL,
    interval VARCHAR(20) DEFAULT 'monthly' NOT NULL,
    features TEXT,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
);
""")
print("   ✓ saas_plans")

# 2. saas_subscriptions
cursor.execute("""
CREATE TABLE IF NOT EXISTS saas_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    plan_id INTEGER NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    status VARCHAR(20) DEFAULT 'active' NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES saas_plans(id) ON DELETE RESTRICT
);
""")
cursor.execute("CREATE INDEX IF NOT EXISTS ix_saas_subscriptions_customer_id ON saas_subscriptions(customer_id);")
cursor.execute("CREATE INDEX IF NOT EXISTS ix_saas_subscriptions_plan_id ON saas_subscriptions(plan_id);")
cursor.execute("CREATE INDEX IF NOT EXISTS ix_saas_subscriptions_status ON saas_subscriptions(status);")
print("   ✓ saas_subscriptions")

# 3. saas_invoices
cursor.execute("""
CREATE TABLE IF NOT EXISTS saas_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'ILS' NOT NULL,
    due_date DATE NOT NULL,
    paid_date DATE,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (subscription_id) REFERENCES saas_subscriptions(id) ON DELETE CASCADE
);
""")
cursor.execute("CREATE INDEX IF NOT EXISTS ix_saas_invoices_subscription_id ON saas_invoices(subscription_id);")
cursor.execute("CREATE INDEX IF NOT EXISTS ix_saas_invoices_status ON saas_invoices(status);")
print("   ✓ saas_invoices")

target.commit()
cursor.execute("PRAGMA foreign_keys = ON;")
target.close()

print("\n✅ تم إنشاء جميع جداول SaaS بنجاح!")

