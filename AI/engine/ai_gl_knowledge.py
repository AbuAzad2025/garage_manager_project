"""
معرفة دفتر الأستاذ للمساعد الذكي
GL Knowledge Base for AI Assistant

🎯 الهدف: جعل المساعد الذكي خبيراً في:
- نظام دفتر الأستاذ (GL)
- القيود المحاسبية
- التحليل المالي
- حل المشاكل المحاسبية
"""

from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Any, Optional


# ═══════════════════════════════════════════════════════════════════════
# 📚 GL System Knowledge - معرفة نظام دفتر الأستاذ
# ═══════════════════════════════════════════════════════════════════════

GL_SYSTEM_KNOWLEDGE = {
    "description": """
    🏦 **نظام دفتر الأستاذ (GL) في نظام أزاد:**
    
    نظام محاسبي متكامل بمعايير Enterprise-Grade يتبع Double-Entry Bookkeeping.
    كل معاملة تُسجّل تلقائياً في دفتر الأستاذ عبر Event Listeners.
    """,
    
    "models": {
        "GLBatch": {
            "description": "مجموعة قيود محاسبية (Batch of GL Entries)",
            "fields": {
                "id": "المعرّف الفريد",
                "batch_date": "تاريخ المجموعة",
                "source_type": "نوع المصدر (SALE, PAYMENT, EXPENSE, etc.)",
                "source_id": "معرّف المصدر",
                "purpose": "الغرض (REVENUE, OPENING_BALANCE, EXPENSE, etc.)",
                "currency": "العملة",
                "memo": "الوصف",
                "reference": "المرجع الخارجي",
                "entity_type": "نوع الكيان",
                "entity_id": "معرّف الكيان",
                "total_debit": "إجمالي المدين",
                "total_credit": "إجمالي الدائن",
            },
            "relationships": {
                "entries": "القيود المحاسبية (GLEntry) - علاقة 1:N"
            }
        },
        
        "GLEntry": {
            "description": "قيد محاسبي واحد (Single GL Entry)",
            "fields": {
                "id": "المعرّف",
                "gl_batch_id": "معرّف المجموعة",
                "account_code": "رمز الحساب (1000_CASH, 4000_SALES, etc.)",
                "debit_amount": "المبلغ المدين",
                "credit_amount": "المبلغ الدائن",
                "description": "الوصف",
                "entity_type": "نوع الكيان المرتبط",
                "entity_id": "معرّف الكيان المرتبط",
            }
        }
    },
    
    "accounts": {
        "description": "دليل الحسابات (Chart of Accounts)",
        "structure": {
            "1xxx": "أصول (Assets)",
            "2xxx": "خصوم (Liabilities)",
            "3xxx": "حقوق الملكية (Equity)",
            "4xxx": "إيرادات (Revenue)",
            "5xxx": "مصروفات (Expenses)",
        },
        
        "main_accounts": {
            "1000_CASH": "النقدية",
            "1010_BANK": "البنك",
            "1020_CARD_CLEARING": "مقاصة البطاقات",
            "1100_AR": "العملاء (Accounts Receivable)",
            "1200_INVENTORY": "المخزون",
            "1300_CHECKS_RECEIVABLE": "شيكات تحت التحصيل",
            
            "2000_AP": "الموردين (Accounts Payable)",
            "2100_CHECKS_PAYABLE": "شيكات تحت الدفع",
            
            "3000_EQUITY": "رأس المال",
            "3100_RETAINED_EARNINGS": "الأرباح المحتجزة",
            
            "4000_SALES": "إيرادات المبيعات",
            "4100_SERVICE_REVENUE": "إيرادات الخدمات",
            
            "5000_EXPENSES": "المصاريف العامة",
            "5100_COGS": "تكلفة البضاعة المباعة (Cost of Goods Sold)",
        }
    },
    
    "auto_gl_creation": {
        "description": "إنشاء GL تلقائي عبر Event Listeners",
        "modules": [
            {
                "module": "Customer Opening Balance",
                "listener": "_customer_opening_balance_gl",
                "trigger": "after_insert, after_update",
                "entries": "AR ↔ Equity"
            },
            {
                "module": "Supplier Opening Balance",
                "listener": "_supplier_opening_balance_gl",
                "trigger": "after_insert, after_update",
                "entries": "AP ↔ Equity"
            },
            {
                "module": "Partner Opening Balance",
                "listener": "_partner_opening_balance_gl",
                "trigger": "after_insert, after_update",
                "entries": "AP ↔ Equity"
            },
            {
                "module": "Sale",
                "listener": "_sale_gl_batch_upsert",
                "trigger": "after_insert, after_update (CONFIRMED)",
                "entries": "AR (debit) ↔ Revenue (credit) + Partner AP + COGS"
            },
            {
                "module": "Payment",
                "listener": "_payment_gl_batch_upsert",
                "trigger": "after_insert, after_update (COMPLETED)",
                "entries": "Cash/Bank ↔ AR/AP (depends on direction)"
            },
            {
                "module": "Expense",
                "listener": "_expense_gl_batch_upsert",
                "trigger": "after_insert, after_update",
                "entries": "Expense (debit) ↔ Cash/Bank (credit)"
            },
            {
                "module": "Check",
                "listener": "create_gl_entry_for_check",
                "trigger": "status change",
                "entries": "Complex lifecycle accounting"
            },
            {
                "module": "Shipment",
                "listener": "_shipment_gl_*",
                "trigger": "arrival",
                "entries": "Inventory (debit) ↔ AP (credit) + COGS"
            },
            {
                "module": "Service",
                "listener": "_service_gl_*",
                "trigger": "completion",
                "entries": "AR (debit) ↔ Service Revenue (credit)"
            },
        ]
    }
}


