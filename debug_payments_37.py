# -*- coding: utf-8 -*-
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from decimal import Decimal
from app import create_app
from models import Payment, PreOrder, Sale
from extensions import db

app = create_app()
customer_id = 37

with app.app_context():
    print("=" * 80)
    print(f"جميع الدفعات للعميل #{customer_id}")
    print("=" * 80)
    
    # جميع الدفعات الواردة
    all_payments = db.session.query(Payment).filter(
        Payment.customer_id == customer_id,
        Payment.direction == 'IN'
    ).all()
    
    print(f"\nإجمالي الدفعات الواردة: {len(all_payments)}")
    
    for payment in all_payments:
        print(f"\nدفعة #{payment.id}:")
        print(f"   المبلغ: {payment.total_amount}")
        print(f"   preorder_id: {payment.preorder_id}")
        print(f"   sale_id: {payment.sale_id}")
        print(f"   entity_type: {payment.entity_type}")
        print(f"   status: {payment.status}")
        print(f"   payment_date: {payment.payment_date}")
        print(f"   reference: {payment.reference}")
        print(f"   notes: {payment.notes}")
    
    # الدفعات المرتبطة بالحجوزات
    print(f"\n" + "=" * 80)
    print("الدفعات المرتبطة بالحجوزات:")
    payments_from_preorders = db.session.query(Payment).join(
        PreOrder, Payment.preorder_id == PreOrder.id
    ).filter(
        PreOrder.customer_id == customer_id,
        Payment.direction == 'IN',
        Payment.status.in_(['COMPLETED', 'PENDING'])
    ).all()
    
    print(f"عدد الدفعات المرتبطة بالحجوزات: {len(payments_from_preorders)}")
    for payment in payments_from_preorders:
        print(f"\nدفعة #{payment.id}:")
        print(f"   المبلغ: {payment.total_amount}")
        print(f"   preorder_id: {payment.preorder_id}")
        print(f"   sale_id: {payment.sale_id}")
        print(f"   preorder.status: {payment.preorder.status if payment.preorder else 'N/A'}")
    
    # الحجوزات بدون دفعات
    print(f"\n" + "=" * 80)
    print("الحجوزات بدون دفعات مرتبطة:")
    preorders_without_payments = db.session.query(PreOrder).outerjoin(
        Payment, db.and_(
            Payment.preorder_id == PreOrder.id,
            Payment.direction == 'IN',
            Payment.status.in_(['COMPLETED', 'PENDING'])
        )
    ).filter(
        PreOrder.customer_id == customer_id,
        PreOrder.status != 'CANCELLED',
        PreOrder.prepaid_amount > 0,
        db.or_(Payment.id.is_(None), Payment.id == None)
    ).all()
    
    print(f"عدد الحجوزات بدون دفعات: {len(preorders_without_payments)}")
    for preorder in preorders_without_payments:
        print(f"\nحجز #{preorder.id}:")
        print(f"   الحالة: {preorder.status}")
        print(f"   prepaid_amount: {preorder.prepaid_amount}")
        print(f"   total_amount: {preorder.total_amount}")
        
        # التحقق من وجود مبيعة مرتبطة
        sale = db.session.query(Sale).filter(Sale.preorder_id == preorder.id).first()
        if sale:
            print(f"   مبيعة مرتبطة: #{sale.id} - total_amount: {sale.total_amount}, total_paid: {sale.total_paid}")
    
    print("\n" + "=" * 80)

