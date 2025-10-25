#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
إصلاح total_paid لجميع الفواتير
"""

from app import create_app
from models import Sale, Payment, PaymentStatus, PaymentDirection, db
from sqlalchemy import func

app = create_app()

with app.app_context():
    print('═══════════════════════════════════════════════════════')
    print('🔧 إعادة حساب total_paid لجميع الفواتير')
    print('═══════════════════════════════════════════════════════')
    print()
    
    # جلب جميع الفواتير
    sales = Sale.query.all()
    fixed_count = 0
    
    for sale in sales:
        # حساب total_paid الحقيقي من الدفعات
        actual_paid = db.session.query(
            func.coalesce(func.sum(Payment.total_amount), 0)
        ).filter(
            Payment.sale_id == sale.id,
            Payment.status == PaymentStatus.COMPLETED,
            Payment.direction == PaymentDirection.IN
        ).scalar() or 0
        
        old_paid = float(sale.total_paid or 0)
        new_paid = float(actual_paid)
        
        # إذا مختلف، نحدّث
        if abs(old_paid - new_paid) > 0.01:  # فرق أكثر من 1 فلس
            print(f'📋 {sale.sale_number}:')
            print(f'   قديم: {old_paid} → جديد: {new_paid}')
            
            sale.total_paid = new_paid
            sale.balance_due = float(sale.total_amount or 0) - new_paid
            
            # تحديث payment_status
            if new_paid >= float(sale.total_amount or 0):
                sale.payment_status = 'PAID'
            elif new_paid > 0:
                sale.payment_status = 'PARTIAL'
            else:
                sale.payment_status = 'PENDING'
            
            fixed_count += 1
    
    if fixed_count > 0:
        db.session.commit()
        print()
        print(f'✅ تم تحديث {fixed_count} فاتورة!')
    else:
        print('✅ جميع الفواتير صحيحة!')
    
    print()
    print('═══════════════════════════════════════════════════════')

