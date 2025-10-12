#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""اختبار شامل مع تسجيل دخول Admin"""

from app import app
import requests

print('\n' + '='*80)
print('🔐 اختبار وحدة الشيكات مع Admin Login')
print('='*80)

# إنشاء session
session = requests.Session()

# تسجيل الدخول
login_data = {
    'username': 'azad',
    'password': 'AZ12345'
}

print('\n1️⃣ تسجيل الدخول...')
resp = session.post('http://localhost:5000/auth/login', data=login_data, allow_redirects=False)
print(f'   Status: {resp.status_code}')

if resp.status_code in [200, 302]:
    print('   ✅ تم الدخول بنجاح!')
    
    # 2. جلب جميع الشيكات
    print('\n2️⃣ GET /checks/api/checks')
    print('-' * 80)
    resp = session.get('http://localhost:5000/checks/api/checks')
    print(f'   Status: {resp.status_code}')
    
    if resp.status_code == 200:
        data = resp.json()
        print(f'   ✅ Success: {data.get("success")}')
        print(f'   📊 Total: {data.get("total")} شيك')
        
        # تصنيف المصادر
        sources = {}
        for check in data.get('checks', []):
            source = check.get('source', 'Unknown')
            sources[source] = sources.get(source, 0) + 1
        
        print(f'\n   📋 توزيع حسب المصدر:')
        for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
            print(f'      • {source}: {count} شيك')
        
        # عرض عينة من كل مصدر
        print(f'\n   🔍 عينة من الشيكات:')
        seen_sources = set()
        for check in data.get('checks', []):
            source = check.get('source')
            if source not in seen_sources:
                seen_sources.add(source)
                print(f'\n      [{source}]')
                print(f'      • رقم: {check.get("check_number", "N/A")}')
                print(f'      • البنك: {check.get("check_bank", "N/A")}')
                print(f'      • المبلغ: {check.get("amount", 0):,.0f} {check.get("currency")}')
                print(f'      • الحالة: {check.get("status_ar")}')
    
    # 3. الإحصائيات
    print('\n\n3️⃣ GET /checks/api/statistics')
    print('-' * 80)
    resp = session.get('http://localhost:5000/checks/api/statistics')
    print(f'   Status: {resp.status_code}')
    
    if resp.status_code == 200:
        data = resp.json()
        stats = data.get('statistics', {})
        
        incoming = stats.get('incoming', {})
        outgoing = stats.get('outgoing', {})
        
        print(f'   📥 الواردة:')
        print(f'      • المبلغ: {incoming.get("total_amount", 0):,.2f}')
        print(f'      • متأخرة: {incoming.get("overdue_count", 0)}')
        print(f'      • هذا الأسبوع: {incoming.get("this_week_count", 0)}')
        
        print(f'\n   📤 الصادرة:')
        print(f'      • المبلغ: {outgoing.get("total_amount", 0):,.2f}')
        print(f'      • متأخرة: {outgoing.get("overdue_count", 0)}')
        print(f'      • هذا الأسبوع: {outgoing.get("this_week_count", 0)}')
    
    # 4. التنبيهات
    print('\n\n4️⃣ GET /checks/api/alerts')
    print('-' * 80)
    resp = session.get('http://localhost:5000/checks/api/alerts')
    print(f'   Status: {resp.status_code}')
    
    if resp.status_code == 200:
        data = resp.json()
        alerts = data.get('alerts', [])
        print(f'   ⚠️ عدد التنبيهات: {len(alerts)}')
        
        for i, alert in enumerate(alerts[:3], 1):
            print(f'\n      {i}. {alert.get("title")}')
            print(f'         {alert.get("message")}')
    
else:
    print(f'   ❌ فشل الدخول: {resp.status_code}')

print('\n' + '='*80)
print('✅ اكتمل الفحص')
print('='*80 + '\n')

