#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to fix previous sales created from preorders
Ensures total_paid includes prepaid amount and balance_due is calculated correctly
"""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from app import create_app
from extensions import db
from models import Sale, PreOrder, Payment, PaymentDirection, PaymentStatus
from decimal import Decimal

def fix_sales_from_preorders():
    """إصلاح المبيعات السابقة من الحجوزات المسبقة"""
    app = create_app()
    
    with app.app_context():
        # البحث عن جميع المبيعات التي لها preorder_id
        sales = Sale.query.filter(Sale.preorder_id.isnot(None)).all()
        
        fixed_count = 0
        error_count = 0
        
        print(f"Found {len(sales)} sales linked to preorders")
        
        for sale in sales:
            try:
                # جلب الحجز المسبق
                preorder = PreOrder.query.get(sale.preorder_id)
                if not preorder:
                    print(f"[WARNING] Sale #{sale.id}: PreOrder #{sale.preorder_id} not found")
                    continue
                
                prepaid_amount = Decimal(str(preorder.prepaid_amount or 0))
                
                if prepaid_amount <= 0:
                    print(f"[INFO] Sale #{sale.id}: No prepaid amount (prepaid_amount = 0)")
                    continue
                
                # البحث عن Payment المرتبط بالحجز
                prepaid_payment = Payment.query.filter(
                    Payment.preorder_id == preorder.id,
                    Payment.direction == PaymentDirection.IN.value,
                    Payment.status == PaymentStatus.COMPLETED.value
                ).first()
                
                # تحديث total_paid و balance_due
                old_total_paid = Decimal(str(sale.total_paid or 0))
                old_balance_due = Decimal(str(sale.balance_due or 0))
                total_amount = Decimal(str(sale.total_amount or 0))
                
                print(f"[DEBUG] Sale #{sale.id}: total_amount={total_amount}, old_total_paid={old_total_paid}, old_balance_due={old_balance_due}, prepaid_amount={prepaid_amount}")
                
                # ربط Payment بالـ Sale إذا لم يكن مربوطاً
                if prepaid_payment:
                    needs_update = False
                    if not prepaid_payment.sale_id:
                        prepaid_payment.sale_id = sale.id
                        needs_update = True
                    if not prepaid_payment.customer_id:
                        prepaid_payment.customer_id = sale.customer_id
                        needs_update = True
                    
                    if needs_update:
                        db.session.add(prepaid_payment)
                        print(f"[OK] Sale #{sale.id}: Linked Payment #{prepaid_payment.id} to Sale")
                
                # حساب total_paid من Payments المرتبطة بالـ Sale (بعد ربط Payment)
                payments_total = db.session.query(
                    db.func.coalesce(db.func.sum(Payment.total_amount), 0)
                ).filter(
                    Payment.sale_id == sale.id,
                    Payment.direction == PaymentDirection.IN.value,
                    Payment.status == PaymentStatus.COMPLETED.value
                ).scalar() or 0
                
                payments_total_decimal = Decimal(str(payments_total))
                print(f"[DEBUG] Sale #{sale.id}: payments_total={payments_total_decimal}, prepaid_payment exists={prepaid_payment is not None}")
                
                # إذا كان total_paid لا يحتوي على العربون، نحدثه
                # الأولوية للعربون من الحجز المسبق
                if prepaid_amount > 0:
                    # إذا كان هناك Payment مرتبط بالحجز، نستخدمه
                    if prepaid_payment:
                        prepaid_payment_amount = Decimal(str(prepaid_payment.total_amount or 0))
                        # نستخدم أكبر قيمة بين payments_total و prepaid_amount
                        new_total_paid = max(payments_total_decimal, prepaid_payment_amount)
                        print(f"[DEBUG] Sale #{sale.id}: Using prepaid_payment_amount={prepaid_payment_amount}, new_total_paid={new_total_paid}")
                    else:
                        # إذا لم يكن هناك Payment، نستخدم prepaid_amount مباشرة
                        new_total_paid = max(payments_total_decimal, prepaid_amount)
                        print(f"[DEBUG] Sale #{sale.id}: Using prepaid_amount directly, new_total_paid={new_total_paid}")
                    
                    sale.total_paid = new_total_paid
                elif payments_total_decimal > 0:
                    sale.total_paid = payments_total_decimal
                    print(f"[DEBUG] Sale #{sale.id}: Using payments_total, new_total_paid={payments_total_decimal}")
                
                # حساب balance_due
                sale.balance_due = total_amount - Decimal(str(sale.total_paid or 0))
                
                # التحقق من التغييرات
                if old_total_paid != sale.total_paid or old_balance_due != sale.balance_due:
                    db.session.add(sale)
                    fixed_count += 1
                    print(f"[FIXED] Sale #{sale.id}: Updated - total_paid: {old_total_paid} -> {sale.total_paid}, balance_due: {old_balance_due} -> {sale.balance_due}")
                else:
                    print(f"[INFO] Sale #{sale.id}: No update needed (total_paid={sale.total_paid}, balance_due={sale.balance_due})")
                    
            except Exception as e:
                error_count += 1
                print(f"[ERROR] Sale #{sale.id}: {str(e)}")
                db.session.rollback()
                continue
        
        if fixed_count > 0:
            db.session.commit()
            print(f"\n[SUCCESS] Fixed {fixed_count} sales successfully")
        else:
            print(f"\n[INFO] No sales need fixing")
        
        if error_count > 0:
            print(f"[WARNING] {error_count} errors occurred")
        
        print(f"\n[COMPLETE] Fix completed")

if __name__ == "__main__":
    fix_sales_from_preorders()

