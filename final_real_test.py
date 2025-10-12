#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""الفحص النهائي الحقيقي"""

import requests
import time

print('\n' + '='*80)
print('🔥 الفحص الحقيقي - من المتصفح')
print('='*80)

# Wait for server
print('\n⏰ انتظار السيرفر...')
for i in range(5):
    try:
        r = requests.get('http://localhost:5000/', timeout=2)
        print(f'✅ السيرفر يعمل! (محاولة {i+1})')
        break
    except:
        print(f'⏳ محاولة {i+1}/5...')
        time.sleep(2)
else:
    print('❌ السيرفر لا يعمل!')
    exit(1)

# Test API directly (no authentication needed for testing)
print('\n📡 اختبار API مباشرة...')

try:
    # Try with session
    import requests
    session = requests.Session()
    
    # Login first
    login_data = {
        'username': 'azad',
        'password': 'AZ12345'
    }
    
    print('🔐 تسجيل الدخول...')
    login_resp = session.post('http://localhost:5000/auth/login', data=login_data, allow_redirects=True)
    print(f'   Status: {login_resp.status_code}')
    print(f'   URL: {login_resp.url}')
    
    if 'login' in login_resp.url:
        print('   ⚠️ Login failed - trying test client...')
        
        # Use test client
        from app import app
        from models import User
        
        with app.test_client() as client:
            with app.app_context():
                user = User.query.filter_by(username='azad').first()
                with client.session_transaction() as sess:
                    sess['_user_id'] = str(user.id)
                    sess['_fresh'] = True
                
                resp = client.get('/checks/api/checks')
                if resp.status_code == 200:
                    data = resp.get_json()
                    print(f'\n✅ من Test Client:')
                    print(f'   Total: {data.get("total")} شيك')
                else:
                    print(f'❌ Error: {resp.status_code}')
    else:
        # Try API
        print('\n📊 جلب الشيكات...')
        api_resp = session.get('http://localhost:5000/checks/api/checks')
        print(f'   Status: {api_resp.status_code}')
        
        if api_resp.status_code == 200:
            data = api_resp.json()
            total = data.get('total', 0)
            checks = data.get('checks', [])
            
            print(f'   ✅ Total: {total} شيك')
            
            if total > 0:
                print(f'\n   📋 أول 3 شيكات:')
                for i, check in enumerate(checks[:3], 1):
                    print(f'\n   {i}. [{check.get("source")}]')
                    print(f'      رقم: {check.get("check_number")}')
                    print(f'      مبلغ: {check.get("amount"):,.0f}')
            else:
                print('   ⚠️ لا توجد شيكات في API!')
        else:
            print(f'   ❌ API Error: {api_resp.status_code}')
            print(f'   Response: {api_resp.text[:200]}')

except Exception as e:
    print(f'\n❌ Error: {e}')

print('\n' + '='*80)
print('افتح المتصفح: http://localhost:5000/checks/')
print('Login: azad / AZ12345')
print('='*80 + '\n')

