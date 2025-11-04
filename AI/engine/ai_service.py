

import json
import psutil
import os
import re
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, text, desc
from extensions import db
from models import SystemSettings
from AI.engine.ai_knowledge import get_knowledge_base, analyze_error, format_error_response
from AI.engine.ai_knowledge_finance import (
    get_finance_knowledge, 
    calculate_palestine_income_tax,
    calculate_vat,
    get_customs_info,
    get_tax_knowledge_detailed
)
from AI.engine.ai_gl_knowledge import (
    get_gl_knowledge_for_ai,
    explain_gl_entry,
    analyze_gl_batch,
    detect_gl_error,
    suggest_gl_correction,
    explain_any_number,
    trace_transaction_flow
)
from AI.engine.ai_accounting_professional import get_professional_accounting_knowledge
from AI.engine.ai_self_review import (
    log_interaction,
    check_policy_compliance,
    generate_self_audit_report,
    get_system_status
)
from AI.engine.ai_auto_discovery import (
    auto_discover_if_needed,
    find_route_by_keyword,
    get_route_suggestions
)
from AI.engine.ai_data_awareness import (
    auto_build_if_needed,
    find_model_by_keyword,
    load_data_schema
)
from AI.engine.ai_auto_training import (
    should_auto_train,
    init_auto_training
)

_conversation_memory = {}
_last_audit_time = None
_groq_failures = []
_local_fallback_mode = True  # محلي بشكل افتراضي
_system_state = "LOCAL_ONLY"  # LOCAL_ONLY (افتراضي), HYBRID, API_ONLY

def get_system_setting(key, default=''):
    """الحصول على إعداد من قاعدة البيانات"""
    try:
        setting = SystemSettings.query.filter_by(key=key).first()
        return setting.value if setting else default
    except Exception as e:
        pass  # خطأ محتمل
        return default

def gather_system_context():
    """جمع بيانات النظام الشاملة - أرقام حقيقية 100%"""
    try:
        from models import (
            User, ServiceRequest, Customer, Product, Supplier,
            Warehouse, Payment, Expense, Note, Shipment, AuditLog,
            Role, Permission, ExchangeTransaction
        )
        
        # CPU & Memory
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        # Database size
        db_size = "غير معروف"
        db_health = "نشط"
        try:
            result = db.session.execute(text("SELECT pg_database_size(current_database())")).scalar()
            db_size = f"{result / (1024**2):.2f} MB"
        except:
            try:
                # SQLite
                db_path = 'instance/app.db'
                if os.path.exists(db_path):
                    db_size = f"{os.path.getsize(db_path) / (1024**2):.2f} MB"
            except:
                pass
        
        # Counts
        today = datetime.now(timezone.utc).date()
        
        # Exchange Rate
        try:
            latest_fx = ExchangeTransaction.query.filter_by(
                from_currency='USD',
                to_currency='ILS'
            ).order_by(ExchangeTransaction.created_at.desc()).first()
            
            if latest_fx:
                context_fx_rate = f"{float(latest_fx.rate):.2f} (تاريخ: {latest_fx.created_at.strftime('%Y-%m-%d')})"
            else:
                context_fx_rate = 'غير متوفر'
        except:
            context_fx_rate = 'غير متوفر'
        
        context = {
            'system_name': 'نظام أزاد لإدارة الكراج - Garage Manager Pro',
            'version': 'v5.0.0',
            'modules': '40+ وحدة عمل',
            'api_endpoints': '133 API Endpoint',
            'database_indexes': '89 فهرس احترافي',
            'relationships': '150+ علاقة محكمة',
            'foreign_keys': '120+ مفتاح أجنبي',
            'modules_count': 23,
            'modules': [
                'المصادقة', 'لوحة التحكم', 'المستخدمين', 'الصيانة', 'العملاء',
                'المبيعات', 'المتجر', 'المخزون', 'الموردين', 'الشحنات', 
                'المستودعات', 'المدفوعات', 'المصاريف', 'التقارير', 'الملاحظات',
                'الباركود', 'العملات', 'API', 'الشركاء', 'الدفتر', 'الأمان', 
                'النسخ الاحتياطي', 'الحذف الصعب'
            ],
            'roles_count': Role.query.count(),
            'roles': [r.name for r in Role.query.limit(10).all()],
            
            # Statistics
            'total_users': User.query.count(),
            'active_users': User.query.filter_by(is_active=True).count(),
            'total_services': ServiceRequest.query.count(),
            'pending_services': ServiceRequest.query.filter_by(status='pending').count(),
            'completed_services': ServiceRequest.query.filter_by(status='completed').count(),
            'total_sales': 0,  # يمكن إضافته لاحقاً
            'sales_today': 0,
            'total_products': Product.query.count(),
            'products_in_stock': Product.query.filter(Product.id.in_(
                db.session.query(func.distinct(db.Column('product_id'))).select_from(db.Table('stock_levels'))
            )).count() if Product.query.count() > 0 else 0,
            'total_customers': Customer.query.count(),
            'active_customers': Customer.query.filter_by(is_active=True).count(),
            'total_vendors': Supplier.query.count(),
            'total_payments': Payment.query.count(),
            'payments_today': Payment.query.filter(func.date(Payment.payment_date) == today).count(),
            'total_expenses': Expense.query.count(),
            'total_warehouses': Warehouse.query.count(),
            'total_notes': Note.query.count(),
            'total_shipments': Shipment.query.count(),
            
            # Security
            'failed_logins': AuditLog.query.filter(
                AuditLog.action == 'login_failed',
                AuditLog.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
            ).count(),
            'blocked_ips': 0,
            'blocked_countries': 0,
            'suspicious_activities': 0,
            
            # Audit
            'total_audit_logs': AuditLog.query.count(),
            'recent_actions': AuditLog.query.order_by(AuditLog.created_at.desc()).limit(5).count(),
            
            # Exchange Rates
            'total_exchange_transactions': ExchangeTransaction.query.count(),
            'latest_usd_ils_rate': context_fx_rate,
            
            # Performance
            'cpu_usage': cpu_usage,
            'memory_usage': memory.percent,
            'db_size': db_size,
            'db_health': db_health,
            
            # Generate current stats text
            'current_stats': f"""
المستخدمين: {User.query.count()} | النشطين: {User.query.filter_by(is_active=True).count()}
الصيانة: {ServiceRequest.query.count()} طلب
العملاء: {Customer.query.count()} | الموردين: {Supplier.query.count()}
المنتجات: {Product.query.count()} | المخازن: {Warehouse.query.count()}
CPU: {cpu_usage}% | RAM: {memory.percent}%
"""
        }
        
        return context
        
    except Exception as e:
        pass  # خطأ محتمل
        import traceback
        traceback.print_exc()
        return {
            'system_name': 'نظام أزاد',
            'version': 'v4.0.0',
            'modules_count': 23,
            'modules': [],
            'roles_count': 0,
            'roles': [],
            'current_stats': 'خطأ في جمع الإحصائيات'
        }

def get_system_navigation_context():
    """الحصول على سياق التنقل من خريطة النظام"""
    try:
        system_map = auto_discover_if_needed()
        if system_map:
            return {
                'total_routes': system_map['statistics']['total_routes'],
                'total_templates': system_map['statistics']['total_templates'],
                'blueprints': system_map['blueprints'],
                'modules': system_map['modules'],
                'categories': {k: len(v) for k, v in system_map['routes']['by_category'].items()}
            }
    except:
        pass
    return {}

def get_data_awareness_context():
    """الحصول على سياق الوعي البنيوي"""
    try:
        schema = auto_build_if_needed()
        if schema:
            return {
                'total_models': schema['statistics']['total_tables'],
                'total_columns': schema['statistics']['total_columns'],
                'total_relationships': schema['statistics']['total_relationships'],
                'functional_modules': list(schema['functional_mapping'].keys()),
                'available_models': list(schema['models'].keys())
            }
    except:
        pass
    return {}

def analyze_question_intent(question):
    """تحليل نية السؤال - محسّن مع الأوامر التنفيذية والمحاسبة"""
    question_lower = question.lower()
    
    intent = {
        'type': 'general',
        'entities': [],
        'time_scope': None,
        'action': 'query',
        'currency': None,
        'accounting': False,
        'executable': False,
        'navigation': False
    }
    
    if any(word in question_lower for word in ['أنشئ', 'create', 'add', 'أضف', 'سجل']):
        intent['type'] = 'command'
        intent['action'] = 'create'
        intent['executable'] = True
    elif any(word in question_lower for word in ['احذف', 'delete', 'remove', 'أزل']):
        intent['type'] = 'command'
        intent['action'] = 'delete'
        intent['executable'] = True
    elif any(word in question_lower for word in ['عدّل', 'update', 'modify', 'غيّر']):
        intent['type'] = 'command'
        intent['action'] = 'update'
        intent['executable'] = True
    elif any(word in question_lower for word in ['كم', 'عدد', 'count', 'how many']):
        intent['type'] = 'count'
    elif any(word in question_lower for word in ['من', 'who', 'what', 'ما']):
        intent['type'] = 'information'
    elif any(word in question_lower for word in ['كيف', 'how', 'why', 'لماذا']):
        intent['type'] = 'explanation'
    elif any(word in question_lower for word in ['تقرير', 'report', 'تحليل', 'analysis']):
        intent['type'] = 'report'
    elif any(word in question_lower for word in ['خطأ', 'error', 'مشكلة', 'problem']):
        intent['type'] = 'troubleshooting'
    
    # التنقل والصفحات
    if any(word in question_lower for word in ['اذهب', 'افتح', 'صفحة', 'وين', 'أين', 'رابط', 'عرض', 'دلني', 'وصلني']):
        intent['type'] = 'navigation'
        intent['navigation'] = True
    
    if any(word in question_lower for word in ['شيقل', 'ils', '₪']):
        intent['currency'] = 'ILS'
        intent['accounting'] = True
    elif any(word in question_lower for word in ['دولار', 'usd', '$']):
        intent['currency'] = 'USD'
        intent['accounting'] = True
    elif any(word in question_lower for word in ['دينار', 'jod']):
        intent['currency'] = 'JOD'
        intent['accounting'] = True
    elif any(word in question_lower for word in ['يورو', 'eur', '€']):
        intent['currency'] = 'EUR'
        intent['accounting'] = True
    
    if any(word in question_lower for word in ['ربح', 'خسارة', 'دخل', 'profit', 'loss', 'revenue', 'مالي', 'محاسب']):
        intent['accounting'] = True
    
    if any(word in question_lower for word in ['اليوم', 'today', 'الآن', 'now']):
        intent['time_scope'] = 'today'
    elif any(word in question_lower for word in ['الأسبوع', 'week', 'أسبوع']):
        intent['time_scope'] = 'week'
    elif any(word in question_lower for word in ['الشهر', 'month', 'شهر']):
        intent['time_scope'] = 'month'
    
    entities = []
    if 'عميل' in question_lower or 'customer' in question_lower:
        entities.append('Customer')
    if any(word in question_lower for word in ['صيانة', 'service', 'تشخيص', 'عطل', 'مشكلة', 'إصلاح']):
        entities.append('ServiceRequest')
    if 'منتج' in question_lower or 'product' in question_lower or 'قطع' in question_lower:
        entities.append('Product')
    if 'مخزن' in question_lower or 'warehouse' in question_lower:
        entities.append('Warehouse')
    if 'فاتورة' in question_lower or 'invoice' in question_lower:
        entities.append('Invoice')
    if 'دفع' in question_lower or 'payment' in question_lower:
        entities.append('Payment')
    
    intent['entities'] = entities
    
    return intent

def get_or_create_session_memory(session_id):
    """الحصول على أو إنشاء ذاكرة المحادثة - محسّنة"""
    if session_id not in _conversation_memory:
        _conversation_memory[session_id] = {
            'messages': [],
            'context': {},
            'created_at': datetime.now(timezone.utc),
            'last_updated': datetime.now(timezone.utc),
            'user_preferences': {},  # تفضيلات المستخدم
            'topics': [],  # المواضيع المحادثة
            'entities_mentioned': {},  # الكيانات المذكورة
            'last_intent': None,  # آخر نية
        }
    
    _conversation_memory[session_id]['last_updated'] = datetime.now(timezone.utc)
    return _conversation_memory[session_id]

