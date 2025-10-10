"""
AI Service - خدمة المساعد الذكي الشامل
المنطق الكامل للمساعد الذكي بعيداً عن Routes
نظام ذكي متقدم مع RAG وفهم عميق للنظام
"""

import json
import psutil
import os
import re
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, text
from extensions import db
from models import SystemSettings
from services.ai_knowledge import get_knowledge_base, analyze_error, format_error_response
from services.ai_knowledge_finance import (
    get_finance_knowledge, 
    calculate_palestine_income_tax,
    calculate_vat,
    get_customs_info
)
from services.ai_self_review import (
    log_interaction,
    check_policy_compliance,
    generate_self_audit_report,
    get_system_status
)
from services.ai_auto_discovery import (
    auto_discover_if_needed,
    find_route_by_keyword,
    get_route_suggestions
)
from services.ai_data_awareness import (
    auto_build_if_needed,
    find_model_by_keyword,
    load_data_schema
)


_conversation_memory = {}
_last_audit_time = None
_groq_failures = []
_local_fallback_mode = False


def get_system_setting(key, default=''):
    """الحصول على إعداد من قاعدة البيانات"""
    try:
        setting = SystemSettings.query.filter_by(key=key).first()
        return setting.value if setting else default
    except Exception as e:
        print(f"خطأ في قراءة الإعداد {key}: {str(e)}")
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
            'system_name': 'نظام أزاد لإدارة الكراج',
            'version': 'v4.0.0',
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
        print(f"خطأ في gather_system_context: {str(e)}")
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
    """الحصول على أو إنشاء ذاكرة المحادثة"""
    if session_id not in _conversation_memory:
        _conversation_memory[session_id] = {
            'messages': [],
            'context': {},
            'created_at': datetime.now(timezone.utc),
            'last_updated': datetime.now(timezone.utc)
        }
    
    _conversation_memory[session_id]['last_updated'] = datetime.now(timezone.utc)
    return _conversation_memory[session_id]