# ═══════════════════════════════════════════════════════════════════════
# 💡 GL Business Rules - قواعد العمل المحاسبية
# ═══════════════════════════════════════════════════════════════════════

GL_BUSINESS_RULES = {
    "double_entry": {
        "rule": "كل قيد يجب أن يكون متوازن (Total Debit = Total Credit)",
        "example": "عند بيع بمبلغ 1000:\n- مدين: AR 1000\n- دائن: Sales 1000"
    },
    
    "opening_balance": {
        "rule": "الرصيد الافتتاحي يُسجّل في GL عبر listener",
        "customer": {
            "positive": "له علينا → AR (credit) + Equity (debit)",
            "negative": "عليه لنا → AR (debit) + Equity (credit)"
        },
        "supplier": {
            "positive": "له علينا → AP (credit) + Equity (debit)",
            "negative": "عليه لنا → AP (debit) + Equity (credit)"
        }
    },
    
    "sale_accounting": {
        "rule": "المبيعات تُسجّل عند CONFIRMED",
        "basic": "AR (debit) ↔ Revenue (credit)",
        "with_partners": "Revenue يُقسّم حسب نسب الشركاء",
        "with_exchange": "COGS (debit) + AP Supplier (credit)",
        "complex": """
        1. AR للعميل (مدين)
        2. Revenue للشركة (دائن) - حسب warehouse type
        3. AP للشريك (دائن) - إذا كان partner warehouse
        4. COGS + AP للمورد - إذا كان exchange warehouse
        """
    },
    
    "payment_accounting": {
        "rule": "الدفعات تُسجّل عند COMPLETED",
        "incoming": "Cash/Bank (debit) ↔ AR (credit)",
        "outgoing": "AP (debit) ↔ Cash/Bank (credit)",
        "multi_entity": "Payment يمكن أن يرتبط بـ 10 كيانات مختلفة"
    },
    
    "check_lifecycle": {
        "incoming_received": "Checks Receivable (debit) ↔ AR (credit)",
        "incoming_cashed": "Bank (debit) ↔ Checks Receivable (credit)",
        "incoming_returned": "AR (debit) ↔ Checks Receivable (credit)",
        
        "outgoing_issued": "AP (debit) ↔ Checks Payable (credit)",
        "outgoing_cashed": "Checks Payable (debit) ↔ Bank (credit)",
        "outgoing_returned": "Checks Payable (debit) ↔ AP (credit)",
    }
}


# ═══════════════════════════════════════════════════════════════════════
# 🔍 GL Analysis Functions - دوال تحليل دفتر الأستاذ
# ═══════════════════════════════════════════════════════════════════════

