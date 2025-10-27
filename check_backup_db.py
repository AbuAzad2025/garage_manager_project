#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔍 فحص قاعدة البيانات القديمة (Backup)
"""
import sqlite3
import sys

def check_backup_db(db_path):
    print("\n" + "="*70)
    print(f"🔍 فحص قاعدة البيانات: {db_path}")
    print("="*70 + "\n")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. فحص الدفعات
        cursor.execute("SELECT COUNT(*) FROM payments")
        total_payments = cursor.fetchone()[0]
        print(f"💰 إجمالي الدفعات: {total_payments}")
        
        if total_payments == 0:
            print("   ❌ لا توجد دفعات!")
        else:
            print(f"   ✅ توجد {total_payments} دفعة")
            
            # عينة من الدفعات
            cursor.execute("""
                SELECT id, payment_number, total_amount, status, customer_id, invoice_id, sale_id
                FROM payments 
                LIMIT 5
            """)
            print("\n   📝 أمثلة:")
            for row in cursor.fetchall():
                pid, pnum, amount, status, cust, inv, sale = row
                linked = f"→ فاتورة #{inv}" if inv else f"→ مبيعة #{sale}" if sale else ""
                print(f"      - دفعة #{pid} ({pnum}): {amount} ₪ - {status} {linked}")
        
        print()
        
        # 2. فحص الفواتير
        cursor.execute("SELECT COUNT(*) FROM invoices")
        total_invoices = cursor.fetchone()[0]
        print(f"📄 إجمالي الفواتير: {total_invoices}")
        
        if total_invoices > 0:
            # التحقق من وجود عمود status
            cursor.execute("PRAGMA table_info(invoices)")
            columns = [col[1] for col in cursor.fetchall()]
            has_status = 'status' in columns
            
            print(f"   - عمود status موجود: {'✅ نعم' if has_status else '❌ لا'}")
            
            # عينة من الفواتير
            if has_status:
                cursor.execute("""
                    SELECT id, invoice_number, total_amount, total_paid, status
                    FROM invoices 
                    LIMIT 3
                """)
                print("\n   📝 أمثلة:")
                for row in cursor.fetchall():
                    iid, inum, total, paid, status = row
                    print(f"      - فاتورة #{iid} ({inum}): {total} ₪ (مدفوع: {paid}) - {status}")
            else:
                cursor.execute("""
                    SELECT id, invoice_number, total_amount, total_paid
                    FROM invoices 
                    LIMIT 3
                """)
                print("\n   📝 أمثلة:")
                for row in cursor.fetchall():
                    iid, inum, total, paid = row
                    print(f"      - فاتورة #{iid} ({inum}): {total} ₪ (مدفوع: {paid})")
        
        print()
        
        # 3. فحص المبيعات
        cursor.execute("SELECT COUNT(*) FROM sales")
        total_sales = cursor.fetchone()[0]
        print(f"🛒 إجمالي المبيعات: {total_sales}")
        
        print()
        
        # 4. فحص العملاء
        cursor.execute("SELECT COUNT(*) FROM customers")
        total_customers = cursor.fetchone()[0]
        print(f"👥 إجمالي العملاء: {total_customers}")
        
        print()
        
        # 5. فحص دفتر الأستاذ
        cursor.execute("SELECT COUNT(*) FROM gl_batches")
        total_gl_batches = cursor.fetchone()[0]
        print(f"📒 إجمالي قيود GL: {total_gl_batches}")
        
        print()
        
        # الخلاصة
        print("="*70)
        if total_payments > 0:
            print("✅ قاعدة البيانات سليمة - الدفعات موجودة!")
            print(f"   يمكننا استعادة {total_payments} دفعة")
        else:
            print("❌ هذه القاعدة أيضاً لا تحتوي على دفعات!")
        print("="*70 + "\n")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ خطأ: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    db_path = r"C:\Users\AhmadGh\Downloads\app.db"
    check_backup_db(db_path)

