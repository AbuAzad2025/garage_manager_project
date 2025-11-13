#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سكريبت لتصحيح جداول البنك على السيرفر
يصحح foreign keys من payments_old إلى payments

⚠️ مهم: اعمل backup للبيانات قبل تشغيل السكريبت!
"""
import sqlite3
import sys
from datetime import datetime
import os

if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def backup_database(db_path, backup_dir='backups'):
    """إنشاء نسخة احتياطية من قاعدة البيانات"""
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'app_db_backup_{timestamp}.db')
    
    src_conn = sqlite3.connect(db_path)
    dst_conn = sqlite3.connect(backup_path)
    src_conn.backup(dst_conn)
    src_conn.close()
    dst_conn.close()
    
    print(f"✅ تم إنشاء نسخة احتياطية: {backup_path}")
    return backup_path

def fix_database(db_path):
    """تصحيح جداول البنك"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    try:
        print("🔄 بدء تصحيح قاعدة البيانات...")
        cur.execute('PRAGMA foreign_keys=off')
        conn.commit()
        
        print("📋 1. تصحيح جدول online_payments...")
        cur.execute('SELECT COUNT(*) FROM online_payments')
        online_count = cur.fetchone()[0]
        print(f"   - عدد السجلات: {online_count}")
        
        if online_count > 0:
            cur.execute('DROP TABLE IF EXISTS online_payments_old_fix')
            cur.execute('ALTER TABLE online_payments RENAME TO online_payments_old_fix')
            conn.commit()
            
            cur.execute('''
                CREATE TABLE online_payments (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    payment_ref VARCHAR(100),
                    order_id INTEGER NOT NULL,
                    amount NUMERIC(12,2) NOT NULL,
                    currency VARCHAR(10) NOT NULL,
                    fx_rate_used NUMERIC(10,6),
                    fx_rate_source VARCHAR(20),
                    fx_rate_timestamp DATETIME,
                    fx_base_currency VARCHAR(10),
                    fx_quote_currency VARCHAR(10),
                    method VARCHAR(50),
                    gateway VARCHAR(50),
                    status VARCHAR(8) NOT NULL,
                    transaction_data JSON,
                    processed_at DATETIME,
                    card_last4 VARCHAR(4),
                    card_encrypted BLOB,
                    card_expiry VARCHAR(5),
                    cardholder_name VARCHAR(128),
                    card_brand VARCHAR(20),
                    card_fingerprint VARCHAR(64),
                    payment_id INTEGER,
                    idempotency_key VARCHAR(64),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    CONSTRAINT chk_online_payment_amount_positive CHECK (amount > 0),
                    FOREIGN KEY(order_id) REFERENCES online_preorders (id) ON DELETE CASCADE,
                    FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE SET NULL
                )
            ''')
            conn.commit()
            
            cur.execute('''
                INSERT INTO online_payments 
                (id, payment_ref, order_id, amount, currency, fx_rate_used, fx_rate_source, 
                 fx_rate_timestamp, fx_base_currency, fx_quote_currency, method, gateway, 
                 status, transaction_data, processed_at, card_last4, card_encrypted, 
                 card_expiry, cardholder_name, card_brand, card_fingerprint, payment_id, 
                 idempotency_key, created_at, updated_at)
                SELECT id, payment_ref, order_id, amount, currency, fx_rate_used, fx_rate_source,
                       fx_rate_timestamp, fx_base_currency, fx_quote_currency, method, gateway,
                       status, transaction_data, processed_at, card_last4, card_encrypted,
                       card_expiry, cardholder_name, card_brand, card_fingerprint, payment_id,
                       idempotency_key, created_at, updated_at
                FROM online_payments_old_fix
            ''')
            conn.commit()
            
            cur.execute('DROP TABLE online_payments_old_fix')
            conn.commit()
        else:
            cur.execute('DROP TABLE IF EXISTS online_payments')
            cur.execute('''
                CREATE TABLE online_payments (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    payment_ref VARCHAR(100),
                    order_id INTEGER NOT NULL,
                    amount NUMERIC(12,2) NOT NULL,
                    currency VARCHAR(10) NOT NULL,
                    fx_rate_used NUMERIC(10,6),
                    fx_rate_source VARCHAR(20),
                    fx_rate_timestamp DATETIME,
                    fx_base_currency VARCHAR(10),
                    fx_quote_currency VARCHAR(10),
                    method VARCHAR(50),
                    gateway VARCHAR(50),
                    status VARCHAR(8) NOT NULL,
                    transaction_data JSON,
                    processed_at DATETIME,
                    card_last4 VARCHAR(4),
                    card_encrypted BLOB,
                    card_expiry VARCHAR(5),
                    cardholder_name VARCHAR(128),
                    card_brand VARCHAR(20),
                    card_fingerprint VARCHAR(64),
                    payment_id INTEGER,
                    idempotency_key VARCHAR(64),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    CONSTRAINT chk_online_payment_amount_positive CHECK (amount > 0),
                    FOREIGN KEY(order_id) REFERENCES online_preorders (id) ON DELETE CASCADE,
                    FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE SET NULL
                )
            ''')
            conn.commit()
        print("   ✅ تم تصحيح online_payments")
        
        print("📋 2. تصحيح جدول checks...")
        cur.execute('SELECT COUNT(*) FROM checks')
        checks_count = cur.fetchone()[0]
        print(f"   - عدد السجلات: {checks_count}")
        
        cur.execute('DROP TABLE IF EXISTS checks_old_fix')
        cur.execute('ALTER TABLE checks RENAME TO checks_old_fix')
        conn.commit()
        
        cur.execute('''
            CREATE TABLE checks (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                check_number VARCHAR(100) NOT NULL,
                check_bank VARCHAR(200) NOT NULL,
                check_date DATETIME NOT NULL,
                check_due_date DATETIME NOT NULL,
                amount NUMERIC(12,2) NOT NULL,
                currency VARCHAR(10) NOT NULL,
                fx_rate_issue NUMERIC(10,6),
                fx_rate_issue_source VARCHAR(20),
                fx_rate_issue_timestamp DATETIME,
                fx_rate_issue_base VARCHAR(10),
                fx_rate_issue_quote VARCHAR(10),
                fx_rate_cash NUMERIC(10,6),
                fx_rate_cash_source VARCHAR(20),
                fx_rate_cash_timestamp DATETIME,
                fx_rate_cash_base VARCHAR(10),
                fx_rate_cash_quote VARCHAR(10),
                direction VARCHAR(3) NOT NULL,
                status VARCHAR(11) NOT NULL,
                drawer_name VARCHAR(200),
                drawer_phone VARCHAR(20),
                drawer_id_number VARCHAR(50),
                drawer_address TEXT,
                payee_name VARCHAR(200),
                payee_phone VARCHAR(20),
                payee_account VARCHAR(50),
                notes TEXT,
                internal_notes TEXT,
                reference_number VARCHAR(100),
                status_history TEXT,
                customer_id INTEGER,
                supplier_id INTEGER,
                partner_id INTEGER,
                created_by_id INTEGER NOT NULL,
                is_archived BOOLEAN NOT NULL,
                archived_at DATETIME,
                archived_by INTEGER,
                archive_reason VARCHAR(200),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                payment_id INTEGER,
                CONSTRAINT ck_check_amount_positive CHECK (amount > 0),
                CONSTRAINT fk_checks_payment_id FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE SET NULL,
                FOREIGN KEY(partner_id) REFERENCES partners (id) ON DELETE SET NULL,
                FOREIGN KEY(created_by_id) REFERENCES users (id),
                FOREIGN KEY(archived_by) REFERENCES users (id),
                FOREIGN KEY(supplier_id) REFERENCES suppliers (id) ON DELETE SET NULL,
                FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE SET NULL
            )
        ''')
        conn.commit()
        
        if checks_count > 0:
            cur.execute('INSERT INTO checks SELECT * FROM checks_old_fix')
            conn.commit()
        
        cur.execute('DROP TABLE checks_old_fix')
        conn.commit()
        print("   ✅ تم تصحيح checks")
        
        print("📋 3. تصحيح جدول bank_transactions...")
        cur.execute('SELECT COUNT(*) FROM bank_transactions')
        bank_tx_count = cur.fetchone()[0]
        print(f"   - عدد السجلات: {bank_tx_count}")
        
        cur.execute('DROP TABLE IF EXISTS bank_transactions_old_fix')
        cur.execute('ALTER TABLE bank_transactions RENAME TO bank_transactions_old_fix')
        conn.commit()
        
        cur.execute('''
            CREATE TABLE bank_transactions (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                bank_account_id INTEGER NOT NULL,
                statement_id INTEGER,
                transaction_date DATE NOT NULL,
                value_date DATE,
                reference VARCHAR(100),
                description TEXT,
                debit NUMERIC(15,2),
                credit NUMERIC(15,2),
                balance NUMERIC(15,2),
                matched BOOLEAN NOT NULL,
                payment_id INTEGER,
                gl_batch_id INTEGER,
                reconciliation_id INTEGER,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                created_by INTEGER,
                updated_by INTEGER,
                CONSTRAINT ck_bank_tx_debit_credit CHECK ((debit = 0 AND credit > 0) OR (credit = 0 AND debit > 0) OR (debit = 0 AND credit = 0)),
                FOREIGN KEY(bank_account_id) REFERENCES bank_accounts (id) ON DELETE CASCADE,
                FOREIGN KEY(statement_id) REFERENCES bank_statements (id) ON DELETE CASCADE,
                FOREIGN KEY(gl_batch_id) REFERENCES gl_batches (id),
                FOREIGN KEY(reconciliation_id) REFERENCES bank_reconciliations (id),
                FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE SET NULL,
                FOREIGN KEY(created_by) REFERENCES users (id),
                FOREIGN KEY(updated_by) REFERENCES users (id)
            )
        ''')
        conn.commit()
        
        if bank_tx_count > 0:
            cur.execute('INSERT INTO bank_transactions SELECT * FROM bank_transactions_old_fix')
            conn.commit()
        
        cur.execute('DROP TABLE bank_transactions_old_fix')
        conn.commit()
        print("   ✅ تم تصحيح bank_transactions")
        
        cur.execute('PRAGMA foreign_keys=on')
        conn.commit()
        
        print("\n✅ تم تصحيح جميع الجداول بنجاح!")
        print(f"📊 الإحصائيات:")
        print(f"   - online_payments: {online_count} سجل")
        print(f"   - checks: {checks_count} سجل")
        print(f"   - bank_transactions: {bank_tx_count} سجل")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ خطأ في التصحيح: {str(e)}")
        print("⚠️ تم عمل rollback - لم يتم تطبيق أي تغييرات")
        raise
    
    finally:
        conn.close()

if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'instance/app.db'
    
    if not os.path.exists(db_path):
        print(f"❌ ملف قاعدة البيانات غير موجود: {db_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("🔧 سكريبت تصحيح جداول البنك على السيرفر")
    print("=" * 60)
    print(f"📁 مسار قاعدة البيانات: {db_path}")
    print()
    
    skip_input = '--yes' in sys.argv or '-y' in sys.argv
    if not skip_input:
        try:
            response = input("⚠️ هل قمت بعمل backup للبيانات؟ (yes/no): ")
            if response.lower() != 'yes':
                print("❌ الرجاء عمل backup قبل المتابعة!")
                sys.exit(1)
        except EOFError:
            print("⚠️ تشغيل بدون تأكيد (استخدم --yes للتمرير التلقائي)")
            skip_input = True
    
    print("\n🔄 إنشاء نسخة احتياطية إضافية...")
    backup_path = backup_database(db_path)
    
    print("\n🚀 بدء التصحيح...")
    fix_database(db_path)
    
    print("\n✅ تم الانتهاء بنجاح!")

