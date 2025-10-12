#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""اختبار API الشيكات"""

from app import app, db
from models import Payment, PaymentMethod, PaymentSplit
from datetime import datetime

with app.app_context():
    print("\n" + "="*80)
    print("فحص الشيكات في قاعدة البيانات")
    print("="*80 + "\n")
    
    # 1. الشيكات العادية
    print("1️⃣ شيكات عادية (Payment.method = CHEQUE):")
    print("-" * 80)
    
    regular_checks = Payment.query.filter(
        Payment.method == PaymentMethod.CHEQUE.value
    ).all()
    
    print(f"   العدد: {len(regular_checks)}")
    for p in regular_checks[:5]:
        print(f"   • {p.payment_number}: {p.check_number} - {p.total_amount} {p.currency}")
        print(f"     الاستحقاق: {p.check_due_date}")
        print(f"     الحالة: {p.status}")
        print(f"     الاتجاه: {p.direction}")
        print()
    
    # 2. الشيكات الجزئية
    print("\n2️⃣ شيكات جزئية (PaymentSplit.method = CHEQUE):")
    print("-" * 80)
    
    split_checks = PaymentSplit.query.filter(
        PaymentSplit.method == PaymentMethod.CHEQUE.value
    ).all()
    
    print(f"   العدد: {len(split_checks)}")
    for s in split_checks[:5]:
        print(f"   • Split #{s.id}: {s.amount}")
        print(f"     الدفعة: {s.payment_id}")
        print(f"     Details: {s.details}")
        print()
    
    # 3. اختبار الـ API endpoint مباشرة
    print("\n3️⃣ اختبار get_checks logic:")
    print("-" * 80)
    
    # محاكاة الكود من get_checks
    from models import PaymentDirection, PaymentStatus
    
    checks = []
    today = datetime.utcnow().date()
    
    # الشيكات العادية
    for payment in regular_checks[:3]:
        if not payment.check_due_date:
            print(f"   ⚠️ {payment.payment_number} - لا يوجد تاريخ استحقاق!")
            continue
        
        due_date = payment.check_due_date.date() if isinstance(payment.check_due_date, datetime) else payment.check_due_date
        days_until_due = (due_date - today).days
        
        print(f"   ✓ {payment.payment_number}:")
        print(f"     - رقم الشيك: {payment.check_number}")
        print(f"     - البنك: {payment.check_bank}")
        print(f"     - الاستحقاق: {due_date} ({days_until_due} يوم)")
    
    print("\n" + "="*80)

