"""
AI Knowledge Base - قاعدة المعرفة الشاملة للنظام
فهرسة وتحليل كل ملفات النظام لبناء ذاكرة معرفية مستمرة
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime


KNOWLEDGE_CACHE_FILE = 'instance/ai_knowledge_cache.json'
TRAINING_LOG_FILE = 'instance/ai_training_log.json'


class SystemKnowledgeBase:
    """قاعدة المعرفة - فهم عميق لبنية النظام مع Persistent Memory"""
    
    def __init__(self):
        self.base_path = Path('.')
        self.knowledge = {
            'models': {},
            'routes': {},
            'templates': {},
            'forms': {},
            'relationships': {},
            'business_rules': [],
            'common_errors': [],
            'last_indexed': None,
            'index_count': 0
        }
        self.load_from_cache()
    
    def load_from_cache(self):
        """تحميل المعرفة من الذاكرة المستمرة"""
        try:
            if os.path.exists(KNOWLEDGE_CACHE_FILE):
                with open(KNOWLEDGE_CACHE_FILE, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    self.knowledge.update(cached)
                    print(f"✅ تم تحميل المعرفة من الذاكرة (آخر فهرسة: {self.knowledge.get('last_indexed', 'N/A')})")
        except Exception as e:
            print(f"⚠️ تعذر تحميل الذاكرة: {str(e)}")
    
    def save_to_cache(self):
        """حفظ المعرفة في الذاكرة المستمرة"""
        try:
            os.makedirs('instance', exist_ok=True)
            self.knowledge['last_indexed'] = datetime.now().isoformat()
            self.knowledge['index_count'] = self.knowledge.get('index_count', 0) + 1
            
            with open(KNOWLEDGE_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.knowledge, f, ensure_ascii=False, indent=2)
            
            print(f"✅ تم حفظ المعرفة في الذاكرة (فهرسة #{self.knowledge['index_count']})")
        except Exception as e:
            print(f"⚠️ تعذر حفظ الذاكرة: {str(e)}")
    
    def index_all_files(self, force_reindex=False):
        """فهرسة كل ملفات النظام مع حفظ مستمر"""
        if not force_reindex and self.knowledge.get('last_indexed'):
            print(f"ℹ️  المعرفة محملة من الذاكرة (آخر فهرسة: {self.knowledge.get('last_indexed')})")
            print(f"   استخدم force_reindex=True لإعادة الفهرسة")
            return self.knowledge
        
        print("🔍 بدء فهرسة شاملة للنظام...")
        
        self.index_models()
        self.index_routes()
        self.index_templates()
        self.analyze_relationships()
        self.extract_business_rules()
        self.extract_currency_rules()
        
        self.save_to_cache()
        
        print(f"✅ تم فهرسة: {len(self.knowledge['models'])} موديل، {len(self.knowledge['routes'])} route")
        return self.knowledge
    
    def extract_currency_rules(self):
        """استخراج قواعد العملات وسعر الصرف"""
        currency_rules = [
            {
                'rule': 'العملات المدعومة: ILS, USD, JOD, EUR',
                'source': 'models.py - CURRENCY_CHOICES',
                'impact': 'high'
            },
            {
                'rule': 'سعر الصرف يُحفظ مع كل عملية (fx_rate_used)',
                'source': 'models.py - Payment, Invoice',
                'impact': 'high'
            },
            {
                'rule': 'التحويل التلقائي بين العملات عند الدفع',
                'source': 'routes/payments.py',
                'impact': 'medium'
            },
            {
                'rule': 'سعر الصرف من 3 مصادر: online, manual, default',
                'source': 'models.py - fx_rate_source',
                'impact': 'medium'
            }
        ]
        
        self.knowledge['business_rules'].extend(currency_rules)
        print(f"   💱 Currency Rules: {len(currency_rules)}")
    
    def index_models(self):
        """فهرسة Models - فهم الجداول"""
        try:
            models_file = self.base_path / 'models.py'
            if not models_file.exists():
                return
            
            content = models_file.read_text(encoding='utf-8')
            
            class_pattern = r'class\s+(\w+)\(.*?(?:db\.Model|Base)\):'
            classes = re.findall(class_pattern, content)
            
            for class_name in classes:
                class_match = re.search(
                    rf'class\s+{class_name}\(.*?\):(.*?)(?=\nclass\s|\Z)',
                    content,
                    re.DOTALL
                )
                
                if class_match:
                    class_body = class_match.group(1)
                    
                    columns = re.findall(r'(\w+)\s*=\s*db\.Column\((.*?)\)', class_body)
                    relationships = re.findall(r'(\w+)\s*=\s*db\.relationship\((.*?)\)', class_body)
                    
                    self.knowledge['models'][class_name] = {
                        'columns': [col[0] for col in columns],
                        'relationships': [rel[0] for rel in relationships],
                        'file': 'models.py',
                        'full_definition': class_body[:500]
                    }
            
            print(f"   📊 Models: {len(self.knowledge['models'])}")
            
        except Exception as e:
            print(f"⚠️  خطأ في فهرسة Models: {str(e)}")
    
    def index_routes(self):
        """فهرسة Routes - فهم المسارات"""
        try:
            routes_dir = self.base_path / 'routes'
            if not routes_dir.exists():
                return
            
            for route_file in routes_dir.glob('*.py'):
                if route_file.name.startswith('__'):
                    continue
                
                content = route_file.read_text(encoding='utf-8')
                
                route_pattern = r'@\w+_bp\.route\([\'"](.+?)[\'"]\s*,?\s*methods=\[(.+?)\]\)'
                routes = re.findall(route_pattern, content)
                
                blueprint_name = route_file.stem
                
                if routes:
                    self.knowledge['routes'][blueprint_name] = {
                        'file': str(route_file),
                        'routes': [(r[0], r[1]) for r in routes]
                    }
            
            print(f"   🔗 Routes: {len(self.knowledge['routes'])} ملف")
            
        except Exception as e:
            print(f"⚠️  خطأ في فهرسة Routes: {str(e)}")
    
    def index_templates(self):
        """فهرسة Templates - فهم الواجهات"""
        try:
            templates_dir = self.base_path / 'templates'
            if not templates_dir.exists():
                return
            
            template_count = 0
            for template_file in templates_dir.rglob('*.html'):
                module_name = template_file.parent.name
                if module_name not in self.knowledge['templates']:
                    self.knowledge['templates'][module_name] = []
                
                self.knowledge['templates'][module_name].append(template_file.name)
                template_count += 1
            
            print(f"   📄 Templates: {template_count} ملف")
            
        except Exception as e:
            print(f"⚠️  خطأ في فهرسة Templates: {str(e)}")
    
    def analyze_relationships(self):
        """تحليل العلاقات بين الجداول"""
        for model_name, model_data in self.knowledge['models'].items():
            relationships = model_data.get('relationships', [])
            
            for rel in relationships:
                rel_key = f"{model_name} → {rel}"
                self.knowledge['relationships'][rel_key] = {
                    'from': model_name,
                    'to': rel,
                    'type': 'one-to-many'  # يمكن تحسينها
                }
        
        print(f"   🔗 Relationships: {len(self.knowledge['relationships'])}")
    
    def extract_business_rules(self):
        """استخراج القواعد التشغيلية من الكود"""
        business_rules = [
            {
                'rule': 'كل كراج له قاعدة بيانات مستقلة',
                'source': 'app.py - multi-tenant architecture',
                'impact': 'high'
            },
            {
                'rule': 'لا يمكن حذف دفعة مربوطة بفاتورة',
                'source': 'routes/payments.py',
                'impact': 'high'
            },
            {
                'rule': 'الشريك يتسلم أرباحه بعد التسوية فقط',
                'source': 'models.py - PartnerSettlement',
                'impact': 'medium'
            },
            {
                'rule': 'Super Admin (ID=1) يتجاوز وضع الصيانة',
                'source': 'app.py - check_maintenance_mode',
                'impact': 'high'
            },
            {
                'rule': 'المخازن بأنواع: Online, Partner, Inventory, Exchange, Main',
                'source': 'models.py - Warehouse',
                'impact': 'medium'
            }
        ]
        
        self.knowledge['business_rules'] = business_rules
        print(f"   📜 Business Rules: {len(business_rules)}")
    
    def find_model_by_name(self, name):
        """البحث عن موديل بالاسم"""
        name_lower = name.lower()
        for model_name, model_data in self.knowledge['models'].items():
            if name_lower in model_name.lower():
                return {model_name: model_data}
        return None
    
    def find_related_models(self, model_name):
        """إيجاد الموديلات المرتبطة"""
        related = []
        for rel_key, rel_data in self.knowledge['relationships'].items():
            if rel_data['from'] == model_name:
                related.append(rel_data['to'])
            elif rel_data['to'] == model_name:
                related.append(rel_data['from'])
        return related
    
    def get_system_structure(self):
        """الحصول على هيكل النظام الكامل"""
        return {
            'models_count': len(self.knowledge['models']),
            'models': list(self.knowledge['models'].keys()),
            'routes_count': sum(len(r['routes']) for r in self.knowledge['routes'].values()),
            'templates_count': sum(len(t) for t in self.knowledge['templates'].values()),
            'relationships_count': len(self.knowledge['relationships']),
            'business_rules_count': len(self.knowledge['business_rules'])
        }
    
    def explain_model(self, model_name):
        """شرح موديل بالتفصيل"""
        if model_name not in self.knowledge['models']:
            return None
        
        model = self.knowledge['models'][model_name]
        related = self.find_related_models(model_name)
        
        explanation = f"""
