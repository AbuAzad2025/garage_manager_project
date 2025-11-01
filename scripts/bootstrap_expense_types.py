#!/usr/bin/env python3
"""
إنشاء أنواع المصاريف المحددة مسبقاً
Bootstrap expense types
"""

import sys
import os
from pathlib import Path

# إضافة المسار الجذر
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask
from extensions import db
from config import Config
from models import ExpenseType
import json

def bootstrap_expense_types(database_url=None):
    """إنشاء أنواع المصاريف المحددة مسبقاً"""
    
    # إنشاء التطبيق
    app = Flask(__name__)
    
    if database_url:
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config.from_object(Config)
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    
    with app.app_context():
        print("=" * 80)
        print("🏗️  إنشاء أنواع المصاريف المحددة مسبقاً")
        print("=" * 80)
        
        # التحقق من وجود أنواع مصاريف مسبقاً
        existing_count = ExpenseType.query.count()
        
        if existing_count > 0:
            print(f"\n⚠️  يوجد {existing_count} نوع مصاريف موجود مسبقاً")
            print("   سيتم تخطي الأنواع الموجودة وإضافة الجديدة فقط")
        
        # أنواع المصاريف المحددة مسبقاً (متوافقة مع السكيما الحالية)
        expense_types_data = [
            ("SALARY", "رواتب", {"required": ["employee_id", "period"], "optional": ["description"], "gl_account_code": "6100_SALARIES"}),
            ("RENT", "إيجار", {"required": ["period"], "optional": ["warehouse_id", "tax_invoice_number", "description"], "gl_account_code": "6200_RENT"}),
            ("UTILITIES", "مرافق (كهرباء/ماء/اتصالات)", {"required": ["period", "utility_account_id"], "optional": ["tax_invoice_number", "description"], "gl_account_code": "6300_UTILITIES"}),
            ("MAINTENANCE", "صيانة", {"required": [], "optional": ["warehouse_id", "stock_adjustment_id", "description"], "gl_account_code": "6400_MAINTENANCE"}),
            ("FUEL", "وقود", {"required": [], "optional": ["beneficiary_name", "description"], "gl_account_code": "6500_FUEL"}),
            ("OFFICE", "لوازم مكتبية", {"required": [], "optional": ["beneficiary_name", "description"], "gl_account_code": "6600_OFFICE"}),
            ("INSURANCE", "تأمين", {"required": ["period"], "optional": ["beneficiary_name", "tax_invoice_number", "description"], "gl_account_code": "6700_INSURANCE"}),
            ("GOV_FEES", "رسوم حكومية/ضرائب", {"required": ["period"], "optional": ["beneficiary_name", "tax_invoice_number", "description"], "gl_account_code": "6800_GOV_FEES"}),
            ("TRAVEL", "سفر/مهمات", {"required": ["employee_id", "period"], "optional": ["beneficiary_name", "description"], "gl_account_code": "6900_TRAVEL"}),
            ("TRAINING", "تدريب", {"required": [], "optional": ["period", "beneficiary_name", "description"], "gl_account_code": "6910_TRAINING"}),
            ("MARKETING", "تسويق/إعلانات", {"required": ["beneficiary_name"], "optional": ["period", "description"], "gl_account_code": "6920_MARKETING"}),
            ("SOFTWARE", "اشتراكات تقنية/برمجيات", {"required": ["period"], "optional": ["beneficiary_name", "description"], "gl_account_code": "6930_SOFTWARE"}),
            ("BANK_FEES", "رسوم بنكية", {"required": ["beneficiary_name"], "optional": ["description"], "gl_account_code": "6940_BANK_FEES"}),
            ("EMPLOYEE_ADVANCE", "سلفة موظف", {"required": ["employee_id"], "optional": ["period", "description"], "gl_account_code": "6950_ADVANCES"}),
            ("HOSPITALITY", "ضيافة", {"required": [], "optional": ["beneficiary_name", "description"], "gl_account_code": "6960_HOSPITALITY"}),
            ("HOME_EXPENSE", "مصاريف بيتية", {"required": [], "optional": ["beneficiary_name", "description"], "gl_account_code": "6970_HOME"}),
            ("OWNERS_EXPENSE", "مصاريف المالكين", {"required": [], "optional": ["beneficiary_name", "description"], "gl_account_code": "6980_OWNERS"}),
            ("ENTERTAINMENT", "مصاريف ترفيهية", {"required": [], "optional": ["beneficiary_name", "description"], "gl_account_code": "6985_ENTERTAINMENT"}),
            ("SHIP_INSURANCE", "تأمين شحنة", {"required": ["shipment_id"], "optional": ["description"], "gl_account_code": "7100_SHIP_INS"}),
            ("SHIP_CUSTOMS", "جمارك", {"required": ["shipment_id"], "optional": ["description"], "gl_account_code": "7200_CUSTOMS"}),
            ("SHIP_IMPORT_TAX", "ضريبة استيراد", {"required": ["shipment_id"], "optional": ["description"], "gl_account_code": "7300_IMPORT_TAX"}),
            ("SHIP_FREIGHT", "شحن (بحري/جوي/بري)", {"required": ["shipment_id"], "optional": ["description"], "gl_account_code": "7400_FREIGHT"}),
            ("SHIP_CLEARANCE", "تخليص جمركي", {"required": ["shipment_id"], "optional": ["description"], "gl_account_code": "7500_CLEARANCE"}),
            ("SHIP_HANDLING", "أرضيات/مناولة", {"required": ["shipment_id"], "optional": ["description"], "gl_account_code": "7600_HANDLING"}),
            ("SHIP_PORT_FEES", "رسوم ميناء/مطار", {"required": ["shipment_id"], "optional": ["description"], "gl_account_code": "7700_PORT_FEES"}),
            ("SHIP_STORAGE", "تخزين مؤقت", {"required": ["shipment_id"], "optional": ["description"], "gl_account_code": "7800_STORAGE"}),
            ("OTHER", "أخرى", {"required": [], "optional": ["beneficiary_name", "description"], "gl_account_code": "9999_OTHER"}),
        ]
        
        print(f"\n🔨 إنشاء {len(expense_types_data)} نوع مصاريف...")
        
        created_count = 0
        skipped_count = 0
        
        for code, name, meta in expense_types_data:
            try:
                # التحقق من وجود النوع مسبقاً
                existing = ExpenseType.query.filter(
                    (ExpenseType.code == code) | (ExpenseType.name == name)
                ).first()
                
                if existing:
                    print(f"   ⏩ {name} (موجود مسبقاً)")
                    skipped_count += 1
                    continue
                
                # إنشاء النوع الجديد
                expense_type = ExpenseType(
                    name=name,
                    code=code,
                    description=name,
                    is_active=True,
                    fields_meta=meta
                )
                
                db.session.add(expense_type)
                db.session.commit()
                
                print(f"   ✓ {name}")
                created_count += 1
                
            except Exception as e:
                db.session.rollback()
                print(f"   ✗ {name}: {e}")
        
        print(f"\n✅ تم إنشاء {created_count} نوع جديد")
        if skipped_count > 0:
            print(f"⏩ تم تخطي {skipped_count} نوع موجود مسبقاً")
        
        # عرض الإحصائيات
        print("\n📊 إجمالي أنواع المصاريف:")
        total = ExpenseType.query.count()
        active = ExpenseType.query.filter_by(is_active=True).count()
        print(f"   • الإجمالي: {total}")
        print(f"   • النشط: {active}")
        
        print("\n" + "=" * 80)
        print("🎉 تم الانتهاء!")
        print("=" * 80)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="إنشاء أنواع المصاريف المحددة مسبقاً")
    parser.add_argument('--database-url', help='رابط قاعدة البيانات')
    
    args = parser.parse_args()
    
    try:
        bootstrap_expense_types(args.database_url)
    except Exception as e:
        print(f"\n❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

