"""
🎓 AI Accounting Professional - المساعد المحاسبي المحترف
════════════════════════════════════════════════════════════════════════════

الهدف: جعل المساعد الذكي محاسب محترف ومدقق مالي خبير في:
- دفتر الأستاذ العام (General Ledger)
- القيود المحاسبية المزدوجة (Double-Entry Bookkeeping)
- التحليل المالي العميق (Deep Financial Analysis)
- القوانين الضريبية (الفلسطينية والإسرائيلية)
- التدقيق المالي (Financial Audit)
- كشف الأخطاء المحاسبية (Error Detection)

المطور: نظام أزاد - Azad Intelligent Systems
التاريخ: 2025-11-01
الإصدار: Professional 1.0
"""

from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass


# ═══════════════════════════════════════════════════════════════════════════
# 📚 ACCOUNTING FUNDAMENTALS - الأساسيات المحاسبية
# ═══════════════════════════════════════════════════════════════════════════

ACCOUNTING_EQUATION = """
المعادلة المحاسبية الأساسية (Fundamental Accounting Equation):

الأصول = الخصوم + حقوق الملكية
Assets = Liabilities + Equity

🔍 التفسير:
- الأصول (Assets): كل ما تملكه المنشأة (نقد، مخزون، معدات...)
- الخصوم (Liabilities): كل ما على المنشأة (ديون، مستحقات...)
- حقوق الملكية (Equity): صافي ملكية الأصحاب

📊 مثال عملي:
شركة لديها:
- نقد: 100,000 ₪
- مخزون: 50,000 ₪
- ديون للموردين: 40,000 ₪

حقوق الملكية = (100,000 + 50,000) - 40,000 = 110,000 ₪
"""