def explain_gl_entry(gl_entry_data: Dict) -> str:
    """
    شرح قيد محاسبي بطريقة مفهومة
    
    Args:
        gl_entry_data: بيانات القيد (account_code, debit, credit, description)
    
    Returns:
        شرح واضح بالعربية
    """
    account_code = gl_entry_data.get('account_code', '')
    debit = float(gl_entry_data.get('debit_amount', 0))
    credit = float(gl_entry_data.get('credit_amount', 0))
    description = gl_entry_data.get('description', '')
    
    # شرح الحساب
    account_name = GL_SYSTEM_KNOWLEDGE['accounts']['main_accounts'].get(
        account_code, account_code
    )
    
    # تحديد النوع
    entry_type = "مدين" if debit > 0 else "دائن"
    amount = debit if debit > 0 else credit
    
    # شرح الأثر
    effect = _explain_account_effect(account_code, entry_type, amount)
    
    explanation = f"""
📝 **قيد محاسبي:**
- الحساب: {account_name} ({account_code})
- النوع: {entry_type}
- المبلغ: {amount:,.2f} شيقل
- الوصف: {description}

💡 **الأثر:**
{effect}
"""
    
    return explanation.strip()


def _explain_account_effect(account_code: str, entry_type: str, amount: float) -> str:
    """شرح أثر القيد على الحساب"""
    
    account_category = account_code[:1]  # First digit
    
    effects = {
        "1": {  # Assets
            "مدين": f"زيادة في الأصول بمبلغ {amount:,.2f} شيقل ✅",
            "دائن": f"نقص في الأصول بمبلغ {amount:,.2f} شيقل ⬇️"
        },
        "2": {  # Liabilities
            "مدين": f"نقص في الخصوم (تسديد التزام) بمبلغ {amount:,.2f} شيقل ⬇️",
            "دائن": f"زيادة في الخصوم (التزام جديد) بمبلغ {amount:,.2f} شيقل ⬆️"
        },
        "3": {  # Equity
            "مدين": f"نقص في رأس المال بمبلغ {amount:,.2f} شيقل ⬇️",
            "دائن": f"زيادة في رأس المال بمبلغ {amount:,.2f} شيقل ⬆️"
        },
        "4": {  # Revenue
            "مدين": f"تخفيض إيرادات بمبلغ {amount:,.2f} شيقل (مرتجعات) ⬇️",
            "دائن": f"إيرادات جديدة بمبلغ {amount:,.2f} شيقل 💰"
        },
        "5": {  # Expenses
            "مدين": f"مصروف جديد بمبلغ {amount:,.2f} شيقل 💸",
            "دائن": f"تخفيض مصروف (إلغاء) بمبلغ {amount:,.2f} شيقل ✅"
        }
    }
    
    return effects.get(account_category, {}).get(entry_type, "تأثير غير معروف")


def analyze_gl_batch(gl_batch_data: Dict) -> Dict[str, Any]:
    """
    تحليل شامل لمجموعة قيود
    
    Args:
        gl_batch_data: بيانات GLBatch مع entries
    
    Returns:
        تحليل شامل
    """
    total_debit = sum(float(e.get('debit_amount', 0)) for e in gl_batch_data.get('entries', []))
    total_credit = sum(float(e.get('credit_amount', 0)) for e in gl_batch_data.get('entries', []))
    
    is_balanced = abs(total_debit - total_credit) < 0.01
    
    analysis = {
        "balanced": is_balanced,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "difference": total_debit - total_credit,
        "entries_count": len(gl_batch_data.get('entries', [])),
        "source_type": gl_batch_data.get('source_type'),
        "purpose": gl_batch_data.get('purpose'),
        "explanation": _explain_gl_batch_purpose(gl_batch_data)
    }
    
    if not is_balanced:
        analysis["warning"] = f"⚠️ القيد غير متوازن! الفرق: {analysis['difference']:,.2f} شيقل"
    
    return analysis


