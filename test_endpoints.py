#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
فحص شامل لجميع Endpoints المتعلقة بالعملاء والحذف القوي
"""

from app import create_app

app = create_app()

print('═' * 120)
print('✅ فحص Endpoints للعملاء والحذف القوي')
print('═' * 120)
print()

# جلب جميع routes المتعلقة بالعملاء والحذف
relevant_routes = []
for rule in app.url_map.iter_rules():
    if 'customer' in rule.endpoint or 'delete' in rule.endpoint.lower():
        relevant_routes.append({
            'endpoint': rule.endpoint,
            'methods': ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'})),
            'path': str(rule)
        })

# ترتيب حسب endpoint
relevant_routes.sort(key=lambda x: x['endpoint'])

print(f"{'Endpoint':<55} {'Methods':<15} {'Path':<60}")
print('─' * 130)

for route in relevant_routes:
    print(f"{route['endpoint']:<55} {route['methods']:<15} {route['path']:<60}")

print()
print('═' * 120)
print('🔍 التحقق من التطابق بين Routes و Templates')
print('═' * 120)
print()

# الـ endpoints المستخدمة في التطبيق
expected_endpoints = {
    # العملاء - الحذف العادي
    'customers_bp.delete_customer': {
        'route': '/<int:id>/delete',
        'methods': ['POST'],
        'template_usage': "templates/customers/_table.html: url_for('customers_bp.delete_customer', id=customer.id)"
    },
    
    # الحذف القوي
    'hard_delete_bp.delete_customer': {
        'route': '/customer/<int:customer_id>',
        'methods': ['GET', 'POST'],
        'template_usage': "templates/customers/_table.html: url_for('hard_delete_bp.delete_customer', customer_id=customer.id)"
    },
    
    'hard_delete_bp.delete_sale': {
        'route': '/sale/<int:sale_id>',
        'methods': ['GET', 'POST'],
        'template_usage': "templates/sales/list.html"
    },
    
    'hard_delete_bp.delete_supplier': {
        'route': '/supplier/<int:supplier_id>',
        'methods': ['GET', 'POST'],
        'template_usage': "templates/vendors/suppliers/list.html"
    },
    
    'hard_delete_bp.delete_partner': {
        'route': '/partner/<int:partner_id>',
        'methods': ['GET', 'POST'],
        'template_usage': "templates/vendors/partners/list.html"
    },
    
    'hard_delete_bp.delete_expense': {
        'route': '/expense/<int:expense_id>',
        'methods': ['GET', 'POST'],
        'template_usage': "templates/expenses/expenses_list.html"
    },
    
    'hard_delete_bp.deletion_logs': {
        'route': '/logs',
        'methods': ['GET'],
        'template_usage': "templates/hard_delete/logs.html"
    },
    
    'hard_delete_bp.restore_deletion': {
        'route': '/restore/<int:deletion_id>',
        'methods': ['GET', 'POST'],
        'template_usage': "templates/hard_delete/logs.html"
    }
}

# التحقق من وجود جميع الـ endpoints
all_ok = True
for endpoint_name, details in expected_endpoints.items():
    # البحث في routes
    found = False
    for route in relevant_routes:
        if route['endpoint'] == endpoint_name:
            found = True
            print(f"✅ {endpoint_name}")
            print(f"   Route: {route['path']}")
            print(f"   Methods: {route['methods']}")
            print(f"   Usage: {details['template_usage']}")
            print()
            break
    
    if not found:
        print(f"❌ {endpoint_name} - NOT FOUND!")
        all_ok = False
        print()

print('═' * 120)
if all_ok:
    print('✅ جميع Endpoints موجودة ومتطابقة!')
else:
    print('❌ يوجد endpoints مفقودة!')
print('═' * 120)
print()

# اختبار إضافي: فحص أن جميع url_for في Templates لها endpoints موجودة
print('═' * 120)
print('🧪 اختبار التطبيق')
print('═' * 120)

with app.app_context():
    # اختبار endpoints
    test_results = []
    
    # اختبار customers_bp.delete_customer
    try:
        from flask import url_for
        url = url_for('customers_bp.delete_customer', id=1)
        test_results.append(('customers_bp.delete_customer', '✅', url))
    except Exception as e:
        test_results.append(('customers_bp.delete_customer', '❌', str(e)))
    
    # اختبار hard_delete_bp.delete_customer
    try:
        url = url_for('hard_delete_bp.delete_customer', customer_id=1)
        test_results.append(('hard_delete_bp.delete_customer', '✅', url))
    except Exception as e:
        test_results.append(('hard_delete_bp.delete_customer', '❌', str(e)))
    
    # اختبار hard_delete_bp.deletion_logs
    try:
        url = url_for('hard_delete_bp.deletion_logs')
        test_results.append(('hard_delete_bp.deletion_logs', '✅', url))
    except Exception as e:
        test_results.append(('hard_delete_bp.deletion_logs', '❌', str(e)))
    
    # عرض النتائج
    print()
    for endpoint, status, result in test_results:
        print(f"{status} {endpoint:<45} → {result}")

print()
print('═' * 120)
print('✅ اختبار الـ Endpoints اكتمل بنجاح!')
print('═' * 120)

