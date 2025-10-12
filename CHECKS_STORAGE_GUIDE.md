# 📦 دليل تخزين وجلب الشيكات
## Complete Guide: Where & How Checks are Stored

---

## 🎯 الإجابة المباشرة

### 1️⃣ **شيكات النفقات (Expense Checks)**

#### 📍 **أين تُخزن؟**

في جدول `expenses` مباشرة - **حقول مخصصة**:

```sql
-- الحقول المخصصة في جدول expenses
check_number      VARCHAR(100)    -- رقم الشيك
check_bank        VARCHAR(100)    -- اسم البنك
check_due_date    DATE            -- تاريخ الاستحقاق
```

#### 📝 **بنية التخزين:**

```python
# جدول: expenses
| id | date       | amount  | payment_method | check_number | check_bank    | check_due_date |
|----|------------|---------|----------------|--------------|---------------|----------------|
| 1  | 2025-10-01 | 1627.00 | cheque         | CHK-EXP-001  | بنك القدس     | 2025-10-28     |
| 2  | 2025-10-05 | 873.00  | cheque         | CHK-EXP-002  | بنك القدس     | 2025-11-21     |
```

#### 🔍 **كيف يتم جلبها؟**

```python
from models import Expense

# طريقة 1: جلب جميع شيكات المصروفات
expense_checks = Expense.query.filter_by(payment_method='cheque').all()

for expense in expense_checks:
    print(f"رقم الشيك: {expense.check_number}")
    print(f"البنك: {expense.check_bank}")
    print(f"الاستحقاق: {expense.check_due_date}")
    print(f"المبلغ: {expense.amount} {expense.currency}")
    print(f"الوصف: {expense.description}")
    print("---")

# طريقة 2: مع فلاتر إضافية
from datetime import datetime

# الشيكات المتأخرة
overdue_checks = Expense.query.filter(
    Expense.payment_method == 'cheque',
    Expense.check_due_date < datetime.utcnow()
).all()

# الشيكات القريبة الاستحقاق
from datetime import timedelta
week_ahead = datetime.utcnow() + timedelta(days=7)

due_soon = Expense.query.filter(
    Expense.payment_method == 'cheque',
    Expense.check_due_date.between(datetime.utcnow(), week_ahead)
).all()

# طريقة 3: حسب البنك
bank_checks = Expense.query.filter(
    Expense.payment_method == 'cheque',
    Expense.check_bank == 'بنك فلسطين'
).all()
```

#### 🎯 **الاتجاه (Direction):**
- **دائماً صادرة (OUT)** - لأن المصروفات نحن ندفعها
- الشيك يكون من شركتنا لجهة خارجية

---

### 2️⃣ **شيكات الدفعات الجزئية (PaymentSplit Checks)**

#### 📍 **أين تُخزن؟**

في جدول `payment_splits` - في حقل **`details` (JSON)**:

```sql
-- الحقول في جدول payment_splits
id              INTEGER
payment_id      INTEGER      -- رابط للدفعة الأصلية
method          VARCHAR      -- 'CHEQUE'
amount          DECIMAL
details         TEXT         -- ⭐ JSON يحتوي على معلومات الشيك
```

#### 📝 **بنية التخزين:**

```python
# جدول: payment_splits
| id | payment_id | method | amount  | details (JSON)                                           |
|----|------------|--------|---------|----------------------------------------------------------|
| 3  | 283        | CHEQUE | 800.00  | {"check_number": "123456", "check_bank": "القدس", ...}  |
| 5  | 286        | CHEQUE | 7000.00 | {"check_number": "CHK-003", "check_bank": "الأردن", ...}|
```

#### 📦 **محتوى details (JSON):**

```json
{
  "check_number": "123456",
  "check_bank": "بنك فلسطين",
  "check_due_date": "2025-11-15"
}
```

#### 🔍 **كيف يتم جلبها؟**

