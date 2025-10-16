import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class AutomatedBackupManager:
    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        self.app = app
        self.backup_dir = Path(app.instance_path) / 'backups' / 'db'
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        self.retention_policy = {
            'max_backups': 5  # احتفظ بآخر 5 نسخ فقط
        }
    
    def create_backup(self):
        try:
            from extensions import db
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f'auto_backup_{timestamp}.db'
            backup_path = self.backup_dir / backup_filename
            
            db_path = self.app.config.get('SQLALCHEMY_DATABASE_URI', '').replace('sqlite:///', '')
            
            if not db_path or not os.path.exists(db_path):
                logger.error(f'Database file not found: {db_path}')
                return None
            
            shutil.copy2(db_path, backup_path)
            
            file_size = backup_path.stat().st_size / (1024 * 1024)
            logger.info(f'✅ Backup created: {backup_filename} ({file_size:.2f} MB)')
            
            self.cleanup_old_backups()
            
            return backup_path
            
        except Exception as e:
            logger.error(f'❌ Backup failed: {str(e)}')
            return None
    
    def cleanup_old_backups(self):
        try:
            # احصل على جميع النسخ الاحتياطية (auto_backup و backup)
            auto_backups = sorted(self.backup_dir.glob('auto_backup_*.db'), key=os.path.getmtime, reverse=True)
            manual_backups = sorted(self.backup_dir.glob('backup_*.db'), key=os.path.getmtime, reverse=True)
            
            # اجمع جميع النسخ وفرزها حسب التاريخ
            all_backups = sorted(auto_backups + manual_backups, key=os.path.getmtime, reverse=True)
            
            # احتفظ بآخر 5 نسخ فقط
            max_backups = self.retention_policy['max_backups']
            
            for i, backup in enumerate(all_backups):
                if i >= max_backups:
                    backup.unlink()
                    logger.info(f'🗑️ Deleted old backup: {backup.name}')
                    
        except Exception as e:
            logger.error(f'❌ Cleanup failed: {str(e)}')
    
    def get_backup_status(self):
        auto_backups = sorted(self.backup_dir.glob('auto_backup_*.db'), key=os.path.getmtime, reverse=True)
        manual_backups = sorted(self.backup_dir.glob('backup_*.db'), key=os.path.getmtime, reverse=True)
        all_backups = sorted(auto_backups + manual_backups, key=os.path.getmtime, reverse=True)
        
        total_size = sum(b.stat().st_size for b in all_backups) / (1024 * 1024)
        
        latest_backup = None
        if all_backups:
            latest = all_backups[0]
            latest_backup = {
                'filename': latest.name,
                'date': datetime.fromtimestamp(latest.stat().st_mtime),
                'size_mb': latest.stat().st_size / (1024 * 1024)
            }
        
        return {
            'total_backups': len(all_backups),
            'total_size_mb': total_size,
            'latest_backup': latest_backup,
            'retention_policy': self.retention_policy
        }

def schedule_automated_backups(app, scheduler):
    backup_manager = AutomatedBackupManager(app)
    
    scheduler.add_job(
        func=backup_manager.create_backup,
        trigger='cron',
        hour=3,
        minute=0,
        id='daily_auto_backup',
        name='Daily Automated Backup',
        replace_existing=True
    )
    
    app.logger.info('✅ Automated daily backups scheduled at 3:00 AM')
    
    return backup_manager

