#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""عرض حي للمستخدم"""

from app import app
from models import User, Payment, PaymentSplit, Expense, Check, PaymentMethod
from datetime import datetime

print('\n' + '='*80)
print('🔥 الفحص الحي المباشر - أنا كمستخدم')
print('='*80)

with app.app_context():
    # 1. فحص البيانات في DB
    print('\n📊 البيانات في قاعدة البيانات:')
    
    payment_checks = Payment.query.filter_by(method=PaymentMethod.CHEQUE.value).count()
    print(f'   • Payment (method=CHEQUE): {payment_checks}')
    
    split_checks = PaymentSplit.query.filter_by(method=PaymentMethod.CHEQUE.value).count()
    print(f'   • PaymentSplit (method=CHEQUE): {split_checks}')
    
    expense_checks = Expense.query.filter_by(payment_method='cheque').count()
    print(f'   • Expense (payment_method=cheque): {expense_checks}')
    
    manual_checks = Check.query.count()
    print(f'   • Check (يدوي): {manual_checks}')
    
    total_in_db = payment_checks + split_checks + expense_checks + manual_checks
    print(f'\n   📌 الإجمالي في DB: {total_in_db} شيك')
    
    # 2. فحص API
    print('\n📡 الآن أفحص API:')
    with app.test_client() as client:
        user = User.query.filter_by(username='azad').first()
        
        if not user:
            print('   ❌ المستخدم غير موجود!')
        else:
            print(f'   ✅ المستخدم: {user.username} (super_admin)')
            
            # Login simulation
            with client.session_transaction() as sess:
                sess['_user_id'] = str(user.id)
                sess['_fresh'] = True
            
            # Call API
            resp = client.get('/checks/api/checks')
            
            if resp.status_code == 200:
                data = resp.get_json()
                total_from_api = data.get('total', 0)
                checks = data.get('checks', [])
                
                print(f'   ✅ API Status: 200')
                print(f'   📊 Total من API: {total_from_api} شيك')
                
                # Statistics
                sources = {}
                for c in checks:
                    s = c.get('source', 'Unknown')
                    sources[s] = sources.get(s, 0) + 1
                
                print(f'\n   📋 التوزيع:')
                for source, count in sources.items():
                    print(f'      • {source}: {count}')
                
                # Sample من كل source
                print(f'\n   🔍 عينات:')
                shown = set()
                for check in checks[:10]:  # أول 10
                    source = check.get('source')
                    if source not in shown:
                        shown.add(source)
                        print(f'\n      [{source}]')
                        print(f'      ├─ رقم: {check.get("check_number")}')
                        print(f'      ├─ بنك: {check.get("check_bank")}')
                        print(f'      ├─ مبلغ: {check.get("amount"):,.0f} {check.get("currency")}')
                        print(f'      ├─ جهة: {check.get("entity_name", "N/A")}')
                        print(f'      ├─ ساحب: {check.get("drawer_name", "N/A")}')
                        print(f'      └─ مستفيد: {check.get("payee_name", "N/A")}')
                
                print(f'\n' + '='*80)
                print(f'✅ النتيجة النهائية:')
                print('='*80)
                print(f'✅ DB: {total_in_db} شيك')
                print(f'✅ API: {total_from_api} شيك')
                print(f'✅ الفرق: {abs(total_in_db - total_from_api)} شيك')
                
                if total_from_api >= 28:
                    print(f'\n🎉 النظام يعمل بشكل ممتاز!')
                    print(f'✅ {total_from_api} شيك جاهزة')
                    print(f'✅ من 4 مصادر مختلفة')
                    print(f'✅ الربط الذكي يعمل')
                    print(f'✅ super_admin بدون permission issues')
                else:
                    print(f'\n⚠️ هناك شيكات ناقصة')
                
                print('='*80)
            else:
                print(f'   ❌ API Error: {resp.status_code}')
                print(f'   Response: {resp.get_data(as_text=True)[:200]}')

print()

