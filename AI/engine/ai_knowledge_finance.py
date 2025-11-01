

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


# ═══════════════════════════════════════════════════════════════════════════
# 🎓 ADVANCED TAX KNOWLEDGE - المعرفة الضريبية المتقدمة
# ═══════════════════════════════════════════════════════════════════════════

TAX_KNOWLEDGE_PALESTINE = {
    "country": "فلسطين - Palestine",
    "system": "نظام ضريبي حديث يتبع المعايير الدولية",
    
    "vat": {
        "name": "ضريبة القيمة المضافة - VAT",
        "rate": 16,
        "law": "قانون رقم 6 لسنة 2005 المعدل بالقرار رقم 11 لسنة 2010",
        "authority": "دائرة ضريبة القيمة المضافة - وزارة المالية",
        
        "registration": {
            "mandatory": "إلزامي للمنشآت التي يتجاوز دخلها السنوي 75,000 ₪",
            "voluntary": "اختياري للمنشآت بين 50,000-75,000 ₪",
            "exempt": "معفى إذا كان الدخل أقل من 50,000 ₪"
        },
        
        "calculation": {
            "inclusive": "إذا كان السعر شامل الضريبة: الصافي = الإجمالي ÷ 1.16",
            "exclusive": "إذا كان السعر بدون ضريبة: الضريبة = الصافي × 0.16",
            "formula": "الضريبة = المبلغ الخاضع للضريبة × 16%",
            "examples": [
                {"price_exclusive": 1000, "vat": 160, "total": 1160},
                {"price_inclusive": 1160, "net": 1000, "vat": 160}
            ]
        },
        
        "exempt_items": [
            "الخبز الطازج",
            "الحليب الطازج",
            "البيض",
            "الأدوية الأساسية المسجلة",
            "الكتب والمطبوعات التعليمية",
            "الخدمات المالية (بنوك وتأمين)",
            "خدمات التعليم",
            "الخدمات الصحية الأساسية"
        ],
        
        "zero_rated": [
            "الصادرات (Exports) - 0%",
            "بيع سلع للمناطق الحرة - 0%"
        ],
        
        "filing": {
            "frequency": "شهري للمنشآت الكبيرة، ربع سنوي للصغيرة",
            "deadline": "اليوم الـ15 من الشهر التالي",
            "form": "نموذج VAT-101",
            "penalty": "غرامة 2% شهرياً على التأخير (حد أقصى 50%)"
        },
        
        "input_output": {
            "output_vat": "ضريبة المخرجات = الضريبة المحصلة من المبيعات",
            "input_vat": "ضريبة المدخلات = الضريبة المدفوعة على المشتريات",
            "net_vat": "الضريبة المستحقة = ضريبة المخرجات - ضريبة المدخلات",
            "refund": "إذا كانت المدخلات > المخرجات → يحق استرداد الفرق"
        }
    },
    
    "income_tax": {
        "name": "ضريبة الدخل",
        "law": "قانون ضريبة الدخل رقم 8 لسنة 2011",
        "authority": "دائرة ضريبة الدخل",
        
        "personal": {
            "name": "ضريبة الدخل على الأشخاص الطبيعيين",
            "brackets": [
                {"from": 0, "to": 75000, "rate": 5, "description": "شريحة أولى"},
                {"from": 75001, "to": 150000, "rate": 10, "description": "شريحة ثانية"},
                {"from": 150001, "to": 300000, "rate": 15, "description": "شريحة ثالثة"},
                {"from": 300001, "to": None, "rate": 20, "description": "شريحة رابعة"}
            ],
            "exemptions": {
                "personal": 36000,
                "married": 48000,
                "per_child": 6000,
                "max_children": 5
            },
            "example": {
                "salary": 120000,
                "personal_exemption": 36000,
                "married_exemption": 12000,
                "children_exemption": 12000,
                "taxable": 60000,
                "tax": 5250,
                "calculation": "0-75000: 5% × 60000 = 3000 ₪"
            }
        },
        
        "corporate": {
            "name": "ضريبة الدخل على الشركات",
            "rate": 15,
            "description": "نسبة موحدة 15% على صافي الربح",
            "calculation": "الضريبة = صافي الربح × 15%",
            "deductions": [
                "المصروفات التشغيلية الفعلية",
                "الإهلاك حسب الجداول المعتمدة",
                "الديون المعدومة المثبتة",
                "التبرعات (حد أقصى 10% من الدخل)"
            ],
            "non_deductible": [
                "المصروفات الشخصية للمالك",
                "الغرامات والعقوبات",
                "الضرائب المدفوعة",
                "المبالغ المدفوعة للمساهمين كتوزيعات"
            ],
            "example": {
                "revenue": 500000,
                "expenses": 350000,
                "net_profit": 150000,
                "tax_15": 22500
            }
        },
        
        "withholding_tax": {
            "name": "ضريبة الاستقطاع",
            "description": "تُقتطع من المصدر عند الدفع",
            "rates": {
                "professionals": 5,
                "contractors": 2,
                "rent": 5,
                "dividends": 10,
                "interest": 10
            },
            "filing": "شهري - نموذج 9"
        }
    },
    
    "customs_duties": {
        "name": "الرسوم الجمركية",
        "authority": "الجمارك الفلسطينية",
        "description": "تُفرض على البضائع المستوردة",
        
        "rates": {
            "raw_materials": "0-5%",
            "semi_finished": "5-12%",
            "finished_goods": "12-20%",
            "luxury_items": "30-50%"
        },
        
        "calculation": {
            "base": "القيمة CIF (التكلفة + التأمين + الشحن)",
            "formula": "الرسوم = القيمة CIF × نسبة الرسوم",
            "total_cost": "التكلفة الإجمالية = CIF + الرسوم + VAT"
        },
        
        "automotive": {
            "passenger_cars": {
                "description": "سيارات الركاب (HS 8703)",
                "factors": ["سعة المحرك", "نوع الوقود", "سنة الصنع"],
                "rates": "متغيرة - تخضع لاتفاقيات باريس الاقتصادية"
            },
            "commercial_vehicles": {
                "description": "المركبات التجارية (HS 8704)",
                "rate": "رسوم مخفضة مقارنة بسيارات الركاب"
            }
        }
    },
    
    "property_tax": {
        "name": "ضريبة الأملاك",
        "description": "تُفرض على العقارات",
        "rate": "10-20% من القيمة الإيجارية السنوية"
    },
    
    "penalties": {
        "late_filing": "غرامة 500-2000 ₪ حسب نوع الضريبة",
        "late_payment": "غرامة 2% شهرياً (حد أقصى 50%)",
        "tax_evasion": "غرامة تصل إلى 3 أضعاف الضريبة + السجن"
    }
}

