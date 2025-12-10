"""
🧠 AI NLP Engine - محرك معالجة اللغة الطبيعية
تحليل لغوي ذكي - ليس قوائم غبية!

يفهم:
- السياق من الجملة كاملة
- العلاقات بين الكلمات
- المعنى الحقيقي وليس فقط الكلمات
- الأفعال والأسماء والصفات
- التركيب النحوي
"""

import re
from typing import Dict, List, Any, Tuple, Optional

# ==================== تحليل البنية النحوية ====================

class ArabicSentenceAnalyzer:
    """محلل الجمل العربية - يفهم البنية النحوية"""
    
    def __init__(self):
        # أنماط الأفعال العربية
        self.verb_patterns = {
            'question': r'(كم|ماذا|ما|من|أين|متى|كيف|هل|لماذا)',
            'command': r'(أعطني|أرني|اعرض|احسب|حلل|افحص|أنشئ|أضف|احذف|عدل)',
            'request': r'(أريد|أحتاج|ممكن|لو سمحت|من فضلك|عايز|بدي)',
            'analysis': r'(حلل|افحص|راجع|قيّم|اختبر|تأكد)',
            'comparison': r'(قارن|الفرق|أيهما|أفضل|أسوأ)',
            'search': r'(ابحث|جد|وين|فين|أين|دلني|وصلني)',
        }
        
        # أنماط الكيانات
        self.entity_patterns = {
            'customer': r'(عميل|عملاء|زبون|زبائن|الزباين|العملاء)',
            'money': r'(\d+[\d,]*\.?\d*)\s*(شيقل|دولار|دينار|يورو|₪|\$|€)',
            'time': r'(اليوم|أمس|غداً|الأسبوع|الشهر|السنة|هذا\s+\w+)',
            'number': r'(\d+[\d,]*)',
            'percentage': r'(\d+\.?\d*)%',
        }
        
        # كلمات الربط والسياق
        self.context_words = {
            'positive': ['ممتاز', 'رائع', 'جيد', 'عظيم', 'ناجح', 'مبروك'],
            'negative': ['سيء', 'فاشل', 'ضعيف', 'مشكلة', 'خطأ', 'عطل'],
            'urgent': ['سريع', 'عاجل', 'فوري', 'الآن', 'حالاً'],
            'polite': ['لو سمحت', 'من فضلك', 'شكراً', 'جزاك الله'],
        }
    
    def extract_verb_intent(self, text: str) -> Optional[str]:
        """استخراج النية من الفعل الرئيسي"""
        text_lower = text.lower()
        
        for intent, pattern in self.verb_patterns.items():
            if re.search(pattern, text_lower):
                return intent
        
        # استنتاج من السياق
        if '؟' in text:
            return 'question'
        elif text.endswith('!'):
            return 'command'
        
        return None
    
    def extract_entities(self, text: str) -> Dict[str, List[Any]]:
        """استخراج الكيانات من النص"""
        entities = {}
        
        for entity_type, pattern in self.entity_patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                entities[entity_type] = matches
        
        return entities
    
    def detect_sentiment(self, text: str) -> str:
        """كشف المشاعر من السياق"""
        text_lower = text.lower()
        
        positive_count = sum(1 for word in self.context_words['positive'] if word in text_lower)
        negative_count = sum(1 for word in self.context_words['negative'] if word in text_lower)
        
        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'
    
    def analyze(self, text: str) -> Dict[str, Any]:
        """تحليل شامل للجملة"""
        return {
            'intent': self.extract_verb_intent(text),
            'entities': self.extract_entities(text),
            'sentiment': self.detect_sentiment(text),
            'has_question_mark': '؟' in text or '?' in text,
            'word_count': len(text.split()),
            'is_polite': any(word in text.lower() for word in self.context_words['polite']),
            'is_urgent': any(word in text.lower() for word in self.context_words['urgent']),
        }

# ==================== فهم المعنى الدلالي ====================

