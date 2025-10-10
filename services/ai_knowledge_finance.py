"""
AI Finance Knowledge - المعرفة المالية والضريبية والجمركية
قواعد المحاسبة والضرائب لفلسطين وإسرائيل
"""

FINANCE_KNOWLEDGE = {
    "accounting_principles": {
        "استحقاق": "الإيرادات تُسجّل عند تحققها لا عند قبضها",
        "مطابقة": "تُطابق المصروفات مع الإيرادات المرتبطة بها",
        "وحدة_محاسبية": "الكيان المالي منفصل عن مالكه",
        "استمرارية": "المنشأة مستمرة ما لم يثبت العكس",
        "حيطة_حذر": "عدم المبالغة في تقدير الأصول والإيرادات"
    },
    
    "tax_palestine": {
        "name": "فلسطين - Palestine",
        "vat_rate": 16,
        "vat_name": "ضريبة القيمة المضافة",
        "vat_law": "قانون رقم 6 لسنة 2005 المعدل",
        "income_tax_personal": [
            {"من": 0, "إلى": 75000, "نسبة": 5},
            {"من": 75001, "إلى": 150000, "نسبة": 10},
            {"من": 150001, "إلى": 300000, "نسبة": 15},
            {"من": 300001, "إلى": None, "نسبة": 20}
        ],
        "income_tax_corporate": 15,
        "notes": [
            "ضريبة القيمة المضافة 16% على معظم السلع والخدمات",
            "بعض السلع الأساسية معفاة (خبز، حليب، أدوية أساسية)",
            "ضريبة الدخل على الشركات 15%",
            "إعفاء للمشاريع الصغيرة التي دخلها أقل من 50,000 ₪"
        ]
    },
    
    "tax_israel": {
        "name": "إسرائيل - Israel",
        "vat_rate": 17,
        "vat_name": "מע\"מ - VAT",
        "income_tax_personal_max": 47,
        "income_tax_corporate": 23,
        "capital_gains_tax": 25,
        "notes": [
            "ضريبة القيمة المضافة 17%",
            "ضريبة الشركات 23%",
            "ضريبة الدخل الشخصي تصاعدية حتى 47%",
            "إعفاءات للتصدير (Zero-rated exports)"
        ]
    },
    
    "customs_codes": {
        "8703": {
            "description": "سيارات ركاب وعربات أخرى",
            "tax_rate_palestine": "varies",
            "tax_rate_israel": 83,
            "notes": "الرسوم تعتمد على سعة المحرك ونوع الوقود"
        },
        "8704": {
            "description": "شاحنات نقل البضائع",
            "tax_rate_palestine": "varies",
            "tax_rate_israel": 12,
            "notes": "المركبات التجارية رسومها أقل"
        },
        "8708": {
            "description": "قطع غيار للسيارات",
            "tax_rate_palestine": 0,
            "tax_rate_israel": 0,
            "notes": "قطع الغيار عادة معفاة أو بنسب منخفضة"
        },
        "8507": {
            "description": "بطاريات كهربائية",
            "tax_rate_palestine": 5,
            "tax_rate_israel": 12,
            "notes": "البطاريات خاضعة لرسوم بيئية إضافية"
        }
    },
    
    "excise_taxes": {
        "وقود_بنزين": {
            "palestine": "حسب السعر العالمي + ضريبة محلية",
            "israel": "63% excise + 17% VAT",
            "notes": "تخضع للتقلبات الشهرية"
        },
        "سجائر": {
            "palestine": "95%",
            "israel": "500% تقريباً",
            "notes": "من أعلى النسب عالمياً"
        },
        "مشروبات_غازية": {
            "palestine": "50%",
            "israel": "varies",
            "notes": "حسب نسبة السكر"
        },
        "كحول": {
            "palestine": "ممنوع / غير مطبق",
            "israel": "100%+",
            "notes": "خاضع لرقابة صارمة"
        }
    },
    
    "financial_formulas": {
        "gross_profit": "الربح الإجمالي = الإيرادات - تكلفة البضاعة المباعة",
        "net_profit": "صافي الربح = الربح الإجمالي - المصروفات التشغيلية - الضرائب",
        "vat_calculation": "VAT = المبلغ الأساسي × (نسبة الضريبة / 100)",
        "gross_up": "المبلغ الإجمالي = المبلغ الصافي / (1 - نسبة الضريبة)",
        "roi": "العائد على الاستثمار = (الربح / رأس المال) × 100"
    },
    
    "accounting_terms": {
        "دائن": "Creditor - من له حق على المنشأة",
        "مدين": "Debtor - من عليه دين للمنشأة",
        "أصول": "Assets - ممتلكات المنشأة",
        "خصوم": "Liabilities - التزامات المنشأة",
        "حقوق_ملكية": "Equity - صافي قيمة المنشأة",
        "إيرادات": "Revenue - الدخل من النشاط",
        "مصروفات": "Expenses - التكاليف التشغيلية",
        "قيود_يومية": "Journal Entries - تسجيل العمليات المحاسبية",
        "ميزان_مراجعة": "Trial Balance - للتحقق من التوازن"
    },
    
    "currency_exchange": {
        "ILS": {"name": "شيقل إسرائيلي", "symbol": "₪", "base": True},
        "USD": {"name": "دولار أمريكي", "symbol": "$", "typical_rate_vs_ILS": 3.7},
        "JOD": {"name": "دينار أردني", "symbol": "د.أ", "typical_rate_vs_ILS": 5.2},
        "EUR": {"name": "يورو", "symbol": "€", "typical_rate_vs_ILS": 4.0},
        "notes": [
            "الأسعار تتقلب يومياً - استخدم آخر سعر مسجل في النظام",
            "العملة الأساسية في النظام: ILS (شيقل)",
            "التحويل يتم عبر جدول ExchangeTransaction"
        ]
    }
}


def get_finance_knowledge():
    """الحصول على المعرفة المالية الكاملة"""
    return FINANCE_KNOWLEDGE


def calculate_palestine_income_tax(income):
    """حساب ضريبة الدخل الفلسطينية"""
    if income <= 0:
        return 0
    
    brackets = FINANCE_KNOWLEDGE['tax_palestine']['income_tax_personal']
    total_tax = 0
    remaining = income
    
    for i, bracket in enumerate(brackets):
        from_amount = bracket['من']
        to_amount = bracket['إلى']
        rate = bracket['نسبة']
        
        if to_amount is None:
            taxable = remaining
        else:
            taxable = min(remaining, to_amount - from_amount)
        
        if taxable > 0:
            total_tax += taxable * (rate / 100)
            remaining -= taxable
        
        if remaining <= 0:
            break
    
    return total_tax


def calculate_vat(amount, country='palestine'):
    """حساب ضريبة القيمة المضافة"""
    if country.lower() == 'palestine':
        rate = FINANCE_KNOWLEDGE['tax_palestine']['vat_rate']
    elif country.lower() == 'israel':
        rate = FINANCE_KNOWLEDGE['tax_israel']['vat_rate']
    else:
        rate = 0
    
    vat_amount = amount * (rate / 100)
    total_with_vat = amount + vat_amount
    
    return {
        'base_amount': amount,
        'vat_rate': rate,
        'vat_amount': vat_amount,
        'total_with_vat': total_with_vat
    }


def get_customs_info(hs_code):
    """معلومات الجمارك حسب الكود"""
    return FINANCE_KNOWLEDGE['customs_codes'].get(hs_code, None)

