"""
تقرير شامل - القيود المحاسبية والضرائب في المتجر الإلكتروني
===========================================================
"""

print("="*90)
print("COMPREHENSIVE REPORT - Online Shop GL & TAX")
print("="*90)

print("\n" + "="*90)
print("PART 1: CURRENT STATE - القيود المحاسبية")
print("="*90)

gl_status = {
    "OnlinePreOrder": {
        "has_gl_listener": "✅ نعم - _online_preorder_gl_batch_upsert",
        "location": "models.py:9795",
        "creates": "GLBatch عند after_insert/after_update",
        "entries": [
            "مدين: 1100_AR (حسابات العملاء)",
            "دائن: 2300_ADVANCE_PAYMENTS (دفعات مقدمة)"
        ],
        "status": "✅ يعمل تلقائياً"
    },
    "Payment (Online)": {
        "has_gl_listener": "✅ نعم - _payment_gl_batch_upsert",
        "location": "models.py:7316",
        "creates": "GLBatch عند after_insert/after_update",
        "entries": [
            "يعتمد على direction و status:",
            "IN + COMPLETED → مدين: صندوق، دائن: AR",
            "OUT + COMPLETED → مدين: AR، دائن: صندوق"
        ],
        "status": "✅ يعمل تلقائياً"
    }
}

for entity, info in gl_status.items():
    print(f"\n{entity}:")
    for key, value in info.items():
        if isinstance(value, list):
            print(f"  {key}:")
            for v in value:
                print(f"    - {v}")
        else:
            print(f"  {key}: {value}")

print("\n" + "="*90)
print("PART 2: CURRENT STATE - الضرائب")
print("="*90)

tax_status = {
    "إعدادات النظام": {
        "default_vat_rate": "18% (في system_settings)",
        "vat_enabled": "True",
        "location": "system_settings table",
        "status": "✅ موجود"
    },
    "المنتجات": {
        "tax_rate في Product": "موجود (حقل في الجدول)",
        "القيمة الحالية": "0% لجميع المنتجات",
        "المشكلة": "⚠️ لا تُستخدم نسبة default_vat_rate",
        "status": "⚠️ يحتاج تحسين"
    },
    "المبيعات العادية (Sale)": {
        "SaleLine.tax_rate": "✅ موجود",
        "الحساب": "(qty * price * (1 - discount%) * (1 + tax%))",
        "TaxEntry": "✅ يُنشأ تلقائياً عند الحفظ",
        "status": "✅ يعمل صح"
    },
    "المتجر الإلكتروني": {
        "OnlinePreOrder": "❌ لا يحسب الضرائب",
        "OnlineCart.subtotal": "sum(qty * price) فقط - بدون ضريبة",
        "TaxEntry": "❌ لا يُنشأ",
        "المشكلة": "⚠️ الأسعار بدون VAT",
        "status": "❌ يحتاج إصلاح"
    }
}

for category, info in tax_status.items():
    print(f"\n{category}:")
    for key, value in info.items():
        print(f"  {key}: {value}")

print("\n" + "="*90)
print("PART 3: المشاكل المكتشفة")
print("="*90)

issues = [
    {
        "issue": "المتجر الإلكتروني لا يحسب الضرائب",
        "location": "routes/shop.py:775",
        "current_code": "subtotal = sum(i.quantity * float(i.price or 0) for i in cart.items)",
        "problem": "الحساب بدون ضريبة - السعر مباشرة من product.online_price",
        "impact": [
            "العميل يدفع بدون VAT",
            "الشركة تخسر VAT",
            "لا يُنشأ TaxEntry",
            "التقارير الضريبية ناقصة"
        ],
        "severity": "🔴 HIGH"
    },
    {
        "issue": "المنتجات بدون tax_rate",
        "location": "products table",
        "current_code": "tax_rate = 0 لجميع المنتجات",
        "problem": "لا تُستخدم default_vat_rate من الإعدادات",
        "impact": [
            "المبيعات بدون ضريبة",
            "يجب تحديد tax_rate يدوياً لكل منتج"
        ],
        "severity": "🟡 MEDIUM"
    }
]

for i, issue in enumerate(issues, 1):
    print(f"\n{i}. {issue['issue']}")
    print(f"   Location: {issue['location']}")
    print(f"   Current: {issue['current_code']}")
    print(f"   Problem: {issue['problem']}")
    print(f"   Impact:")
    for impact in issue['impact']:
        print(f"     - {impact}")
    print(f"   Severity: {issue['severity']}")

print("\n" + "="*90)
print("PART 4: الحلول المقترحة")
print("="*90)

solutions = [
    {
        "solution": "إصلاح حساب المتجر الإلكتروني ليشمل الضرائب",
        "file": "routes/shop.py",
        "change": """
قبل:
  subtotal = sum(i.quantity * float(i.price or 0) for i in cart.items)

بعد:
  from models import SystemSettings
  vat_rate = SystemSettings.get_setting('default_vat_rate', 0.0) if SystemSettings.get_setting('vat_enabled', False) else 0.0
  
  subtotal_before_tax = sum(i.quantity * float(i.price or 0) for i in cart.items)
  tax_amount = subtotal_before_tax * (vat_rate / 100.0)
  subtotal = subtotal_before_tax + tax_amount
        """,
        "priority": "🔴 HIGH"
    },
    {
        "solution": "إنشاء TaxEntry للطلبات الأونلاين",
        "file": "models.py - OnlinePreOrder listener",
        "change": "إضافة create_tax_entry في _online_preorder_gl_batch_upsert",
        "priority": "🟡 MEDIUM"
    },
    {
        "solution": "تطبيق default_vat_rate على المنتجات الجديدة",
        "file": "models.py - Product before_insert",
        "change": "إذا tax_rate = 0، استخدم default_vat_rate",
        "priority": "🟢 LOW (اختياري)"
    }
]

for i, sol in enumerate(solutions, 1):
    print(f"\n{i}. {sol['solution']}")
    print(f"   File: {sol['file']}")
    print(f"   Priority: {sol['priority']}")
    if 'change' in sol:
        print(f"   Change: {sol['change']}")

print("\n" + "="*90)
print("PART 5: الخلاصة والتوصيات")
print("="*90)

summary = """
الوضع الحالي:
  ✅ القيود المحاسبية (GL):
     - OnlinePreOrder ينشئ GL تلقائياً ✅
     - Payment ينشئ GL تلقائياً ✅
     - الحسابات صحيحة (AR, ADVANCE_PAYMENTS) ✅

  ❌ الضرائب (VAT):
     - المتجر الإلكتروني لا يحسب ضرائب ❌
     - OnlineCart.subtotal بدون VAT ❌
     - لا يُنشأ TaxEntry ❌

التوصيات:
  1. 🔴 HIGH: إضافة حساب الضرائب في المتجر الإلكتروني
  2. 🟡 MEDIUM: إنشاء TaxEntry للطلبات الأونلاين
  3. 🟢 LOW: تطبيق default_vat_rate على المنتجات تلقائياً

الأولوية:
  المتجر الإلكتروني يجب أن يحسب VAT ليتطابق مع المبيعات العادية!
"""

print(summary)

