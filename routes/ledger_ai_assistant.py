"""
المساعد الذكي للمحاسبة - AI Accounting Assistant
يحلل البيانات المالية ويكتشف المشاكل ويجيب على الأسئلة
يستخدم GPT-4 أو Claude لفهم طبيعي حقيقي
"""

import re
import os
import json
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required
from sqlalchemy import or_
from extensions import db
from utils import permission_required
from models import (
    Sale, Expense, Payment, ServiceRequest,
    Customer, Supplier, Partner,
    Product, StockLevel, Warehouse,
    ExchangeTransaction, SaleLine,
    fx_rate
)

ai_assistant_bp = Blueprint("ai_assistant", __name__, url_prefix="/ledger/ai")

# محاولة استيراد OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️ OpenAI not installed. Install with: pip install openai")

# محاولة استيراد Anthropic (Claude)
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("⚠️ Anthropic not installed. Install with: pip install anthropic")


def get_database_schema():
    """الحصول على بنية قاعدة البيانات"""
    from sqlalchemy import inspect
    
    inspector = inspect(db.engine)
    schema = {}
    
    for table_name in inspector.get_table_names():
        columns = []
        for column in inspector.get_columns(table_name):
            columns.append({
                'name': column['name'],
                'type': str(column['type'])
            })
        schema[table_name] = columns
    
    return schema


def get_code_structure():
    """الحصول على بنية الكود الأساسية"""
    import os
    
    structure = {
        'models': [],
        'routes': [],
        'key_functions': []
    }
    
    # قراءة models.py
    try:
        with open('models.py', 'r', encoding='utf-8') as f:
            content = f.read()
            # استخراج أسماء الـ classes
            import re
            classes = re.findall(r'class (\w+)\(', content)
            structure['models'] = classes
            
            # استخراج الدوال المهمة
            functions = re.findall(r'def (\w+)\(', content)
            structure['key_functions'] = functions[:20]  # أول 20 دالة
    except:
        pass
    
    # قراءة routes
    try:
        routes_dir = 'routes'
        if os.path.exists(routes_dir):
            structure['routes'] = [f for f in os.listdir(routes_dir) if f.endswith('.py')]
    except:
        pass
    
    return structure


def execute_safe_query(query_text):
    """تنفيذ استعلام SQL آمن للقراءة فقط"""
    try:
        # السماح فقط بـ SELECT
        if not query_text.strip().upper().startswith('SELECT'):
            return {"error": "Only SELECT queries allowed"}
        
        # منع الاستعلامات الخطرة
        dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE']
        for keyword in dangerous_keywords:
            if keyword in query_text.upper():
                return {"error": f"Dangerous keyword '{keyword}' not allowed"}
        
        # تنفيذ الاستعلام
        result = db.session.execute(db.text(query_text))
        rows = result.fetchall()
        
        # تحويل النتائج لـ list of dicts
        data = []
        for row in rows[:100]:  # أول 100 صف فقط
            data.append(dict(row._mapping))
        
        return {"success": True, "data": data, "count": len(data)}
        
    except Exception as e:
        return {"error": str(e)}


def use_real_ai(query, financial_context, db_schema, code_structure):
    """استخدام GPT-4 أو Claude حقيقي مع صلاحيات كاملة"""
    
    # محاولة استخدام OpenAI GPT-4
    if OPENAI_AVAILABLE and os.getenv('OPENAI_API_KEY'):
        try:
            client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            
            system_prompt = """أنت مساعد محاسبي ذكي متقدم جداً متخصص في تحليل البيانات المالية وأنظمة ERP.

🔑 صلاحياتك الكاملة:
1. ✅ قراءة جميع جداول قاعدة البيانات
2. ✅ فهم بنية الكود والـ Models
3. ✅ تحليل العلاقات بين الجداول
4. ✅ الوصول للبيانات المالية الحالية
5. ✅ فهم الـ Routes والـ Functions

📋 الجداول المتاحة:
- sale: فواتير المبيعات (id, customer_id, total_amount, currency, sale_date)
- expense: النفقات (id, amount, currency, date, payee_type, payee_entity_id)
- payment: الدفعات (id, total_amount, currency, payment_date, direction, customer_id, supplier_id)
- customer: العملاء (id, name, phone, email)
- supplier: الموردين (id, name, phone, email)
- product: المنتجات (id, name, sku, price, barcode)
- stock_level: المخزون (id, product_id, warehouse_id, quantity)
- partner: الشركاء (id, name, share_percentage)
- service_request: طلبات الصيانة (id, total_cost, created_at)

🎯 مهامك:
- الإجابة على أي سؤال محاسبي بدقة 100%
- شرح من أين جاءت الأرقام بالضبط (الجدول، الحقل، الشرط)
- اكتشاف المشاكل البرمجية والمحاسبية
- تحليل العلاقات والأنماط
- فهم الأسئلة بأي صيغة (فصحى، عامية، أخطاء إملائية، بدون همزات)
- اقتراح حلول عملية وتحسينات

📝 قواعد الإجابة:
- أجب بالعربية دائماً
- كن دقيقاً ومحترفاً
- اذكر مصدر كل رقم (مثال: "من جدول sale حقل total_amount")
- إذا وجدت مشكلة، اشرح السبب والحل
- استخدم emojis للتوضيح
- قدم أمثلة محددة مع الأرقام

مثال على إجابة جيدة:
"📊 إجمالي المبيعات: 150,000 شيقل
• المصدر: جدول sale، حقل total_amount
• العدد: 45 فاتورة
• الفترة: 2025-01-01 إلى 2025-12-31
• تم التحويل من USD و EUR باستخدام fx_rate()
• أكبر فاتورة: #123 للعميل أحمد بمبلغ 15,000 شيقل" """
            
            user_prompt = f"""📊 البيانات المالية الحالية:
{json.dumps(financial_context, ensure_ascii=False, indent=2)}

🗄️ بنية قاعدة البيانات:
{json.dumps(db_schema, ensure_ascii=False, indent=2)}

💻 بنية الكود:
{json.dumps(code_structure, ensure_ascii=False, indent=2)}

❓ السؤال: {query}

أجب بشكل احترافي ومفصل. إذا كان السؤال عن "من أين جاء الرقم"، اشرح الجدول والحقول المستخدمة."""
            
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            return response.choices[0].message.content, []
            
        except Exception as e:
            print(f"OpenAI Error: {str(e)}")
    
    # محاولة استخدام Claude
    if ANTHROPIC_AVAILABLE and os.getenv('ANTHROPIC_API_KEY'):
        try:
            client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            
            prompt = f"""أنت مساعد محاسبي ذكي متقدم جداً متخصص في تحليل البيانات المالية وأنظمة ERP.

لديك صلاحيات كاملة للوصول إلى:
1. قاعدة البيانات الكاملة (جميع الجداول والعلاقات)
2. بنية الكود (Models, Routes, Functions)
3. البيانات المالية الحالية

📊 البيانات المالية:
{json.dumps(financial_context, ensure_ascii=False, indent=2)}

🗄️ بنية قاعدة البيانات:
{json.dumps(db_schema, ensure_ascii=False, indent=2)}

💻 بنية الكود:
{json.dumps(code_structure, ensure_ascii=False, indent=2)}

❓ السؤال: {query}

مهامك:
- الإجابة بدقة عالية
- شرح من أين جاءت الأرقام (الجدول والحقل)
- اكتشاف المشاكل
- اقتراح حلول
- فهم أي صيغة للسؤال (فصحى، عامية، أخطاء إملائية)

أجب بالعربية بشكل احترافي ومفصل."""
            
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            return message.content[0].text, []
            
        except Exception as e:
            print(f"Claude Error: {str(e)}")
    
    # إذا لم يتوفر AI، استخدم المحلل البسيط
    return None, None


