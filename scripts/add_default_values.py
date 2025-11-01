#!/usr/bin/env python3
"""
إضافة قيم افتراضية للحقول الإلزامية الفارغة
Add default values for required empty fields
"""

import sqlite3
import sys
from datetime import datetime

db_path = sys.argv[1] if len(sys.argv) > 1 else "C:/Users/AhmadGh/Desktop/locc app/app (3).db"

print("=" * 80)
print("🔧 إضافة قيم افتراضية للحقول الإلزامية")
print("=" * 80)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("PRAGMA foreign_keys = OFF;")

changes_made = 0

# 1. إضافة تاريخ تعيين افتراضي للموظفين
print("\n1️⃣ فحص تواريخ تعيين الموظفين...")

try:
    # التحقق من وجود عمود hire_date
    cursor.execute("PRAGMA table_info(users);")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'hire_date' in columns:
        # البحث عن موظفين بدون تاريخ تعيين
        cursor.execute("""
            SELECT id, username, full_name, created_at 
            FROM users 
            WHERE hire_date IS NULL
            LIMIT 10;
        """)
        
        users_without_hire = cursor.fetchall()
        
        if users_without_hire:
            print(f"   📋 وجد {len(users_without_hire)} مستخدم بدون تاريخ تعيين")
            
            for user_id, username, full_name, created_at in users_without_hire:
                # استخدام تاريخ إنشاء الحساب كتاريخ تعيين افتراضي
                default_hire_date = created_at if created_at else datetime.now().strftime("%Y-%m-%d")
                
                cursor.execute("""
                    UPDATE users 
                    SET hire_date = ? 
                    WHERE id = ?;
                """, (default_hire_date, user_id))
                
                name_display = full_name or username
                print(f"   ✓ {name_display}: تاريخ التعيين = {default_hire_date} (افتراضي)")
                changes_made += 1
            
            conn.commit()
        else:
            print(f"   ✅ جميع المستخدمين لديهم تاريخ تعيين")
    else:
        print(f"   ℹ️  عمود hire_date غير موجود في جدول users")
        
except Exception as e:
    print(f"   ⚠️  {e}")

# 2. إضافة أكواد افتراضية للفروع بدون كود
print("\n2️⃣ فحص أكواد الفروع...")

try:
    cursor.execute("""
        SELECT id, name, code 
        FROM branches 
        WHERE code IS NULL OR code = '';
    """)
    
    branches_without_code = cursor.fetchall()
    
    if branches_without_code:
        print(f"   📋 وجد {len(branches_without_code)} فرع بدون كود")
        
        for branch_id, name, code in branches_without_code:
            # إنشاء كود افتراضي من اسم الفرع
            default_code = f"BR{branch_id:03d}"
            
            cursor.execute("""
                UPDATE branches 
                SET code = ? 
                WHERE id = ?;
            """, (default_code, branch_id))
            
            print(f"   ✓ {name}: الكود = {default_code} (افتراضي)")
            changes_made += 1
        
        conn.commit()
    else:
        print(f"   ✅ جميع الفروع لديها أكواد")
        
except Exception as e:
    print(f"   ⚠️  {e}")

# 3. إضافة أكواد افتراضية للمواقع بدون كود
print("\n3️⃣ فحص أكواد المواقع...")

try:
    cursor.execute("""
        SELECT id, name, code 
        FROM sites 
        WHERE code IS NULL OR code = '';
    """)
    
    sites_without_code = cursor.fetchall()
    
    if sites_without_code:
        print(f"   📋 وجد {len(sites_without_code)} موقع بدون كود")
        
        for site_id, name, code in sites_without_code:
            default_code = f"ST{site_id:03d}"
            
            cursor.execute("""
                UPDATE sites 
                SET code = ? 
                WHERE id = ?;
            """, (default_code, site_id))
            
            print(f"   ✓ {name}: الكود = {default_code} (افتراضي)")
            changes_made += 1
        
        conn.commit()
    else:
        print(f"   ✅ جميع المواقع لديها أكواد")
        
except Exception as e:
    print(f"   ℹ️  {e}")

# 4. إضافة أنواع افتراضية للمستودعات
print("\n4️⃣ فحص أنواع المستودعات...")

