"""
🐍 AI Python Expert - خبير Python احترافي
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- تصحيح الأخطاء البرمجية تلقائياً
- اقتراح حلول للأخطاء
- تحسين الكود
- كتابة كود Python احترافي
- Debugging متقدم

Created: 2025-11-01
Version: Python Expert 1.0 - MASTER LEVEL
"""

import ast
import re
import traceback
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════
# 🐍 PYTHON EXPERT ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class PythonExpert:
    """
    خبير Python عبقري
    
    القدرات:
    1. تحليل الأخطاء وتصحيحها
    2. اقتراح حلول متعددة
    3. تحسين الكود
    4. كتابة كود احترافي
    5. Refactoring
    6. Performance optimization
    """
    
    def __init__(self):
        self.common_errors = self._load_common_errors()
        self.best_practices = self._load_best_practices()
    
    def analyze_error(self, error_message: str, code_context: str = None) -> Dict[str, Any]:
        """
        تحليل خطأ Python وتقديم حلول
        
        Args:
            error_message: رسالة الخطأ
            code_context: السياق البرمجي (الكود حول الخطأ)
        
        Returns:
            تحليل كامل مع حلول
        """
        analysis = {
            'error_type': self._identify_error_type(error_message),
            'cause': '',
            'solutions': [],
            'code_fix': None,
            'explanation': '',
            'prevention_tips': []
        }
        
        # تحليل حسب نوع الخطأ
        error_type = analysis['error_type']
        
        if error_type == 'SyntaxError':
            return self._analyze_syntax_error(error_message, code_context)
        
        elif error_type == 'IndentationError':
            return self._analyze_indentation_error(error_message, code_context)
        
        elif error_type == 'NameError':
            return self._analyze_name_error(error_message, code_context)
        
        elif error_type == 'AttributeError':
            return self._analyze_attribute_error(error_message, code_context)
        
        elif error_type == 'TypeError':
            return self._analyze_type_error(error_message, code_context)
        
        elif error_type == 'ValueError':
            return self._analyze_value_error(error_message, code_context)
        
        elif error_type == 'KeyError':
            return self._analyze_key_error(error_message, code_context)
        
        elif error_type == 'IndexError':
            return self._analyze_index_error(error_message, code_context)
        
        elif error_type == 'ImportError' or error_type == 'ModuleNotFoundError':
            return self._analyze_import_error(error_message, code_context)
        
        else:
            return self._analyze_generic_error(error_message, code_context)
    
    def _identify_error_type(self, error_message: str) -> str:
        """تحديد نوع الخطأ"""
        error_types = [
            'SyntaxError', 'IndentationError', 'NameError', 'AttributeError',
            'TypeError', 'ValueError', 'KeyError', 'IndexError',
            'ImportError', 'ModuleNotFoundError', 'FileNotFoundError',
            'ZeroDivisionError', 'RuntimeError', 'MemoryError'
        ]
        
        for error_type in error_types:
            if error_type in error_message:
                return error_type
        
        return 'UnknownError'
    
    def _analyze_syntax_error(self, error_msg: str, context: str) -> Dict:
        """تحليل SyntaxError"""
        return {
            'error_type': 'SyntaxError',
            'cause': 'خطأ في بناء الجملة - الكود غير صالح من ناحية القواعد',
            'solutions': [
                'تحقق من الأقواس {} [] () - هل كلها مغلقة؟',
                'تحقق من علامات الاقتباس " \' - هل متطابقة؟',
                'تحقق من النقطتين : في نهاية if, for, def, class',
                'تحقق من الفواصل , بين العناصر',
                'تحقق من عدم استخدام كلمات محجوزة كأسماء متغيرات'
            ],
            'explanation': '''
SyntaxError يحدث عندما يكون الكود مخالفاً لقواعد Python.

الأسباب الشائعة:
1. قوس غير مغلق: print("hello"
2. نقص النقطتين: if x > 5
3. استخدام = بدل ==: if x = 5
4. مسافة خاطئة في الكلمات المحجوزة
            ''',
            'prevention_tips': [
                'استخدم IDE يعرض الأخطاء مباشرة',
                'اكتب الكود بتنسيق واضح',
                'استخدم linter مثل pylint أو flake8'
            ]
        }
    
    def _analyze_indentation_error(self, error_msg: str, context: str) -> Dict:
        """تحليل IndentationError"""
        return {
            'error_type': 'IndentationError',
            'cause': 'خطأ في المسافات البادئة (Indentation)',
            'solutions': [
                'استخدم 4 مسافات (spaces) لكل مستوى',
                'لا تخلط tabs و spaces',
                'تأكد من أن جميع الأسطر داخل block لها نفس المسافة',
                'استخدم محرر نصوص يعرض المسافات'
            ],
            'code_fix': '''
# ✅ صحيح:
def my_function():
    if True:
        print("Hello")  # 8 spaces (4 + 4)
    
# ❌ خطأ:
def my_function():
    if True:
      print("Hello")  # 6 spaces - غير متسق
            ''',
            'explanation': '''
Python يعتمد على المسافات البادئة لتحديد الـ blocks.

القاعدة:
- كل block داخلي يجب أن يكون بـ 4 spaces إضافية
- يجب الالتزام بنفس النمط في كل الملف
            ''',
            'prevention_tips': [
                'اضبط المحرر على استخدام 4 spaces للـ Tab',
                'فعّل "show whitespace" في المحرر',
                'استخدم auto-formatter مثل black'
            ]
        }
    
    def _analyze_name_error(self, error_msg: str, context: str) -> Dict:
        """تحليل NameError"""
        # استخراج اسم المتغير من الرسالة
        match = re.search(r"name '(\w+)' is not defined", error_msg)
        var_name = match.group(1) if match else 'unknown'
        
        return {
            'error_type': 'NameError',
            'cause': f"المتغير '{var_name}' غير معرّف",
            'solutions': [
                f"عرّف المتغير قبل استخدامه: {var_name} = ...",
                f"تحقق من الإملاء - هل كتبت {var_name} بشكل صحيح؟",
                f"تحقق من الـ scope - هل {var_name} معرّف في نفس النطاق؟",
                "إذا كان import - تأكد من استيراد الـ module"
            ],
            'code_fix': f'''
# ✅ الحل:
{var_name} = "some_value"  # عرّف المتغير أولاً
print({var_name})  # ثم استخدمه

# أو إذا كان function:
def {var_name}():
    pass
            ''',
            'explanation': f'''
NameError يحدث عندما تحاول استخدام متغير أو دالة غير موجودة.

الأسباب:
1. لم يتم تعريف {var_name} بعد
2. خطأ إملائي في الاسم
3. المتغير معرّف في scope مختلف
4. نسيت import الـ module
            ''',
            'prevention_tips': [
                'عرّف المتغيرات قبل استخدامها',
                'استخدم IDE يكتشف المتغيرات غير المعرّفة',
                'انتبه للـ scope (global vs local)'
            ]
        }
    
    def _analyze_attribute_error(self, error_msg: str, context: str) -> Dict:
        """تحليل AttributeError"""
        # استخراج الـ attribute
        match = re.search(r"has no attribute '(\w+)'", error_msg)
        attr_name = match.group(1) if match else 'unknown'
        
        return {
            'error_type': 'AttributeError',
            'cause': f"الكائن لا يملك خاصية '{attr_name}'",
            'solutions': [
                f"تحقق من أن الكائن من النوع الصحيح",
                f"استخدم dir(object) لرؤية الخصائص المتاحة",
                f"تحقق من الإملاء - هل '{attr_name}' مكتوب بشكل صحيح؟",
                "تحقق من أن الكائن ليس None",
                "تحقق من documentation الـ class"
            ],
            'code_fix': '''
# ✅ الحل 1: تحقق من النوع
if hasattr(obj, 'attribute_name'):
    obj.attribute_name
else:
    print("Attribute doesn't exist")

# ✅ الحل 2: استخدم getattr مع قيمة افتراضية
value = getattr(obj, 'attribute_name', default_value)

# ✅ الحل 3: تحقق من None
if obj is not None:
    obj.attribute_name
            ''',
            'explanation': '''
AttributeError يحدث عندما تحاول الوصول لخاصية غير موجودة.

الأسباب الشائعة:
1. الكائن من نوع مختلف عن المتوقع
2. الكائن = None
3. خطأ إملائي في اسم الخاصية
4. الخاصية private أو لا تنتمي للـ class
            ''',
            'prevention_tips': [
                'استخدم isinstance() للتحقق من النوع',
                'استخدم hasattr() قبل الوصول للخاصية',
                'استخدم Type Hints في Python 3.6+'
            ]
        }
    
    def _analyze_type_error(self, error_msg: str, context: str) -> Dict:
        """تحليل TypeError"""
        return {
            'error_type': 'TypeError',
            'cause': 'عملية على أنواع بيانات غير متوافقة',
            'solutions': [
                'تحقق من أنواع البيانات المستخدمة',
                'حوّل النوع إذا لزم: int(), str(), float(), list()',
                'تحقق من عدد المعاملات (arguments) للدالة',
                'تحقق من أن الكائن قابل للعملية المطلوبة'
            ],
            'code_fix': '''
# ❌ خطأ:
result = "5" + 3  # لا يمكن جمع str مع int

# ✅ الحل:
result = int("5") + 3  # تحويل str لـ int
# أو:
result = "5" + str(3)  # تحويل int لـ str

# مثال آخر:
# ❌ خطأ:
my_list = [1, 2, 3]
my_list[1.5]  # index يجب أن يكون int

# ✅ الحل:
my_list[int(1.5)]  # أو my_list[1]
            ''',
            'explanation': '''
TypeError يحدث عند استخدام نوع بيانات في عملية غير مناسبة.

الأسباب:
1. عمليات حسابية على أنواع مختلفة
2. عدد خاطئ من arguments
3. استخدام نوع غير مناسب (مثل str كـ index)
4. عملية غير مدعومة على هذا النوع
            ''',
            'prevention_tips': [
                'استخدم Type Hints',
                'تحقق من الأنواع: isinstance(x, int)',
                'استخدم type() لمعرفة نوع المتغير'
            ]
        }
    
    def _analyze_value_error(self, error_msg: str, context: str) -> Dict:
        """تحليل ValueError"""
        return {
            'error_type': 'ValueError',
            'cause': 'قيمة غير صالحة للعملية المطلوبة',
            'solutions': [
                'تحقق من صحة القيمة قبل العملية',
                'استخدم try-except للتعامل مع القيم الخاطئة',
                'استخدم validation للـ input',
                'تحقق من المدى المقبول للقيمة'
            ],
            'code_fix': '''
# ❌ خطأ:
number = int("abc")  # "abc" ليست رقم

# ✅ الحل:
try:
    number = int("abc")
except ValueError:
    print("القيمة ليست رقماً صالحاً")
    number = 0  # قيمة افتراضية

# أو استخدم validation:
value = input("أدخل رقم: ")
if value.isdigit():
    number = int(value)
else:
    print("يجب إدخال رقم")
            ''',
            'explanation': '''
ValueError يحدث عند تمرير قيمة غير صالحة لدالة.

أمثلة:
1. int("abc") - تحويل نص غير رقمي
2. math.sqrt(-1) - جذر تربيعي لعدد سالب
3. datetime.strptime("abc", "%Y-%m-%d") - تنسيق خاطئ
            ''',
            'prevention_tips': [
                'استخدم try-except عند التحويلات',
                'تحقق من صحة البيانات (validation)',
                'استخدم مكتبات validation مثل pydantic'
            ]
        }
    
    def _analyze_key_error(self, error_msg: str, context: str) -> Dict:
        """تحليل KeyError"""
        # استخراج المفتاح
        match = re.search(r"KeyError: ['\"](\w+)['\"]", error_msg)
        key = match.group(1) if match else 'unknown'
        
        return {
            'error_type': 'KeyError',
            'cause': f"المفتاح '{key}' غير موجود في القاموس",
            'solutions': [
                f"تحقق من وجود المفتاح قبل الوصول إليه",
                f"استخدم .get() بدلاً من []",
                f"أضف المفتاح '{key}' للقاموس أولاً",
                "تحقق من الإملاء الصحيح للمفتاح"
            ],
            'code_fix': f'''
# ❌ خطأ:
value = my_dict['{key}']  # إذا لم يكن موجود = KeyError

# ✅ الحل 1: استخدم get()
value = my_dict.get('{key}')  # يعيد None إذا لم يكن موجود
# أو مع قيمة افتراضية:
value = my_dict.get('{key}', 'default_value')

# ✅ الحل 2: تحقق من الوجود
if '{key}' in my_dict:
    value = my_dict['{key}']
else:
    value = 'default'

# ✅ الحل 3: استخدم try-except
try:
    value = my_dict['{key}']
except KeyError:
    value = 'default'
            ''',
            'explanation': f'''
KeyError يحدث عند محاولة الوصول لمفتاح غير موجود في dictionary.

الأسباب:
1. المفتاح '{key}' غير موجود في القاموس
2. خطأ إملائي في اسم المفتاح
3. القاموس فارغ
4. المفتاح تم حذفه
            ''',
            'prevention_tips': [
                'استخدم .get() بدلاً من []',
                'تحقق من وجود المفتاح: if key in dict',
                'استخدم defaultdict من collections'
            ]
        }
    
    def _analyze_index_error(self, error_msg: str, context: str) -> Dict:
        """تحليل IndexError"""
        return {
            'error_type': 'IndexError',
            'cause': 'محاولة الوصول لـ index خارج نطاق القائمة',
            'solutions': [
                'تحقق من طول القائمة قبل الوصول',
                'استخدم try-except',
                'تأكد من أن القائمة ليست فارغة',
                'استخدم enumerate() للتكرار الآمن'
            ],
            'code_fix': '''
# ❌ خطأ:
my_list = [1, 2, 3]
value = my_list[10]  # Index 10 غير موجود (الحد الأقصى 2)

# ✅ الحل 1: تحقق من الطول
if len(my_list) > index:
    value = my_list[index]
else:
    value = None

# ✅ الحل 2: استخدم try-except
try:
    value = my_list[index]
except IndexError:
    value = None

# ✅ الحل 3: تحقق من الفراغ
if my_list:  # إذا لم تكن فارغة
    value = my_list[0]

# ✅ الحل 4: استخدم enumerate
for i, item in enumerate(my_list):
    print(f"Index {i}: {item}")
            ''',
            'explanation': '''
IndexError يحدث عند محاولة الوصول لـ index غير موجود.

الأسباب:
1. Index أكبر من طول القائمة
2. Index سالب خارج النطاق
3. القائمة فارغة
4. خطأ في الحساب (off-by-one error)
            ''',
            'prevention_tips': [
                'تحقق من len() قبل الوصول',
                'استخدم slicing الآمن: my_list[:10]',
                'استخدم enumerate() بدلاً من range(len())'
            ]
        }
    
    def _analyze_import_error(self, error_msg: str, context: str) -> Dict:
        """تحليل ImportError"""
        # استخراج اسم الـ module
        match = re.search(r"No module named ['\"](\w+)['\"]", error_msg)
        module = match.group(1) if match else 'unknown'
        
        return {
            'error_type': 'ImportError/ModuleNotFoundError',
            'cause': f"المكتبة '{module}' غير مثبتة أو غير موجودة",
            'solutions': [
                f"ثبت المكتبة: pip install {module}",
                f"تحقق من الإملاء الصحيح لـ '{module}'",
                "تحقق من أنك في البيئة الافتراضية الصحيحة (venv)",
                "تحقق من أن الملف موجود في نفس المجلد",
                "أضف المسار لـ sys.path إذا كان ملف محلي"
            ],
            'code_fix': f'''
# الحل 1: ثبت المكتبة
# في Terminal:
# pip install {module}

# الحل 2: إذا كان ملف محلي
import sys
sys.path.append('/path/to/module')
import {module}

# الحل 3: استخدم relative import
from . import {module}  # إذا كان في نفس الـ package

# الحل 4: استخدم try-except للتوافق
try:
    import {module}
except ImportError:
    print("{module} is not installed")
    # استخدم بديل أو اطلب التثبيت
            ''',
            'explanation': f'''
ImportError يحدث عند عدم القدرة على استيراد module.

الأسباب:
1. المكتبة '{module}' غير مثبتة
2. خطأ في اسم الـ module
3. البيئة الافتراضية خاطئة
4. مشكلة في PYTHONPATH
5. الملف غير موجود
            ''',
            'prevention_tips': [
                'استخدم requirements.txt لتوثيق المكتبات',
                'استخدم virtual environment',
                'تحقق من تثبيت المكتبات: pip list'
            ]
        }
    
    def _analyze_generic_error(self, error_msg: str, context: str) -> Dict:
        """تحليل عام لأي خطأ"""
        return {
            'error_type': 'Error',
            'cause': 'خطأ في التنفيذ',
            'solutions': [
                'راجع رسالة الخطأ بعناية',
                'ابحث عن رسالة الخطأ في Google',
                'تحقق من الـ stack trace لمعرفة مكان الخطأ',
                'استخدم debugger للتتبع',
                'أضف print() لفهم سير البرنامج'
            ],
            'explanation': f'''
الخطأ: {error_msg}

راجع:
1. الـ stack trace لمعرفة مكان الخطأ بالضبط
2. رسالة الخطأ للفهم
3. الكود المحيط بمكان الخطأ
            ''',
            'prevention_tips': [
                'استخدم try-except للأخطاء المتوقعة',
                'استخدم logging للتتبع',
                'اكتب tests للكود'
            ]
        }
    
    def suggest_code_improvement(self, code: str) -> Dict[str, Any]:
        """اقتراح تحسينات على الكود"""
        suggestions = {
            'performance': [],
            'readability': [],
            'best_practices': [],
            'security': []
        }
        
        # فحص الأداء
        if 'for' in code and 'append' in code:
            suggestions['performance'].append(
                "استخدم list comprehension بدلاً من for-append"
            )
        
        # فحص القراءة
        if len(code.split('\n')) > 50:
            suggestions['readability'].append(
                "الدالة طويلة جداً - فكر في تقسيمها لدوال أصغر"
            )
        
        # فحص best practices
        if 'except:' in code and 'Exception' not in code:
            suggestions['best_practices'].append(
                "تجنب bare except - حدد نوع Exception"
            )
        
        return suggestions
    
    def _load_common_errors(self) -> Dict:
        """تحميل الأخطاء الشائعة"""
        return {}
    
    def _load_best_practices(self) -> List:
        """تحميل أفضل الممارسات"""
        return [
            "استخدم Type Hints في Python 3.6+",
            "اكتب docstrings لكل function",
            "استخدم meaningful names للمتغيرات",
            "اتبع PEP 8 style guide",
            "استخدم virtual environments",
            "اكتب unit tests",
            "استخدم logging بدلاً من print",
            "تجنب global variables",
            "استخدم context managers (with)",
            "استخدم list/dict comprehensions عندما مناسب"
        ]


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 SINGLETON
# ═══════════════════════════════════════════════════════════════════════════

_python_expert = None

def get_python_expert() -> PythonExpert:
    """الحصول على خبير Python (Singleton)"""
    global _python_expert
    
    if _python_expert is None:
        _python_expert = PythonExpert()
    
    return _python_expert


__all__ = [
    'PythonExpert',
    'get_python_expert'
]

