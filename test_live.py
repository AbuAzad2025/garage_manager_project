#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""اختبار حي للنظام"""

from app import app
from models import User
import requests

print('\n' + '='*80)
print('🔥 الفحص الحي - كأني مستخدم عادي')
print('='*80)

# Test 1: السيرفر يعمل؟
try:
    r = requests.get('http://localhost:5000/', timeout=2)
    print(f'\n✅ السيرفر يعمل: {r.status_code}')
except:
    print('\n❌ السيرفر لا يعمل!')
    exit(1)

# Test 2: API مع session
with app.test_client() as client:
    with app.app_context():
        user = User.query.filter_by(username='azad').first()
        
        if not user:
            print('❌ المستخدم azad غير موجود!')
            exit(1)
        
        # Simulate login
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        
        # Test checks API
        print(f'\n📡 اختبار /checks/api/checks...')
        resp = client.get('/checks/api/checks')
        
        if resp.status_code == 200:
            data = resp.get_json()
            total = data.get('total', 0)
            checks = data.get('checks', [])
            
            print(f'   ✅ Status: 200')
            print(f'   📊 Total: {total} شيك')
            
            if total > 0:
                # عينة
                print(f'\n   📋 عينات من كل مصدر:')
                sources = {}
                for check in checks:
                    s = check.get('source')
                    if s not in sources:
                        sources[s] = check
                
                for source, check in sources.items():
                    print(f'\n      [{source}]')
                    print(f'      رقم: {check.get("check_number")}')
                    print(f'      بنك: {check.get("check_bank")}')
                    print(f'      مبلغ: {check.get("amount"):,.0f} {check.get("currency")}')
                    print(f'      جهة: {check.get("entity_name", "N/A")}')
            else:
                print('   ⚠️ لا توجد شيكات!')
        else:
            print(f'   ❌ Error: {resp.status_code}')

print('\n' + '='*80)
print('✅ الاختبار مكتمل!')
print('='*80 + '\n')

