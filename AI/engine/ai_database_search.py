"""
🔍 AI Database Search Engine - محرك البحث في قاعدة البيانات
════════════════════════════════════════════════════════════════════

وظيفة هذا الملف:
- البحث الذكي في قاعدة البيانات
- استخراج البيانات المطلوبة
- تحليل نية المستخدم (Intent Analysis)
- إرجاع نتائج منظمة للمساعد

Refactored: 2025-11-01
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import func, text, desc, or_, and_
from extensions import db
from typing import Dict, List, Any, Optional


def search_database_for_query(query: str) -> Dict[str, Any]:
    """
    البحث الذكي في قاعدة البيانات حسب السؤال
    
    Args:
        query: سؤال المستخدم
    
    Returns:
        نتائج البحث مع البيانات المطلوبة
    """
    try:
        from models import (
            Customer, Supplier, Product, ServiceRequest, Invoice,
            Payment, Expense, Warehouse, User, Sale, Shipment,
            StockLevel, Note, AuditLog, Partner
        )
        
        results = {'intent': None}
        query_lower = query.lower()
        
        # تحليل نية السؤال
        intent = analyze_query_intent(query_lower)
        results['intent'] = intent
        
        # البحث حسب النية
        entities = intent.get('entities', [])
        
        # 1. العملاء
        if 'customer' in entities or any(word in query_lower for word in ['عميل', 'زبون', 'customer']):
            results.update(search_customers(query_lower))
        
        # 2. الموردين
        if 'supplier' in entities or any(word in query_lower for word in ['مورد', 'vendor', 'supplier']):
            results.update(search_suppliers(query_lower))
        
        # 3. المنتجات
        if 'product' in entities or any(word in query_lower for word in ['منتج', 'قطعة', 'product', 'part']):
            results.update(search_products(query_lower))
        
        # 4. الصيانة
        if 'service' in entities or any(word in query_lower for word in ['صيانة', 'service', 'repair']):
            results.update(search_services(query_lower))
        
        # 5. المبيعات
        if 'sale' in entities or any(word in query_lower for word in ['مبيعات', 'بيع', 'sales', 'sell']):
            results.update(search_sales(query_lower))
        
        # 6. المدفوعات
        if 'payment' in entities or any(word in query_lower for word in ['دفع', 'payment', 'pay']):
            results.update(search_payments(query_lower))
        
        # 7. المصروفات
        if 'expense' in entities or any(word in query_lower for word in ['مصروف', 'expense', 'نفقة']):
            results.update(search_expenses(query_lower))
        
        # 8. المخزون
        if 'inventory' in entities or any(word in query_lower for word in ['مخزون', 'inventory', 'stock']):
            results.update(search_inventory(query_lower))
        
        # 9. الإحصائيات العامة
        if not results or len(results) <= 1:
            results.update(get_general_statistics())
        
        return results
        
    except Exception as e:
        return {'error': str(e), 'intent': None}


def analyze_query_intent(query_lower: str) -> Dict[str, Any]:
    """
    تحليل نية السؤال
    
    Returns:
        {
            'type': 'count|list|analysis|balance|status',
            'entities': ['customer', 'sale', ...],
            'time_scope': 'today|week|month|year|all',
            'action': 'search|calculate|report'
        }
    """
    intent = {
        'type': 'general',
        'entities': [],
        'time_scope': 'all',
        'action': 'search'
    }
    
    # تحديد نوع السؤال
    if any(word in query_lower for word in ['كم', 'عدد', 'how many', 'count']):
        intent['type'] = 'count'
        intent['action'] = 'calculate'
    elif any(word in query_lower for word in ['رصيد', 'balance', 'حساب']):
        intent['type'] = 'balance'
        intent['action'] = 'calculate'
    elif any(word in query_lower for word in ['قائمة', 'list', 'أعرض', 'show']):
        intent['type'] = 'list'
        intent['action'] = 'search'
    elif any(word in query_lower for word in ['تحليل', 'analyze', 'تقرير', 'report']):
        intent['type'] = 'analysis'
        intent['action'] = 'report'
    
    # تحديد الكيانات
    entity_keywords = {
        'customer': ['عميل', 'زبون', 'customer', 'client'],
        'supplier': ['مورد', 'vendor', 'supplier'],
        'product': ['منتج', 'قطعة', 'product', 'part', 'item'],
        'service': ['صيانة', 'service', 'repair', 'خدمة'],
        'sale': ['مبيعات', 'بيع', 'sales', 'sell'],
        'invoice': ['فاتورة', 'invoice'],
        'payment': ['دفع', 'payment', 'دفعة'],
        'expense': ['مصروف', 'expense', 'نفقة'],
        'inventory': ['مخزون', 'inventory', 'stock']
    }
    
    for entity, keywords in entity_keywords.items():
        if any(kw in query_lower for kw in keywords):
            intent['entities'].append(entity)
    
    # تحديد النطاق الزمني
    if any(word in query_lower for word in ['اليوم', 'today']):
        intent['time_scope'] = 'today'
    elif any(word in query_lower for word in ['هالأسبوع', 'this week', 'أسبوع']):
        intent['time_scope'] = 'week'
    elif any(word in query_lower for word in ['هالشهر', 'this month', 'شهر']):
        intent['time_scope'] = 'month'
    elif any(word in query_lower for word in ['هالسنة', 'this year', 'سنة']):
        intent['time_scope'] = 'year'
    
    return intent


def get_time_range(scope: str) -> tuple:
    """
    الحصول على نطاق زمني
    
    Args:
        scope: 'today', 'week', 'month', 'year', 'all'
    
    Returns:
        (start_date, end_date)
    """
    now = datetime.now(timezone.utc)
    
    if scope == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif scope == 'week':
        start = now - timedelta(days=7)
        end = now
    elif scope == 'month':
        start = now - timedelta(days=30)
        end = now
    elif scope == 'year':
        start = now - timedelta(days=365)
        end = now
    else:  # all
        start = datetime(2000, 1, 1, tzinfo=timezone.utc)
        end = now
    
    return (start, end)


def search_customers(query: str) -> Dict[str, Any]:
    """البحث في العملاء"""
    try:
        from models import Customer
        
        result = {}
        
        # عدد العملاء
        total = Customer.query.count()
        active = Customer.query.filter_by(is_active=True).count()
        
        result['customers_count'] = total
        result['customers_active'] = active
        
        # البحث بالاسم
        if len(query) > 3:
            search_results = Customer.query.filter(
                or_(
                    Customer.name.ilike(f'%{query}%'),
                    Customer.phone.ilike(f'%{query}%'),
                    Customer.email.ilike(f'%{query}%')
                )
            ).limit(10).all()
            
            if search_results:
                result['customers_found'] = [
                    {
                        'id': c.id,
                        'name': c.name,
                        'phone': c.phone,
                        'balance': float(c.balance) if hasattr(c, 'balance') else 0
                    }
                    for c in search_results
                ]
        
        # أمثلة عشوائية
        samples = Customer.query.order_by(func.random()).limit(5).all()
        result['customers_sample'] = [
            {'id': c.id, 'name': c.name, 'phone': c.phone}
            for c in samples
        ]
        
        return result
        
    except Exception as e:
        return {'customers_error': str(e)}


def search_suppliers(query: str) -> Dict[str, Any]:
    """البحث في الموردين"""
    try:
        from models import Supplier
        
        result = {}
        
        total = Supplier.query.count()
        result['suppliers_count'] = total
        
        # البحث بالاسم
        if len(query) > 3:
            search_results = Supplier.query.filter(
                or_(
                    Supplier.name.ilike(f'%{query}%'),
                    Supplier.phone.ilike(f'%{query}%')
                )
            ).limit(10).all()
            
            if search_results:
                result['suppliers_found'] = [
                    {'id': s.id, 'name': s.name, 'phone': s.phone}
                    for s in search_results
                ]
        
        return result
        
    except Exception as e:
        return {'suppliers_error': str(e)}


def search_products(query: str) -> Dict[str, Any]:
    """البحث في المنتجات"""
    try:
        from models import Product
        
        result = {}
        
        total = Product.query.count()
        result['products_count'] = total
        
        # البحث
        if len(query) > 2:
            search_results = Product.query.filter(
                or_(
                    Product.name.ilike(f'%{query}%'),
                    Product.barcode.ilike(f'%{query}%'),
                    Product.sku.ilike(f'%{query}%')
                )
            ).limit(10).all()
            
            if search_results:
                result['products_found'] = [
                    {
                        'id': p.id,
                        'name': p.name,
                        'sku': p.sku,
                        'price': float(p.price) if hasattr(p, 'price') else 0
                    }
                    for p in search_results
                ]
        
        return result
        
    except Exception as e:
        return {'products_error': str(e)}


def search_services(query: str) -> Dict[str, Any]:
    """البحث في الصيانة"""
    try:
        from models import ServiceRequest
        
        result = {}
        
        total = ServiceRequest.query.count()
        pending = ServiceRequest.query.filter_by(status='pending').count()
        completed = ServiceRequest.query.filter_by(status='completed').count()
        
        result['services_total'] = total
        result['services_pending'] = pending
        result['services_completed'] = completed
        
        return result
        
    except Exception as e:
        return {'services_error': str(e)}


def search_sales(query: str) -> Dict[str, Any]:
    """البحث في المبيعات"""
    try:
        from models import Sale
        
        result = {}
        
        total_count = Sale.query.filter_by(status='CONFIRMED').count()
        total_amount = db.session.query(func.sum(Sale.sale_total)).filter_by(
            status='CONFIRMED'
        ).scalar() or 0
        
        result['sales_count'] = total_count
        result['sales_total'] = float(total_amount)
        
        # مبيعات اليوم
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        today_sales = db.session.query(func.sum(Sale.sale_total)).filter(
            Sale.status == 'CONFIRMED',
            Sale.sale_date >= today
        ).scalar() or 0
        
        result['sales_today'] = float(today_sales)
        
        return result
        
    except Exception as e:
        return {'sales_error': str(e)}


def search_payments(query: str) -> Dict[str, Any]:
    """البحث في المدفوعات"""
    try:
        from models import Payment
        
        result = {}
        
        total_count = Payment.query.count()
        total_amount = db.session.query(func.sum(Payment.amount)).scalar() or 0
        
        result['payments_count'] = total_count
        result['payments_total'] = float(total_amount)
        
        return result
        
    except Exception as e:
        return {'payments_error': str(e)}


def search_expenses(query: str) -> Dict[str, Any]:
    """البحث في المصروفات"""
    try:
        from models import Expense
        
        result = {}
        
        total_count = Expense.query.count()
        total_amount = db.session.query(func.sum(Expense.amount)).scalar() or 0
        
        result['expenses_count'] = total_count
        result['expenses_total'] = float(total_amount)
        
        return result
        
    except Exception as e:
        return {'expenses_error': str(e)}


def search_inventory(query: str) -> Dict[str, Any]:
    """البحث في المخزون"""
    try:
        from models import StockLevel, Product, Warehouse
        
        result = {}
        
        # عدد المنتجات في المخزون
        products_in_stock = db.session.query(
            func.count(func.distinct(StockLevel.product_id))
        ).scalar() or 0
        
        result['inventory_products_count'] = products_in_stock
        
        # عدد المستودعات
        warehouses_count = Warehouse.query.count()
        result['warehouses_count'] = warehouses_count
        
        return result
        
    except Exception as e:
        return {'inventory_error': str(e)}


def get_general_statistics() -> Dict[str, Any]:
    """إحصائيات عامة عن النظام"""
    try:
        from models import (
            Customer, Supplier, Product, ServiceRequest,
            Sale, Payment, Expense, User, Warehouse
        )
        
        return {
            'general_customers': Customer.query.count(),
            'general_suppliers': Supplier.query.count(),
            'general_products': Product.query.count(),
            'general_services': ServiceRequest.query.count(),
            'general_users': User.query.count(),
            'general_warehouses': Warehouse.query.count()
        }
        
    except Exception as e:
        return {'general_error': str(e)}


__all__ = [
    'search_database_for_query',
    'analyze_query_intent',
    'get_time_range'
]

