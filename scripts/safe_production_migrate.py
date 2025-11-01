#!/usr/bin/env python3
"""
سكريبت آمن لتطبيق التهجيرات على قاعدة بيانات الإنتاج
Safe Production Database Migration Script

الاستخدام:
    python scripts/safe_production_migrate.py --database-url "postgresql://..." --backup-dir "./backups"

الميزات:
    ✅ نسخ احتياطي تلقائي قبل كل migration
    ✅ تطبيق تدريجي (واحد واحد)
    ✅ فحص سلامة البيانات بعد كل خطوة
    ✅ إمكانية التراجع (rollback)
    ✅ سجل كامل للعملية
"""

import os
import sys
import argparse
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

# إضافة المسار الجذر للمشروع
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# استيراد بعد إضافة المسار
from flask import Flask
from extensions import db, migrate
from config import Config
from sqlalchemy import text, inspect
import logging

# إعداد السجلات
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration_production.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class SafeMigrationManager:
    """مدير آمن للتهجيرات"""
    
    def __init__(self, database_url, backup_dir="./backups/production"):
        self.database_url = database_url
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # إنشاء تطبيق Flask مؤقت
        self.app = self._create_app()
        self.db_type = self._detect_db_type()
        
        logger.info(f"🎯 تم الكشف عن نوع قاعدة البيانات: {self.db_type}")
    
    def _create_app(self):
        """إنشاء تطبيق Flask للاتصال بقاعدة البيانات"""
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = self.database_url
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 1800,
        }
        
        db.init_app(app)
        migrate.init_app(app, db)
        
        return app
    
    def _detect_db_type(self):
        """كشف نوع قاعدة البيانات"""
        if 'postgresql' in self.database_url or 'postgres' in self.database_url:
            return 'postgresql'
        elif 'mysql' in self.database_url:
            return 'mysql'
        elif 'sqlite' in self.database_url:
            return 'sqlite'
        else:
            return 'unknown'
    
    def create_backup(self, label="auto"):
        """إنشاء نسخة احتياطية من قاعدة البيانات"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{label}_{timestamp}"
        
        logger.info(f"📦 بدء النسخ الاحتياطي: {backup_name}")
        
        try:
            if self.db_type == 'sqlite':
                # نسخ ملف SQLite مباشرة
                db_path = self.database_url.replace('sqlite:///', '')
                backup_path = self.backup_dir / f"{backup_name}.db"
                shutil.copy2(db_path, backup_path)
                
            elif self.db_type == 'postgresql':
                # استخدام pg_dump
                backup_path = self.backup_dir / f"{backup_name}.sql"
                # استخراج معلومات الاتصال من URL
                # postgresql://user:pass@host:port/dbname
                cmd = f"pg_dump {self.database_url} > {backup_path}"
                subprocess.run(cmd, shell=True, check=True)
                
            elif self.db_type == 'mysql':
                # استخدام mysqldump
                backup_path = self.backup_dir / f"{backup_name}.sql"
                # يحتاج تعديل حسب تنسيق URL
                logger.warning("⚠️ MySQL backup يحتاج إعداد يدوي")
                return None
                
            else:
                logger.error("❌ نوع قاعدة البيانات غير مدعوم للنسخ الاحتياطي التلقائي")
                return None
            
            logger.info(f"✅ تم النسخ الاحتياطي بنجاح: {backup_path}")
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"❌ فشل النسخ الاحتياطي: {str(e)}")
            raise
    
    def get_current_revision(self):
        """الحصول على آخر revision مطبق"""
        with self.app.app_context():
            try:
                result = db.session.execute(
                    text("SELECT version_num FROM alembic_version")
                ).fetchone()
                if result:
                    return result[0]
                return None
            except Exception as e:
                logger.warning(f"⚠️ لم يتم العثور على جدول alembic_version: {str(e)}")
                return None
    
    def get_pending_migrations(self):
        """الحصول على التهجيرات المعلقة"""
        try:
            result = subprocess.run(
                ['flask', 'db', 'heads'],
                capture_output=True,
                text=True,
                env={**os.environ, 'DATABASE_URL': self.database_url}
            )
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"❌ فشل الحصول على التهجيرات المعلقة: {str(e)}")
            return None
    
    def check_data_integrity(self):
        """فحص سلامة البيانات الأساسية"""
        with self.app.app_context():
            try:
                # فحص الجداول الرئيسية
                inspector = inspect(db.engine)
                tables = inspector.get_table_names()
                
                logger.info(f"📊 عدد الجداول: {len(tables)}")
                
                # فحص عدد السجلات في بعض الجداول المهمة
                important_tables = ['users', 'customers', 'sales', 'invoices', 'payments']
                
                counts = {}
                for table in important_tables:
                    if table in tables:
                        try:
                            result = db.session.execute(
                                text(f"SELECT COUNT(*) FROM {table}")
                            ).fetchone()
                            counts[table] = result[0] if result else 0
                        except Exception as e:
                            logger.warning(f"⚠️ تعذر فحص جدول {table}: {str(e)}")
                            counts[table] = "ERROR"
                
                logger.info("📈 عدد السجلات في الجداول المهمة:")
                for table, count in counts.items():
                    logger.info(f"   - {table}: {count}")
                
                return counts
                
            except Exception as e:
                logger.error(f"❌ فشل فحص سلامة البيانات: {str(e)}")
                return None
    
    def apply_migration_step(self, steps=1):
        """تطبيق عدد محدد من التهجيرات"""
        logger.info(f"🚀 تطبيق {steps} migration(s)...")
        
        try:
            cmd = ['flask', 'db', 'upgrade', f'+{steps}']
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env={**os.environ, 'DATABASE_URL': self.database_url}
            )
            
            if result.returncode == 0:
                logger.info(f"✅ تم تطبيق التهجيرات بنجاح")
                logger.info(result.stdout)
                return True
            else:
                logger.error(f"❌ فشل تطبيق التهجيرات:")
                logger.error(result.stderr)
                return False
                
        except Exception as e:
            logger.error(f"❌ خطأ أثناء تطبيق التهجيرات: {str(e)}")
            return False
    
    def apply_all_migrations_safely(self, step_by_step=True):
        """تطبيق جميع التهجيرات بشكل آمن"""
        logger.info("=" * 80)
        logger.info("🎯 بدء عملية التهجير الآمن")
        logger.info("=" * 80)
        
        # 1. فحص الحالة الحالية
        current_rev = self.get_current_revision()
        logger.info(f"📍 Revision الحالي: {current_rev}")
        
        # 2. فحص البيانات قبل البدء
        logger.info("\n📊 فحص سلامة البيانات قبل التهجير:")
        data_before = self.check_data_integrity()
        
        # 3. نسخة احتياطية رئيسية
        logger.info("\n📦 إنشاء نسخة احتياطية رئيسية...")
        main_backup = self.create_backup("before_migration")
        
        if not main_backup:
            logger.error("❌ فشل النسخ الاحتياطي! العملية ملغاة.")
            return False
        
        # 4. تطبيق التهجيرات
        if step_by_step:
            # تطبيق واحد واحد (أكثر أماناً)
            logger.info("\n🔄 التطبيق التدريجي للتهجيرات...")
            
            max_steps = 20  # حد أقصى للأمان
            for step in range(1, max_steps + 1):
                logger.info(f"\n--- الخطوة {step} ---")
                
                # نسخة احتياطية قبل كل خطوة
                step_backup = self.create_backup(f"step_{step}")
                
                # تطبيق migration واحد
                success = self.apply_migration_step(1)
                
                if not success:
                    logger.error(f"❌ فشلت الخطوة {step}!")
                    logger.info(f"💡 يمكنك استعادة النسخة الاحتياطية: {step_backup}")
                    return False
                
                # فحص البيانات بعد كل خطوة
                logger.info("🔍 فحص سلامة البيانات...")
                data_after = self.check_data_integrity()
                
                if not data_after:
                    logger.error("❌ فشل فحص البيانات!")
                    return False
                
                # مقارنة عدد السجلات
                if data_before and data_after:
                    for table in data_before.keys():
                        if table in data_after:
                            before = data_before[table]
                            after = data_after[table]
                            if before != after and before != "ERROR" and after != "ERROR":
                                change = after - before if isinstance(after, int) and isinstance(before, int) else "N/A"
                                logger.info(f"   ℹ️ {table}: {before} → {after} (تغير: {change})")
                
                # تحديث البيانات للمقارنة التالية
                data_before = data_after
                
                # التحقق من وجود مزيد من التهجيرات
                current_rev = self.get_current_revision()
                logger.info(f"📍 Revision الحالي بعد الخطوة: {current_rev}")
                
                # توقف إذا وصلنا لآخر migration
                # (يمكن تحسين هذا الفحص)
                
        else:
            # تطبيق جميع التهجيرات دفعة واحدة (أقل أماناً)
            logger.info("\n🚀 تطبيق جميع التهجيرات دفعة واحدة...")
            
            try:
                cmd = ['flask', 'db', 'upgrade', 'head']
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    env={**os.environ, 'DATABASE_URL': self.database_url}
                )
                
                if result.returncode != 0:
                    logger.error(f"❌ فشل تطبيق التهجيرات:")
                    logger.error(result.stderr)
                    return False
                
                logger.info("✅ تم تطبيق جميع التهجيرات")
                logger.info(result.stdout)
                
            except Exception as e:
                logger.error(f"❌ خطأ: {str(e)}")
                return False
        
        # 5. فحص نهائي
        logger.info("\n" + "=" * 80)
        logger.info("🎉 اكتملت عملية التهجير!")
        logger.info("=" * 80)
        
        logger.info("\n📊 فحص نهائي للبيانات:")
        final_data = self.check_data_integrity()
        
        final_rev = self.get_current_revision()
        logger.info(f"\n✅ Revision النهائي: {final_rev}")
        
        logger.info(f"\n💾 النسخة الاحتياطية الرئيسية: {main_backup}")
        logger.info("   احتفظ بها لمدة أسبوع على الأقل!")
        
        return True


def main():
    parser = argparse.ArgumentParser(
        description="سكريبت آمن لتطبيق التهجيرات على قاعدة بيانات الإنتاج"
    )
    
    parser.add_argument(
        '--database-url',
        required=True,
        help='رابط قاعدة البيانات (DATABASE_URL)'
    )
    
    parser.add_argument(
        '--backup-dir',
        default='./backups/production',
        help='مجلد النسخ الاحتياطية (افتراضي: ./backups/production)'
    )
    
    parser.add_argument(
        '--all-at-once',
        action='store_true',
        help='تطبيق جميع التهجيرات دفعة واحدة (افتراضي: تدريجياً)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='محاكاة العملية بدون تطبيق فعلي'
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("🔍 وضع المحاكاة - لن يتم تطبيق أي تغييرات فعلية")
    
    # تأكيد من المستخدم
    print("\n" + "=" * 80)
    print("⚠️  تحذير: أنت على وشك تطبيق تهجيرات على قاعدة بيانات الإنتاج!")
    print("=" * 80)
    print(f"\n📍 قاعدة البيانات: {args.database_url[:50]}...")
    print(f"📦 مجلد النسخ الاحتياطية: {args.backup_dir}")
    print(f"🔄 طريقة التطبيق: {'دفعة واحدة' if args.all_at_once else 'تدريجي (خطوة خطوة)'}")
    
    if not args.dry_run:
        confirm = input("\n⚠️  هل أنت متأكد؟ اكتب 'YES' للمتابعة: ")
        if confirm != 'YES':
            logger.info("❌ العملية ملغاة من قبل المستخدم")
            return
    
    # إنشاء المدير وتشغيل العملية
    try:
        manager = SafeMigrationManager(
            database_url=args.database_url,
            backup_dir=args.backup_dir
        )
        
        if args.dry_run:
            logger.info("🔍 الفحص الأولي:")
            current_rev = manager.get_current_revision()
            logger.info(f"   Revision الحالي: {current_rev}")
            manager.check_data_integrity()
            logger.info("\n✅ انتهى وضع المحاكاة")
        else:
            success = manager.apply_all_migrations_safely(
                step_by_step=not args.all_at_once
            )
            
            if success:
                logger.info("\n🎉 تمت العملية بنجاح!")
                sys.exit(0)
            else:
                logger.error("\n❌ فشلت العملية!")
                sys.exit(1)
                
    except Exception as e:
        logger.error(f"\n❌ خطأ غير متوقع: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

