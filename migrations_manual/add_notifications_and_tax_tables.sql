-- Migration: Add NotificationLog and TaxEntry tables
-- Date: 2025-10-31
-- Description: إضافة جداول الإشعارات والضرائب

-- ============================================================================
-- 1. NotificationLog Table - سجل الإشعارات
-- ============================================================================

CREATE TABLE IF NOT EXISTS notification_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type VARCHAR(20) NOT NULL,  -- email, sms, whatsapp
    recipient VARCHAR(255) NOT NULL,
    subject VARCHAR(500),
    content TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, sent, failed, delivered
    provider_id VARCHAR(100),  -- Twilio SID, etc
    error_message TEXT,
    extra_data TEXT,  -- JSON metadata
    sent_at DATETIME,
    delivered_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Relations
    customer_id INTEGER,
    user_id INTEGER,
    
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Indexes for NotificationLog
CREATE INDEX IF NOT EXISTS idx_notification_type ON notification_logs(type);
CREATE INDEX IF NOT EXISTS idx_notification_recipient ON notification_logs(recipient);
CREATE INDEX IF NOT EXISTS idx_notification_status ON notification_logs(status);
CREATE INDEX IF NOT EXISTS idx_notification_created ON notification_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_notification_sent ON notification_logs(sent_at);
CREATE INDEX IF NOT EXISTS idx_notification_customer ON notification_logs(customer_id);
CREATE INDEX IF NOT EXISTS idx_notification_user ON notification_logs(user_id);


-- ============================================================================
-- 2. TaxEntry Table - سجلات الضرائب
-- ============================================================================

CREATE TABLE IF NOT EXISTS tax_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_type VARCHAR(20) NOT NULL,  -- INPUT_VAT, OUTPUT_VAT, INCOME_TAX, WITHHOLDING
    transaction_type VARCHAR(50) NOT NULL,  -- SALE, PURCHASE, SERVICE, PAYMENT
    transaction_id INTEGER,
    transaction_reference VARCHAR(50),
    
    -- Tax details
    tax_rate DECIMAL(5, 2) NOT NULL,
    base_amount DECIMAL(12, 2) NOT NULL,
    tax_amount DECIMAL(12, 2) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'ILS',
    
    -- Accounting integration
    debit_account VARCHAR(20),
    credit_account VARCHAR(20),
    gl_entry_id INTEGER,
    
    -- Period tracking
    fiscal_year INTEGER,
    fiscal_month INTEGER,
    tax_period VARCHAR(7),  -- YYYY-MM
    
    -- Status
    is_reconciled INTEGER DEFAULT 0,  -- BOOLEAN
    is_filed INTEGER DEFAULT 0,  -- BOOLEAN
    filing_reference VARCHAR(100),
    
    -- Relations
    customer_id INTEGER,
    supplier_id INTEGER,
    
    -- Metadata
    notes TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

-- Indexes for TaxEntry
CREATE INDEX IF NOT EXISTS idx_tax_entry_type ON tax_entries(entry_type);
CREATE INDEX IF NOT EXISTS idx_tax_transaction_type ON tax_entries(transaction_type);
CREATE INDEX IF NOT EXISTS idx_tax_transaction_id ON tax_entries(transaction_id);
CREATE INDEX IF NOT EXISTS idx_tax_transaction_ref ON tax_entries(transaction_reference);
CREATE INDEX IF NOT EXISTS idx_tax_fiscal_year ON tax_entries(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_tax_fiscal_month ON tax_entries(fiscal_month);
CREATE INDEX IF NOT EXISTS idx_tax_period ON tax_entries(tax_period);
CREATE INDEX IF NOT EXISTS idx_tax_reconciled ON tax_entries(is_reconciled);
CREATE INDEX IF NOT EXISTS idx_tax_filed ON tax_entries(is_filed);
CREATE INDEX IF NOT EXISTS idx_tax_customer ON tax_entries(customer_id);
CREATE INDEX IF NOT EXISTS idx_tax_supplier ON tax_entries(supplier_id);
CREATE INDEX IF NOT EXISTS idx_tax_created ON tax_entries(created_at);
CREATE INDEX IF NOT EXISTS idx_tax_period_type ON tax_entries(tax_period, entry_type);
CREATE INDEX IF NOT EXISTS idx_tax_transaction ON tax_entries(transaction_type, transaction_id);


-- ============================================================================
-- 3. Insert Default Settings for Notifications
-- ============================================================================

INSERT OR IGNORE INTO system_settings (key, value, description, data_type, is_public)
VALUES 
    ('twilio_account_sid', '', 'Twilio Account SID for SMS/WhatsApp', 'string', 0),
    ('twilio_auth_token', '', 'Twilio Auth Token', 'string', 0),
    ('twilio_phone_number', '', 'Twilio Phone Number (e.g., +1234567890)', 'string', 0),
    ('twilio_whatsapp_number', 'whatsapp:+14155238886', 'Twilio WhatsApp Number', 'string', 0),
    ('inventory_manager_phone', '', 'رقم هاتف مدير المخزون للإشعارات', 'string', 0),
    ('inventory_manager_email', '', 'بريد مدير المخزون للإشعارات', 'string', 0);


-- ============================================================================
-- Migration Complete
-- ============================================================================

-- Verification Queries
SELECT 'NotificationLog table created' as status, COUNT(*) as count FROM notification_logs;
SELECT 'TaxEntry table created' as status, COUNT(*) as count FROM tax_entries;
SELECT 'New settings added' as status, COUNT(*) as count FROM system_settings WHERE key LIKE 'twilio%' OR key LIKE 'inventory%';

