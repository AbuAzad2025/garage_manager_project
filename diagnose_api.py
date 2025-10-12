#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""تشخيص API الشيكات"""

from app import app, db
from models import Payment, PaymentSplit, Expense, Check, PaymentMethod, User

with app.test_client() as client:
    with app.app_context():
        # Login
        user = User.query.first()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
        
        print('\n' + '='*80)
        print('🔍 تشخيص API الشيكات')
        print('='*80)
        
        # عدد في قاعدة البيانات
        db_payment = Payment.query.filter_by(method=PaymentMethod.CHEQUE.value).count()
        db_split = PaymentSplit.query.filter_by(method=PaymentMethod.CHEQUE.value).count()
        db_expense = Expense.query.filter_by(payment_method='cheque').count()
        db_check = Check.query.count()
        db_total = db_payment + db_split + db_expense + db_check
        
        print('\n📊 في قاعدة البيانات:')
        print(f'   Payment:       {db_payment}')
        print(f'   PaymentSplit:  {db_split}')
        print(f'   Expense:       {db_expense}')
        print(f'   Check:         {db_check}')
        print(f'   ────────────────')
        print(f'   Total:         {db_total}')
        
        # عدد من API
        resp = client.get('/checks/api/checks')
        if resp.status_code == 200:
            data = resp.get_json()
            api_total = data.get('total', 0)
            checks = data.get('checks', [])
            
            print(f'\n📡 من API:')
            print(f'   Total: {api_total}')
            
            # تصنيف المصادر
            sources = {}
            for check in checks:
                source = check.get('source', 'Unknown')
                sources[source] = sources.get(source, 0) + 1
            
            print(f'\n   توزيع حسب المصدر:')
            for source, count in sources.items():
                print(f'     {source}: {count}')
            
            # المقارنة
            print(f'\n⚠️ الفرق:')
            print(f'   في DB: {db_total}')
            print(f'   من API: {api_total}')
            print(f'   الناقص: {db_total - api_total}')
            
            if db_split > 0 and 'دفعة جزئية' not in sources:
                print(f'\n❌ مشكلة: PaymentSplit لا يظهر في API!')
                print(f'   في DB: {db_split} شيكات')
                print(f'   في API: 0 شيكات')
            
            if db_expense > 0 and 'مصروف' not in sources:
                print(f'\n❌ مشكلة: Expense لا يظهر في API!')
                print(f'   في DB: {db_expense} شيكات')
                print(f'   في API: 0 شيكات')
        
        print('\n' + '='*80)

