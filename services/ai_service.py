"""
AI Service - خدمة المساعد الذكي الشامل
المنطق الكامل للمساعد الذكي بعيداً عن Routes
"""

import json
import psutil
import os
from datetime import datetime, timezone
from sqlalchemy import func, text
from extensions import db
from models import SystemSettings


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
            Role, Permission
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


def build_system_message(system_context):
    """بناء رسالة النظام الأساسية للـ AI"""
    return f"""أنت النظام الذكي لـ "أزاد لإدارة الكراج" - Azad Garage Manager System
أنت جزء من النظام، تعرف كل شيء عنه، وتتكلم بصوته.

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
🎯 دورك وطريقة الإجابة:
═══════════════════════════════════════

📋 قواعد الإجابة الأساسية:
1. أجب بالعربية الاحترافية الواضحة
2. استخدم البيانات الحقيقية من نتائج البحث فقط
3. لا تخمن أو تفترض - البيانات الفعلية فقط
4. كن مختصراً ومباشراً في الإجابات
5. استخدم الإيموجي بشكل احترافي ومناسب

🎤 أسلوب الحديث:
- تكلم باسم النظام: "أنا نظام أزاد..." أو "نظامنا يوفر..."
- كن محترفاً وودوداً في نفس الوقت
- استخدم أسلوب واضح وسهل الفهم
- رتب الإجابات بنقاط أو جداول عند الحاجة

📊 عند الإجابة على أسئلة البيانات:
- ابدأ بإجابة مباشرة (نعم/لا أو الرقم المطلوب)
- ثم قدم التفاصيل في نقاط منظمة
- اذكر المصدر (إذا كان مهماً)
- أضف إحصائيات ذات صلة

💬 أمثلة على نمط الإجابة:

▶️ إذا سُئلت عن الشركة:
"نعم! أنا نظام أزاد لإدارة الكراج 🚗
تم تطويري بواسطة المهندس أحمد غنام من رام الله - فلسطين 🇵🇸
نظام متكامل لإدارة كراجات السيارات والصيانة بكل احترافية."

▶️ إذا سُئلت عن عميل:
"✅ نعم، العميل [الاسم] موجود في النظام:
📋 بيانات العميل:
• الرصيد: [X] شيقل
• عدد الفواتير: [Y]
• آخر عملية: [التاريخ]"

▶️ إذا سُئلت عن اليوم:
"📊 تقرير يوم [التاريخ]:
🔧 الصيانة:
• [X] طلب صيانة
• [Y] قطعة مستخدمة
💰 المبيعات: [Z] شيقل"

▶️ إذا لم تجد البيانات:
"⚠️ للأسف، لا توجد بيانات عن [الموضوع] في النظام حالياً.
يمكنك إضافتها من [اسم الوحدة]."

🎯 التعريف بالنفس:
عندما يسألك أحد "من أنت؟" أو "ما هو نظامك؟"، أجب:
"👋 أنا نظام أزاد - نظام ذكي متكامل لإدارة الكراج!
🏢 طوّرني المهندس أحمد غنام من رام الله - فلسطين
⚙️ أدير كل شيء: الصيانة، المبيعات، المخزون، العملاء، وأكثر!
💡 يمكنني مساعدتك في أي استفسار عن النظام."

أنت النظام! تكلم بثقة واحترافية ووضوح."""


def search_database_for_query(query):
    """البحث الشامل غير المحدود في كل قاعدة البيانات"""
    results = {}
    query_lower = query.lower()
    
    try:
        # استيراد جميع الموديلات
        from models import (
            Customer, Supplier, Product, ServiceRequest, Invoice, Payment,
            Expense, ExpenseType, Warehouse, StockLevel, Note, Shipment,
            Role, Permission, PartnerSettlement, SupplierSettlement,
            Account, PreOrder, OnlineCart, ExchangeTransaction, Partner,
            ServicePart, ServiceTask
        )
        
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
                        'vehicle': getattr(s, 'vehicle_info', 'N/A'),
                        'status': s.status,
                        'diagnosis': getattr(s, 'diagnosis', 'N/A')[:100]
                    } for s in today_services]
                    
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
                    Invoice.paid < Invoice.total
                ).all()
                
                paid_invoices = Invoice.query.filter(
                    Invoice.paid >= Invoice.total
                ).all()
                
                total_debt = sum(float(i.total - i.paid) for i in unpaid_invoices if hasattr(i, 'paid'))
                
                results['payment_status'] = {
                    'paid_count': len(paid_invoices),
                    'unpaid_count': len(unpaid_invoices),
                    'total_debt': total_debt
                }
        except Exception as e:
            results['today_error'] = str(e)
        
        # عد المخازن
        if 'مخزن' in query or 'مخازن' in query:
            results['warehouses_count'] = Warehouse.query.count()
            results['warehouses'] = [{
                'id': w.id,
                'name': w.name,
                'type': getattr(w, 'warehouse_type', 'N/A')
            } for w in Warehouse.query.all()]
        
        # عد العملاء
        if 'عميل' in query or 'عملاء' in query or 'زبون' in query or 'زبائن' in query:
            results['customers_count'] = Customer.query.count()
        
        # عد المنتجات
        if 'منتج' in query or 'منتجات' in query or 'قطع' in query:
            results['products_count'] = Product.query.count()
        
    except Exception as e:
        results['error'] = str(e)
    
    return results


def ai_chat_response(message, search_results=None):
    """رد AI مع نتائج البحث في قاعدة البيانات"""
    # الحصول على المفتاح النشط
    keys_json = get_system_setting('AI_API_KEYS', '[]')
    
    try:
        keys = json.loads(keys_json)
        active_key = next((k for k in keys if k.get('is_active')), None)
        
        if not active_key:
            return '⚠️ لا يوجد مفتاح AI نشط. يرجى تفعيل مفتاح من إدارة المفاتيح'
        
        # جمع بيانات النظام الشاملة
        system_context = gather_system_context()
        
        # استخدام Groq API
        try:
            import requests
            
            api_key = active_key.get('key')
            provider = active_key.get('provider', 'groq')
            
            if 'groq' in provider.lower():
                # Groq API
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                # بناء رسالة النظام
                system_msg = build_system_message(system_context)
                
                # إضافة نتائج البحث إلى الرسالة
                if search_results:
                    search_summary = "\n\n═══ نتائج البحث في قاعدة البيانات ═══\n"
                    for key, value in search_results.items():
                        if value and key != 'error':
                            search_summary += f"\n{key}: {json.dumps(value, ensure_ascii=False)}\n"
                    message = message + search_summary
                
                data = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": message}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2000
                }
                
                response = requests.post(url, headers=headers, json=data, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    return result['choices'][0]['message']['content']
                else:
                    return f'⚠️ خطأ من Groq API: {response.status_code} - {response.text[:200]}'
            
            return '⚠️ نوع المزود غير مدعوم حالياً'
            
        except requests.exceptions.Timeout:
            return '⚠️ انتهت مهلة الاتصال بـ AI. حاول مرة أخرى.'
        except Exception as e:
            return f'⚠️ خطأ في الاتصال بـ AI: {str(e)}'
    
    except Exception as e:
        return f'⚠️ خطأ في قراءة المفاتيح: {str(e)}'


def ai_chat_with_search(message):
    """رد AI مع بحث شامل في قاعدة البيانات"""
    # البحث في قاعدة البيانات
    search_results = search_database_for_query(message)
    
    # الحصول على رد AI مع النتائج
    return ai_chat_response(message, search_results)

