#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re

files_to_fix = [
    'templates/reports/supplier_detail.html',
    'templates/reports/partner_detail.html',
    'templates/vendors/partners/settlement_preview.html',
    'templates/reports/customer_detail.html',
    'templates/customers/account_statement.html',
    'templates/vendors/partners/statement.html',
    'templates/vendors/suppliers/statement.html',
    'templates/vendors/suppliers/settlement_preview.html',
    'templates/customers/list.html',
    'templates/expenses/expenses_print.html',
]

def fix_file(filepath):
    if not os.path.exists(filepath):
        print(f"⚠️  {filepath} - غير موجود")
        return False
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        
        # البحث عن {% block content %} متبوعاً بـ <div class="content-wrapper
        pattern = r'({% block content %})\s*\n\s*<div class="content-wrapper[^>]*>'
        
        if not re.search(pattern, content, re.MULTILINE):
            print(f"✅ {filepath} - لا يحتاج إصلاح")
            return False
        
        # إزالة <div class="content-wrapper..."> بعد {% block content %}
        content = re.sub(pattern, r'\1', content, flags=re.MULTILINE)
        
        # إزالة آخر </div> قبل {% endblock %}
        # نبحث عن {% endblock %} ونرجع للخلف للبحث عن </div>
        endblock_pattern = r'</div>\s*\n\s*({% endblock %})'
        matches = list(re.finditer(endblock_pattern, content))
        
        if matches:
            last_match = matches[-1]
            content = content[:last_match.start()] + '\n' + last_match.group(1) + content[last_match.end():]
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ تم إصلاح: {filepath}")
            return True
        else:
            print(f"✅ {filepath} - لا يحتاج إصلاح")
            return False
            
    except Exception as e:
        print(f"❌ {filepath}: {e}")
        return False

print("=" * 60)
print("🔧 إصلاح الملفات المتبقية")
print("=" * 60)

fixed = 0
for f in files_to_fix:
    if fix_file(f):
        fixed += 1

print("=" * 60)
print(f"✅ تم إصلاح {fixed} من {len(files_to_fix)} ملف")
print("=" * 60)

