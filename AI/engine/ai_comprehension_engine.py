from typing import Dict, List, Any, Optional
from datetime import datetime
import re


class ComprehensionEngine:
    
    def __init__(self):
        self.understanding_levels = {
            'surface': 0,
            'shallow': 1,
            'moderate': 2,
            'deep': 3,
            'expert': 4,
            'mastery': 5
        }
        
        self.comprehension_map = {}
        self.learning_paths = {}
    
    def understand_concept(self, concept: str, context: Dict = None) -> Dict[str, Any]:
        if context is None:
            context = {}
        
        understanding = {
            'concept': concept,
            'timestamp': datetime.now().isoformat(),
            'level': 'surface',
            'what': '',
            'why': '',
            'how': '',
            'when': '',
            'where': '',
            'examples': [],
            'counterexamples': [],
            'relationships': [],
            'implications': [],
            'mistakes_to_avoid': []
        }
        
        understanding['what'] = self._explain_what(concept, context)
        understanding['why'] = self._explain_why(concept, context)
        understanding['how'] = self._explain_how(concept, context)
        understanding['when'] = self._explain_when(concept, context)
        understanding['where'] = self._explain_where(concept, context)
        
        understanding['examples'] = self._generate_examples(concept, context)
        understanding['counterexamples'] = self._generate_counterexamples(concept, context)
        understanding['relationships'] = self._find_relationships(concept, context)
        understanding['implications'] = self._analyze_implications(concept, context)
        understanding['mistakes_to_avoid'] = self._identify_common_mistakes(concept, context)
        
        understanding['level'] = self._assess_understanding_level(understanding)
        
        self.comprehension_map[concept] = understanding
        
        return understanding
    
    def _explain_what(self, concept: str, context: Dict) -> str:
        concept_lower = concept.lower()
        
        definitions = {
            'عميل': 'شخص أو جهة تشتري منتجات أو خدمات من الشركة',
            'customer': 'شخص أو جهة تشتري منتجات أو خدمات من الشركة',
            'مورد': 'شخص أو شركة توفر المنتجات أو المواد الخام للشركة',
            'supplier': 'شخص أو شركة توفر المنتجات أو المواد الخام للشركة',
            'بيع': 'عملية تسليم منتج أو خدمة للعميل مقابل مبلغ مالي',
            'sale': 'عملية تسليم منتج أو خدمة للعميل مقابل مبلغ مالي',
            'قيد محاسبي': 'تسجيل عملية مالية في دفاتر الشركة يوضح الحسابات المدينة والدائنة',
            'gl entry': 'تسجيل عملية مالية في دفاتر الشركة يوضح الحسابات المدينة والدائنة',
            'رصيد': 'المبلغ المالي المستحق لشخص أو على شخص في لحظة معينة',
            'balance': 'المبلغ المالي المستحق لشخص أو على شخص في لحظة معينة',
            'vat': 'ضريبة القيمة المضافة - ضريبة تفرض على المبيعات والمشتريات',
            'مخزون': 'كمية المنتجات المتوفرة في المستودع',
            'stock': 'كمية المنتجات المتوفرة في المستودع'
        }
        
        return definitions.get(concept_lower, f'{concept} هو مفهوم يحتاج لمزيد من الدراسة')
    
    def _explain_why(self, concept: str, context: Dict) -> str:
        concept_lower = concept.lower()
        
        reasons = {
            'عميل': 'لأن الشركة تحتاج لمن يشتري منتجاتها لتحقيق الإيرادات والاستمرار',
            'customer': 'لأن الشركة تحتاج لمن يشتري منتجاتها لتحقيق الإيرادات والاستمرار',
            'قيد محاسبي': 'لتوثيق كل عملية مالية وضمان دقة السجلات المالية والامتثال القانوني',
            'gl entry': 'لتوثيق كل عملية مالية وضمان دقة السجلات المالية والامتثال القانوني',
            'vat': 'لتحصيل ضريبة لصالح الحكومة على كل معاملة تجارية',
            'مخزون': 'لمعرفة المنتجات المتاحة للبيع وتجنب نفاذها أو تكدسها'
        }
        
        return reasons.get(concept_lower, f'لأن {concept} جزء أساسي من العمليات التجارية')
    
    def _explain_how(self, concept: str, context: Dict) -> str:
        concept_lower = concept.lower()
        
        methods = {
            'عميل': 'يتم إضافته عبر صفحة /customers/create بإدخال الاسم والهاتف والبيانات الأساسية',
            'customer': 'يتم إضافته عبر صفحة /customers/create بإدخال الاسم والهاتف والبيانات الأساسية',
            'قيد محاسبي': 'ينشأ تلقائياً عند أي عملية (بيع، دفع، مشتريات) مع تحديد الحسابات المدينة والدائنة',
            'gl entry': 'ينشأ تلقائياً عند أي عملية (بيع، دفع، مشتريات) مع تحديد الحسابات المدينة والدائنة',
            'vat': 'يُحسب تلقائياً كنسبة مئوية من صافي المبلغ (16% فلسطين، 17% إسرائيل)',
            'رصيد': 'يُحسب بجمع كل العمليات: الرصيد = (الدفعات الواردة) - (المبيعات والفواتير)'
        }
        
        return methods.get(concept_lower, f'{concept} يعمل ضمن آليات النظام')
    
    def _explain_when(self, concept: str, context: Dict) -> str:
        concept_lower = concept.lower()
        
        timing = {
            'عميل': 'عند وجود عميل جديد يريد الشراء أو التعامل مع الشركة',
            'قيد محاسبي': 'فوراً عند حدوث أي عملية مالية (بيع، دفع، مشتريات، مصروف)',
            'vat': 'مع كل فاتورة بيع أو شراء تخضع للضريبة',
            'رصيد': 'يتحدث مع كل عملية جديدة (بيع، دفع، فاتورة)'
        }
        
        return timing.get(concept_lower, f'يُستخدم {concept} عند الحاجة إليه في سياق العمل')
    
    def _explain_where(self, concept: str, context: Dict) -> str:
        concept_lower = concept.lower()
        
        locations = {
            'عميل': 'في جدول customers في قاعدة البيانات، ويُعرض في /customers',
            'قيد محاسبي': 'في جداول gl_batches و gl_entries، ويُعرض في /gl_dashboard',
            'vat': 'في حقل vat_amount في جدول sales وفي القيود المحاسبية',
            'رصيد': 'في حقل balance في جدول customers/suppliers'
        }
        
        return locations.get(concept_lower, f'{concept} موجود في النظام')
    
    def _generate_examples(self, concept: str, context: Dict) -> List[str]:
        concept_lower = concept.lower()
        
        examples_map = {
            'عميل': [
                'عميل اسمه "أحمد" يشتري قطع غيار بقيمة 500 ₪',
                'عميل "محمد" له رصيد مدين 1000 ₪ (عليه يدفع)',
                'عميل "فاطمة" دفعت 200 ₪ من رصيدها'
            ],
            'قيد محاسبي': [
                'قيد بيع: مدين 1300 (ذمم) 1000 ₪، دائن 4000 (مبيعات) 862 ₪، دائن 2100 (VAT) 138 ₪',
                'قيد دفع: مدين 1100 (صندوق) 500 ₪، دائن 1300 (ذمم) 500 ₪',
                'قيد مشتريات: مدين 5100 (مشتريات) 1000 ₪، دائن 2300 (ذمم موردين) 1000 ₪'
            ],
            'رصيد': [
                'رصيد موجب +500 ₪ = العميل عليه (مدين)',
                'رصيد سالب -300 ₪ = العميل له (دائن - دفع زيادة)',
                'رصيد صفر 0 ₪ = الحساب متعادل'
            ]
        }
        
        return examples_map.get(concept_lower, [f'مثال على {concept}'])
    
    def _generate_counterexamples(self, concept: str, context: Dict) -> List[str]:
        concept_lower = concept.lower()
        
        counter_map = {
            'عميل': [
                'المورد ليس عميل - هو من نشتري منه',
                'الموظف ليس عميل - هو يعمل في الشركة'
            ],
            'قيد محاسبي': [
                'قيد غير متوازن (مدين ≠ دائن) - خطأ محاسبي',
                'قيد بدون حسابات - ليس قيد صحيح'
            ],
            'رصيد': [
                'الرصيد الموجب ليس معناه العميل له - بل عليه',
                'الرصيد السالب ليس ديناً - بل رصيد دائن للعميل'
            ]
        }
        
        return counter_map.get(concept_lower, [])
    
    def _find_relationships(self, concept: str, context: Dict) -> List[str]:
        concept_lower = concept.lower()
        
        relationships_map = {
            'عميل': [
                'له علاقة بـ: المبيعات، الدفعات، السيارات، الفواتير',
                'يؤثر على: حساب ذمم العملاء (1300)، الإيرادات',
                'يرتبط بـ: جدول customers، sales، payments، vehicles'
            ],
            'قيد محاسبي': [
                'يرتبط بـ: دليل الحسابات، الميزانية، قائمة الدخل',
                'يتأثر بـ: كل عملية مالية في النظام',
                'يؤثر على: أرصدة الحسابات، التقارير المالية'
            ],
            'vat': [
                'يرتبط بـ: المبيعات، المشتريات، الفواتير',
                'يؤثر على: حساب ضريبة القيمة المضافة (2100)',
                'يتأثر بـ: نسبة الضريبة (16% أو 17%)'
            ]
        }
        
        return relationships_map.get(concept_lower, [])
    
    def _analyze_implications(self, concept: str, context: Dict) -> List[str]:
        concept_lower = concept.lower()
        
        implications_map = {
            'عميل': [
                'إضافة عميل جديد = إمكانية مبيعات جديدة',
                'عميل برصيد كبير = خطر عدم التحصيل',
                'عميل نشط = إيرادات متكررة'
            ],
            'قيد محاسبي': [
                'قيد خاطئ = تقارير مالية خاطئة',
                'قيد غير متوازن = مشاكل في المراجعة',
                'قيود منتظمة = نظام محاسبي سليم'
            ],
            'رصيد': [
                'رصيد موجب كبير = ذمم مدينة عالية',
                'رصيد سالب = سيولة زائدة من العميل',
                'أرصدة متوازنة = صحة مالية'
            ]
        }
        
        return implications_map.get(concept_lower, [])
    
    def _identify_common_mistakes(self, concept: str, context: Dict) -> List[str]:
        concept_lower = concept.lower()
        
        mistakes_map = {
            'عميل': [
                'رقم هاتف مكرر - يسبب خطأ في النظام',
                'عدم إدخال البيانات كاملة - صعوبة التواصل',
                'الخلط بين العميل والمورد'
            ],
            'قيد محاسبي': [
                'عدم التوازن بين المدين والدائن',
                'اختيار حساب خاطئ',
                'نسيان VAT في القيد',
                'قيد مكرر'
            ],
            'رصيد': [
                'قراءة الرصيد بالعكس (موجب = له، خطأ!)',
                'عدم احتساب VAT',
                'نسيان دفعات سابقة'
            ]
        }
        
        return mistakes_map.get(concept_lower, [])
    
    def _assess_understanding_level(self, understanding: Dict) -> str:
        score = 0
        
        if understanding['what']:
            score += 1
        if understanding['why']:
            score += 1
        if understanding['how']:
            score += 1
        if len(understanding['examples']) >= 2:
            score += 1
        if len(understanding['relationships']) >= 2:
            score += 1
        if len(understanding['implications']) >= 2:
            score += 1
        
        level_map = {
            0: 'surface',
            1: 'surface',
            2: 'shallow',
            3: 'moderate',
            4: 'deep',
            5: 'expert',
            6: 'mastery'
        }
        
        return level_map.get(score, 'surface')
    
    def explain_fully(self, concept: str, context: Dict = None) -> str:
        understanding = self.understand_concept(concept, context)
        
        parts = []
        parts.append(f"📚 فهم عميق لـ: {concept}")
        parts.append(f"مستوى الفهم: {understanding['level'].upper()}\n")
        
        if understanding['what']:
            parts.append(f"❓ ما هو؟\n{understanding['what']}\n")
        
        if understanding['why']:
            parts.append(f"💡 لماذا؟\n{understanding['why']}\n")
        
        if understanding['how']:
            parts.append(f"⚙️ كيف؟\n{understanding['how']}\n")
        
        if understanding['when']:
            parts.append(f"⏰ متى؟\n{understanding['when']}\n")
        
        if understanding['where']:
            parts.append(f"📍 أين؟\n{understanding['where']}\n")
        
        if understanding['examples']:
            parts.append("✅ أمثلة:")
            for i, ex in enumerate(understanding['examples'], 1):
                parts.append(f"{i}. {ex}")
            parts.append("")
        
        if understanding['counterexamples']:
            parts.append("❌ ليس:")
            for ce in understanding['counterexamples']:
                parts.append(f"  - {ce}")
            parts.append("")
        
        if understanding['relationships']:
            parts.append("🔗 العلاقات:")
            for rel in understanding['relationships']:
                parts.append(f"  - {rel}")
            parts.append("")
        
        if understanding['implications']:
            parts.append("⚡ التأثيرات:")
            for imp in understanding['implications']:
                parts.append(f"  - {imp}")
            parts.append("")
        
        if understanding['mistakes_to_avoid']:
            parts.append("⚠️ أخطاء شائعة:")
            for mistake in understanding['mistakes_to_avoid']:
                parts.append(f"  - {mistake}")
        
        return '\n'.join(parts)


_comprehension_engine = None

def get_comprehension_engine():
    global _comprehension_engine
    if _comprehension_engine is None:
        _comprehension_engine = ComprehensionEngine()
    return _comprehension_engine


__all__ = ['ComprehensionEngine', 'get_comprehension_engine']

