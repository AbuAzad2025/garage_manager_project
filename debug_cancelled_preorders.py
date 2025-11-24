# -*- coding: utf-8 -*-
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from decimal import Decimal
from app import create_app
from models import PreOrder, Payment
from extensions import db

app = create_app()
customer_id = 37

with app.app_context():
    print("=" * 80)
    print(f"الحجوزات الملغاة للعميل #{customer_id}")
    print("=" * 80)
    
    cancelled_preorders = db.session.query(PreOrder).outerjoin(
        Payment, db.and_(
            Payment.preorder_id == PreOrder.id,
            Payment.direction == 'IN',
            Payment.status.in_(['COMPLETED', 'PENDING'])
        )
    ).filter(
        PreOrder.customer_id == customer_id,
        PreOrder.status == 'CANCELLED',
        PreOrder.prepaid_amount > 0,
        db.or_(Payment.id.is_(None), Payment.id == None)
    ).all()
    
    print(f"\nعدد الحجوزات الملغاة بدون دفعات: {len(cancelled_preorders)}")
    
    for preorder in cancelled_preorders:
        print(f"\nحجز #{preorder.id}:")
        print(f"   الحالة: {preorder.status}")
        print(f"   prepaid_amount: {preorder.prepaid_amount}")
        print(f"   total_amount: {preorder.total_amount}")
        print(f"   reference: {preorder.reference}")
        print(f"   created_at: {preorder.created_at}")
    
    print("\n" + "=" * 80)

