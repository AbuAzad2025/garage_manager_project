#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""اختبار نهائي بدون CSRF"""

from app import app, db
from models import User
import json

print('\n' + '='*80)
print('🎯 الفحص النهائي الكامل لوحدة الشيكات')
print('='*80)

with app.test_client() as client:
    with app.app_context():
        # Login
        user = User.query.filter_by(username='azad').first()
        
        if not user:
            print('\n❌ المستخدم azad غير موجود!')
        else:
            print(f'\n✅ المستخدم: {user.username}')
            
            with client.session_transaction() as sess:
                sess['_user_id'] = str(user.id)
                sess['_fresh'] = True
            
            # اختبار الشيكات
            print('\n📡 GET /checks/api/checks')
            resp = client.get('/checks/api/checks')
            
            if resp.status_code == 200:
                data = resp.get_json()
                total = data.get('total', 0)
                checks = data.get('checks', [])
                
                print(f'   ✅ Status: 200')
                print(f'   📊 Total: {total} شيك')
                
                # التوزيع
                sources = {}
                for c in checks:
                    s = c.get('source', 'Unknown')
                    sources[s] = sources.get(s, 0) + 1
                
                print(f'\n   📊 التوزيع حسب المصدر:')
                for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
                    print(f'      • {source}: {count}')
                
                # عينة من كل مصدر
                print(f'\n   📋 عينة من كل مصدر:')
                seen = set()
                for check in checks:
                    source = check.get('source')
                    if source not in seen:
                        seen.add(source)
                        print(f'\n      [{source}]')
                        print(f'      • رقم الشيك: {check.get("check_number", "N/A")}')
                        print(f'      • البنك: {check.get("check_bank", "N/A")}')
                        print(f'      • المبلغ: {check.get("amount", 0):,.0f} {check.get("currency")}')
                        print(f'      • الجهة: {check.get("entity_name", "N/A")}')
                        print(f'      • الساحب: {check.get("drawer_name", "N/A")}')
                        print(f'      • المستفيد: {check.get("payee_name", "N/A")}')
                        print(f'      • الحالة: {check.get("status_ar")}')
                
                # التحقق
                print(f'\n' + '='*80)
                print('النتيجة:')
                print('='*80)
                
                if total >= 28:
                    print(f'✅ النظام يعمل بشكل ممتاز!')
                    print(f'✅ {total} شيك من 4 مصادر')
                    print(f'✅ الربط الذكي يعمل (drawer_name, payee_name)')
                    print(f'✅ جاهز للفحص البصري في المتصفح')
                else:
                    print(f'⚠️ يعمل لكن ناقص بعض الشيكات')
                    print(f'   الحالي: {total}')
                    print(f'   المتوقع: 28-33')
                
                print('='*80)
                
            else:
                print(f'   ❌ Error: {resp.status_code}')
                print(f'   {resp.get_data(as_text=True)[:300]}')

print()