def _explain_gl_batch_purpose(gl_batch_data: Dict) -> str:
    """شرح غرض مجموعة القيود"""
    
    source_type = gl_batch_data.get('source_type', '')
    purpose = gl_batch_data.get('purpose', '')
    memo = gl_batch_data.get('memo', '')
    
    explanations = {
        "SALE_REVENUE": "قيد إيرادات مبيعات - تسجيل فاتورة مبيعات",
        "OPENING_BALANCE": "قيد رصيد افتتاحي - تسجيل الرصيد المبدئي",
        "PAYMENT": "قيد دفعة - تسجيل دفعة مالية",
        "EXPENSE": "قيد مصروف - تسجيل مصروف",
        "CHECK": "قيد شيك - إدارة دورة حياة الشيك",
        "SHIPMENT": "قيد شحنة - استلام بضاعة",
        "SERVICE": "قيد خدمة - تسجيل خدمة صيانة",
    }
    
    key = f"{source_type}_{purpose}".upper()
    
    return explanations.get(key, explanations.get(purpose, memo or "قيد محاسبي عام"))


# ═══════════════════════════════════════════════════════════════════════
# 📊 GL Reports Knowledge - معرفة تقارير دفتر الأستاذ
# ═══════════════════════════════════════════════════════════════════════

GL_REPORTS_KNOWLEDGE = {
    "trial_balance": {
        "name_ar": "ميزان المراجعة",
        "name_en": "Trial Balance",
        "description": "قائمة بجميع الحسابات مع أرصدتها المدينة والدائنة",
        "purpose": "التحقق من توازن القيود المحاسبية",
        "formula": "إجمالي المدين = إجمالي الدائن",
        "columns": ["رمز الحساب", "اسم الحساب", "المدين", "الدائن", "الرصيد"]
    },
    
    "balance_sheet": {
        "name_ar": "الميزانية العمومية",
        "name_en": "Balance Sheet",
        "description": "بيان المركز المالي في تاريخ معين",
        "formula": "الأصول = الخصوم + حقوق الملكية",
        "sections": {
            "assets": "الأصول (Assets)",
            "liabilities": "الخصوم (Liabilities)",
            "equity": "حقوق الملكية (Equity)"
        }
    },
    
    "income_statement": {
        "name_ar": "قائمة الدخل",
        "name_en": "Income Statement",
        "description": "بيان الأرباح والخسائر عن فترة معينة",
        "formula": "صافي الربح = الإيرادات - المصروفات",
        "sections": {
            "revenue": "الإيرادات (Revenue)",
            "cogs": "تكلفة البضاعة المباعة (COGS)",
            "gross_profit": "إجمالي الربح (Gross Profit)",
            "expenses": "المصروفات (Operating Expenses)",
            "net_profit": "صافي الربح (Net Profit)"
        }
    },
    
    "cash_flow": {
        "name_ar": "قائمة التدفقات النقدية",
        "name_en": "Cash Flow Statement",
        "description": "بيان حركة النقد خلال فترة معينة",
        "sections": {
            "operating": "الأنشطة التشغيلية",
            "investing": "الأنشطة الاستثمارية",
            "financing": "الأنشطة التمويلية"
        }
    }
}


# ═══════════════════════════════════════════════════════════════════════
# 🎯 AI Helper Functions - دوال مساعدة للذكاء الاصطناعي
# ═══════════════════════════════════════════════════════════════════════

def get_gl_knowledge_for_ai() -> Dict[str, Any]:
    """
    الحصول على جميع معارف GL للمساعد الذكي
    
    Returns:
        قاعدة معرفة شاملة
    """
    return {
        "system_knowledge": GL_SYSTEM_KNOWLEDGE,
        "business_rules": GL_BUSINESS_RULES,
        "reports_knowledge": GL_REPORTS_KNOWLEDGE,
        
        "capabilities": [
            "فهم نظام دفتر الأستاذ بالكامل",
            "شرح القيود المحاسبية",
            "تحليل GLBatch",
            "كشف الأخطاء المحاسبية",
            "شرح التقارير المالية",
            "تتبع المعاملات من المصدر للـ GL",
        ],
        
        "can_answer": [
            "ما هو دفتر الأستاذ؟",
            "كيف يتم إنشاء GL تلقائياً؟",
            "ما هي القيود المحاسبية للمبيعات؟",
            "فسّر لي هذا القيد",
            "لماذا الرصيد غير متوازن؟",
            "ما هو ميزان المراجعة؟",
            "كيف أقرأ الميزانية العمومية؟",
            "ما الفرق بين AR و AP؟",
        ]
    }


