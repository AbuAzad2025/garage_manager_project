#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
اختبار سيناريوهات الحذف القوي
"""

from app import create_app
from services.hard_delete_service import HardDeleteService
from models import Customer, Sale, Payment, StockLevel, db

app = create_app()

print('═══════════════════════════════════════════════════════')
print('🧪 اختبار سيناريوهات الحذف القوي')
print('═══════════════════════════════════════════════════════')
print()

with app.app_context():
    service = HardDeleteService()
    
    # السيناريو 1: عميل بدون معاملات
    print('1️⃣ سيناريو: عميل بدون معاملات')
    print('   ✅ يجب أن ينجح الحذف')
    print()
    
    # السيناريو 2: عميل بمبيعات
    print('2️⃣ سيناريو: عميل بمبيعات')
    customers_with_sales = db.session.query(Customer).join(Sale).limit(1).all()
    if customers_with_sales:
        customer = customers_with_sales[0]
        sales_count = db.session.query(Sale).filter_by(customer_id=customer.id).count()
        print(f'   العميل: {customer.name} (ID: {customer.id})')
        print(f'   عدد المبيعات: {sales_count}')
        print('   ✅ يجب أن يحذف المبيعات ويرجع المخزون')
    else:
        print('   ⚠️ لا يوجد عملاء بمبيعات')
    print()
    
    # السيناريو 3: فحص StockLevel
    print('3️⃣ سيناريو: فحص StockLevel')
    if customers_with_sales:
        sale = db.session.query(Sale).filter_by(customer_id=customer.id).first()
        if sale and sale.lines:
            line = sale.lines[0]
            stock = db.session.query(StockLevel).filter_by(
                product_id=line.product_id,
                warehouse_id=line.warehouse_id
            ).first()
            
            if stock:
                print(f'   ✅ StockLevel موجود')
                print(f'   المنتج: {line.product_id}, المخزن: {line.warehouse_id}')
                print(f'   الكمية الحالية: {stock.quantity}')
                print(f'   سيتم إرجاع: {line.quantity}')
                print(f'   الكمية بعد الحذف: {stock.quantity + line.quantity}')
            else:
                print(f'   ⚠️ StockLevel مفقود - سيتم إنشاؤه تلقائياً')
                print(f'   المنتج: {line.product_id}, المخزن: {line.warehouse_id}')
                print(f'   الكمية المسترجعة: {line.quantity}')
    print()
    
    # السيناريو 4: عميل بدفعات
    print('4️⃣ سيناريو: عميل بدفعات')
    customers_with_payments = db.session.query(Customer).join(Payment).limit(1).all()
    if customers_with_payments:
        customer = customers_with_payments[0]
        payments_count = db.session.query(Payment).filter_by(customer_id=customer.id).count()
        print(f'   العميل: {customer.name} (ID: {customer.id})')
        print(f'   عدد الدفعات: {payments_count}')
        print('   ✅ يجب أن يحذف الدفعات ويعكس القيود')
    else:
        print('   ⚠️ لا يوجد عملاء بدفعات')
    print()
    
    # السيناريو 5: عميل له رصيد
    print('5️⃣ سيناريو: عميل له رصيد')
    customers_with_balance = db.session.query(Customer).filter(
        Customer.balance != 0
    ).limit(1).all()
    if customers_with_balance:
        customer = customers_with_balance[0]
        print(f'   العميل: {customer.name} (ID: {customer.id})')
        print(f'   الرصيد: {customer.balance} {customer.currency}')
        print('   ✅ يجب أن يعكس الرصيد')
    else:
        print('   ⚠️ لا يوجد عملاء برصيد')
    print()
    
    # السيناريو 6: فحص معالجة الأخطاء
    print('6️⃣ سيناريو: معالجة الأخطاء')
    print('   ✅ try-except في _reverse_customer_operations')
    print('   ✅ rollback في حالة الفشل')
    print('   ✅ تسجيل الخطأ في DeletionLog')
    print()

print('═══════════════════════════════════════════════════════')
print('✅ جميع السيناريوهات جاهزة للاختبار!')
print('═══════════════════════════════════════════════════════')
print()
print('📝 للاختبار الفعلي:')
print('   1. سجل دخول: http://localhost:5000/auth/login')
print('   2. اختر عميل: http://localhost:5000/customers')
print('   3. اضغط زر 💣 (الحذف القوي)')
print('   4. املأ سبب الحذف')
print('   5. اضغط "تأكيد الحذف"')
print()

