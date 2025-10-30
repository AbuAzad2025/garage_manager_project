-- إنشاء الجداول المفقودة للنظام متعدد الفروع
-- SQLite Safe Script

-- 1. جدول employee_deductions
CREATE TABLE IF NOT EXISTS employee_deductions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    deduction_type VARCHAR(50) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'ILS',
    start_date DATE NOT NULL,
    end_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    notes TEXT,
    expense_id INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_employee_deductions_employee_id ON employee_deductions(employee_id);
CREATE INDEX IF NOT EXISTS ix_employee_deductions_type ON employee_deductions(deduction_type);
CREATE INDEX IF NOT EXISTS ix_employee_deductions_is_active ON employee_deductions(is_active);

-- 2. جدول employee_advance_installments
CREATE TABLE IF NOT EXISTS employee_advance_installments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    advance_expense_id INTEGER NOT NULL,
    installment_number INTEGER NOT NULL,
    total_installments INTEGER NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'ILS',
    due_date DATE NOT NULL,
    paid BOOLEAN NOT NULL DEFAULT 0,
    paid_date DATE,
    salary_expense_id INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (advance_expense_id) REFERENCES expenses(id) ON DELETE CASCADE,
    FOREIGN KEY (salary_expense_id) REFERENCES expenses(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_advance_installments_employee_id ON employee_advance_installments(employee_id);
CREATE INDEX IF NOT EXISTS ix_advance_installments_due_date ON employee_advance_installments(due_date);
CREATE INDEX IF NOT EXISTS ix_advance_installments_paid ON employee_advance_installments(paid);

-- 3. جدول sites
CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER NOT NULL,
    name VARCHAR(120) NOT NULL,
    code VARCHAR(32) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    address VARCHAR(200),
    geo_lat NUMERIC(10, 6),
    geo_lng NUMERIC(10, 6),
    manager_user_id INTEGER,
    notes TEXT,
    is_archived BOOLEAN NOT NULL DEFAULT 0,
    archived_at DATETIME,
    archived_by INTEGER,
    archive_reason VARCHAR(200),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE CASCADE,
    FOREIGN KEY (manager_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (archived_by) REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE (branch_id, code),
    UNIQUE (branch_id, name)
);

CREATE INDEX IF NOT EXISTS ix_sites_branch_id ON sites(branch_id);
CREATE INDEX IF NOT EXISTS ix_sites_is_active ON sites(is_active);

-- 4. جدول user_branches
CREATE TABLE IF NOT EXISTS user_branches (
    user_id INTEGER NOT NULL,
    branch_id INTEGER NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, branch_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_user_branches_user ON user_branches(user_id);
CREATE INDEX IF NOT EXISTS ix_user_branches_branch ON user_branches(branch_id);

-- 5. إنشاء indexes إضافية
CREATE INDEX IF NOT EXISTS ix_employees_branch_id ON employees(branch_id);
CREATE INDEX IF NOT EXISTS ix_employees_site_id ON employees(site_id);
CREATE INDEX IF NOT EXISTS ix_expenses_branch_id ON expenses(branch_id);
CREATE INDEX IF NOT EXISTS ix_expenses_site_id ON expenses(site_id);
CREATE INDEX IF NOT EXISTS ix_expenses_branch_date ON expenses(branch_id, date);
CREATE INDEX IF NOT EXISTS ix_employees_branch_name ON employees(branch_id, name);

-- تم بنجاح
SELECT '✅ تم إنشاء جميع الجداول والفهارس المفقودة' AS status;