def detect_gl_error(gl_batch_data: Dict) -> Optional[Dict[str, str]]:
    """
    كشف الأخطاء في القيود المحاسبية
    
    Args:
        gl_batch_data: بيانات GLBatch
    
    Returns:
        معلومات الخطأ إذا وُجد
    """
    entries = gl_batch_data.get('entries', [])
    
    if not entries:
        return {
            "error": "empty_batch",
            "message": "⚠️ لا توجد قيود في هذه المجموعة",
            "solution": "تأكد من إضافة قيود محاسبية"
        }
    
    # فحص التوازن
    total_debit = sum(float(e.get('debit_amount', 0)) for e in entries)
    total_credit = sum(float(e.get('credit_amount', 0)) for e in entries)
    
    if abs(total_debit - total_credit) > 0.01:
        return {
            "error": "unbalanced",
            "message": f"⚠️ القيد غير متوازن!\nالمدين: {total_debit:,.2f}\nالدائن: {total_credit:,.2f}\nالفرق: {total_debit - total_credit:,.2f}",
            "solution": "راجع القيود وتأكد أن إجمالي المدين = إجمالي الدائن"
        }
    
    # فحص القيود الفارغة
    for i, entry in enumerate(entries):
        debit = float(entry.get('debit_amount', 0))
        credit = float(entry.get('credit_amount', 0))
        
        if debit == 0 and credit == 0:
            return {
                "error": "zero_entry",
                "message": f"⚠️ القيد رقم {i+1} فارغ (لا مدين ولا دائن)",
                "solution": "احذف القيد الفارغ أو أضف مبلغ"
            }
        
        if debit > 0 and credit > 0:
            return {
                "error": "double_entry",
                "message": f"⚠️ القيد رقم {i+1} يحتوي على مدين ودائن معاً!",
                "solution": "كل قيد يجب أن يكون إما مدين أو دائن فقط"
            }
    
    # لا توجد أخطاء
    return None


def suggest_gl_correction(error_info: Dict) -> str:
    """اقتراح تصحيح للخطأ المحاسبي"""
    
    error_type = error_info.get('error', '')
    
    suggestions = {
        "unbalanced": """
💡 **خطوات التصحيح:**
1. احسب الفرق بين المدين والدائن
2. ابحث عن القيد الخاطئ (مبلغ مفقود أو مضاعف)
3. تحقق من أن كل معاملة لها طرفين متساويين
4. إذا كان الفرق صغير (< 1)، قد يكون خطأ تقريب
""",
        "empty_batch": """
💡 **خطوات التصحيح:**
1. تحقق من أن المعاملة تم حفظها بنجاح
2. راجع Event Listener المسؤول
3. تأكد من أن الشروط مستوفاة (مثل: status = CONFIRMED)
""",
        "zero_entry": """
💡 **خطوات التصحيح:**
1. احذف القيد الفارغ
2. أو أضف المبلغ الصحيح (إما مدين أو دائن)
""",
        "double_entry": """
💡 **خطوات التصحيح:**
1. حدد إذا كان القيد مدين أم دائن
2. اجعل الآخر = 0
3. لا يمكن أن يكون القيد الواحد مدين ودائن معاً!
"""
    }
    
    return suggestions.get(error_type, "راجع البيانات وتواصل مع الدعم الفني")


# ═══════════════════════════════════════════════════════════════════════
# 🎓 Export للاستخدام في AI Service
# ═══════════════════════════════════════════════════════════════════════

__all__ = [
    'GL_SYSTEM_KNOWLEDGE',
    'GL_BUSINESS_RULES',
    'GL_REPORTS_KNOWLEDGE',
    'get_gl_knowledge_for_ai',
    'explain_gl_entry',
    'analyze_gl_batch',
    'detect_gl_error',
    'suggest_gl_correction',
    'explain_any_number',
    'trace_transaction_flow'
]


# ═══════════════════════════════════════════════════════════════════════════
# 🔍 DEEP FINANCIAL ANALYZER - محلل مالي عميق
# ═══════════════════════════════════════════════════════════════════════════

