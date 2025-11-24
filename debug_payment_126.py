# -*- coding: utf-8 -*-
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from decimal import Decimal
from app import create_app
from models import Payment, PreOrder
from extensions import db

app = create_app()
payment_id = 126

with app.app_context():
    print("=" * 80)
    print(f"تفاصيل دفعة #{payment_id}")
    print("=" * 80)
    
    payment = db.session.get(Payment, payment_id)
    if not payment:
        print(f"الدفعة #{payment_id} غير موجودة!")
        exit(1)
    
    print(f"\nمعلومات الدفعة:")
    print(f"   المبلغ: {payment.total_amount}")
    print(f"   preorder_id: {payment.preorder_id}")
    print(f"   sale_id: {payment.sale_id}")
    print(f"   direction: {payment.direction}")
    print(f"   status: {payment.status}")
    print(f"   entity_type: {payment.entity_type}")
    print(f"   reference: {payment.reference}")
    print(f"   notes: {payment.notes}")
    
    if payment.preorder_id:
        preorder = db.session.get(PreOrder, payment.preorder_id)
        if preorder:
            print(f"\nمعلومات الحجز المرتبط:")
            print(f"   الحالة: {preorder.status}")
            print(f"   prepaid_amount: {preorder.prepaid_amount}")
            print(f"   total_amount: {preorder.total_amount}")
            print(f"   reference: {preorder.reference}")
    
    print("\n" + "=" * 80)

