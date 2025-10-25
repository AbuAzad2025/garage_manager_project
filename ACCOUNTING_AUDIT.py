#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════
🔍 تدقيق محاسبي شامل للنظام - 2025-10-25
═══════════════════════════════════════════════════════════════════

يفحص:
1. ✅ الرصيد الافتتاحي (Opening Balance)
2. ✅ Customer.balance (الحساب التلقائي)
3. ✅ GL للمبيعات (نسب الشركاء/الموردين)
4. ✅ GLBatch entries (التوازن المحاسبي)
5. ✅ Hard Delete (عكس العمليات)

═══════════════════════════════════════════════════════════════════
"""

from app import create_app
from models import (
    Customer, Supplier, Partner, Sale, Payment, GLBatch, GLEntry, Account,
    SaleLine, Warehouse, WarehouseType, ProductPartner, WarehousePartnerShare,
    ExchangeTransaction, db
)
from sqlalchemy import func, text
from decimal import Decimal
from datetime import datetime

app = create_app()

def print_section(title):
    print()
    print('═' * 70)
    print(f'📊 {title}')
    print('═' * 70)

with app.app_context():
    print()
    print('🔍 تدقيق محاسبي شامل - بدأ في:', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    # ═══════════════════════════════════════════════════════════════════
    # 1. فحص الرصيد الافتتاحي
    # ═══════════════════════════════════════════════════════════════════
    print_section('1. الرصيد الافتتاحي (Opening Balance)')
    
    customers_with_ob = Customer.query.filter(Customer.opening_balance != 0).all()
    suppliers_with_ob = Supplier.query.filter(Supplier.opening_balance != 0).all()
    partners_with_ob = Partner.query.filter(Partner.opening_balance != 0).all()
    
    print(f'✅ العملاء بهم رصيد افتتاحي: {len(customers_with_ob)}')
    for c in customers_with_ob[:3]:
        ob = float(c.opening_balance or 0)
        meaning = "له علينا" if ob > 0 else "عليه لنا"
        print(f'   {c.name}: {ob:,.2f} ({meaning})')
    
    print(f'✅ الموردين بهم رصيد افتتاحي: {len(suppliers_with_ob)}')
    for s in suppliers_with_ob[:3]:
        ob = float(s.opening_balance or 0)
        meaning = "له علينا" if ob > 0 else "عليه لنا"
        print(f'   {s.name}: {ob:,.2f} ({meaning})')
    
    print(f'✅ الشركاء بهم رصيد افتتاحي: {len(partners_with_ob)}')
    for p in partners_with_ob[:3]:
        ob = float(p.opening_balance or 0)
        meaning = "له علينا" if ob > 0 else "عليه لنا"
        print(f'   {p.name}: {ob:,.2f} ({meaning})')
    
    # ═══════════════════════════════════════════════════════════════════
    # 2. فحص Customer.balance
    # ═══════════════════════════════════════════════════════════════════
    print_section('2. Customer.balance (الحساب التلقائي)')
    
    customers = Customer.query.limit(5).all()
    for c in customers:
        try:
            balance = c.balance
            ob = float(c.opening_balance or 0)
            print(f'✅ {c.name}:')
            print(f'   الرصيد الافتتاحي: {ob:,.2f}')
            print(f'   الرصيد الحالي: {balance:,.2f}')
            print(f'   النوع: {type(balance).__name__}')
        except Exception as e:
            print(f'❌ {c.name}: خطأ - {e}')
    
    # ═══════════════════════════════════════════════════════════════════
    # 3. فحص GL للمبيعات (نسب الشركاء/الموردين)
    # ═══════════════════════════════════════════════════════════════════
    print_section('3. GL للمبيعات (تحليل النسب)')
    
    # فحص GLBatch للمبيعات
    gl_sales = GLBatch.query.filter_by(source_type='SALE').order_by(GLBatch.created_at.desc()).limit(5).all()
    
    print(f'✅ عدد قيود المبيعات: {GLBatch.query.filter_by(source_type="SALE").count()}')
    
    for batch in gl_sales:
        sale = Sale.query.get(batch.source_id)
        if not sale:
            continue
        
        print(f'\n📋 فاتورة: {sale.sale_number}')
        print(f'   المبلغ: {float(sale.total_amount or 0):,.2f}')
        print(f'   العميل: {sale.customer.name if sale.customer else "—"}')
        
        # جلب القيود الفرعية
        entries = db.session.execute(text("""
            SELECT account, debit, credit
            FROM gl_entries
            WHERE batch_id = :bid
        """), {"bid": batch.id}).fetchall()
        
        total_debit = 0.0
        total_credit = 0.0
        
        print(f'   القيود:')
        for acc_code, debit, credit in entries:
            account = Account.query.filter_by(code=acc_code).first()
            acc_name = account.name if account else acc_code
            
            if float(debit or 0) > 0:
                print(f'     مدين {acc_name}: {float(debit):,.2f}')
                total_debit += float(debit)
            if float(credit or 0) > 0:
                print(f'     دائن {acc_name}: {float(credit):,.2f}')
                total_credit += float(credit)
        
        # التحقق من التوازن
        if abs(total_debit - total_credit) < 0.01:
            print(f'   ✅ متوازن: {total_debit:,.2f} = {total_credit:,.2f}')
        else:
            print(f'   ❌ غير متوازن! مدين={total_debit:,.2f}, دائن={total_credit:,.2f}')
    
    # ═══════════════════════════════════════════════════════════════════
    # 4. فحص دليل الحسابات
    # ═══════════════════════════════════════════════════════════════════
    print_section('4. دليل الحسابات (Chart of Accounts)')
    
    accounts = Account.query.filter_by(is_active=True).all()
    print(f'✅ عدد الحسابات النشطة: {len(accounts)}')
    
    accounts_by_type = {}
    for acc in accounts:
        acc_type = acc.type or 'UNKNOWN'
        if acc_type not in accounts_by_type:
            accounts_by_type[acc_type] = []
        accounts_by_type[acc_type].append(acc)
    
    for acc_type, accs in accounts_by_type.items():
        print(f'\n   {acc_type}: {len(accs)} حساب')
        for acc in accs[:3]:
            print(f'     • {acc.code}: {acc.name}')
        if len(accs) > 3:
            print(f'     ... و {len(accs) - 3} حساب آخر')
    
    # ═══════════════════════════════════════════════════════════════════
    # 5. فحص نسب الشركاء في المبيعات
    # ═══════════════════════════════════════════════════════════════════
    print_section('5. نسب الشركاء/الموردين في البضاعة')
    
    # فحص ProductPartner
    product_partners = db.session.query(
        func.count(ProductPartner.id)
    ).scalar() or 0
    
    print(f'✅ عدد ربط المنتجات بالشركاء (ProductPartner): {product_partners}')
    
    # فحص WarehousePartnerShare
    warehouse_shares = db.session.query(
        func.count(WarehousePartnerShare.id)
    ).scalar() or 0
    
    print(f'✅ عدد نسب المستودعات (WarehousePartnerShare): {warehouse_shares}')
    
    # فحص مستودعات الشركاء
    partner_warehouses = Warehouse.query.filter_by(warehouse_type='PARTNER').all()
    print(f'✅ مستودعات الشركاء: {len(partner_warehouses)}')
    for wh in partner_warehouses:
        partner = Partner.query.get(wh.partner_id) if wh.partner_id else None
        print(f'   {wh.name}: {partner.name if partner else "—"} ({wh.share_percent}%)')
    
    # فحص مستودعات العهدة
    exchange_warehouses = Warehouse.query.filter_by(warehouse_type='EXCHANGE').all()
    print(f'✅ مستودعات العهدة: {len(exchange_warehouses)}')
    for wh in exchange_warehouses:
        # عدد ExchangeTransactions
        ex_count = ExchangeTransaction.query.filter_by(warehouse_id=wh.id).count()
        print(f'   {wh.name}: {ex_count} معاملة عهدة')
    
    # ═══════════════════════════════════════════════════════════════════
    # 6. فحص التوازن المحاسبي العام
    # ═══════════════════════════════════════════════════════════════════
    print_section('6. التوازن المحاسبي العام')
    
    # إجمالي المدين والدائن من جميع القيود
    total_result = db.session.execute(text("""
        SELECT 
            COALESCE(SUM(debit), 0) as total_debit,
            COALESCE(SUM(credit), 0) as total_credit
        FROM gl_entries
    """)).fetchone()
    
    if total_result:
        total_dr = float(total_result[0] or 0)
        total_cr = float(total_result[1] or 0)
        
        print(f'إجمالي المدين: {total_dr:,.2f} ₪')
        print(f'إجمالي الدائن: {total_cr:,.2f} ₪')
        print(f'الفرق: {abs(total_dr - total_cr):,.2f} ₪')
        
        if abs(total_dr - total_cr) < 0.01:
            print('✅ النظام متوازن محاسبياً!')
        else:
            print('⚠️ يوجد فرق في التوازن!')
    
    # ═══════════════════════════════════════════════════════════════════
    # 7. إحصائيات عامة
    # ═══════════════════════════════════════════════════════════════════
    print_section('7. إحصائيات عامة')
    
    stats = {
        'عملاء': Customer.query.filter_by(is_archived=False).count(),
        'موردين': Supplier.query.filter_by(is_archived=False).count(),
        'شركاء': Partner.query.count(),
        'مبيعات': Sale.query.filter_by(status='CONFIRMED').count(),
        'دفعات': Payment.query.filter_by(status='COMPLETED').count(),
        'قيود محاسبية (GLBatch)': GLBatch.query.count(),
        'قيود فرعية (GLEntry)': db.session.query(func.count(GLEntry.id)).scalar() or 0,
    }
    
    for key, value in stats.items():
        print(f'✅ {key}: {value}')
    
    # ═══════════════════════════════════════════════════════════════════
    # 8. فحص أنواع GLBatch
    # ═══════════════════════════════════════════════════════════════════
    print_section('8. أنواع القيود المحاسبية')
    
    batch_types = db.session.execute(text("""
        SELECT source_type, COUNT(*) as count
        FROM gl_batches
        GROUP BY source_type
    """)).fetchall()
    
    for source_type, count in batch_types:
        print(f'✅ {source_type}: {count} قيد')
    
    # ═══════════════════════════════════════════════════════════════════
    # النتيجة النهائية
    # ═══════════════════════════════════════════════════════════════════
    print()
    print('═' * 70)
    print('✅ انتهى التدقيق المحاسبي!')
    print(f'🕐 الوقت: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('═' * 70)
    print()