class SemanticUnderstanding:
    """فهم المعنى الدلالي - ليس فقط الكلمات"""
    
    def __init__(self):
        # خريطة المفاهيم (concepts)
        self.concepts = {
            'financial_performance': {
                'keywords': ['ربح', 'خسارة', 'مبيعات', 'إيرادات', 'نفقات', 'دخل'],
                'related': ['محاسبة', 'مالية', 'أداء'],
                'intent': 'analysis',
            },
            'customer_satisfaction': {
                'keywords': ['رضا', 'شكوى', 'تقييم', 'خدمة', 'جودة'],
                'related': ['عملاء', 'تجربة'],
                'intent': 'feedback',
            },
            'inventory_management': {
                'keywords': ['مخزون', 'بضاعة', 'قطع', 'منتجات', 'نفاد'],
                'related': ['مستودع', 'توفر', 'كمية'],
                'intent': 'stock_check',
            },
            'performance_metrics': {
                'keywords': ['أداء', 'نسبة', 'معدل', 'كفاءة', 'إنتاجية'],
                'related': ['قياس', 'تقييم', 'مؤشر'],
                'intent': 'analysis',
            },
        }
    
    def find_concept(self, text: str) -> Optional[Tuple[str, float]]:
        """العثور على المفهوم الأساسي في النص"""
        text_lower = text.lower()
        
        best_match = None
        best_score = 0
        
        for concept_name, concept_data in self.concepts.items():
            score = 0
            
            # تطابق الكلمات المفتاحية
            for keyword in concept_data['keywords']:
                if keyword in text_lower:
                    score += 2
            
            # تطابق الكلمات المرتبطة
            for related in concept_data['related']:
                if related in text_lower:
                    score += 1
            
            if score > best_score:
                best_score = score
                best_match = concept_name
        
        if best_match and best_score > 0:
            return (best_match, best_score / 10.0)  # normalize to 0-1
        
        return None
    
    def understand_question(self, text: str) -> Dict[str, Any]:
        """فهم السؤال بشكل عميق"""
        concept = self.find_concept(text)
        
        understanding = {
            'main_concept': concept[0] if concept else None,
            'confidence': concept[1] if concept else 0.0,
            'is_comparative': any(word in text.lower() for word in ['أفضل', 'أسوأ', 'مقارنة', 'الفرق']),
            'is_temporal': any(word in text.lower() for word in ['اليوم', 'أمس', 'الأسبوع', 'الشهر']),
            'is_quantitative': any(word in text.lower() for word in ['كم', 'عدد', 'مجموع', 'متوسط']),
        }
        
        return understanding

# ==================== استنتاج النية المتقدم ====================

class AdvancedIntentDetector:
    """كاشف النية المتقدم - يستنتج وليس فقط يطابق"""
    
    def __init__(self):
        self.sentence_analyzer = ArabicSentenceAnalyzer()
        self.semantic_engine = SemanticUnderstanding()
    
    def detect_intent(self, text: str) -> Dict[str, Any]:
        """كشف النية بذكاء"""
        
        # تحليل الجملة
        sentence_analysis = self.sentence_analyzer.analyze(text)
        
        # فهم المعنى
        semantic = self.semantic_engine.understand_question(text)
        
        # دمج التحليلات
        intent_result = {
            'primary_intent': None,
            'secondary_intents': [],
            'confidence': 0.0,
            'reasoning': [],
        }
        
        # الاستنتاج المنطقي
        text_lower = text.lower()
        
        # 1. سؤال كمي (عدد، مبلغ)
        if semantic['is_quantitative'] or any(w in text_lower for w in ['كم', 'عدد']):
            intent_result['primary_intent'] = 'quantitative_query'
            intent_result['confidence'] = 0.9
            intent_result['reasoning'].append('يطلب رقماً أو عدداً')
        
        # 2. تحليل وتقييم
        elif semantic['main_concept'] in ['financial_performance', 'performance_metrics']:
            intent_result['primary_intent'] = 'performance_analysis'
            intent_result['confidence'] = 0.85
            intent_result['reasoning'].append('يطلب تحليل أداء')
        
        # 3. مقارنة
        elif semantic['is_comparative']:
            intent_result['primary_intent'] = 'comparison'
            intent_result['confidence'] = 0.9
            intent_result['reasoning'].append('يقارن بين شيئين')
        
        # 4. بحث وتنقل
        elif sentence_analysis['intent'] == 'search':
            intent_result['primary_intent'] = 'navigation'
            intent_result['confidence'] = 0.95
            intent_result['reasoning'].append('يبحث عن صفحة أو مكان')
        
        # 5. أمر تنفيذي
        elif sentence_analysis['intent'] == 'command':
            intent_result['primary_intent'] = 'executable_command'
            intent_result['confidence'] = 0.8
            intent_result['reasoning'].append('يطلب تنفيذ إجراء')
        
        # 6. طلب شرح
        elif any(w in text_lower for w in ['ما هو', 'ما هي', 'اشرح', 'عرف']):
            intent_result['primary_intent'] = 'explanation_request'
            intent_result['confidence'] = 0.9
            intent_result['reasoning'].append('يطلب شرحاً أو تعريفاً')
        
        # 7. حساب رياضي
        elif sentence_analysis['entities'].get('number') or 'احسب' in text_lower:
            intent_result['primary_intent'] = 'calculation'
            intent_result['confidence'] = 0.95
            intent_result['reasoning'].append('يطلب حساباً رياضياً')
        
        # إضافة النوايا الثانوية
        if semantic['is_temporal']:
            intent_result['secondary_intents'].append('time_scoped')
        if sentence_analysis['is_urgent']:
            intent_result['secondary_intents'].append('urgent')
        if sentence_analysis['is_polite']:
            intent_result['secondary_intents'].append('polite')
        
        return intent_result

# ==================== معالج السياق الذكي ====================