```python
from models import PaymentSplit, Payment, PaymentMethod, PaymentDirection

# طريقة 1: جلب جميع الـ splits بشيكات
split_checks = PaymentSplit.query.filter_by(
    method=PaymentMethod.CHEQUE.value
).all()

for split in split_checks:
    # استخراج معلومات الشيك من details
    details = split.details or {}
    
    print(f"PaymentSplit #{split.id}")
    print(f"رقم الشيك: {details.get('check_number', 'N/A')}")
    print(f"البنك: {details.get('check_bank', 'N/A')}")
    print(f"الاستحقاق: {details.get('check_due_date', 'N/A')}")
    print(f"المبلغ: {split.amount}")
    
    # الوصول للدفعة الأصلية
    payment = split.payment
    print(f"الاتجاه: {payment.direction}")
    print(f"العملة: {payment.currency}")
    print("---")

# طريقة 2: مع join للحصول على معلومات الدفعة
from sqlalchemy.orm import joinedload

split_checks_with_payment = PaymentSplit.query\
    .options(joinedload(PaymentSplit.payment))\
    .filter_by(method=PaymentMethod.CHEQUE.value)\
    .all()

# طريقة 3: حسب اتجاه الدفعة (وارد/صادر)
from sqlalchemy import and_

# الشيكات الواردة فقط
incoming_splits = db.session.query(PaymentSplit)\
    .join(Payment)\
    .filter(
        PaymentSplit.method == PaymentMethod.CHEQUE.value,
        Payment.direction == PaymentDirection.IN.value
    ).all()

# الشيكات الصادرة فقط
outgoing_splits = db.session.query(PaymentSplit)\
    .join(Payment)\
    .filter(
        PaymentSplit.method == PaymentMethod.CHEQUE.value,
        Payment.direction == PaymentDirection.OUT.value
    ).all()

# طريقة 4: البحث في JSON (SQLite/PostgreSQL)
from sqlalchemy import func, cast, String

# البحث عن شيك برقم محدد (PostgreSQL)
split_by_number = PaymentSplit.query.filter(
    PaymentSplit.method == PaymentMethod.CHEQUE.value,
    PaymentSplit.details['check_number'].astext == '123456'
).all()

# للبحث في SQLite (يحتاج json_extract)
# split_by_number = PaymentSplit.query.filter(
#     PaymentSplit.method == PaymentMethod.CHEQUE.value,
#     func.json_extract(PaymentSplit.details, '$.check_number') == '123456'
# ).all()
```

#### 🎯 **الاتجاه (Direction):**
- يعتمد على اتجاه الدفعة الأصلية (Payment.direction)
- **IN** = وارد (نستلم شيك)
- **OUT** = صادر (ندفع شيك)

#### 💡 **لماذا JSON في PaymentSplit؟**
لأن الدفعة قد تكون مركبة:
```
دفعة 10,000 شيكل = 3000 نقدي + 7000 شيك
```

---

## 🔄 **مقارنة شاملة**

| الميزة | Expense Checks | PaymentSplit Checks |
|--------|----------------|---------------------|
| **الجدول** | `expenses` | `payment_splits` |
| **التخزين** | حقول مباشرة | JSON في `details` |
| **الحقول** | check_number, check_bank, check_due_date | كل شيء في details |
| **الاتجاه** | دائماً OUT | حسب Payment.direction |
| **الاستخدام** | مصروفات | دفعات مركبة |
| **البساطة** | سهل الاستعلام | يحتاج JSON parsing |
| **المرونة** | محدودة | عالية (يمكن إضافة حقول) |

---

## 🎨 **أمثلة عملية**

### مثال 1: جلب جميع الشيكات المتأخرة (من المصدرين)

```python
from datetime import datetime
from models import Expense, PaymentSplit, Payment, PaymentMethod

def get_all_overdue_checks():
    """جلب جميع الشيكات المتأخرة من جميع المصادر"""
    today = datetime.utcnow()
    all_overdue = []
    
    # 1. من Expenses
    expense_overdue = Expense.query.filter(
        Expense.payment_method == 'cheque',
        Expense.check_due_date < today
    ).all()
    
    for expense in expense_overdue:
        all_overdue.append({
            'source': 'expense',
            'id': expense.id,
            'check_number': expense.check_number,
            'check_bank': expense.check_bank,
            'check_due_date': expense.check_due_date,
            'amount': expense.amount,
            'currency': expense.currency,
            'direction': 'OUT',  # دائماً صادرة
            'description': expense.description
        })
    
    # 2. من PaymentSplits
    split_checks = PaymentSplit.query\
        .join(Payment)\
        .filter(PaymentSplit.method == PaymentMethod.CHEQUE.value)\
        .all()
    
    for split in split_checks:
        details = split.details or {}
        due_date_str = details.get('check_due_date')
        
        if due_date_str:
            try:
                from datetime import datetime
                if isinstance(due_date_str, str):
                    due_date = datetime.fromisoformat(due_date_str)
                else:
                    due_date = due_date_str
                
                if due_date < today:
                    all_overdue.append({
                        'source': 'payment_split',
                        'id': split.id,
                        'payment_id': split.payment_id,
                        'check_number': details.get('check_number'),
                        'check_bank': details.get('check_bank'),
                        'check_due_date': due_date,
                        'amount': split.amount,
                        'currency': split.payment.currency,
                        'direction': split.payment.direction,
                        'description': f"من دفعة #{split.payment.payment_number}"
                    })
            except:
                pass
    
    return all_overdue

# الاستخدام
overdue_checks = get_all_overdue_checks()
print(f"عدد الشيكات المتأخرة: {len(overdue_checks)}")

for check in overdue_checks:
    print(f"{check['source']}: {check['check_number']} - {check['amount']}")
```

