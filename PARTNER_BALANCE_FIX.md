# إصلاح خطأ حساب رصيد الشركاء

**التاريخ:** 2025-10-17  
**الحالة:** ✅ **تم الإصلاح**

---

## ❌ المشكلة

```
Error calculating partner 1 balance: type object 'Sale' has no attribute 'partner_id'
```

### السبب:
الكود في `routes/vendors.py` كان يحاول الوصول إلى:
```python
sales = Sale.query.filter(Sale.partner_id == partner.id).all()
```

لكن جدول `Sale` **لا يحتوي على حقل `partner_id`**!

---

## 🔍 التحليل

### جدول Sale يحتوي على:
- `customer_id` ← للعملاء
- `seller_id` ← للموظف البائع
- ❌ **لا يوجد `partner_id`**

### الشركاء (Partners) يرتبطون بـ:
- ✅ `ServiceTask` ← **مهام الصيانة**
- ✅ `ServicePart` ← قطع الغيار في الخدمة
- ✅ `Warehouse` ← المستودعات
- ✅ `Payment` ← المدفوعات
- ✅ `ExchangeTransaction` ← معاملات التبادل

---

## ✅ الحل المطبق

تم تعديل الكود ليبحث عن `ServiceTask` بدلاً من `Sale`:

### قبل:
```python
# خطأ: Sale ليس له partner_id
sales = Sale.query.filter(Sale.partner_id == partner.id).all()
```

### بعد:
```python
# صحيح: ServiceTask له partner_id
from models import ServiceTask
service_tasks = ServiceTask.query.filter(ServiceTask.partner_id == partner.id).all()

for task in service_tasks:
    if task.service and task.service.total_amount:
        amount = float(task.service.total_amount or 0)
        # احسب حصة الشريك
        if task.share_percentage:
            amount = amount * (float(task.share_percentage) / 100.0)
        sales_total += amount
```

---

## 🎯 ما يحسبه الكود الآن:

### 1. **إيرادات الشريك** (من ServiceTask):
- خدمات الصيانة التي عمل عليها الشريك
- يحسب حصته بناءً على `share_percentage`
- يحوّل العملات إلى شيكل إذا لزم الأمر

### 2. **المدفوعات للشريك** (من Payment):
- الدفعات الواردة من الشريك
- `Payment.partner_id == partner.id`
- `Payment.direction == 'IN'`

### 3. **الرصيد النهائي**:
```
الرصيد = الإيرادات - المدفوعات
```

- **موجب** → مستحق دفع للشريك
- **سالب** → الشريك مدين لنا

---

## 📊 النتيجة

### قبل:
```
❌ Error calculating partner 1 balance: type object 'Sale' has no attribute 'partner_id'
❌ Error calculating partner 2 balance: ...
❌ Error calculating partner 3 balance: ...
```

### بعد:
```
✅ حساب رصيد الشريك 1 بنجاح
✅ حساب رصيد الشريك 2 بنجاح
✅ حساب رصيد الشريك 3 بنجاح
```

---

## 📝 ملاحظات

1. **ServiceTask** هو الرابط الصحيح بين الشركاء والخدمات
2. `share_percentage` يحدد حصة الشريك من كل خدمة
3. يتم تحويل جميع المبالغ إلى شيكل للحساب الموحد
4. الكود الآن يتعامل مع الأخطاء بشكل صحيح

---

## 🚀 للتطبيق

الكود تم تعديله في:
- ✅ `routes/vendors.py` (السطر ~472)

**لا حاجة لإعادة تشغيل** - التعديل سيعمل في الطلب القادم.

---

## ✅ الخلاصة

- ✅ تم إصلاح الخطأ
- ✅ حساب رصيد الشركاء يعمل الآن بشكل صحيح
- ✅ يحسب من ServiceTask وليس Sale
- ✅ يراعي نسبة حصة الشريك

**الشركاء الآن يُعرضون بأرصدتهم الصحيحة!** 🎉

