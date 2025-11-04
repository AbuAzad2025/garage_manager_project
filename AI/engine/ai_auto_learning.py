"""
🧠 AI Auto-Learning Engine - محرك التعلم الذاتي التلقائي
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- اكتشاف تلقائي للتحديثات في النظام
- فهرسة تلقائية للجداول والحقول الجديدة
- اكتشاف Routes جديدة
- تحديث المعرفة تلقائياً
- عمل Scan يومي للنظام

Created: 2025-11-01
Version: Auto-Learning 1.0
"""

import os
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Set
from sqlalchemy import inspect, MetaData
from extensions import db


# ═══════════════════════════════════════════════════════════════════════════
# 📁 FILE PATHS
# ═══════════════════════════════════════════════════════════════════════════

AUTO_LEARNING_LOG = 'AI/data/auto_learning_log.json'
LAST_SCAN_FILE = 'AI/data/last_scan.json'
DISCOVERED_CHANGES = 'AI/data/discovered_changes.json'


# ═══════════════════════════════════════════════════════════════════════════
# 🔍 AUTO SCANNER - الماسح التلقائي
# ═══════════════════════════════════════════════════════════════════════════

class AutoLearningEngine:
    """
    محرك التعلم الذاتي
    
    يعمل تلقائياً كل يوم ويكتشف:
    - جداول جديدة في قاعدة البيانات
    - حقول جديدة في الجداول
    - Routes جديدة
    - ملفات Python جديدة
    - Templates جديدة
    - Forms جديدة
    """
    
    def __init__(self):
        self.base_path = Path('.')
        self.changes = {
            'new_tables': [],
            'new_fields': {},
            'new_routes': [],
            'new_files': [],
            'new_templates': [],
            'timestamp': None
        }
        self.load_last_scan()
    
    def should_run_scan(self) -> bool:
        """
        هل يجب عمل Scan؟
        
        Returns:
            True إذا مر أكثر من 24 ساعة على آخر scan
        """
        if not self.last_scan_time:
            return True
        
        time_diff = datetime.now() - datetime.fromisoformat(self.last_scan_time)
        
        # إذا مر أكثر من 24 ساعة
        return time_diff > timedelta(hours=24)
    
    def load_last_scan(self):
        """تحميل معلومات آخر scan"""
        try:
            if os.path.exists(LAST_SCAN_FILE):
                with open(LAST_SCAN_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.last_scan_time = data.get('timestamp')
                    self.last_scan_data = data.get('snapshot', {})
            else:
                self.last_scan_time = None
                self.last_scan_data = {}
        except:
            self.last_scan_time = None
            self.last_scan_data = {}
    
    def save_scan(self, snapshot: Dict):
        """حفظ معلومات الـ Scan الحالي"""
        try:
            os.makedirs('AI/data', exist_ok=True)
            
            data = {
                'timestamp': datetime.now().isoformat(),
                'snapshot': snapshot
            }
            
            with open(LAST_SCAN_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving scan: {e}")
    
    def run_full_scan(self, force: bool = False) -> Dict[str, Any]:
        """
        عمل Scan شامل للنظام
        
        Args:
            force: إجبار الـ Scan حتى لو لم يمر 24 ساعة
        
        Returns:
            تقرير بالتغييرات المكتشفة
        """
        if not force and not self.should_run_scan():
            return {
                'scanned': False,
                'reason': 'Too soon - last scan was less than 24 hours ago',
                'last_scan': self.last_scan_time
            }
        
        print("[SCAN] Starting Auto-Learning Scan...")
        
        # إنشاء snapshot حالي
        current_snapshot = {
            'tables': self.scan_database_tables(),
            'routes': self.scan_routes(),
            'models': self.scan_models(),
            'templates': self.scan_templates(),
            'forms': self.scan_forms()
        }
        
        # مقارنة مع الـ Scan السابق
        if self.last_scan_data:
            changes = self.detect_changes(self.last_scan_data, current_snapshot)
        else:
            changes = {'first_scan': True, 'message': 'أول scan - تم فهرسة النظام بالكامل'}
        
        # حفظ الـ Snapshot الحالي
        self.save_scan(current_snapshot)
        
        # حفظ التغييرات
        self.save_changes(changes)
        
        # تحديث قاعدة المعرفة
        self.update_knowledge_base(changes)
        
        # تسجيل في الـ Log
        self.log_scan(changes)
        
        print(f"[OK] Scan completed - {len(changes.get('new_tables', []))} new tables, {len(changes.get('new_routes', []))} new routes")
        
        return {
            'scanned': True,
            'timestamp': datetime.now().isoformat(),
            'changes': changes,
            'snapshot': current_snapshot
        }
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🗄️ DATABASE SCANNING - فحص قاعدة البيانات
    # ═══════════════════════════════════════════════════════════════════════
    
    def scan_database_tables(self) -> Dict[str, Any]:
        """
        فحص جميع الجداول والحقول في قاعدة البيانات
        
        Returns:
            {
                'table_name': {
                    'fields': ['field1', 'field2', ...],
                    'field_types': {'field1': 'Integer', ...}
                }
            }
        """
        try:
            inspector = inspect(db.engine)
            tables_info = {}
            
            for table_name in inspector.get_table_names():
                columns = inspector.get_columns(table_name)
                
                fields = []
                field_types = {}
                
                for col in columns:
                    field_name = col['name']
                    field_type = str(col['type'])
                    
                    fields.append(field_name)
                    field_types[field_name] = field_type
                
                tables_info[table_name] = {
                    'fields': fields,
                    'field_types': field_types,
                    'field_count': len(fields)
                }
            
            return tables_info
            
        except Exception as e:
            print(f"Error scanning database: {e}")
            return {}
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🛣️ ROUTES SCANNING - فحص المسارات
    # ═══════════════════════════════════════════════════════════════════════
    
    def scan_routes(self) -> List[Dict[str, Any]]:
        """
        فحص جميع الـ Routes في مجلد routes/
        
        Returns:
            [
                {
                    'path': '/customers',
                    'methods': ['GET', 'POST'],
                    'function': 'index',
                    'file': 'routes/customers.py'
                }
            ]
        """
        routes = []
        routes_dir = self.base_path / 'routes'
        
        if not routes_dir.exists():
            return routes
        
        for py_file in routes_dir.glob('*.py'):
            if py_file.name.startswith('__'):
                continue
            
            try:
                content = py_file.read_text(encoding='utf-8')
                
                # البحث عن @blueprint.route
                route_pattern = r'@\w+_bp\.route\([\'"](.+?)[\'"]\s*(?:,\s*methods=\[(.+?)\])?\)'
                
                for match in re.finditer(route_pattern, content):
                    path = match.group(1)
                    methods = match.group(2)
                    
                    if methods:
                        methods = [m.strip().strip('"\'') for m in methods.split(',')]
                    else:
                        methods = ['GET']
                    
                    routes.append({
                        'path': path,
                        'methods': methods,
                        'file': str(py_file.relative_to(self.base_path))
                    })
            
            except Exception as e:
                print(f"Error scanning {py_file}: {e}")
        
        return routes
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📋 MODELS SCANNING - فحص الموديلات
    # ═══════════════════════════════════════════════════════════════════════
    
    def scan_models(self) -> List[str]:
        """
        فحص ملف models.py واكتشاف الـ Classes
        
        Returns:
            ['Customer', 'Supplier', 'Product', ...]
        """
        models = []
        models_file = self.base_path / 'models.py'
        
        if not models_file.exists():
            return models
        
        try:
            content = models_file.read_text(encoding='utf-8')
            
            # البحث عن class ... (db.Model):
            class_pattern = r'^class\s+(\w+)\s*\([^)]*db\.Model[^)]*\):'
            
            for match in re.finditer(class_pattern, content, re.MULTILINE):
                class_name = match.group(1)
                models.append(class_name)
        
        except Exception as e:
            print(f"Error scanning models: {e}")
        
        return models
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🎨 TEMPLATES SCANNING - فحص القوالب
    # ═══════════════════════════════════════════════════════════════════════
    
    def scan_templates(self) -> List[str]:
        """
        فحص مجلد templates/
        
        Returns:
            ['customers/index.html', 'sales/form.html', ...]
        """
        templates = []
        templates_dir = self.base_path / 'templates'
        
        if not templates_dir.exists():
            return templates
        
        for html_file in templates_dir.rglob('*.html'):
            relative_path = str(html_file.relative_to(templates_dir))
            templates.append(relative_path)
        
        return templates
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📝 FORMS SCANNING - فحص الفورمات
    # ═══════════════════════════════════════════════════════════════════════
    
    def scan_forms(self) -> List[str]:
        """
        فحص ملف forms.py
        
        Returns:
            ['CustomerForm', 'ProductForm', ...]
        """
        forms = []
        forms_file = self.base_path / 'forms.py'
        
        if not forms_file.exists():
            return forms
        
        try:
            content = forms_file.read_text(encoding='utf-8')
            
            # البحث عن class ...Form(FlaskForm):
            form_pattern = r'^class\s+(\w+Form)\s*\('
            
            for match in re.finditer(form_pattern, content, re.MULTILINE):
                form_name = match.group(1)
                forms.append(form_name)
        
        except Exception as e:
            print(f"Error scanning forms: {e}")
        
        return forms
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🔄 CHANGE DETECTION - اكتشاف التغييرات
    # ═══════════════════════════════════════════════════════════════════════
    
    def detect_changes(self, old_snapshot: Dict, new_snapshot: Dict) -> Dict[str, Any]:
        """
        مقارنة الـ Snapshot القديم بالجديد واكتشاف التغييرات
        
        Returns:
            {
                'new_tables': [...],
                'new_fields': {...},
                'new_routes': [...],
                'new_models': [...],
                'new_templates': [...],
                'new_forms': [...]
            }
        """
        changes = {}
        
        # 1. جداول جديدة
        old_tables = set(old_snapshot.get('tables', {}).keys())
        new_tables = set(new_snapshot.get('tables', {}).keys())
        changes['new_tables'] = list(new_tables - old_tables)
        
        # 2. حقول جديدة في جداول موجودة
        changes['new_fields'] = {}
        for table_name in old_tables & new_tables:
            old_fields = set(old_snapshot['tables'][table_name]['fields'])
            new_fields = set(new_snapshot['tables'][table_name]['fields'])
            
            added_fields = list(new_fields - old_fields)
            if added_fields:
                changes['new_fields'][table_name] = added_fields
        
        # 3. Routes جديدة
        old_routes = set(r['path'] for r in old_snapshot.get('routes', []))
        new_routes = [r for r in new_snapshot.get('routes', []) if r['path'] not in old_routes]
        changes['new_routes'] = new_routes
        
        # 4. Models جديدة
        old_models = set(old_snapshot.get('models', []))
        new_models = set(new_snapshot.get('models', []))
        changes['new_models'] = list(new_models - old_models)
        
        # 5. Templates جديدة
        old_templates = set(old_snapshot.get('templates', []))
        new_templates = set(new_snapshot.get('templates', []))
        changes['new_templates'] = list(new_templates - old_templates)
        
        # 6. Forms جديدة
        old_forms = set(old_snapshot.get('forms', []))
        new_forms = set(new_snapshot.get('forms', []))
        changes['new_forms'] = list(new_forms - old_forms)
        
        return changes
    
    # ═══════════════════════════════════════════════════════════════════════
    # 💾 KNOWLEDGE UPDATE - تحديث قاعدة المعرفة
    # ═══════════════════════════════════════════════════════════════════════
    
    def update_knowledge_base(self, changes: Dict):
        """
        تحديث قاعدة المعرفة بناءً على التغييرات المكتشفة
        """
        try:
            from AI.engine.ai_knowledge import get_knowledge_base
            
            kb = get_knowledge_base()
            
            # إعادة فهرسة إذا كان هناك تغييرات
            if any(changes.get(k) for k in ['new_tables', 'new_routes', 'new_models']):
                kb.index_all_files(force_reindex=True)
                print("[OK] Knowledge base updated")
        
        except Exception as e:
            print(f"Error updating knowledge base: {e}")
    
    def save_changes(self, changes: Dict):
        """حفظ التغييرات المكتشفة"""
        try:
            os.makedirs('AI/data', exist_ok=True)
            
            with open(DISCOVERED_CHANGES, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'changes': changes
                }, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            print(f"Error saving changes: {e}")
    
    def log_scan(self, changes: Dict):
        """تسجيل الـ Scan في الـ Log"""
        try:
            # تحميل الـ Log الحالي
            if os.path.exists(AUTO_LEARNING_LOG):
                with open(AUTO_LEARNING_LOG, 'r', encoding='utf-8') as f:
                    log = json.load(f)
            else:
                log = []
            
            # إضافة سجل جديد
            log.append({
                'timestamp': datetime.now().isoformat(),
                'changes_count': {
                    'tables': len(changes.get('new_tables', [])),
                    'fields': len(changes.get('new_fields', {})),
                    'routes': len(changes.get('new_routes', [])),
                    'models': len(changes.get('new_models', [])),
                    'templates': len(changes.get('new_templates', [])),
                    'forms': len(changes.get('new_forms', []))
                },
                'changes': changes
            })
            
            # الاحتفاظ بآخر 100 سجل
            log = log[-100:]
            
            # حفظ
            os.makedirs('AI/data', exist_ok=True)
            with open(AUTO_LEARNING_LOG, 'w', encoding='utf-8') as f:
                json.dump(log, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            print(f"Error logging scan: {e}")
    
    def get_scan_history(self, limit: int = 10) -> List[Dict]:
        """الحصول على تاريخ الـ Scans"""
        try:
            if os.path.exists(AUTO_LEARNING_LOG):
                with open(AUTO_LEARNING_LOG, 'r', encoding='utf-8') as f:
                    log = json.load(f)
                    return log[-limit:]
            return []
        except:
            return []


# ═══════════════════════════════════════════════════════════════════════════
# 🔄 AUTO-RUN SCHEDULER - جدولة تلقائية
# ═══════════════════════════════════════════════════════════════════════════

def schedule_daily_scan():
    """
    جدولة Scan يومي تلقائي
    
    يعمل كل 24 ساعة
    """
    engine = get_auto_learning_engine()
    
    # عمل Scan
    result = engine.run_full_scan(force=False)
    
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 SINGLETON
# ═══════════════════════════════════════════════════════════════════════════

_auto_learning_engine = None

def get_auto_learning_engine() -> AutoLearningEngine:
    """الحصول على محرك التعلم الذاتي (Singleton)"""
    global _auto_learning_engine
    
    if _auto_learning_engine is None:
        _auto_learning_engine = AutoLearningEngine()
    
    return _auto_learning_engine


__all__ = [
    'AutoLearningEngine',
    'get_auto_learning_engine',
    'schedule_daily_scan'
]