📊 موديل: {model_name}
═════════════════════════════

📁 الملف: {model['file']}

📋 الأعمدة ({len(model['columns'])}):
{chr(10).join(f'  • {col}' for col in model['columns'][:10])}

🔗 العلاقات ({len(model['relationships'])}):
{chr(10).join(f'  → {rel}' for rel in model['relationships'])}

🤝 مرتبط بـ:
{chr(10).join(f'  ↔ {r}' for r in related)}
"""
        return explanation


class ErrorAnalyzer:
    """محلل الأخطاء - فهم وتفسير الأخطاء"""
    
    @staticmethod
    def analyze_traceback(traceback_text):
        """تحليل Traceback وتقديم حل"""
        analysis = {
            'error_type': 'Unknown',
            'file': 'Unknown',
            'line': 0,
            'cause': 'Unknown',
            'solution': 'Unknown',
            'severity': 'medium'
        }
        
        error_patterns = {
            'UndefinedError': {
                'cause': 'دالة أو متغير غير معرف في Template',
                'solution': 'تأكد من تسجيل الدالة كـ @app.template_global() أو تمريرها في render_template',
                'severity': 'high'
            },
            'NameError': {
                'cause': 'دالة أو متغير غير معرف في Python',
                'solution': 'تأكد من استيراد الدالة أو تعريفها قبل الاستخدام',
                'severity': 'high'
            },
            'AttributeError': {
                'cause': 'محاولة الوصول لخاصية غير موجودة',
                'solution': 'تأكد من وجود الخاصية أو استخدم getattr() مع قيمة افتراضية',
                'severity': 'medium'
            },
            'IntegrityError': {
                'cause': 'خرق قيد في قاعدة البيانات (Unique, Foreign Key)',
                'solution': 'تأكد من صحة البيانات قبل الحفظ، أو التعامل مع الخطأ',
                'severity': 'high'
            }
        }
        
        for error_name, error_info in error_patterns.items():
            if error_name in traceback_text:
                analysis['error_type'] = error_name
                analysis['cause'] = error_info['cause']
                analysis['solution'] = error_info['solution']
                analysis['severity'] = error_info['severity']
                break
        
        file_match = re.search(r'File "(.+?)", line (\d+)', traceback_text)
        if file_match:
            analysis['file'] = file_match.group(1)
            analysis['line'] = int(file_match.group(2))
        
        return analysis
    
    @staticmethod
    def format_error_response(analysis):
        """تنسيق رد الخطأ بشكل واضح"""
        severity_emoji = {
            'high': '🔴',
            'medium': '🟡',
            'low': '🟢'
        }
        
        return f"""
{severity_emoji.get(analysis['severity'], '⚠️')} **خطأ: {analysis['error_type']}**

📁 الملف: `{analysis['file']}`
📍 السطر: `{analysis['line']}`

💡 السبب:
{analysis['cause']}

🔧 الحل:
{analysis['solution']}
"""


_knowledge_base = None
_error_analyzer = ErrorAnalyzer()


def get_knowledge_base():
    """الحصول على قاعدة المعرفة (Singleton)"""
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = SystemKnowledgeBase()
        _knowledge_base.index_all_files()
    return _knowledge_base


def analyze_error(traceback_text):
    """تحليل خطأ"""
    return _error_analyzer.analyze_traceback(traceback_text)


def format_error_response(analysis):
    """تنسيق رد الخطأ"""
    return _error_analyzer.format_error_response(analysis)

