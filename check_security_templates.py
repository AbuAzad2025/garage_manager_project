#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""فحص قوالب وحدة الأمان"""

from app import create_app
import os

app = create_app()

with app.app_context():
    # جلب جميع routes الأمان
    security_routes = [r for r in app.url_map.iter_rules() 
                      if r.endpoint and r.endpoint.startswith('security.')]
    
    print(f"📊 إحصائيات وحدة الأمان:")
    print(f"  ✅ عدد Routes: {len(security_routes)}")
    
    # فحص القوالب المفقودة
    missing_templates = []
    existing_templates = []
    
    for route in security_routes:
        if 'api' in route.endpoint or route.endpoint == 'security.static':
            continue
        
        template_name = route.endpoint.replace('security.', '') + '.html'
        template_path = os.path.join('templates', 'security', template_name)
        
        if os.path.exists(template_path):
            existing_templates.append(template_name)
        else:
            missing_templates.append({
                'template': template_name,
                'route': route.rule,
                'endpoint': route.endpoint
            })
    
    print(f"  ✅ قوالب موجودة: {len(existing_templates)}")
    print(f"  ❌ قوالب مفقودة: {len(missing_templates)}")
    
    if missing_templates:
        print(f"\n⚠️ القوالب المفقودة:")
        for item in missing_templates[:15]:
            print(f"  ❌ {item['template']}")
            print(f"     Route: {item['route']}")
    
    # فحص المميزات الأساسية
    print(f"\n🔍 فحص المميزات الأساسية:")
    
    essential_features = [
        ('live_monitoring', 'مراقبة فورية'),
        ('user_control', 'التحكم بالمستخدمين'),
        ('sql_console', 'SQL Console'),
        ('python_console', 'Python Console'),
        ('system_settings', 'إعدادات النظام'),
        ('emergency_tools', 'أدوات الطوارئ'),
        ('data_export', 'تصدير البيانات'),
        ('performance_monitor', 'مراقبة الأداء'),
        ('system_branding', 'العلامة التجارية'),
        ('logs_viewer', 'عرض اللوجات'),
        ('integrations', 'مركز التكامل'),
    ]
    
    for endpoint_suffix, name in essential_features:
        endpoint = f'security.{endpoint_suffix}'
        route_exists = any(r.endpoint == endpoint for r in security_routes)
        template_path = os.path.join('templates', 'security', f'{endpoint_suffix}.html')
        template_exists = os.path.exists(template_path)
        
        if route_exists and template_exists:
            print(f"  ✅ {name}")
        elif route_exists and not template_exists:
            print(f"  ⚠️ {name} - Route موجود لكن القالب مفقود")
        elif not route_exists:
            print(f"  ❌ {name} - مفقود تماماً")
    
    print(f"\n✅ انتهى الفحص")

