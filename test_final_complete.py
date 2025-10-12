#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
اختبار نهائي كامل - بعد الإصلاح
"""

from app import app, db
from models import Payment, PaymentSplit, Expense, Check, PaymentMethod, User
from flask_login import login_user

with app.app_context():
    print('\n' + '='*80)
    print('🎯 الفحص النهائي الكامل - بعد الإصلاح')
    print('='*80)
    
    # البيانات في قاعدة البيانات
    db_payment = Payment.query.filter_by(method=PaymentMethod.CHEQUE.value).count()
    db_split = PaymentSplit.query.filter_by(method=PaymentMethod.CHEQUE.value).count()
    db_expense = Expense.query.filter_by(payment_method='cheque').count()
    db_check = Check.query.count()
    db_total = db_payment + db_split + db_expense + db_check
    
    print('\n📊 قاعدة البيانات:')
    print(f'   Payment (method=CHEQUE):    {db_payment:2d} شيك')
    print(f'   PaymentSplit (method=CHEQUE): {db_split:2d} شيكات') 
    print(f'   Expense (payment_method):     {db_expense:2d} شيكات')
    print(f'   Check (يدوي):                 {db_check:2d} شيكات')
    print(f'   ─────────────────────────────────')
    print(f'   الإجمالي:                    {db_total:2d} شيك')
    
    # من API
    with app.test_client() as client:
        # Login كـ admin
        user = db.session.query(User).filter_by(username='azad').first()
        if user:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(user.id)
                sess['_fresh'] = True
            
            resp = client.get('/checks/api/checks')
            
            if resp.status_code == 200:
                data = resp.get_json()
                api_total = data.get('total', 0)
                checks = data.get('checks', [])
                
                print(f'\n📡 من API:')
                print(f'   Total: {api_total} شيك')
                
                # تصنيف
                sources = {}
                for check in checks:
                    source = check.get('source', 'Unknown')
                    sources[source] = sources.get(source, 0) + 1
                
                print(f'\n   توزيع حسب المصدر:')
                for source, count in sorted(sources.items()):
                    print(f'     • {source}: {count}')
                
                # التحقق
                print(f'\n🔍 التحقق:')
                if api_total == db_total:
                    print(f'   ✅ API يجلب جميع الشيكات ({api_total}/{db_total})')
                else:
                    print(f'   ⚠️ API ناقص: {api_total}/{db_total}')
                    print(f'   الناقص: {db_total - api_total} شيك')
                    
                    # تفصيل الناقص
                    if 'دفعة جزئية' not in sources and db_split > 0:
                        print(f'      ❌ PaymentSplit لا يظهر ({db_split} شيكات)')
                    if 'مصروف' not in sources and db_expense > 0:
                        print(f'      ❌ Expense لا يظهر ({db_expense} شيكات)')
            else:
                print(f'\n   ❌ API Error: {resp.status_code}')
    
    print('\n' + '='*80)
    print('النتيجة:')
    print('='*80)
    
    if api_total == db_total:
        print('✅ النظام يعمل بشكل كامل!')
        print(f'✅ جميع المصادر الأربعة تُجلب بنجاح')
        print(f'✅ {api_total} شيك متوفر')
    else:
        print('⚠️ هناك مشكلة في جلب بعض المصادر')
        print('💡 يرجى مراجعة routes/checks.py → get_checks()')
    
    print('='*80 + '\n')

