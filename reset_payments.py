#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""حذف الدفعات TEST وإعادة seed"""

from app import app, db
from models import Payment, PaymentSplit

with app.app_context():
    print("\n" + "="*80)
    print("حذف الدفعات TEST")
    print("="*80 + "\n")
    
    # حذف PaymentSplits أولاً
    splits_deleted = db.session.query(PaymentSplit).filter(
        PaymentSplit.payment_id.in_(
            db.session.query(Payment.id).filter(
                Payment.notes.like('%TEST%')
            )
        )
    ).delete(synchronize_session=False)
    
    print(f"✓ حذف {splits_deleted} split")
    
    # حذف Payments
    payments_deleted = db.session.query(Payment).filter(
        Payment.notes.like('%TEST%')
    ).delete(synchronize_session=False)
    
    print(f"✓ حذف {payments_deleted} دفعة")
    
    db.session.commit()
    
    print("\n" + "="*80)
    print("✅ تم حذف جميع الدفعات TEST")
    print("="*80 + "\n")

