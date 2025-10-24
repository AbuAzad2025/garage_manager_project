#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
فحص شامل لجميع الـ Endpoints في النظام
"""

import os
import re
from collections import defaultdict

def extract_routes_from_file(filepath):
    """استخراج جميع الـ routes من ملف"""
    routes = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # البحث عن @blueprint.route أو @app.route
        # Pattern: @blueprint.route('/path', methods=['GET', 'POST'])
        pattern = r"@\w+\.route\(['\"]([^'\"]+)['\"](?:,\s*methods=\[([^\]]+)\])?\)"
        
        matches = re.finditer(pattern, content)
        
        for match in matches:
            route_path = match.group(1)
            methods = match.group(2)
            
            if methods:
                methods = [m.strip().strip('"').strip("'") for m in methods.split(',')]
            else:
                methods = ['GET']
            
            routes.append({
                'path': route_path,
                'methods': methods,
                'file': os.path.basename(filepath)
            })
            
    except Exception as e:
        print(f"❌ خطأ في قراءة {filepath}: {e}")
    
    return routes

def find_blueprints(filepath):
    """البحث عن Blueprint declarations"""
    blueprints = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # البحث عن Blueprint('name', __name__, url_prefix='/prefix')
        pattern = r"Blueprint\(['\"](\w+)['\"],\s*__name__(?:,\s*url_prefix=['\"]([^'\"]+)['\"])?\)"
        
        matches = re.finditer(pattern, content)
        
        for match in matches:
            bp_name = match.group(1)
            url_prefix = match.group(2) or ''
            
            blueprints.append({
                'name': bp_name,
                'prefix': url_prefix,
                'file': os.path.basename(filepath)
            })
            
    except Exception as e:
        pass
    
    return blueprints

def main():
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║       🔍 فحص شامل لجميع الـ Endpoints في النظام          ║")
    print("╚═══════════════════════════════════════════════════════════╝\n")
    
    routes_dir = 'routes'
    
    if not os.path.exists(routes_dir):
        print(f"❌ المجلد {routes_dir} غير موجود")
        return
    
    all_routes = []
    all_blueprints = []
    routes_by_file = defaultdict(list)
    routes_by_method = defaultdict(list)
    
    # جمع جميع الـ routes
    print("📂 فحص ملفات Routes...")
    print("━" * 60)
    
    for filename in sorted(os.listdir(routes_dir)):
        if filename.endswith('.py') and filename != '__init__.py':
            filepath = os.path.join(routes_dir, filename)
            
            # استخراج blueprints
            blueprints = find_blueprints(filepath)
            all_blueprints.extend(blueprints)
            
            # استخراج routes
            routes = extract_routes_from_file(filepath)
            
            if routes:
                print(f"✅ {filename:<30} → {len(routes):>3} endpoints")
                all_routes.extend(routes)
                routes_by_file[filename] = routes
                
                for route in routes:
                    for method in route['methods']:
                        routes_by_method[method].append(route)
    
    print("━" * 60)
    print(f"\n📊 الإحصائيات:")
    print(f"├─ إجمالي الملفات: {len(routes_by_file)}")
    print(f"├─ إجمالي الـ Endpoints: {len(all_routes)}")
    print(f"└─ إجمالي الـ Blueprints: {len(all_blueprints)}\n")
    
    # تحليل بحسب HTTP Methods
    print("📌 توزيع HTTP Methods:")
    print("━" * 60)
    for method in sorted(routes_by_method.keys()):
        count = len(routes_by_method[method])
        print(f"  {method:<10} → {count:>3} endpoints")
    
    # عرض Blueprints
    if all_blueprints:
        print("\n📦 Blueprints المسجلة:")
        print("━" * 60)
        for bp in sorted(all_blueprints, key=lambda x: x['name']):
            prefix = bp['prefix'] or '/'
            print(f"  {bp['name']:<25} → {prefix:<20} ({bp['file']})")
    
    # البحث عن endpoints مكررة
    print("\n🔍 فحص Endpoints المكررة:")
    print("━" * 60)
    
    path_count = defaultdict(list)
    for route in all_routes:
        path_count[route['path']].append(route['file'])
    
    duplicates = {path: files for path, files in path_count.items() if len(files) > 1}
    
    if duplicates:
        print("⚠️  تم العثور على endpoints مكررة:")
        for path, files in sorted(duplicates.items()):
            print(f"  {path}")
            for f in files:
                print(f"    └─ {f}")
    else:
        print("✅ لا توجد endpoints مكررة")
    
    # عرض أكثر 10 ملفات تحتوي على endpoints
    print("\n📈 أكثر الملفات احتواءً على Endpoints:")
    print("━" * 60)
    
    top_files = sorted(routes_by_file.items(), key=lambda x: len(x[1]), reverse=True)[:10]
    
    for filename, routes in top_files:
        print(f"  {filename:<30} → {len(routes):>3} endpoints")
    
    # فحص أنماط شائعة
    print("\n🎯 أنماط URL الشائعة:")
    print("━" * 60)
    
    patterns = defaultdict(int)
    for route in all_routes:
        # استخراج النمط الأساسي
        path = route['path']
        # إزالة المتغيرات <...>
        pattern = re.sub(r'<[^>]+>', '<var>', path)
        patterns[pattern] += 1
    
    top_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:10]
    
    for pattern, count in top_patterns:
        if count > 1:
            print(f"  {pattern:<40} × {count}")
    
    # حفظ التقرير
    report_file = 'ENDPOINTS_REPORT.txt'
    
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("═" * 70 + "\n")
            f.write("  تقرير شامل لجميع الـ Endpoints في النظام\n")
            f.write("═" * 70 + "\n\n")
            
            f.write(f"إجمالي الملفات: {len(routes_by_file)}\n")
            f.write(f"إجمالي الـ Endpoints: {len(all_routes)}\n")
            f.write(f"إجمالي الـ Blueprints: {len(all_blueprints)}\n\n")
            
            f.write("━" * 70 + "\n")
            f.write("قائمة جميع الـ Endpoints:\n")
            f.write("━" * 70 + "\n\n")
            
            for filename, routes in sorted(routes_by_file.items()):
                f.write(f"\n{filename}:\n")
                for route in sorted(routes, key=lambda x: x['path']):
                    methods = ', '.join(route['methods'])
                    f.write(f"  [{methods:<15}] {route['path']}\n")
        
        print(f"\n💾 تم حفظ التقرير المفصل في: {report_file}")
        
    except Exception as e:
        print(f"\n❌ خطأ في حفظ التقرير: {e}")
    
    print("\n" + "═" * 60)
    print("✅ اكتمل الفحص بنجاح")
    print("═" * 60)

if __name__ == '__main__':
    main()

