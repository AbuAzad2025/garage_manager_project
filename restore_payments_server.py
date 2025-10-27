#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 استعادة الدفعات على السيرفر
يجب رفع ملف app.db القديم (من Downloads) إلى ~/garage_manager_project/backup_with_payments.db
"""
import sqlite3
import sys
import os

def restore_payments():
    print("\n" + "="*70)
    print("🔧 استعادة الدفعات على السيرفر")
    print("="*70 + "\n")
    
    # المسارات
    backup_path = os.path.expanduser("~/garage_manager_project/backup_with_payments.db")
    target_path = os.path.expanduser("~/garage_manager_project/instance/app.db")
    
    # التحقق من وجود النسخة الاحتياطية
    if not os.path.exists(backup_path):
        print("❌ لم يتم العثور على النسخة الاحتياطية!")
        print(f"   المسار المتوقع: {backup_path}")
        print()
        print("📝 الخطوات:")
        print("   1. افتح PythonAnywhere → Files")
        print("   2. اذهب إلى ~/garage_manager_project/")
        print("   3. ارفع ملف app.db القديم (من Downloads)")
        print("   4. أعد تسميته إلى: backup_with_payments.db")
        print("   5. شغّل هذا السكريبت مرة أخرى")
        return
    
    try:
        # الاتصال بقاعدة البيانات القديمة
        backup_conn = sqlite3.connect(backup_path)
        backup_cursor = backup_conn.cursor()
        
        # الاتصال بقاعدة البيانات الحالية
        target_conn = sqlite3.connect(target_path)
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
        
        # 2. حذف الدفعات الحالية (إن وجدت)
        if target_count > 0:
            print("⏳ حذف الدفعات الحالية...")
            target_cursor.execute("DELETE FROM payments")
            print("   ✅ تم الحذف")
            print()
        
        # 3. نسخ الدفعات
        print("⏳ جاري نسخ الدفعات...")
        
        # الحصول على أسماء الأعمدة من الجدول القديم
        backup_cursor.execute("PRAGMA table_info(payments)")
        old_columns = [col[1] for col in backup_cursor.fetchall()]
        
        # الحصول على أسماء الأعمدة من الجدول الجديد
        target_cursor.execute("PRAGMA table_info(payments)")
        new_columns = [col[1] for col in target_cursor.fetchall()]
        
        # الأعمدة المشتركة
        common_columns = [col for col in old_columns if col in new_columns]
        
        print(f"   الأعمدة المشتركة: {len(common_columns)}")
        print()
        
        # استخراج البيانات القديمة
        columns_str = ', '.join(common_columns)
        backup_cursor.execute(f"SELECT {columns_str} FROM payments")
        payments_data = backup_cursor.fetchall()
        
        # إدراج البيانات في الجدول الجديد
        placeholders = ', '.join(['?' for _ in common_columns])
        insert_sql = f"INSERT INTO payments ({columns_str}) VALUES ({placeholders})"
        
        success_count = 0
        for payment in payments_data:
            try:
                target_cursor.execute(insert_sql, payment)
                success_count += 1
            except Exception as e:
                print(f"   ⚠️  تخطي دفعة: {e}")
        
        target_conn.commit()
        
        # 4. التحقق من النجاح
        target_cursor.execute("SELECT COUNT(*) FROM payments")
        final_count = target_cursor.fetchone()[0]
        
        print("="*70)
        print(f"✅ تم النسخ بنجاح!")
        print(f"   الدفعات المستعادة: {success_count}")
        print(f"   الدفعات الآن: {final_count}")
        print("="*70 + "\n")
        
        print("🚀 لإعادة تحميل التطبيق:")
        print("   touch /var/www/palkaraj_pythonanywhere_com_wsgi.py")
        print()
        
        backup_conn.close()
        target_conn.close()
        
    except Exception as e:
        print(f"❌ خطأ: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    restore_payments()