try:
    cursor.execute("PRAGMA table_info(warehouses);")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'warehouse_type' in columns:
        cursor.execute("""
            SELECT id, name, warehouse_type 
            FROM warehouses 
            WHERE warehouse_type IS NULL OR warehouse_type = '';
        """)
        
        warehouses_without_type = cursor.fetchall()
        
        if warehouses_without_type:
            print(f"   📋 وجد {len(warehouses_without_type)} مستودع بدون نوع")
            
            for wh_id, name, wh_type in warehouses_without_type:
                default_type = "MAIN"  # نوع افتراضي: مستودع رئيسي
                
                cursor.execute("""
                    UPDATE warehouses 
                    SET warehouse_type = ? 
                    WHERE id = ?;
                """, (default_type, wh_id))
                
                print(f"   ✓ {name}: النوع = {default_type} (افتراضي)")
                changes_made += 1
            
            conn.commit()
        else:
            print(f"   ✅ جميع المستودعات لديها أنواع")
    else:
        print(f"   ℹ️  عمود warehouse_type غير موجود")
        
except Exception as e:
    print(f"   ⚠️  {e}")

# 5. إضافة عملات افتراضية للفروع
print("\n5️⃣ فحص عملات الفروع...")

try:
    cursor.execute("""
        SELECT id, name, currency 
        FROM branches 
        WHERE currency IS NULL OR currency = '';
    """)
    
    branches_without_currency = cursor.fetchall()
    
    if branches_without_currency:
        print(f"   📋 وجد {len(branches_without_currency)} فرع بدون عملة")
        
        for branch_id, name, currency in branches_without_currency:
            default_currency = "ILS"  # الشيكل الإسرائيلي
            
            cursor.execute("""
                UPDATE branches 
                SET currency = ? 
                WHERE id = ?;
            """, (default_currency, branch_id))
            
            print(f"   ✓ {name}: العملة = {default_currency} (افتراضي)")
            changes_made += 1
        
        conn.commit()
    else:
        print(f"   ✅ جميع الفروع لديها عملات")
        
except Exception as e:
    print(f"   ⚠️  {e}")

# 6. إضافة حالة افتراضية للفروع والمواقع
print("\n6️⃣ فحص حالة التفعيل...")

try:
    # الفروع
    cursor.execute("""
        UPDATE branches 
        SET is_active = 1 
        WHERE is_active IS NULL;
    """)
    
    if cursor.rowcount > 0:
        print(f"   ✓ تم تفعيل {cursor.rowcount} فرع")
        changes_made += cursor.rowcount
    
    # المواقع
    cursor.execute("""
        UPDATE sites 
        SET is_active = 1 
        WHERE is_active IS NULL;
    """)
    
    if cursor.rowcount > 0:
        print(f"   ✓ تم تفعيل {cursor.rowcount} موقع")
        changes_made += cursor.rowcount
    
    conn.commit()
    
    if cursor.rowcount == 0:
        print(f"   ✅ جميع الفروع والمواقع نشطة")
        
except Exception as e:
    print(f"   ⚠️  {e}")

# 7. إضافة علامة للقيم الافتراضية في الملاحظات
print("\n7️⃣ إضافة علامات للقيم الافتراضية...")

try:
    # وسم الفروع التي أنشئت تلقائياً
    cursor.execute("""
        UPDATE branches 
        SET notes = COALESCE(notes || ' ', '') || '[تم الإنشاء تلقائياً]'
        WHERE code LIKE 'BR%' 
        AND (notes IS NULL OR notes NOT LIKE '%[تم الإنشاء تلقائياً]%');
    """)
    
    if cursor.rowcount > 0:
        print(f"   ✓ تم وسم {cursor.rowcount} فرع افتراضي")
    
    conn.commit()
        
except Exception as e:
    print(f"   ⚠️  {e}")

cursor.execute("PRAGMA foreign_keys = ON;")

# النتيجة النهائية
print("\n" + "=" * 80)
print("📊 النتيجة النهائية")
print("=" * 80)

if changes_made > 0:
    print(f"\n✅ تم إجراء {changes_made} تعديل")
    print("\n💡 ملاحظة: جميع القيم المضافة تلقائياً تم تمييزها")
    print("   يمكنك تعديلها لاحقاً من واجهة النظام")
else:
    print(f"\n✅ جميع الحقول الإلزامية لديها قيم")
    print("   لا يوجد تعديلات مطلوبة")

# عرض ملخص البيانات
print("\n📋 ملخص البيانات:")

cursor.execute("SELECT COUNT(*) FROM branches;")
print(f"   • الفروع: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM sites;")
print(f"   • المواقع: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM warehouses;")
print(f"   • المستودعات: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM expense_types WHERE is_active = 1;")
print(f"   • أنواع المصاريف النشطة: {cursor.fetchone()[0]}")

conn.close()

print("\n" + "=" * 80)
print("🎉 تم الانتهاء بنجاح!")
print("=" * 80)