def explain_any_number(number_value: float, context: str) -> str:
    """
    تفسير أي رقم في النظام بالتفصيل الكامل
    
    المساعد يجب أن يعرف يشرح أي رقم:
    - ما هو؟
    - من أين أتى؟
    - كيف تم حسابه؟
    - لماذا بهذا الشكل؟
    - البنود المكونة له
    - احتمالات الخطأ
    
    Args:
        number_value: القيمة الرقمية
        context: السياق (customer_balance, sales_total, etc.)
    
    Returns:
        شرح تفصيلي كامل
    """
    
    explanations = {
        "customer_balance": lambda val: f"""
📊 **رصيد العميل: {val:,.2f} ₪**

🔍 **ما هو؟**
الرصيد الحالي للعميل في دفاترنا

📥 **من أين أتى؟**
- المبيعات الآجلة للعميل (+)
- الفواتير الصادرة له (+)
- الخدمات المقدمة له (+)
- الدفعات المستلمة منه (-)
- الدفعات المدفوعة له (-) [نادرة]

🧮 **كيف تم حسابه؟**
الرصيد = (المبيعات + الفواتير + الخدمات) - (الدفعات الواردة IN)

{'🔴 **المعنى:** العميل عليه يدفع ' + str(abs(val)) + ' ₪' if val < 0 else '🟢 **المعنى:** للعميل رصيد عندنا ' + str(val) + ' ₪ (دفع زيادة)' if val > 0 else '⚪ **المعنى:** الحساب مسدد بالكامل'}

💡 **لماذا بهذا الشكل؟**
نظام القيد المزدوج: كل معاملة تُسجل في دفتر الأستاذ
- بيع → مدين AR (يزيد الدين)
- دفع → دائن AR (ينقص الدين)

⚠️ **احتمالات الخطأ:**
1. دفعة لم تُسجل (يظهر الرصيد أكبر من الواقع)
2. دفعة مسجلة مرتين (يظهر الرصيد أقل)
3. مبيعة ملغاة لم يتم عكس قيدها
4. خطأ في ربط الدفعة بالعميل
""",
        
        "total_sales": lambda val: f"""
💰 **إجمالي المبيعات: {val:,.2f} ₪**

🔍 **ما هو؟**
مجموع جميع عمليات البيع في الفترة المحددة

📥 **من أين أتى؟**
- جدول Sales → جمع sale_total
- الحالة: CONFIRMED فقط
- التاريخ: ضمن الفترة المختارة

🧮 **كيف تم حسابه؟**
```sql
SELECT SUM(sale_total) 
FROM sales 
WHERE status = 'CONFIRMED' 
AND sale_date BETWEEN start_date AND end_date
```

💡 **التفصيل:**
- سعر القطعة × الكمية = المجموع الفرعي
- المجموع الفرعي - الخصم = الصافي
- الصافي + الضريبة (VAT) = الإجمالي

📊 **القيد المحاسبي:**
- مدين: 1100_AR (ذمم العملاء) {val:,.2f} ₪
- دائن: 4000_SALES (إيرادات المبيعات) {val / 1.16:,.2f} ₪
- دائن: 2100_VAT_PAYABLE (ضريبة) {val - (val / 1.16):,.2f} ₪

⚠️ **احتمالات الخطأ:**
1. مبيعات بحالة PENDING لم تُؤكد
2. مبيعات ملغاة لم يتم تغيير حالتها
3. تكرار في التسجيل
4. خطأ في حساب الضريبة
""",
        
        "vat_payable": lambda val: f"""
🧾 **ضريبة القيمة المضافة المستحقة: {val:,.2f} ₪**

🔍 **ما هي؟**
الضريبة الواجب توريدها للحكومة

📥 **من أين أتت؟**
ضريبة المخرجات - ضريبة المدخلات

🧮 **كيف تم حسابها؟**
1. **ضريبة المخرجات (على المبيعات):**
   - المبيعات الخاضعة للضريبة × 16%
   
2. **ضريبة المدخلات (على المشتريات):**
   - المشتريات الخاضعة للضريبة × 16%
   
3. **الصافي:**
   ضريبة المخرجات - ضريبة المدخلات = {val:,.2f} ₪

{'🔴 **المعنى:** علينا ندفع ' + str(abs(val)) + ' ₪ للحكومة' if val > 0 else '🟢 **المعنى:** لنا رصيد ' + str(abs(val)) + ' ₪ يمكن استرداده'}

📊 **القيد المحاسبي:**
- عند البيع: دائن VAT_PAYABLE (تزيد الضريبة المستحقة)
- عند الشراء: مدين VAT_PAYABLE (تنقص الضريبة المستحقة)
- عند التوريد: مدين VAT_PAYABLE | دائن BANK

⚠️ **احتمالات الخطأ:**
1. عمليات معفاة تم احتساب ضريبة عليها
2. خطأ في النسبة (16% vs 17%)
3. ضريبة مدخلات غير قابلة للخصم تم خصمها
4. عدم ربط الفواتير بالضريبة
"""
    }
    
    handler = explanations.get(context)
    if handler:
        return handler(number_value)
    else:
        return f"""
📊 **القيمة: {number_value:,.2f} ₪**

🔍 السياق: {context}

💡 يرجى تحديد نوع الرقم للحصول على شرح تفصيلي:
- customer_balance (رصيد عميل)
- total_sales (إجمالي مبيعات)
- vat_payable (ضريبة مستحقة)
- net_profit (صافي ربح)
- inventory_value (قيمة مخزون)
"""


