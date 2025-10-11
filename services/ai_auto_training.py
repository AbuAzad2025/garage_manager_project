# ai_auto_training.py - AI Auto Training System
# Location: /garage_manager/services/ai_auto_training.py
# Description: AI automatic training and learning system

"""
🤖 AI Auto Training System
نظام التدريب الصامت التلقائي

يقوم بتدريب المساعد الذكي تلقائياً كل 48 ساعة
أو عند اكتشاف تعديلات على الملفات

Developer: Ahmed Ghannam
Location: Ramallah, Palestine 🇵🇸
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path


AUTO_TRAINING_LOG = 'instance/ai_auto_training.json'


def should_auto_train():
    """فحص إذا كان التدريب التلقائي مطلوب"""
    try:
        if not os.path.exists(AUTO_TRAINING_LOG):
            return True  # أول تدريب
        
        with open(AUTO_TRAINING_LOG, 'r', encoding='utf-8') as f:
            log = json.load(f)
        
        last_training = log.get('last_training')
        if not last_training:
            return True
        
        # فحص إذا مر أكثر من 48 ساعة
        last_dt = datetime.fromisoformat(last_training)
        hours_passed = (datetime.now() - last_dt).total_seconds() / 3600
        
        if hours_passed > 48:
            return True
        
        # فحص إذا تغيرت الملفات الحيوية
        files_to_check = ['models.py', 'routes/', 'templates/', 'forms.py']
        current_mtime = 0
        
        for file_path in files_to_check:
            path = Path(file_path)
            if path.exists():
                if path.is_file():
                    current_mtime = max(current_mtime, path.stat().st_mtime)
                elif path.is_dir():
                    for f in path.rglob('*.py'):
                        current_mtime = max(current_mtime, f.stat().st_mtime)
        
        last_checked_mtime = log.get('last_files_mtime', 0)
        
        if current_mtime > last_checked_mtime:
            return True  # تم تعديل ملفات
        
        return False
    
    except:
        return False


def execute_silent_training():
    """تنفيذ التدريب الصامت"""
    try:
        from services.ai_knowledge import get_knowledge_base
        from services.ai_auto_discovery import build_system_map
        from services.ai_data_awareness import build_data_schema
        
        print("\n🤖 [Auto Training] بدء التدريب الصامت...")
        
        # تنفيذ التدريب
        kb = get_knowledge_base()
        kb.index_all_files(force_reindex=True)
        
        build_system_map()
        build_data_schema()
        
        # تسجيل الحدث
        log_auto_training()
        
        print("✅ [Auto Training] اكتمل التدريب الصامت")
        
        return True
    
    except Exception as e:
        print(f"❌ [Auto Training] فشل التدريب: {str(e)}")
        return False


def log_auto_training():
    """تسجيل حدث التدريب التلقائي"""
    try:
        os.makedirs('instance', exist_ok=True)
        
        # حساب mtime للملفات
        files_to_check = ['models.py', 'routes/', 'templates/', 'forms.py']
        current_mtime = 0
        
        for file_path in files_to_check:
            path = Path(file_path)
            if path.exists():
                if path.is_file():
                    current_mtime = max(current_mtime, path.stat().st_mtime)
                elif path.is_dir():
                    for f in path.rglob('*.py'):
                        current_mtime = max(current_mtime, f.stat().st_mtime)
        
        log_entry = {
            'last_training': datetime.now().isoformat(),
            'last_files_mtime': current_mtime,
            'auto_trainings_count': 0
        }
        
        if os.path.exists(AUTO_TRAINING_LOG):
            with open(AUTO_TRAINING_LOG, 'r', encoding='utf-8') as f:
                old_log = json.load(f)
                log_entry['auto_trainings_count'] = old_log.get('auto_trainings_count', 0) + 1
        
        with open(AUTO_TRAINING_LOG, 'w', encoding='utf-8') as f:
            json.dump(log_entry, f, ensure_ascii=False, indent=2)
    
    except Exception as e:
        print(f"⚠️  فشل تسجيل التدريب التلقائي: {str(e)}")


def init_auto_training():
    """تهيئة نظام التدريب التلقائي (يُستدعى عند بدء النظام)"""
    try:
        if should_auto_train():
            execute_silent_training()
    except:
        pass


if __name__ == '__main__':
    print("🧪 اختبار نظام التدريب التلقائي...")
    if should_auto_train():
        print("✅ التدريب مطلوب - سيتم التنفيذ...")
    else:
        print("ℹ️  لا حاجة للتدريب حالياً")

