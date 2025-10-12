#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""فحص شيكات PaymentSplit"""

from app import app, db
from models import PaymentSplit, Payment, PaymentMethod

with app.app_context():
    print('\n' + '='*80)
    print('🔍 فحص الشيكات في PaymentSplit')
    print('='*80)
    
    # جلب جميع الـ splits بشيكات
    splits = PaymentSplit.query.filter_by(method=PaymentMethod.CHEQUE.value).all()
    
    print(f'\n📊 عدد الشيكات في PaymentSplit: {len(splits)}')
    
    if len(splits) == 0:
        print('\n⚠️ لا توجد شيكات في PaymentSplit!')
    else:
        print('-' * 80)
        
        for i, split in enumerate(splits, 1):
            print(f'\n{i}. PaymentSplit #{split.id}:')
            print(f'   payment_id: {split.payment_id}')
            print(f'   amount: {split.amount}')
            print(f'   method: {split.method}')
            
            # الدفعة الأصلية
            if split.payment:
                print(f'   Payment:')
                print(f'     - رقم: {split.payment.payment_number}')
                print(f'     - اتجاه: {split.payment.direction}')
                print(f'     - عملة: {split.payment.currency}')
            
            # معلومات الشيك من details
            if split.details:
                print(f'   معلومات الشيك (من details):')
                for key, val in split.details.items():
                    print(f'     - {key}: {val}')
            else:
                print(f'   ⚠️ details فارغ!')
    
    print('\n' + '='*80)

