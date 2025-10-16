

import os
import json
from datetime import datetime
from pathlib import Path
from flask import current_app


SYSTEM_MAP_FILE = 'instance/ai_system_map.json'
DISCOVERY_LOG_FILE = 'instance/ai_discovery_log.json'


def discover_all_routes():
    routes = []
    
    try:
        for rule in current_app.url_map.iter_rules():
            if rule.endpoint == 'static':
                continue
                
            route_info = {
                'endpoint': rule.endpoint,
                'url': str(rule.rule),
                'methods': sorted(list(rule.methods - {'HEAD', 'OPTIONS'})),
                'blueprint': rule.endpoint.split('.')[0] if '.' in rule.endpoint else None,
                'function_name': rule.endpoint.split('.')[-1] if '.' in rule.endpoint else rule.endpoint,
            }
            
            routes.append(route_info)
    
    except Exception as e:
        print(f"خطأ في اكتشاف Routes: {str(e)}")
    
    return routes


def discover_all_templates():
    """فحص جميع القوالب في مجلد templates/"""
    templates = []
    templates_dir = Path('templates')
    
    if not templates_dir.exists():
        return templates
    
    try:
        for template_file in templates_dir.rglob('*.html'):
            relative_path = template_file.relative_to(templates_dir)
            
            template_info = {
                'name': str(relative_path),
                'full_path': str(template_file),
                'module': str(relative_path.parent) if relative_path.parent != Path('.') else 'root',
                'file_size': template_file.stat().st_size,
                'last_modified': datetime.fromtimestamp(template_file.stat().st_mtime).isoformat()
            }
            
            templates.append(template_info)
    
    except Exception as e:
        print(f"خطأ في فحص Templates: {str(e)}")
    
    return templates


def link_routes_to_templates(routes, templates):
    """ربط Routes بالـ Templates"""
    linked = []
    template_names = {t['name'] for t in templates}
    
    for route in routes:
        route_copy = route.copy()
        
        # محاولة تخمين Template بناءً على الـ endpoint
        blueprint = route.get('blueprint')
        function = route.get('function_name')
        
        possible_templates = []
        
        if blueprint:
            # محاولة 1: blueprint/function.html
            guess1 = f"{blueprint}/{function}.html"
            if guess1 in template_names:
                possible_templates.append(guess1)
            
            # محاولة 2: blueprint/index.html
            guess2 = f"{blueprint}/index.html"
            if guess2 in template_names and function == 'index':
                possible_templates.append(guess2)
            
            # محاولة 3: blueprint/list.html, edit.html, etc.
            common_names = ['list', 'detail', 'edit', 'create', 'delete', 'view']
            for common in common_names:
                if common in function:
                    guess = f"{blueprint}/{common}.html"
                    if guess in template_names:
                        possible_templates.append(guess)
        
        route_copy['linked_templates'] = possible_templates
        route_copy['has_template'] = len(possible_templates) > 0
        linked.append(route_copy)
    
    return linked


def categorize_routes(routes):
    """تصنيف Routes حسب النوع"""
    categories = {
        'api': [],
        'admin': [],
        'security': [],
        'reports': [],
        'public': [],
        'other': []
    }
    
    for route in routes:
        url = route['url'].lower()
        
        if '/api/' in url or route['blueprint'] == 'api':
            categories['api'].append(route)
        elif '/admin/' in url or 'admin' in route['blueprint'] or '':
            categories['admin'].append(route)
        elif '/security/' in url or route['blueprint'] == 'security':
            categories['security'].append(route)
        elif '/report' in url or route['blueprint'] in ['reports', 'admin_reports']:
            categories['reports'].append(route)
        elif '/auth/' in url or route['blueprint'] == 'auth':
            categories['public'].append(route)
        else:
            categories['other'].append(route)
    
    return categories


def build_system_map():
    """بناء خريطة النظام الكاملة"""
    print("\n🔍 بدء اكتشاف النظام...")
    
    # 1. اكتشاف Routes
    routes = discover_all_routes()
    print(f"✅ تم اكتشاف {len(routes)} مسار")
    
    # 2. اكتشاف Templates
    templates = discover_all_templates()
    print(f"✅ تم اكتشاف {len(templates)} قالب")
    
    # 3. ربط Routes بـ Templates
    linked_routes = link_routes_to_templates(routes, templates)
    linked_count = sum(1 for r in linked_routes if r['has_template'])
    print(f"✅ تم ربط {linked_count} مسار بقوالبها")
    
    # 4. تصنيف Routes
    categories = categorize_routes(linked_routes)
    
    # 5. بناء الخريطة
    system_map = {
        'generated_at': datetime.now().isoformat(),
        'system_name': 'نظام أزاد لإدارة الكراج',
        'version': '4.0.0',
        'statistics': {
            'total_routes': len(routes),
            'total_templates': len(templates),
            'linked_routes': linked_count,
            'unlinked_routes': len(routes) - linked_count,
        },
        'routes': {
            'all': linked_routes,
            'by_category': categories,
        },
        'templates': {
            'all': templates,
            'by_module': group_templates_by_module(templates),
        },
        'blueprints': extract_blueprints(routes),
        'modules': extract_modules(templates),
    }
    
    # 6. حفظ الخريطة
    save_system_map(system_map)
    
    # 7. تسجيل الحدث
    log_discovery_event('auto_build', len(routes), len(templates))
    
    print(f"\n✅ اكتمل بناء خريطة النظام!")
    print(f"📊 الإحصائيات:")
    print(f"   • المسارات: {len(routes)}")
    print(f"   • القوالب: {len(templates)}")
    print(f"   • الروابط: {linked_count}")
    
    return system_map


