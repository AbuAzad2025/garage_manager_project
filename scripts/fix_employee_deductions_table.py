import sqlite3

conn = sqlite3.connect('instance/app.db')
cursor = conn.cursor()

cursor.execute("PRAGMA foreign_keys = OFF;")

print("🔧 تحديث جدول employee_deductions...")

# حذف الجدول القديم
cursor.execute("DROP TABLE IF EXISTS employee_deductions;")

# إنشاء الجدول الجديد (مطابق للـ Model)
cursor.execute("""
CREATE TABLE employee_deductions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    deduction_type VARCHAR(50) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'ILS' NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    notes TEXT,
    expense_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE SET NULL
);
""")

# إنشاء Indexes
cursor.execute("CREATE INDEX ix_employee_deductions_employee_id ON employee_deductions(employee_id);")
cursor.execute("CREATE INDEX ix_employee_deductions_deduction_type ON employee_deductions(deduction_type);")
cursor.execute("CREATE INDEX ix_employee_deductions_start_date ON employee_deductions(start_date);")
cursor.execute("CREATE INDEX ix_employee_deductions_end_date ON employee_deductions(end_date);")
cursor.execute("CREATE INDEX ix_employee_deductions_is_active ON employee_deductions(is_active);")
cursor.execute("CREATE INDEX ix_employee_deductions_expense_id ON employee_deductions(expense_id);")

conn.commit()
cursor.execute("PRAGMA foreign_keys = ON;")
conn.close()

print("✅ تم تحديث employee_deductions بنجاح!")

