#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚨 فحص عاجل: أين الدفعات؟
"""
from app import app, db
from models import Payment, Invoice, Sale, Customer
from sqlalchemy import func

def check_payments():
    with app.app_context():
        print("\n" + "="*70)
        print("🚨 فحص عاجل: الدفعات")
        print("="*70 + "\n")
        
        # 1. عدد الدفعات الكلي
        total_payments = Payment.query.count()
        print(f"💰 إجمالي الدفعات في الجدول: {total_payments}")
        
        if total_payments == 0:
            print("❌ لا توجد دفعات في الجدول!")
            print("   هذه مشكلة خطيرة - البيانات فُقدت!")
            print("\n" + "="*70)
            return
        
        print()
        
        # 2. الدفعات حسب النوع
        customer_payments = Payment.query.filter(Payment.customer_id.isnot(None)).count()
        supplier_payments = Payment.query.filter(Payment.supplier_id.isnot(None)).count()
        partner_payments = Payment.query.filter(Payment.partner_id.isnot(None)).count()
        
        print("📊 تصنيف الدفعات:")
        print(f"   - دفعات العملاء: {customer_payments}")
        print(f"   - دفعات الموردين: {supplier_payments}")
        print(f"   - دفعات الشركاء: {partner_payments}")
        print()
        
        # 3. الدفعات المرتبطة بالفواتير
        invoice_payments = Payment.query.filter(Payment.invoice_id.isnot(None)).count()
        print(f"📄 دفعات مرتبطة بفواتير: {invoice_payments}")
        
        # 4. الدفعات المرتبطة بالمبيعات
        sale_payments = Payment.query.filter(Payment.sale_id.isnot(None)).count()
        print(f"🛒 دفعات مرتبطة بمبيعات: {sale_payments}")
        print()
        
        # 5. أمثلة
        print("📝 أمثلة على الدفعات:")
        sample_payments = Payment.query.limit(5).all()
        for p in sample_payments:
            entity = "عميل" if p.customer_id else "مورد" if p.supplier_id else "شريك" if p.partner_id else "؟"
            linked = ""
            if p.invoice_id:
                linked = f" → فاتورة #{p.invoice_id}"
            elif p.sale_id:
                linked = f" → مبيعة #{p.sale_id}"
            print(f"   - دفعة #{p.id} ({entity}): {p.total_amount} ₪ - {p.status}{linked}")
        print()
        
        # 6. التحقق من الفواتير
        total_invoices = Invoice.query.count()
        print(f"📄 إجمالي الفواتير: {total_invoices}")
        
        if total_invoices > 0:
            sample_invoice = Invoice.query.first()
            invoice_payments_count = Payment.query.filter(Payment.invoice_id == sample_invoice.id).count()
            print(f"   مثال: فاتورة #{sample_invoice.id} لها {invoice_payments_count} دفعة")
            print(f"   - إجمالي الفاتورة: {sample_invoice.total_amount} ₪")
            print(f"   - المبلغ المدفوع: {sample_invoice.total_paid} ₪")
            print(f"   - الحالة: {sample_invoice.status}")
        print()
        
        # 7. التحقق من العملاء
        customers_with_payments = db.session.query(func.count(func.distinct(Payment.customer_id)))\
            .filter(Payment.customer_id.isnot(None)).scalar() or 0
        print(f"👥 عدد العملاء الذين لهم دفعات: {customers_with_payments}")
        
        print("\n" + "="*70)
        
        if total_payments > 0:
            print("✅ الدفعات موجودة في قاعدة البيانات")
            print("   إذا لم تظهر في الواجهة، المشكلة في الكود وليس البيانات")
        else:
            print("❌ البيانات فُقدت - نحتاج استعادة من Backup!")
        
        print("="*70 + "\n")

if __name__ == '__main__':
    check_payments()