DOUBLE_ENTRY_SYSTEM = {
    "name": "نظام القيد المزدوج",
    "english": "Double-Entry Bookkeeping",
    
    "principles": {
        "balance": {
            "rule": "كل قيد محاسبي يجب أن يحتوي على طرفين متساويين",
            "formula": "إجمالي المدين = إجمالي الدائن",
            "example": "بيع بقيمة 1000 ₪ → مدين: العملاء 1000 | دائن: المبيعات 1000"
        },
        "debit_credit": {
            "debit": "المدين (Debit) - الطرف الأيسر - يزيد الأصول والمصروفات",
            "credit": "الدائن (Credit) - الطرف الأيمن - يزيد الخصوم والإيرادات",
            "rules": {
                "أصول": "المدين يزيد | الدائن ينقص",
                "خصوم": "المدين ينقص | الدائن يزيد",
                "حقوق ملكية": "المدين ينقص | الدائن يزيد",
                "إيرادات": "المدين ينقص | الدائن يزيد",
                "مصروفات": "المدين يزيد | الدائن ينقص"
            }
        },
        "normal_balances": {
            "assets": "رصيد طبيعي مدين",
            "liabilities": "رصيد طبيعي دائن",
            "equity": "رصيد طبيعي دائن",
            "revenue": "رصيد طبيعي دائن",
            "expenses": "رصيد طبيعي مدين"
        }
    },
    
    "examples": {
        "sale_cash": {
            "description": "بيع نقدي 5000 ₪",
            "entries": [
                {"account": "1000_CASH", "debit": 5000, "credit": 0, "description": "النقدية"},
                {"account": "4000_SALES", "debit": 0, "credit": 5000, "description": "إيرادات المبيعات"}
            ],
            "explanation": "زادت النقدية (أصل) → مدين | زادت المبيعات (إيراد) → دائن"
        },
        "sale_credit": {
            "description": "بيع آجل (على الحساب) 3000 ₪",
            "entries": [
                {"account": "1100_AR", "debit": 3000, "credit": 0, "description": "ذمم العملاء"},
                {"account": "4000_SALES", "debit": 0, "credit": 3000, "description": "إيرادات المبيعات"}
            ],
            "explanation": "زادت ذمم العملاء (أصل) → مدين | زادت المبيعات (إيراد) → دائن"
        },
        "payment_received": {
            "description": "تحصيل من عميل 2000 ₪",
            "entries": [
                {"account": "1000_CASH", "debit": 2000, "credit": 0, "description": "النقدية"},
                {"account": "1100_AR", "debit": 0, "credit": 2000, "description": "ذمم العملاء"}
            ],
            "explanation": "زادت النقدية (أصل) → مدين | نقصت ذمم العملاء (أصل) → دائن"
        },
        "purchase_credit": {
            "description": "شراء بضاعة على الحساب 4000 ₪",
            "entries": [
                {"account": "1200_INVENTORY", "debit": 4000, "credit": 0, "description": "المخزون"},
                {"account": "2000_AP", "debit": 0, "credit": 4000, "description": "ذمم الموردين"}
            ],
            "explanation": "زاد المخزون (أصل) → مدين | زادت ذمم الموردين (خصوم) → دائن"
        },
        "expense_cash": {
            "description": "دفع مصروف إيجار 1500 ₪ نقداً",
            "entries": [
                {"account": "5000_RENT_EXPENSE", "debit": 1500, "credit": 0, "description": "مصروف الإيجار"},
                {"account": "1000_CASH", "debit": 0, "credit": 1500, "description": "النقدية"}
            ],
            "explanation": "زاد المصروف (مصروف) → مدين | نقصت النقدية (أصل) → دائن"
        },
        "salary_payment": {
            "description": "دفع رواتب 8000 ₪",
            "entries": [
                {"account": "5100_SALARIES", "debit": 8000, "credit": 0, "description": "مصروف الرواتب"},
                {"account": "1010_BANK", "debit": 0, "credit": 8000, "description": "البنك"}
            ],
            "explanation": "زاد مصروف الرواتب → مدين | نقص رصيد البنك → دائن"
        }
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# 🏦 CHART OF ACCOUNTS - دليل الحسابات الشامل
# ═══════════════════════════════════════════════════════════════════════════

CHART_OF_ACCOUNTS = {
    "structure": """
    نظام ترميز الحسابات (Account Coding System):
    
    1xxx = الأصول (Assets)
    2xxx = الخصوم (Liabilities)
    3xxx = حقوق الملكية (Equity)
    4xxx = الإيرادات (Revenue)
    5xxx = المصروفات (Expenses)
    
    التقسيم الفرعي:
    - xx00-xx09: حسابات رئيسية
    - xx10-xx19: حسابات فرعية - المجموعة الأولى
    - xx20-xx29: حسابات فرعية - المجموعة الثانية
    - وهكذا...
    """,
    
    "accounts": {
        # ═════ 1xxx: الأصول (Assets) ═════
        "1000_CASH": {
            "name": "النقدية (الصندوق)",
            "english": "Cash on Hand",
            "type": "ASSET",
            "category": "Current Asset - أصل متداول",
            "normal_balance": "DEBIT",
            "description": "النقدية الموجودة في الصندوق",
            "increases_with": "DEBIT",
            "decreases_with": "CREDIT",
            "examples": [
                "استلام نقدية من عميل",
                "دفع نقدي لمورد",
                "مبيعات نقدية"
            ]
        },
        
        "1010_BANK": {
            "name": "البنك",
            "english": "Bank Account",
            "type": "ASSET",
            "category": "Current Asset",
            "normal_balance": "DEBIT",
            "description": "الحساب الجاري في البنك",
            "increases_with": "DEBIT",
            "decreases_with": "CREDIT"
        },
        
        "1020_CARD_CLEARING": {
            "name": "مقاصة بطاقات الائتمان",
            "english": "Credit Card Clearing",
            "type": "ASSET",
            "category": "Current Asset",
            "normal_balance": "DEBIT",
            "description": "مبالغ بطاقات الائتمان في طريقها للتحصيل",
            "clearing_period": "2-3 أيام عمل"
        },
        
        "1100_AR": {
            "name": "ذمم العملاء (المدينون)",
            "english": "Accounts Receivable",
            "type": "ASSET",
            "category": "Current Asset",
            "normal_balance": "DEBIT",
            "description": "المبالغ المستحقة من العملاء",
            "calculation": "المبيعات الآجلة - المقبوضات من العملاء",
            "increases_with": "DEBIT - عند البيع الآجل",
            "decreases_with": "CREDIT - عند التحصيل من العميل",
            "important_notes": [
                "رصيد مدين = العميل مدين لنا (عليه يدفع)",
                "رصيد دائن = العميل دائن (له رصيد عندنا - دفع زيادة)",
                "يجب متابعة أعمار الديون (Aging)"
            ]
        },
        
        "1150_CHEQUES_RECEIVABLE": {
            "name": "شيكات تحت التحصيل",
            "english": "Checks Receivable",
            "type": "ASSET",
            "category": "Current Asset",
            "normal_balance": "DEBIT",
            "description": "شيكات مستلمة لم يتم صرفها بعد",
            "lifecycle": {
                "received": "استلام الشيك → مدين CHEQUES_RECEIVABLE | دائن AR",
                "cashed": "صرف الشيك → مدين BANK | دائن CHEQUES_RECEIVABLE",
                "returned": "إرجاع الشيك → مدين AR | دائن CHEQUES_RECEIVABLE"
            }
        },
        
        "1200_INVENTORY": {
            "name": "المخزون - رئيسي",
            "english": "Main Inventory",
            "type": "ASSET",
            "category": "Current Asset",
            "normal_balance": "DEBIT",
            "description": "بضاعة جاهزة للبيع",
            "valuation_methods": ["FIFO", "LIFO", "Weighted Average"],
            "calculation": "مخزون أول المدة + المشتريات - تكلفة البضاعة المباعة"
        },
        
        "1205_INV_EXCHANGE": {
            "name": "المخزون - تبادل (Exchange)",
            "english": "Exchange Inventory",
            "type": "ASSET",
            "category": "Current Asset",
            "normal_balance": "DEBIT",
            "description": "مخزون مستودعات التبادل (بضاعة موردين)"
        },
        
        "1210_INV_PARTNER": {
            "name": "المخزون - شركاء",
            "english": "Partner Inventory",
            "type": "ASSET",
            "category": "Current Asset",
            "normal_balance": "DEBIT",
            "description": "مخزون خاص بالشركاء"
        },
        
        "1300_PREPAID_EXPENSES": {
            "name": "مصروفات مدفوعة مقدماً",
            "english": "Prepaid Expenses",
            "type": "ASSET",
            "category": "Current Asset",
            "normal_balance": "DEBIT",
            "description": "مصروفات دُفعت مقدماً (إيجار سنوي، تأمينات...)",
            "examples": ["إيجار مدفوع لمدة سنة", "تأمينات مدفوعة مقدماً"]
        },
        
        "1500_EQUIPMENT": {
            "name": "المعدات",
            "english": "Equipment",
            "type": "ASSET",
            "category": "Fixed Asset - أصل ثابت",
            "normal_balance": "DEBIT",
            "description": "معدات وأدوات العمل",
            "depreciation": "يخضع للإهلاك"
        },
        
        "1510_VEHICLES": {
            "name": "السيارات والمركبات",
            "english": "Vehicles",
            "type": "ASSET",
            "category": "Fixed Asset",
            "normal_balance": "DEBIT",
            "depreciation_rate": "20% سنوياً (تقريباً)"
        },
        
        # ═════ 2xxx: الخصوم (Liabilities) ═════
        "2000_AP": {
            "name": "ذمم الموردين (الدائنون)",
            "english": "Accounts Payable",
            "type": "LIABILITY",
            "category": "Current Liability - خصم متداول",
            "normal_balance": "CREDIT",
            "description": "المبالغ المستحقة للموردين",
            "calculation": "المشتريات الآجلة - المدفوعات للموردين",
            "increases_with": "CREDIT - عند الشراء الآجل",
            "decreases_with": "DEBIT - عند الدفع للمورد",
            "important_notes": [
                "رصيد دائن = مورد دائن (له علينا - يجب أن ندفع)",
                "رصيد مدين = مورد مدين (دفعنا له زيادة)"
            ]
        },
        
        "2100_VAT_PAYABLE": {
            "name": "ضريبة القيمة المضافة - مستحقة الدفع",
            "english": "VAT Payable",
            "type": "LIABILITY",
            "category": "Current Liability",
            "normal_balance": "CREDIT",
            "description": "ضريبة القيمة المضافة المحصلة من العملاء والواجب توريدها للحكومة",
            "calculation": "ضريبة المبيعات - ضريبة المشتريات",
            "payment_schedule": "شهري أو ربع سنوي حسب القانون"
        },
        
        "2150_CHEQUES_PAYABLE": {
            "name": "شيكات تحت الدفع",
            "english": "Checks Payable",
            "type": "LIABILITY",
            "category": "Current Liability",
            "normal_balance": "CREDIT",
            "description": "شيكات صادرة لم يتم صرفها بعد",
            "lifecycle": {
                "issued": "إصدار الشيك → مدين AP | دائن CHEQUES_PAYABLE",
                "cashed": "صرف الشيك → مدين CHEQUES_PAYABLE | دائن BANK",
                "returned": "إرجاع الشيك → مدين CHEQUES_PAYABLE | دائن AP"
            }
        },
        
        "2200_INCOME_TAX_PAYABLE": {
            "name": "ضريبة الدخل المستحقة",
            "english": "Income Tax Payable",
            "type": "LIABILITY",
            "category": "Current Liability",
            "normal_balance": "CREDIT",
            "description": "ضريبة الدخل المحسوبة والواجب دفعها",
            "rates": {
                "palestine_corporate": "15%",
                "israel_corporate": "23%"
            }
        },
        
        "2300_SALARIES_PAYABLE": {
            "name": "رواتب مستحقة",
            "english": "Salaries Payable",
            "type": "LIABILITY",
            "category": "Current Liability",
            "normal_balance": "CREDIT",
            "description": "رواتب الموظفين المستحقة لم تُدفع بعد"
        },
        
        "2500_LONG_TERM_LOANS": {
            "name": "قروض طويلة الأجل",
            "english": "Long-term Loans",
            "type": "LIABILITY",
            "category": "Long-term Liability - خصم طويل الأجل",
            "normal_balance": "CREDIT",
            "description": "قروض مستحقة بعد أكثر من سنة"
        },
        
        # ═════ 3xxx: حقوق الملكية (Equity) ═════
        "3000_CAPITAL": {
            "name": "رأس المال",
            "english": "Owner's Capital",
            "type": "EQUITY",
            "category": "Owner's Equity",
            "normal_balance": "CREDIT",
            "description": "رأس المال المستثمر من قبل المالك",
            "increases_with": "CREDIT - زيادة رأس المال",
            "decreases_with": "DEBIT - سحوبات المالك"
        },
        
        "3100_RETAINED_EARNINGS": {
            "name": "الأرباح المحتجزة",
            "english": "Retained Earnings",
            "type": "EQUITY",
            "category": "Owner's Equity",
            "normal_balance": "CREDIT",
            "description": "الأرباح المتراكمة التي لم يتم توزيعها",
            "calculation": "أرباح السنوات السابقة + صافي ربح السنة الحالية - التوزيعات"
        },
        
        "3200_DRAWINGS": {
            "name": "المسحوبات الشخصية",
            "english": "Owner's Drawings",
            "type": "EQUITY",
            "category": "Owner's Equity",
            "normal_balance": "DEBIT",
            "description": "المبالغ المسحوبة من قبل المالك للاستخدام الشخصي",
            "note": "تُطرح من رأس المال"
        },
        
        # ═════ 4xxx: الإيرادات (Revenue) ═════
        "4000_SALES": {
            "name": "إيرادات المبيعات",
            "english": "Sales Revenue",
            "type": "REVENUE",
            "category": "Operating Revenue",
            "normal_balance": "CREDIT",
            "description": "الإيرادات من بيع البضاعة",
            "increases_with": "CREDIT - عند البيع",
            "decreases_with": "DEBIT - مرتجعات ومسموحات"
        },
        
        "4100_SERVICE_REVENUE": {
            "name": "إيرادات الخدمات",
            "english": "Service Revenue",
            "type": "REVENUE",
            "category": "Operating Revenue",
            "normal_balance": "CREDIT",
            "description": "الإيرادات من تقديم خدمات الصيانة"
        },
        
        "4200_SALES_RETURNS": {
            "name": "مرتجعات المبيعات",
            "english": "Sales Returns & Allowances",
            "type": "REVENUE",
            "category": "Contra Revenue - إيراد عكسي",
            "normal_balance": "DEBIT",
            "description": "تخفيضات على المبيعات بسبب المرتجعات",
            "note": "يُطرح من إجمالي المبيعات"
        },
        
        "4300_DISCOUNTS_GIVEN": {
            "name": "الخصومات الممنوحة",
            "english": "Discounts Given",
            "type": "REVENUE",
            "category": "Contra Revenue",
            "normal_balance": "DEBIT",
            "description": "الخصومات المعطاة للعملاء"
        },
        
        "4900_OTHER_INCOME": {
            "name": "إيرادات أخرى",
            "english": "Other Income",
            "type": "REVENUE",
            "category": "Non-operating Revenue",
            "normal_balance": "CREDIT",
            "description": "إيرادات متنوعة (فوائد بنكية، أرباح عملات...)"
        },
        
        # ═════ 5xxx: المصروفات (Expenses) ═════
        "5000_COGS": {
            "name": "تكلفة البضاعة المباعة",
            "english": "Cost of Goods Sold (COGS)",
            "type": "EXPENSE",
            "category": "Direct Expense",
            "normal_balance": "DEBIT",
            "description": "التكلفة المباشرة للبضاعة المباعة",
            "calculation": "مخزون أول المدة + المشتريات - مخزون آخر المدة",
            "importance": "تُطرح من المبيعات لحساب إجمالي الربح"
        },
        
        "5105_COGS_EXCHANGE": {
            "name": "تكلفة البضاعة المباعة - تبادل",
            "english": "COGS - Exchange",
            "type": "EXPENSE",
            "category": "Direct Expense",
            "normal_balance": "DEBIT",
            "description": "تكلفة بضاعة التبادل المباعة"
        },
        
        "5200_SALARIES": {
            "name": "الرواتب والأجور",
            "english": "Salaries & Wages",
            "type": "EXPENSE",
            "category": "Operating Expense",
            "normal_balance": "DEBIT",
            "description": "رواتب الموظفين"
        },
        
        "5300_RENT": {
            "name": "الإيجار",
            "english": "Rent Expense",
            "type": "EXPENSE",
            "category": "Operating Expense",
            "normal_balance": "DEBIT",
            "description": "إيجار المقر"
        },
        
        "5400_UTILITIES": {
            "name": "المرافق (كهرباء، ماء، هاتف)",
            "english": "Utilities Expense",
            "type": "EXPENSE",
            "category": "Operating Expense",
            "normal_balance": "DEBIT",
            "description": "فواتير الخدمات"
        },
        
        "5500_DEPRECIATION": {
            "name": "الإهلاك",
            "english": "Depreciation Expense",
            "type": "EXPENSE",
            "category": "Operating Expense",
            "normal_balance": "DEBIT",
            "description": "إهلاك الأصول الثابتة",
            "note": "قيد تسوية - لا يتطلب دفع نقدي"
        },
        
        "5600_ADVERTISING": {
            "name": "الإعلان والتسويق",
            "english": "Advertising & Marketing",
            "type": "EXPENSE",
            "category": "Operating Expense",
            "normal_balance": "DEBIT",
            "description": "مصاريف الترويج"
        },
        
        "5700_INSURANCE": {
            "name": "التأمين",
            "english": "Insurance Expense",
            "type": "EXPENSE",
            "category": "Operating Expense",
            "normal_balance": "DEBIT",
            "description": "أقساط التأمين"
        },
        
        "5800_BAD_DEBT": {
            "name": "الديون المعدومة",
            "english": "Bad Debt Expense",
            "type": "EXPENSE",
            "category": "Operating Expense",
            "normal_balance": "DEBIT",
            "description": "ديون لا يمكن تحصيلها"
        },
        
        "5900_BANK_FEES": {
            "name": "رسوم بنكية",
            "english": "Bank Fees & Charges",
            "type": "EXPENSE",
            "category": "Operating Expense",
            "normal_balance": "DEBIT",
            "description": "عمولات ورسوم البنك"
        },
        
        "5950_MISC_EXPENSES": {
            "name": "مصروفات متنوعة",
            "english": "Miscellaneous Expenses",
            "type": "EXPENSE",
            "category": "Operating Expense",
            "normal_balance": "DEBIT",
            "description": "مصروفات أخرى غير مصنفة"
        }
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# 💰 BALANCE CALCULATION - حسابات الأرصدة
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class BalanceFormula:
    """صيغة حساب الرصيد"""
    entity: str
    formula: str
    components: List[str]
    positive_meaning: str
    negative_meaning: str
    examples: List[Dict[str, Any]]

BALANCE_FORMULAS = {
    "customer": BalanceFormula(
        entity="Customer - العميل",
        formula="الرصيد = (المبيعات + الفواتير + الخدمات) - (الدفعات الواردة)",
        components=[
            "المبيعات (Sales)",
            "الفواتير (Invoices)",
            "الخدمات (Services)",
            "الدفعات الواردة IN (Incoming Payments)",
            "الدفعات الصادرة OUT (Outgoing Payments - نادرة)"
        ],
        negative_meaning="رصيد سالب (-) = العميل مدين لنا (عليه يدفع) - يُعرض بالأحمر 🔴",
        positive_meaning="رصيد موجب (+) = العميل دائن (له رصيد عندنا - دفع زيادة) - يُعرض بالأخضر 🟢",
        examples=[
            {
                "scenario": "عميل اشترى ولم يدفع",
                "transactions": ["مبيعات: 1000 ₪"],
                "balance": -1000,
                "meaning": "العميل عليه 1000 ₪",
                "color": "أحمر"
            },
            {
                "scenario": "عميل دفع جزئياً",
                "transactions": ["مبيعات: 1000 ₪", "دفع IN: 600 ₪"],
                "balance": -400,
                "meaning": "العميل لسه عليه 400 ₪",
                "color": "أحمر"
            },
            {
                "scenario": "عميل دفع بالكامل",
                "transactions": ["مبيعات: 1000 ₪", "دفع IN: 1000 ₪"],
                "balance": 0,
                "meaning": "الحساب مسدد بالكامل",
                "color": "أسود"
            },
            {
                "scenario": "عميل دفع زيادة",
                "transactions": ["مبيعات: 1000 ₪", "دفع IN: 1200 ₪"],
                "balance": 200,
                "meaning": "للعميل رصيد 200 ₪ عندنا",
                "color": "أخضر"
            }
        ]
    ),
    
    "supplier": BalanceFormula(
        entity="Supplier - المورد",
        formula="الرصيد = (المشتريات + الشحنات + الفواتير) - (الدفعات الصادرة)",
        components=[
            "المشتريات (Purchases)",
            "الشحنات (Shipments)",
            "الفواتير (Invoices)",
            "الدفعات الصادرة OUT (Outgoing Payments)",
            "الدفعات الواردة IN (Incoming Payments - نادرة)"
        ],
        negative_meaning="رصيد سالب (-) = المورد مدين لنا (علينا ندفع له) - يُعرض بالأحمر 🔴",
        positive_meaning="رصيد موجب (+) = المورد دائن (دفعنا له زيادة) - يُعرض بالأخضر 🟢",
        examples=[
            {
                "scenario": "شراء من مورد بدون دفع",
                "transactions": ["شحنة: 5000 ₪"],
                "balance": -5000,
                "meaning": "علينا ندفع للمورد 5000 ₪",
                "color": "أحمر"
            },
            {
                "scenario": "دفع جزئي للمورد",
                "transactions": ["شحنة: 5000 ₪", "دفع OUT: 3000 ₪"],
                "balance": -2000,
                "meaning": "لسه علينا 2000 ₪ للمورد",
                "color": "أحمر"
            },
            {
                "scenario": "دفع كامل للمورد",
                "transactions": ["شحنة: 5000 ₪", "دفع OUT: 5000 ₪"],
                "balance": 0,
                "meaning": "الحساب مسدد بالكامل",
                "color": "أسود"
            }
        ]
    ),
    
    "partner": BalanceFormula(
        entity="Partner - الشريك",
        formula="الرصيد = (حصص المبيعات + الأرباح) - (التسويات)",
        components=[
            "حصص المبيعات (Partner Share)",
            "الأرباح المستحقة (Due Profits)",
            "التسويات (Settlements)"
        ],
        negative_meaning="رصيد سالب (-) = الشريك مدين (نادر جداً)",
        positive_meaning="رصيد موجب (+) = للشريك رصيد مستحق (له علينا) - يُعرض بالأخضر 🟢",
        examples=[
            {
                "scenario": "شريك لديه مبيعات ولم يتم التسوية",
                "transactions": ["حصة من مبيعات: 2000 ₪"],
                "balance": 2000,
                "meaning": "للشريك 2000 ₪ مستحقة",
                "color": "أخضر"
            },
            {
                "scenario": "تسوية جزئية للشريك",
                "transactions": ["حصة من مبيعات: 2000 ₪", "تسوية: 1000 ₪"],
                "balance": 1000,
                "meaning": "لسه للشريك 1000 ₪",
                "color": "أخضر"
            }
        ]
    )
}


# ═══════════════════════════════════════════════════════════════════════════
# 📊 FINANCIAL STATEMENTS - القوائم المالية
# ═══════════════════════════════════════════════════════════════════════════

FINANCIAL_STATEMENTS = {
    "income_statement": {
        "name_ar": "قائمة الدخل (قائمة الأرباح والخسائر)",
        "name_en": "Income Statement (Profit & Loss)",
        "purpose": "قياس الأداء المالي خلال فترة زمنية محددة",
        "formula": "صافي الربح = الإيرادات - المصروفات",
        
        "structure": {
            "1_revenue": {
                "name": "الإيرادات (Revenue)",
                "items": [
                    "مبيعات البضاعة (Sales)",
                    "إيرادات الخدمات (Service Revenue)",
                    "- مرتجعات المبيعات (Sales Returns)",
                    "- الخصومات الممنوحة (Discounts Given)",
                    "= صافي المبيعات (Net Sales)"
                ]
            },
            "2_cogs": {
                "name": "تكلفة البضاعة المباعة (COGS)",
                "calculation": "مخزون أول المدة + المشتريات - مخزون آخر المدة"
            },
            "3_gross_profit": {
                "name": "إجمالي الربح (Gross Profit)",
                "formula": "صافي المبيعات - تكلفة البضاعة المباعة",
                "importance": "مؤشر على كفاءة التسعير والشراء"
            },
            "4_operating_expenses": {
                "name": "المصروفات التشغيلية (Operating Expenses)",
                "items": [
                    "الرواتب (Salaries)",
                    "الإيجار (Rent)",
                    "المرافق (Utilities)",
                    "الإعلان (Advertising)",
                    "الإهلاك (Depreciation)",
                    "التأمين (Insurance)",
                    "مصروفات أخرى (Other Expenses)"
                ]
            },
            "5_operating_profit": {
                "name": "الربح التشغيلي (Operating Profit/EBIT)",
                "formula": "إجمالي الربح - المصروفات التشغيلية"
            },
            "6_other_income_expenses": {
                "name": "إيرادات ومصروفات أخرى",
                "items": [
                    "+ إيرادات أخرى (Other Income)",
                    "- فوائد القروض (Interest Expense)"
                ]
            },
            "7_net_profit_before_tax": {
                "name": "صافي الربح قبل الضريبة (Profit Before Tax)",
                "formula": "الربح التشغيلي + الإيرادات الأخرى - المصروفات الأخرى"
            },
            "8_income_tax": {
                "name": "ضريبة الدخل (Income Tax)",
                "rates": {
                    "palestine": "15% للشركات",
                    "israel": "23% للشركات"
                }
            },
            "9_net_profit": {
                "name": "صافي الربح (Net Profit / Net Income)",
                "formula": "الربح قبل الضريبة - ضريبة الدخل",
                "importance": "المؤشر النهائي للربحية"
            }
        },
        
        "example": {
            "period": "للسنة المنتهية في 31/12/2024",
            "data": {
                "sales": 500000,
                "sales_returns": -5000,
                "net_sales": 495000,
                "cogs": -300000,
                "gross_profit": 195000,
                "salaries": -50000,
                "rent": -24000,
                "utilities": -6000,
                "advertising": -10000,
                "depreciation": -15000,
                "other_operating": -10000,
                "operating_profit": 80000,
                "other_income": 5000,
                "interest_expense": -3000,
                "profit_before_tax": 82000,
                "income_tax_15": -12300,
                "net_profit": 69700
            }
        }
    },
    
    "balance_sheet": {
        "name_ar": "الميزانية العمومية (قائمة المركز المالي)",
        "name_en": "Balance Sheet (Statement of Financial Position)",
        "purpose": "إظهار المركز المالي للمنشأة في تاريخ معين",
        "equation": "الأصول = الخصوم + حقوق الملكية",
        
        "structure": {
            "assets": {
                "name": "الأصول (Assets)",
                "current_assets": {
                    "name": "أصول متداولة (Current Assets)",
                    "definition": "أصول ستتحول لنقد خلال سنة",
                    "items": [
                        "النقدية (Cash)",
                        "البنك (Bank)",
                        "ذمم العملاء (AR)",
                        "المخزون (Inventory)",
                        "مصروفات مدفوعة مقدماً (Prepaid)"
                    ]
                },
                "fixed_assets": {
                    "name": "أصول ثابتة (Fixed Assets)",
                    "definition": "أصول طويلة الأجل",
                    "items": [
                        "المعدات (Equipment)",
                        "السيارات (Vehicles)",
                        "- مجمع الإهلاك (Accumulated Depreciation)"
                    ]
                }
            },
            "liabilities": {
                "name": "الخصوم (Liabilities)",
                "current_liabilities": {
                    "name": "خصوم متداولة (Current Liabilities)",
                    "definition": "التزامات مستحقة خلال سنة",
                    "items": [
                        "ذمم الموردين (AP)",
                        "ضريبة القيمة المضافة (VAT Payable)",
                        "رواتب مستحقة (Salaries Payable)"
                    ]
                },
                "long_term_liabilities": {
                    "name": "خصوم طويلة الأجل (Long-term Liabilities)",
                    "items": [
                        "قروض طويلة الأجل (Long-term Loans)"
                    ]
                }
            },
            "equity": {
                "name": "حقوق الملكية (Owner's Equity)",
                "items": [
                    "رأس المال (Capital)",
                    "الأرباح المحتجزة (Retained Earnings)",
                    "- المسحوبات (Drawings)"
                ]
            }
        }
    },
    
    "cash_flow_statement": {
        "name_ar": "قائمة التدفقات النقدية",
        "name_en": "Cash Flow Statement",
        "purpose": "تتبع حركة النقد (الداخل والخارج)",
        
        "sections": {
            "operating": {
                "name": "التدفقات من الأنشطة التشغيلية (Operating Activities)",
                "items": [
                    "+ النقد المحصل من العملاء",
                    "- النقد المدفوع للموردين",
                    "- النقد المدفوع كرواتب",
                    "- النقد المدفوع كمصروفات"
                ]
            },
            "investing": {
                "name": "التدفقات من الأنشطة الاستثمارية (Investing Activities)",
                "items": [
                    "- شراء معدات",
                    "+ بيع أصول ثابتة"
                ]
            },
            "financing": {
                "name": "التدفقات من الأنشطة التمويلية (Financing Activities)",
                "items": [
                    "+ قروض جديدة",
                    "- سداد قروض",
                    "+ زيادة رأس المال",
                    "- المسحوبات الشخصية"
                ]
            }
        }
    },
    
    "trial_balance": {
        "name_ar": "ميزان المراجعة",
        "name_en": "Trial Balance",
        "purpose": "التحقق من توازن القيود المحاسبية",
        "rule": "إجمالي المدين = إجمالي الدائن",
        "columns": [
            "رمز الحساب (Account Code)",
            "اسم الحساب (Account Name)",
            "المدين (Debit)",
            "الدائن (Credit)"
        ],
        "note": "إذا لم يتوازن ميزان المراجعة، هناك خطأ في القيود المحاسبية"
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 Export للمحرك الرئيسي
# ═══════════════════════════════════════════════════════════════════════════

def get_professional_accounting_knowledge() -> Dict[str, Any]:
    """
    الحصول على المعرفة المحاسبية الاحترافية الكاملة
    
    Returns:
        قاعدة معرفة شاملة للمحاسبة الاحترافية
    """
    return {
        "fundamentals": {
            "accounting_equation": ACCOUNTING_EQUATION,
            "double_entry": DOUBLE_ENTRY_SYSTEM
        },
        "chart_of_accounts": CHART_OF_ACCOUNTS,
        "balance_formulas": {
            "customer": BALANCE_FORMULAS["customer"].__dict__,
            "supplier": BALANCE_FORMULAS["supplier"].__dict__,
            "partner": BALANCE_FORMULAS["partner"].__dict__
        },
        "financial_statements": FINANCIAL_STATEMENTS,
        
        "capabilities": [
            "فهم عميق للمعادلة المحاسبية الأساسية",
            "إتقان نظام القيد المزدوج",
            "معرفة شاملة بدليل الحسابات (87+ حساب)",
            "حساب أرصدة العملاء والموردين والشركاء بدقة",
            "قراءة وتحليل القوائم المالية الأربع",
            "كشف الأخطاء المحاسبية",
            "تفسير كل رقم في النظام بالتفصيل"
        ]
    }


__all__ = [
    'get_professional_accounting_knowledge',
    'ACCOUNTING_EQUATION',
    'DOUBLE_ENTRY_SYSTEM',
    'CHART_OF_ACCOUNTS',
    'BALANCE_FORMULAS',
    'FINANCIAL_STATEMENTS'
]

