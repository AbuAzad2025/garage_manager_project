"""
AI Reasoning Engine - محرك الاستدلال والتفكير الحقيقي
"""

from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime
from extensions import db
from sqlalchemy import text


class ReasoningEngine:
    
    def __init__(self):
        self.knowledge_base = {}
        self.inference_rules = []
        self._load_inference_rules()
    
    def reason_through_problem(self, query: str, available_data: Dict) -> Dict[str, Any]:
        steps = []
        
        understanding = self._understand_query(query)
        steps.append(f"فهمت: {understanding['intent']}")
        
        if understanding['intent'] == 'query_balance':
            return self._reason_balance_query(query, available_data, steps)
        
        elif understanding['intent'] == 'explain_gl':
            return self._reason_gl_explanation(query, available_data, steps)
        
        elif understanding['intent'] == 'explain_calculation':
            return self._reason_calculation(query, available_data, steps)
        
        elif understanding['intent'] == 'tutorial':
            return self._reason_tutorial(query, available_data, steps)
        
        else:
            return self._reason_general(query, available_data, steps)
    
    def _understand_query(self, query: str) -> Dict:
        q_lower = query.lower()
        
        if any(w in q_lower for w in ['كم', 'رصيد', 'balance']):
            return {'intent': 'query_balance', 'needs': ['entity_data', 'transactions']}
        
        if any(w in q_lower for w in ['قيد', 'gl', 'محاسبي', 'ledger']):
            return {'intent': 'explain_gl', 'needs': ['accounting_knowledge', 'gl_rules']}
        
        if any(w in q_lower for w in ['احسب', 'calculate', 'vat', 'ضريبة']):
            return {'intent': 'explain_calculation', 'needs': ['formula', 'numbers']}
        
        if any(w in q_lower for w in ['كيف', 'how', 'steps', 'خطوات']):
            return {'intent': 'tutorial', 'needs': ['procedure', 'system_knowledge']}
        
        return {'intent': 'general', 'needs': []}
    
    def _reason_balance_query(self, query: str, data: Dict, steps: List) -> Dict:
        steps.append("استنتجت: سؤال عن رصيد")
        
        entity_name = self._extract_entity_name(query)
        steps.append(f"استخرجت الاسم: {entity_name if entity_name else 'غير محدد'}")
        
        if entity_name:
            customer_data = self._find_in_database('Customer', 'name', entity_name)
            
            if customer_data:
                steps.append(f"وجدت العميل في Database: ID={customer_data['id']}")
                
                sales = self._get_customer_sales(customer_data['id'])
                payments = self._get_customer_payments(customer_data['id'])
                
                steps.append(f"جلبت {len(sales)} فاتورة بيع")
                steps.append(f"جلبت {len(payments)} دفعة")
                
                total_sales = sum(Decimal(str(s.get('total', 0))) for s in sales)
                total_payments = sum(Decimal(str(p.get('amount', 0))) for p in payments)
                balance = total_sales - total_payments
                
                steps.append(f"حسبت: {total_sales} - {total_payments} = {balance}")
                
                answer_parts = [
                    f"🔍 بحثت عن: {entity_name}",
                    f"✅ وجدته: عميل #{customer_data['id']}",
                    "",
                    "📊 تحليل الرصيد:",
                    f"  • إجمالي المبيعات: {float(total_sales):.2f} ₪",
                    f"  • إجمالي الدفعات: {float(total_payments):.2f} ₪",
                    f"  • الرصيد الحالي: {float(balance):.2f} ₪",
                    "",
                    f"💼 الحالة: {'عليه' if balance > 0 else 'له' if balance < 0 else 'متعادل'}",
                    "",
                    "💡 كيف حُسب:",
                    "  الرصيد = المبيعات - الدفعات",
                    "  (طريقة القيد المزدوج)",
                    "",
                    "📋 من الناحية المحاسبية:",
                    "  • الحساب: 1300 - ذمم العملاء",
                    f"  • مدين: {float(total_sales):.2f} ₪",
                    f"  • دائن: {float(total_payments):.2f} ₪",
                    f"  • الرصيد: {float(balance):.2f} ₪"
                ]
                
                return {
                    'answer': '\n'.join(answer_parts),
                    'confidence': 0.95,
                    'reasoning_steps': steps,
                    'data_used': {
                        'customer': customer_data,
                        'sales_count': len(sales),
                        'payments_count': len(payments)
                    }
                }
            else:
                steps.append("لم أجد العميل في Database")
                return {
                    'answer': f"لم أجد عميلاً باسم '{entity_name}' في قاعدة البيانات.\n\nيمكنك التحقق من:\n1. الإملاء الصحيح\n2. قائمة العملاء: /customers",
                    'confidence': 0.7,
                    'reasoning_steps': steps
                }
        
        else:
            steps.append("لم أستطع استخراج اسم العميل من السؤال")
            return {
                'answer': "لم أفهم اسم العميل المطلوب. من فضلك حدد الاسم.",
                'confidence': 0.5,
                'reasoning_steps': steps
            }
    
    def _reason_gl_explanation(self, query: str, data: Dict, steps: List) -> Dict:
        steps.append("استنتجت: سؤال عن قيود محاسبية")
        
        if 'بيع' in query.lower() or 'sale' in query.lower():
            steps.append("الموضوع: قيد البيع")
            
            answer = """🔍 قيد فاتورة البيع - شرح كامل:

📋 القيد المحاسبي:
════════════════════════════════════════
مدين: 1300 - ذمم العملاء (إجمالي الفاتورة)
دائن: 4000 - المبيعات (صافي بعد الخصم)
دائن: 2100 - ضريبة القيمة المضافة (16%)

💡 المنطق:
══════════
1. العميل صار عليه دين (مدين في حساب الذمم)
2. سجلنا مبيعات (دائن في حساب الإيرادات)
3. سجلنا ضريبة نستحقها للحكومة (دائن)

🔢 مثال رقمي:
══════════
فاتورة بـ 1000 ₪:
- صافي: 862.07 ₪
- VAT 16%: 137.93 ₪
- إجمالي: 1000 ₪

القيد:
مدين: ذمم عملاء = 1000 ₪
دائن: مبيعات = 862.07 ₪
دائن: VAT = 137.93 ₪

✅ التوازن: 1000 = 862.07 + 137.93 ✓

📌 ملاحظات مهمة:
• القيد يُنشأ تلقائياً عند حفظ الفاتورة
• يجب أن يكون متوازناً (مدين = دائن)
• VAT تحسب من الصافي بعد الخصم"""
            
            return {
                'answer': answer,
                'confidence': 0.95,
                'reasoning_steps': steps
            }
        
        steps.append("لم أحدد نوع القيد بدقة")
        return {
            'answer': "القيود المحاسبية في النظام تُنشأ تلقائياً لكل معاملة:\n• بيع → ذمم عملاء (مدين) + مبيعات وVAT (دائن)\n• دفعة واردة → صندوق (مدين) + ذمم (دائن)\n• مصروف → مصروفات (مدين) + صندوق (دائن)",
            'confidence': 0.8,
            'reasoning_steps': steps
        }
    
    def _reason_calculation(self, query: str, data: Dict, steps: List) -> Dict:
        steps.append("استنتجت: سؤال عن حساب")
        
        if 'vat' in query.lower() or 'ضريبة' in query.lower():
            steps.append("الموضوع: حساب VAT")
            
            answer = """🔢 حساب ضريبة القيمة المضافة (VAT) - شرح تفصيلي:

📐 الصيغة الأساسية:
═══════════════════════════════════
VAT = الصافي × 0.16

🇵🇸 في فلسطين: 16%
🇮🇱 في إسرائيل: 17%

💡 مثال عملي:
═══════════════════════════════════
لنفترض فاتورة:
  • منتج A: 100 ₪ × 2 = 200 ₪
  • منتج B: 50 ₪ × 3 = 150 ₪
  • Subtotal (المجموع): 350 ₪
  • خصم 10%: -35 ₪
  • Net (الصافي): 315 ₪
  • VAT 16%: 315 × 0.16 = 50.4 ₪
  • Total (الإجمالي): 365.4 ₪

📊 خطوات الحساب:
1. احسب مجموع المنتجات
2. اطرح الخصم
3. اضرب الصافي × 0.16
4. اجمع الصافي + VAT

⚠️ ملاحظات مهمة:
• VAT تحسب من الصافي (بعد الخصم)
• ليس من المجموع الأولي
• النظام يحسبها تلقائياً

💼 القيد المحاسبي:
دائن: 2100 - ضريبة القيمة المضافة = 50.4 ₪"""
            
            return {
                'answer': answer,
                'confidence': 0.95,
                'reasoning_steps': steps
            }
        
        return {'answer': '', 'confidence': 0, 'reasoning_steps': steps}
    
    def _reason_tutorial(self, query: str, data: Dict, steps: List) -> Dict:
        steps.append("استنتجت: سؤال تعليمي - يحتاج شرح خطوات")
        
        q_lower = query.lower()
        
        if 'عميل' in q_lower and ('أضيف' in q_lower or 'add' in q_lower or 'إنشاء' in q_lower):
            steps.append("الموضوع المطلوب: كيفية إضافة عميل جديد")
            steps.append("استدعاء المعرفة: إجراءات إضافة العميل + القيود المحاسبية")
            
            answer = """📝 كيف تضيف عميل - شرح تفصيلي بالمنطق:

🔗 المسار: /customers/create

📋 الخطوات:
════════════════════════════════════════
1️⃣ افتح صفحة العملاء: /customers
2️⃣ اضغط زر "إضافة عميل جديد"
3️⃣ املأ البيانات:
   
   ✅ الحقول الإجباري:
   • الاسم - مثال: أحمد محمد
   • الهاتف - مثال: 0599123456 (فريد)
   
   📝 الحقول الاختيارية:
   • Email - مثال: ahmad@email.com
   • العنوان - مثال: رام الله، شارع المنارة
   • رقم الهوية
   • ملاحظات

4️⃣ الرصيد الافتتاحي (مهم!):
   • 0 = عميل جديد بدون رصيد سابق
   • موجب (مثلاً 500) = العميل عليه رصيد سابق
   • سالب (مثلاً -300) = العميل له رصيد سابق

5️⃣ اضغط "حفظ"

💼 ماذا يحدث محاسبياً؟
════════════════════════════════════════
إذا كان رصيد افتتاحي 500 ₪:

القيد التلقائي:
مدين: 1300 - ذمم عملاء = 500 ₪
دائن: 3100 - رأس المال = 500 ₪

المعنى: العميل عليه دين قديم (500 ₪)

⚠️ نصائح مهمة:
════════════════════════════════════════
• رقم الهاتف يجب أن يكون فريداً (لا يتكرر)
• الرصيد الافتتاحي غير قابل للتعديل لاحقاً
• كل معاملة مستقبلية ستؤثر على الرصيد تلقائياً"""
            
            return {
                'answer': answer,
                'confidence': 0.95,
                'reasoning_steps': steps
            }
        
        return {'answer': '', 'confidence': 0, 'reasoning_steps': steps}
    
    def _reason_general(self, query: str, data: Dict, steps: List) -> Dict:
        return {'answer': '', 'confidence': 0, 'reasoning_steps': steps}
    
    def _extract_entity_name(self, query: str) -> Optional[str]:
        import re
        
        patterns = [
            r'رصيد\s+([^\s،.؟?]+)',
            r'balance\s+of\s+(\w+)',
            r'customer\s+(\w+)',
            r'العميل\s+([^\s،.؟?]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _find_in_database(self, model_name: str, field: str, value: Any) -> Optional[Dict]:
        try:
            from models import Customer, Supplier, Product
            
            model_map = {
                'Customer': Customer,
                'Supplier': Supplier,
                'Product': Product
            }
            
            model = model_map.get(model_name)
            if not model:
                return None
            
            entity = model.query.filter(
                getattr(model, field).like(f'%{value}%')
            ).first()
            
            if entity:
                return {
                    'id': entity.id,
                    'name': getattr(entity, 'name', ''),
                    'balance': float(getattr(entity, 'balance', 0))
                }
        
        except Exception as e:
            print(f"Database search error: {e}")
        
        return None
    
    def _get_customer_sales(self, customer_id: int) -> List[Dict]:
        try:
            from models import Sale
            
            sales = Sale.query.filter_by(customer_id=customer_id).all()
            
            return [
                {
                    'id': s.id,
                    'date': s.sale_date.isoformat() if s.sale_date else None,
                    'total': float(s.total_amount or 0)
                }
                for s in sales
            ]
        except:
            return []
    
    def _get_customer_payments(self, customer_id: int) -> List[Dict]:
        try:
            from models import Payment
            
            payments = Payment.query.filter_by(
                entity_type='customer',
                entity_id=customer_id
            ).all()
            
            return [
                {
                    'id': p.id,
                    'date': p.payment_date.isoformat() if p.payment_date else None,
                    'amount': float(p.amount or 0)
                }
                for p in payments
            ]
        except:
            return []
    
    def _load_inference_rules(self):
        self.inference_rules = [
            {
                'if': 'query_about_balance',
                'then': ['find_entity', 'get_transactions', 'calculate', 'explain']
            },
            {
                'if': 'query_about_gl',
                'then': ['identify_transaction_type', 'explain_accounts', 'show_example']
            }
        ]


_reasoning_engine = None

def get_reasoning_engine():
    global _reasoning_engine
    if _reasoning_engine is None:
        _reasoning_engine = ReasoningEngine()
    return _reasoning_engine


__all__ = ['ReasoningEngine', 'get_reasoning_engine']

