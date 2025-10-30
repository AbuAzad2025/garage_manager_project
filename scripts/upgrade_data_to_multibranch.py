#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
سكريبت تحسين البيانات القديمة لتطابق النظام الجديد
- ربط الموظفين والنفقات بالفرع الرئيسي MAIN
- إنشاء حسابات GL المخصصة لأنواع المصاريف
- تحديث البيانات التاريخية
"""

import sys
import os

# إضافة المسار للوصول إلى الموديلات
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db
from models import (
    Branch, Site, Employee, Expense, ExpenseType, Warehouse,
    Account, AccountType
)
from sqlalchemy import text as sa_text


def upgrade_data():
    """تحسين شامل للبيانات القديمة"""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("🔄 بدء تحسين البيانات للنظام متعدد الفروع")
        print("=" * 60)
        
        # 1️⃣ التأكد من وجود الفرع الرئيسي MAIN
        main_branch = Branch.query.filter_by(code='MAIN').first()
        if not main_branch:
            print("\n✅ إنشاء الفرع الرئيسي MAIN...")
            main_branch = Branch(
                name='الفرع الرئيسي',
                code='MAIN',
                is_active=True,
                currency='ILS',
                city='رام الله',
                address='المقر الرئيسي'
            )
            db.session.add(main_branch)
            db.session.commit()
            print(f"   ✅ تم إنشاء الفرع: {main_branch.name} (ID: {main_branch.id})")
        else:
            print(f"\n✅ الفرع الرئيسي موجود: {main_branch.name} (ID: {main_branch.id})")
        
        # 2️⃣ ربط الموظفين غير المربوطين بالفرع الرئيسي
        print("\n🔄 تحديث الموظفين...")
        employees_updated = db.session.execute(
            sa_text("UPDATE employees SET branch_id = :bid WHERE branch_id IS NULL"),
            {'bid': main_branch.id}
        ).rowcount
        db.session.commit()
        print(f"   ✅ تم ربط {employees_updated} موظف بالفرع الرئيسي")
        
        # 3️⃣ ربط النفقات غير المربوطة بالفرع الرئيسي
        print("\n🔄 تحديث النفقات...")
        expenses_updated = db.session.execute(
            sa_text("UPDATE expenses SET branch_id = :bid WHERE branch_id IS NULL"),
            {'bid': main_branch.id}
        ).rowcount
        db.session.commit()
        print(f"   ✅ تم ربط {expenses_updated} مصروف بالفرع الرئيسي")
        
        # 4️⃣ ربط المستودعات بالفرع الرئيسي (اختياري)
        print("\n🔄 تحديث المستودعات...")
        warehouses_updated = db.session.execute(
            sa_text("UPDATE warehouses SET branch_id = :bid WHERE branch_id IS NULL"),
            {'bid': main_branch.id}
        ).rowcount
        db.session.commit()
        print(f"   ✅ تم ربط {warehouses_updated} مستودع بالفرع الرئيسي")
        
        # 5️⃣ التأكد من وجود أكواد لأنواع المصاريف
        print("\n🔄 تحديث أنواع المصاريف...")
        types_without_code = ExpenseType.query.filter(
            (ExpenseType.code.is_(None)) | (ExpenseType.code == '')
        ).all()
        
        # خريطة افتراضية للأسماء → الأكواد
        name_to_code_map = {
            'رواتب': 'SALARY',
            'إيجار': 'RENT',
            'كهرباء': 'UTILITIES',
            'ماء': 'UTILITIES',
            'مرافق': 'UTILITIES',
            'صيانة': 'MAINTENANCE',
            'وقود': 'FUEL',
            'لوازم': 'OFFICE',
            'تأمين': 'INSURANCE',
            'رسوم': 'GOV_FEES',
            'ضرائب': 'GOV_FEES',
            'سفر': 'TRAVEL',
            'تدريب': 'TRAINING',
            'تسويق': 'MARKETING',
            'إعلان': 'MARKETING',
            'برمجيات': 'SOFTWARE',
            'اشتراك': 'SOFTWARE',
            'بنك': 'BANK_FEES',
            'جمارك': 'SHIP_CUSTOMS',
            'شحن': 'SHIP_FREIGHT',
            'سلفة': 'EMPLOYEE_ADVANCE',
            'ضيافة': 'HOSPITALITY',
            'بيتية': 'HOME_EXPENSE',
            'مالك': 'OWNERS_EXPENSE',
            'ترفيه': 'ENTERTAINMENT',
        }
        
        codes_assigned = 0
        for etype in types_without_code:
            name_lower = etype.name.lower()
            assigned_code = None
            
            # محاولة مطابقة الاسم
            for key, code in name_to_code_map.items():
                if key in name_lower:
                    assigned_code = code
                    break
            
            if not assigned_code:
                assigned_code = 'OTHER'
            
            etype.code = assigned_code
            codes_assigned += 1
        
        db.session.commit()
        print(f"   ✅ تم تعيين أكواد لـ {codes_assigned} نوع مصروف")
        
        # 6️⃣ إنشاء حسابات GL المخصصة إن لم تكن موجودة
        print("\n🔄 إنشاء حسابات GL المخصصة...")
        
        gl_accounts_to_create = [
            ('5100_SALARIES', 'مصروف رواتب وأجور', 'EXPENSE', '5000_EXPENSES'),
            ('5200_RENT', 'مصروف إيجار', 'EXPENSE', '5000_EXPENSES'),
            ('5300_UTILITIES', 'مصروف مرافق', 'EXPENSE', '5000_EXPENSES'),
            ('5400_MAINTENANCE', 'مصروف صيانة', 'EXPENSE', '5000_EXPENSES'),
            ('5500_FUEL', 'مصروف وقود', 'EXPENSE', '5000_EXPENSES'),
            ('5600_OFFICE', 'مصروف لوازم مكتبية', 'EXPENSE', '5000_EXPENSES'),
            ('5700_INSURANCE', 'مصروف تأمين', 'EXPENSE', '5000_EXPENSES'),
            ('5800_GOV_FEES', 'مصروف رسوم وضرائب', 'EXPENSE', '5000_EXPENSES'),
            ('5900_TRAVEL', 'مصروف سفر', 'EXPENSE', '5000_EXPENSES'),
            ('5910_TRAINING', 'مصروف تدريب', 'EXPENSE', '5000_EXPENSES'),
            ('5920_MARKETING', 'مصروف تسويق', 'EXPENSE', '5000_EXPENSES'),
            ('5930_SOFTWARE', 'مصروف برمجيات', 'EXPENSE', '5000_EXPENSES'),
            ('5940_BANK_FEES', 'مصروف رسوم بنكية', 'EXPENSE', '5000_EXPENSES'),
            ('2300_EMPLOYEE_ADVANCES', 'سلف الموظفين', 'LIABILITY', '2000_AP'),
            ('5950_HOSPITALITY', 'مصروف ضيافة', 'EXPENSE', '5000_EXPENSES'),
            ('5960_HOME_EXPENSE', 'مصروفات بيتية', 'EXPENSE', '5000_EXPENSES'),
            ('5970_OWNERS', 'مصروفات المالكين', 'EXPENSE', '5000_EXPENSES'),
            ('5980_ENTERTAINMENT', 'مصروف ترفيهي', 'EXPENSE', '5000_EXPENSES'),
            ('5810_SHIP_INSURANCE', 'مصروف تأمين شحن', 'EXPENSE', '5000_EXPENSES'),
            ('5820_CUSTOMS', 'مصروف جمارك', 'EXPENSE', '5000_EXPENSES'),
            ('5830_IMPORT_TAX', 'مصروف ضرائب استيراد', 'EXPENSE', '5000_EXPENSES'),
            ('5840_FREIGHT', 'مصروف شحن', 'EXPENSE', '5000_EXPENSES'),
            ('5850_CLEARANCE', 'مصروف تخليص جمركي', 'EXPENSE', '5000_EXPENSES'),
            ('5860_HANDLING', 'مصروف مناولة/أرضيات', 'EXPENSE', '5000_EXPENSES'),
            ('5870_PORT_FEES', 'مصروف رسوم ميناء/مطار', 'EXPENSE', '5000_EXPENSES'),
            ('5880_STORAGE', 'مصروف تخزين مؤقت', 'EXPENSE', '5000_EXPENSES'),
        ]
        
        accounts_created = 0
        for code, name, acc_type, parent_code in gl_accounts_to_create:
            existing = Account.query.filter_by(code=code).first()
            if existing:
                continue
            
            parent = Account.query.filter_by(code=parent_code).first()
            
            try:
                acc = Account(
                    code=code,
                    name=name,
                    account_type=acc_type,
                    parent_id=parent.id if parent else None,
                    is_active=True,
                    currency='ILS'
                )
                db.session.add(acc)
                accounts_created += 1
            except Exception as e:
                print(f"   ⚠️ تخطي حساب {code}: {e}")
        
        try:
            db.session.commit()
            print(f"   ✅ تم إنشاء {accounts_created} حساب GL جديد")
        except Exception as e:
            db.session.rollback()
            print(f"   ⚠️ خطأ في إنشاء الحسابات: {e}")
        
        # 7️⃣ تحديث fields_meta بأكواد الحسابات الصحيحة
        print("\n🔄 تحديث ربط أنواع المصاريف بحسابات GL...")
        
        gl_mapping = {
            'SALARY': '5100_SALARIES',
            'RENT': '5200_RENT',
            'UTILITIES': '5300_UTILITIES',
            'MAINTENANCE': '5400_MAINTENANCE',
            'FUEL': '5500_FUEL',
            'OFFICE': '5600_OFFICE',
            'INSURANCE': '5700_INSURANCE',
            'GOV_FEES': '5800_GOV_FEES',
            'TRAVEL': '5900_TRAVEL',
            'TRAINING': '5910_TRAINING',
            'MARKETING': '5920_MARKETING',
            'SOFTWARE': '5930_SOFTWARE',
            'BANK_FEES': '5940_BANK_FEES',
            'OTHER': '5000_EXPENSES',
            'EMPLOYEE_ADVANCE': '2300_EMPLOYEE_ADVANCES',
            'HOSPITALITY': '5950_HOSPITALITY',
            'HOME_EXPENSE': '5960_HOME_EXPENSE',
            'OWNERS_EXPENSE': '5970_OWNERS',
            'ENTERTAINMENT': '5980_ENTERTAINMENT',
            'SHIP_INSURANCE': '5810_SHIP_INSURANCE',
            'SHIP_CUSTOMS': '5820_CUSTOMS',
            'SHIP_IMPORT_TAX': '5830_IMPORT_TAX',
            'SHIP_FREIGHT': '5840_FREIGHT',
            'SHIP_CLEARANCE': '5850_CLEARANCE',
            'SHIP_HANDLING': '5860_HANDLING',
            'SHIP_PORT_FEES': '5870_PORT_FEES',
            'SHIP_STORAGE': '5880_STORAGE',
        }
        
        types_updated = 0
        import json
        
        for etype in ExpenseType.query.all():
            if not etype.code:
                continue
            
            gl_code = gl_mapping.get(etype.code)
            if not gl_code:
                continue
            
            # قراءة fields_meta الحالية
            meta = etype.fields_meta or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except:
                    meta = {}
            
            # تحديث gl_account_code
            old_gl = meta.get('gl_account_code')
            meta['gl_account_code'] = gl_code
            
            if old_gl != gl_code:
                etype.fields_meta = meta
                types_updated += 1
        
        db.session.commit()
        print(f"   ✅ تم تحديث {types_updated} نوع مصروف بحسابات GL محددة")
        
        # 8️⃣ إحصائيات نهائية
        print("\n" + "=" * 60)
        print("📊 الإحصائيات النهائية")
        print("=" * 60)
        
        stats = {
            'branches': Branch.query.count(),
            'sites': Site.query.count(),
            'employees': Employee.query.count(),
            'employees_with_branch': Employee.query.filter(Employee.branch_id.isnot(None)).count(),
            'expenses': Expense.query.count(),
            'expenses_with_branch': Expense.query.filter(Expense.branch_id.isnot(None)).count(),
            'warehouses': Warehouse.query.count(),
            'warehouses_with_branch': Warehouse.query.filter(Warehouse.branch_id.isnot(None)).count(),
            'expense_types': ExpenseType.query.count(),
            'expense_types_with_code': ExpenseType.query.filter(ExpenseType.code.isnot(None)).count(),
            'gl_accounts': Account.query.count() if Account.query.first() else 0,
        }
        
        print(f"   الفروع: {stats['branches']}")
        print(f"   المواقع: {stats['sites']}")
        print(f"   الموظفين: {stats['employees']} ({stats['employees_with_branch']} مربوط بفرع)")
        print(f"   النفقات: {stats['expenses']} ({stats['expenses_with_branch']} مربوط بفرع)")
        print(f"   المستودعات: {stats['warehouses']} ({stats['warehouses_with_branch']} مربوط بفرع)")
        print(f"   أنواع المصاريف: {stats['expense_types']} ({stats['expense_types_with_code']} له كود)")
        print(f"   حسابات GL: {stats['gl_accounts']}")
        
        # 9️⃣ التحقق من النزاهة
        print("\n🔍 التحقق من نزاهة البيانات...")
        
        checks = []
        
        # موظفين بدون فرع
        emp_no_branch = Employee.query.filter(Employee.branch_id.is_(None)).count()
        if emp_no_branch > 0:
            checks.append(f"⚠️ {emp_no_branch} موظف بدون فرع")
        else:
            checks.append(f"✅ جميع الموظفين مربوطون بفرع")
        
        # نفقات بدون فرع
        exp_no_branch = Expense.query.filter(Expense.branch_id.is_(None)).count()
        if exp_no_branch > 0:
            checks.append(f"⚠️ {exp_no_branch} مصروف بدون فرع")
        else:
            checks.append(f"✅ جميع المصاريف مربوطة بفرع")
        
        # أنواع مصاريف بدون كود
        types_no_code = ExpenseType.query.filter(
            (ExpenseType.code.is_(None)) | (ExpenseType.code == '')
        ).count()
        if types_no_code > 0:
            checks.append(f"⚠️ {types_no_code} نوع مصروف بدون كود")
        else:
            checks.append(f"✅ جميع أنواع المصاريف لها أكواد")
        
        # أنواع مصاريف بدون GL account
        types_no_gl = 0
        for etype in ExpenseType.query.all():
            meta = etype.fields_meta or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except:
                    meta = {}
            if not meta.get('gl_account_code'):
                types_no_gl += 1
        
        if types_no_gl > 0:
            checks.append(f"⚠️ {types_no_gl} نوع مصروف بدون حساب GL")
        else:
            checks.append(f"✅ جميع أنواع المصاريف مربوطة بحسابات GL")
        
        for check in checks:
            print(f"   {check}")
        
        print("\n" + "=" * 60)
        print("✅ اكتمل التحسين بنجاح!")
        print("=" * 60)
        
        return stats


if __name__ == '__main__':
    try:
        stats = upgrade_data()
        print("\n✅ النظام جاهز للاستخدام الفوري!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ خطأ: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

