"""
⏰ AI Scheduler - جدولة المهام التلقائية
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- جدولة Auto-Learning يومياً
- تشغيل Scans تلقائياً
- تحديث المعرفة دورياً

Created: 2025-11-01
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import logging


# ═══════════════════════════════════════════════════════════════════════════
# 🔧 CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('AI_Scheduler')

# Scheduler
scheduler = BackgroundScheduler()
_scheduler_started = False


# ═══════════════════════════════════════════════════════════════════════════
# 📋 SCHEDULED JOBS
# ═══════════════════════════════════════════════════════════════════════════

def run_auto_learning_scan():
    """
    مهمة: Auto-Learning Scan
    
    تعمل: يومياً الساعة 3:00 صباحاً
    """
    try:
        logger.info("[SCAN] Starting scheduled Auto-Learning Scan...")
        
        from AI.engine.ai_auto_learning import get_auto_learning_engine
        
        engine = get_auto_learning_engine()
        result = engine.run_full_scan(force=False)
        
        if result['scanned']:
            changes = result.get('changes', {})
            
            new_tables = len(changes.get('new_tables', []))
            new_routes = len(changes.get('new_routes', []))
            new_models = len(changes.get('new_models', []))
            
            logger.info(f"[OK] Scan completed - {new_tables} new tables, {new_routes} new routes, {new_models} new models")
        else:
            logger.info(f"[SKIP] Scan skipped - {result.get('reason')}")
    
    except Exception as e:
        logger.error(f"[ERROR] Error in Auto-Learning Scan: {e}")


def cleanup_old_logs():
    """
    مهمة: تنظيف الـ Logs القديمة
    
    تعمل: أسبوعياً
    """
    try:
        logger.info("[CLEANUP] Cleaning up old logs...")
        
        import os
        from pathlib import Path
        from datetime import datetime, timedelta
        
        # حذف logs أقدم من 90 يوم
        cutoff_date = datetime.now() - timedelta(days=90)
        
        log_dirs = ['AI/data/daily_reports', 'AI/data']
        
        for log_dir in log_dirs:
            if not os.path.exists(log_dir):
                continue
            
            for file_path in Path(log_dir).glob('*.log'):
                if file_path.stat().st_mtime < cutoff_date.timestamp():
                    os.remove(file_path)
                    logger.info(f"[CLEANUP] Removed old log: {file_path}")
        
        logger.info("[OK] Cleanup completed")
    
    except Exception as e:
        logger.error(f"[ERROR] Error in cleanup: {e}")


def run_daily_code_scan():
    """
    مهمة: فحص الكود اليومي
    
    تعمل: يومياً الساعة 2:00 صباحاً
    """
    try:
        logger.info("[SCAN] Starting daily code quality scan...")
        
        from AI.engine.ai_code_quality_monitor import get_code_monitor
        
        monitor = get_code_monitor()
        report = monitor.run_daily_scan()
        
        logger.info(f"[OK] Code scan completed - Quality Score: {report['quality_score']}/100")
        logger.info(f"[OK] Total issues: {report['total_issues']}")
        
    except Exception as e:
        logger.error(f"[ERROR] Error in code scan: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# 🚀 SCHEDULER INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════

def start_scheduler():
    """
    تشغيل الجدولة
    
    يجب استدعاؤها عند بدء التطبيق
    """
    
    global _scheduler_started
    if _scheduler_started:
        logger.info("AI Scheduler already running; skipping re-initialization")
        return

    # مهمة 1: Code Quality Scan - يومياً الساعة 2:00 ص
    scheduler.add_job(
        func=run_daily_code_scan,
        trigger=CronTrigger(hour=2, minute=0),  # 2:00 AM
        id='daily_code_scan',
        name='Daily Code Quality Scan',
        replace_existing=True
    )
    
    # مهمة 2: Auto-Learning Scan - يومياً الساعة 3:00 ص
    scheduler.add_job(
        func=run_auto_learning_scan,
        trigger=CronTrigger(hour=3, minute=0),  # 3:00 AM
        id='auto_learning_scan',
        name='Auto-Learning Daily Scan',
        replace_existing=True
    )
    
    # مهمة 3: Cleanup - كل أسبوع
    scheduler.add_job(
        func=cleanup_old_logs,
        trigger=CronTrigger(day_of_week='sun', hour=1, minute=0),  # كل أحد 1:00 AM
        id='cleanup_logs',
        name='Weekly Logs Cleanup',
        replace_existing=True
    )
    
    # تشغيل الـ Scheduler
    scheduler.start()
    _scheduler_started = True
    
    logger.info("AI Scheduler started - All AI systems enabled")
    logger.info("   Daily Code Scan: 2:00 AM")
    logger.info("   Daily Auto-Learning Scan: 3:00 AM")
    logger.info("   Weekly Cleanup: Sunday 1:00 AM")


def stop_scheduler():
    """إيقاف الجدولة"""
    global _scheduler_started
    if not _scheduler_started:
        return
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        _scheduler_started = False
        logger.info("🛑 AI Scheduler stopped")
    except Exception as e:
        logger.warning(f"Error stopping scheduler: {e}")
        _scheduler_started = False


def run_manual_scan():
    """
    تشغيل Scan يدوياً (للاختبار)
    
    يمكن استدعاؤها من أي مكان
    """
    run_auto_learning_scan()


__all__ = [
    'start_scheduler',
    'stop_scheduler',
    'run_manual_scan'
]

