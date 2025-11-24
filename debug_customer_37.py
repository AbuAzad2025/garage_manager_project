# -*- coding: utf-8 -*-
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from decimal import Decimal
from sqlalchemy import func, and_, or_
from app import create_app
from models import (
    Customer, Sale, PreOrder, Payment, SaleLine,
    SaleStatus, PaymentStatus, PaymentDirection
)
from extensions import db
from utils.balance_calculator import calculate_customer_balance_components
from utils.customer_balance_updater import update_customer_balance_components

app = create_app()
customer_id = 37

with app.app_context():
    print("=" * 80)
    print(f"تشخيص رصيد العميل #{customer_id}")
    print("=" * 80)
    
    customer = db.session.get(Customer, customer_id)
    if not customer:
        print(f"العميل #{customer_id} غير موجود!")
        exit(1)
    
    print(f"\nمعلومات العميل:")
    print(f"   الاسم: {customer.name}")
    print(f"   الرصيد الحالي في قاعدة البيانات: {customer.current_balance}")
    print(f"   sales_balance في قاعدة البيانات: {customer.sales_balance}")
    print(f"   payments_in_balance في قاعدة البيانات: {customer.payments_in_balance}")
    print(f"   preorders_balance في قاعدة البيانات: {customer.preorders_balance}")
    
    print(f"\nالمبيعات من الحجوزات المسبقة:")
    sales_from_preorders = db.session.query(Sale).filter(
        Sale.customer_id == customer_id,
        Sale.preorder_id.isnot(None)
    ).all()
    
    if not sales_from_preorders:
        print("   لا توجد مبيعات من حجوزات مسبقة!")
    else:
        total_sales_from_preorders = Decimal('0.00')
        for sale in sales_from_preorders:
            print(f"\n   مبيعة #{sale.id}:")
            print(f"      رقم المبيعة: {sale.sale_number}")
            print(f"      الحالة: {sale.status}")
            print(f"      total_amount: {sale.total_amount}")
            print(f"      total_paid: {sale.total_paid}")
            print(f"      preorder_id: {sale.preorder_id}")
            print(f"      currency: {sale.currency}")
            
            if sale.status == 'CONFIRMED':
                if sale.currency == 'ILS':
                    total_sales_from_preorders += Decimal(str(sale.total_amount or 0))
                else:
                    try:
                        from models import convert_amount
                        amt = convert_amount(Decimal(str(sale.total_amount or 0)), sale.currency, "ILS", sale.sale_date)
                        total_sales_from_preorders += amt
                    except Exception as e:
                        print(f"      خطأ في تحويل العملة: {e}")
            else:
                print(f"      المبيعة ليست بحالة CONFIRMED!")
        
        print(f"\n   إجمالي المبيعات من الحجوزات (CONFIRMED): {total_sales_from_preorders}")
    
    print(f"\nجميع المبيعات (CONFIRMED):")
    all_confirmed_sales = db.session.query(Sale).filter(
        Sale.customer_id == customer_id,
        Sale.status == 'CONFIRMED'
    ).all()
    
    total_all_sales = Decimal('0.00')
    for sale in all_confirmed_sales:
        if sale.currency == 'ILS':
            total_all_sales += Decimal(str(sale.total_amount or 0))
        else:
            try:
                from models import convert_amount
                amt = convert_amount(Decimal(str(sale.total_amount or 0)), sale.currency, "ILS", sale.sale_date)
                total_all_sales += amt
            except Exception:
                pass
    
    print(f"   إجمالي جميع المبيعات (CONFIRMED): {total_all_sales}")
    
    print(f"\nالعربونات من الحجوزات المسبقة:")
    preorders = db.session.query(PreOrder).filter(
        PreOrder.customer_id == customer_id,
        PreOrder.status != 'CANCELLED'
    ).all()
    
    total_prepaid = Decimal('0.00')
    for preorder in preorders:
        print(f"\n   حجز #{preorder.id}:")
        print(f"      الحالة: {preorder.status}")
        print(f"      prepaid_amount: {preorder.prepaid_amount}")
        print(f"      total_amount: {preorder.total_amount}")
        
        prepaid_payments = db.session.query(Payment).filter(
            Payment.preorder_id == preorder.id,
            Payment.direction == PaymentDirection.IN.value,
            Payment.status.in_([PaymentStatus.COMPLETED.value, PaymentStatus.PENDING.value])
        ).all()
        
        for payment in prepaid_payments:
            print(f"      دفعة #{payment.id}:")
            print(f"         المبلغ: {payment.total_amount}")
            print(f"         sale_id: {payment.sale_id}")
            print(f"         preorder_id: {payment.preorder_id}")
            print(f"         الحالة: {payment.status}")
            
            if payment.currency == 'ILS':
                total_prepaid += Decimal(str(payment.total_amount or 0))
            else:
                try:
                    from models import convert_amount
                    amt = convert_amount(Decimal(str(payment.total_amount or 0)), payment.currency, "ILS", payment.payment_date)
                    total_prepaid += amt
                except Exception:
                    pass
    
    print(f"\n   إجمالي العربونات: {total_prepaid}")
    
    print(f"\nحساب المكونات من balance_calculator:")
    components = calculate_customer_balance_components(customer_id, db.session)
    if components:
        print(f"   sales_balance المحسوب: {components.get('sales_balance', 0)}")
        print(f"   payments_in_balance المحسوب: {components.get('payments_in_balance', 0)}")
        print(f"   preorders_balance المحسوب: {components.get('preorders_balance', 0)}")
        
        calculated_balance = (
            Decimal(str(customer.opening_balance or 0)) +
            Decimal(str(components.get('payments_in_balance', 0))) +
            Decimal(str(components.get('returns_balance', 0))) +
            Decimal(str(components.get('returned_checks_out_balance', 0))) +
            Decimal(str(components.get('service_expenses_balance', 0))) -
            Decimal(str(components.get('sales_balance', 0))) -
            Decimal(str(components.get('invoices_balance', 0))) -
            Decimal(str(components.get('services_balance', 0))) -
            Decimal(str(components.get('preorders_balance', 0))) -
            Decimal(str(components.get('online_orders_balance', 0))) -
            Decimal(str(components.get('payments_out_balance', 0))) -
            Decimal(str(components.get('returned_checks_in_balance', 0))) -
            Decimal(str(components.get('expenses_balance', 0)))
        )
        
        print(f"\n   الرصيد المحسوب: {calculated_balance}")
        print(f"   الرصيد في قاعدة البيانات: {customer.current_balance}")
        print(f"   الفرق: {calculated_balance - Decimal(str(customer.current_balance or 0))}")
    
    print(f"\nتحديث الرصيد...")
    try:
        update_customer_balance_components(customer_id, db.session)
        db.session.commit()
        db.session.refresh(customer)
        print(f"   تم التحديث")
        print(f"   الرصيد الجديد: {customer.current_balance}")
        print(f"   sales_balance الجديد: {customer.sales_balance}")
        print(f"   payments_in_balance الجديد: {customer.payments_in_balance}")
        print(f"   preorders_balance الجديد: {customer.preorders_balance}")
    except Exception as e:
        print(f"   خطأ في التحديث: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