TAX_KNOWLEDGE_ISRAEL = {
    "country": "إسرائيل - Israel - ישראל",
    "system": "نظام ضريبي متطور ومعقد",
    
    "vat": {
        "name": "מע\"מ - VAT - ضريبة القيمة المضافة",
        "rate": 17,
        "law": "חוק מס ערך מוסף",
        "authority": "רשות המסים - سلطة الضرائب",
        
        "registration": {
            "threshold": "إلزامي عند تجاوز 101,584 ₪ سنوياً (2024)",
            "licensed": "معفى لأصحاب الرخص (עוסק פטור)"
        },
        
        "calculation": {
            "inclusive": "السعر شامل: الصافي = الإجمالي ÷ 1.17",
            "exclusive": "السعر بدون: الضريبة = الصافي × 0.17",
            "examples": [
                {"price_exclusive": 1000, "vat": 170, "total": 1170},
                {"price_inclusive": 1170, "net": 1000, "vat": 170}
            ]
        },
        
        "exempt_items": [
            "الفواكه والخضروات الطازجة",
            "معظم المواد الغذائية الأساسية",
            "الخدمات المالية",
            "الخدمات الصحية",
            "التعليم"
        ],
        
        "zero_rated": [
            "الصادرات - 0%",
            "السياحة الوافدة - 0%",
            "الخدمات للسياح - 0%"
        ],
        
        "filing": {
            "frequency_small": "كل شهرين (עוסק קטן)",
            "frequency_large": "شهري",
            "deadline": "اليوم الـ15 من الشهر التالي",
            "online": "إلزامي عبر האינטרנט"
        }
    },
    
    "income_tax": {
        "name": "מס הכנסה - ضريبة الدخل",
        "authority": "רשות המסים",
        
        "personal": {
            "name": "ضريبة الدخل الشخصية",
            "progressive": "تصاعدية من 10% حتى 50%",
            "brackets_2024": [
                {"from": 0, "to": 83040, "rate": 10},
                {"from": 83041, "to": 119280, "rate": 14},
                {"from": 119281, "to": 191560, "rate": 20},
                {"from": 191561, "to": 266480, "rate": 31},
                {"from": 266481, "to": 560280, "rate": 35},
                {"from": 560281, "to": 721560, "rate": 47},
                {"from": 721561, "to": None, "rate": 50}
            ],
            "credits": {
                "basic": 2820,
                "married": 2820,
                "per_child": 1680
            }
        },
        
        "corporate": {
            "name": "ضريبة الشركات - מס חברות",
            "rate": 23,
            "description": "نسبة موحدة 23% على الأرباح",
            "small_business": "شركات صغيرة قد تخضع لـ 17% على الـ 500,000 ₪ الأولى"
        },
        
        "capital_gains": {
            "name": "ضريبة أرباح رأس المال - מס רווח הון",
            "rate": 25,
            "description": "على الأرباح من بيع الأصول"
        },
        
        "national_insurance": {
            "name": "التأمين الوطني - ביטוח לאומי",
            "employee": "7% تقريباً",
            "employer": "7.6% تقريباً",
            "self_employed": "17.83% تقريباً"
        }
    },
    
    "purchase_tax": {
        "name": "מס קנייה - ضريبة الشراء",
        "vehicles": {
            "rate": "83-100% حسب نوع السيارة",
            "electric": "خصم كبير للسيارات الكهربائية",
            "hybrid": "خصم متوسط للسيارات الهجينة"
        },
        "real_estate": {
            "rate": "0-10% حسب قيمة العقار وعدد الشقق"
        }
    },
    
    "land_appreciation_tax": {
        "name": "מס שבח - ضريبة تحسين الأراضي",
        "rate": "25% على أرباح بيع العقارات",
        "exemptions": "معفى على الشقة الأولى في حدود معينة"
    }
}


