# 🔍 فحص تحويل العملات في نظام تسوية الشركاء

**التاريخ:** 2025-10-17  
**الحالة:** 🔍 **قيد الفحص**

---

## ✅ ما يعمل بشكل صحيح

### 1. المبيعات (_get_partner_sales_share) ✅
```python
# لكل عملية بيع:
partner_share_ils = _convert_to_ils(partner_share, item.currency, item.date)
total_ils += partner_share_ils
```
**الحالة:** ✅ يحول كل عملية إلى ILS قبل الجمع

### 2. الدفعات للشريك (_get_payments_to_partner) ✅
```python
# لكل دفعة:
amount_ils = _convert_to_ils(payment.total_amount, payment.currency, payment.payment_date)
total_ils += amount_ils
```
**الحالة:** ✅ يحول كل دفعة إلى ILS قبل الجمع

### 3. الدفعات من الشريك (_get_partner_payments_received) ✅
```python
# لكل دفعة:
amount_ils = _convert_to_ils(payment.total_amount, payment.currency, payment.payment_date)
total_ils += amount_ils
```
**الحالة:** ✅ يحول كل دفعة إلى ILS قبل الجمع

### 4. مبيعات للشريك (_get_partner_sales_as_customer) ✅
```python
# لكل فاتورة:
amount_ils = _convert_to_ils(sale.total_amount, sale.currency, sale.sale_date)
total_ils += amount_ils
```
**الحالة:** ✅ يحول كل فاتورة إلى ILS قبل الجمع

### 5. رسوم الصيانة (_get_partner_service_fees) ✅
```python
# لكل صيانة:
amount_ils = _convert_to_ils(service.total_amount, service.currency, service.received_at)
total_ils += amount_ils
```
**الحالة:** ✅ يحول كل صيانة إلى ILS قبل الجمع

### 6. المصروفات (_get_partner_expenses) ✅
```python
# لكل مصروف:
amount_ils = _convert_to_ils(amount, currency, expense_date)
total_ils += amount_ils
```
**الحالة:** ✅ يحول كل مصروف إلى ILS قبل الجمع

---

## ⚠️ محتمل المشكلة

### 1. المخزون (_get_partner_inventory) ⚠️
```python
# الكود الحالي:
cost = item.purchase_price  # من Product.purchase_price
partner_share = qty * cost * share_pct / 100
total += partner_share  # ❌ جمع مباشر بدون تحويل!
```

**المشكلة المحتملة:**
- إذا كان `Product.purchase_price` بعملات مختلفة
- يتم الجمع مباشرة بدون تحويل!

**الحل المطلوب:**
- التحقق من عملة المنتج (إن وجدت)
- تحويل كل قطعة إلى ILS قبل الجمع
- أو افتراض أن جميع التكاليف بالعملة الأساسية

### 2. القطع التالفة (_get_partner_damaged_items) ⚠️
```python
# الكود الحالي:
partner_loss = qty * unit_cost * share_pct / 100
total_ils += partner_loss  # ❌ جمع مباشر بدون تحويل!
```

**المشكلة المحتملة:**
- `unit_cost` من `StockAdjustmentItem` قد يكون بعملة مختلفة
- يتم الجمع مباشرة بدون تحويل!

---

## 🔍 التحليل

### السيناريو المشكل:

```
المخزون:
- قطعة A: تكلفة 100 USD
- قطعة B: تكلفة 200 ILS
- قطعة C: تكلفة 50 EUR

الكود الحالي:
total = 100 + 200 + 50 = 350 ❌ (خليط من العملات!)

الصحيح:
100 USD × 3.6 = 360 ILS
200 ILS × 1.0 = 200 ILS
50 EUR × 4.0 = 200 ILS
total = 360 + 200 + 200 = 760 ILS ✅
```

---

## ✅ الحل المطلوب

### 1. إضافة تحويل العملات للمخزون

```python
def _get_partner_inventory(partner_id, date_from, date_to):
    # ... الكود الحالي ...
    
    for inv_item in inventory_items:
        # ... استخراج البيانات ...
        
        # حساب نصيب الشريك
        partner_share = Decimal(str(qty)) * Decimal(str(cost or 0)) * Decimal(str(share_pct)) / Decimal("100")
        
        # 🔥 التحويل إلى ILS قبل الجمع
        # التحقق من عملة المنتج
        product_currency = getattr(Product.query.get(prod_id), 'currency', 'ILS') or 'ILS'
        partner_share_ils = _convert_to_ils(partner_share, product_currency, datetime.utcnow())
        
        total += partner_share_ils  # ✅ جمع بعد التحويل
```

### 2. إضافة تحويل العملات للقطع التالفة

```python
def _get_partner_damaged_items(partner_id, date_from, date_to):
    # ... الكود الحالي ...
    
    for damaged in damaged_items:
        # ... استخراج البيانات ...
        
        # حساب نصيب الخسارة
        partner_loss = Decimal(str(quantity)) * Decimal(str(unit_cost or 0)) * Decimal(str(share_pct)) / Decimal("100")
        
        # 🔥 التحويل إلى ILS قبل الجمع
        # التحقق من عملة التعديل
        adjustment_currency = 'ILS'  # افتراضي - يمكن جلبها من StockAdjustment
        partner_loss_ils = _convert_to_ils(partner_loss, adjustment_currency, damaged.date)
        
        total_ils += partner_loss_ils  # ✅ جمع بعد التحويل
```

---

## 🎯 الخطة

### المرحلة 1: التحقق من عملات المنتجات
- [ ] التحقق من وجود حقل `currency` في جدول `Product`
- [ ] إذا لم يكن موجوداً، افتراض ILS لجميع التكاليف

### المرحلة 2: تصحيح دالة المخزون
- [ ] إضافة تحويل العملات لكل قطعة
- [ ] اختبار مع منتجات بعملات مختلفة

### المرحلة 3: تصحيح دالة القطع التالفة
- [ ] إضافة تحويل العملات لكل قطعة تالفة
- [ ] اختبار مع تعديلات بعملات مختلفة

### المرحلة 4: الاختبار الشامل
- [ ] إنشاء بيانات تجريبية بعملات مختلفة
- [ ] التأكد من صحة المجاميع
- [ ] مقارنة مع الحساب اليدوي

---

## 📊 تقييم الخطورة

### المخزون:
- **الخطورة:** 🟠 متوسطة
- **السبب:** في معظم الأنظمة، التكاليف بعملة واحدة
- **الحل:** افتراض ILS إن لم تكن هناك عملة محددة

### القطع التالفة:
- **الخطورة:** 🟡 منخفضة
- **السبب:** عادة تكون بنفس عملة المنتج
- **الحل:** نفس المنطق أعلاه

---

## ✅ التوصية

### الأولوية 1 (عاجل):
1. التحقق من وجود عملات مختلفة في قاعدة البيانات الحالية
2. إذا كانت جميع المنتجات بـ ILS → لا مشكلة حالياً
3. إذا كانت هناك عملات مختلفة → تصحيح فوري

### الأولوية 2 (احتياطي):
1. إضافة تحويل العملات للمخزون والتالف
2. حتى لو كانت جميع المنتجات بـ ILS حالياً
3. للحماية المستقبلية

---

**الخلاصة:** النظام يحول العملات بشكل صحيح في معظم الدوال، لكن المخزون والقطع التالفة قد تحتاج تحسين!

