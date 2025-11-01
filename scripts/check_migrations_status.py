#!/usr/bin/env python3
"""
فحص حالة التهجيرات والتحقق من البيانات
Check migration status and verify data integrity
"""

import os
import sys
from pathlib import Path

# إضافة المسار الجذر
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask
from extensions import db
from config import Config
from sqlalchemy import text, inspect
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def create_app(database_url=None):
    """إنشاء تطبيق Flask"""
    app = Flask(__name__)
    
    if database_url:
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config.from_object(Config)
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    return app


def get_current_migration(app):
    """الحصول على آخر migration مطبق"""
    with app.app_context():
        try:
            result = db.session.execute(
                text("SELECT version_num FROM alembic_version")
            ).fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"خطأ في قراءة alembic_version: {str(e)}")
            return None


def check_table_exists(app, table_name):
    """التحقق من وجود جدول"""
    with app.app_context():
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        return table_name in tables


def check_column_exists(app, table_name, column_name):
    """التحقق من وجود عمود في جدول"""
    with app.app_context():
        try:
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns(table_name)]
            return column_name in columns
        except Exception:
            return False


def get_record_counts(app):
    """حساب عدد السجلات في الجداول المهمة"""
    with app.app_context():
        tables = {
            'users': 'المستخدمين',
            'customers': 'العملاء',
            'vendors': 'الموردين',
            'sales': 'المبيعات',
            'invoices': 'الفواتير',
            'payments': 'الدفعات',
            'service_orders': 'أوامر الخدمة',
            'expenses': 'المصاريف',
            'warehouses': 'المستودعات',
            'branches': 'الفروع',
            'sites': 'المواقع',
        }
        
        counts = {}
        for table_en, table_ar in tables.items():
            try:
                if check_table_exists(app, table_en):
                    result = db.session.execute(
                        text(f"SELECT COUNT(*) FROM {table_en}")
                    ).fetchone()
                    counts[table_ar] = result[0] if result else 0
                else:
                    counts[table_ar] = "لا يوجد"
            except Exception as e:
                counts[table_ar] = f"خطأ: {str(e)[:30]}"
        
        return counts


def check_migration_features(app):
    """فحص ميزات التهجيرات المطلوبة"""
    features = {}
    
    # فحص نظام الفروع
    features['نظام الفروع'] = check_table_exists(app, 'branches')
    features['نظام المواقع'] = check_table_exists(app, 'sites')
    features['ربط المستخدمين بالفروع'] = check_table_exists(app, 'user_branches')
    
    # فحص تحسينات الموظفين
    if check_table_exists(app, 'users'):
        features['تاريخ تعيين الموظفين'] = check_column_exists(app, 'users', 'hire_date')
    
    features['نظام خصومات الموظفين'] = check_table_exists(app, 'employee_deductions')
    features['نظام سلف الموظفين'] = check_table_exists(app, 'employee_advances')
    
    # فحص أنواع المصاريف
    if check_table_exists(app, 'expense_types'):
        with app.app_context():
            try:
                result = db.session.execute(
                    text("SELECT COUNT(*) FROM expense_types WHERE is_system_type = 1")
                ).fetchone()
                features['أنواع مصاريف محددة مسبقاً'] = result[0] > 0 if result else False
            except:
                features['أنواع مصاريف محددة مسبقاً'] = "غير متأكد"
    
    # فحص مدير الموظف للفروع
    if check_table_exists(app, 'branches'):
        features['مدير موظف للفروع'] = check_column_exists(app, 'branches', 'manager_employee_id')
    
    if check_table_exists(app, 'sites'):
        features['مدير موظف للمواقع'] = check_column_exists(app, 'sites', 'manager_employee_id')
    
    # فحص الفرع في المستودعات
    if check_table_exists(app, 'warehouses'):
        features['ربط المستودعات بالفروع'] = check_column_exists(app, 'warehouses', 'branch_id')
    
    # فحص تغيير الخصم إلى مبلغ
    if check_table_exists(app, 'service_parts'):
        features['الخصم كمبلغ في قطع الخدمة'] = check_column_exists(app, 'service_parts', 'discount')
    
    # فحص حالة المنتج في المرتجعات
    if check_table_exists(app, 'sale_return_lines'):
        features['حالة المنتج في المرتجعات'] = check_column_exists(app, 'sale_return_lines', 'condition')
    
    return features


def print_status(database_url=None):
    """طباعة حالة قاعدة البيانات والتهجيرات"""
    
    print("\n" + "=" * 80)
    print("🔍 فحص حالة قاعدة البيانات والتهجيرات")
    print("=" * 80)
    
    # إنشاء التطبيق
    app = create_app(database_url)
    
    # معلومات الاتصال
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    if 'password' in db_uri or 'pass' in db_uri:
        # إخفاء كلمة المرور
        db_uri_safe = db_uri[:30] + "***" + db_uri[-20:] if len(db_uri) > 50 else "***"
    else:
        db_uri_safe = db_uri
    
    print(f"\n📍 قاعدة البيانات: {db_uri_safe}")
    
    # التحقق من الاتصال
    try:
        with app.app_context():
            db.session.execute(text("SELECT 1")).fetchone()
        print("✅ الاتصال بقاعدة البيانات ناجح")
    except Exception as e:
        print(f"❌ فشل الاتصال بقاعدة البيانات: {str(e)}")
        return
    
    # الحصول على آخر migration
    current_migration = get_current_migration(app)
    print(f"\n📌 آخر Migration مطبق: {current_migration or 'لا يوجد'}")
    
    # التهجيرات المطلوبة (بالترتيب)
    required_migrations = [
        ('a8e34bc7e6bf', 'add_payment_id_to_checks (قديم)'),
        ('branches_sites_001', 'نظام الفروع والمواقع'),
        ('employee_enhance_001', 'تحسينات الموظفين'),
        ('expense_types_seed_002', 'أنواع المصاريف المحددة'),
        ('manager_employee_001', 'مدير موظف للفروع'),
        ('5ee38733531c', 'ربط المستودعات بالفروع'),
        ('discount_to_amount_001', 'تغيير الخصم إلى مبلغ'),
        ('7904e55f7ab9', 'حالة المنتج في المرتجعات'),
    ]
    
    print("\n📋 التهجيرات المطلوبة:")
    for i, (rev_id, description) in enumerate(required_migrations, 1):
        status = "✅" if current_migration == rev_id else "⏳"
        print(f"   {i}. {status} {rev_id} - {description}")
    
    if current_migration == required_migrations[-1][0]:
        print("\n🎉 جميع التهجيرات مطبقة!")
    else:
        print("\n⚠️  يوجد تهجيرات معلقة")
    
    # عدد السجلات
    print("\n📊 عدد السجلات في قاعدة البيانات:")
    counts = get_record_counts(app)
    for table, count in counts.items():
        print(f"   • {table}: {count}")
    
    # فحص الميزات
    print("\n🔧 حالة الميزات:")
    features = check_migration_features(app)
    for feature, status in features.items():
        icon = "✅" if status is True else "❌" if status is False else "❓"
        print(f"   {icon} {feature}")
    
    print("\n" + "=" * 80)
    print("✅ انتهى الفحص")
    print("=" * 80 + "\n")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="فحص حالة التهجيرات في قاعدة البيانات"
    )
    
    parser.add_argument(
        '--database-url',
        help='رابط قاعدة البيانات (اختياري، يستخدم .env إذا لم يحدد)'
    )
    
    args = parser.parse_args()
    
    try:
        print_status(args.database_url)
    except Exception as e:
        logger.error(f"خطأ: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