@ai_assistant_bp.route("/ask", methods=["POST"], endpoint="ask_question")
@login_required
@permission_required("manage_ledger")
def ask_question():
    """نقطة الوصول الرئيسية للمساعد الذكي - توجيه للمساعد الشامل"""
    try:
        # استيراد خدمة AI المركزية
        from services.ai_service import ai_chat_with_search, search_database_for_query
        
        data = request.get_json()
        query = data.get('query', '').strip()
        from_date_str = data.get('from_date')
        to_date_str = data.get('to_date')
        
        # إضافة معلومات التاريخ للسؤال إذا كانت موجودة
        if from_date_str or to_date_str:
            date_context = f"\n(الفترة: من {from_date_str or 'البداية'} إلى {to_date_str or 'اليوم'})"
            query += date_context
        
        # استخدام خدمة AI المركزية
        answer = ai_chat_with_search(query)
        
        # الحصول على نتائج البحث للتفاصيل
        search_results = search_database_for_query(query)
        
        # تحويل الإجابة لصيغة متوافقة مع الدفتر
        details = []
        if search_results:
            for key, value in search_results.items():
                if key.startswith('found_'):
                    details.append(f"✅ تم العثور على بيانات في: {key}")
                elif isinstance(value, dict):
                    details.append(f"📊 {key}: {len(value)} عنصر")
                elif isinstance(value, list):
                    details.append(f"📋 {key}: {len(value)} صف")
        
        return jsonify({
            "success": True,
            "answer": answer,
            "details": details if details else ["تم الإجابة بنجاح من المساعد الشامل"]
        })
        
    except Exception as e:
        import traceback
        print(f"Error in AI assistant: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


def analyze_query(query, from_date, to_date):
    """محلل الأسئلة الذكي - يستخدم GPT حقيقي أو محلل بسيط"""
    
    # جلب البيانات أولاً
    def convert_to_ils(amount, currency, date):
        if not amount or amount == 0:
            return 0.0
        amount = float(amount)
        if not currency or currency == 'ILS':
            return amount
        try:
            rate = fx_rate(currency, 'ILS', date, raise_on_missing=False)
            return float(amount * rate) if rate > 0 else amount
        except:
            return amount
    
    # جلب جميع البيانات المالية
    def get_all_financial_data():
        """جلب جميع البيانات المالية من النظام"""
        data = {}
        
        # المبيعات
        sales_query = Sale.query
        if from_date:
            sales_query = sales_query.filter(Sale.sale_date >= from_date)
        if to_date:
            sales_query = sales_query.filter(Sale.sale_date <= to_date)
        sales = sales_query.all()
        data['sales'] = {
            'count': len(sales),
            'total': sum(convert_to_ils(float(s.total_amount or 0), s.currency, s.sale_date) for s in sales),
            'items': sales
        }
        
        # النفقات
        expenses_query = Expense.query
        if from_date:
            expenses_query = expenses_query.filter(Expense.date >= from_date)
        if to_date:
            expenses_query = expenses_query.filter(Expense.date <= to_date)
        expenses = expenses_query.all()
        data['expenses'] = {
            'count': len(expenses),
            'total': sum(convert_to_ils(float(e.amount or 0), e.currency, e.date) for e in expenses),
            'items': expenses
        }
        
        # الدفعات
        payments_query = Payment.query
        if from_date:
            payments_query = payments_query.filter(Payment.payment_date >= from_date)
        if to_date:
            payments_query = payments_query.filter(Payment.payment_date <= to_date)
        payments = payments_query.all()
        
        incoming_total = sum(
            float(p.total_amount or 0) * float(p.fx_rate_used or 1.0) if p.fx_rate_used
            else convert_to_ils(float(p.total_amount or 0), p.currency, p.payment_date)
            for p in payments if p.direction == 'incoming'
        )
        outgoing_total = sum(
            float(p.total_amount or 0) * float(p.fx_rate_used or 1.0) if p.fx_rate_used
            else convert_to_ils(float(p.total_amount or 0), p.currency, p.payment_date)
            for p in payments if p.direction == 'outgoing'
        )
        
        data['payments'] = {
            'count': len(payments),
            'incoming_count': len([p for p in payments if p.direction == 'incoming']),
            'outgoing_count': len([p for p in payments if p.direction == 'outgoing']),
            'incoming_total': incoming_total,
            'outgoing_total': outgoing_total,
            'items': payments
        }
        
        # العملاء (نحتفظ بالـ objects الأصلية)
        customers = Customer.query.all()
        data['customers'] = {
            'count': len(customers),
            'items': customers  # نحتفظ بالـ objects
        }
        
        # الموردين
        suppliers = Supplier.query.all()
        data['suppliers'] = {
            'count': len(suppliers),
            'items': suppliers  # نحتفظ بالـ objects
        }
        
        # المنتجات
        products = Product.query.all()
        data['products'] = {
            'count': len(products),
            'items': products  # نحتفظ بالـ objects
        }
        
        # الشركاء
        partners = Partner.query.all()
        data['partners'] = {
            'count': len(partners),
            'items': partners  # نحتفظ بالـ objects
        }
        
        # المستودعات
        warehouses = Warehouse.query.all()
        data['warehouses'] = {
            'count': len(warehouses),
            'items': warehouses  # نحتفظ بالـ objects
        }
        
        # الخدمات
        services_query = ServiceRequest.query
        if from_date:
            services_query = services_query.filter(ServiceRequest.created_at >= from_date)
        if to_date:
            services_query = services_query.filter(ServiceRequest.created_at <= to_date)
        services = services_query.all()
        data['services'] = {
            'count': len(services),
            'items': services  # نحتفظ بالـ objects
        }
        
        # الربح
        data['profit'] = data['sales']['total'] - data['expenses']['total']
        
        return data
    
    # جلب البيانات
    all_data = get_all_financial_data()
    
    # تحضير السياق للـ AI (تحويل objects لـ dicts)
    customers_summary = []
    for c in all_data['customers']['items'][:10]:
        sales_for_customer = [s for s in all_data['sales']['items'] if s.customer_id == c.id]
        sales_total = sum(convert_to_ils(float(s.total_amount or 0), s.currency, s.sale_date) for s in sales_for_customer)
        
        payments_for_customer = [p for p in all_data['payments']['items'] if p.customer_id == c.id and p.direction == 'incoming']
        payments_total = sum(
            float(p.total_amount or 0) * float(p.fx_rate_used or 1.0) if p.fx_rate_used
            else convert_to_ils(float(p.total_amount or 0), p.currency, p.payment_date)
            for p in payments_for_customer
        )
        
        customers_summary.append({
            'name': c.name,
            'sales': f"{sales_total:,.2f}",
            'payments': f"{payments_total:,.2f}",
            'balance': f"{sales_total - payments_total:,.2f}"
        })
    
    suppliers_summary = []
    for s in all_data['suppliers']['items'][:10]:
        expenses_for_supplier = [e for e in all_data['expenses']['items'] 
                                if e.payee_type == 'SUPPLIER' and e.payee_entity_id == s.id]
        purchases = sum(convert_to_ils(float(e.amount or 0), e.currency, e.date) for e in expenses_for_supplier)
        
        payments_for_supplier = [p for p in all_data['payments']['items'] if p.supplier_id == s.id and p.direction == 'outgoing']
        paid = sum(
            float(p.total_amount or 0) * float(p.fx_rate_used or 1.0) if p.fx_rate_used
            else convert_to_ils(float(p.total_amount or 0), p.currency, p.payment_date)
            for p in payments_for_supplier
        )
        
        suppliers_summary.append({
            'name': s.name,
            'purchases': f"{purchases:,.2f}",
            'paid': f"{paid:,.2f}",
            'balance': f"{purchases - paid:,.2f}"
        })
    
    products_summary = []
    total_stock_value = 0
    total_stock_qty = 0
    for p in all_data['products']['items'][:20]:
        stock_levels = StockLevel.query.filter(StockLevel.product_id == p.id).all()
        qty = sum(int(sl.quantity or 0) for sl in stock_levels)
        value = qty * float(p.price or 0)
        total_stock_qty += qty
        total_stock_value += value
        
        if qty > 0:
            products_summary.append({
                'name': p.name,
                'quantity': qty,
                'price': f"{float(p.price or 0):,.2f}",
                'value': f"{value:,.2f}"
            })
    
    financial_context = {
        'period': {
            'from': from_date.strftime('%Y-%m-%d') if from_date else 'غير محدد',
            'to': to_date.strftime('%Y-%m-%d') if to_date else 'غير محدد'
        },
        'summary': {
            'total_sales': f"{all_data['sales']['total']:,.2f} شيقل",
            'sales_count': all_data['sales']['count'],
            'total_expenses': f"{all_data['expenses']['total']:,.2f} شيقل",
            'expenses_count': all_data['expenses']['count'],
            'net_profit': f"{all_data['profit']:,.2f} شيقل",
            'profit_status': 'ربح' if all_data['profit'] >= 0 else 'خسارة',
            'incoming_payments': f"{all_data['payments']['incoming_total']:,.2f} شيقل",
            'outgoing_payments': f"{all_data['payments']['outgoing_total']:,.2f} شيقل",
            'customers_count': all_data['customers']['count'],
            'suppliers_count': all_data['suppliers']['count'],
            'products_count': all_data['products']['count'],
            'stock_value': f"{total_stock_value:,.2f} شيقل",
            'stock_quantity': total_stock_qty
        },
        'customers': customers_summary,
        'suppliers': suppliers_summary,
        'products': products_summary
    }
    
    # الحصول على بنية قاعدة البيانات والكود
    db_schema = get_database_schema()
    code_structure = get_code_structure()
    
    # محاولة استخدام AI حقيقي
    ai_answer, ai_details = use_real_ai(query, financial_context, db_schema, code_structure)
    
    if ai_answer:
        # إذا نجح AI، استخدم إجابته
        print("✅ Using AI (GPT-4 or Claude)")
        return ai_answer, ai_details
    
    # إذا لم يتوفر AI، استخدم المحلل الذكي المحسّن (مجاني 100%)
    print("💡 Using advanced free analyzer (no API key needed)")
    
    # تطبيع النص - إزالة الهمزات والتشكيل
    def normalize_text(text):
        """تطبيع النص العربي لفهم أفضل"""
        if not text:
            return ""
        
        text = text.lower().strip()
        
        # إزالة التشكيل
        arabic_diacritics = re.compile("""
            ّ    | # Tashdid
            َ    | # Fatha
            ً    | # Tanwin Fath
            ُ    | # Damma
            ٌ    | # Tanwin Damm
            ِ    | # Kasra
            ٍ    | # Tanwin Kasr
            ْ    | # Sukun
            ـ     # Tatwil/Kashida
        """, re.VERBOSE)
        text = re.sub(arabic_diacritics, '', text)
        
        # توحيد الهمزات
        text = re.sub("[إأٱآا]", "ا", text)
        text = re.sub("ى", "ي", text)
        text = re.sub("ؤ", "و", text)
        text = re.sub("ئ", "ي", text)
        text = re.sub("ة", "ه", text)
        
        return text
    
    # استخراج الأسماء من السؤال
    def extract_name_from_query(query, exclude_words):
        """استخراج الاسم من السؤال"""
        words = query.split()
        for word in words:
            if len(word) > 2 and word not in exclude_words:
                return word
        return None
    
    # محلل المشاكل الذكي
    def analyze_system_issues():
        """تحليل شامل للنظام واكتشاف المشاكل"""
        issues = []
        warnings = []
        
        # 1. فحص المبيعات بدون عملاء
        orphan_sales = [s for s in all_data['sales']['items'] if not s.customer_id]
        if orphan_sales:
            issues.append({
                'type': 'data_integrity',
                'severity': 'medium',
                'title': f'🔴 {len(orphan_sales)} فاتورة بدون عميل',
                'description': 'توجد فواتير مبيعات غير مرتبطة بعملاء',
                'affected': [f"فاتورة #{s.id}" for s in orphan_sales[:5]],
                'solution': 'قم بربط هذه الفواتير بالعملاء المناسبين'
            })
        
        # 2. فحص النفقات بدون نوع
        typeless_expenses = [e for e in all_data['expenses']['items'] if not e.type]
        if typeless_expenses:
            issues.append({
                'type': 'data_integrity',
                'severity': 'low',
                'title': f'⚠️ {len(typeless_expenses)} مصروف بدون نوع',
                'description': 'توجد مصروفات غير مصنفة',
                'affected': [f"مصروف #{e.id}" for e in typeless_expenses[:5]],
                'solution': 'قم بتصنيف هذه المصروفات'
            })
        
        # 3. فحص الدفعات بدون مرجع
        orphan_payments = [p for p in all_data['payments']['items'] 
                         if not p.customer_id and not p.supplier_id and not p.partner_id]
        if orphan_payments:
            issues.append({
                'type': 'data_integrity',
                'severity': 'high',
                'title': f'🔴 {len(orphan_payments)} دفعة بدون مرجع',
                'description': 'دفعات غير مرتبطة بأي جهة (عميل/مورد/شريك)',
                'affected': [f"دفعة #{p.id}" for p in orphan_payments[:5]],
                'solution': 'قم بربط هذه الدفعات بالجهات المناسبة'
            })
        
        # 4. فحص العملات المفقودة
        missing_fx_sales = []
        for s in all_data['sales']['items']:
            if s.currency and s.currency != 'ILS':
                try:
                    rate = fx_rate(s.currency, 'ILS', s.sale_date, raise_on_missing=False)
                    if rate <= 0:
                        missing_fx_sales.append(s)
                except:
                    missing_fx_sales.append(s)
        
        if missing_fx_sales:
            issues.append({
                'type': 'currency',
                'severity': 'high',
                'title': f'🔴 {len(missing_fx_sales)} فاتورة بعملة بدون سعر صرف',
                'description': 'فواتير بعملات أجنبية لا يمكن تحويلها للشيقل',
                'affected': [f"فاتورة #{s.id} ({s.currency})" for s in missing_fx_sales[:5]],
                'solution': 'أضف أسعار الصرف من إعدادات العملات'
            })
        
        # 5. فحص المنتجات بدون سعر
        priceless_products = [p for p in all_data['products']['items'] if not p.price or p.price <= 0]
        if priceless_products:
            warnings.append({
                'type': 'product',
                'severity': 'medium',
                'title': f'⚠️ {len(priceless_products)} منتج بدون سعر',
                'description': 'منتجات بدون سعر أو سعر صفر',
                'affected': [p.name for p in priceless_products[:5]],
                'solution': 'حدد أسعار لهذه المنتجات'
            })
        
        # 6. فحص المنتجات بكمية سالبة
        negative_stock = []
        for p in all_data['products']['items']:
            stock_levels = StockLevel.query.filter(StockLevel.product_id == p.id).all()
            for sl in stock_levels:
                if sl.quantity and sl.quantity < 0:
                    negative_stock.append((p, sl))
        
        if negative_stock:
            issues.append({
                'type': 'inventory',
                'severity': 'high',
                'title': f'🔴 {len(negative_stock)} منتج بكمية سالبة',
                'description': 'مخزون سالب يشير إلى خطأ في التسجيل',
                'affected': [f"{p.name} في {sl.warehouse.name if sl.warehouse else 'مستودع غير محدد'}: {sl.quantity}" 
                           for p, sl in negative_stock[:5]],
                'solution': 'راجع حركات المخزون وصحح الأخطاء'
            })
        
        # 7. فحص العملاء بأرصدة كبيرة
        high_debt_customers = []
        for c in all_data['customers']['items']:
            sales = [s for s in all_data['sales']['items'] if s.customer_id == c.id]
            sales_total = sum(convert_to_ils(float(s.total_amount or 0), s.currency, s.sale_date) for s in sales)
            
            payments = [p for p in all_data['payments']['incoming'] if p.customer_id == c.id]
            payments_total = sum(
                float(p.total_amount or 0) * float(p.fx_rate_used or 1.0) if p.fx_rate_used
                else convert_to_ils(float(p.total_amount or 0), p.currency, p.payment_date)
                for p in payments
            )
            
            balance = sales_total - payments_total
            if balance > 10000:  # أكثر من 10,000 شيقل
                high_debt_customers.append((c, balance))
        
        if high_debt_customers:
            warnings.append({
                'type': 'financial',
                'severity': 'medium',
                'title': f'💰 {len(high_debt_customers)} عميل برصيد مرتفع',
                'description': 'عملاء بأرصدة مستحقة كبيرة',
                'affected': [f"{c.name}: {balance:,.2f} شيقل" for c, balance in high_debt_customers[:5]],
                'solution': 'تابع مع هؤلاء العملاء لتحصيل المستحقات'
            })
        
        # 8. فحص الموردين بمستحقات كبيرة
        high_debt_suppliers = []
        for s in all_data['suppliers']['items']:
            expenses = [e for e in all_data['expenses']['items'] 
                       if e.payee_type == 'SUPPLIER' and e.payee_entity_id == s.id]
            purchases = sum(convert_to_ils(float(e.amount or 0), e.currency, e.date) for e in expenses)
            
            payments = [p for p in all_data['payments']['outgoing'] if p.supplier_id == s.id]
            paid = sum(
                float(p.total_amount or 0) * float(p.fx_rate_used or 1.0) if p.fx_rate_used
                else convert_to_ils(float(p.total_amount or 0), p.currency, p.payment_date)
                for p in payments
            )
            
            balance = purchases - paid
            if balance > 10000:
                high_debt_suppliers.append((s, balance))
        
        if high_debt_suppliers:
            warnings.append({
                'type': 'financial',
                'severity': 'high',
                'title': f'💸 {len(high_debt_suppliers)} مورد بمستحقات كبيرة',
                'description': 'موردين لديهم مستحقات كبيرة غير مدفوعة',
                'affected': [f"{s.name}: {balance:,.2f} شيقل" for s, balance in high_debt_suppliers[:5]],
                'solution': 'تأكد من سداد المستحقات في الوقت المناسب'
            })
        
        # 9. فحص الخسائر
        profit = all_data['sales']['total'] - all_data['expenses']['total']
        if profit < 0:
            issues.append({
                'type': 'financial',
                'severity': 'critical',
                'title': f'🚨 خسارة: {abs(profit):,.2f} شيقل',
                'description': 'النظام يسجل خسارة في الفترة الحالية',
                'affected': [
                    f"المبيعات: {all_data['sales']['total']:,.2f} شيقل",
                    f"النفقات: {all_data['expenses']['total']:,.2f} شيقل"
                ],
                'solution': 'راجع المصروفات وحاول زيادة المبيعات'
            })
        
        # 10. فحص المنتجات الراكدة
        stagnant_products = []
        for p in all_data['products']['items']:
            has_sales = any(
                any(line.product_id == p.id for line in (s.lines or []))
                for s in all_data['sales']['items']
            )
            if not has_sales:
                stock_levels = StockLevel.query.filter(StockLevel.product_id == p.id).all()
                total_qty = sum(int(sl.quantity or 0) for sl in stock_levels)
                if total_qty > 0:
                    stagnant_products.append((p, total_qty))
        
        if stagnant_products:
            warnings.append({
                'type': 'inventory',
                'severity': 'low',
                'title': f'📦 {len(stagnant_products)} منتج راكد',
                'description': 'منتجات في المخزون بدون مبيعات في الفترة',
                'affected': [f"{p.name}: {qty} قطعة" for p, qty in stagnant_products[:5]],
                'solution': 'فكر في عروض ترويجية لهذه المنتجات'
            })
        
        return issues, warnings
    
    # محلل الإجابات الذكي المحسّن (مجاني)
    def smart_answer(query, data):
        """محلل أسئلة ذكي متقدم - يفهم السياق ويشرح المصادر"""
        answer = ""
        details = []
        
        # تطبيع السؤال لفهم أفضل
        q_normalized = normalize_text(query)
        q_lower = query.lower()
        
        # دالة لشرح مصدر البيانات
        def explain_source(table, field, description):
            """شرح من أين جاءت البيانات"""
            return f"📍 المصدر: جدول {table}، حقل {field} - {description}"
        
        # === أسئلة عن المشاكل والأخطاء ===
        if any(normalize_text(word) in q_normalized for word in ['مشكلة', 'مشاكل', 'خطأ', 'أخطاء', 'خلل', 'تحليل', 'فحص', 'تدقيق', 'issue', 'error', 'problem']):
            issues, warnings = analyze_system_issues()
            
            total_problems = len(issues) + len(warnings)
            
            if total_problems == 0:
                answer = "✅ النظام سليم! لا توجد مشاكل"
                details.append("🎉 جميع الفحوصات نجحت")
                details.append("• البيانات متكاملة")
                details.append("• لا توجد أخطاء برمجية")
                details.append("• العملات محدثة")
                details.append("• المخزون سليم")
            else:
                answer = f"🔍 وجدت {len(issues)} مشكلة و {len(warnings)} تحذير"
                
                if issues:
                    details.append("<br><strong>🔴 المشاكل الحرجة:</strong>")
                    for issue in issues:
                        details.append(f"<br><strong>{issue['title']}</strong>")
                        details.append(f"  📝 {issue['description']}")
                        if issue['affected']:
                            details.append(f"  📌 المتأثر:")
                            for item in issue['affected']:
                                details.append(f"    • {item}")
                        details.append(f"  💡 الحل: {issue['solution']}")
                
                if warnings:
                    details.append("<br><strong>⚠️ التحذيرات:</strong>")
                    for warning in warnings:
                        details.append(f"<br><strong>{warning['title']}</strong>")
                        details.append(f"  📝 {warning['description']}")
                        if warning['affected']:
                            details.append(f"  📌 المتأثر:")
                            for item in warning['affected']:
                                details.append(f"    • {item}")
                        details.append(f"  💡 الحل: {warning['solution']}")
            
            return answer, details
        
        # === أسئلة عن الأرقام الإجمالية ===
        if any(normalize_text(word) in q_normalized for word in ['كم', 'إجمالي', 'اجمالي', 'مجموع', 'total', 'كام', 'قديش']):
            
            # المبيعات
            if any(normalize_text(word) in q_normalized for word in ['مبيعات', 'بيع', 'فواتير', 'sales', 'مبيع', 'بيوع']):
                answer = f"📊 إجمالي المبيعات: {data['sales']['total']:,.2f} شيقل"
                
                # شرح المصدر
                details.append(explain_source('sale', 'total_amount', 'مجموع جميع الفواتير محولة للشيقل'))
                details.append(f"• عدد الفواتير: {data['sales']['count']}")
                details.append(f"• الفترة: {from_date.strftime('%Y-%m-%d') if from_date else 'من البداية'} إلى {to_date.strftime('%Y-%m-%d') if to_date else 'اليوم'}")
                
                if data['sales']['count'] > 0:
                    details.append(f"• متوسط الفاتورة: {data['sales']['total'] / data['sales']['count']:,.2f} شيقل")
                    
                    # تحليل بالعملات
                    by_currency = {}
                    for s in data['sales']['items']:
                        curr = s.currency or 'ILS'
                        if curr not in by_currency:
                            by_currency[curr] = {'count': 0, 'amount': 0}
                        by_currency[curr]['count'] += 1
                        by_currency[curr]['amount'] += float(s.total_amount or 0)
                    
                    if len(by_currency) > 1:
                        details.append("<br><strong>📈 توزيع العملات:</strong>")
                        for curr, info in by_currency.items():
                            details.append(f"  • {curr}: {info['count']} فاتورة بمبلغ {info['amount']:,.2f}")
                    
                    top_sales = sorted(data['sales']['items'], key=lambda x: float(x.total_amount or 0), reverse=True)[:3]
                    details.append("<br><strong>🏆 أكبر 3 فواتير:</strong>")
                    for s in top_sales:
                        customer_name = s.customer.name if s.customer else "غير محدد"
                        details.append(f"  • فاتورة #{s.id} - {customer_name}: {float(s.total_amount or 0):,.2f} {s.currency}")
                        details.append(f"    التاريخ: {s.sale_date.strftime('%Y-%m-%d')}")
                
                return answer, details
            
            # النفقات
            elif any(normalize_text(word) in q_normalized for word in ['نفقات', 'مصروفات', 'مصاريف', 'expenses', 'نفقه', 'مصروف']):
                answer = f"💰 إجمالي النفقات: {data['expenses']['total']:,.2f} شيقل"
                
                # شرح المصدر
                details.append(explain_source('expense', 'amount', 'مجموع جميع المصروفات محولة للشيقل'))
                details.append(f"• عدد المصروفات: {data['expenses']['count']}")
                details.append(f"• الفترة: {from_date.strftime('%Y-%m-%d') if from_date else 'من البداية'} إلى {to_date.strftime('%Y-%m-%d') if to_date else 'اليوم'}")
                
                if data['expenses']['count'] > 0:
                    details.append(f"• متوسط المصروف: {data['expenses']['total'] / data['expenses']['count']:,.2f} شيقل")
                    
                    # تصنيف حسب النوع
                    by_type = {}
                    for e in data['expenses']['items']:
                        etype = e.type.name if e.type else 'غير محدد'
                        if etype not in by_type:
                            by_type[etype] = 0
                        by_type[etype] += convert_to_ils(float(e.amount or 0), e.currency, e.date)
                    
                    details.append("<br><strong>📊 التصنيف حسب النوع:</strong>")
                    for etype, amount in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
                        percentage = (amount / data['expenses']['total'] * 100) if data['expenses']['total'] > 0 else 0
                        details.append(f"  • {etype}: {amount:,.2f} شيقل ({percentage:.1f}%)")
                    
                    # أكبر 3 مصروفات
                    top_expenses = sorted(data['expenses']['items'], key=lambda x: float(x.amount or 0), reverse=True)[:3]
                    details.append("<br><strong>🔝 أكبر 3 مصروفات:</strong>")
                    for e in top_expenses:
                        etype = e.type.name if e.type else 'غير محدد'
                        details.append(f"  • مصروف #{e.id} - {etype}: {float(e.amount or 0):,.2f} {e.currency}")
                        details.append(f"    التاريخ: {e.date.strftime('%Y-%m-%d')}")
                
                return answer, details
            
            # الدفعات
            elif any(normalize_text(word) in q_normalized for word in ['دفعات', 'دفع', 'payments', 'دفعه', 'مدفوع']):
                incoming_total = sum(
                    float(p.total_amount or 0) * float(p.fx_rate_used or 1.0) if p.fx_rate_used
                    else convert_to_ils(float(p.total_amount or 0), p.currency, p.payment_date)
                    for p in data['payments']['incoming']
                )
                outgoing_total = sum(
                    float(p.total_amount or 0) * float(p.fx_rate_used or 1.0) if p.fx_rate_used
                    else convert_to_ils(float(p.total_amount or 0), p.currency, p.payment_date)
                    for p in data['payments']['outgoing']
                )
                
                answer = f"💳 الدفعات - واردة: {incoming_total:,.2f} شيقل | صادرة: {outgoing_total:,.2f} شيقل"
                details.append(f"• دفعات واردة: {len(data['payments']['incoming'])}")
                details.append(f"• دفعات صادرة: {len(data['payments']['outgoing'])}")
                details.append(f"• صافي التدفق النقدي: {incoming_total - outgoing_total:,.2f} شيقل")
                return answer, details
            
            # الربح
            elif any(normalize_text(word) in q_normalized for word in ['ربح', 'خسارة', 'خساره', 'profit', 'loss', 'ارباح']):
                profit = data['sales']['total'] - data['expenses']['total']
                if profit >= 0:
                    answer = f"📈 صافي الربح: {profit:,.2f} شيقل"
                else:
                    answer = f"📉 خسارة: {abs(profit):,.2f} شيقل"
                
                details.append(f"• إجمالي المبيعات: {data['sales']['total']:,.2f} شيقل")
                details.append(f"• إجمالي النفقات: {data['expenses']['total']:,.2f} شيقل")
                details.append(f"• هامش الربح: {(profit / data['sales']['total'] * 100) if data['sales']['total'] > 0 else 0:.2f}%")
                return answer, details
            
            # العملاء
            elif any(normalize_text(word) in q_normalized for word in ['عملاء', 'customers', 'زبائن', 'عميل', 'زبون']):
                answer = f"👥 عدد العملاء: {data['customers']['count']}"
                
                customers_with_debt = 0
                total_debt = 0
                for c in data['customers']['items']:
                    sales = [s for s in data['sales']['items'] if s.customer_id == c.id]
                    sales_total = sum(convert_to_ils(float(s.total_amount or 0), s.currency, s.sale_date) for s in sales)
                    
                    payments = [p for p in data['payments']['incoming'] if p.customer_id == c.id]
                    payments_total = sum(
                        float(p.total_amount or 0) * float(p.fx_rate_used or 1.0) if p.fx_rate_used
                        else convert_to_ils(float(p.total_amount or 0), p.currency, p.payment_date)
                        for p in payments
                    )
                    
                    balance = sales_total - payments_total
                    if balance > 0:
                        customers_with_debt += 1
                        total_debt += balance
                
                details.append(f"• عملاء مدينون: {customers_with_debt}")
                details.append(f"• إجمالي المستحقات: {total_debt:,.2f} شيقل")
                return answer, details
            
            # الموردين
            elif any(normalize_text(word) in q_normalized for word in ['موردين', 'مورد', 'suppliers', 'vendor', 'موردون']):
                answer = f"🏭 عدد الموردين: {data['suppliers']['count']}"
                
                suppliers_with_debt = 0
                total_debt = 0
                for s in data['suppliers']['items']:
                    expenses = [e for e in data['expenses']['items'] 
                               if e.payee_type == 'SUPPLIER' and e.payee_entity_id == s.id]
                    purchases = sum(convert_to_ils(float(e.amount or 0), e.currency, e.date) for e in expenses)
                    
                    payments = [p for p in data['payments']['outgoing'] if p.supplier_id == s.id]
                    paid = sum(
                        float(p.total_amount or 0) * float(p.fx_rate_used or 1.0) if p.fx_rate_used
                        else convert_to_ils(float(p.total_amount or 0), p.currency, p.payment_date)
                        for p in payments
                    )
                    
                    balance = purchases - paid
                    if balance > 0:
                        suppliers_with_debt += 1
                        total_debt += balance
                
                details.append(f"• موردين مستحق لهم: {suppliers_with_debt}")
                details.append(f"• إجمالي المستحقات: {total_debt:,.2f} شيقل")
                return answer, details
            
            # المنتجات
            elif any(normalize_text(word) in q_normalized for word in ['منتجات', 'مخزون', 'products', 'stock', 'منتج', 'قطع', 'بضاعه', 'بضاعة']):
                answer = f"📦 عدد المنتجات: {data['products']['count']}"
                
                total_stock_value = 0
                total_qty = 0
                for p in data['products']['items']:
                    stock_levels = StockLevel.query.filter(StockLevel.product_id == p.id).all()
                    qty = sum(int(sl.quantity or 0) for sl in stock_levels)
                    total_qty += qty
                    total_stock_value += qty * float(p.price or 0)
                
                details.append(f"• إجمالي الكمية: {total_qty} قطعة")
                details.append(f"• قيمة المخزون: {total_stock_value:,.2f} شيقل")
                details.append(f"• عدد المستودعات: {data['warehouses']['count']}")
                return answer, details
        
        # === بحث بالاسم ===
        # استخراج الاسم بعد التطبيع
        exclude_words_normalized = [normalize_text(w) for w in [
            'كم', 'ما', 'هو', 'هي', 'من', 'اين', 'أين', 'كيف', 'هل', 'لدي', 'عندي', 'بقي',
            'رصيد', 'إجمالي', 'اجمالي', 'مجموع', 'عدد', 'كمية', 'سعر', 'قيمة', 'مبلغ'
        ]]
        
        search_name = None
        for word in q_normalized.split():
            if len(word) > 2 and word not in exclude_words_normalized:
                search_name = word
                break
        
        if search_name:
            results_found = False
            
            # بحث في العملاء
            for c in data['customers']['items']:
                if search_name in normalize_text(c.name):
                    results_found = True
                    sales = [s for s in data['sales']['items'] if s.customer_id == c.id]
                    sales_total = sum(convert_to_ils(float(s.total_amount or 0), s.currency, s.sale_date) for s in sales)
                    
                    payments = [p for p in data['payments']['incoming'] if p.customer_id == c.id]
                    payments_total = sum(
                        float(p.total_amount or 0) * float(p.fx_rate_used or 1.0) if p.fx_rate_used
                        else convert_to_ils(float(p.total_amount or 0), p.currency, p.payment_date)
                        for p in payments
                    )
                    
                    balance = sales_total - payments_total
                    answer = f"👤 العميل: {c.name}"
                    details.append(f"• إجمالي المبيعات: {sales_total:,.2f} شيقل ({len(sales)} فاتورة)")
                    details.append(f"• إجمالي الدفعات: {payments_total:,.2f} شيقل ({len(payments)} دفعة)")
                    details.append(f"• الرصيد: {balance:,.2f} شيقل {'(مدين)' if balance > 0 else '(دائن)' if balance < 0 else '(متوازن)'}")
                    
                    if c.phone:
                        details.append(f"• الهاتف: {c.phone}")
                    if c.email:
                        details.append(f"• البريد: {c.email}")
                    
                    return answer, details
            
            # بحث في الموردين
            for s in data['suppliers']['items']:
                if search_name in normalize_text(s.name):
                    results_found = True
                    expenses = [e for e in data['expenses']['items'] 
                               if e.payee_type == 'SUPPLIER' and e.payee_entity_id == s.id]
                    purchases = sum(convert_to_ils(float(e.amount or 0), e.currency, e.date) for e in expenses)
                    
                    payments = [p for p in data['payments']['outgoing'] if p.supplier_id == s.id]
                    paid = sum(
                        float(p.total_amount or 0) * float(p.fx_rate_used or 1.0) if p.fx_rate_used
                        else convert_to_ils(float(p.total_amount or 0), p.currency, p.payment_date)
                        for p in payments
                    )
                    
                    balance = purchases - paid
                    answer = f"🏭 المورد: {s.name}"
                    details.append(f"• إجمالي المشتريات: {purchases:,.2f} شيقل ({len(expenses)} مصروف)")
                    details.append(f"• إجمالي المدفوع: {paid:,.2f} شيقل ({len(payments)} دفعة)")
                    details.append(f"• المستحق: {balance:,.2f} شيقل")
                    
                    if s.phone:
                        details.append(f"• الهاتف: {s.phone}")
                    if s.email:
                        details.append(f"• البريد: {s.email}")
                    
                    return answer, details
            
            # بحث في المنتجات
            for p in data['products']['items']:
                if search_name in normalize_text(p.name) or (p.sku and search_name in normalize_text(p.sku)):
                    results_found = True
                    stock_levels = StockLevel.query.filter(StockLevel.product_id == p.id).all()
                    total_qty = sum(int(sl.quantity or 0) for sl in stock_levels)
                    
                    answer = f"📦 المنتج: {p.name}"
                    details.append(f"• الكمية المتوفرة: {total_qty} قطعة")
                    details.append(f"• السعر: {float(p.price or 0):,.2f} شيقل")
                    details.append(f"• القيمة الإجمالية: {total_qty * float(p.price or 0):,.2f} شيقل")
                    
                    if p.sku:
                        details.append(f"• رمز المنتج: {p.sku}")
                    if p.barcode:
                        details.append(f"• الباركود: {p.barcode}")
                    
                    details.append("<br><strong>توزيع المخزون:</strong>")
                    for sl in stock_levels:
                        if sl.quantity and sl.quantity > 0:
                            warehouse_name = sl.warehouse.name if sl.warehouse else "غير محدد"
                            details.append(f"  • {warehouse_name}: {sl.quantity} قطعة")
                    
                    return answer, details
            
            # بحث في الشركاء
            for p in data['partners']['items']:
                if search_name in normalize_text(p.name):
                    results_found = True
                    answer = f"👔 الشريك: {p.name}"
                    details.append(f"• نسبة الشراكة: {float(p.share_percentage or 0):.2f}%")
                    
                    if p.phone:
                        details.append(f"• الهاتف: {p.phone}")
                    if p.email:
                        details.append(f"• البريد: {p.email}")
                    
                    return answer, details
            
            if not results_found:
                answer = f"❌ لم أجد نتائج لـ '{search_name}'"
                details.append("جرب البحث بكلمات أخرى أو تأكد من الإملاء")
                return answer, details
        
        # === رسالة افتراضية مع فحص تلقائي ===
        issues, warnings = analyze_system_issues()
        total_problems = len(issues) + len(warnings)
        
        if total_problems > 0:
            answer = f"🤖 مرحباً! وجدت {len(issues)} مشكلة و {len(warnings)} تحذير في النظام"
            details = [
                "<strong>⚠️ تنبيه: يوجد مشاكل تحتاج انتباهك!</strong>",
                f"• مشاكل حرجة: {len(issues)}",
                f"• تحذيرات: {len(warnings)}",
                "<br><strong>اكتب 'فحص النظام' أو 'ما هي المشاكل؟' لرؤية التفاصيل</strong>"
            ]
        else:
            answer = "🤖 أنا المساعد المحاسبي الذكي!"
            details = [
                "✅ <strong>النظام يعمل بشكل سليم!</strong>",
                "<br><strong>يمكنني الإجابة على:</strong>",
                "📊 <strong>الأسئلة المالية:</strong>",
                "  • كم إجمالي المبيعات؟",
                "  • ما هي النفقات؟",
                "  • كم الربح أو الخسارة؟",
                "<br>👥 <strong>أسئلة العملاء والموردين:</strong>",
                "  • ما رصيد العميل [اسم]؟",
                "  • كم مستحق للمورد [اسم]؟",
                "<br>📦 <strong>أسئلة المخزون:</strong>",
                "  • كم بقي من منتج [اسم]؟",
                "  • ما قيمة المخزون؟",
                "<br>🔍 <strong>فحص النظام:</strong>",
                "  • هل يوجد مشاكل؟",
                "  • فحص النظام",
                "  • ما هي الأخطاء؟",
                "<br><strong>💡 اكتب سؤالك بشكل طبيعي وسأفهمه!</strong>"
            ]
        
        return answer, details
    
    # استدعاء المحلل الذكي
    return smart_answer(query, all_data)

