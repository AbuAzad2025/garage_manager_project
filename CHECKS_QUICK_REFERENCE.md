# ⚡ مرجع سريع - الشيكات
## Quick Reference: Checks Storage & Retrieval

---

## 📦 1. شيكات النفقات (Expense Checks)

### التخزين:
```
جدول: expenses
├─ check_number       VARCHAR(100)
├─ check_bank         VARCHAR(100)
└─ check_due_date     DATE
```

### الاتجاه:
- **دائماً OUT (صادرة)** ➡️

### الجلب:
```python
from models import Expense

# جلب الكل
checks = Expense.query.filter_by(payment_method='cheque').all()

# الوصول للبيانات
for expense in checks:
    print(expense.check_number)      # مباشرة
    print(expense.check_bank)         # مباشرة
    print(expense.check_due_date)     # مباشرة
    print(expense.amount)
```

---

## 📦 2. شيكات الدفعات الجزئية (PaymentSplit Checks)

### التخزين:
```
جدول: payment_splits
├─ method    VARCHAR ('CHEQUE')
└─ details   JSON
    ├─ check_number
    ├─ check_bank
    └─ check_due_date
```

### الاتجاه:
- **حسب الدفعة الأصلية** (Payment.direction)
  - IN = وارد ⬅️
  - OUT = صادر ➡️

### الجلب:
```python
from models import PaymentSplit, PaymentMethod

# جلب الكل
splits = PaymentSplit.query.filter_by(
    method=PaymentMethod.CHEQUE.value
).all()

# الوصول للبيانات
for split in splits:
    details = split.details or {}  # JSON
    
    print(details.get('check_number'))     # من JSON
    print(details.get('check_bank'))        # من JSON
    print(details.get('check_due_date'))    # من JSON
    print(split.amount)                     # مباشرة
    print(split.payment.direction)          # من الدفعة الأصلية
```

---

## 🔍 مقارنة سريعة

| | Expense | PaymentSplit |
|---|---------|--------------|
| **الجدول** | `expenses` | `payment_splits` |
| **check_number** | حقل مباشر | في `details` JSON |
| **check_bank** | حقل مباشر | في `details` JSON |
| **check_due_date** | حقل مباشر | في `details` JSON |
| **الاتجاه** | OUT دائماً | حسب Payment |
| **الجلب** | سهل | يحتاج JSON |

---

## 💡 أمثلة عملية

### مثال 1: جلب جميع الشيكات
```python
from models import Expense, PaymentSplit, PaymentMethod

# من النفقات
expense_checks = Expense.query.filter_by(payment_method='cheque').all()

# من الدفعات الجزئية
split_checks = PaymentSplit.query.filter_by(
    method=PaymentMethod.CHEQUE.value
).all()

# العدد الإجمالي
total = len(expense_checks) + len(split_checks)
print(f"إجمالي الشيكات: {total}")
```

### مثال 2: فلترة حسب البنك
```python
# من النفقات - سهل
bank_checks = Expense.query.filter(
    Expense.payment_method == 'cheque',
    Expense.check_bank == 'بنك فلسطين'
).all()

# من الدفعات - يحتاج معالجة
all_splits = PaymentSplit.query.filter_by(
    method=PaymentMethod.CHEQUE.value
).all()

bank_splits = [
    s for s in all_splits 
    if s.details and s.details.get('check_bank') == 'بنك فلسطين'
]
```

### مثال 3: الشيكات المتأخرة
```python
from datetime import datetime

today = datetime.utcnow()

# من النفقات
overdue_expenses = Expense.query.filter(
    Expense.payment_method == 'cheque',
    Expense.check_due_date < today
).all()

# من الدفعات - يحتاج معالجة يدوية
all_splits = PaymentSplit.query.filter_by(
    method=PaymentMethod.CHEQUE.value
).all()

overdue_splits = []
for split in all_splits:
    details = split.details or {}
    due_str = details.get('check_due_date')
    if due_str:
        try:
            due = datetime.fromisoformat(due_str)
            if due < today:
                overdue_splits.append(split)
        except:
            pass
```

---

## ⚡ نصائح سريعة

1. **للنفقات:** الوصول مباشر للحقول ✅
   ```python
   expense.check_number  # ✅ مباشر
   ```

2. **للدفعات الجزئية:** استخدم `details` ⚠️
   ```python
   split.details.get('check_number')  # ✅ صحيح
   split.check_number  # ❌ خطأ - لا يوجد
   ```

3. **تحقق دائماً من `details`:**
   ```python
   details = split.details or {}  # ✅
   check_num = details.get('check_number', 'N/A')
   ```

4. **للاتجاه في PaymentSplit:**
   ```python
   direction = split.payment.direction  # من الدفعة الأصلية
   ```

---

## 📚 وثائق أخرى

- **`CHECKS_STORAGE_GUIDE.md`** - دليل مفصل كامل
- **`CHECKS_COMPLETE_GUIDE.md`** - دليل شامل للنظام
- **`CHECKS_SYSTEM_REPORT.md`** - تقرير تقني

---

**✅ مرجع سريع جاهز!**

