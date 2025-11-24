# -*- coding: utf-8 -*-
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from decimal import Decimal
from app import create_app
from models import PreOrder, Payment, Sale
from extensions import db

app = create_app()
preorder_id = 1

with app.app_context():
    print("=" * 80)
    print(f"تشخيص حجز #{preorder_id}")
    print("=" * 80)
    
    preorder = db.session.get(PreOrder, preorder_id)
    if not preorder:
        print(f"الحجز #{preorder_id} غير موجود!")
        exit(1)
    
    print(f"\nمعلومات الحجز:")
    print(f"   الحالة: {preorder.status}")
    print(f"   prepaid_amount: {preorder.prepaid_amount}")
    print(f"   total_amount: {preorder.total_amount}")
    print(f"   customer_id: {preorder.customer_id}")
    print(f"   currency: {preorder.currency}")
    
    print(f"\nالدفعات المرتبطة بالحجز:")
    payments = db.session.query(Payment).filter(
        Payment.preorder_id == preorder_id
    ).all()
    
    if not payments:
        print("   لا توجد دفعات مرتبطة بالحجز!")
    else:
        for payment in payments:
            print(f"\n   دفعة #{payment.id}:")
            print(f"      المبلغ: {payment.total_amount}")
            print(f"      sale_id: {payment.sale_id}")
            print(f"      preorder_id: {payment.preorder_id}")
            print(f"      direction: {payment.direction}")
            print(f"      status: {payment.status}")
    
    print(f"\nالمبيعات المرتبطة بالحجز:")
    sales = db.session.query(Sale).filter(
        Sale.preorder_id == preorder_id
    ).all()
    
    if not sales:
        print("   لا توجد مبيعات مرتبطة بالحجز!")
    else:
        for sale in sales:
            print(f"\n   مبيعة #{sale.id}:")
            print(f"      رقم المبيعة: {sale.sale_number}")
            print(f"      الحالة: {sale.status}")
            print(f"      total_amount: {sale.total_amount}")
            print(f"      total_paid: {sale.total_paid}")
    
    print("\n" + "=" * 80)