def get_tax_knowledge_detailed():
    """الحصول على المعرفة الضريبية الشاملة"""
    return {
        "palestine": TAX_KNOWLEDGE_PALESTINE,
        "israel": TAX_KNOWLEDGE_ISRAEL,
        
        "comparison": {
            "vat": {
                "palestine": "16%",
                "israel": "17%",
                "difference": "فرق بسيط 1%"
            },
            "corporate_tax": {
                "palestine": "15%",
                "israel": "23%",
                "difference": "فلسطين أقل بـ 8%"
            },
            "personal_tax": {
                "palestine": "تصاعدية 5-20%",
                "israel": "تصاعدية 10-50%",
                "difference": "إسرائيل أعلى بكثير"
            }
        },
        
        "tax_planning_tips": [
            "الاستفادة من الإعفاءات القانونية",
            "توثيق جميع المصروفات القابلة للخصم",
            "الالتزام بالمواعيد النهائية لتجنب الغرامات",
            "الاحتفاظ بسجلات محاسبية منظمة",
            "استشارة محاسب قانوني عند الحاجة"
        ]
    }


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
    """
    حساب ضريبة القيمة المضافة
    
    ملاحظة: يستخدم الثوابت من SystemSettings للدولة الافتراضية (فلسطين)
    """
    # استخدام الثوابت من SystemSettings للدولة الافتراضية
    if country.lower() == 'palestine':
        try:
            from utils import get_vat_rate, is_vat_enabled
            if not is_vat_enabled():
                rate = 0
            else:
                rate = get_vat_rate()
        except:
            # Fallback للقيمة المحفوظة
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


def get_all_system_modules():
    """معلومات كل وحدات النظام"""
    return {
        'auth': {'name': 'المصادقة', 'route': '/auth'},
        'customers': {'name': 'العملاء', 'route': '/customers'},
        'service': {'name': 'الصيانة', 'route': '/service'},
        'sales': {'name': 'المبيعات', 'route': '/sales'},
        'shop': {'name': 'المتجر', 'route': '/shop'},
        'warehouses': {'name': 'المستودعات', 'route': '/warehouses'},
        'expenses': {'name': 'النفقات', 'route': '/expenses'},
        'payments': {'name': 'المدفوعات', 'route': '/payments'},
        'vendors': {'name': 'الموردين', 'route': '/vendors'},
        'ledger': {'name': 'دفتر الأستاذ', 'route': '/ledger'},
        'security': {'name': 'الأمان', 'route': '/security'},
    }

