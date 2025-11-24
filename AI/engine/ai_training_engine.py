"""
🎓 AI Training Engine - محرك التدريب الحقيقي
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- تدريب حقيقي للمساعد
- فحص شامل للنظام
- بناء معرفة كاملة
- حفظ وتحديث المعرفة

Created: 2025-11-01
Version: Training Engine 2.0 - REAL
"""

import os
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy import inspect, text
from extensions import db
import threading
import time


# ═══════════════════════════════════════════════════════════════════════════
# 📁 FILE PATHS
# ═══════════════════════════════════════════════════════════════════════════

TRAINING_STATUS_FILE = 'AI/data/training_status.json'
TRAINING_LOG_FILE = 'AI/data/training_log.json'
KNOWLEDGE_BASE_FILE = 'AI/data/complete_system_knowledge.json'


# ═══════════════════════════════════════════════════════════════════════════
# 🎓 TRAINING ENGINE - محرك التدريب
# ═══════════════════════════════════════════════════════════════════════════

class AITrainingEngine:
    """
    محرك التدريب الحقيقي
    
    يقوم بـ:
    1. فحص شامل لقاعدة البيانات (كل الجداول والحقول)
    2. فحص كل الملفات (models, routes, forms, templates)
    3. فحص كل العلاقات
    4. فحص كل الـ Enums
    5. بناء معرفة كاملة
    6. حفظ المعرفة في JSON
    """
    
    def __init__(self):
        self.base_path = Path('.')
        self.status = {
            'running': False,
            'progress': 0.0,
            'current_step': '',
            'started_at': None,
            'completed_at': None,
            'error': None
        }
        self.total_steps = 9
        self.knowledge = {}
        self.load_status()
    
    def load_status(self):
        """تحميل حالة التدريب"""
        try:
            if os.path.exists(TRAINING_STATUS_FILE):
                with open(TRAINING_STATUS_FILE, 'r', encoding='utf-8') as f:
                    self.status = json.load(f)
        except Exception:
            pass
    
    def save_status(self):
        """حفظ حالة التدريب"""
        try:
            os.makedirs('AI/data', exist_ok=True)
            with open(TRAINING_STATUS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.status, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] Error saving training status: {e}")
    
    def log_step(self, step: str, details: Dict = None):
        """تسجيل خطوة في الـ Log"""
        try:
            if os.path.exists(TRAINING_LOG_FILE):
                with open(TRAINING_LOG_FILE, 'r', encoding='utf-8') as f:
                    log = json.load(f)
            else:
                log = []
            
            log.append({
                'timestamp': datetime.now().isoformat(),
                'step': step,
                'details': details or {}
            })
            
            # الاحتفاظ بآخر 500 سجل
            log = log[-500:]
            
            os.makedirs('AI/data', exist_ok=True)
            with open(TRAINING_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(log, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            print(f"[ERROR] Error logging step: {e}")
    
    def run_full_training(self, force: bool = False) -> Dict[str, Any]:
        from AI.engine.ai_integrated_intelligence import get_integrated_intelligence
        
        ai = get_integrated_intelligence()
        
        if not force and ai.learning_system:
            stats = ai.learning_system.get_learning_stats()
            if stats['total_learned_queries'] > 100:
                return {
                    'success': True,
                    'message': 'Already trained',
                    'stats': stats
                }
        
        return self._run_training_process(force)
    
    def _run_training_process(self, force: bool = False) -> Dict[str, Any]:
        """
        تشغيل تدريب كامل
        
        Args:
            force: إجبار التدريب حتى لو كان يعمل
        
        Returns:
            تقرير بالتدريب
        """
        if self.status.get('running') and not force:
            return {
                'success': False,
                'error': 'Training already running',
                'status': self.status
            }
        
        # بدء التدريب
        self.status = {
            'running': True,
            'progress': 0.0,
            'current_step': 'Initializing...',
            'started_at': datetime.now().isoformat(),
            'completed_at': None,
            'error': None
        }
        self.save_status()
        
        try:
            # الخطوة 1: فحص قاعدة البيانات
            self._update_progress(1, 'Scanning database...')
            db_knowledge = self._scan_database_complete()
            self.knowledge['database'] = db_knowledge
            self.log_step('database_scan', {
                'tables_count': len(db_knowledge.get('tables', {})),
                'total_fields': sum(len(t.get('fields', [])) for t in db_knowledge.get('tables', {}).values())
            })
            
            # الخطوة 2: فحص الموديلات
            self._update_progress(2, 'Scanning models...')
            models_knowledge = self._scan_models_complete()
            self.knowledge['models'] = models_knowledge
            self.log_step('models_scan', {
                'models_count': len(models_knowledge.get('classes', []))
            })
            
            # الخطوة 3: فحص Routes
            self._update_progress(3, 'Scanning routes...')
            routes_knowledge = self._scan_routes_complete()
            self.knowledge['routes'] = routes_knowledge
            self.log_step('routes_scan', {
                'routes_count': len(routes_knowledge.get('routes', []))
            })
            
            # الخطوة 4: فحص Forms
            self._update_progress(4, 'Scanning forms...')
            forms_knowledge = self._scan_forms_complete()
            self.knowledge['forms'] = forms_knowledge
            self.log_step('forms_scan', {
                'forms_count': len(forms_knowledge.get('forms', []))
            })
            
            # الخطوة 5: فحص Templates
            self._update_progress(5, 'Scanning templates...')
            templates_knowledge = self._scan_templates_complete()
            self.knowledge['templates'] = templates_knowledge
            self.log_step('templates_scan', {
                'templates_count': len(templates_knowledge.get('templates', []))
            })
            
            # الخطوة 6: فحص العلاقات
            self._update_progress(6, 'Analyzing relationships...')
            relationships = self._analyze_relationships()
            self.knowledge['relationships'] = relationships
            self.log_step('relationships_analysis', {
                'relationships_count': len(relationships)
            })
            
            # الخطوة 7: فحص Enums
            self._update_progress(7, 'Scanning enums...')
            enums = self._scan_enums()
            self.knowledge['enums'] = enums
            self.log_step('enums_scan', {
                'enums_count': len(enums)
            })
            
            # الخطوة 8: تدريب الوحدات الخاصة (Checks, Vendors, Partners, Products, Owner)
            self._update_progress(8, 'Training specialized modules...')
            specialized_modules = self._train_specialized_modules()
            self.knowledge['specialized_modules'] = specialized_modules
            self.log_step('specialized_modules', {
                'modules_trained': len(specialized_modules)
            })
            
            # الخطوة 9: حفظ المعرفة
            self._update_progress(9, 'Saving knowledge base...')
            self._save_knowledge_base()
            self.log_step('knowledge_saved', {
                'file': KNOWLEDGE_BASE_FILE
            })
            
            # إكمال
            self.status.update({
                'running': False,
                'progress': 100.0,
                'current_step': 'Completed',
                'completed_at': datetime.now().isoformat(),
                'error': None
            })
            self.save_status()
            
            return {
                'success': True,
                'message': 'Training completed successfully',
                'status': self.status,
                'knowledge_summary': {
                    'tables': len(db_knowledge.get('tables', {})),
                    'models': len(models_knowledge.get('classes', [])),
                    'routes': len(routes_knowledge.get('routes', [])),
                    'forms': len(forms_knowledge.get('forms', [])),
                    'templates': len(templates_knowledge.get('templates', [])),
                    'relationships': len(relationships),
                    'enums': len(enums)
                }
            }
        
        except Exception as e:
            self.status.update({
                'running': False,
                'error': str(e),
                'completed_at': datetime.now().isoformat()
            })
            self.save_status()
            self.log_step('error', {'error': str(e)})
            
            return {
                'success': False,
                'error': str(e),
                'status': self.status
            }
    
    def _update_progress(self, step: int, message: str):
        """تحديث التقدم"""
        progress = (step / self.total_steps) * 100
        self.status.update({
            'progress': round(progress, 2),
            'current_step': message
        })
        self.save_status()
        print(f"[TRAINING] {progress:.1f}% - {message}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🗄️ DATABASE SCANNING - فحص شامل لقاعدة البيانات
    # ═══════════════════════════════════════════════════════════════════════
    
    def _scan_database_complete(self) -> Dict[str, Any]:
        """
        فحص شامل لقاعدة البيانات
        
        Returns:
            {
                'tables': {
                    'table_name': {
                        'fields': [...],
                        'field_types': {...},
                        'primary_keys': [...],
                        'foreign_keys': [...],
                        'indexes': [...],
                        'constraints': [...]
                    }
                }
            }
        """
        try:
            from flask import has_app_context
            if not has_app_context():
                return {'error': 'No application context'}
                
            from extensions import db
            from sqlalchemy import inspect
            
            inspector = inspect(db.engine)
            tables_info = {}
            
            for table_name in inspector.get_table_names():
                # الحقول
                columns = inspector.get_columns(table_name)
                
                fields = []
                field_types = {}
                nullable_fields = []
                
                for col in columns:
                    field_name = col['name']
                    field_type = str(col['type'])
                    is_nullable = col.get('nullable', True)
                    
                    fields.append(field_name)
                    field_types[field_name] = {
                        'type': field_type,
                        'nullable': is_nullable,
                        'default': col.get('default'),
                        'autoincrement': col.get('autoincrement', False)
                    }
                    
                    if is_nullable:
                        nullable_fields.append(field_name)
                
                # Primary Keys
                pk_constraint = inspector.get_pk_constraint(table_name)
                primary_keys = pk_constraint.get('constrained_columns', [])
                
                # Foreign Keys
                foreign_keys = []
                fk_constraints = inspector.get_foreign_keys(table_name)
                for fk in fk_constraints:
                    foreign_keys.append({
                        'columns': fk.get('constrained_columns', []),
                        'referred_table': fk.get('referred_table'),
                        'referred_columns': fk.get('referred_columns', [])
                    })
                
                # Indexes
                indexes = []
                for idx in inspector.get_indexes(table_name):
                    indexes.append({
                        'name': idx.get('name'),
                        'columns': idx.get('column_names', []),
                        'unique': idx.get('unique', False)
                    })
                
                tables_info[table_name] = {
                    'fields': fields,
                    'field_types': field_types,
                    'field_count': len(fields),
                    'primary_keys': primary_keys,
                    'foreign_keys': foreign_keys,
                    'indexes': indexes,
                    'nullable_fields': nullable_fields
                }
            
            return {
                'tables': tables_info,
                'total_tables': len(tables_info),
                'scanned_at': datetime.now().isoformat()
            }
        
        except Exception as e:
            print(f"[ERROR] Error scanning database: {e}")
            return {'error': str(e)}
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📋 MODELS SCANNING - فحص شامل للموديلات
    # ═══════════════════════════════════════════════════════════════════════
    
    def _scan_models_complete(self) -> Dict[str, Any]:
        """فحص شامل لملف models.py"""
        models_file = self.base_path / 'models.py'
        
        if not models_file.exists():
            return {'error': 'models.py not found'}
        
        try:
            content = models_file.read_text(encoding='utf-8')
            
            classes = []
            
            # البحث عن class ... (db.Model):
            class_pattern = r'^class\s+(\w+)\s*\([^)]*db\.Model[^)]*\):'
            
            for match in re.finditer(class_pattern, content, re.MULTILINE):
                class_name = match.group(1)
                
                # البحث عن الحقول
                class_start = match.end()
                class_end = self._find_class_end(content, class_start)
                class_content = content[class_start:class_end]
                
                # استخراج الحقول
                field_pattern = r'(\w+)\s*=\s*db\.(Column|relationship|hybrid_property)'
                fields = re.findall(field_pattern, class_content)
                
                classes.append({
                    'name': class_name,
                    'fields': [f[0] for f in fields],
                    'field_types': [f[1] for f in fields]
                })
            
            return {
                'classes': classes,
                'total_classes': len(classes),
                'scanned_at': datetime.now().isoformat()
            }
        
        except Exception as e:
            return {'error': str(e)}
    
    def _find_class_end(self, content: str, start: int) -> int:
        """العثور على نهاية الـ class"""
        indent_level = 0
        for i in range(start, len(content)):
            if content[i] == '\n':
                line = content[i:content.find('\n', i+1) if content.find('\n', i+1) != -1 else len(content)]
                
                if line.strip() and not line.strip().startswith(' ') and not line.strip().startswith('\t'):
                    if not line.strip().startswith('class '):
                        return i
        return len(content)
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🛣️ ROUTES SCANNING - فحص شامل للمسارات
    # ═══════════════════════════════════════════════════════════════════════
    
    def _scan_routes_complete(self) -> Dict[str, Any]:
        """فحص شامل لكل Routes"""
        routes = []
        routes_dir = self.base_path / 'routes'
        
        if not routes_dir.exists():
            return {'routes': []}
        
        for py_file in routes_dir.rglob('*.py'):
            if py_file.name.startswith('__'):
                continue
            
            try:
                content = py_file.read_text(encoding='utf-8')
                
                # البحث عن @blueprint.route
                route_pattern = r'@(\w+_bp)\.route\([\'"](.+?)[\'"]\s*(?:,\s*methods=\[(.+?)\])?\)'
                
                for match in re.finditer(route_pattern, content):
                    blueprint = match.group(1)
                    path = match.group(2)
                    methods_str = match.group(3)
                    
                    if methods_str:
                        methods = [m.strip().strip('"\'') for m in methods_str.split(',')]
                    else:
                        methods = ['GET']
                    
                    # البحث عن اسم الدالة
                    func_match = re.search(r'def\s+(\w+)\s*\(', content[match.end():match.end()+200])
                    func_name = func_match.group(1) if func_match else 'unknown'
                    
                    routes.append({
                        'path': path,
                        'methods': methods,
                        'function': func_name,
                        'blueprint': blueprint,
                        'file': str(py_file.relative_to(self.base_path))
                    })
            
            except Exception as e:
                print(f"[ERROR] Error scanning {py_file}: {e}")
        
        return {
            'routes': routes,
            'total_routes': len(routes),
            'scanned_at': datetime.now().isoformat()
        }
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📝 FORMS SCANNING - فحص شامل للفورمات
    # ═══════════════════════════════════════════════════════════════════════
    
    def _scan_forms_complete(self) -> Dict[str, Any]:
        """فحص شامل لملف forms.py"""
        forms_file = self.base_path / 'forms.py'
        
        if not forms_file.exists():
            return {'forms': []}
        
        try:
            content = forms_file.read_text(encoding='utf-8')
            
            forms = []
            
            # البحث عن class ...Form(FlaskForm):
            form_pattern = r'^class\s+(\w+Form)\s*\([^)]*FlaskForm[^)]*\):'
            
            for match in re.finditer(form_pattern, content, re.MULTILINE):
                form_name = match.group(1)
                
                # البحث عن الحقول
                form_start = match.end()
                form_end = self._find_class_end(content, form_start)
                form_content = content[form_start:form_end]
                
                # استخراج الحقول
                field_pattern = r'(\w+)\s*=\s*(StringField|IntegerField|DecimalField|SelectField|DateField|BooleanField|TextAreaField)'
                fields = re.findall(field_pattern, form_content)
                
                forms.append({
                    'name': form_name,
                    'fields': [f[0] for f in fields],
                    'field_types': [f[1] for f in fields]
                })
            
            return {
                'forms': forms,
                'total_forms': len(forms),
                'scanned_at': datetime.now().isoformat()
            }
        
        except Exception as e:
            return {'error': str(e)}
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🎨 TEMPLATES SCANNING - فحص شامل للقوالب
    # ═══════════════════════════════════════════════════════════════════════
    
    def _scan_templates_complete(self) -> Dict[str, Any]:
        """فحص شامل للقوالب"""
        templates = []
        templates_dir = self.base_path / 'templates'
        
        if not templates_dir.exists():
            return {'templates': []}
        
        for html_file in templates_dir.rglob('*.html'):
            relative_path = str(html_file.relative_to(templates_dir))
            
            try:
                content = html_file.read_text(encoding='utf-8')
                
                # البحث عن extends و includes
                extends = re.findall(r'{%\s*extends\s+[\'"](.+?)[\'"]\s*%}', content)
                includes = re.findall(r'{%\s*include\s+[\'"](.+?)[\'"]\s*%}', content)
                
                templates.append({
                    'path': relative_path,
                    'extends': extends,
                    'includes': includes,
                    'size': len(content),
                    'lines': content.count('\n')
                })
            
            except Exception as e:
                print(f"[ERROR] Error scanning {html_file}: {e}")
        
        return {
            'templates': templates,
            'total_templates': len(templates),
            'scanned_at': datetime.now().isoformat()
        }
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🔗 RELATIONSHIPS ANALYSIS - تحليل العلاقات
    # ═══════════════════════════════════════════════════════════════════════
    
    def _analyze_relationships(self) -> List[Dict[str, Any]]:
        """تحليل العلاقات بين الجداول"""
        relationships = []
        
        try:
            from flask import has_app_context
            if not has_app_context():
                return []
                
            from extensions import db
            from sqlalchemy import inspect
            
            inspector = inspect(db.engine)
            
            for table_name in inspector.get_table_names():
                fk_constraints = inspector.get_foreign_keys(table_name)
                
                for fk in fk_constraints:
                    relationships.append({
                        'from_table': table_name,
                        'from_columns': fk.get('constrained_columns', []),
                        'to_table': fk.get('referred_table'),
                        'to_columns': fk.get('referred_columns', []),
                        'type': 'many-to-one' if len(fk.get('constrained_columns', [])) == 1 else 'composite'
                    })
        
        except Exception as e:
            print(f"[ERROR] Error analyzing relationships: {e}")
        
        return relationships
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🔢 ENUMS SCANNING - فحص الـ Enums
    # ═══════════════════════════════════════════════════════════════════════
    
    def _scan_enums(self) -> List[Dict[str, Any]]:
        """فحص جميع الـ Enums"""
        enums = []
        
        # فحص models.py
        models_file = self.base_path / 'models.py'
        if models_file.exists():
            try:
                content = models_file.read_text(encoding='utf-8')
                
                # البحث عن Enum
                enum_pattern = r'(class\s+(\w+)\s*\([^)]*Enum[^)]*\):.*?)(?=class\s+\w+|$)'
                
                for match in re.finditer(enum_pattern, content, re.MULTILINE | re.DOTALL):
                    enum_name = match.group(2)
                    enum_content = match.group(1)
                    
                    # استخراج القيم
                    value_pattern = r'(\w+)\s*=\s*[\'"](\w+)[\'"]'
                    values = re.findall(value_pattern, enum_content)
                    
                    enums.append({
                        'name': enum_name,
                        'values': {k: v for k, v in values},
                        'file': 'models.py'
                    })
            
            except Exception as e:
                print(f"[ERROR] Error scanning enums: {e}")
        
        return enums
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🎯 SPECIALIZED MODULES TRAINING - تدريب الوحدات الخاصة
    # ═══════════════════════════════════════════════════════════════════════
    
    def _train_specialized_modules(self) -> Dict[str, Any]:
        """تدريب شامل للوحدات الخاصة: Checks, Vendors, Partners, Products, Owner"""
        modules_data = {}
        
        try:
            from flask import has_app_context
            if not has_app_context():
                return {'error': 'No application context'}
                
            from extensions import db
            from sqlalchemy import inspect
            from models import Check, Supplier, Partner, Product, SystemSettings
            
            inspector = inspect(db.engine)
            
            # 1. Checks System
            try:
                check_columns = [col.name for col in Check.__table__.columns]
                check_statuses = ['PENDING', 'CASHED', 'RETURNED', 'BOUNCED', 'RESUBMITTED', 'CANCELLED', 'ARCHIVED', 'OVERDUE']
                modules_data['checks'] = {
                    'model': 'Check',
                    'columns': check_columns,
                    'statuses': check_statuses,
                    'routes_file': 'routes/checks.py',
                    'description': 'نظام إدارة الشيكات الكامل مع دورة حياة الشيك'
                }
            except Exception as e:
                modules_data['checks'] = {'error': str(e)}
            
            # 2. Vendors & Suppliers
            try:
                supplier_columns = [col.name for col in Supplier.__table__.columns]
                supplier_tables = [t for t in inspector.get_table_names() if 'supplier' in t.lower()]
                modules_data['vendors_suppliers'] = {
                    'model': 'Supplier',
                    'columns': supplier_columns,
                    'related_tables': supplier_tables,
                    'routes_file': 'routes/vendors.py',
                    'settlements_file': 'routes/supplier_settlements.py',
                    'description': 'نظام إدارة الموردين والتسويات'
                }
            except Exception as e:
                modules_data['vendors_suppliers'] = {'error': str(e)}
            
            # 3. Partners
            try:
                partner_columns = [col.name for col in Partner.__table__.columns]
                partner_tables = [t for t in inspector.get_table_names() if 'partner' in t.lower()]
                modules_data['partners'] = {
                    'model': 'Partner',
                    'columns': partner_columns,
                    'related_tables': partner_tables,
                    'routes_file': 'routes/partner_settlements.py',
                    'description': 'نظام إدارة الشركاء والحصص والتسويات'
                }
            except Exception as e:
                modules_data['partners'] = {'error': str(e)}
            
            # 4. Products
            try:
                product_columns = [col.name for col in Product.__table__.columns]
                product_tables = [t for t in inspector.get_table_names() if 'product' in t.lower()]
                modules_data['products'] = {
                    'model': 'Product',
                    'columns': product_columns,
                    'related_tables': product_tables,
                    'routes_file': 'routes/parts.py',
                    'description': 'نظام إدارة المنتجات الكامل مع الفئات والتقييمات'
                }
            except Exception as e:
                modules_data['products'] = {'error': str(e)}
            
            # 5. Owner Module
            try:
                owner_routes = []
                from app import app
                for rule in app.url_map.iter_rules():
                    if 'owner' in rule.endpoint.lower() or 'advanced' in rule.endpoint.lower():
                        owner_routes.append({
                            'path': rule.rule,
                            'endpoint': rule.endpoint
                        })
                
                owner_files = ['routes/advanced_control.py', 'routes/security_control.py', 'routes/security.py']
                modules_data['owner'] = {
                    'routes': owner_routes,
                    'files': owner_files,
                    'description': 'وحدة المالك - جميع الصلاحيات والتحكم المتقدم'
                }
            except Exception as e:
                modules_data['owner'] = {'error': str(e)}
            
            # 6. All Remaining Modules
            try:
                remaining_modules = [
                    'warehouses', 'branches', 'expenses', 'shipments', 'ledger',
                    'financial_reports', 'accounting_docs', 'accounting_validation',
                    'currencies', 'bank', 'notes', 'workflows', 'projects',
                    'assets', 'budgets', 'cost_centers', 'recurring_invoices',
                    'pricing', 'engineering', 'barcode', 'archive'
                ]
                
                modules_data['remaining_modules'] = {
                    'modules': remaining_modules,
                    'description': 'جميع الوحدات المتبقية في النظام'
                }
            except Exception as e:
                modules_data['remaining_modules'] = {'error': str(e)}
        
        except Exception as e:
            print(f"[ERROR] Error training specialized modules: {e}")
        
        return modules_data
    
    # ═══════════════════════════════════════════════════════════════════════
    # 💾 SAVE KNOWLEDGE - حفظ المعرفة
    # ═══════════════════════════════════════════════════════════════════════
    
    def _save_knowledge_base(self):
        """حفظ قاعدة المعرفة الكاملة"""
        try:
            os.makedirs('AI/data', exist_ok=True)
            
            knowledge_doc = {
                'version': '2.0',
                'created_at': datetime.now().isoformat(),
                'knowledge': self.knowledge,
                'summary': {
                    'tables': len(self.knowledge.get('database', {}).get('tables', {})),
                    'models': len(self.knowledge.get('models', {}).get('classes', [])),
                    'routes': len(self.knowledge.get('routes', {}).get('routes', [])),
                    'forms': len(self.knowledge.get('forms', {}).get('forms', [])),
                    'templates': len(self.knowledge.get('templates', {}).get('templates', [])),
                    'relationships': len(self.knowledge.get('relationships', [])),
                    'enums': len(self.knowledge.get('enums', []))
                }
            }
            
            with open(KNOWLEDGE_BASE_FILE, 'w', encoding='utf-8') as f:
                json.dump(knowledge_doc, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            print(f"[ERROR] Error saving knowledge base: {e}")
            raise
    
    def get_status(self) -> Dict[str, Any]:
        """الحصول على حالة التدريب"""
        self.load_status()
        return self.status
    
    def get_training_log(self, limit: int = 50) -> List[Dict]:
        """الحصول على سجل التدريب"""
        try:
            if os.path.exists(TRAINING_LOG_FILE):
                with open(TRAINING_LOG_FILE, 'r', encoding='utf-8') as f:
                    log = json.load(f)
                    return log[-limit:]
            return []
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 SINGLETON
# ═══════════════════════════════════════════════════════════════════════════

_training_engine = None

def get_training_engine() -> AITrainingEngine:
    """الحصول على محرك التدريب (Singleton)"""
    global _training_engine
    
    if _training_engine is None:
        _training_engine = AITrainingEngine()
    
    return _training_engine


__all__ = [
    'AITrainingEngine',
    'get_training_engine'
]