def group_templates_by_module(templates):
    """تجميع Templates حسب الوحدة"""
    grouped = {}
    
    for template in templates:
        module = template['module']
        if module not in grouped:
            grouped[module] = []
        grouped[module].append(template['name'])
    
    return grouped


def extract_blueprints(routes):
    """استخراج قائمة البلوپرنتات"""
    blueprints = set()
    
    for route in routes:
        if route['blueprint']:
            blueprints.add(route['blueprint'])
    
    return sorted(list(blueprints))


def extract_modules(templates):
    """استخراج قائمة الوحدات من Templates"""
    modules = set()
    
    for template in templates:
        if template['module'] != 'root':
            modules.add(template['module'])
    
    return sorted(list(modules))


def save_system_map(system_map):
    """حفظ خريطة النظام"""
    try:
        os.makedirs('instance', exist_ok=True)
        
        with open(SYSTEM_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(system_map, f, ensure_ascii=False, indent=2)
        
        print(f"✅ تم حفظ الخريطة في {SYSTEM_MAP_FILE}")
    
    except Exception as e:
        print(f"⚠️ خطأ في حفظ الخريطة: {str(e)}")


def load_system_map():
    """تحميل خريطة النظام"""
    try:
        if os.path.exists(SYSTEM_MAP_FILE):
            with open(SYSTEM_MAP_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            print("⚠️ خريطة النظام غير موجودة - سيتم إنشاؤها تلقائياً")
            return None
    
    except Exception as e:
        print(f"⚠️ خطأ في تحميل الخريطة: {str(e)}")
        return None


def log_discovery_event(event_type, routes_count, templates_count):
    """تسجيل حدث الاستكشاف"""
    try:
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'event': event_type,
            'routes_discovered': routes_count,
            'templates_discovered': templates_count,
        }
        
        logs = []
        if os.path.exists(DISCOVERY_LOG_FILE):
            with open(DISCOVERY_LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        
        logs.append(log_entry)
        
        # الاحتفاظ بآخر 50 حدث فقط
        logs = logs[-50:]
        
        with open(DISCOVERY_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    
    except Exception as e:
        print(f"⚠️ خطأ في تسجيل الحدث: {str(e)}")


def find_route_by_keyword(keyword, system_map=None):
    """البحث عن مسار حسب كلمة مفتاحية"""
    if not system_map:
        system_map = load_system_map()
    
    if not system_map:
        return []
    
    keyword_lower = keyword.lower()
    matches = []
    
    for route in system_map['routes']['all']:
        if (keyword_lower in route['endpoint'].lower() or
            keyword_lower in route['url'].lower() or
            (route['blueprint'] and keyword_lower in route['blueprint'].lower())):
            matches.append(route)
    
    return matches


def find_template_by_keyword(keyword, system_map=None):
    """البحث عن قالب حسب كلمة مفتاحية"""
    if not system_map:
        system_map = load_system_map()
    
    if not system_map:
        return []
    
    keyword_lower = keyword.lower()
    matches = []
    
    for template in system_map['templates']['all']:
        if keyword_lower in template['name'].lower():
            matches.append(template)
    
    return matches


def get_route_suggestions(user_query):
    """اقتراح مسارات بناءً على سؤال المستخدم"""
    system_map = load_system_map()
    
    if not system_map:
        return None
    
    query_lower = user_query.lower()
    
    # خريطة الكلمات المفتاحية
    keyword_map = {
        'نفق': 'expenses',
        'مصروف': 'expenses',
        'عميل': 'customers',
        'عملاء': 'customers',
        'زبون': 'customers',
        'مورد': 'vendors',
        'موردين': 'vendors',
        'مخزن': 'warehouses',
        'صيانة': 'service',
        'إصلاح': 'service',
        'فاتورة': 'invoices',
        'دفع': 'payments',
        'تقرير': 'reports',
        'مبيعات': 'sales',
        'شراء': 'purchases',
        'منتج': 'shop',
        'قطع': 'parts',
        'شحن': 'shipments',
        'شريك': 'partners',
        'حساب': 'ledger',
        'أمان': 'security',
        'مستخدم': 'users',
    }
    
    # البحث عن تطابقات
    for arabic, english in keyword_map.items():
        if arabic in query_lower or english in query_lower:
            matches = find_route_by_keyword(english, system_map)
            if matches:
                return {
                    'keyword': arabic,
                    'matches': matches[:5],  # أول 5 نتائج
                    'count': len(matches)
                }
    
    return None


def auto_discover_if_needed():
    """إعادة الاستكشاف إذا لزم الأمر"""
    if not os.path.exists(SYSTEM_MAP_FILE):
        print("🔄 لم يتم العثور على خريطة النظام - سيتم إنشاؤها...")
        return build_system_map()
    
    # فحص إذا كانت الخريطة قديمة (أكثر من 24 ساعة)
    try:
        file_time = os.path.getmtime(SYSTEM_MAP_FILE)
        age_hours = (datetime.now().timestamp() - file_time) / 3600
        
        if age_hours > 24:
            print(f"🔄 الخريطة قديمة ({age_hours:.1f} ساعة) - سيتم تحديثها...")
            return build_system_map()
    
    except:
        pass
    
    return load_system_map()


if __name__ == '__main__':
    print("🧪 اختبار نظام الاستكشاف الذاتي...")
    print("⚠️ يجب تشغيل هذا الملف من داخل Flask context")

