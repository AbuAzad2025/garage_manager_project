"""
💬 AI Conversation Manager - مدير المحادثة والذاكرة
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- إدارة الذاكرة التحادثية (Conversation Memory)
- تتبع السياق (Context Tracking)
- إدارة الجلسات (Session Management)
- الرد الذكي المحلي (Local Smart Responses)

Refactored: 2025-11-01
"""

from datetime import datetime
from typing import Dict, List, Any, Optional
import json
import os


# ═══════════════════════════════════════════════════════════════════════════
# 🧠 CONVERSATION MEMORY - الذاكرة التحادثية
# ═══════════════════════════════════════════════════════════════════════════

_conversation_memory = {}


def get_or_create_session_memory(session_id: str) -> Dict[str, Any]:
    """
    الحصول على ذاكرة الجلسة أو إنشاءها
    
    Args:
        session_id: معرف الجلسة (مثل: user_123)
    
    Returns:
        ذاكرة الجلسة مع تاريخ المحادثات
    """
    global _conversation_memory
    
    if session_id not in _conversation_memory:
        _conversation_memory[session_id] = {
            'session_id': session_id,
            'created_at': datetime.now().isoformat(),
            'messages': [],
            'context': {},
            'last_entities': []
        }
    
    return _conversation_memory[session_id]


def add_to_memory(session_id: str, role: str, content: str):
    """
    إضافة رسالة للذاكرة
    
    Args:
        session_id: معرف الجلسة
        role: 'user' أو 'assistant'
        content: محتوى الرسالة
    """
    memory = get_or_create_session_memory(session_id)
    
    memory['messages'].append({
        'role': role,
        'content': content,
        'timestamp': datetime.now().isoformat()
    })
    
    # حفظ آخر 50 رسالة فقط (توفير الذاكرة)
    if len(memory['messages']) > 50:
        memory['messages'] = memory['messages'][-50:]


def clear_session_memory(session_id: str):
    """مسح ذاكرة جلسة معينة"""
    global _conversation_memory
    
    if session_id in _conversation_memory:
        del _conversation_memory[session_id]


def get_conversation_context(session_id: str) -> Dict[str, Any]:
    """
    الحصول على سياق المحادثة
    
    Returns:
        {
            'last_topic': 'customers',
            'last_entities': ['customer_123'],
            'message_count': 10
        }
    """
    memory = get_or_create_session_memory(session_id)
    
    return {
        'message_count': len(memory['messages']),
        'last_entities': memory.get('last_entities', []),
        'context': memory.get('context', {})
    }


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 LOCAL SMART RESPONSES - الردود الذكية المحلية
# ═══════════════════════════════════════════════════════════════════════════

def get_local_faq_responses() -> Dict[str, str]:
    """
    الأسئلة الشائعة - ردود فورية محلية بدون AI
    
    هذه الردود سريعة ولا تحتاج Groq API
    """
    return {
        'من أنت': """🤖 أنا المساعد الذكي المحاسبي المحترف في نظام أزاد.

📌 قدراتي:
• قراءة مباشرة من قاعدة البيانات (87 جدول)
• حسابات مالية دقيقة (VAT، ضرائب، عملات)
• معرفة شاملة بدفتر الأستاذ العام (GL)
• تحليل عميق لأي رقم في النظام
• خبير في القانون الضريبي (فلسطين + إسرائيل)

🏢 النظام:
• الشركة: أزاد للأنظمة الذكية
• المطور: المهندس أحمد غنام
• الموقع: رام الله - فلسطين 🇵🇸""",
        
        'ما قدراتك': """🧠 قدراتي الكاملة كمحاسب محترف:

1. 📊 التحليل المحاسبي:
   • شرح أي رقم بالتفصيل (من أين؟ كيف؟ لماذا؟)
   • تتبع المعاملات من البداية للنهاية
   • قراءة القيود المحاسبية (GL Entries)
   • كشف الأخطاء المحاسبية

2. 💰 الحسابات المالية:
   • حساب VAT (16% فلسطين / 17% إسرائيل)
   • حساب ضريبة الدخل
   • تحويل العملات
   • حساب الأرباح والخسائر

3. 📈 القوائم المالية:
   • قائمة الدخل (Income Statement)
   • الميزانية العمومية (Balance Sheet)
   • قائمة التدفقات النقدية
   • ميزان المراجعة (Trial Balance)

4. 🔍 التدقيق المالي:
   • فحص توازن القيود
   • كشف الأخطاء المحاسبية
   • اقتراح التصحيحات

5. 🧭 التنقل:
   • معرفة كل صفحات النظام (197 صفحة)
   • توجيه مباشر للوحدات""",
        
        'كيف أضيف عميل': """📝 إضافة عميل جديد:

1. اذهب إلى: `/customers/add`
2. أدخل البيانات المطلوبة:
   • الاسم
   • رقم الهاتف
   • البريد الإلكتروني (اختياري)
   • العنوان
3. اضغط حفظ

🔗 الرابط المباشر: /customers/add""",
        
        'اشرح رصيد العميل': """📊 **رصيد العميل - الشرح الكامل:**

🧮 **الصيغة:**
الرصيد = (المبيعات + الفواتير + الخدمات) - (الدفعات الواردة IN)

📍 **المعنى:**
• رصيد سالب (-) = 🔴 أحمر = العميل عليه يدفع
• رصيد موجب (+) = 🟢 أخضر = للعميل رصيد عندنا (دفع زيادة)
• رصيد صفر (0) = ⚪ الحساب مسدد بالكامل

💡 **مثال:**
عميل اشترى بـ 1000 ₪ ودفع 600 ₪
الرصيد = (1000) - (600) = -400 ₪
المعنى: العميل لسه عليه 400 ₪

📊 **القيود المحاسبية:**
• عند البيع: مدين AR (يزيد الدين)
• عند الدفع: دائن AR (ينقص الدين)""",
        
        'كيف أحسب الضريبة': """🧾 **حساب ضريبة القيمة المضافة:**

🇵🇸 **فلسطين (16%):**
• إذا السعر بدون ضريبة:
  الضريبة = المبلغ × 0.16
  مثال: 1000 × 0.16 = 160 ₪

• إذا السعر شامل الضريبة:
  الصافي = الإجمالي ÷ 1.16
  مثال: 1160 ÷ 1.16 = 1000 ₪

🇮🇱 **إسرائيل (17%):**
• بدون ضريبة: المبلغ × 0.17
• شامل: الإجمالي ÷ 1.17

📊 **القيد المحاسبي:**
مدين: AR (الإجمالي)
دائن: SALES (الصافي)
دائن: VAT_PAYABLE (الضريبة)"""
    }


