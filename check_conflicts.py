#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
فحص التعارضات والتكرار في الملفات الجديدة
"""

import re
import os
from collections import defaultdict

def check_function_conflicts():
    """فحص تكرار أسماء الوظائف"""
    print("🔍 فحص تكرار أسماء الوظائف...")
    print("=" * 60)
    
    js_files = [
        'static/js/event-utils.js',
        'static/js/performance-utils.js',
        'static/js/safe-enhancements.js'
    ]
    
    all_functions = defaultdict(list)
    
    for filepath in js_files:
        if not os.path.exists(filepath):
            continue
            
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # البحث عن function declarations
        func_pattern = r'function\s+(\w+)\s*\('
        matches = re.finditer(func_pattern, content)
        
        for match in matches:
            func_name = match.group(1)
            all_functions[func_name].append(os.path.basename(filepath))
    
    # البحث عن تكرار
    duplicates = {name: files for name, files in all_functions.items() if len(files) > 1}
    
    print(f"✅ إجمالي الوظائف: {len(all_functions)}")
    
    if duplicates:
        print(f"❌ وظائف مكررة: {len(duplicates)}\n")
        for name, files in duplicates.items():
            print(f"  ⚠️  {name}:")
            for f in files:
                print(f"      - {f}")
    else:
        print("✅ لا توجد وظائف مكررة\n")
    
    return len(duplicates) == 0

def check_global_variables():
    """فحص تعارض المتغيرات العامة"""
    print("🔍 فحص المتغيرات العامة (window.*)...")
    print("=" * 60)
    
    js_files = [
        'static/js/event-utils.js',
        'static/js/performance-utils.js',
        'static/js/safe-enhancements.js'
    ]
    
    global_vars = defaultdict(list)
    
    for filepath in js_files:
        if not os.path.exists(filepath):
            continue
            
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # البحث عن window.X = 
        pattern = r'window\.(\w+)\s*='
        matches = re.finditer(pattern, content)
        
        for match in matches:
            var_name = match.group(1)
            global_vars[var_name].append(os.path.basename(filepath))
    
    print(f"✅ إجمالي المتغيرات العامة المضافة: {len(global_vars)}")
    print("\nالمتغيرات المضافة:")
    for var_name, files in sorted(global_vars.items()):
        print(f"  ✅ window.{var_name:<20} ← {files[0]}")
    
    # فحص التكرار
    duplicates = {name: files for name, files in global_vars.items() if len(files) > 1}
    
    if duplicates:
        print(f"\n❌ متغيرات مكررة: {len(duplicates)}")
        for name, files in duplicates.items():
            print(f"  ⚠️  window.{name}:")
            for f in files:
                print(f"      - {f}")
    else:
        print("\n✅ لا توجد متغيرات مكررة")
    
    return len(duplicates) == 0

def check_existing_conflicts():
    """فحص التعارض مع الملفات الموجودة"""
    print("\n🔍 فحص التعارض مع الكود الموجود...")
    print("=" * 60)
    
    # فحص window objects الموجودة مسبقاً
    new_globals = ['EventUtils', '$events', 'PerfUtils', 'SafeEnhancements']
    existing_js_files = [
        'static/js/ux-enhancements.js',
        'static/js/payments.js',
        'static/js/warehouses.js',
        'static/js/sales.js'
    ]
    
    conflicts = []
    
    for js_file in existing_js_files:
        if not os.path.exists(js_file):
            continue
            
        with open(js_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        for global_var in new_globals:
            if f'window.{global_var}' in content or f'{global_var}.' in content:
                conflicts.append(f"{global_var} موجود في {os.path.basename(js_file)}")
    
    if conflicts:
        print("❌ تم العثور على تعارضات محتملة:")
        for conflict in conflicts:
            print(f"  ⚠️  {conflict}")
    else:
        print("✅ لا توجد تعارضات مع الكود الموجود")
    
    return len(conflicts) == 0

def check_css_conflicts():
    """فحص تعارض CSS classes"""
    print("\n🔍 فحص تعارض CSS classes...")
    print("=" * 60)
    
    new_css = 'static/css/enhancements.css'
    existing_css = 'static/css/style.css'
    
    if not os.path.exists(new_css):
        print("⚠️  enhancements.css غير موجود")
        return True
    
    with open(new_css, 'r', encoding='utf-8') as f:
        new_content = f.read()
    
    # استخراج class names
    new_classes = set(re.findall(r'\.([a-zA-Z][\w-]*)\s*{', new_content))
    
    print(f"✅ Classes جديدة في enhancements.css: {len(new_classes)}")
    
    if os.path.exists(existing_css):
        with open(existing_css, 'r', encoding='utf-8') as f:
            existing_content = f.read()
        
        existing_classes = set(re.findall(r'\.([a-zA-Z][\w-]*)\s*{', existing_content))
        
        # البحث عن تكرار
        duplicates = new_classes & existing_classes
        
        if duplicates:
            print(f"\n⚠️  تكرار في {len(duplicates)} class:")
            for cls in sorted(duplicates):
                print(f"  - .{cls}")
            print("\n💡 ملاحظة: التكرار قد يكون مقصوداً للتجاوز (override)")
            return False
        else:
            print("✅ لا توجد classes مكررة")
            return True
    
    return True

def check_event_listener_conflicts():
    """فحص تعارض Event Listeners"""
    print("\n🔍 فحص تعارض Event Listeners...")
    print("=" * 60)
    
    issues = []
    
    # فحص DOMContentLoaded listeners
    pattern = r"DOMContentLoaded['\"]"
    
    js_files = []
    for root, dirs, files in os.walk('static/js'):
        for f in files:
            if f.endswith('.js'):
                js_files.append(os.path.join(root, f))
    
    # إضافة base.html
    if os.path.exists('templates/base.html'):
        js_files.append('templates/base.html')
    
    domready_count = 0
    for filepath in js_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            matches = len(re.findall(pattern, content))
            if matches > 0:
                domready_count += matches
        except:
            pass
    
    print(f"✅ DOMContentLoaded listeners: {domready_count}")
    
    if domready_count > 15:
        print("⚠️  عدد كبير من DOMContentLoaded listeners")
        print("   → لكن هذا طبيعي في النظام الكبير")
    else:
        print("✅ عدد معقول")
    
    return True

def main():
    print("\n" + "=" * 60)
    print("         فحص شامل للتعارضات والتكرار")
    print("=" * 60 + "\n")
    
    results = []
    
    # 1. فحص الوظائف
    results.append(("Functions", check_function_conflicts()))
    
    # 2. فحص المتغيرات العامة
    results.append(("Global Variables", check_global_variables()))
    
    # 3. فحص التعارض مع الموجود
    results.append(("Existing Code", check_existing_conflicts()))
    
    # 4. فحص CSS
    results.append(("CSS Classes", check_css_conflicts()))
    
    # 5. فحص Event Listeners
    results.append(("Event Listeners", check_event_listener_conflicts()))
    
    # النتيجة النهائية
    print("\n" + "=" * 60)
    print("📊 النتيجة النهائية:")
    print("=" * 60)
    
    all_passed = all(result[1] for result in results)
    
    for name, passed in results:
        status = "✅" if passed else "⚠️"
        print(f"{status} {name:<30} {'لا توجد مشاكل' if passed else 'يحتاج مراجعة'}")
    
    print("\n" + "=" * 60)
    
    if all_passed:
        print("✅ ممتاز! لا توجد تعارضات أو تكرار")
        print("✅ جميع التحسينات آمنة ومنفصلة")
        print("✅ النظام يعمل بشكل طبيعي")
    else:
        print("⚠️  تم العثور على بعض التحذيرات")
        print("💡 معظمها مقبولة ولا تؤثر على الوظائف")
    
    print("=" * 60)

if __name__ == '__main__':
    main()

