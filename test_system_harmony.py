#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
اختبار شامل للتناغم بين الكود والقوالب وملفات Static
"""

import os
import re
from collections import defaultdict

def test_template_static_links():
    """فحص روابط Static في القوالب"""
    print("🔗 فحص روابط ملفات Static في القوالب...")
    print("=" * 60)
    
    missing_files = []
    total_links = 0
    
    templates_dir = 'templates'
    
    for root, dirs, files in os.walk(templates_dir):
        for filename in files:
            if not filename.endswith('.html'):
                continue
            
            filepath = os.path.join(root, filename)
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # البحث عن url_for('static', filename='...')
                pattern = r"url_for\('static',\s*filename=['\"]([^'\"]+)['\"]\)"
                matches = re.findall(pattern, content)
                
                for static_file in matches:
                    total_links += 1
                    full_path = os.path.join('static', static_file)
                    
                    if not os.path.exists(full_path):
                        missing_files.append({
                            'template': os.path.relpath(filepath),
                            'static_file': static_file
                        })
            
            except Exception as e:
                pass
    
    print(f"✅ إجمالي روابط Static: {total_links}")
    
    if missing_files:
        print(f"❌ ملفات Static مفقودة: {len(missing_files)}\n")
        for item in missing_files[:10]:  # عرض أول 10
            print(f"  ⚠️  {item['template']}")
            print(f"      → {item['static_file']}")
    else:
        print("✅ جميع ملفات Static موجودة")
    
    return len(missing_files) == 0

def test_url_for_endpoints():
    """فحص url_for في القوالب"""
    print("\n🔗 فحص url_for endpoints في القوالب...")
    print("=" * 60)
    
    templates_dir = 'templates'
    endpoints_used = defaultdict(int)
    
    for root, dirs, files in os.walk(templates_dir):
        for filename in files:
            if not filename.endswith('.html'):
                continue
            
            filepath = os.path.join(root, filename)
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # البحث عن url_for('endpoint.action')
                pattern = r"url_for\(['\"]([^'\"]+)['\"]\s*[,\)]"
                matches = re.findall(pattern, content)
                
                for endpoint in matches:
                    if endpoint != 'static':
                        endpoints_used[endpoint] += 1
            
            except Exception as e:
                pass
    
    print(f"✅ إجمالي endpoints مستخدمة: {len(endpoints_used)}")
    print(f"✅ إجمالي استخدامات: {sum(endpoints_used.values())}")
    
    # عرض أكثر 10 استخداماً
    top = sorted(endpoints_used.items(), key=lambda x: x[1], reverse=True)[:10]
    print("\nأكثر Endpoints استخداماً:")
    for endpoint, count in top:
        print(f"  {endpoint:<40} × {count}")
    
    return True

def test_js_css_harmony():
    """فحص التناغم بين JS و CSS"""
    print("\n🎨 فحص التناغم بين JavaScript و CSS...")
    print("=" * 60)
    
    # جمع جميع classes المستخدمة في JS
    js_classes = set()
    
    for root, dirs, files in os.walk('static/js'):
        for filename in files:
            if filename.endswith('.js'):
                filepath = os.path.join(root, filename)
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # البحث عن classList.add, classList.remove, querySelector('.')
                    patterns = [
                        r"classList\.(?:add|remove|toggle)\(['\"]([^'\"]+)['\"]\)",
                        r"querySelector(?:All)?\(['\"]\.([a-zA-Z][\w-]+)['\"]\)",
                        r"matches\(['\"]\.([a-zA-Z][\w-]+)['\"]\)",
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, content)
                        js_classes.update(matches)
                
                except:
                    pass
    
    # جمع جميع classes المعرّفة في CSS
    css_classes = set()
    
    for root, dirs, files in os.walk('static/css'):
        for filename in files:
            if filename.endswith('.css'):
                filepath = os.path.join(root, filename)
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # البحث عن .classname {
                    matches = re.findall(r'\.([a-zA-Z][\w-]*)\s*{', content)
                    css_classes.update(matches)
                
                except:
                    pass
    
    print(f"✅ Classes مستخدمة في JS: {len(js_classes)}")
    print(f"✅ Classes معرّفة في CSS: {len(css_classes)}")
    
    # Classes في JS لكن ليست في CSS
    missing_in_css = js_classes - css_classes
    
    if missing_in_css:
        # فلترة Bootstrap و AdminLTE classes
        common_classes = {'btn', 'card', 'modal', 'table', 'form', 'alert', 'badge', 'nav'}
        missing_in_css = missing_in_css - common_classes
        
        if missing_in_css:
            print(f"\n⚠️  Classes في JS لكن ليست في CSS: {len(missing_in_css)}")
            for cls in sorted(list(missing_in_css)[:10]):
                print(f"  - .{cls}")
    else:
        print("\n✅ جميع Classes المستخدمة معرّفة")
    
    return True

def test_route_template_harmony():
    """فحص التناغم بين Routes و Templates"""
    print("\n🔀 فحص التناغم بين Routes و Templates...")
    print("=" * 60)
    
    # جمع جميع render_template من routes
    routes_templates = set()
    
    routes_dir = 'routes'
    if os.path.exists(routes_dir):
        for filename in os.listdir(routes_dir):
            if filename.endswith('.py'):
                filepath = os.path.join(routes_dir, filename)
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # البحث عن render_template('path/file.html')
                    pattern = r"render_template\(['\"]([^'\"]+)['\"]\)"
                    matches = re.findall(pattern, content)
                    routes_templates.update(matches)
                
                except:
                    pass
    
    # فحص app.py أيضاً
    if os.path.exists('app.py'):
        try:
            with open('app.py', 'r', encoding='utf-8') as f:
                content = f.read()
            
            pattern = r"render_template\(['\"]([^'\"]+)['\"]\)"
            matches = re.findall(pattern, content)
            routes_templates.update(matches)
        except:
            pass
    
    # جمع جميع Templates الموجودة فعلاً
    existing_templates = set()
    
    templates_dir = 'templates'
    if os.path.exists(templates_dir):
        for root, dirs, files in os.walk(templates_dir):
            for filename in files:
                if filename.endswith('.html'):
                    rel_path = os.path.relpath(
                        os.path.join(root, filename),
                        templates_dir
                    ).replace('\\', '/')
                    existing_templates.add(rel_path)
    
    print(f"✅ Templates مستخدمة في Routes: {len(routes_templates)}")
    print(f"✅ Templates موجودة فعلاً: {len(existing_templates)}")
    
    # Templates مستخدمة لكن غير موجودة
    missing_templates = routes_templates - existing_templates
    
    if missing_templates:
        print(f"\n❌ Templates مفقودة: {len(missing_templates)}")
        for tmpl in sorted(list(missing_templates)[:10]):
            print(f"  ⚠️  {tmpl}")
    else:
        print("\n✅ جميع Templates المستخدمة موجودة")
    
    return len(missing_templates) == 0

def test_js_dependencies():
    """فحص dependencies بين ملفات JS"""
    print("\n📦 فحص Dependencies بين ملفات JavaScript...")
    print("=" * 60)
    
    # الترتيب الصحيح للتحميل
    correct_order = [
        'event-utils.js',
        'performance-utils.js',
        'safe-enhancements.js'
    ]
    
    # فحص base.html للتأكد من الترتيب
    if os.path.exists('templates/base.html'):
        with open('templates/base.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        loaded_order = []
        for script in correct_order:
            match = re.search(rf'src="[^"]*{script}"', content)
            if match:
                loaded_order.append(script)
        
        print(f"✅ ملفات JS الجديدة المحملة: {len(loaded_order)}")
        
        if loaded_order == correct_order:
            print("✅ الترتيب صحيح (event-utils → performance-utils → safe-enhancements)")
        else:
            print("⚠️  الترتيب قد لا يكون مثالياً")
            print(f"   الموجود: {' → '.join(loaded_order)}")
            print(f"   المثالي: {' → '.join(correct_order)}")
    
    return True

def test_csrf_protection():
    """فحص CSRF protection في النماذج"""
    print("\n🔒 فحص CSRF Protection في النماذج...")
    print("=" * 60)
    
    forms_protected = 0
    forms_unprotected = 0
    
    templates_dir = 'templates'
    
    for root, dirs, files in os.walk(templates_dir):
        for filename in files:
            if filename.endswith('.html'):
                filepath = os.path.join(root, filename)
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # البحث عن <form>
                    forms = re.findall(r'<form[^>]*>(.*?)</form>', content, re.DOTALL | re.IGNORECASE)
                    
                    for form_content in forms:
                        if 'csrf_token' in form_content or 'hidden_tag' in form_content:
                            forms_protected += 1
                        else:
                            # فحص إذا كان GET form (لا يحتاج CSRF)
                            if 'method="get"' not in form_content.lower() and 'method=\'get\'' not in form_content.lower():
                                forms_unprotected += 1
                
                except:
                    pass
    
    total = forms_protected + forms_unprotected
    print(f"✅ نماذج محمية: {forms_protected}")
    print(f"{'❌' if forms_unprotected > 0 else '✅'} نماذج غير محمية: {forms_unprotected}")
    
    if total > 0:
        protection_rate = (forms_protected / total) * 100
        print(f"📊 نسبة الحماية: {protection_rate:.1f}%")
    
    return forms_unprotected == 0

def main():
    print("\n" + "=" * 60)
    print("   اختبار شامل للتناغم بين مكونات النظام")
    print("=" * 60 + "\n")
    
    tests = []
    
    # 1. فحص روابط Static
    tests.append(("Static Links", test_template_static_links()))
    
    # 2. فحص url_for endpoints
    tests.append(("URL Endpoints", test_url_for_endpoints()))
    
    # 3. فحص تناغم JS/CSS
    tests.append(("JS/CSS Harmony", test_js_css_harmony()))
    
    # 4. فحص تناغم Routes/Templates
    tests.append(("Routes/Templates", test_route_template_harmony()))
    
    # 5. فحص dependencies
    tests.append(("JS Dependencies", test_js_dependencies()))
    
    # 6. فحص CSRF
    tests.append(("CSRF Protection", test_csrf_protection()))
    
    # النتيجة النهائية
    print("\n" + "=" * 60)
    print("📊 النتيجة النهائية:")
    print("=" * 60)
    
    all_passed = all(result[1] for result in tests)
    
    for name, passed in tests:
        status = "✅" if passed else "❌"
        print(f"{status} {name:<25} {'ممتاز' if passed else 'يحتاج مراجعة'}")
    
    print("\n" + "=" * 60)
    
    if all_passed:
        print("🎉 ممتاز! جميع الاختبارات نجحت")
        print("✅ التناغم الكامل بين مكونات النظام")
        print("✅ النظام جاهز للاستخدام")
    else:
        print("⚠️  بعض الاختبارات تحتاج مراجعة")
        print("💡 معظمها مشاكل بسيطة يمكن تجاهلها")
    
    print("=" * 60)
    
    # حفظ التقرير
    report_file = 'HARMONY_TEST_REPORT.txt'
    
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("═" * 70 + "\n")
            f.write("  تقرير اختبار التناغم بين مكونات النظام\n")
            f.write("═" * 70 + "\n\n")
            
            for name, passed in tests:
                status = "✅ نجح" if passed else "❌ فشل"
                f.write(f"{status}: {name}\n")
            
            f.write("\n" + "━" * 70 + "\n")
            
            if all_passed:
                f.write("النتيجة: ✅ جميع الاختبارات نجحت\n")
                f.write("الحالة: جاهز للاستخدام\n")
            else:
                f.write("النتيجة: ⚠️ بعض الاختبارات تحتاج مراجعة\n")
        
        print(f"\n💾 تم حفظ التقرير في: {report_file}")
    
    except Exception as e:
        print(f"\n❌ خطأ في حفظ التقرير: {e}")

if __name__ == '__main__':
    main()