def get_local_quick_answers() -> Dict[str, Any]:
    """
    إجابات سريعة لأسئلة شائعة
    
    تُستخدم للرد الفوري بدون الحاجة لـ Groq
    """
    return {
        'greetings': {
            'patterns': ['مرحبا', 'هلا', 'السلام', 'صباح', 'مساء', 'hello', 'hi'],
            'responses': [
                '🤖 مرحباً! أنا المساعد المحاسبي المحترف. كيف أساعدك اليوم؟',
                '👋 أهلاً وسهلاً! أنا هنا لمساعدتك في أي سؤال محاسبي أو مالي.',
                '🌟 حياك الله! اسألني عن أي شيء في النظام.'
            ]
        },
        
        'thanks': {
            'patterns': ['شكرا', 'مشكور', 'thanks', 'thank you'],
            'responses': [
                '😊 العفو! سعيد بخدمتك.',
                '🙏 على الرحب والسعة!',
                '✨ دائماً في الخدمة!'
            ]
        },
        
        'help': {
            'patterns': ['مساعدة', 'help', 'ساعدني'],
            'responses': [
                """🤝 **كيف أساعدك؟**

يمكنني مساعدتك في:
• شرح أي رقم أو رصيد
• حساب الضرائب
• تحليل القيود المحاسبية
• القوائم المالية
• التدقيق المالي
• أي سؤال عن النظام

اسألني أي شيء! 💬"""
            ]
        }
    }


def match_local_response(message: str) -> Optional[str]:
    """
    محاولة إيجاد رد محلي سريع
    
    Args:
        message: رسالة المستخدم
    
    Returns:
        الرد المحلي أو None
    """
    message_lower = message.lower().strip()
    
    # 1. الأسئلة الشائعة (FAQ)
    faqs = get_local_faq_responses()
    for question, answer in faqs.items():
        if question.lower() in message_lower:
            return answer
    
    # 2. الردود السريعة
    quick = get_local_quick_answers()
    
    import random
    
    for category, data in quick.items():
        patterns = data['patterns']
        for pattern in patterns:
            if pattern in message_lower:
                return random.choice(data['responses'])
    
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 📊 CONVERSATION ANALYTICS - تحليلات المحادثة
# ═══════════════════════════════════════════════════════════════════════════

def get_conversation_stats() -> Dict[str, Any]:
    """إحصائيات المحادثات"""
    global _conversation_memory
    
    total_sessions = len(_conversation_memory)
    total_messages = sum(
        len(session['messages'])
        for session in _conversation_memory.values()
    )
    
    return {
        'total_sessions': total_sessions,
        'total_messages': total_messages,
        'active_sessions': total_sessions
    }


__all__ = [
    'get_or_create_session_memory',
    'add_to_memory',
    'clear_session_memory',
    'get_conversation_context',
    'get_local_faq_responses',
    'match_local_response',
    'get_conversation_stats'
]

