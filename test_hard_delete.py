#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
اختبار نظام الحذف القوي
"""

import requests
from bs4 import BeautifulSoup

print('═══════════════════════════════════════════════════════')
print('🧪 اختبار الحذف القوي للعملاء')
print('═══════════════════════════════════════════════════════')
print()

# 1. فتح صفحة الحذف القوي
url_get = 'http://localhost:5000/hard-delete/customer/1'
print(f'📍 GET: {url_get}')

try:
    response = requests.get(url_get, timeout=5)
    print(f'   Status: {response.status_code}')
    
    if response.status_code == 200:
        print('   ✅ الصفحة تفتح بنجاح')
        
        # استخراج CSRF Token
        soup = BeautifulSoup(response.text, 'html.parser')
        csrf_input = soup.find('input', attrs={'name': 'csrf_token'})
        
        if csrf_input:
            csrf_token = csrf_input.get('value')
            print(f'   ✅ CSRF Token: {csrf_token[:30]}...')
        else:
            print('   ❌ CSRF Token مفقود!')
            csrf_token = None
            
        # فحص الـ form
        forms = soup.find_all('form')
        print(f'   📊 عدد الـ forms في الصفحة: {len(forms)}')
        
        form = soup.find('form', attrs={'method': 'POST'})
        if not form:
            form = soup.find('form')
            
        if form:
            print(f'   ✅ Form موجود: method={form.get("method", "GET")}')
            print(f'   📍 Action: {form.get("action", "نفس الصفحة")}')
        else:
            print('   ❌ Form مفقود!')
            # حفظ HTML للفحص
            with open('debug_html.html', 'w', encoding='utf-8') as f:
                f.write(response.text)
            print('   💾 تم حفظ HTML في debug_html.html')
            
        # فحص textarea reason
        reason_field = soup.find('textarea', attrs={'name': 'reason'})
        if reason_field:
            print(f'   ✅ حقل السبب موجود')
        else:
            print('   ❌ حقل السبب مفقود!')
            
    elif response.status_code == 302:
        print(f'   ⚠️ Redirect إلى: {response.headers.get("Location")}')
        print('   💡 تحتاج تسجيل دخول أولاً!')
    else:
        print(f'   ❌ خطأ: {response.status_code}')
        
except requests.exceptions.ConnectionError:
    print('   ❌ لا يمكن الاتصال بالسيرفر!')
    print('   💡 تأكد أن السيرفر شغال على http://localhost:5000')
except Exception as e:
    print(f'   ❌ خطأ: {e}')

print()
print('═══════════════════════════════════════════════════════')
print('📝 ملاحظات:')
print('═══════════════════════════════════════════════════════')
print('1. إذا كان Status 302 = تحتاج تسجيل دخول أولاً')
print('2. إذا كان Status 200 = الصفحة شغالة')
print('3. افتح المتصفح وسجل دخول ثم جرب')
print()

