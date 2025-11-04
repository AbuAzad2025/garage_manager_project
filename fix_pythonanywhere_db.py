import sqlite3
import shutil
from datetime import datetime

db_path = 'instance/app.db'
backup_path = f'instance/backups/db/pythonanywhere_fix_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

print(f"Creating backup: {backup_path}")
try:
    shutil.copy2(db_path, backup_path)
    print("Backup created successfully!")
except Exception as e:
    print(f"Warning: Could not create backup - {e}")

conn = sqlite3.connect(db_path)
conn.execute("PRAGMA foreign_keys = OFF")
cursor = conn.cursor()

try:
    print("\n=== 1. Fixing expenses table (PRIMARY KEY) ===")
    cursor.execute("SELECT sql FROM sqlite_master WHERE name='expenses'")
    result = cursor.fetchone()
    if result and "PRIMARY KEY" not in result[0].upper():
        cursor.execute("SELECT COUNT(*) FROM expenses")
        count = cursor.fetchone()[0]
        print(f"Found {count} expense records - needs PRIMARY KEY")
        
        cursor.execute("ALTER TABLE expenses RENAME TO expenses_old")
        cursor.execute("""
            CREATE TABLE expenses (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                date DATETIME NOT NULL,
                amount NUMERIC(12, 2) NOT NULL,
                currency VARCHAR(10) DEFAULT 'ILS' NOT NULL,
                fx_rate_used NUMERIC(10, 6),
                fx_rate_source VARCHAR(20),
                fx_rate_timestamp DATETIME,
                fx_base_currency VARCHAR(10),
                fx_quote_currency VARCHAR(10),
                type_id INTEGER NOT NULL,
                branch_id INTEGER,
                site_id INTEGER,
                employee_id INTEGER,
                warehouse_id INTEGER,
                partner_id INTEGER,
                supplier_id INTEGER,
                shipment_id INTEGER,
                utility_account_id INTEGER,
                stock_adjustment_id INTEGER,
                payee_type VARCHAR(20) DEFAULT 'OTHER' NOT NULL,
                payee_entity_id INTEGER,
                payee_name VARCHAR(200),
                beneficiary_name VARCHAR(200),
                paid_to VARCHAR(200),
                disbursed_by VARCHAR(200),
                period_start DATE,
                period_end DATE,
                payment_method VARCHAR(20) DEFAULT 'cash' NOT NULL,
                payment_details TEXT,
                description VARCHAR(200),
                notes TEXT,
                tax_invoice_number VARCHAR(100),
                check_number VARCHAR(100),
                check_bank VARCHAR(100),
                check_due_date DATE,
                check_payee VARCHAR(200),
                bank_transfer_ref VARCHAR(100),
                bank_name VARCHAR(100),
                account_number VARCHAR(100),
                account_holder VARCHAR(200),
                card_number VARCHAR(8),
                card_holder VARCHAR(120),
                card_expiry VARCHAR(10),
                online_gateway VARCHAR(50),
                online_ref VARCHAR(100),
                is_archived BOOLEAN DEFAULT 0 NOT NULL,
                archived_at DATETIME,
                archived_by INTEGER,
                archive_reason VARCHAR(200),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """)
        cursor.execute("INSERT INTO expenses SELECT * FROM expenses_old")
        cursor.execute("DROP TABLE expenses_old")
        print("Fixed expenses table!")
    else:
        print("Expenses table already OK")

    print("\n=== 2. Fixing payments FK (loan_settlements -> supplier_loan_settlements) ===")
    cursor.execute("PRAGMA foreign_key_list('payments')")
    needs_fix = any(fk[2] == 'loan_settlements' for fk in cursor.fetchall())
    
    if needs_fix:
        cursor.execute("SELECT COUNT(*) FROM payments")
        count = cursor.fetchone()[0]
        print(f"Found {count} payment records - fixing FK")
        
        cursor.execute("ALTER TABLE payments RENAME TO payments_old")
        cursor.execute("""
            CREATE TABLE payments (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                payment_number VARCHAR(50),
                payment_date DATE NOT NULL,
                subtotal NUMERIC(12, 2),
                tax_rate NUMERIC(5, 2),
                tax_amount NUMERIC(12, 2),
                total_amount NUMERIC(12, 2) NOT NULL,
                currency VARCHAR(10) DEFAULT 'ILS' NOT NULL,
                fx_rate_used NUMERIC(10, 6),
                fx_rate_source VARCHAR(20),
                fx_rate_timestamp DATETIME,
                fx_base_currency VARCHAR(10),
                fx_quote_currency VARCHAR(10),
                method VARCHAR(20) DEFAULT 'cash' NOT NULL,
                status VARCHAR(20) DEFAULT 'PENDING' NOT NULL,
                direction VARCHAR(10) NOT NULL,
                entity_type VARCHAR(50),
                reference TEXT,
                receipt_number VARCHAR(100),
                notes TEXT,
                receiver_name VARCHAR(200),
                check_number VARCHAR(100),
                check_bank VARCHAR(100),
                check_due_date DATE,
                card_holder VARCHAR(120),
                card_expiry VARCHAR(10),
                card_last4 VARCHAR(4),
                bank_transfer_ref VARCHAR(100),
                created_by INTEGER,
                customer_id INTEGER,
                supplier_id INTEGER,
                partner_id INTEGER,
                shipment_id INTEGER,
                expense_id INTEGER,
                loan_settlement_id INTEGER,
                sale_id INTEGER,
                invoice_id INTEGER,
                preorder_id INTEGER,
                service_id INTEGER,
                refund_of_id INTEGER,
                idempotency_key VARCHAR(100),
                is_archived BOOLEAN DEFAULT 0 NOT NULL,
                archived_at DATETIME,
                archived_by INTEGER,
                archive_reason VARCHAR(200),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY(loan_settlement_id) REFERENCES supplier_loan_settlements (id) ON DELETE CASCADE
            )
        """)
        cursor.execute("INSERT INTO payments SELECT * FROM payments_old")
        cursor.execute("DROP TABLE payments_old")
        print("Fixed payments FK!")
    else:
        print("Payments FK already OK")

    print("\n=== 3. Fixing supplier_settlements columns ===")
    cursor.execute("PRAGMA table_info('supplier_settlements')")
    cols = [col[1] for col in cursor.fetchall()]
    
    if 'previous_settlement_id' not in cols:
        print("Adding missing columns to supplier_settlements...")
        
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN previous_settlement_id INTEGER")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN opening_balance NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN rights_exchange NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN rights_total NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN obligations_sales NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN obligations_services NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN obligations_preorders NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN obligations_expenses NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN obligations_total NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN payments_out NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN payments_in NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN payments_returns NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN payments_net NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN closing_balance NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN is_approved BOOLEAN DEFAULT 0 NOT NULL")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN approved_by INTEGER")
        cursor.execute("ALTER TABLE supplier_settlements ADD COLUMN approved_at DATETIME")
        print("Added all missing columns!")
    else:
        print("Supplier_settlements already OK")

    print("\n=== 4. Fixing partner_settlements columns ===")
    cursor.execute("PRAGMA table_info('partner_settlements')")
    cols = [col[1] for col in cursor.fetchall()]
    
    if 'previous_settlement_id' not in cols:
        print("Adding missing columns to partner_settlements...")
        
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN previous_settlement_id INTEGER")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN opening_balance NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN rights_inventory NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN rights_sales_share NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN rights_preorders NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN rights_total NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN obligations_sales_to_partner NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN obligations_services NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN obligations_damaged NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN obligations_expenses NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN obligations_returns NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN obligations_total NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN payments_out NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN payments_in NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN payments_net NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN closing_balance NUMERIC(12, 2) DEFAULT 0")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN is_approved BOOLEAN DEFAULT 0 NOT NULL")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN approved_by INTEGER")
        cursor.execute("ALTER TABLE partner_settlements ADD COLUMN approved_at DATETIME")
        print("Added all missing columns!")
    else:
        print("Partner_settlements already OK")

    conn.commit()
    print("\n" + "="*60)
    print("SUCCESS - All fixes applied!")
    print("="*60)
    
except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
    conn.rollback()
finally:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.close()

