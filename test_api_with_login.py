#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""اختبار API مع login"""

from app import app, db
from models import User

with app.test_client() as client:
    with app.app_context():
        print('\n' + '='*80)
        print('🧪 اختبار API الشيكات مع Authentication')
        print('='*80)
        
        # الحصول على مستخدم
        user = User.query.first()
        if not user:
            print('\n❌ لا يوجد مستخدمين!')
        else:
            print(f'\n👤 المستخدم: {user.username}')
            
            # محاولة login
            with client.session_transaction() as sess:
                sess['_user_id'] = str(user.id)
                sess['_fresh'] = True
            
            # اختبار API
            print('\n📡 GET /checks/api/checks')
            resp = client.get('/checks/api/checks')
            print(f'   Status: {resp.status_code}')
            
            if resp.status_code == 200:
                data = resp.get_json()
                print(f'   ✅ Success: {data.get("success")}')
                print(f'   📊 Total: {data.get("total")} شيك')
                
                print(f'\n   📋 أول 5 شيكات:')
                for i, check in enumerate(data.get('checks', [])[:5], 1):
                    print(f'      {i}. {check.get("check_number", "N/A")} - {check.get("source")}')
                    print(f'         البنك: {check.get("check_bank", "N/A")}')
                    print(f'         المبلغ: {check.get("amount")} {check.get("currency")}')
            else:
                print(f'   ❌ خطأ: {resp.get_data(as_text=True)[:200]}')
        
        print('\n' + '='*80)