def trace_transaction_flow(transaction_type: str, transaction_id: int) -> Dict[str, Any]:
    """
    تتبع مسار معاملة من البداية للنهاية
    
    يشرح كل خطوة في رحلة المعاملة:
    1. التسجيل الأولي
    2. القيود المحاسبية
    3. تأثيرها على الأرصدة
    4. تأثيرها على القوائم المالية
    
    Args:
        transaction_type: نوع المعاملة (sale, payment, expense, etc.)
        transaction_id: رقم المعاملة
    
    Returns:
        تفصيل كامل للمسار
    """
    
    flows = {
        "sale": {
            "step_1": {
                "title": "1️⃣ تسجيل عملية البيع",
                "table": "Sales",
                "action": "إنشاء سجل جديد مع SaleLines",
                "data": ["العميل", "المنتجات", "الكميات", "الأسعار", "الخصم", "الإجمالي"]
            },
            "step_2": {
                "title": "2️⃣ تحديث المخزون",
                "table": "StockLevel",
                "action": "نقص الكميات من المستودع",
                "formula": "الكمية الجديدة = الكمية السابقة - الكمية المباعة"
            },
            "step_3": {
                "title": "3️⃣ إنشاء القيد المحاسبي (GL)",
                "table": "GLBatch + GLEntry",
                "entries": [
                    {"account": "1100_AR", "debit": "المبلغ الإجمالي", "credit": 0},
                    {"account": "4000_SALES", "debit": 0, "credit": "المبلغ بدون ضريبة"},
                    {"account": "2100_VAT", "debit": 0, "credit": "الضريبة 16%"}
                ]
            },
            "step_4": {
                "title": "4️⃣ تحديث رصيد العميل",
                "calculation": "رصيد العميل = الرصيد السابق + مبلغ البيع (يزيد الدين عليه)"
            },
            "step_5": {
                "title": "5️⃣ التأثير على القوائم المالية",
                "income_statement": "+إيرادات المبيعات",
                "balance_sheet": "+ذمم العملاء (AR), +ضريبة مستحقة (VAT)",
                "cash_flow": "لا تأثير (بيع آجل)"
            }
        },
        
        "payment_in": {
            "step_1": {
                "title": "1️⃣ تسجيل الدفعة",
                "table": "Payment",
                "data": ["العميل", "المبلغ", "طريقة الدفع", "التاريخ"]
            },
            "step_2": {
                "title": "2️⃣ إنشاء القيد المحاسبي",
                "entries": [
                    {"account": "1000_CASH أو 1010_BANK", "debit": "المبلغ", "credit": 0},
                    {"account": "1100_AR", "debit": 0, "credit": "المبلغ"}
                ]
            },
            "step_3": {
                "title": "3️⃣ تحديث رصيد العميل",
                "calculation": "رصيد العميل = الرصيد السابق - المبلغ المدفوع (ينقص الدين)"
            },
            "step_4": {
                "title": "4️⃣ التأثير على القوائم المالية",
                "balance_sheet": "+النقدية/البنك, -ذمم العملاء",
                "cash_flow": "+تدفق نقدي من الأنشطة التشغيلية"
            }
        }
    }
    
    return flows.get(transaction_type, {
        "error": f"نوع المعاملة '{transaction_type}' غير معروف",
        "available": list(flows.keys())
    })