### مثال 2: إحصائيات الشيكات حسب البنك

```python
from collections import defaultdict
from models import Expense, PaymentSplit, PaymentMethod

def get_checks_by_bank():
    """تجميع الشيكات حسب البنك"""
    banks = defaultdict(lambda: {'count': 0, 'total': 0, 'checks': []})
    
    # 1. من Expenses
    expenses = Expense.query.filter_by(payment_method='cheque').all()
    for exp in expenses:
        bank = exp.check_bank or 'Unknown'
        banks[bank]['count'] += 1
        banks[bank]['total'] += float(exp.amount or 0)
        banks[bank]['checks'].append({
            'type': 'expense',
            'number': exp.check_number,
            'amount': exp.amount
        })
    
    # 2. من PaymentSplits
    splits = PaymentSplit.query.filter_by(method=PaymentMethod.CHEQUE.value).all()
    for split in splits:
        details = split.details or {}
        bank = details.get('check_bank', 'Unknown')
        banks[bank]['count'] += 1
        banks[bank]['total'] += float(split.amount or 0)
        banks[bank]['checks'].append({
            'type': 'split',
            'number': details.get('check_number'),
            'amount': split.amount
        })
    
    return dict(banks)

# الاستخدام
banks_summary = get_checks_by_bank()
for bank, info in banks_summary.items():
    print(f"{bank}: {info['count']} شيك - المجموع: {info['total']}")
```

### مثال 3: تصدير شيكات لملف CSV

```python
import csv
from models import Expense, PaymentSplit, PaymentMethod

def export_checks_to_csv(filename='checks_export.csv'):
    """تصدير جميع الشيكات لملف CSV"""
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # الرأس
        writer.writerow([
            'المصدر', 'رقم الشيك', 'البنك', 'تاريخ الاستحقاق',
            'المبلغ', 'العملة', 'الاتجاه', 'الوصف'
        ])
        
        # من Expenses
        expenses = Expense.query.filter_by(payment_method='cheque').all()
        for exp in expenses:
            writer.writerow([
                'مصروف',
                exp.check_number,
                exp.check_bank,
                exp.check_due_date,
                exp.amount,
                exp.currency,
                'صادر',
                exp.description
            ])
        
        # من PaymentSplits
        splits = PaymentSplit.query\
            .filter_by(method=PaymentMethod.CHEQUE.value)\
            .all()
        
        for split in splits:
            details = split.details or {}
            writer.writerow([
                'دفعة جزئية',
                details.get('check_number'),
                details.get('check_bank'),
                details.get('check_due_date'),
                split.amount,
                split.payment.currency if split.payment else 'ILS',
                split.payment.direction if split.payment else 'N/A',
                f"من دفعة #{split.payment_id}"
            ])
    
    print(f"✅ تم التصدير إلى {filename}")
```

---

## 🎯 **الخلاصة النهائية**

### **شيكات النفقات (Expense):**
```python
# التخزين: حقول مباشرة في جدول expenses
✓ check_number
✓ check_bank  
✓ check_due_date

# الجلب:
Expense.query.filter_by(payment_method='cheque').all()
```

### **شيكات الدفعات الجزئية (PaymentSplit):**
```python
# التخزين: JSON في حقل details
✓ details = {
    'check_number': '...',
    'check_bank': '...',
    'check_due_date': '...'
}

# الجلب:
PaymentSplit.query.filter_by(method=PaymentMethod.CHEQUE.value).all()
# ثم استخراج البيانات من split.details
```

---

## 📌 **نصائح مهمة**

1. **دائماً تحقق من `payment_method` أو `method`:**
   ```python
   # للـ Expense
   if expense.payment_method == 'cheque':
       # معالجة الشيك
   
   # للـ PaymentSplit
   if split.method == PaymentMethod.CHEQUE.value:
       # معالجة الشيك
   ```

2. **للـ PaymentSplit - تحقق من وجود details:**
   ```python
   details = split.details or {}
   check_number = details.get('check_number', 'N/A')
   ```

3. **للتاريخ في PaymentSplit - قد يكون string:**
   ```python
   due_date_str = details.get('check_due_date')
   if isinstance(due_date_str, str):
       due_date = datetime.fromisoformat(due_date_str)
   ```

4. **استخدم join للأداء الأفضل:**
   ```python
   PaymentSplit.query.options(joinedload(PaymentSplit.payment))
   ```

---

**🎉 الآن لديك فهم كامل لتخزين وجلب الشيكات!**

