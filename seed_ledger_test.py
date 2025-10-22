#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
seed data للدفتر - مبيعات، صيانة، حجوزات، نفقات
"""

from app import create_app
from extensions import db
from models import (
    Sale, SaleLine, ServiceRequest, PreOrder, Expense,
    Customer, Product, StockLevel, Warehouse, User
)
from datetime import datetime, timedelta
from decimal import Decimal

app = create_app()

with app.app_context():
    print("\n" + "="*70)
    print("🌱 إنشاء بيانات تجريبية للدفتر")
    print("="*70)
    
    # جلب بيانات موجودة
    user = User.query.first()
    customer = Customer.query.first()
    
    if not customer:
        print("❌ لا يوجد عملاء! أضف عميل أولاً")
        exit(1)
    
    product = Product.query.first()
    warehouse = Warehouse.query.first()
    
    if not product or not warehouse:
        print("❌ لا يوجد منتجات أو مستودعات!")
        exit(1)
    
    print(f"\n✅ العميل: {customer.name}")
    print(f"✅ المنتج: {product.name} - {product.price} ₪")
    print(f"✅ المستودع: {warehouse.name}")
    
    # 1. إنشاء مبيعة
    print("\n📦 إنشاء مبيعة...")
    sale = Sale(
        sale_number=f"SAL-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        sale_date=datetime.now(),
        customer_id=customer.id,
        subtotal=Decimal('1000.00'),
        tax_rate=Decimal('0.00'),
        tax_amount=Decimal('0.00'),
        discount_amount=Decimal('0.00'),
        total_amount=Decimal('1000.00'),
        amount_paid=Decimal('0.00'),
        balance_due=Decimal('1000.00'),
        currency='ILS',
        status='CONFIRMED',
        payment_status='UNPAID',
        created_by=user.id if user else 1
    )
    db.session.add(sale)
    db.session.flush()
    
    # إضافة سطر مبيعة
    sale_line = SaleLine(
        sale_id=sale.id,
        product_id=product.id,
        warehouse_id=warehouse.id,
        quantity=2,
        unit_price=Decimal('500.00'),
        subtotal=Decimal('1000.00'),
        tax_rate=Decimal('0.00'),
        tax_amount=Decimal('0.00'),
        total=Decimal('1000.00')
    )
    db.session.add(sale_line)
    print(f"✅ مبيعة: {sale.sale_number} - {sale.total_amount} ₪")
    
    # 2. إنشاء صيانة
    print("\n🔧 إنشاء صيانة...")
    service = ServiceRequest(
        service_number=f"SRV-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        customer_id=customer.id,
        description="صيانة تجريبية",
        parts_total=Decimal('500.00'),
        labor_total=Decimal('300.00'),
        discount_total=Decimal('0.00'),
        tax_rate=Decimal('0.00'),
        status='COMPLETED',
        created_by=user.id if user else 1,
        created_at=datetime.now()
    )
    db.session.add(service)
    print(f"✅ صيانة: {service.service_number} - قطع: 500 + عمالة: 300 = 800 ₪")
    
    # 3. إنشاء حجز مسبق
    print("\n📅 إنشاء حجز مسبق...")
    preorder = PreOrder(
        preorder_number=f"PRE-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        customer_id=customer.id,
        warehouse_id=warehouse.id,
        total_amount=Decimal('2000.00'),
        deposit_amount=Decimal('500.00'),
        status='PENDING',
        currency='ILS',
        created_by=user.id if user else 1,
        created_at=datetime.now()
    )
    db.session.add(preorder)
    print(f"✅ حجز مسبق: {preorder.preorder_number} - {preorder.total_amount} ₪")
    
    # 4. إنشاء نفقة
    print("\n💰 إنشاء نفقة...")
    expense = Expense(
        description="مصروف تجريبي - إيجار",
        amount=Decimal('3000.00'),
        date=datetime.now().date(),
        currency='ILS',
        created_by=user.id if user else 1
    )
    db.session.add(expense)
    print(f"✅ نفقة: {expense.description} - {expense.amount} ₪")
    
    # حفظ كل شيء
    db.session.commit()
    
    print("\n" + "="*70)
    print("✅ تم إنشاء البيانات بنجاح!")
    print("="*70)
    print("\n📊 الملخص:")
    print(f"   - مبيعة: 1,000 ₪")
    print(f"   - صيانة: 800 ₪")
    print(f"   - حجز مسبق: 2,000 ₪")
    print(f"   - نفقة: 3,000 ₪")
    print(f"\n💰 المتوقع في الدفتر:")
    print(f"   - الإيرادات: 1,000 + 800 + 2,000 = 3,800 ₪")
    print(f"   - النفقات: 3,000 ₪")
    print(f"   - الربح: 3,800 - 3,000 = 800 ₪")
    print("\n🎯 افتح الدفتر الآن: http://localhost:5000/ledger/")
    print("="*70 + "\n")

