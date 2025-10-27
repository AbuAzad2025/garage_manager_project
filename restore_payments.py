#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 استعادة الدفعات من النسخة الاحتياطية
"""
import sqlite3
import sys

def restore_payments(backup_db_path, target_db_path):
    print("\n" + "="*70)
    print("🔧 استعادة الدفعات")
    print("="*70 + "\n")
    
    try:
        # الاتصال بقاعدة البيانات القديمة
        backup_conn = sqlite3.connect(backup_db_path)
        backup_cursor = backup_conn.cursor()
        
        # الاتصال بقاعدة البيانات الحالية
        target_conn = sqlite3.connect(target_db_path)
        target_cursor = target_conn.cursor()
        
        # 1. التحقق من البيانات
        backup_cursor.execute("SELECT COUNT(*) FROM payments")
        backup_count = backup_cursor.fetchone()[0]
        
        target_cursor.execute("SELECT COUNT(*) FROM payments")
        target_count = target_cursor.fetchone()[0]
        
        print(f"📊 الإحصائيات:")
        print(f"   النسخة القديمة: {backup_count} دفعة")
        print(f"   النسخة الحالية: {target_count} دفعة")
        print()
        
        if backup_count == 0:
            print("❌ لا توجد دفعات في النسخة القديمة!")
            return
        
        # 2. نسخ الدفعات
        print("⏳ جاري نسخ الدفعات...")
        
        # الحصول على أسماء الأعمدة من الجدول القديم
        backup_cursor.execute("PRAGMA table_info(payments)")
        old_columns = [col[1] for col in backup_cursor.fetchall()]
        
        # الحصول على أسماء الأعمدة من الجدول الجديد
        target_cursor.execute("PRAGMA table_info(payments)")
        new_columns = [col[1] for col in target_cursor.fetchall()]
        
        # الأعمدة المشتركة
        common_columns = [col for col in old_columns if col in new_columns and col != 'id']
        
        print(f"   الأعمدة المشتركة: {len(common_columns)}")
        print()
        
        # استخراج البيانات القديمة
        columns_str = ', '.join(common_columns)
        backup_cursor.execute(f"SELECT {columns_str} FROM payments")
        payments_data = backup_cursor.fetchall()
        
        # إدراج البيانات في الجدول الجديد
        placeholders = ', '.join(['?' for _ in common_columns])
        insert_sql = f"INSERT INTO payments ({columns_str}) VALUES ({placeholders})"
        
        for payment in payments_data:
            try:
                target_cursor.execute(insert_sql, payment)
            except Exception as e:
                print(f"   ⚠️  تخطي دفعة (موجودة مسبقاً): {e}")
        
        target_conn.commit()
        
        # 3. التحقق من النجاح
        target_cursor.execute("SELECT COUNT(*) FROM payments")
        final_count = target_cursor.fetchone()[0]
        
        print("="*70)
        print(f"✅ تم النسخ بنجاح!")
        print(f"   الدفعات الآن: {final_count}")
        print(f"   تم استعادة: {final_count - target_count} دفعة")
        print("="*70 + "\n")
        
        backup_conn.close()
        target_conn.close()
        
    except Exception as e:
        print(f"❌ خطأ: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    backup_path = r"C:\Users\AhmadGh\Downloads\app.db"
    target_path = r"instance\app.db"
    
    print("⚠️  تحذير: سيتم نسخ الدفعات من النسخة الاحتياطية")
    print("   المسار القديم:", backup_path)
    print("   المسار الحالي:", target_path)
    print()
    
    response = input("هل تريد المتابعة؟ (yes/no): ")
    if response.lower() in ['yes', 'y', 'نعم']:
        restore_payments(backup_path, target_path)
    else:
        print("تم الإلغاء.")

