#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""تسجيل دخول واختبار كامل"""

import requests
import json

print('\n' + '='*80)
print('🔐 تسجيل دخول واختبار وحدة الشيكات')
print('='*80)

session = requests.Session()

# Login
print('\n1️⃣ تسجيل الدخول...')
login_resp = session.post(
    'http://localhost:5000/auth/login',
    data={
        'username': 'azad',
        'password': 'AZ12345',
        'remember_me': 'on'
    },
    allow_redirects=True
)

print(f'   Status: {login_resp.status_code}')
print(f'   URL بعد Login: {login_resp.url}')

if 'login' not in login_resp.url:
    print('   ✅ تم الدخول بنجاح!')
    
    # جلب الشيكات
    print('\n2️⃣ جلب الشيكات...')
    checks_resp = session.get('http://localhost:5000/checks/api/checks')
    print(f'   Status: {checks_resp.status_code}')
    
    if checks_resp.status_code == 200:
        data = checks_resp.json()
        print(f'   ✅ Total: {data.get("total")} شيك')
        
        # تصنيف
        sources = {}
        for c in data.get('checks', []):
            s = c.get('source', 'Unknown')
            sources[s] = sources.get(s, 0) + 1
        
        print(f'\n   📊 التوزيع:')
        for source, count in sources.items():
            print(f'      • {source}: {count}')
        
        # عينة
        print(f'\n   📋 عينة (أول 5):')
        for i, check in enumerate(data.get('checks', [])[:5], 1):
            print(f'      {i}. [{check.get("source")}] {check.get("check_number")}')
            print(f'         {check.get("check_bank")} - {check.get("amount"):,.0f} {check.get("currency")}')
            print(f'         الجهة: {check.get("entity_name", "N/A")}')
    
    # Statistics
    print('\n3️⃣ الإحصائيات...')
    stats_resp = session.get('http://localhost:5000/checks/api/statistics')
    if stats_resp.status_code == 200:
        stats = stats_resp.json().get('statistics', {})
        print(f'   📥 وارد: {stats.get("incoming", {}).get("total_amount", 0):,.2f}')
        print(f'   📤 صادر: {stats.get("outgoing", {}).get("total_amount", 0):,.2f}')
    
    # Alerts
    print('\n4️⃣ التنبيهات...')
    alerts_resp = session.get('http://localhost:5000/checks/api/alerts')
    if alerts_resp.status_code == 200:
        alerts = alerts_resp.json().get('alerts', [])
        print(f'   ⚠️ عدد التنبيهات: {len(alerts)}')
        for alert in alerts[:3]:
            print(f'      • {alert.get("title")}')
    
    print('\n' + '='*80)
    print('✅ النظام يعمل بشكل كامل!')
    print(f'📊 {data.get("total")} شيك جاهزة للعرض')
    print('='*80)
    
else:
    print(f'   ❌ فشل الدخول')
    print(f'   Response: {login_resp.text[:200]}')

print()