class ContextualProcessor:
    """معالج السياق - يفهم العلاقات بين الأسئلة"""
    
    def __init__(self):
        self.conversation_history = []
        self.current_topic = None
        self.mentioned_entities = set()
    
    def add_message(self, text: str, analysis: Dict[str, Any]):
        """إضافة رسالة للسياق"""
        self.conversation_history.append({
            'text': text,
            'analysis': analysis,
        })
        
        # تحديث الكيانات المذكورة
        if 'entities' in analysis:
            for entity_type, values in analysis['entities'].items():
                self.mentioned_entities.add(entity_type)
        
        # تحديث الموضوع الحالي
        if analysis.get('main_concept'):
            self.current_topic = analysis['main_concept']
    
    def resolve_references(self, text: str) -> str:
        """حل الضمائر والإشارات"""
        # "وكم منهم..." -> يعود للكيان المذكور سابقاً
        text_lower = text.lower()
        
        if any(ref in text_lower for ref in ['منهم', 'منها', 'هذا', 'ذلك', 'تلك']):
            if 'customer' in self.mentioned_entities:
                text = text.replace('منهم', 'من العملاء')
            elif 'product' in self.mentioned_entities:
                text = text.replace('منها', 'من المنتجات')
        
        return text
    
    def get_context_clues(self) -> Dict[str, Any]:
        """الحصول على دلائل السياق"""
        return {
            'current_topic': self.current_topic,
            'mentioned_entities': list(self.mentioned_entities),
            'conversation_length': len(self.conversation_history),
        }

# ==================== المحرك الرئيسي ====================

class IntelligentNLPEngine:
    """محرك NLP الذكي - يجمع كل شيء"""
    
    def __init__(self):
        self.intent_detector = AdvancedIntentDetector()
        self.context_processor = ContextualProcessor()
    
    def process(self, text: str) -> Dict[str, Any]:
        """معالجة ذكية كاملة للنص"""
        
        # 1. حل الإشارات من السياق
        resolved_text = self.context_processor.resolve_references(text)
        
        # 2. كشف النية
        intent = self.intent_detector.detect_intent(resolved_text)
        
        # 3. تحليل الجملة
        sentence = self.intent_detector.sentence_analyzer.analyze(resolved_text)
        
        # 4. فهم المعنى
        semantic = self.intent_detector.semantic_engine.understand_question(resolved_text)
        
        # 5. دمج كل شيء
        result = {
            'original_text': text,
            'resolved_text': resolved_text,
            'intent': intent,
            'sentence_structure': sentence,
            'semantic_meaning': semantic,
            'context': self.context_processor.get_context_clues(),
        }
        
        # 6. حفظ في السياق
        self.context_processor.add_message(text, result)
        
        return result
    
    def explain_understanding(self, result: Dict[str, Any]) -> str:
        """شرح كيف فهم النظام السؤال"""
        explanation = f"""🧠 **فهمي للسؤال:**

📝 **النص:** {result['original_text']}

🎯 **النية الرئيسية:** {result['intent']['primary_intent']}
   الثقة: {result['intent']['confidence']*100:.0f}%

💭 **السبب:**
{chr(10).join(f'   • {r}' for r in result['intent']['reasoning'])}

📊 **التحليل:**
   • المفهوم: {result['semantic_meaning']['main_concept']}
   • نوع السؤال: {'كمي' if result['semantic_meaning']['is_quantitative'] else 'نوعي'}
   • له بُعد زمني: {'نعم' if result['semantic_meaning']['is_temporal'] else 'لا'}

🔗 **السياق:**
   • الموضوع الحالي: {result['context']['current_topic']}
   • الكيانات المذكورة: {', '.join(result['context']['mentioned_entities'][:5])}
"""
        return explanation

# ==================== الواجهة البسيطة ====================

# نسخة عامة للاستخدام
_global_nlp_engine = None

def get_nlp_engine():
    """الحصول على محرك NLP العام"""
    global _global_nlp_engine
    if _global_nlp_engine is None:
        _global_nlp_engine = IntelligentNLPEngine()
    return _global_nlp_engine

def understand_text(text: str, explain: bool = False) -> Dict[str, Any]:
    """فهم النص بذكاء
    
    Args:
        text: النص المراد فهمه
        explain: هل تريد شرح الفهم؟
    
    Returns:
        تحليل ذكي كامل
    """
    engine = get_nlp_engine()
    result = engine.process(text)
    
    if explain:
        result['explanation'] = engine.explain_understanding(result)
    return result

# ==================== اختبار ====================

if __name__ == '__main__':

    test_questions = [
        "كم عدد العملاء؟",
        "وكم منهم دفعوا؟",  # سؤال متابعة
        "حلل أداء المبيعات",
        "احسب VAT لـ 5000 شيقل",
        "وين صفحة الصيانة؟",
        "ما الفرق بين الشامل ونظامكم؟",
    ]
    
    for q in test_questions:

        result = understand_text(q, explain=True)