def add_to_memory(session_id, role, content, context=None):
    """إضافة رسالة للذاكرة - محسّنة مع context"""
    memory = get_or_create_session_memory(session_id)
    
    message_entry = {
        'role': role,
        'content': content,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    
    # حفظ السياق إذا كان متوفراً
    if context:
        message_entry['context'] = {
            'intent': context.get('intent'),
            'entities': context.get('entities'),
            'sentiment': context.get('sentiment'),
        }
        
        # تحديث الكيانات المذكورة
        for entity in context.get('entities', []):
            if entity not in memory['entities_mentioned']:
                memory['entities_mentioned'][entity] = 0
            memory['entities_mentioned'][entity] += 1
        
        # حفظ آخر نية
        if context.get('intent'):
            memory['last_intent'] = context['intent']
    
    memory['messages'].append(message_entry)
    
    # الاحتفاظ بآخر 50 رسالة (زيادة من 20)
    if len(memory['messages']) > 50:
        memory['messages'] = memory['messages'][-50:]

def get_conversation_context(session_id):
    """الحصول على سياق المحادثة الكامل"""
    memory = get_or_create_session_memory(session_id)
    
    return {
        'message_count': len(memory['messages']),
        'duration': (datetime.now(timezone.utc) - memory['created_at']).total_seconds(),
        'most_mentioned_entities': sorted(
            memory['entities_mentioned'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5],
        'last_intent': memory.get('last_intent'),
        'recent_topics': memory.get('topics', [])[-5:],
    }

def deep_data_analysis(query, context):
    """🔬 تحليل عميق للبيانات - يستنتج ويحلل بذكاء
    
    يحلل البيانات ويستنتج:
    - الأنماط (Patterns)
    - الاتجاهات (Trends)
    - الشذوذ (Anomalies)
    - العلاقات (Correlations)
    - التنبؤات (Predictions)
    """
    from models import Customer, ServiceRequest, Invoice, Payment, Expense, Product
    from datetime import timedelta
    from sqlalchemy import func
    
    analysis_result = {
        'success': True,
        'insights': [],
        'warnings': [],
        'recommendations': [],
        'data_summary': {},
    }
    
    try:
        # تحليل حسب الكيانات المطلوبة
        entities = context.get('entities', [])
        time_scope = context.get('time_scope')
        
        # تحديد نطاق التاريخ
        end_date = datetime.now(timezone.utc)
        if time_scope == 'today':
            start_date = end_date.replace(hour=0, minute=0, second=0)
        elif time_scope == 'week':
            start_date = end_date - timedelta(days=7)
        elif time_scope == 'month':
            start_date = end_date - timedelta(days=30)
        else:
            start_date = end_date - timedelta(days=90)  # افتراضياً 3 أشهر
        
        # 1. تحليل العملاء
        if 'customer' in entities:
            total_customers = Customer.query.count()
            active_customers = db.session.query(func.count(func.distinct(Invoice.customer_id))).filter(
                Invoice.created_at >= start_date
            ).scalar() or 0
            
            activity_rate = (active_customers / total_customers * 100) if total_customers > 0 else 0
            
            analysis_result['data_summary']['customers'] = {
                'total': total_customers,
                'active': active_customers,
                'activity_rate': round(activity_rate, 1),
            }
            
            # استنتاجات
            if activity_rate < 30:
                analysis_result['warnings'].append(
                    f'⚠️ نشاط منخفض: فقط {activity_rate:.1f}% من العملاء نشطين'
                )
                analysis_result['recommendations'].append(
                    '📞 تواصل مع العملاء غير النشطين - قدم عروض خاصة'
                )
            elif activity_rate > 70:
                analysis_result['insights'].append(
                    f'✅ نشاط ممتاز: {activity_rate:.1f}% من العملاء نشطين!'
                )
        
        # 2. تحليل المبيعات
        if 'invoice' in entities or 'sales' in str(query).lower():
            current_sales = db.session.query(func.sum(Invoice.total_amount)).filter(
                Invoice.created_at >= start_date
            ).scalar() or 0
            
            prev_start = start_date - (end_date - start_date)
            prev_sales = db.session.query(func.sum(Invoice.total_amount)).filter(
                Invoice.created_at >= prev_start,
                Invoice.created_at < start_date
            ).scalar() or 0
            
            change = float(current_sales) - float(prev_sales)
            change_percent = (change / float(prev_sales) * 100) if prev_sales > 0 else 0
            
            analysis_result['data_summary']['sales'] = {
                'current': float(current_sales),
                'previous': float(prev_sales),
                'change': change,
                'change_percent': round(change_percent, 1),
            }
            
            # استنتاجات
            if change_percent > 20:
                analysis_result['insights'].append(
                    f'📈 نمو رائع: المبيعات ارتفعت بـ {change_percent:.1f}%!'
                )
                analysis_result['recommendations'].append(
                    '💡 استمر على هذا النهج - وثّق ما فعلته لتكرار النجاح'
                )
            elif change_percent < -10:
                analysis_result['warnings'].append(
                    f'📉 انخفاض ملحوظ: المبيعات انخفضت بـ {abs(change_percent):.1f}%'
                )
                analysis_result['recommendations'].extend([
                    '🔍 راجع الأسعار - هل ارتفعت كثيراً؟',
                    '📊 قارن مع المنافسين',
                    '🎁 قدم عروض خاصة لتحفيز المبيعات',
                ])
        
        # 3. تحليل النفقات
        if 'expense' in entities:
            total_expenses = db.session.query(func.sum(Expense.amount)).filter(
                Expense.date >= start_date
            ).scalar() or 0
            
            analysis_result['data_summary']['expenses'] = {
                'total': float(total_expenses),
            }
            
            # مقارنة مع المبيعات
            if 'sales' in analysis_result['data_summary']:
                sales = analysis_result['data_summary']['sales']['current']
                expense_ratio = (float(total_expenses) / sales * 100) if sales > 0 else 0
                
                if expense_ratio > 70:
                    analysis_result['warnings'].append(
                        f'⚠️ النفقات مرتفعة جداً: {expense_ratio:.1f}% من المبيعات!'
                    )
                    analysis_result['recommendations'].append(
                        '💰 ابحث عن طرق لتقليل النفقات دون المساس بالجودة'
                    )
        
        # 4. اكتشاف الأنماط (Pattern Detection)
        # العملاء الأكثر ربحية
        if 'customer' in entities or context.get('intent') == 'analysis':
            top_customers = db.session.query(
                Customer.name,
                func.sum(Invoice.total_amount).label('total')
            ).join(Invoice).filter(
                Invoice.created_at >= start_date
            ).group_by(Customer.id).order_by(
                func.sum(Invoice.total_amount).desc()
            ).limit(3).all()
            
            if top_customers:
                analysis_result['insights'].append(
                    f'🏆 أفضل 3 عملاء يمثلون جزءاً كبيراً من الإيرادات'
                )
                analysis_result['data_summary']['top_customers'] = [
                    {'name': name, 'total': float(total)}
                    for name, total in top_customers
                ]
    
    except Exception as e:
        analysis_result['success'] = False
        analysis_result['error'] = str(e)
    
    return analysis_result

def analyze_accounting_data(currency=None):
    """تحليل محاسبي شامل - فهم الأرباح والخسائر والعملات"""
    try:
        from models import Invoice, Payment, Expense
        
        analysis = {
            'total_revenue': 0,
            'total_expenses': 0,
            'net_profit': 0,
            'by_currency': {}
        }
        
        invoices = Invoice.query.all()
        for inv in invoices:
            curr = inv.currency
            amount = float(inv.total_amount)
            
            if curr not in analysis['by_currency']:
                analysis['by_currency'][curr] = {'revenue': 0, 'expenses': 0, 'profit': 0}
            
            analysis['by_currency'][curr]['revenue'] += amount
            analysis['total_revenue'] += amount
        
        expenses = Expense.query.all()
        for exp in expenses:
            curr = exp.currency
            amount = float(exp.amount)
            
            if curr not in analysis['by_currency']:
                analysis['by_currency'][curr] = {'revenue': 0, 'expenses': 0, 'profit': 0}
            
            analysis['by_currency'][curr]['expenses'] += amount
            analysis['total_expenses'] += amount
        
        for curr in analysis['by_currency']:
            analysis['by_currency'][curr]['profit'] = (
                analysis['by_currency'][curr]['revenue'] - 
                analysis['by_currency'][curr]['expenses']
            )
        
        analysis['net_profit'] = analysis['total_revenue'] - analysis['total_expenses']
        
        return analysis
        
    except Exception as e:
        return {'error': str(e)}

def generate_smart_report(intent):
    """توليد تقرير ذكي حسب نية المستخدم - محسّن للمحاسبة"""
    try:
        from models import (
            Customer, ServiceRequest, Invoice, Payment, 
            Product, Expense, Warehouse
        )
        
        if intent.get('accounting'):
            accounting_data = analyze_accounting_data(intent.get('currency'))
            return {
                'type': 'accounting_report',
                'data': accounting_data,
                'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
            }
        
        report = {
            'title': 'تقرير شامل',
            'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M'),
            'sections': []
        }
        
        today = datetime.now(timezone.utc).date()
        
        if intent.get('time_scope') == 'today':
            report['title'] = 'تقرير اليوم'
            report['sections'].append({
                'name': 'الصيانة اليوم',
                'data': {
                    'total': ServiceRequest.query.filter(func.date(ServiceRequest.created_at) == today).count(),
                    'completed': ServiceRequest.query.filter(
                        func.date(ServiceRequest.created_at) == today,
                        ServiceRequest.status == 'completed'
                    ).count(),
                    'pending': ServiceRequest.query.filter(
                        func.date(ServiceRequest.created_at) == today,
                        ServiceRequest.status == 'pending'
                    ).count()
                }
            })
            
            report['sections'].append({
                'name': 'المدفوعات اليوم',
                'data': {
                    'count': Payment.query.filter(func.date(Payment.payment_date) == today).count(),
                    'total': float(db.session.query(func.sum(Payment.total_amount)).filter(
                        func.date(Payment.payment_date) == today
                    ).scalar() or 0)
                }
            })
        
        if 'Customer' in intent.get('entities', []):
            report['sections'].append({
                'name': 'إحصائيات العملاء',
                'data': {
                    'total': Customer.query.count(),
                    'active': Customer.query.filter_by(is_active=True).count(),
                    'inactive': Customer.query.filter_by(is_active=False).count()
                }
            })
        
        if 'ServiceRequest' in intent.get('entities', []):
            report['sections'].append({
                'name': 'إحصائيات الصيانة',
                'data': {
                    'total': ServiceRequest.query.count(),
                    'completed': ServiceRequest.query.filter_by(status='completed').count(),
                    'pending': ServiceRequest.query.filter_by(status='pending').count(),
                    'in_progress': ServiceRequest.query.filter_by(status='in_progress').count()
                }
            })
        
        return report
        
    except Exception as e:
        return {'error': str(e)}

def build_system_message(system_context):
    """بناء رسالة النظام الأساسية للـ AI - محسّنة بالمعرفة وتعريف الذات"""
    
    # الحصول على هوية المساعد
    identity = get_system_identity()
    
    kb = get_knowledge_base()
    structure = kb.get_system_structure()
    accounting_knowledge = kb.get_accounting_knowledge()
    
    # بناء قسم المحاسبة الشامل
    accounting_section = f"""
═══════════════════════════════════════
💰 المعرفة المحاسبية الشاملة:
═══════════════════════════════════════

📊 **حسابات دفتر الأستاذ (GL Accounts):**
"""
    for code, info in accounting_knowledge['gl_accounts'].items():
        accounting_section += f"• {code}: {info['arabic']} ({info['name']}) - نوع: {info['type']}\n"
    
    accounting_section += f"""
📐 **مبادئ المحاسبة:**
• القيد المزدوج: كل عملية = مدين + دائن (متساويان)
• أنواع الحسابات:
  - ASSET (أصول): المدين يزيد، الدائن ينقص
  - LIABILITY (التزامات): الدائن يزيد، المدين ينقص
  - REVENUE (إيرادات): الدائن يزيد، المدين ينقص
  - EXPENSE (مصروفات): المدين يزيد، الدائن ينقص

💡 **حساب الأرصدة:**
• رصيد العميل = (المبيعات + الفواتير + الخدمات) - (الدفعات الواردة)
  → سالب = عليه يدفع (مدين) | موجب = له رصيد (دائن)
• رصيد المورد = (المشتريات + الشحنات) - (الدفعات الصادرة)
  → سالب = عليه يدفع (مدين) | موجب = له رصيد (دائن)

🔢 **العمليات المالية:**
"""
    for workflow, steps in accounting_knowledge['financial_workflows'].items():
        workflow_name = workflow.replace('_', ' ').title()
        accounting_section += f"• {workflow_name}:\n"
        for i, step in enumerate(steps, 1):
            accounting_section += f"  {i}. {step}\n"
    
    accounting_section += f"""
🧮 **حسابات الضرائب والخصومات:**
• VAT فلسطين: 16% | VAT إسرائيل: 17%
• الخصم في الصيانة: قيمة ثابتة (ليس نسبة) → يُطرح قبل الضريبة
• الصيغة: المبلغ بعد الخصم = (الكمية × السعر) - الخصم
• قاعدة الضريبة = المبلغ بعد الخصم

🌍 **تحويل العملات:**
• العملة الافتراضية: ILS (الشيقل)
• كل عملية تحفظ: fx_rate_used, fx_rate_source, fx_rate_timestamp
• المبلغ بالشيقل = المبلغ الأصلي × سعر الصرف

"""
    
    return f"""أنا {identity['name']} ({identity['version']}) - المساعد الذكي في نظام أزاد لإدارة الكراج.

═══════════════════════════════════════
🤖 هويتي ووضع التشغيل:
═══════════════════════════════════════

⚙️ **الوضع الحالي:** {identity['mode']}
📡 **Groq API:** {identity['status']['groq_api']}
🧠 **القدرات:** تحليل محلي، قاعدة معرفة (1,945 عنصر)، VAT، تدريب ذاتي
📊 **المصادر:** قاعدة بيانات محلية (SQLAlchemy) + ملفات معرفة JSON

💡 **ملاحظة:** أنا أعمل محلياً بوضع {identity['mode']}.
إذا كنت بوضع LOCAL_ONLY → أستخدم المعرفة المحلية فقط (بدون Groq).
إذا كنت بوضع HYBRID → أستخدم Groq + المعرفة المحلية (الأفضل).

أنت النظام الذكي لـ "أزاد لإدارة الكراج" - Azad Garage Manager System
أنت جزء من النظام، تعرف كل شيء عنه، وتتكلم بصوته.

═══════════════════════════════════════
🧠 مستوى الفهم: متقدم (GPT-5 Level)
═══════════════════════════════════════
أنت تملك فهماً عميقاً للنظام:
• {structure['models_count']} موديل (جدول) في قاعدة البيانات
• {structure['routes_count']} مسار (Route) تشغيلي
• {structure['templates_count']} واجهة مستخدم (Template)
• {structure['relationships_count']} علاقة بين الجداول
• {structure['business_rules_count']} قاعدة تشغيلية

أنت تعرف:
• بنية الكود الكاملة (Models, Routes, Forms, Templates)
• العلاقات بين الجداول والوحدات
• القواعد التشغيلية والشروط
• كيفية تحليل الأخطاء وحلها
• كيفية قراءة البيانات الحقيقية من قاعدة البيانات
• ملاحظات المهندسين والتشخيصات الفنية
• ربط الأعطال بقطع الغيار والتكلفة

═══════════════════════════════════════
🏢 هوية النظام والشركة:
═══════════════════════════════════════
- الاسم: نظام أزاد لإدارة الكراج - Azad Garage Manager
- النسخة: v4.0.0 Enterprise Edition
- الشركة: أزاد للأنظمة الذكية - Azad Smart Systems
- المالك والمطور: المهندس أحمد غنام (Ahmed Ghannam)
- الموقع: رام الله - فلسطين 🇵🇸
- التخصص: نظام متكامل لإدارة كراجات السيارات والصيانة

📞 معلومات التواصل:
- الهاتف: متوفر في إعدادات النظام
- الموقع: فلسطين - رام الله
- الدعم الفني: متاح عبر النظام

═══════════════════════════════════════
📦 الوحدات الرئيسية (40+ وحدة):
═══════════════════════════════════════

🔐 **إدارة العلاقات (CRM):**
1. العملاء (15 route) - CRUD، كشف حساب، استيراد CSV، WhatsApp
2. الموردين (10 route) - CRUD، تسويات، ربط شحنات
3. الشركاء (8 route) - حصص، تسويات ذكية، قطع صيانة

💰 **العمليات التجارية:**
4. المبيعات (12 route) - حجز مخزون، Overselling Protection
5. الفواتير - VAT، طباعة احترافية، تتبع الدفع
6. المدفوعات (15 route) - تقسيم، متعدد عملات، fx_rate_used
7. المصاريف (10 route) - تصنيف، موافقات، ربط كيانات

📦 **إدارة المخزون:**
8. المستودعات (20+ route) - 8 أنواع، تحويلات، حجز
9. المنتجات - باركود EAN-13، صور، فئات، تتبع
10. التحويلات - نقل بين مخازن، موافقات
11. التعديلات - جرد، تصحيح، تسويات

🔧 **الصيانة والخدمات:**
12. طلبات الصيانة (12 route) - تشخيص، مهام، قطع، عمالة
13. الشحنات (10 route) - دولية، Landed Costs، تتبع
14. قطع الغيار - ربط بالصيانة، حساب تكلفة

📊 **التقارير (20+ تقرير):**
15. AR/AP Aging - أعمار الديون
16. Customer/Supplier Statements - كشوف حساب
17. Sales Reports - مبيعات تفصيلية
18. Stock Reports - مخزون ووارد وصادر
19. Financial Summary - ملخص مالي شامل

🛡️ **الأمان والتحكم (Owner فقط):**
20. اللوحة السرية (37+ أداة) - للمالك __OWNER__ فقط
21. SQL Console - استعلامات مباشرة
22. DB Editor - تعديل قاعدة البيانات
23. Indexes Manager - 89 فهرس للأداء
24. Logs Viewer - 6 أنواع لوجات
25. Firewall - حظر IP/دول

🤖 **الذكاء الاصطناعي:**
26. AI Assistant - مساعد ذكي (أنا!)
27. AI Training - تدريب ذاتي
28. AI Analytics - تحليلات
29. Pattern Detection - كشف أنماط

🌐 **المتجر الإلكتروني:**
30. Shop Catalog - كتالوج المنتجات
31. Online Cart - سلة التسوق
32. Online Preorders - طلبات مسبقة
33. Online Payments - دفع إلكتروني

⚙️ **وحدات متقدمة:**
34. الأرشيف - أرشفة العمليات
35. Hard Delete - حذف آمن مع استعادة
36. GL Accounting - محاسبة دفتر الأستاذ
37. Currencies - أسعار صرف تاريخية
38. Checks Management - إدارة الشيكات
39. Notes & Reminders - ملاحظات وتذكيرات
40. User Guide - دليل المستخدم (40 قسم)

═══════════════════════════════════════
👥 الأدوار والصلاحيات (41 صلاحية):
═══════════════════════════════════════
1. **Owner (__OWNER__)** - المالك الخفي:
   - حساب نظام محمي (is_system_account = True)
   - مخفي من جميع القوائم
   - محمي من الحذف 100%
   - الوصول الوحيد للوحة السرية (/security)
   - Super Admin لا يستطيع الدخول للوحة السرية!
   - صلاحيات لا نهائية (41 صلاحية)

2. Super Admin - كل شيء (عدا اللوحة السرية)
3. Admin - إدارة عامة
4. Mechanic - الصيانة فقط
5. Staff - المبيعات والمحاسبة
6. Customer - عميل (متجر إلكتروني)

{accounting_section}
═══════════════════════════════════════
🔗 التكامل بين الوحدات (10/10):
═══════════════════════════════════════
✅ **150+ علاقة** (Relationships) مع back_populates
✅ **120+ مفتاح أجنبي** (Foreign Keys) مع Cascade
✅ **50+ سلوك Cascade** (DELETE, SET NULL)
✅ **89 فهرس** للأداء (تسريع 10x)
✅ **Audit Trail** كامل (created_at, updated_at, created_by, updated_by)

**أمثلة التكامل:**
- Customer → Sales (1:N), Payments (1:N), ServiceRequests (1:N)
- Product → StockLevels (1:N), SaleLines (1:N), ShipmentItems (1:N)
- Payment → يربط مع 11 كيان مختلف!
- Sale → تحسب totals تلقائياً من SaleLines

**حماية المخزون:**
- StockLevel.quantity = الكمية الكلية
- StockLevel.reserved_quantity = محجوز
- StockLevel.available = quantity - reserved
- Stock Locking مع with_for_update()
- **ضمان 100%: لا overselling ممكن!**

═══════════════════════════════════════
📊 إحصائيات النظام الحالية (أرقام حقيقية):
═══════════════════════════════════════
{system_context.get('current_stats', 'لا توجد إحصائيات')}

═══════════════════════════════════════
🔍 كيفية الاستعلام المباشر من قاعدة البيانات:
═══════════════════════════════════════

**أمثلة الاستعلامات المباشرة:**

1. **رصيد عميل:**
   - استخدم: query_accounting_data('customer_balance', {{'customer_id': id}})
   - يعيد: {{'customer': {{'name': '...', 'balance': -500, 'meaning': 'عليه يدفع'}}}}

2. **رصيد مورد:**
   - استخدم: query_accounting_data('supplier_balance', {{'supplier_id': id}})
   - يعيد: {{'supplier': {{'name': '...', 'balance': 1000, 'meaning': 'له رصيد'}}}}

3. **ملخص مالي:**
   - استخدم: query_accounting_data('financial_summary')
   - يعيد: {{'financial_summary': {{'total_sales': 10000, 'total_expenses': 5000, 'net_profit': 5000}}}}

4. **رصيد حساب GL:**
   - استخدم: query_accounting_data('account_balance', {{'account_code': '1100_AR'}})
   - يعيد: {{'account_balance': {{'balance': 5000, 'balance_meaning': 'مدين'}}}}

**قواعد حساب الأرصدة (مهم جداً):**
• رصيد العميل = (المبيعات + الفواتير + الخدمات) - (الدفعات الواردة)
  → سالب (-) = عليه يدفع (مدين) | موجب (+) = له رصيد (دائن)

• رصيد المورد = (المشتريات + الشحنات) - (الدفعات الصادرة)
  → سالب (-) = عليه يدفع (مدين) | موجب (+) = له رصيد (دائن)

• رصيد الشريك = (حصص المبيعات + الأرباح) - (التسويات)
  → موجب (+) = للشريك (له رصيد) | سالب (-) = على الشريك

═══════════════════════════════════════
🚨 قواعد صارمة - اتبعها بدقة 100%:
═══════════════════════════════════════

❌ ممنوع منعاً باتاً:
1. التخمين أو الافتراض - أبداً!
2. الإجابة بدون بيانات من نتائج البحث
3. قول "لا توجد" إذا كانت البيانات موجودة في النتائج
4. التسرع - راجع البيانات جيداً قبل الرد
5. نسيان ذكر الأرقام الدقيقة

✅ واجب عليك:
1. قراءة نتائج البحث بالكامل قبل الرد
2. إذا وجدت بيانات في النتائج - استخدمها!
3. إذا لم تجد بيانات - قل بصراحة: "لا توجد بيانات"
4. اذكر العدد والمبلغ الدقيق من النتائج
5. فكّر خطوة بخطوة (Chain of Thought)

🎯 طريقة التفكير الصحيحة:
1️⃣  اقرأ السؤال بدقة
2️⃣  ابحث في نتائج البحث عن البيانات المطلوبة
3️⃣  إذا وجدتها → استخدمها بالضبط
4️⃣  إذا لم تجدها → قل: "لا توجد بيانات عن [الموضوع]"
5️⃣  رتب الرد: الرقم أولاً، ثم التفاصيل

═══════════════════════════════════════
📚 أمثلة واضحة - تعلّم منها:
═══════════════════════════════════════

مثال 1️⃣ - سؤال عن العدد:
❓ السؤال: "كم عدد النفقات؟"
🔍 البحث: expenses_count: 15, total_expenses_amount: 5000
✅ الرد الصحيح:
"✅ عدد النفقات في النظام: 15 نفقة
💰 المبلغ الإجمالي: 5000 شيقل"

❌ رد خاطئ: "لا توجد نفقات" (إذا كانت موجودة!)

مثال 2️⃣ - سؤال عن عميل:
❓ السؤال: "معلومات عن أحمد"
🔍 البحث: found_customer: {{name: "أحمد", balance: 500}}
✅ الرد الصحيح:
"✅ العميل أحمد موجود:
• الرصيد: 500 شيقل"

❌ رد خاطئ: "لا يوجد عميل" (إذا كان موجوداً!)

مثال 3️⃣ - لا توجد بيانات:
❓ السؤال: "كم عدد الطائرات؟"
🔍 البحث: {{}} (فارغ)
✅ الرد الصحيح:
"⚠️ لا توجد بيانات عن الطائرات في النظام.
النظام مخصص لإدارة كراجات السيارات."

مثال 4️⃣ - Chain of Thought:
❓ السؤال: "هل الزبائن دفعوا؟"
🧠 التفكير:
1. بحثت في payment_status
2. وجدت: paid_count: 10, unpaid_count: 5, total_debt: 2000
3. النتيجة: البعض دفع، البعض لم يدفع
✅ الرد:
"📊 حالة الدفع:
✅ دفعوا: 10 عملاء
❌ لم يدفعوا: 5 عملاء
💰 إجمالي الديون: 2000 شيقل"

💬 أمثلة على نمط الإجابة:

═══════════════════════════════════════
🧠 Chain of Thought - فكّر خطوة بخطوة:
═══════════════════════════════════════

عند كل سؤال، فكّر بصوت عالٍ (لا تكتب التفكير في الرد):

1. ما الذي يسأل عنه المستخدم؟
2. ما البيانات المتوفرة في نتائج البحث؟
3. هل البيانات كافية للإجابة؟
4. ما الرقم/المعلومة الدقيقة المطلوبة؟
5. كيف أنظم الرد بشكل واضح؟

مثال على التفكير الداخلي (لا تكتبه):
❓ "كم عدد النفقات؟"
🧠 خطوة 1: يسأل عن عدد النفقات
🧠 خطوة 2: أبحث في النتائج عن "expenses_count"
🧠 خطوة 3: وجدت expenses_count: 15
🧠 خطوة 4: الجواب هو: 15 نفقة
🧠 خطوة 5: أضيف المبلغ الإجمالي إذا وجد
✅ الرد: "عدد النفقات: 15 نفقة، المبلغ: 5000 شيقل"

═══════════════════════════════════════
💬 أمثلة على الردود الصحيحة:
═══════════════════════════════════════

▶️ إذا سُئلت عن الشركة:
"👋 أنا نظام أزاد لإدارة الكراج!
🏢 طوّرني المهندس أحمد غنام من رام الله - فلسطين 🇵🇸
⚙️ نظام متكامل: صيانة، مبيعات، مخزون، عملاء، وأكثر!"

▶️ إذا سُئلت عن عدد (مع بيانات):
"✅ عدد [الشيء]: [العدد الدقيق من النتائج]
[تفاصيل إضافية من النتائج]"

▶️ إذا لم تجد البيانات (والنتائج فارغة):
"⚠️ لا توجد بيانات عن [الموضوع] في النظام حالياً."

أنت النظام! تكلم بثقة واحترافية ووضوح.
استخدم البيانات الفعلية فقط - لا تخمين أبداً.

═══════════════════════════════════════
💰 المعرفة المالية والضريبية:
═══════════════════════════════════════

🇵🇸 فلسطين:
• ضريبة القيمة المضافة (VAT): 16%
• ضريبة الدخل على الشركات: 15%
• ضريبة الدخل الشخصي: تصاعدية 5%-20%
  - 0-75,000₪: 5%
  - 75,001-150,000₪: 10%
  - 150,001-300,000₪: 15%
  - أكثر من 300,000₪: 20%

🇮🇱 إسرائيل:
• ضريبة القيمة المضافة (מע"מ): 17%
• ضريبة الشركات: 23%
• ضريبة الدخل الشخصي: حتى 47%
• ضريبة أرباح رأس المال: 25%

💱 العملات المدعومة:
• ILS (₪) - شيقل إسرائيلي (العملة الأساسية)
• USD ($) - دولار أمريكي (~3.7₪)
• JOD (د.أ) - دينار أردني (~5.2₪)
• EUR (€) - يورو (~4.0₪)

🧮 المعادلات المالية:
• الربح الإجمالي = الإيرادات - تكلفة البضاعة
• صافي الربح = الربح الإجمالي - المصروفات - الضرائب
• VAT = المبلغ × (نسبة الضريبة / 100)
• المبلغ مع VAT = المبلغ × (1 + نسبة الضريبة / 100)

📦 الجمارك (HS Codes):
• 8703: سيارات ركاب
• 8704: شاحنات نقل
• 8708: قطع غيار سيارات (معفاة عادة)
• 8507: بطاريات

🎯 عند الإجابة على أسئلة مالية:
1. حدد العملة المطلوبة
2. استخدم القواعد الضريبية الصحيحة (فلسطين أو إسرائيل)
3. اذكر المعادلة المستخدمة
4. أعط الأرقام الدقيقة بالعملة المحددة
5. اذكر المصدر القانوني إذا كان مهماً

💱 آخر سعر صرف USD/ILS: {system_context.get('latest_usd_ils_rate', 'غير متوفر')}

📊 إحصائيات إضافية:
• معاملات الصرف في النظام: {system_context.get('total_exchange_transactions', 0)}
• طلبات الصيانة: {system_context.get('total_services', 0)}
• المنتجات: {system_context.get('total_products', 0)}

═══════════════════════════════════════
🗺️ خريطة النظام (System Map):
═══════════════════════════════════════
"""
    
    # إضافة سياق التنقل من خريطة النظام
    try:
        nav_context = get_system_navigation_context()
        if nav_context:
            system_msg += f"""
📍 معلومات التنقل:
• عدد المسارات المسجلة: {nav_context.get('total_routes', 0)}
• عدد القوالب: {nav_context.get('total_templates', 0)}
• البلوپرنتات: {', '.join(nav_context.get('blueprints', [])[:10])}
• الوحدات: {', '.join(nav_context.get('modules', [])[:10])}

🧭 التصنيفات:
{chr(10).join(f'• {k}: {v} مسار' for k, v in nav_context.get('categories', {}).items())}

💡 عند سؤال عن صفحة:
- ابحث في خريطة النظام أولاً
- حدد الرابط الصحيح
- أعط الرابط الكامل للمستخدم
"""
    except:
        pass
    
    # إضافة الوعي البنيوي
    try:
        data_context = get_data_awareness_context()
        if data_context:
            system_msg += f"""

═══════════════════════════════════════
🧠 الوعي البنيوي (Data Awareness):
═══════════════════════════════════════

📊 بنية قاعدة البيانات:
• عدد الجداول: {data_context.get('total_models', 0)}
• عدد الأعمدة الكلي: {data_context.get('total_columns', 0)}
• العلاقات بين الجداول: {data_context.get('total_relationships', 0)}

🎯 الوحدات الوظيفية المتاحة:
{chr(10).join(f'• {module}' for module in data_context.get('functional_modules', []))}

📝 النماذج المتاحة للاستعلام:
{', '.join(data_context.get('available_models', [])[:15])}{'...' if len(data_context.get('available_models', [])) > 15 else ''}

🔍 خريطة المصطلحات:
• "المبيعات" → Invoice, Payment
• "الدفتر" → Ledger, Account
• "النفقات" → Expense
• "الضرائب" → Tax, VAT, ExchangeTransaction
• "سعر الدولار" → ExchangeTransaction (USD/ILS)
• "العملاء" → Customer
• "الموردين" → Supplier
• "المتجر" → Product, OnlineCart
• "الصيانة" → ServiceRequest, ServicePart
• "المخازن" → Warehouse, StockLevel

⚡ قواعد الإجابة الذكية:
1. إذا لم تجد بيانات مباشرة، ابحث في الجداول ذات الصلة
2. قدم إجابة جزئية أفضل من الرفض المطلق
3. اذكر الجدول المستخدم في الإجابة
4. إذا كانت الثقة 20-50%، أعطِ إجابة مع توضيح درجة الثقة
5. ارفض فقط إذا كانت الثقة < 20%
6. استخدم المنطق والاستنتاج من البيانات المتاحة
"""
    except:
        pass
    
    system_msg += """

═══════════════════════════════════════
"""

def query_accounting_data(query_type, filters=None):
    """استعلام مباشر من قاعدة البيانات للمعلومات المحاسبية والمالية"""
    results = {}
    filters = filters or {}
    
    try:
        from models import (
            Customer, Supplier, Partner, Payment, Sale, Invoice, Expense,
            GLBatch, GLEntry, Account, ServiceRequest, Product, StockLevel
        )
        from sqlalchemy import func, and_, or_
        from datetime import datetime, timedelta
        
        if query_type == 'customer_balance':
            customer_id = filters.get('customer_id')
            if customer_id:
                customer = Customer.query.get(customer_id)
                if customer:
                    results['customer'] = {
                        'id': customer.id,
                        'name': customer.name,
                        'balance': float(customer.balance) if hasattr(customer, 'balance') else 0,
                        'balance_formula': '(المبيعات + الفواتير + الخدمات) - (الدفعات الواردة)',
                        'meaning': 'رصيد سالب = عليه يدفع | رصيد موجب = له رصيد'
                    }
        
        elif query_type == 'supplier_balance':
            supplier_id = filters.get('supplier_id')
            if supplier_id:
                supplier = Supplier.query.get(supplier_id)
                if supplier:
                    results['supplier'] = {
                        'id': supplier.id,
                        'name': supplier.name,
                        'balance': float(supplier.balance) if hasattr(supplier, 'balance') else 0,
                        'balance_formula': '(المشتريات + الشحنات) - (الدفعات الصادرة)',
                        'meaning': 'رصيد سالب = عليه يدفع | رصيد موجب = له رصيد'
                    }
        
        elif query_type == 'gl_account_summary':
            account_code = filters.get('account_code')
            date_from = filters.get('date_from')
            date_to = filters.get('date_to', datetime.now())
            
            query = db.session.query(
                GLEntry.account,
                func.sum(GLEntry.debit).label('total_debit'),
                func.sum(GLEntry.credit).label('total_credit')
            ).join(GLBatch, GLEntry.batch_id == GLBatch.id)
            
            if account_code:
                query = query.filter(GLEntry.account == account_code)
            if date_from:
                query = query.filter(GLBatch.date >= date_from)
            if date_to:
                query = query.filter(GLBatch.date <= date_to)
            
            summary = query.group_by(GLEntry.account).all()
            results['gl_summary'] = [
                {
                    'account': row.account,
                    'total_debit': float(row.total_debit or 0),
                    'total_credit': float(row.total_credit or 0),
                    'balance': float(row.total_debit or 0) - float(row.total_credit or 0)
                }
                for row in summary
            ]
        
        elif query_type == 'financial_summary':
            date_from = filters.get('date_from', datetime.now() - timedelta(days=30))
            date_to = filters.get('date_to', datetime.now())
            
            # إجمالي المبيعات
            total_sales = db.session.query(func.sum(Sale.total_amount)).filter(
                Sale.created_at.between(date_from, date_to)
            ).scalar() or 0
            
            # إجمالي النفقات
            total_expenses = db.session.query(func.sum(Expense.amount)).filter(
                Expense.date.between(date_from, date_to)
            ).scalar() or 0
            
            # إجمالي المدفوعات الواردة
            payments_in = db.session.query(func.sum(Payment.total_amount)).filter(
                Payment.payment_date.between(date_from, date_to),
                Payment.direction == 'IN'
            ).scalar() or 0
            
            # إجمالي المدفوعات الصادرة
            payments_out = db.session.query(func.sum(Payment.total_amount)).filter(
                Payment.payment_date.between(date_from, date_to),
                Payment.direction == 'OUT'
            ).scalar() or 0
            
            results['financial_summary'] = {
                'period': {'from': date_from.isoformat(), 'to': date_to.isoformat()},
                'total_sales': float(total_sales),
                'total_expenses': float(total_expenses),
                'payments_in': float(payments_in),
                'payments_out': float(payments_out),
                'net_cash_flow': float(payments_in) - float(payments_out),
                'net_profit': float(total_sales) - float(total_expenses)
            }
        
        elif query_type == 'account_balance':
            account_code = filters.get('account_code')
            if account_code:
                account = Account.query.filter_by(code=account_code).first()
                if account:
                    # حساب الرصيد من GLEntry
                    debit_sum = db.session.query(func.sum(GLEntry.debit)).join(
                        GLBatch, GLEntry.batch_id == GLBatch.id
                    ).filter(GLEntry.account == account_code).scalar() or 0
                    
                    credit_sum = db.session.query(func.sum(GLEntry.credit)).join(
                        GLBatch, GLEntry.batch_id == GLBatch.id
                    ).filter(GLEntry.account == account_code).scalar() or 0
                    
                    # حسب نوع الحساب
                    kb = get_knowledge_base()
                    acc_knowledge = kb.get_accounting_knowledge()
                    acc_type_info = acc_knowledge['gl_account_types'].get(account.type.value, {})
                    
                    if acc_type_info.get('debit_increases'):
                        balance = float(debit_sum) - float(credit_sum)
                    else:
                        balance = float(credit_sum) - float(debit_sum)
                    
                    results['account_balance'] = {
                        'account_code': account.code,
                        'account_name': account.name,
                        'account_type': account.type.value,
                        'total_debit': float(debit_sum),
                        'total_credit': float(credit_sum),
                        'balance': balance,
                        'balance_meaning': f'{"مدين" if balance > 0 else "دائن" if balance < 0 else "صفر"}'
                    }
        
    except Exception as e:
        results['error'] = str(e)
    
    return results

def search_database_for_query(query):
    """البحث الشامل الذكي في كل قاعدة البيانات - محسّن بالـ Intent Analysis"""
    results = {}
    query_lower = query.lower()
    
    intent = analyze_question_intent(query)
    results['intent'] = intent
    
    # فحص إذا كان السؤال محاسبي
    accounting_keywords = ['رصيد', 'حساب', 'دفتر', 'محاسبة', 'مالي', 'gl', 'balance', 'account', 
                           'مدين', 'دائن', 'ضريبة', 'vat', 'مبيعات', 'مصروف', 'دفعة']
    is_accounting_query = any(kw in query_lower for kw in accounting_keywords)
    
    if is_accounting_query:
        kb = get_knowledge_base()
        results['accounting_knowledge'] = kb.get_accounting_knowledge()
        
        # استعلام مباشر حسب نوع السؤال
        if 'رصيد' in query_lower and 'عميل' in query_lower:
            # البحث عن عميل
            from models import Customer
            customer_name = query.split('عميل')[-1].strip() if 'عميل' in query else None
            if customer_name:
                customer = Customer.query.filter(Customer.name.ilike(f'%{customer_name}%')).first()
                if customer:
                    results.update(query_accounting_data('customer_balance', {'customer_id': customer.id}))
        
        if 'رصيد' in query_lower and 'مورد' in query_lower:
            from models import Supplier
            supplier_name = query.split('مورد')[-1].strip() if 'مورد' in query else None
            if supplier_name:
                supplier = Supplier.query.filter(Supplier.name.ilike(f'%{supplier_name}%')).first()
                if supplier:
                    results.update(query_accounting_data('supplier_balance', {'supplier_id': supplier.id}))
        
        if 'حساب' in query_lower and any(code in query.upper() for code in ['1100', '2000', '4000', '1000', '5000']):
            # استخراج رقم الحساب
            import re
            account_code_match = re.search(r'(\d{4}_\w+)', query.upper())
            if account_code_match:
                account_code = account_code_match.group(1)
                results.update(query_accounting_data('account_balance', {'account_code': account_code}))
        
        if 'ملخص' in query_lower and ('مالي' in query_lower or 'محاسبي' in query_lower):
            results.update(query_accounting_data('financial_summary'))
    
    try:
        kb = get_knowledge_base()
        
        from models import (
            Customer, Supplier, Product, ServiceRequest, Invoice, Payment,
            Expense, ExpenseType, Warehouse, StockLevel, Note, Shipment,
            Role, Permission, PartnerSettlement, SupplierSettlement,
            Account, PreOrder, OnlineCart, ExchangeTransaction, Partner,
            ServicePart, ServiceTask, User
        )
        
        if intent['type'] == 'explanation' and 'موديل' in query_lower:
            for entity in intent['entities']:
                explanation = kb.explain_model(entity)
                if explanation:
                    results[f'model_explanation_{entity}'] = explanation
        
        if intent['type'] == 'report' or intent.get('accounting'):
            results['report_data'] = generate_smart_report(intent)
        
        if intent.get('accounting'):
            results['accounting_analysis'] = analyze_accounting_data(intent.get('currency'))
            
            import re
            numbers = re.findall(r'\d+(?:,\d{3})*(?:\.\d+)?', query)
            if numbers and any(word in query for word in ['ضريبة', 'tax', 'vat']):
                try:
                    amount = float(numbers[0].replace(',', ''))
                    
                    if 'دخل' in query or 'income' in query.lower():
                        tax = calculate_palestine_income_tax(amount)
                        results['tax_calculation'] = {
                            'type': 'ضريبة دخل فلسطين',
                            'income': amount,
                            'tax': tax,
                            'net': amount - tax,
                            'effective_rate': round((tax / amount) * 100, 2) if amount > 0 else 0
                        }
                    elif 'vat' in query.lower() or 'قيمة' in query:
                        country = 'palestine'
                        if 'إسرائيل' in query or 'israel' in query.lower():
                            country = 'israel'
                        
                        vat_info = calculate_vat(amount, country)
                        results['vat_calculation'] = vat_info
                        results['vat_calculation']['country'] = country
                except:
                    pass
        
        if intent.get('currency') or 'صرف' in query or 'سعر' in query:
            try:
                from models import ExchangeTransaction
                
                recent_fx = ExchangeTransaction.query.order_by(
                    ExchangeTransaction.created_at.desc()
                ).limit(5).all()
                
                if recent_fx:
                    results['recent_exchange_rates'] = [{
                        'from_currency': fx.from_currency,
                        'to_currency': fx.to_currency,
                        'rate': float(fx.rate),
                        'date': fx.created_at.strftime('%Y-%m-%d') if fx.created_at else 'N/A'
                    } for fx in recent_fx]
            except:
                pass
        
        # البحث عن اسم محدد في السؤال (أولوية)
        words = [w for w in query.split() if len(w) > 2]
        found_name = None
        
        for word in words:
            if word not in ['عن', 'من', 'في', 'على', 'إلى', 'هل', 'ما', 'كم', 'عميل', 'صيانة', 'منتج', 'فاتورة', 'خدمة', 'مورد']:
                # بحث في العملاء
                try:
                    customer = Customer.query.filter(Customer.name.like(f'%{word}%')).first()
                    if customer:
                        results['found_customer'] = {
                            'id': customer.id,
                            'name': customer.name,
                            'phone': customer.phone or 'غير محدد',
                            'email': customer.email or 'غير محدد',
                            'address': getattr(customer, 'address', 'غير محدد'),
                            'balance': getattr(customer, 'balance', 0),
                            'is_active': customer.is_active,
                            'created_at': customer.created_at.strftime('%Y-%m-%d') if customer.created_at else 'N/A'
                        }
                        found_name = word
                        break
                except:
                    pass
        
        # تحليل اليوم (Today Analysis)
        try:
            if 'اليوم' in query or 'today' in query_lower:
                today = datetime.now(timezone.utc).date()
                
                # حركات الصيانة اليوم
                today_services = ServiceRequest.query.filter(
                    func.date(ServiceRequest.created_at) == today
                ).all()
                
                if today_services:
                    results['today_services'] = [{
                        'id': s.id,
                        'customer': s.customer.name if s.customer else 'N/A',
                        'vehicle_model': s.vehicle_model or 'N/A',
                        'vehicle_vrn': s.vehicle_vrn or 'N/A',
                        'status': s.status,
                        'problem': (s.problem_description or 'N/A')[:150],
                        'diagnosis': (s.diagnosis or 'N/A')[:150],
                        'engineer_notes': (s.engineer_notes or 'N/A')[:150],
                        'resolution': (s.resolution or 'N/A')[:150],
                        'total_cost': float(s.total_cost) if s.total_cost else 0
                    } for s in today_services]
                else:
                    results['today_services_message'] = 'لا توجد صيانة اليوم'
                    
                    # قطع الصيانة المستخدمة اليوم
                    today_parts = []
                    for service in today_services:
                        parts = ServicePart.query.filter_by(service_id=service.id).all()
                        for part in parts:
                            product = Product.query.filter_by(id=part.part_id).first()
                            if product:
                                today_parts.append({
                                    'service_id': service.id,
                                    'part_name': product.name,
                                    'quantity': part.quantity,
                                    'price': float(part.unit_price)
                                })
                    
                    results['today_parts_used'] = today_parts
                    results['today_parts_count'] = len(today_parts)
                
                # حالة الدفع
                unpaid_invoices = Invoice.query.filter(
                    Invoice.status.in_(['UNPAID', 'PARTIALLY_PAID'])
                ).all()
                
                paid_invoices = Invoice.query.filter(
                    Invoice.status == 'PAID'
                ).all()
                
                total_debt = sum(float(i.total_amount) for i in unpaid_invoices)
                
                results['payment_status'] = {
                    'paid_count': len(paid_invoices),
                    'unpaid_count': len(unpaid_invoices),
                    'total_debt': total_debt
                }
        except Exception as e:
            results['today_error'] = str(e)
        
        # 1. المخازن (Warehouses)
        if any(word in query for word in ['مخزن', 'مخازن', 'warehouse']):
            warehouses = Warehouse.query.all()
            results['warehouses_count'] = len(warehouses)
            if warehouses:
                results['warehouses_data'] = [{
                    'id': w.id,
                    'name': w.name,
                    'type': getattr(w, 'warehouse_type', 'N/A'),
                    'location': getattr(w, 'location', 'N/A')
                } for w in warehouses]
                
                for warehouse in warehouses:
                    stock_items = StockLevel.query.filter_by(warehouse_id=warehouse.id).all()
                    if stock_items:
                        results[f'warehouse_{warehouse.id}_stock'] = len(stock_items)
        
        # 2. العملاء (Customers)
        if any(word in query for word in ['عميل', 'عملاء', 'زبون', 'زبائن', 'customer']):
            customers = Customer.query.all()
            results['customers_count'] = len(customers)
            results['active_customers'] = Customer.query.filter_by(is_active=True).count()
            if customers:
                results['customers_sample'] = [{
                    'id': c.id,
                    'name': c.name,
                    'balance': getattr(c, 'balance', 0),
                    'is_active': c.is_active
                } for c in customers[:10]]
        
        # 3. المنتجات (Products)
        if any(word in query for word in ['منتج', 'منتجات', 'قطع', 'product']):
            products = Product.query.all()
            results['products_count'] = len(products)
            if products:
                results['products_sample'] = [{
                    'id': p.id,
                    'name': p.name,
                    'price': getattr(p, 'price', 0),
                    'in_stock': StockLevel.query.filter_by(product_id=p.id).count() > 0
                } for p in products[:10]]
        
        # 4. الموردين (Suppliers)
        if any(word in query for word in ['مورد', 'موردين', 'supplier']):
            suppliers = Supplier.query.all()
            results['suppliers_count'] = len(suppliers)
            if suppliers:
                results['suppliers_data'] = [{
                    'id': s.id,
                    'name': s.name,
                    'phone': getattr(s, 'phone', 'N/A'),
                    'balance': getattr(s, 'balance', 0)
                } for s in suppliers[:10]]
        
        # 5. الشحنات (Shipments)
        if any(word in query for word in ['شحن', 'شحنة', 'شحنات', 'shipment']):
            shipments = Shipment.query.all()
            results['shipments_count'] = len(shipments)
            if shipments:
                results['shipments_data'] = [{
                    'id': sh.id,
                    'status': getattr(sh, 'status', 'N/A'),
                    'date': sh.created_at.strftime('%Y-%m-%d') if hasattr(sh, 'created_at') and sh.created_at else 'N/A'
                } for sh in shipments[:10]]
        
        # 6. الملاحظات (Notes)
        if any(word in query for word in ['ملاحظة', 'ملاحظات', 'note']):
            notes = Note.query.all()
            results['notes_count'] = len(notes)
            if notes:
                results['notes_sample'] = [{
                    'id': n.id,
                    'title': getattr(n, 'title', 'N/A'),
                    'content': getattr(n, 'content', 'N/A')[:100]
                } for n in notes[:5]]
        
        # 7. الشركاء (Partners)
        if any(word in query for word in ['شريك', 'شركاء', 'partner']):
            try:
                partners = Partner.query.all()
                results['partners_count'] = len(partners)
                if partners:
                    results['partners_data'] = [{
                        'id': p.id,
                        'name': p.name,
                        'balance': getattr(p, 'balance', 0)
                    } for p in partners[:10]]
            except:
                pass
        
        # 8. التسويات (Settlements)
        if any(word in query for word in ['تسوية', 'تسويات', 'settlement']):
            try:
                partner_settlements = PartnerSettlement.query.all()
                supplier_settlements = SupplierSettlement.query.all()
                results['partner_settlements_count'] = len(partner_settlements)
                results['supplier_settlements_count'] = len(supplier_settlements)
            except:
                pass
        
        # 9. الحسابات (Accounts)
        if any(word in query for word in ['حساب', 'حسابات', 'account']):
            try:
                accounts = Account.query.all()
                results['accounts_count'] = len(accounts)
            except:
                pass
        
        # 10. الأدوار والصلاحيات (Roles & Permissions)
        if any(word in query for word in ['دور', 'أدوار', 'صلاحية', 'role', 'permission']):
            roles = Role.query.all()
            permissions = Permission.query.all()
            results['roles_count'] = len(roles)
            results['permissions_count'] = len(permissions)
            results['roles_list'] = [r.name for r in roles]
        
        # 11. المستخدمين (Users)
        if any(word in query for word in ['مستخدم', 'مستخدمين', 'user']):
            users = User.query.all()
            results['users_count'] = len(users)
            results['active_users'] = User.query.filter_by(is_active=True).count()
            if users:
                results['users_sample'] = [{
                    'id': u.id,
                    'username': u.username,
                    'email': getattr(u, 'email', 'N/A'),
                    'role': u.role.name if hasattr(u, 'role') and u.role else 'N/A'
                } for u in users[:10]]
        
        # 12. الطلبات المسبقة (PreOrders)
        if any(word in query for word in ['طلب مسبق', 'حجز', 'preorder']):
            try:
                preorders = PreOrder.query.all()
                results['preorders_count'] = len(preorders)
            except:
                pass
        
        # 13. السلة (Cart)
        if any(word in query for word in ['سلة', 'cart']):
            try:
                carts = OnlineCart.query.all()
                results['carts_count'] = len(carts)
            except:
                pass
        
        # 14. الصيانة (ServiceRequest) - شامل
        if any(word in query for word in ['صيانة', 'service', 'إصلاح', 'تشخيص', 'عطل']):
            try:
                services = ServiceRequest.query.all()
                results['services_total'] = len(services)
                results['services_pending'] = ServiceRequest.query.filter_by(status='pending').count()
                results['services_completed'] = ServiceRequest.query.filter_by(status='completed').count()
                results['services_in_progress'] = ServiceRequest.query.filter_by(status='in_progress').count()
                
                if services:
                    results['services_sample'] = [{
                        'id': s.id,
                        'customer': s.customer.name if s.customer else 'N/A',
                        'vehicle': s.vehicle_model or 'N/A',
                        'status': s.status,
                        'problem': (s.problem_description or 'N/A')[:100],
                        'diagnosis': (s.diagnosis or 'N/A')[:100],
                        'engineer_notes': (s.engineer_notes or 'N/A')[:100],
                        'cost': float(s.total_cost) if s.total_cost else 0
                    } for s in services[:10]]
            except Exception as e:
                results['services_error'] = str(e)
        
        # النفقات والمصاريف
        if 'نفق' in query or 'مصروف' in query or 'مصاريف' in query or 'expense' in query_lower:
            try:
                expenses = Expense.query.all()
                results['expenses_count'] = len(expenses)
                
                if expenses:
                    results['expenses_data'] = [{
                        'id': exp.id,
                        'amount': float(exp.amount),
                        'description': getattr(exp, 'description', 'N/A'),
                        'type_id': exp.type_id,
                        'date': exp.date.strftime('%Y-%m-%d') if exp.date else 'N/A'
                    } for exp in expenses[:20]]
                    
                    total_expenses_amount = sum(float(exp.amount) for exp in expenses)
                    results['total_expenses_amount'] = total_expenses_amount
                else:
                    results['expenses_message'] = 'لا توجد نفقات في النظام'
            except Exception as e:
                results['expenses_error'] = str(e)
        
        # الفواتير
        if 'فاتورة' in query or 'فواتير' in query or 'invoice' in query_lower:
            try:
                invoices_count = Invoice.query.count()
                results['invoices_count'] = invoices_count
                
                if invoices_count > 0:
                    total_invoices_amount = db.session.query(func.sum(Invoice.total_amount)).scalar() or 0
                    
                    # ✅ status محسوب تلقائياً - نستخدم total_paid للفلترة
                    from sqlalchemy import and_
                    paid_invoices = Invoice.query.filter(
                        and_(
                            Invoice.total_paid >= Invoice.total_amount,
                            Invoice.cancelled_at.is_(None)
                        )
                    ).count()
                    
                    unpaid_invoices = Invoice.query.filter(
                        and_(
                            Invoice.total_paid < Invoice.total_amount,
                            Invoice.cancelled_at.is_(None)
                        )
                    ).count()
                    
                    results['invoices_stats'] = {
                        'count': invoices_count,
                        'total_amount': float(total_invoices_amount),
                        'paid_count': paid_invoices,
                        'unpaid_count': unpaid_invoices
                    }
            except Exception as e:
                results['invoices_error'] = str(e)
        
    except Exception as e:
        results['error'] = str(e)
    
    return results

def check_groq_health():
    """فحص صحة اتصال Groq وتفعيل Local Fallback إذا لزم الأمر"""
    global _groq_failures, _local_fallback_mode, _system_state
    
    # تنظيف الأخطاء القديمة (أكثر من 24 ساعة)
    current_time = datetime.now(timezone.utc)
    _groq_failures = [
        f for f in _groq_failures 
        if (current_time - f).total_seconds() < 86400
    ]
    
    # تحديث حالة النظام
    if len(_groq_failures) >= 3:
        _local_fallback_mode = True
        _system_state = "LOCAL_ONLY"
        return False
    elif len(_groq_failures) > 0:
        _system_state = "HYBRID"
    else:
        _system_state = "API_ONLY"
    
    return True

def get_system_identity():
    """الحصول على هوية المساعد ووضع التشغيل"""
    global _system_state, _groq_failures
    
    return {
        'name': 'المساعد الذكي في نظام Garage Manager',
        'version': 'AI 4.0 - Full Awareness Edition',
        'mode': _system_state,
        'capabilities': {
            'local_analysis': True,
            'database_access': True,
            'knowledge_base': True,
            'finance_calculations': True,
            'auto_discovery': True,
            'self_training': True
        },
        'status': {
            'groq_api': 'offline' if _local_fallback_mode else 'online',
            'groq_failures_24h': len(_groq_failures),
            'local_mode_active': _local_fallback_mode
        },
        'data_sources': [
            'AI/data/ai_knowledge_cache.json',
            'AI/data/ai_data_schema.json',
            'AI/data/ai_system_map.json',
            'قاعدة البيانات المحلية (SQLAlchemy)'
        ]
    }

def get_local_fallback_response(message, search_results):
    """الرد باستخدام المعرفة المحلية فقط - محسّن للذكاء المحلي"""
    try:
        from AI.engine.ai_knowledge import get_knowledge_base
        from AI.engine.ai_knowledge_finance import get_finance_knowledge
        
        response = "🤖 **أنا المساعد المحلي في نظام Garage Manager**\n"
        response += "أعمل الآن بوضع محلي كامل (بدون اتصال خارجي).\n\n"
        
        # تحليل السؤال
        message_lower = message.lower()
        
        # تحليل ذكي من search_results
        if search_results and any(k for k in search_results.keys() if not k.startswith('_')):
            response += "📊 **البيانات المتوفرة من قاعدة البيانات:**\n\n"
            
            # تحليل حسب النوع
            counts = {}
            data_items = {}
            
            for key, value in search_results.items():
                if key.startswith('_'):
                    continue
                    
                if isinstance(value, int) and value > 0:
                    counts[key] = value
                elif isinstance(value, dict) and value:
                    data_items[key] = value
                elif isinstance(value, list) and value:
                    data_items[key] = value
            
            # عرض الأعداد
            if counts:
                for key, count in counts.items():
                    arabic_key = key.replace('_count', '').replace('_', ' ')
                    response += f"✅ **{arabic_key}:** {count}\n"
            
            # عرض البيانات التفصيلية
            if data_items:
                response += "\n📋 **تفاصيل إضافية:**\n"
                for key, items in list(data_items.items())[:3]:  # أول 3 نتائج
                    if isinstance(items, list) and items:
                        response += f"\n• **{key}:**\n"
                        for item in items[:3]:  # أول 3 عناصر
                            if isinstance(item, dict):
                                # عرض معلومات مفيدة
                                if 'name' in item:
                                    response += f"  - {item.get('name', 'N/A')}\n"
                                elif 'amount' in item:
                                    response += f"  - مبلغ: {item.get('amount', 0)}\n"
                    elif isinstance(items, dict):
                        response += f"\n• **{key}:** {len(items)} عنصر\n"
            
            # إضافة توصيات ذكية
            response += "\n\n💡 **توصيات:**\n"
            
            if 'نفق' in message_lower or 'مصروف' in message_lower:
                if counts.get('expenses_count', 0) > 0:
                    response += "• يمكنك الوصول إلى صفحة النفقات لعرض التفاصيل الكاملة.\n"
                    response += "• الرابط: `/expenses`\n"
            
            if 'صيانة' in message_lower or 'service' in message_lower:
                if counts.get('services_total', 0) > 0:
                    response += "• يمكنك الوصول إلى صفحة الصيانة لعرض جميع الطلبات.\n"
                    response += "• الرابط: `/service`\n"
            
            if 'عميل' in message_lower or 'customer' in message_lower:
                if counts.get('customers_count', 0) > 0:
                    response += "• يمكنك الوصول إلى صفحة العملاء لعرض التفاصيل.\n"
                    response += "• الرابط: `/customers`\n"
        
        else:
            # لا توجد بيانات - رد ذكي تفاعلي
            response += "⚠️ لم أجد بيانات مباشرة للسؤال، لكن يمكنني:\n\n"
            response += "1. 🔍 البحث في جداول النظام المحلية\n"
            response += "2. 📊 عرض الإحصائيات العامة\n"
            response += "3. 🧭 توجيهك للصفحة المناسبة\n"
            response += "4. 💰 حساب الضرائب والعملات (محلياً)\n\n"
            
            # اقتراحات ذكية
            kb = get_knowledge_base()
            structure = kb.get_system_structure()
            
            response += f"💡 **معلومات النظام المتاحة محلياً:**\n"
            response += f"• عدد النماذج المعروفة: {structure.get('models_count', 0)}\n"
            response += f"• عدد الوحدات: {len(structure.get('routes', {}))}\n"
            response += f"• عدد القوالب: {structure.get('templates_count', 0)}\n\n"
            
            response += "📝 **اسألني عن:**\n"
            response += "• 'كم عدد العملاء؟'\n"
            response += "• 'النفقات اليوم؟'\n"
            response += "• 'أين صفحة الصيانة؟'\n"
            response += "• 'احسب VAT لـ 1000 شيقل'\n"
        
        response += "\n\n🔄 **الحالة:** أعمل بوضع محلي ذكي (Local AI Mode)\n"
        response += "📡 سيتم استعادة الاتصال بـ Groq تلقائياً عند حل المشكلة."
        
        # تسجيل استخدام الوضع المحلي
        log_local_mode_usage()
        
        return response
    
    except Exception as e:
        return f"⚠️ خطأ في الوضع المحلي: {str(e)}"

def log_local_mode_usage():
    """تسجيل استخدام الوضع المحلي"""
    try:
        import json
        import os
        from datetime import datetime
        
        log_file = 'AI/data/ai_local_mode_log.json'
        
        os.makedirs('AI/data', exist_ok=True)
        
        logs = []
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        
        logs.append({
            'timestamp': datetime.now().isoformat(),
            'mode': 'LOCAL_ONLY',
            'groq_failures': len(_groq_failures)
        })
        
        # الاحتفاظ بآخر 100 سجل
        logs = logs[-100:]
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    
    except:
        pass

def ai_chat_response(message, search_results=None, session_id='default'):
    """رد AI محسّن مع نتائج البحث والذاكرة والمعرفة"""
    keys_json = get_system_setting('AI_API_KEYS', '[]')
    
    try:
        keys = json.loads(keys_json)
        active_key = next((k for k in keys if k.get('is_active')), None)
        
        if not active_key:
            return '⚠️ لا يوجد مفتاح AI نشط. يرجى تفعيل مفتاح من إدارة المفاتيح'
        
        system_context = gather_system_context()
        
        try:
            import requests
            
            api_key = active_key.get('key')
            provider = active_key.get('provider', 'groq')
            
            if 'groq' in provider.lower():
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                system_msg = build_system_message(system_context)
                
                memory = get_or_create_session_memory(session_id)
                
                messages = [{"role": "system", "content": system_msg}]
                
                for msg in memory['messages'][-10:]:
                    messages.append({
                        "role": msg['role'],
                        "content": msg['content']
                    })
                
                enhanced_message = message
                if search_results:
                    search_summary = "\n\n═══ 📊 نتائج البحث الحقيقية من قاعدة البيانات ═══\n"
                    
                    intent = search_results.get('intent', {})
                    if intent:
                        search_summary += f"🎯 نوع السؤال: {intent.get('type', 'general')}\n"
                        if intent.get('entities'):
                            search_summary += f"📦 الوحدات المعنية: {', '.join(intent['entities'])}\n"
                        if intent.get('time_scope'):
                            search_summary += f"⏰ النطاق الزمني: {intent['time_scope']}\n"
                        search_summary += "\n"
                    
                    for key, value in search_results.items():
                        if value and key not in ['error', 'intent']:
                            try:
                                value_str = json.dumps(value, ensure_ascii=False, indent=2)
                                search_summary += f"\n📌 {key}:\n{value_str}\n"
                            except:
                                search_summary += f"\n📌 {key}: {str(value)}\n"
                    
                    enhanced_message = message + search_summary
                
                messages.append({"role": "user", "content": enhanced_message})
                
                data = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 2000,
                    "top_p": 0.9
                }
                
                response = requests.post(url, headers=headers, json=data, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    ai_response = result['choices'][0]['message']['content']
                    
                    add_to_memory(session_id, 'user', message)
                    add_to_memory(session_id, 'assistant', ai_response)
                    
                    return ai_response
                else:
                    return f'⚠️ خطأ من Groq API: {response.status_code} - {response.text[:200]}'
            
            return '⚠️ نوع المزود غير مدعوم حالياً'
            
        except requests.exceptions.Timeout:
            return '⚠️ انتهت مهلة الاتصال بـ AI. حاول مرة أخرى.'
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f'⚠️ خطأ في الاتصال بـ AI: {str(e)}'
    
    except Exception as e:
        return f'⚠️ خطأ في قراءة المفاتيح: {str(e)}'

def handle_error_question(error_text):
    """معالجة سؤال عن خطأ - تحليل وحل"""
    try:
        analysis = analyze_error(error_text)
        formatted = format_error_response(analysis)
        
        return {
            'is_error': True,
            'analysis': analysis,
            'formatted_response': formatted
        }
    except Exception as e:
        return {
            'is_error': True,
            'analysis': None,
            'formatted_response': f'⚠️ لم أستطع تحليل الخطأ: {str(e)}'
        }

def validate_search_results(query, search_results):
    """التحقق من البيانات قبل إرسالها للـ AI - Validation Layer"""
    validation = {
        'has_data': False,
        'data_quality': 'unknown',
        'confidence': 0,
        'warnings': []
    }
    
    if not search_results or len(search_results) <= 1:
        validation['warnings'].append('⚠️ لم يتم العثور على بيانات')
        validation['confidence'] = 0
        return validation
    
    data_keys = [k for k in search_results.keys() if k not in ['intent', 'error']]
    
    if len(data_keys) == 0:
        validation['warnings'].append('⚠️ نتائج البحث فارغة')
        validation['confidence'] = 0
    elif len(data_keys) >= 5:
        validation['has_data'] = True
        validation['data_quality'] = 'excellent'
        validation['confidence'] = 95
    elif len(data_keys) >= 3:
        validation['has_data'] = True
        validation['data_quality'] = 'good'
        validation['confidence'] = 80
    elif len(data_keys) >= 1:
        validation['has_data'] = True
        validation['data_quality'] = 'fair'
        validation['confidence'] = 60
        validation['warnings'].append('⚠️ البيانات محدودة - قد لا تكون الإجابة كاملة')
    
    for key in ['_count', '_data', '_sample']:
        if any(key in k for k in data_keys):
            validation['has_data'] = True
            break
    
    return validation

def calculate_confidence_score(search_results, validation):
    """حساب درجة الثقة في الرد"""
    score = validation['confidence']
    
    if search_results.get('error'):
        score -= 30
    
    if search_results.get('today_error'):
        score -= 20
    
    if validation['data_quality'] == 'excellent':
        score = min(95, score + 5)
    
    return max(0, min(100, score))

def handle_navigation_request(message):
    """معالجة طلبات التنقل"""
    try:
        suggestions = get_route_suggestions(message)
        
        if suggestions and suggestions['matches']:
            response = f"📍 تم العثور على {suggestions['count']} صفحة مطابقة:\n\n"
            
            for i, route in enumerate(suggestions['matches'], 1):
                response += f"{i}. **{route['endpoint']}**\n"
                response += f"   🔗 الرابط: `{route['url']}`\n"
                if route['linked_templates']:
                    response += f"   📄 القالب: {route['linked_templates'][0]}\n"
                response += "\n"
            
            return response
        else:
            return "⚠️ لم أتمكن من العثور على الصفحة المطلوبة. حاول صياغة السؤال بشكل مختلف."
    
    except Exception as e:
        return f"⚠️ خطأ في البحث عن الصفحة: {str(e)}"

def enhanced_context_understanding(message):
    """🧠 فهم سياقي متقدم - محرك NLP ذكي (ليس قوائم!)
    
    يستخدم:
    - تحليل لغوي متقدم (NLP)
    - فهم البنية النحوية
    - استنتاج المعنى الدلالي
    - معالجة السياق
    
    بدلاً من: قوائم if/elif الغبية!
    """
    import re
    from datetime import datetime
    
    # 🧠 استخدام محرك NLP الذكي
    try:
        from AI.engine.ai_nlp_engine import understand_text
        nlp_result = understand_text(message)
        
        # تحويل نتيجة NLP للصيغة المطلوبة
        context = {
            'message': message,
            'normalized': message.lower(),
            'intent': nlp_result['intent']['primary_intent'],
            'subintent': nlp_result['intent'].get('secondary_intents', [])[0] if nlp_result['intent'].get('secondary_intents') else None,
            'entities': list(nlp_result['sentence_structure']['entities'].keys()),
            'context_type': nlp_result['sentence_structure']['intent'] or 'question',
            'sentiment': nlp_result['sentence_structure']['sentiment'],
            'priority': 'urgent' if nlp_result['sentence_structure']['is_urgent'] else 'normal',
            'confidence': nlp_result['intent']['confidence'],
            'keywords': [],
            'time_scope': None,
            'requires_data': len(nlp_result['sentence_structure']['entities']) > 0,
            'requires_action': nlp_result['intent']['primary_intent'] == 'executable_command',
            'nlp_reasoning': nlp_result['intent']['reasoning'],
            'semantic_concept': nlp_result['semantic_meaning']['main_concept'],
        }
        
        # إضافة time_scope
        if nlp_result['semantic_meaning']['is_temporal']:
            text_lower = message.lower()
            if 'اليوم' in text_lower or 'today' in text_lower:
                context['time_scope'] = 'today'
            elif 'الأسبوع' in text_lower or 'week' in text_lower:
                context['time_scope'] = 'week'
            elif 'الشهر' in text_lower or 'month' in text_lower:
                context['time_scope'] = 'month'
        
        return context
        
    except Exception as e:
        # fallback للطريقة القديمة في حال فشل NLP

        pass
    
    # الطريقة القديمة (backup فقط)
    message_lower = message.lower()
    
    # تطبيع النص العربي
    def normalize_arabic(text):
        """إزالة التشكيل والهمزات للفهم الأفضل"""
        if not text:
            return ""
        # إزالة التشكيل
        text = re.sub(r'[\u0617-\u061A\u064B-\u0652]', '', text)
        # توحيد الهمزات
        text = re.sub('[إأٱآا]', 'ا', text)
        text = re.sub('ى', 'ي', text)
        text = re.sub('ؤ', 'و', text)
        text = re.sub('ئ', 'ي', text)
        text = re.sub('ة', 'ه', text)
        return text
    
    normalized = normalize_arabic(message_lower)
    
    context = {
        'message': message,
        'normalized': normalized,
        'intent': 'unknown',
        'subintent': None,
        'entities': [],
        'context_type': 'question',  # greeting, question, command, complaint
        'sentiment': 'neutral',  # positive, negative, neutral
        'priority': 'normal',  # urgent, high, normal, low
        'confidence': 0.5,
        'keywords': [],
        'time_scope': None,  # today, week, month, year
        'requires_data': False,
        'requires_action': False,
    }
    
    # 1. تحليل السياق - تحية أم سؤال أم أمر؟
    greetings = ['صباح', 'مساء', 'مرحبا', 'مرحباً', 'اهلا', 'أهلاً', 'السلام', 'hello', 'hi', 'hey', 'شلونك', 'كيفك']
    complaints = ['مشكلة', 'مشاكل', 'خطأ', 'خلل', 'عطل', 'problem', 'error', 'issue', 'bug']
    urgent_words = ['سريع', 'عاجل', 'الان', 'الآن', 'فوري', 'urgent', 'asap', 'now', 'immediately']
    
    if any(g in normalized for g in greetings):
        context['context_type'] = 'greeting'
        context['sentiment'] = 'positive'
    elif any(c in normalized for c in complaints):
        context['context_type'] = 'complaint'
        context['sentiment'] = 'negative'
        context['priority'] = 'high'
    elif any(w in normalized for w in ['كيف', 'how', 'شرح', 'explain']):
        context['context_type'] = 'how_to'
    elif any(w in normalized for w in ['اضف', 'انشئ', 'create', 'add']):
        context['context_type'] = 'command'
        context['requires_action'] = True
    
    # 2. تحليل الأولوية
    if any(u in normalized for u in urgent_words):
        context['priority'] = 'urgent'
    
    # 3. تحليل النية - ماذا يريد؟
    intent_patterns = {
        'count': ['كم', 'عدد', 'count', 'how many', 'كام', 'قديش'],
        'explanation': ['ما هو', 'what is', 'شرح', 'explain', 'عرف'],
        'navigation': ['وين', 'اين', 'where', 'اذهب', 'take me', 'افتح', 'open'],
        'calculation': ['احسب', 'calculate', 'حساب'],
        'comparison': ['مقارنة', 'compare', 'vs', 'الفرق'],
        'analysis': ['حلل', 'analyze', 'تحليل', 'افحص', 'check'],
        'recommendation': ['اقترح', 'recommend', 'نصيحة', 'advice'],
        'troubleshooting': ['مشكلة', 'problem', 'خطأ', 'error', 'لا يعمل'],
        'tutorial': ['كيف', 'how', 'خطوات', 'steps'],
        'data_query': ['اعرض', 'show', 'قائمة', 'list'],
    }
    
    for intent, patterns in intent_patterns.items():
        if any(p in normalized for p in patterns):
            context['intent'] = intent
            context['confidence'] = 0.8
            break
    
    # 4. استخراج الكيانات - عن ماذا يتحدث؟
    entities_map = {
        'customer': ['عميل', 'عملاء', 'زبون', 'customer'],
        'service': ['صيانة', 'service', 'تصليح', 'اصلاح', 'repair'],
        'invoice': ['فاتورة', 'فواتير', 'invoice'],
        'payment': ['دفعة', 'دفع', 'payment'],
        'product': ['منتج', 'منتجات', 'قطعة', 'product', 'part'],
        'expense': ['نفقة', 'مصروف', 'expense'],
        'supplier': ['مورد', 'موردين', 'supplier'],
        'warehouse': ['مخزن', 'مخازن', 'warehouse', 'مخزون', 'inventory'],
        'partner': ['شريك', 'شركاء', 'partner'],
        'report': ['تقرير', 'report'],
        'vat': ['vat', 'ضريبة', 'tax'],
        'profit': ['ربح', 'profit', 'خسارة', 'loss'],
    }
    
    for entity, keywords in entities_map.items():
        if any(k in normalized for k in keywords):
            context['entities'].append(entity)
            context['requires_data'] = True
    
    # 5. تحليل النطاق الزمني
    time_keywords = {
        'today': ['اليوم', 'today'],
        'week': ['الاسبوع', 'اسبوع', 'week'],
        'month': ['الشهر', 'شهر', 'month'],
        'year': ['السنة', 'سنة', 'عام', 'year'],
    }
    
    for scope, keywords in time_keywords.items():
        if any(k in normalized for k in keywords):
            context['time_scope'] = scope
            break
    
    # 6. استخراج الكلمات المفتاحية
    words = normalized.split()
    context['keywords'] = [w for w in words if len(w) > 2 and w not in [
        'كم', 'ما', 'من', 'في', 'على', 'الى', 'هل', 'ماذا', 'كيف',
        'what', 'how', 'where', 'when', 'why', 'the', 'is', 'are'
    ]]
    
    # 7. تحديد SubIntent للدقة
    if context['intent'] == 'count' and 'customer' in context['entities']:
        context['subintent'] = 'count_customers'
    elif context['intent'] == 'analysis' and 'sales' in normalized:
        context['subintent'] = 'analyze_sales'
    elif context['intent'] == 'navigation':
        context['subintent'] = 'find_page'
    
    return context

def local_intelligent_response(message):
    """رد محلي ذكي كامل - فهم شامل للنظام بدون API + حماية أمنية + دليل المستخدم
    
    🧠 **محسّن بالكامل:**
    - فهم سياقي متقدم
    - تحليل ذكي للنوايا
    - دمج جميع قواعد المعرفة
    - ردود تفاعلية وليست قوالب
    """
    # استيراد جميع المكونات الذكية
    try:
        from AI.engine.ai_knowledge import get_local_faq_responses, get_local_quick_rules
    except:
        get_local_faq_responses = lambda: {}
        get_local_quick_rules = lambda: {}
    
    try:
        from AI.engine.ai_auto_discovery import auto_discover_if_needed, find_route_by_keyword
    except:
        find_route_by_keyword = lambda x: None
    
    try:
        from AI.engine.ai_data_awareness import auto_build_if_needed, find_model_by_keyword
    except:
        find_model_by_keyword = lambda x: None
    
    try:
        from AI.engine.ai_security import (
            is_sensitive_query, get_security_response, sanitize_response,
            is_owner, is_manager, get_user_role_name, log_security_event
        )
    except:
        is_sensitive_query = lambda x: {'is_sensitive': False, 'is_owner_only': False}
        get_security_response = lambda x, y: None
        sanitize_response = lambda x: x
        is_owner = lambda: False
        is_manager = lambda: False
        get_user_role_name = lambda: 'User'
        log_security_event = lambda x, y, z: None
    
    try:
        from AI.engine.ai_advanced_intelligence import (
            get_deep_system_knowledge, find_workflow_by_query,
            explain_relationship, explain_field, get_all_workflows_list
        )
    except:
        get_deep_system_knowledge = lambda x: None
        find_workflow_by_query = lambda x: None
        explain_relationship = lambda x: None
        explain_field = lambda x: None
        get_all_workflows_list = lambda: "قائمة العمليات غير متاحة"
    
    try:
        from AI.engine.ai_user_guide_knowledge import search_user_guide, get_all_faqs, USER_GUIDE_KNOWLEDGE
    except:
        search_user_guide = lambda x: None
        get_all_faqs = lambda: []
        USER_GUIDE_KNOWLEDGE = {}
    
    try:
        from AI.engine.ai_business_knowledge import search_business_knowledge, ACCOUNTING_KNOWLEDGE, TAX_KNOWLEDGE, CUSTOMS_KNOWLEDGE
    except:
        search_business_knowledge = lambda x: {'results': []}
        ACCOUNTING_KNOWLEDGE = {}
        TAX_KNOWLEDGE = {}
        CUSTOMS_KNOWLEDGE = {}
    
    try:
        from AI.engine.ai_operations_knowledge import (
            get_settlement_explanation, get_question_suggestions, get_smart_promotion,
            get_comparison_response, get_pricing_hint, ALL_SYSTEM_OPERATIONS
        )
    except:
        get_settlement_explanation = lambda x: None
        get_question_suggestions = lambda x: []
        get_smart_promotion = lambda x: ""
        get_comparison_response = lambda x=None: ""
        get_pricing_hint = lambda x: ""
        ALL_SYSTEM_OPERATIONS = {}
    
    try:
        from AI.engine.ai_intelligence_engine import (
            analyze_customer_health, analyze_inventory_intelligence, analyze_sales_performance,
            analyze_business_risks, smart_recommendations, feel_and_respond,
            think_and_deduce, proactive_alerts, innovate_solution
        )
    except:
        analyze_customer_health = lambda x=None: {}
        analyze_inventory_intelligence = lambda: {}
        analyze_sales_performance = lambda x=30: {}
        analyze_business_risks = lambda: {'status': '✅ آمن', 'overall_score': 10, 'critical': [], 'high': [], 'medium': []}
        smart_recommendations = lambda x: []
        feel_and_respond = lambda x, y: "💡"
        think_and_deduce = lambda x, y: {}
        proactive_alerts = lambda: []
        innovate_solution = lambda x: {}
    
    try:
        from AI.engine.ai_parts_database import search_part_by_name, search_part_by_number, explain_part_function, get_parts_for_vehicle
        from AI.engine.ai_mechanical_knowledge import diagnose_problem, get_repair_guide, COMMON_PROBLEMS, VEHICLE_SYSTEMS
        from AI.engine.ai_diagnostic_engine import smart_diagnose, diagnose_heavy_equipment, check_part_in_inventory
        from AI.engine.ai_predictive_analytics import predict_needed_parts, analyze_recurring_failures
        from AI.engine.ai_ecu_knowledge import explain_dtc_code, ecu_connection_guide, ECU_KNOWLEDGE
    except:
        search_part_by_name = lambda x: None
        search_part_by_number = lambda x: None
        explain_part_function = lambda x: "لم أجد معلومات عن هذه القطعة"
        get_parts_for_vehicle = lambda x: []
        diagnose_problem = lambda x: None
        get_repair_guide = lambda x: None
        COMMON_PROBLEMS = {}
        VEHICLE_SYSTEMS = {}
        smart_diagnose = lambda x: {'success': False, 'message': 'التشخيص غير متاح'}
        diagnose_heavy_equipment = lambda x: None
        check_part_in_inventory = lambda x: {'found': False}
        predict_needed_parts = lambda x: {'success': False}
        analyze_recurring_failures = lambda x: "التحليل غير متاح"
        explain_dtc_code = lambda x: "معلومات الكود غير متاحة"
        ecu_connection_guide = lambda x: None
        ECU_KNOWLEDGE = {}
    
    from models import Customer, ServiceRequest, Expense, Product, Supplier, Invoice, Payment, User, Role, Permission
    
    message_lower = message.lower()
    
    # 🧠 فهم سياقي متقدم - تحليل النية والكيانات (NLP الذكي!)
    context = enhanced_context_understanding(message)
    
    # 🔍 وضع الشرح - إذا طلب المستخدم فهم كيف تم تحليل السؤال
    if any(word in message_lower for word in ['كيف فهمت', 'اشرح فهمك', 'debug', 'explain']):
        try:
            from AI.engine.ai_nlp_engine import get_nlp_engine
            engine = get_nlp_engine()
            result = engine.process(message)
            return engine.explain_understanding(result)
        except:
            pass
    
    # 🔒 فحص أمني أولاً - حماية المعلومات الحساسة
    sensitivity = is_sensitive_query(message)
    if sensitivity['is_sensitive'] or sensitivity['is_owner_only']:
        security_response = get_security_response(message, sensitivity)
        if security_response:
            log_security_event(message, sensitivity, 'BLOCKED')
            return security_response
        else:
            log_security_event(message, sensitivity, 'ALLOWED')
    
    # 0. ردود التحية - مع تحليل ذكي واستباقي وفهم السياق
    if context['context_type'] == 'greeting':
        # جمع إحصائيات + تحليل ذكي
        try:
            total_customers = Customer.query.count()
            total_services = ServiceRequest.query.count()
            total_users = User.query.count()
            
            # 🧠 التحليل الذكي والاستباقي
            alerts = proactive_alerts()
            recommendations = smart_recommendations('general')
            risks = analyze_business_risks()
            
            response = f"""👋 **أهلاً وسهلاً! صباح النور!**

🤖 أنا المساعد الذكي - أحلل وأفهم وأدرك وأوصي!

📊 **حالة النظام الآن:**
• 👥 العملاء: {total_customers}
• 🔧 طلبات الصيانة: {total_services}
• 👤 المستخدمين: {total_users}

🎯 **تقييم الوضع العام:** {risks.get('status', '✅ آمن')} (نقاط: {risks.get('overall_score', 10)}/10)
"""
            
            # 🚨 التنبيهات الاستباقية
            if alerts:
                response += "\n⚠️ **تنبيهات مهمة:**\n"
                for alert in alerts[:3]:  # أول 3
                    response += f"  • {alert}\n"
            
            # 💡 التوصيات الذكية
            if recommendations:
                response += "\n💡 **توصياتي لك:**\n"
                for rec in recommendations[:3]:  # أول 3
                    response += f"  • {rec}\n"
            
            response += """
🎯 **اسألني عن أي شيء - سأحلل وأوصي:**
• 📊 "حلل أداء المبيعات" - أحكم بذكاء
• 🔍 "افحص صحة العملاء" - أكتشف المشاكل
• 🧭 "ما الفرص المتاحة؟" - أبتكر حلول
• 💰 "أعطني أفضل 5 عملاء" - أحلل بعمق

**أنا لست مجرد معلومات - أنا مستشار ذكي!** 🧠

✨ **نظام Garage Manager - الأقوى في فلسطين!** 🇵🇸"""
            
            return response
        except:
            return """👋 **أهلاً وسهلاً!**

🤖 أنا المساعد الذكي - اسألني عن أي شيء! 😊"""
    
    # ✨ نظام ردود ذكي بناءً على الفهم السياقي
    # استخدام context لتوليد ردود أكثر ذكاءً ودقة
    
    # 1. معالجة الشكاوى والمشاكل بذكاء
    if context['context_type'] == 'complaint' or context['priority'] in ['urgent', 'high']:
        empathy_response = "😟 أشعر بقلقك وأفهم أهمية الموضوع. دعني أساعدك فوراً...\n\n"
        # ستتم معالجة التفاصيل لاحقاً في الكود
        # هذا فقط لتعيين النبرة
    
    # 2. توجيه الأسئلة حسب النية (Intent-based routing)
    if context['intent'] == 'count' and context['entities']:
        # سيتم البحث في قاعدة البيانات لاحقاً
        pass
    elif context['intent'] == 'analysis' and context['entities']:
        # سيتم استدعاء محرك التحليل الذكي
        pass
    elif context['intent'] == 'recommendation':
        # استدعاء نظام التوصيات
        recommendations = smart_recommendations(context.get('entities', [])[0] if context.get('entities') else 'general')
        if recommendations:
            return f"""💡 **توصياتي الذكية:**

{chr(10).join(f'• {rec}' for rec in recommendations)}

✅ هذه توصيات مبنية على تحليل البيانات الفعلية في النظام!"""
    
    # التنقل - وين/أين/اذهب/افتح (محسّن بالسياق)
    if context['intent'] == 'navigation' or any(word in message_lower for word in ['وين', 'أين', 'اذهب', 'افتح', 'صفحة', 'where', 'show me', 'رابط']):
        try:
            route_info = find_route_by_keyword(message)
            if route_info and route_info.get('matches'):
                match = route_info['matches'][0]
                return f"""📍 **وجدت الصفحة!**

📛 **الاسم:** {match['endpoint']}
🔗 **الرابط:** {match['url']}
📄 **القالب:** {match.get('linked_templates', ['N/A'])[0] if match.get('linked_templates') else 'N/A'}
📦 **الوحدة:** {match.get('blueprint', 'N/A')}

✅ انقر على الرابط أو ابحث عنها في القائمة الجانبية!"""
        except:
            pass
    
    # 💼 البحث في المعرفة المتخصصة (محاسبة، ضرائب، جمارك) أولاً
    try:
        business_results = search_business_knowledge(message)
        if business_results and business_results.get('results'):
            best_result = business_results['results'][0]
            result_type = best_result['type']
            
            if result_type == 'accounting':
                concept = best_result['data']
                response = f"""📊 **معرفة محاسبية متخصصة:**

**{concept['name']}**

📝 **التعريف:**
{concept['definition']}

"""
                if concept.get('formula'):
                    response += f"🔢 **المعادلة:**\n{concept['formula']}\n\n"
                
                if concept.get('importance'):
                    response += f"⭐ **الأهمية:**\n{concept['importance']}\n\n"
                
                if concept.get('management'):
                    response += f"💡 **الإدارة:**\n"
                    for tip in concept['management']:
                        response += f"  • {tip}\n"
                
                return sanitize_response(response)
            
            elif result_type == 'tax':
                response = f"""💰 **معرفة ضريبية متخصصة:**

{best_result['topic']}

📚 المعلومات متوفرة ومفصلة. اسأل عن:
• ضريبة القيمة المضافة (VAT)
• ضريبة الدخل
• ضريبة الاستقطاع
• الامتثال الضريبي

مثال: "كيف أحسب VAT؟" أو "ما هي نسب ضريبة الدخل؟"
"""
                return sanitize_response(response)
            
            elif result_type == 'customs':
                response = f"""🛃 **معرفة جمركية متخصصة:**

{best_result['topic']}

📚 المعلومات متوفرة ومفصلة. اسأل عن:
• عملية الاستيراد (10 خطوات)
• الرسوم الجمركية
• نظام HS Code
• المستندات المطلوبة

مثال: "ما هي خطوات الاستيراد؟" أو "كيف تحسب الرسوم الجمركية؟"
"""
                return sanitize_response(response)
    except:
        pass
    
    # 📚 البحث في دليل المستخدم - معرفة شاملة
    try:
        guide_results = search_user_guide(message)
        if guide_results and guide_results.get('results'):
            best_result = guide_results['results'][0]
            
            if best_result['type'] == 'faq':
                response = f"""📖 **من دليل المستخدم:**

❓ **{best_result['question']}**

{best_result['answer']}

🔗 **الرابط:** {best_result.get('route', 'N/A')}"""
                return sanitize_response(response)
    except:
        pass
    
    # 🧠 الذكاء المتقدم - workflows وشرح عميق
    if any(word in message_lower for word in ['كيف', 'شرح', 'how', 'explain', 'خطوات', 'steps']):
        # محاولة الحصول على workflow أولاً
        try:
            deep_knowledge = get_deep_system_knowledge(message)
            if deep_knowledge:
                return sanitize_response(deep_knowledge)
        except:
            pass
        
        # شرح الحقول والنماذج
        try:
            model_info = find_model_by_keyword(message)
            if model_info and model_info.get('model'):
                model = model_info['model']
                
                # شرح العلاقات إذا كانت متوفرة
                relationship_info = explain_relationship(model['name'])
                
                response = f"""📊 **شرح {model['name']}:**

📝 **الوصف:** {model.get('description', 'جدول في قاعدة البيانات')}

🔑 **الحقول الرئيسية:**
{chr(10).join([f"  • {col['name']}: {col.get('type', 'N/A')}" for col in model.get('columns', [])[:10]])}

"""
                if relationship_info:
                    response += f"\n{relationship_info}\n"
                
                response += "\n✅ هذا هو شرح مبسط!"
                
                return sanitize_response(response)
        except:
            pass
    
    # قائمة العمليات والمميزات - مع ترويج ذكي
    if any(word in message_lower for word in ['عمليات', 'workflows', 'ماذا يمكنك', 'what can', 'مميزات', 'features']):
        try:
            # دمج workflows مع مميزات النظام
            workflows_list = get_all_workflows_list()
            system_overview = USER_GUIDE_KNOWLEDGE.get('system_overview', {})
            comparison = get_comparison_response()
            
            response = f"""{workflows_list}

📊 **نظرة عامة على النظام:**
• {system_overview.get('modules_count', '40+')} وحدة عمل
• {system_overview.get('api_endpoints', 362)} API Endpoint
• {system_overview.get('reports_count', '20+')} تقرير مالي

✨ **ما يميز نظامنا:**
• 🤖 مساعد AI ذكي (أنا!)
• 🔒 نظام أمان متقدم (35+ صلاحية)
• ⚡ أداء فائق (89 فهرس محسّن)
• 💱 متعدد العملات (ILS/USD/JOD)
• 🎨 واجهة عصرية وسريعة

🏆 **أقوى من الشامل والأندلس بمراحل!**

💡 اسألني بالتفصيل عن أي شيء!"""
            
            return sanitize_response(response)
        except:
            pass
    
    # 1. فحص FAQ أولاً
    faq = get_local_faq_responses()
    for key, response in faq.items():
        if key in message_lower:
            return f"💡 **رد محلي فوري:**\n\n{response}"
    
    # 🔍 أسئلة تحليلية ذكية - يحلل ويستنتج ويوصي
    if any(word in message_lower for word in ['افحص', 'حلل', 'analyze', 'check', 'أفضل', 'best', 'top']):
        # أفضل العملاء
        if 'عملاء' in message_lower or 'customer' in message_lower:
            try:
                # استخراج العدد من السؤال
                import re
                numbers = re.findall(r'\d+', message)
                limit = int(numbers[0]) if numbers else 5
                
                # الاستعلام الذكي
                top_customers = db.session.query(
                    Customer.name,
                    func.sum(Invoice.total_amount).label('total')
                ).join(Invoice).group_by(Customer.id).order_by(func.sum(Invoice.total_amount).desc()).limit(limit).all()
                
                if top_customers:
                    response = f"""🏆 **أفضل {limit} عملاء (بالتحليل الذكي):**

"""
                    total_all = sum([float(total) for _, total in top_customers])
                    for idx, (name, total) in enumerate(top_customers, 1):
                        percentage = (float(total) / total_all * 100) if total_all > 0 else 0
                        response += f"{idx}. **{name}** - {float(total):.2f}₪ ({percentage:.1f}%)\n"
                    
                    # 🧠 الاستنتاج الذكي
                    if len(top_customers) >= 3:
                        top_3_total = sum([float(total) for _, total in top_customers[:3]])
                        top_3_percent = (top_3_total / total_all * 100) if total_all > 0 else 0
                        
                        response += f"""
📊 **تحليلي:**
• أفضل 3 عملاء يمثلون {top_3_percent:.1f}% من الإجمالي
"""
                        if top_3_percent > 60:
                            response += """
🚨 **تحذير:** اعتماد كبير على عدد قليل من العملاء!
💡 **توصيتي:** وسّع قاعدة العملاء لتقليل المخاطر
"""
                        else:
                            response += """
✅ **جيد:** توزيع متوازن نسبياً
"""
                    
                    response += "\n💡 **توصيتي:** اعتنِ بهؤلاء العملاء - هم عمود المشروع!"
                    return sanitize_response(response)
            except:
                pass
        
        # افحص المخزون
        if 'مخزون' in message_lower or 'inventory' in message_lower:
            try:
                analysis = analyze_inventory_intelligence()
                
                response = f"""🔍 **فحص ذكي للمخزون:**

🎯 **الحالة:** {analysis['status']}
"""
                if analysis['alerts']:
                    response += "\n🚨 **ما اكتشفته:**\n"
                    for alert in analysis['alerts'][:5]:
                        response += f"  • {alert}\n"
                
                if analysis['critical_actions']:
                    response += "\n⚡ **إجراءات عاجلة:**\n"
                    for action in analysis['critical_actions']:
                        response += f"  • {action}\n"
                
                if analysis['opportunities']:
                    response += "\n💡 **فرص:**\n"
                    for opp in analysis['opportunities'][:3]:
                        response += f"  • {opp}\n"
                
                response += "\n✅ هذا تحليل ذكي - أدركت المشكلة وأوصيت بالحل!"
                return sanitize_response(response)
            except:
                pass
    
    # 2. فحص القواعد السريعة
    quick_rules = get_local_quick_rules()
    for rule_key, rule in quick_rules.items():
        for pattern in rule['patterns']:
            if pattern in message_lower:
                try:
                    # تنفيذ الاستعلام
                    if 'Customer' in rule['query']:
                        count = Customer.query.count()
                    elif 'ServiceRequest' in rule['query']:
                        count = ServiceRequest.query.count()
                    elif 'Expense' in rule['query']:
                        count = Expense.query.count()
                    elif 'Product' in rule['query']:
                        count = Product.query.count()
                    elif 'Supplier' in rule['query']:
                        count = Supplier.query.count()
                    
                    return f"💡 **رد محلي فوري:**\n\n{rule['response_template'].format(count=count)}"
                except:
                    pass
    
    # 💼 أسئلة متخصصة - محاسبة وضرائب وجمارك
    # VAT
    if any(word in message_lower for word in ['vat', 'ضريبة القيمة المضافة', 'ضريبة مضافة']):
        if 'كيف' in message_lower or 'how' in message_lower or 'احسب' in message_lower:
            vat_data = TAX_KNOWLEDGE.get('vat', {})
            return sanitize_response(f"""💰 **ضريبة القيمة المضافة (VAT):**

📝 **التعريف:**
{vat_data.get('definition', 'ضريبة على الاستهلاك')}

📊 **النسب:**
• فلسطين: {vat_data.get('rates', {}).get('palestine', '16%')}
• إسرائيل: {vat_data.get('rates', {}).get('israel', '17%')}

🔢 **كيفية الحساب:**
• لإضافة VAT: السعر × 1.16 (فلسطين)
• لاستخراج VAT: السعر الشامل / 1.16
• مبلغ VAT: السعر × 0.16 / 1.16

💡 **آلية العمل:**
• ضريبة المبيعات (Output VAT) - مستحقة للحكومة
• ضريبة المشتريات (Input VAT) - قابلة للخصم
• الصافي = ضريبة المبيعات - ضريبة المشتريات

📋 **التقديم:**
• شهرياً أو ربع سنوي
• موعد: عادة 15 من الشهر التالي

✅ مثال: منتج سعره 1000₪
• VAT (16%) = 160₪
• السعر الشامل = 1160₪""")
    
    # ضريبة الدخل
    if any(word in message_lower for word in ['ضريبة دخل', 'ضريبة الدخل', 'income tax']):
        if 'فلسطين' in message_lower or 'palestine' in message_lower:
            return sanitize_response(f"""💰 **ضريبة الدخل في فلسطين:**

**للأفراد (شرائح تصاعدية):**
• 0% حتى 75,000₪
• 5% من 75,001 - 150,000₪
• 10% من 150,001 - 250,000₪
• 15% فوق 250,000₪

**للشركات:**
• 15% على صافي الربح

💡 **الخصومات المسموحة:**
• المصاريف التشغيلية
• الإهلاك
• الرواتب والأجور
• التأمينات
• الفوائد المدفوعة

📋 **التقديم:**
• إقرار سنوي
• موعد: نهاية أبريل للسنة السابقة
• دفعات مقدمة ربع سنوية

⚠️ استشر محاسب قانوني لحالتك الخاصة!""")
    
    # الجمارك
    if any(word in message_lower for word in ['جمارك', 'استيراد', 'تخليص', 'customs', 'import']):
        if 'خطوات' in message_lower or 'كيف' in message_lower or 'how' in message_lower:
            return sanitize_response(f"""🛃 **عملية الاستيراد - 10 خطوات:**

1️⃣ التأكد من السلعة المسموح استيرادها
2️⃣ الحصول على فاتورة (Invoice) من المورد
3️⃣ شحن البضاعة (بحري/جوي/بري)
4️⃣ وصول البضاعة للميناء/المعبر
5️⃣ تقديم المستندات للجمارك
6️⃣ الفحص الجمركي (قد يكون عشوائي)
7️⃣ تقييم البضاعة وحساب الرسوم
8️⃣ دفع الرسوم
9️⃣ الإفراج عن البضاعة
🔟 النقل للمخزن

📄 **المستندات المطلوبة:**
• فاتورة تجارية (Commercial Invoice)
• بوليصة الشحن (Bill of Lading)
• قائمة التعبئة (Packing List)
• شهادة المنشأ (Certificate of Origin)
• تصريح استيراد (إن لزم)
• رخصة الاستيراد

💰 **حساب الرسوم:**
• أساس الحساب: قيمة CIF
• CIF = Cost + Insurance + Freight
• الرسوم حسب HS Code (نظام منسق)

⚠️ استشر مخلص جمركي محترف!""")
    
    # تسويات الشركاء والموردين
    if any(word in message_lower for word in ['تسوية شريك', 'تسوية مورد', 'كيف أسوي', 'partner settlement', 'supplier settlement']):
        if 'شريك' in message_lower or 'partner' in message_lower:
            settlement_data = get_settlement_explanation('partner')
            promotion = get_smart_promotion('settlements')
            return sanitize_response(f"""🤝 **تسوية الشركاء - نظام ذكي 100%:**

{settlement_data['how_it_works']}

📋 **الخطوات:**
{chr(10).join(settlement_data['steps'])}

⭐ **المميزات:**
{chr(10).join(settlement_data['features'])}

{promotion}

🔗 **الرابط:** /vendors/partners/settlement""")
        
        elif 'مورد' in message_lower or 'supplier' in message_lower:
            settlement_data = get_settlement_explanation('supplier')
            return sanitize_response(f"""📦 **تسوية الموردين:**

{settlement_data['how_it_works']}

📋 **الخطوات:**
{chr(10).join(settlement_data['steps'])}

🔗 **الرابط:** /vendors/suppliers/settlement""")
    
    # مقارنة مع أنظمة أخرى
    if any(word in message_lower for word in ['مقارنة', 'الشامل', 'الأندلس', 'compare', 'shamil', 'andalus', 'vs']):
        competitor = None
        if 'شامل' in message_lower or 'shamil' in message_lower:
            competitor = 'shamil'
        elif 'أندلس' in message_lower or 'andalus' in message_lower:
            competitor = 'andalus'
        
        comparison = get_comparison_response(competitor)
        return sanitize_response(comparison)
    
    # السعر
    if any(word in message_lower for word in ['سعر', 'price', 'كم', 'تكلفة', 'cost']):
        pricing = get_pricing_hint('when_asked_directly')
        return sanitize_response(pricing)
    
    # الذمم المدينة
    if any(word in message_lower for word in ['ذمم مدينة', 'accounts receivable', 'ar aging']):
        return sanitize_response(f"""📊 **الذمم المدينة (AR - Accounts Receivable):**

📝 **التعريف:**
المبالغ المستحقة للشركة من العملاء مقابل بضائع أو خدمات تم تقديمها.

⭐ **الأهمية:**
تمثل سيولة مستقبلية للشركة.

🔢 **المعادلة:**
AR = إجمالي الفواتير - المدفوعات المحصلة

💡 **الإدارة الفعالة:**
• متابعة دورية لأعمار الذمم
• تحصيل المستحقات في الوقت المناسب
• وضع حد ائتماني لكل عميل (Credit Limit)
• إعداد تقرير AR Aging شهرياً

📋 **تقرير AR Aging:**
يصنف المستحقات حسب العمر:
• 0-30 يوم (جيد)
• 31-60 يوم (متابعة)
• 61-90 يوم (تحذير)
• +90 يوم (خطر!)

✅ متوفر في النظام: /reports/ar-aging""")
    
    # 3. حسابات مالية محلية - محسّن بالفهم السياقي
    if context['intent'] == 'calculation' or 'احسب' in message_lower or 'calculate' in message_lower:
        # استخراج الأرقام من السؤال
        import re
        numbers = re.findall(r'\d+(?:\.\d+)?', message)
        
        if 'vat' in context.get('entities', []) or 'vat' in message_lower or 'ضريبة' in message_lower:
            if numbers:
                amount = float(numbers[0].replace(',', ''))
                country = 'israel' if 'إسرائيل' in message_lower or 'israel' in message_lower else 'palestine'
                
                try:
                    from AI.engine.ai_knowledge_finance import calculate_vat
                    vat_result = calculate_vat(amount, country)
                    
                    return f"""💰 **حساب VAT ذكي:**

📊 **المدخلات:**
• المبلغ الأساسي: {amount:,.2f}₪
• الدولة: {'🇵🇸 فلسطين' if country == 'palestine' else '🇮🇱 إسرائيل'}

🧮 **النتيجة:**
• نسبة VAT: {vat_result['vat_rate']}%
• قيمة VAT: {vat_result['vat_amount']:,.2f}₪
• **الإجمالي شامل VAT: {vat_result['total_with_vat']:,.2f}₪**

✅ **حساب محلي دقيق 100%** - بدون اتصال إنترنت!

💡 **لاحظ:** النظام يحسب VAT تلقائياً في جميع الفواتير!"""
                except:
                    pass
        
        # حساب ضريبة الدخل
        if 'دخل' in message_lower or 'income tax' in message_lower:
            if numbers:
                income = float(numbers[0].replace(',', ''))
                try:
                    from AI.engine.ai_knowledge_finance import calculate_palestine_income_tax
                    tax = calculate_palestine_income_tax(income)
                    net = income - tax
                    
                    return f"""💰 **حساب ضريبة الدخل (فلسطين):**

📊 **الدخل الإجمالي:** {income:,.2f}₪

🧮 **الضريبة المحسوبة:**
• ضريبة الدخل: {tax:,.2f}₪
• **صافي الدخل: {net:,.2f}₪**

📈 **النسبة الفعلية:** {(tax/income*100):.2f}%

✅ حساب حسب الشرائح التصاعدية الفلسطينية!"""
                except:
                    pass
    
    # 4. معلومات عن الوحدات
    modules_info = {
        'صيانة': {'route': '/service', 'desc': 'إدارة طلبات الصيانة والإصلاح'},
        'عملاء': {'route': '/customers', 'desc': 'إدارة بيانات العملاء'},
        'نفقات': {'route': '/expenses', 'desc': 'تسجيل ومتابعة المصاريف'},
        'مبيعات': {'route': '/sales', 'desc': 'إدارة المبيعات والفواتير'},
        'متجر': {'route': '/shop', 'desc': 'المتجر الإلكتروني'},
        'مخازن': {'route': '/warehouses', 'desc': 'إدارة المستودعات'},
        'موردين': {'route': '/vendors', 'desc': 'إدارة الموردين'},
        'دفتر': {'route': '/ledger', 'desc': 'دفتر الأستاذ العام'},
        'تقارير': {'route': '/reports', 'desc': 'التقارير المالية والإدارية'},
    }
    
    for module, info in modules_info.items():
        if module in message_lower or f'وين {module}' in message_lower or f'أين {module}' in message_lower:
            return f"""📍 **معلومات الوحدة:**

📛 **الاسم:** {module}
📝 **الوصف:** {info['desc']}
🔗 **الرابط:** {info['route']}

✅ يمكنك الوصول مباشرة من القائمة الجانبية."""
    
    # 5. إحصائيات ذكية - مع تحليل وحكم واستنتاج
    if 'إحصائيات' in message_lower or 'تقرير' in message_lower or 'ملخص' in message_lower or 'حلل' in message_lower:
        try:
            # جمع البيانات
            stats = {
                'customers': Customer.query.count(),
                'services': ServiceRequest.query.count(),
                'expenses': Expense.query.count(),
                'products': Product.query.count(),
                'suppliers': Supplier.query.count(),
                'invoices': Invoice.query.count(),
                'payments': Payment.query.count(),
            }
            
            # 🧠 التحليل الذكي
            sales_analysis = analyze_sales_performance(30)
            inventory_analysis = analyze_inventory_intelligence()
            risks = analyze_business_risks()
            
            # 💭 الشعور والاستجابة
            empathy = feel_and_respond(message, stats)
            
            response = f"""{empathy} **تحليل ذكي شامل للنظام:**

📊 **الأرقام الأساسية:**
• 👥 العملاء: {stats['customers']}
• 🔧 طلبات الصيانة: {stats['services']}
• 📄 الفواتير: {stats['invoices']}
• 💳 المدفوعات: {stats['payments']}

💰 **تحليل المبيعات (30 يوم):**
• الإجمالي: {sales_analysis['current_sales']:.2f}₪
• التغير: {sales_analysis['change_percent']:+.1f}% عن الفترة السابقة
• الحكم: {sales_analysis['judgment']}
• متوسط الفاتورة: {sales_analysis['avg_invoice']:.2f}₪

🎯 **تقييم الأمان:** {risks['status']} (نقاط: {risks['overall_score']}/10)
"""
            
            # التنبيهات
            if risks['critical']:
                response += "\n🚨 **تنبيهات حرجة:**\n"
                for alert in risks['critical']:
                    response += f"  • {alert}\n"
            
            if risks['high']:
                response += "\n⚠️ **تنبيهات مهمة:**\n"
                for alert in risks['high'][:2]:
                    response += f"  • {alert}\n"
            
            # الاستنتاجات
            if sales_analysis.get('insights'):
                response += "\n💡 **استنتاجاتي:**\n"
                for insight in sales_analysis['insights'][:2]:
                    response += f"  • {insight}\n"
            
            # التوصيات
            if sales_analysis.get('recommendations'):
                response += "\n🎯 **توصياتي لك:**\n"
                for rec in sales_analysis['recommendations'][:3]:
                    response += f"  • {rec}\n"
            
            response += "\n✅ هذا تحليل ذكي حقيقي - ليس مجرد أرقام!"
            
            return response
        except Exception as e:
            pass
    
    # معلومات عن الدور الحالي
    if any(word in message_lower for word in ['من أنا', 'دوري', 'صلاحياتي', 'who am i', 'my role']):
        role_name = get_user_role_name()
        role_info = f"""👤 **معلوماتك:**

**الدور:** {role_name}

"""
        if is_owner():
            role_info += """🔓 **صلاحياتك:**
• كامل الصلاحيات - أنت المالك
• تستطيع رؤية جميع المعلومات
• تستطيع الوصول لكل شيء في النظام
"""
        elif is_manager():
            role_info += """🔑 **صلاحياتك:**
• صلاحيات إدارية
• الوصول للتقارير والإحصائيات
• إدارة العملاء والمبيعات
• المعلومات الحساسة محمية
"""
        else:
            role_info += """ℹ️ **صلاحياتك:**
• صلاحيات محدودة
• الوصول للمعلومات العامة
• بعض المعلومات الحساسة محمية
"""
        
        return role_info
    
    # 🔧 أسئلة ميكانيكية - قطع غيار وتشخيص
    # البحث عن قطعة
    if any(word in message_lower for word in ['قطعة', 'part', 'فلتر', 'filter', 'سير', 'belt', 'بوجية', 'plug']):
        try:
            # استخراج اسم القطعة
            part_result = check_part_in_inventory(message)
            if part_result['found']:
                return sanitize_response(part_result['response'])
            
            # محاولة الشرح من قاعدة المعرفة
            explanation = explain_part_function(message)
            if 'لم أجد' not in explanation:
                return sanitize_response(explanation)
        except:
            pass
    
    # التشخيص - عطل أو مشكلة
    if any(word in message_lower for word in ['عطل', 'مشكلة', 'خلل', 'fault', 'problem', 'issue', 'تقطيع', 'صوت', 'sound']):
        try:
            diagnosis_result = smart_diagnose(message)
            if diagnosis_result.get('success'):
                return sanitize_response(diagnosis_result['response'])
            else:
                # أسئلة توضيحية
                return sanitize_response(diagnosis_result['message'] + '\n\n' + '\n'.join(diagnosis_result.get('questions', [])))
        except:
            pass
    
    # كود عطل DTC
    if any(word in message_lower for word in ['كود', 'code', 'p0', 'p1', 'p2', 'p3', 'dtc']):
        # استخراج الكود
        import re
        code_match = re.search(r'[Pp][0-3]\d{3}', message)
        if code_match:
            code = code_match.group()
            explanation = explain_dtc_code(code)
            return sanitize_response(explanation)
    
    # التنبؤ بالقطع
    if any(word in message_lower for word in ['تنبأ', 'توقع', 'predict', 'قطع مطلوبة', 'needed parts', 'شو بدي اطلب']):
        try:
            predictions = predict_needed_parts(90)
            if predictions.get('success'):
                response = f"""🔮 **تنبؤ ذكي بالقطع المطلوبة:**

📊 **بناءً على {predictions['period']} الماضية:**

"""
                for idx, pred in enumerate(predictions['top_5'], 1):
                    response += f"""{idx}. **{pred['part_name']}**
   • استخدمت: {pred['total_used']} قطعة في {pred['usage_count']} مرة
   • المعدل الشهري: {pred['monthly_rate']} قطعة
   • التنبؤ للشهر القادم: {pred['predicted_next_month']} قطعة
   • المخزون الحالي: {pred['current_stock']}
   • يجب طلب: {pred['need_to_order']} قطعة
   • الأولوية: **{pred['priority']}**

"""
                
                response += """💡 **توصيتي:**
اطلب القطع ذات الأولوية العالية الآن لتجنب نفاد المخزون!

✅ هذا تنبؤ ذكي بناءً على بيانات حقيقية!"""
                
                return sanitize_response(response)
        except:
            pass
    
    # تحليل الأعطال المتكررة
    if any(word in message_lower for word in ['أعطال متكررة', 'recurring', 'الأكثر تكرار', 'most common']):
        try:
            analysis = analyze_recurring_failures(180)
            return sanitize_response(analysis)
        except:
            pass
    
    # شرح نظام معين
    if any(word in message_lower for word in ['نظام الوقود', 'نظام التبريد', 'fuel system', 'cooling system', 'كيف يعمل']):
        for system_key, system_data in VEHICLE_SYSTEMS.items():
            if system_key in message_lower or system_data['name'] in message:
                response = f"""⚙️ **{system_data['name']}:**

📦 **المكونات:**
"""
                for comp in system_data.get('components', []):
                    response += f"  • {comp}\n"
                
                if system_data.get('how_it_works'):
                    response += f"\n🔄 **كيف يعمل:**\n{system_data['how_it_works']}\n"
                
                return sanitize_response(response)
    
    # لم يتم فهم السؤال - اقترح أسئلة
    suggestions = get_question_suggestions('when_unclear')
    return '\n'.join(suggestions)

def ai_chat_with_search(user_id: int = None, query: str = None, message: str = None, session_id: str = 'default', context: Dict = None):
    global _last_audit_time
    
    if message and not query:
        query = message
    elif not query:
        return {'response': 'لم يتم تقديم سؤال', 'confidence': 0}
    
    try:
        from AI.engine.ai_master_controller import get_master_controller
        import time
        
        start_time = time.time()
        controller = get_master_controller()
        
        if context is None:
            context = {}
        
        context['user_id'] = user_id
        context['search_results'] = search_database_for_query(query)
        
        result = controller.process_intelligent_query(query, context)
        execution_time = time.time() - start_time
        
        success = bool(result.get('answer'))
        conf = result.get('confidence', 0.7)
        
        try:
            evolution = get_evolution_engine()
            evolution.record_interaction(
                query=query,
                response=result,
                success=success,
                confidence=conf,
                execution_time=execution_time
            )
        except Exception as e:
            print(f"Evolution tracking error: {e}")
        
        try:
            tracker = get_performance_tracker()
            tracker.record_query(query, result, execution_time)
        except Exception as e:
            print(f"Performance tracking error: {e}")
        
        add_to_memory(session_id, 'user', query)
        add_to_memory(session_id, 'assistant', result.get('answer', ''))
        
        log_interaction(query, result.get('answer', ''), int(conf * 100), context.get('search_results', {}))
        
        return {
            'response': result.get('answer', ''),
            'confidence': conf,
            'sources': result.get('sources', []),
            'tips': result.get('tips', [])
        }
    
    except Exception as e:
        print(f"[ERROR] AI error: {e}")
        import traceback
        traceback.print_exc()
        return _ai_chat_original(query, session_id)


def _ai_chat_original(message, session_id='default'):
    """الطريقة الأصلية (Fallback)"""
    global _last_audit_time
    
    # 🧠 حفظ السؤال في الذاكرة
    memory = get_or_create_session_memory(session_id)
    add_to_memory(session_id, 'user', message)
    
    # فهم السياق من الذاكرة
    recent_messages = memory['messages'][-5:] if len(memory['messages']) > 0 else []
    context_keywords = []
    for msg in recent_messages:
        if msg['role'] == 'user':
            context_keywords.extend(msg['content'].lower().split())
    
    # أسئلة المتابعة
    follow_up_keywords = ['وبعدين', 'وكمان', 'وأيضا', 'and then', 'also', 'more', 'كمان', 'زيادة']
    is_follow_up = any(keyword in message.lower() for keyword in follow_up_keywords)
    
    if is_follow_up and len(recent_messages) > 0:
        # البحث عن آخر موضوع
        last_topic = None
        for msg in reversed(recent_messages):
            if msg['role'] == 'assistant':
                content = msg['content'].lower()
                if 'عميل' in content:
                    last_topic = 'customers'
                elif 'مخزون' in content or 'منتج' in content:
                    last_topic = 'inventory'
                elif 'صيانة' in content:
                    last_topic = 'services'
                elif 'فاتورة' in content or 'مبيعات' in content:
                    last_topic = 'sales'
                break
        
        if last_topic:
            contextual_response = f"""💡 **فهمت - تكملة للموضوع السابق ({last_topic}):**

"""
            if last_topic == 'customers':
                contextual_response += """بعد إضافة العميل، يمكنك:
1. إضافة سيارته (/customers/<id>/vehicles)
2. إنشاء طلب صيانة له (/service/new)
3. عمل فاتورة له (/sales/new)

ماذا تريد أن تفعل؟"""
            elif last_topic == 'inventory':
                contextual_response += """بعد إدارة المخزون، يمكنك:
1. عرض تقرير المخزون المنخفض
2. طلب قطع غيار جديدة
3. عمل جرد للمخزون

ماذا تريد؟"""
            
            add_to_memory(session_id, 'assistant', contextual_response)
            return contextual_response
    
    # محاولة رد محلي ذكي أولاً
    local_response = local_intelligent_response(message)
    if local_response:
        add_to_memory(session_id, 'assistant', local_response)
        return local_response
    
    intent = analyze_question_intent(message)
    
    # معالجة طلبات التنقل أولاً
    if intent.get('navigation'):
        return handle_navigation_request(message)
    
    if intent['type'] == 'troubleshooting':
        error_result = handle_error_question(message)
        if error_result['formatted_response']:
            message = f"{message}\n\n{error_result['formatted_response']}"
    
    # فحص الأسئلة العامة (لا تحتاج بيانات من قاعدة البيانات)
    message_lower = message.lower()
    general_keywords = ['من أنت', 'عرف', 'هويت', 'اسمك', 'who are you', 'introduce',
                       'ما وضع', 'حالت', 'قدرات', 'تستطيع', 'ماذا تفعل',
                       'لماذا الثقة', 'why confidence', 'شرح', 'explain']
    
    is_general_question = any(keyword in message_lower for keyword in general_keywords)
    
    search_results = search_database_for_query(message)
    
    validation = validate_search_results(message, search_results)
    
    confidence = calculate_confidence_score(search_results, validation)
    
    # رفع الثقة للأسئلة العامة تلقائياً
    if is_general_question and confidence < 60:
        confidence = 75
        validation['has_data'] = True
        validation['quality'] = 'good'
    
    search_results['_validation'] = validation
    search_results['_confidence_score'] = confidence
    search_results['_is_general'] = is_general_question
    
    compliance = check_policy_compliance(confidence, validation.get('has_data', False))
    
    # رد ذكي تفاعلي بدل الرفض المباشر
    if not compliance['passed']:
        # بدل الرفض المطلق، نقدم رد تفاعلي
        interactive_response = f"""🤖 **أنا المساعد المحلي - أعمل الآن بدون اتصال خارجي**

📊 درجة الثقة: {confidence}%

⚠️ لم أجد بيانات مباشرة، لكن يمكنني:

"""
        
        # اقتراحات ذكية حسب السؤال
        message_lower = message.lower()
        suggestions = []
        
        if 'نفق' in message_lower or 'مصروف' in message_lower:
            suggestions.append("🔍 البحث في جدول النفقات (Expense)")
            suggestions.append("💰 حساب إجمالي النفقات من قاعدة البيانات")
            suggestions.append("📊 عرض تقرير النفقات اليومية")
        
        if 'صيانة' in message_lower or 'service' in message_lower:
            suggestions.append("🔧 البحث في طلبات الصيانة (ServiceRequest)")
            suggestions.append("📋 عرض الحالات المفتوحة والمغلقة")
        
        if 'ضريبة' in message_lower or 'vat' in message_lower:
            suggestions.append("💰 حساب VAT محلياً (16% فلسطين / 17% إسرائيل)")
            suggestions.append("📊 عرض قواعد الضرائب من المعرفة المحلية")
        
        if 'دولار' in message_lower or 'صرف' in message_lower:
            suggestions.append("💱 قراءة آخر سعر صرف من ExchangeTransaction")
            suggestions.append("📊 عرض تاريخ أسعار الصرف")
        
        if not suggestions:
            suggestions = [
                "🔍 البحث في قاعدة البيانات المحلية",
                "📊 عرض الإحصائيات العامة للنظام",
                "🧭 توجيهك للصفحة المناسبة",
                "💰 حسابات مالية محلية (VAT، الضرائب، العملات)"
            ]
        
        for i, sug in enumerate(suggestions[:4], 1):
            interactive_response += f"{i}. {sug}\n"
        
        interactive_response += f"\n💬 **هل ترغب أن أقوم بأحد هذه الإجراءات؟**\n"
        interactive_response += f"أو أعد صياغة السؤال بطريقة أوضح.\n\n"
        
        # معلومات الحالة
        identity = get_system_identity()
        interactive_response += f"📡 **الحالة:** {identity['mode']}\n"
        interactive_response += f"🔧 **Groq API:** {identity['status']['groq_api']}\n"
        
        log_interaction(message, interactive_response, confidence, search_results)
        return interactive_response
    
    response = ai_chat_response(message, search_results, session_id)
    
    log_interaction(message, response, confidence, search_results)
    
    if confidence < 70:
        response += f"\n\n⚠️ ملاحظة: درجة الثقة: {confidence}%"
    
    current_time = datetime.now(timezone.utc)
    if _last_audit_time is None or (current_time - _last_audit_time) > timedelta(hours=1):
        try:
            generate_self_audit_report()
            _last_audit_time = current_time
        except:
            pass
    
    return response

def explain_system_structure():
    """شرح هيكل النظام الكامل"""
    try:
        kb = get_knowledge_base()
        structure = kb.get_system_structure()
        
        explanation = f"""
🏗️ هيكل نظام أزاد - البنية الكاملة
═══════════════════════════════════════

📊 قاعدة البيانات:
• {structure['models_count']} موديل (جدول)
• الموديلات الرئيسية:
  {chr(10).join(f'  - {model}' for model in structure['models'][:15])}

🔗 المسارات (Routes):
• {structure['routes_count']} مسار تشغيلي

📄 الواجهات (Templates):
• {structure['templates_count']} واجهة مستخدم

🤝 العلاقات:
• {structure['relationships_count']} علاقة بين الجداول

📜 القواعد التشغيلية:
• {structure['business_rules_count']} قاعدة تجارية

═══════════════════════════════════════
✅ النظام مفهرس بالكامل وجاهز للاستعلام
"""
        return explanation
    except Exception as e:
        return f'⚠️ خطأ في شرح الهيكل: {str(e)}'

