#!/usr/bin/env python3
"""
فحص توافق البيانات الحالية مع الجداول الجديدة
Check data compatibility with new schema
"""

import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "C:/Users/AhmadGh/Desktop/locc app/app (3).db"

print("=" * 80)
print("🔍 فحص توافق البيانات مع الجداول الجديدة")
print("=" * 80)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

issues = []
warnings = []

# 1. فحص الموظفين (users/employees)
print("\n1️⃣ فحص الموظفين (users):")
try:
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_employee = 1;")
    employee_count = cursor.fetchone()[0]
    print(f"   عدد الموظفين: {employee_count}")
    
    # فحص branch_id
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_employee = 1 AND branch_id IS NULL;")
    no_branch = cursor.fetchone()[0]
    
    if no_branch > 0:
        issues.append(f"⚠️  {no_branch} موظف بدون فرع (branch_id)")
        print(f"   ⚠️  {no_branch} موظف بدون فرع")
    else:
        print(f"   ✅ جميع الموظفين مرتبطين بفروع")
    
    # فحص hire_date
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_employee = 1 AND hire_date IS NULL;")
    no_hire_date = cursor.fetchone()[0]
    
    if no_hire_date > 0:
        warnings.append(f"ℹ️  {no_hire_date} موظف بدون تاريخ تعيين (hire_date)")
        print(f"   ℹ️  {no_hire_date} موظف بدون تاريخ تعيين (اختياري)")
    
except Exception as e:
    print(f"   ⚠️  {e}")

# 2. فحص المصاريف (expenses)
print("\n2️⃣ فحص المصاريف (expenses):")
try:
    cursor.execute("SELECT COUNT(*) FROM expenses;")
    expense_count = cursor.fetchone()[0]
    print(f"   عدد المصاريف: {expense_count}")
    
    if expense_count > 0:
        cursor.execute("SELECT COUNT(*) FROM expenses WHERE branch_id IS NULL;")
        no_branch = cursor.fetchone()[0]
        
        if no_branch > 0:
            issues.append(f"⚠️  {no_branch} مصروف بدون فرع (branch_id)")
            print(f"   ⚠️  {no_branch} مصروف بدون فرع")
        else:
            print(f"   ✅ جميع المصاريف مرتبطة بفروع")
            
        # فحص site_id
        cursor.execute("SELECT COUNT(*) FROM expenses WHERE site_id IS NULL;")
        no_site = cursor.fetchone()[0]
        if no_site > 0:
            print(f"   ℹ️  {no_site} مصروف بدون موقع (site_id - اختياري)")
        
except Exception as e:
    print(f"   ⚠️  {e}")

# 3. فحص المستودعات (warehouses)
print("\n3️⃣ فحص المستودعات (warehouses):")
try:
    cursor.execute("SELECT COUNT(*) FROM warehouses;")
    warehouse_count = cursor.fetchone()[0]
    print(f"   عدد المستودعات: {warehouse_count}")
    
    if warehouse_count > 0:
        cursor.execute("SELECT COUNT(*) FROM warehouses WHERE branch_id IS NULL;")
        no_branch = cursor.fetchone()[0]
        
        if no_branch > 0:
            warnings.append(f"ℹ️  {warehouse_count} مستودع بدون فرع (branch_id - اختياري)")
            print(f"   ℹ️  {no_branch} مستودع بدون فرع (اختياري)")
        else:
            print(f"   ✅ جميع المستودعات مرتبطة بفروع")
    
except Exception as e:
    print(f"   ⚠️  {e}")

# 4. فحص الفروع (branches)
print("\n4️⃣ فحص الفروع (branches):")
try:
    cursor.execute("SELECT COUNT(*) FROM branches;")
    branch_count = cursor.fetchone()[0]
    print(f"   عدد الفروع: {branch_count}")
    
    if branch_count == 0:
        issues.append("⚠️  لا يوجد فروع! يجب إنشاء فرع واحد على الأقل")
        print(f"   ⚠️  لا يوجد فروع في النظام")
    else:
        print(f"   ✅ يوجد {branch_count} فرع")
        
except Exception as e:
    print(f"   ⚠️  {e}")

# 5. فحص المواقع (sites)
print("\n5️⃣ فحص المواقع (sites):")
try:
    cursor.execute("SELECT COUNT(*) FROM sites;")
    site_count = cursor.fetchone()[0]
    print(f"   عدد المواقع: {site_count}")
    
    if site_count == 0:
        warnings.append("ℹ️  لا يوجد مواقع (اختياري)")
        print(f"   ℹ️  لا يوجد مواقع (اختياري)")
    else:
        print(f"   ✅ يوجد {site_count} موقع")
        
except Exception as e:
    print(f"   ⚠️  {e}")

# 6. فحص أنواع المصاريف
print("\n6️⃣ فحص أنواع المصاريف (expense_types):")
try:
    cursor.execute("SELECT COUNT(*) FROM expense_types WHERE is_active = 1;")
    active_types = cursor.fetchone()[0]
    print(f"   عدد الأنواع النشطة: {active_types}")
    
    if active_types == 0:
        warnings.append("ℹ️  لا يوجد أنواع مصاريف نشطة")
        print(f"   ⚠️  لا يوجد أنواع مصاريف نشطة")
    else:
        print(f"   ✅ {active_types} نوع نشط")
        
except Exception as e:
    print(f"   ⚠️  {e}")

# 7. فحص العلاقات الجديدة
print("\n7️⃣ فحص العلاقات الجديدة:")
try:
    # user_branches
    cursor.execute("SELECT COUNT(*) FROM user_branches;")
    user_branches = cursor.fetchone()[0]
    print(f"   • ربط مستخدمين بفروع: {user_branches}")
    
    # employee_deductions
    cursor.execute("SELECT COUNT(*) FROM employee_deductions;")
    deductions = cursor.fetchone()[0]
    print(f"   • خصومات موظفين: {deductions}")
    
    # employee_advances
    cursor.execute("SELECT COUNT(*) FROM employee_advances;")
    advances = cursor.fetchone()[0]
    print(f"   • سلف موظفين: {advances}")
    
except Exception as e:
    print(f"   ℹ️  بعض الجداول قد تكون غير موجودة: {e}")

conn.close()

# النتيجة النهائية
print("\n" + "=" * 80)
print("📊 النتيجة النهائية")
print("=" * 80)

if len(issues) == 0 and len(warnings) == 0:
    print("\n✅ البيانات متوافقة تماماً مع الجداول الجديدة!")
    print("   لا توجد مشاكل أو تحذيرات")
else:
    if len(issues) > 0:
        print(f"\n⚠️  مشاكل يجب حلها ({len(issues)}):")
        for issue in issues:
            print(f"   • {issue}")
    
    if len(warnings) > 0:
        print(f"\n💡 تحذيرات (اختيارية) ({len(warnings)}):")
        for warning in warnings:
            print(f"   • {warning}")

print("\n" + "=" * 80)

if len(issues) > 0:
    sys.exit(1)