def add_to_memory(session_id, role, content):
    """إضافة رسالة للذاكرة"""
    memory = get_or_create_session_memory(session_id)
    memory['messages'].append({
        'role': role,
        'content': content,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })
    
    if len(memory['messages']) > 20:
        memory['messages'] = memory['messages'][-20:]


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
    """بناء رسالة النظام الأساسية للـ AI - محسّنة بالمعرفة"""
    
    kb = get_knowledge_base()
    structure = kb.get_system_structure()
    
    return f"""أنت النظام الذكي لـ "أزاد لإدارة الكراج" - Azad Garage Manager System
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
📦 الوحدات الرئيسية (23 وحدة):
═══════════════════════════════════════
1. 🔐 المصادقة - تسجيل الدخول والأمان
2. 🏠 لوحة التحكم - Dashboard
3. 👥 إدارة المستخدمين - الصلاحيات والأدوار
4. 🔧 الصيانة - إدارة طلبات الصيانة والإصلاح
5. 👤 العملاء - إدارة بيانات العملاء والحسابات
6. 💰 المبيعات - إدارة المبيعات والفواتير
7. 🛒 المتجر الإلكتروني - واجهة تسوق للعملاء
8. 📦 المخزون - إدارة المنتجات وقطع الغيار
9. 🏭 الموردين - إدارة الموردين والمشتريات
10. 🚚 الشحنات - تتبع الشحنات الواردة
11. 🏪 المستودعات - إدارة المخازن والنقل بينها
12. 💳 المدفوعات - نظام دفع متكامل
13. 💸 المصاريف - تسجيل المصاريف والنفقات
14. 📊 التقارير - تقارير شاملة (مالية، مخزون، أداء)
15. 📋 الملاحظات - نظام ملاحظات ذكي
16. 📱 الباركود - مسح وطباعة الباركود
17. 💱 العملات - إدارة أسعار الصرف
18. 🔗 API - واجهة برمجية للتكامل
19. 👔 الشركاء - تسويات الشركاء
20. 📝 دفتر الأستاذ - المحاسبة
21. 🛡️ وحدة الأمان - تحكم شامل (Owner فقط)
22. 🔄 النسخ الاحتياطي - نسخ تلقائية للبيانات
23. 🗑️ الحذف الصعب - نظام حذف آمن

═══════════════════════════════════════
👥 الأدوار والصلاحيات:
═══════════════════════════════════════
1. Super Admin - كل شيء
2. Admin - كل شيء عدا المتجر والامان
3. Mechanic - الصيانة فقط
4. Staff - المبيعات والمحاسبة
5. Customer - المتجر وحسابه الشخصي

═══════════════════════════════════════
📊 إحصائيات النظام الحالية (أرقام حقيقية):
═══════════════════════════════════════
{system_context.get('current_stats', 'لا توجد إحصائيات')}

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


def search_database_for_query(query):
    """البحث الشامل الذكي في كل قاعدة البيانات - محسّن بالـ Intent Analysis"""
    results = {}
    query_lower = query.lower()
    
    intent = analyze_question_intent(query)
    results['intent'] = intent
    
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
                    paid_invoices = Invoice.query.filter_by(status='PAID').count()
                    unpaid_invoices = Invoice.query.filter(Invoice.status.in_(['UNPAID', 'PARTIALLY_PAID'])).count()
                    
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
    global _groq_failures, _local_fallback_mode
    
    # تنظيف الأخطاء القديمة (أكثر من 24 ساعة)
    current_time = datetime.now(timezone.utc)
    _groq_failures = [
        f for f in _groq_failures 
        if (current_time - f).total_seconds() < 86400
    ]
    
    # إذا فشل 3 مرات خلال 24 ساعة → تفعيل Local Fallback
    if len(_groq_failures) >= 3:
        _local_fallback_mode = True
        return False
    
    return True


def get_local_fallback_response(message, search_results):
    """الرد باستخدام المعرفة المحلية فقط (بدون Groq)"""
    try:
        response = "📡 تم استخدام المعرفة المحلية مؤقتًا لتعذر الوصول إلى مزود Groq.\n\n"
        
        # تحليل بسيط من search_results
        if search_results:
            response += "📊 البيانات المتاحة:\n\n"
            
            for key, value in search_results.items():
                if isinstance(value, int):
                    response += f"• {key}: {value}\n"
                elif isinstance(value, dict):
                    response += f"• {key}: {len(value)} عنصر\n"
                elif isinstance(value, list):
                    response += f"• {key}: {len(value)} صف\n"
        else:
            response += "⚠️ لا توجد بيانات متاحة للسؤال المطروح.\n"
        
        response += "\n💡 سيتم استعادة الاتصال بـ Groq تلقائياً عند حل المشكلة."
        
        return response
    
    except Exception as e:
        return f"⚠️ خطأ في الوضع المحلي: {str(e)}"


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


def ai_chat_with_search(message, session_id='default'):
    """رد AI محسّن مع Validation و Self-Review"""
    global _last_audit_time
    
    intent = analyze_question_intent(message)
    
    # معالجة طلبات التنقل أولاً
    if intent.get('navigation'):
        return handle_navigation_request(message)
    
    if intent['type'] == 'troubleshooting':
        error_result = handle_error_question(message)
        if error_result['formatted_response']:
            message = f"{message}\n\n{error_result['formatted_response']}"
    
    search_results = search_database_for_query(message)
    
    validation = validate_search_results(message, search_results)
    
    confidence = calculate_confidence_score(search_results, validation)
    
    search_results['_validation'] = validation
    search_results['_confidence_score'] = confidence
    
    compliance = check_policy_compliance(confidence, validation.get('has_data', False))
    
    if not compliance['passed']:
        refusal = f"""⚠️ لا يمكنني الإجابة بثقة كافية.

📊 درجة الثقة: {confidence}%

🚨 الأسباب:
{chr(10).join('• ' + v for v in compliance['violations'])}

💡 جرّب:
• صياغة السؤال بطريقة أوضح
• التأكد من وجود البيانات في النظام
• استخدام كلمات مفتاحية محددة"""
        
        log_interaction(message, refusal, confidence, search_results)
        return refusal
    
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

