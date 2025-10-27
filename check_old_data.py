#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
فحص البيانات القديمة - هل تحتاج تحديث؟
"""
from app import app, db
from models import Invoice, Sale, Payment, GLBatch, Customer, Supplier, Partner
from sqlalchemy import func

def check_old_data():
    with app.app_context():
        print("\n" + "="*60)
        print("🔍 فحص البيانات القديمة")
        print("="*60 + "\n")
        
        # 1. فحص الفواتير
        total_invoices = Invoice.query.count()
        invoices_with_gl = db.session.query(func.count(func.distinct(GLBatch.invoice_id)))\
            .filter(GLBatch.invoice_id.isnot(None)).scalar() or 0
        invoices_without_gl = total_invoices - invoices_with_gl
        
        print(f"📄 الفواتير:")
        print(f"   إجمالي: {total_invoices}")
        print(f"   لها قيود GL: {invoices_with_gl} ✅")
        print(f"   بدون قيود GL: {invoices_without_gl} {'❌' if invoices_without_gl > 0 else '✅'}")
        print()
        
        # 2. فحص المبيعات
        total_sales = Sale.query.count()
        sales_with_gl = db.session.query(func.count(func.distinct(GLBatch.sale_id)))\
            .filter(GLBatch.sale_id.isnot(None)).scalar() or 0
        sales_without_gl = total_sales - sales_with_gl
        
        print(f"🛒 المبيعات:")
        print(f"   إجمالي: {total_sales}")
        print(f"   لها قيود GL: {sales_with_gl} ✅")
        print(f"   بدون قيود GL: {sales_without_gl} {'❌' if sales_without_gl > 0 else '✅'}")
        print()
        
        # 3. فحص الدفعات
        total_payments = Payment.query.count()
        payments_with_gl = db.session.query(func.count(func.distinct(GLBatch.payment_id)))\
            .filter(GLBatch.payment_id.isnot(None)).scalar() or 0
        payments_without_gl = total_payments - payments_with_gl
        
        print(f"💰 الدفعات:")
        print(f"   إجمالي: {total_payments}")
        print(f"   لها قيود GL: {payments_with_gl} ✅")
        print(f"   بدون قيود GL: {payments_without_gl} {'❌' if payments_without_gl > 0 else '✅'}")
        print()
        
        # 4. فحص العملاء
        customers_count = Customer.query.count()
        print(f"👥 العملاء: {customers_count}")
        if customers_count > 0:
            sample_customer = Customer.query.first()
            print(f"   مثال: {sample_customer.name} - الرصيد: {sample_customer.balance:.2f} ₪")
        print()
        
        # 5. فحص الموردين
        suppliers_count = Supplier.query.count()
        print(f"🏭 الموردين: {suppliers_count}")
        if suppliers_count > 0:
            sample_supplier = Supplier.query.first()
            print(f"   مثال: {sample_supplier.name} - الرصيد: {sample_supplier.balance:.2f} ₪")
        print()
        
        # 6. فحص الشركاء
        partners_count = Partner.query.count()
        print(f"🤝 الشركاء: {partners_count}")
        if partners_count > 0:
            sample_partner = Partner.query.first()
            print(f"   مثال: {sample_partner.name} - الرصيد: {sample_partner.balance:.2f} ₪")
        print()
        
        # الخلاصة
        print("="*60)
        needs_update = (invoices_without_gl > 0 or 
                       sales_without_gl > 0 or 
                       payments_without_gl > 0)
        
        if needs_update:
            print("⚠️  تحتاج لتحديث البيانات القديمة!")
            print("   بعض المعاملات بدون قيود GL")
        else:
            print("✅ البيانات سليمة - لا حاجة للتحديث!")
        print("="*60 + "\n")

if __name__ == '__main__':
    check_old_data()

