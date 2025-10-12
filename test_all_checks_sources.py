#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
اختبار شامل لجميع مصادر الشيكات في النظام
"""

from app import app, db
from models import (
    Payment, PaymentSplit, PaymentMethod, PaymentDirection, PaymentStatus,
    Expense, Check, CheckStatus,
    Customer, Supplier, Partner
)
from datetime import datetime, timedelta
from decimal import Decimal
import random

def create_test_checks():
    """إنشاء شيكات اختبارية من جميع المصادر"""
    
    with app.app_context():
        print("\n" + "="*80)
        print("📝 إنشاء شيكات اختبارية من جميع المصادر")
        print("="*80)
        
        # الحصول على جهات موجودة
        customers = Customer.query.limit(3).all()
        suppliers = Supplier.query.limit(3).all()
        partners = Partner.query.limit(2).all()
        
        if not customers or not suppliers:
            print("❌ لا توجد بيانات كافية. شغّل seed_complete.py أولاً")
            return
        
        base_date = datetime.utcnow()
        
        # ===== 1. شيكات من Payment (بطريقة عادية) =====
        print("\n1️⃣ إنشاء شيكات من Payment (method=CHEQUE)...")
        for i in range(2):
            customer = random.choice(customers)
            payment = Payment(
                customer_id=customer.id,
                direction=PaymentDirection.IN.value,
                method=PaymentMethod.CHEQUE.value,
                status=PaymentStatus.PENDING.value,
                total_amount=Decimal(str(random.randint(1000, 5000))),
                currency="ILS",
                payment_date=base_date - timedelta(days=random.randint(1, 10)),
                check_number=f"CHK-PAY-{i+1:03d}",
                check_bank=random.choice(['بنك فلسطين', 'بنك القدس', 'بنك الأردن']),
                check_due_date=base_date + timedelta(days=random.randint(30, 90)),
                reference=f"دفعة من العميل {customer.name}",
                notes="TEST - شيك من Payment"
            )
            db.session.add(payment)
        print("   ✅ تم إضافة 2 شيك من Payment")
        
        # ===== 2. شيكات من PaymentSplit =====
        print("\n2️⃣ إنشاء شيكات من PaymentSplit...")
        for i in range(2):
            supplier = random.choice(suppliers)
            
            # إنشاء دفعة مركبة
            payment = Payment(
                supplier_id=supplier.id,
                direction=PaymentDirection.OUT.value,
                method=PaymentMethod.CASH.value,  # سيتم تحديثها تلقائياً
                status=PaymentStatus.PENDING.value,
                total_amount=Decimal("10000"),
                currency=supplier.currency or "ILS",
                payment_date=base_date - timedelta(days=random.randint(5, 15)),
                reference=f"دفعة للمورد {supplier.name}",
                notes="TEST - دفعة مركبة مع شيك"
            )
            db.session.add(payment)
            db.session.flush()
            
            # إضافة split نقدي
            split1 = PaymentSplit(
                payment_id=payment.id,
                method=PaymentMethod.CASH.value,
                amount=Decimal("3000"),
                details=None
            )
            db.session.add(split1)
            
            # إضافة split بشيك
            check_due = base_date + timedelta(days=random.randint(30, 60))
            split2 = PaymentSplit(
                payment_id=payment.id,
                method=PaymentMethod.CHEQUE.value,
                amount=Decimal("7000"),
                details={
                    'check_number': f'CHK-SPLIT-{i+1:03d}',
                    'check_bank': random.choice(['بنك فلسطين', 'بنك القدس', 'بنك الأردن']),
                    'check_due_date': check_due.isoformat()
                }
            )
            db.session.add(split2)
            
            # تحديث طريقة الدفع الرئيسية
            payment.method = PaymentMethod.CHEQUE.value
            payment.total_amount = Decimal("10000")
            
        print("   ✅ تم إضافة 2 دفعة مركبة مع شيكات")
        
        # ===== 3. شيكات من Expense =====
        print("\n3️⃣ إنشاء شيكات من Expense...")
        
        # الحصول على ExpenseType أو إنشاء واحد
        from models import ExpenseType
        expense_type = ExpenseType.query.first()
        if not expense_type:
            expense_type = ExpenseType(name='متنوعة', description='مصروفات متنوعة')
            db.session.add(expense_type)
            db.session.flush()
        
        for i in range(3):
            expense = Expense(
                description=f"TEST - مصروف بشيك رقم {i+1}",
                amount=Decimal(str(random.randint(500, 2000))),
                currency="ILS",
                date=base_date - timedelta(days=random.randint(1, 20)),
                type_id=expense_type.id,
                payment_method='cheque',
                check_number=f'CHK-EXP-{i+1:03d}',
                check_bank=random.choice(['بنك فلسطين', 'بنك القدس', 'بنك الأردن']),
                check_due_date=(base_date + timedelta(days=random.randint(15, 45))).date(),
                payee_type='OTHER',
                payee_name=f'جهة خارجية {i+1}',
                notes='TEST - مصروف بشيك'
            )
            db.session.add(expense)
        print("   ✅ تم إضافة 3 مصروفات بشيكات")
        
        # ===== 4. شيكات يدوية من Check =====
        print("\n4️⃣ إنشاء شيكات يدوية من Check model...")
        
        # الحصول على مستخدم  للـ created_by_id
        from models import User
        user = User.query.first()
        if not user:
            print("   ⚠️ لا يوجد مستخدمين - تخطي الشيكات اليدوية")
        else:
            # شيك وارد من عميل
            for i in range(2):
                customer = random.choice(customers)
                check = Check(
                    check_number=f'CHK-MANUAL-IN-{i+1:03d}',
                    check_bank=random.choice(['بنك فلسطين', 'بنك القدس', 'بنك الأردن']),
                    check_date=base_date - timedelta(days=random.randint(1, 5)),
                    check_due_date=base_date + timedelta(days=random.randint(30, 90)),
                    amount=Decimal(str(random.randint(2000, 8000))),
                    currency="ILS",
                    direction=PaymentDirection.IN.value,
                    status=CheckStatus.PENDING.value,
                    customer_id=customer.id,
                    drawer_name=customer.name,
                    drawer_phone=customer.phone or '',
                    payee_name='شركتنا',
                    notes=f'TEST - شيك يدوي وارد من {customer.name}',
                    reference_number=f'MAN-IN-{i+1:03d}',
                    created_by_id=user.id
                )
                db.session.add(check)
            
            # شيك صادر لمورد
            for i in range(2):
                supplier = random.choice(suppliers)
                check = Check(
                    check_number=f'CHK-MANUAL-OUT-{i+1:03d}',
                    check_bank=random.choice(['بنك فلسطين', 'بنك القدس', 'بنك الأردن']),
                    check_date=base_date - timedelta(days=random.randint(1, 5)),
                    check_due_date=base_date + timedelta(days=random.randint(20, 60)),
                    amount=Decimal(str(random.randint(3000, 10000))),
                    currency=supplier.currency or "ILS",
                    direction=PaymentDirection.OUT.value,
                    status=CheckStatus.PENDING.value,
                    supplier_id=supplier.id,
                    drawer_name='شركتنا',
                    payee_name=supplier.name,
                    payee_phone=supplier.phone or '',
                    notes=f'TEST - شيك يدوي صادر للمورد {supplier.name}',
                    reference_number=f'MAN-OUT-{i+1:03d}',
                    created_by_id=user.id
                )
                db.session.add(check)
            
            print("   ✅ تم إضافة 4 شيكات يدوية (2 وارد + 2 صادر)")
        
        # حفظ جميع التغييرات
        db.session.commit()
        
        print("\n" + "="*80)
        print("✅ تم إنشاء جميع الشيكات الاختبارية بنجاح")
        print("="*80)


def display_all_checks():
    """عرض جميع الشيكات من جميع المصادر"""
    
    with app.app_context():
        print("\n" + "="*80)
        print("📊 ملخص الشيكات في النظام")
        print("="*80)
        
        # 1. شيكات Payment
        payment_checks = Payment.query.filter_by(method=PaymentMethod.CHEQUE.value).all()
        print(f"\n1️⃣ شيكات من Payment: {len(payment_checks)}")
        for p in payment_checks[:5]:
            status = '✅' if p.status == PaymentStatus.COMPLETED.value else '⏳'
            direction = '⬅️' if p.direction == PaymentDirection.IN.value else '➡️'
            print(f"   {status} {direction} {p.check_number} - {p.check_bank} - {p.total_amount} {p.currency}")
            print(f"      الاستحقاق: {p.check_due_date.date() if p.check_due_date else 'N/A'}")
        
        # 2. شيكات PaymentSplit
        split_checks = PaymentSplit.query.filter_by(method=PaymentMethod.CHEQUE.value).all()
        print(f"\n2️⃣ شيكات من PaymentSplit: {len(split_checks)}")
        for s in split_checks[:5]:
            details = s.details or {}
            print(f"   ⏳ {details.get('check_number', 'N/A')} - {details.get('check_bank', 'N/A')} - {s.amount}")
            print(f"      الاستحقاق: {details.get('check_due_date', 'N/A')}")
        
        # 3. شيكات Expense
        expense_checks = Expense.query.filter_by(payment_method='cheque').all()
        print(f"\n3️⃣ شيكات من Expenses: {len(expense_checks)}")
        for e in expense_checks[:5]:
            print(f"   💰 {e.check_number} - {e.check_bank} - {e.amount} {e.currency}")
            due = e.check_due_date if isinstance(e.check_due_date, str) else (e.check_due_date.strftime('%Y-%m-%d') if e.check_due_date else 'N/A')
            print(f"      الاستحقاق: {due}")
            print(f"      الوصف: {e.description}")
        
        # 4. شيكات Check (يدوية)
        manual_checks = Check.query.all()
        print(f"\n4️⃣ شيكات يدوية (Check model): {len(manual_checks)}")
        for c in manual_checks[:5]:
            status_emoji = {
                'PENDING': '⏳',
                'CASHED': '✅',
                'RETURNED': '🔄',
                'BOUNCED': '❌',
                'CANCELLED': '⛔'
            }.get(c.status, '❓')
            direction = '⬅️' if c.direction == PaymentDirection.IN.value else '➡️'
            print(f"   {status_emoji} {direction} {c.check_number} - {c.check_bank} - {c.amount} {c.currency}")
            print(f"      الاستحقاق: {c.check_due_date.date() if c.check_due_date else 'N/A'}")
        
        # الإجمالي
        total = len(payment_checks) + len(split_checks) + len(expense_checks) + len(manual_checks)
        print(f"\n{'='*80}")
        print(f"📌 إجمالي الشيكات: {total}")
        print(f"{'='*80}\n")


if __name__ == "__main__":
    print("\n" + "🚀"*40)
    print("اختبار شامل لنظام الشيكات")
    print("Complete Checks System Test")
    print("🚀"*40)
    
    # إنشاء شيكات اختبارية
    create_test_checks()
    
    # عرض الملخص
    display_all_checks()
    
    print("\n✅ الاختبار اكتمل بنجاح!")

