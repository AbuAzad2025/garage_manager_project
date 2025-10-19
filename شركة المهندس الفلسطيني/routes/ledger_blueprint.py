
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, and_, or_, desc
from extensions import db
import utils
from models import (
    Sale, Expense, Payment, ServiceRequest, 
    Customer, Supplier, Partner,
    Product, StockLevel, GLBatch, GLEntry, Account
)

csrf = CSRFProtect()

ledger_bp = Blueprint("ledger", __name__, url_prefix="/ledger")

@ledger_bp.route("/", methods=["GET"], endpoint="index")
@login_required
# @permission_required("manage_ledger")  # Commented out
def ledger_index():
    """صفحة الدفتر الرئيسية"""
    return render_template("ledger/index.html")

@ledger_bp.route("/data", methods=["GET"], endpoint="get_ledger_data")
@login_required
# @permission_required("manage_ledger")  # Commented out
def get_ledger_data():
    """جلب بيانات دفتر الأستاذ من قاعدة البيانات الحقيقية"""
    try:
        from_date_str = request.args.get('from_date')
        to_date_str = request.args.get('to_date')
        transaction_type = request.args.get('transaction_type', '').strip()
        
        # تحليل التواريخ
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d') if from_date_str else None
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if to_date_str else None
        
        ledger_entries = []
        running_balance = 0.0
        
        # 1. المبيعات (Sales)
        if not transaction_type or transaction_type == 'sale':
            sales_query = Sale.query
            if from_date:
                sales_query = sales_query.filter(Sale.sale_date >= from_date)
            if to_date:
                sales_query = sales_query.filter(Sale.sale_date <= to_date)
            
            for sale in sales_query.order_by(Sale.sale_date).all():
                from models import fx_rate
                
                customer_name = sale.customer.name if sale.customer else "عميل غير محدد"
                # تحويل للشيقل
                debit = float(sale.total_amount or 0)
                if sale.currency and sale.currency != 'ILS':
                    try:
                        rate = fx_rate(sale.currency, 'ILS', sale.sale_date, raise_on_missing=False)
                        if rate > 0:
                            debit = float(debit * float(rate))
                        else:
                            from flask import current_app
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود: {sale.currency}/ILS في المبيعات #{sale.id} - استخدام المبلغ الأصلي")
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(f"❌ خطأ في تحويل العملة للمبيعات #{sale.id}: {str(e)}")
                running_balance += debit
                
                ledger_entries.append({
                    "id": sale.id,
                    "date": sale.sale_date.strftime('%Y-%m-%d'),
                    "transaction_number": f"SALE-{sale.id}",
                    "type": "sale",
                    "type_ar": "مبيعات",
                    "description": f"فاتورة مبيعات - {customer_name}",
                    "debit": debit,
                    "credit": 0.0,
                    "balance": running_balance
                })
        
        # 2. المشتريات والنفقات (Expenses)
        if not transaction_type or transaction_type in ['purchase', 'expense']:
            expenses_query = Expense.query
            if from_date:
                expenses_query = expenses_query.filter(Expense.date >= from_date)
            if to_date:
                expenses_query = expenses_query.filter(Expense.date <= to_date)
            
            for expense in expenses_query.order_by(Expense.date).all():
                from models import fx_rate
                
                # تحويل للشيقل
                credit = float(expense.amount or 0)
                if expense.currency and expense.currency != 'ILS':
                    try:
                        rate = fx_rate(expense.currency, 'ILS', expense.date, raise_on_missing=False)
                        if rate > 0:
                            credit = float(credit * float(rate))
                        else:
                            from flask import current_app
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود: {expense.currency}/ILS في المصروف #{expense.id} - استخدام المبلغ الأصلي")
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(f"❌ خطأ في تحويل العملة للمصروف #{expense.id}: {str(e)}")
                running_balance -= credit
                
                exp_type = expense.type.name if expense.type else "مصروف"
                
                ledger_entries.append({
                    "id": expense.id,
                    "date": expense.date.strftime('%Y-%m-%d'),
                    "transaction_number": f"EXP-{expense.id}",
                    "type": "expense",
                    "type_ar": exp_type,
                    "description": expense.description or f"مصروف - {exp_type}",
                    "debit": 0.0,
                    "credit": credit,
                    "balance": running_balance
                })
        
        # 3. الدفعات (Payments)
        if not transaction_type or transaction_type == 'payment':
            payments_query = Payment.query
            if from_date:
                payments_query = payments_query.filter(Payment.payment_date >= from_date)
            if to_date:
                payments_query = payments_query.filter(Payment.payment_date <= to_date)
            
            for payment in payments_query.order_by(Payment.payment_date).all():
                from models import fx_rate as get_fx_rate
                
                # استخدام fx_rate_used إذا كان موجوداً، وإلا حساب السعر
                amount = float(payment.total_amount or 0)
                if payment.fx_rate_used:
                    amount *= float(payment.fx_rate_used)
                elif payment.currency and payment.currency != 'ILS':
                    try:
                        rate = get_fx_rate(payment.currency, 'ILS', payment.payment_date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                        else:
                            from flask import current_app
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود: {payment.currency}/ILS في الدفعة #{payment.id} - استخدام المبلغ الأصلي")
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(f"❌ خطأ في تحويل العملة للدفعة #{payment.id}: {str(e)}")
                
                # تحديد الاتجاه
                if payment.direction == 'OUT':
                    credit = amount
                    debit = 0.0
                    running_balance -= credit
                else:
                    debit = amount
                    credit = 0.0
                    running_balance += debit
                
                entity_name = "غير محدد"
                if payment.customer:
                    entity_name = payment.customer.name
                elif payment.supplier:
                    entity_name = payment.supplier.name
                elif payment.partner:
                    entity_name = payment.partner.name
                
                ledger_entries.append({
                    "id": payment.id,
                    "date": payment.payment_date.strftime('%Y-%m-%d'),
                    "transaction_number": f"PAY-{payment.id}",
                    "type": "payment",
                    "type_ar": "دفعة",
                    "description": f"دفعة - {entity_name} - {payment.reference or ''}",
                    "debit": debit,
                    "credit": credit,
                    "balance": running_balance
                })
        
        # 4. الصيانة (Service Requests)
        if not transaction_type or transaction_type in ['maintenance', 'service']:
            services_query = ServiceRequest.query
            if from_date:
                services_query = services_query.filter(ServiceRequest.created_at >= from_date)
            if to_date:
                services_query = services_query.filter(ServiceRequest.created_at <= to_date)
            
            for service in services_query.order_by(ServiceRequest.created_at).all():
                parts_total = float(service.parts_total or 0)
                labor_total = float(service.labor_total or 0)
                discount = float(service.discount_total or 0)
                tax_rate = float(service.tax_rate or 0)
                
                subtotal = parts_total + labor_total - discount
                if subtotal < 0:
                    subtotal = 0
                tax_amount = subtotal * (tax_rate / 100.0)
                service_total = subtotal + tax_amount
                
                if service_total <= 0:
                    continue
                
                service_currency = getattr(service, 'currency', 'ILS') or 'ILS'
                debit = service_total
                if service_currency != 'ILS':
                    try:
                        rate = fx_rate(service_currency, 'ILS', service.created_at or datetime.utcnow(), raise_on_missing=False)
                        if rate > 0:
                            debit = float(debit * float(rate))
                        else:
                            from flask import current_app
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود: {service_currency}/ILS في الخدمة #{service.id}")
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(f"❌ خطأ في تحويل العملة للخدمة #{service.id}: {str(e)}")
                
                running_balance += debit
                customer_name = service.customer.name if service.customer else "عميل غير محدد"
                ledger_entries.append({
                    "id": service.id,
                    "date": service.created_at.strftime('%Y-%m-%d') if service.created_at else datetime.utcnow().strftime('%Y-%m-%d'),
                    "transaction_number": service.service_number or f"SRV-{service.id}",
                    "type": "service",
                    "type_ar": "صيانة",
                    "description": f"صيانة - {customer_name} - قطع: {parts_total:.2f} + عمالة: {labor_total:.2f}",
                    "debit": debit,
                    "credit": 0.0,
                    "balance": running_balance
                })
        
        # ترتيب حسب التاريخ
        ledger_entries.sort(key=lambda x: x['date'])
        
        # إعادة حساب الرصيد المتراكم
        running_balance = 0.0
        for entry in ledger_entries:
            running_balance += entry['debit'] - entry['credit']
            entry['balance'] = running_balance
        
        # حساب الإحصائيات الحقيقية من قاعدة البيانات
        from models import fx_rate
        
        # 1. إجمالي المبيعات
        sales_query = Sale.query
        if from_date:
            sales_query = sales_query.filter(Sale.sale_date >= from_date)
        if to_date:
            sales_query = sales_query.filter(Sale.sale_date <= to_date)
        
        total_sales = 0.0
        for sale in sales_query.all():
            amount = float(sale.total_amount or 0)
            if sale.currency and sale.currency != 'ILS':
                try:
                    rate = fx_rate(sale.currency, 'ILS', sale.sale_date, raise_on_missing=False)
                    if rate > 0:
                        amount = float(amount * float(rate))
                    else:
                        from flask import current_app
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في إحصائيات دفتر الأستاذ: {sale.currency}/ILS للبيع #{sale.id}")
                except Exception as e:
                    from flask import current_app
                    current_app.logger.error(f"❌ خطأ في تحويل العملة في إحصائيات دفتر الأستاذ للبيع #{sale.id}: {str(e)}")
            total_sales += amount
        
        # 2. إجمالي المشتريات والنفقات
        expenses_query = Expense.query
        if from_date:
            expenses_query = expenses_query.filter(Expense.date >= from_date)
        if to_date:
            expenses_query = expenses_query.filter(Expense.date <= to_date)
        
        total_expenses = 0.0
        for expense in expenses_query.all():
            amount = float(expense.amount or 0)
            if expense.currency and expense.currency != 'ILS':
                try:
                    rate = fx_rate(expense.currency, 'ILS', expense.date, raise_on_missing=False)
                    if rate > 0:
                        amount = float(amount * float(rate))
                    else:
                        from flask import current_app
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في إحصائيات دفتر الأستاذ: {expense.currency}/ILS للمصروف #{expense.id}")
                except Exception as e:
                    from flask import current_app
                    current_app.logger.error(f"❌ خطأ في تحويل العملة في إحصائيات دفتر الأستاذ للمصروف #{expense.id}: {str(e)}")
            total_expenses += amount
        
        # 3. إجمالي الخدمات (الصيانة)
        services_query = ServiceRequest.query
        if from_date:
            services_query = services_query.filter(ServiceRequest.created_at >= from_date)
        if to_date:
            services_query = services_query.filter(ServiceRequest.created_at <= to_date)
        
        total_services = 0.0
        for service in services_query.all():
            # حساب إجمالي الخدمة من parts_total + labor_total + tax - discount
            parts_total = float(service.parts_total or 0)
            labor_total = float(service.labor_total or 0)
            discount = float(service.discount_total or 0)
            tax_rate = float(service.tax_rate or 0)
            
            # الحساب: (parts + labor - discount) * (1 + tax_rate/100)
            subtotal = parts_total + labor_total - discount
            if subtotal < 0:
                subtotal = 0
            tax_amount = subtotal * (tax_rate / 100.0)
            service_total = subtotal + tax_amount
            
            # تحويل للشيقل إذا كانت بعملة أخرى
            service_currency = getattr(service, 'currency', 'ILS') or 'ILS'
            if service_currency != 'ILS':
                try:
                    rate = fx_rate(service_currency, 'ILS', service.created_at or datetime.utcnow(), raise_on_missing=False)
                    if rate > 0:
                        service_total = float(service_total * float(rate))
                    else:
                        from flask import current_app
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في إحصائيات دفتر الأستاذ: {service_currency}/ILS للخدمة #{service.id}")
                except Exception as e:
                    from flask import current_app
                    current_app.logger.error(f"❌ خطأ في تحويل العملة في إحصائيات دفتر الأستاذ للخدمة #{service.id}: {str(e)}")
            
            total_services += service_total
        
        # 4. حساب تكلفة البضاعة المباعة (COGS - Cost of Goods Sold)
        from models import SaleLine
        
        total_cogs = 0.0  # تكلفة البضاعة المباعة
        cogs_details = []
        products_without_cost = []  # منتجات بدون تكلفة شراء
        estimated_products = []  # منتجات تم تقدير تكلفتها
        
        # جلب جميع أسطر المبيعات في الفترة
        sale_lines_query = (
            db.session.query(SaleLine)
            .join(Sale, Sale.id == SaleLine.sale_id)
        )
        if from_date:
            sale_lines_query = sale_lines_query.filter(Sale.sale_date >= from_date)
        if to_date:
            sale_lines_query = sale_lines_query.filter(Sale.sale_date <= to_date)
        
        for line in sale_lines_query.all():
            if line.product:
                qty_sold = float(line.quantity or 0)
                product = line.product
                unit_cost = None
                cost_source = None
                
                # 1️⃣ محاولة استخدام تكلفة الشراء (الأفضل)
                if product.purchase_price and product.purchase_price > 0:
                    unit_cost = float(product.purchase_price)
                    cost_source = "purchase_price"
                # 2️⃣ التكلفة بعد الشحن
                elif product.cost_after_shipping and product.cost_after_shipping > 0:
                    unit_cost = float(product.cost_after_shipping)
                    cost_source = "cost_after_shipping"
                # 3️⃣ التكلفة قبل الشحن
                elif product.cost_before_shipping and product.cost_before_shipping > 0:
                    unit_cost = float(product.cost_before_shipping)
                    cost_source = "cost_before_shipping"
                # 4️⃣ تقدير محافظ: 70% من سعر البيع
                elif product.price and product.price > 0:
                    unit_cost = float(product.price) * 0.70  # 70% من سعر البيع
                    cost_source = "estimated_70%"
                    
                    # تسجيل تحذير
                    from flask import current_app
                    current_app.logger.warning(
                        f"⚠️ تقدير تكلفة المنتج '{product.name}' (#{product.id}): "
                        f"استخدام 70% من سعر البيع = {unit_cost:.2f} ₪"
                    )
                    
                    # إضافة للقائمة
                    estimated_products.append({
                        'id': product.id,
                        'name': product.name,
                        'selling_price': float(product.price),
                        'estimated_cost': unit_cost,
                        'qty_sold': qty_sold
                    })
                # 5️⃣ لا يوجد أي سعر - تجاهل المنتج
                else:
                    from flask import current_app
                    current_app.logger.error(
                        f"❌ المنتج '{product.name}' (#{product.id}) بدون تكلفة أو سعر - "
                        f"تم تجاهله من حساب COGS"
                    )
                    products_without_cost.append({
                        'id': product.id,
                        'name': product.name,
                        'qty_sold': qty_sold
                    })
                    continue  # تخطي هذا المنتج
                
                line_cogs = qty_sold * unit_cost
                total_cogs += line_cogs
                
                if len(cogs_details) < 10:  # حفظ أول 10 لأغراض التفصيل
                    cogs_details.append({
                        'product': product.name,
                        'qty': qty_sold,
                        'unit_cost': unit_cost,
                        'total': line_cogs,
                        'source': cost_source
                    })
        
        # 5. حساب تكلفة الخدمات (قطع الغيار المستخدمة)
        from models import ServicePart
        
        total_service_costs = 0.0
        
        service_parts_query = (
            db.session.query(ServicePart)
            .join(ServiceRequest, ServiceRequest.id == ServicePart.service_id)
        )
        if from_date:
            service_parts_query = service_parts_query.filter(ServiceRequest.created_at >= from_date)
        if to_date:
            service_parts_query = service_parts_query.filter(ServiceRequest.created_at <= to_date)
        
        for part in service_parts_query.all():
            if part.part:  # part هو المنتج
                qty_used = float(part.quantity or 0)
                product = part.part
                unit_cost = None
                
                # نفس المنطق: تكلفة فعلية أو تقدير
                if product.purchase_price and product.purchase_price > 0:
                    unit_cost = float(product.purchase_price)
                elif product.cost_after_shipping and product.cost_after_shipping > 0:
                    unit_cost = float(product.cost_after_shipping)
                elif product.cost_before_shipping and product.cost_before_shipping > 0:
                    unit_cost = float(product.cost_before_shipping)
                elif product.price and product.price > 0:
                    unit_cost = float(product.price) * 0.70  # 70% من سعر البيع
                    from flask import current_app
                    current_app.logger.warning(
                        f"⚠️ تقدير تكلفة قطعة الغيار '{product.name}' في الخدمات: "
                        f"70% من سعر البيع = {unit_cost:.2f} ₪"
                    )
                    if product.id not in [p['id'] for p in estimated_products]:
                        estimated_products.append({
                            'id': product.id,
                            'name': product.name,
                            'selling_price': float(product.price),
                            'estimated_cost': unit_cost,
                            'qty_sold': qty_used,
                            'in_service': True
                        })
                else:
                    from flask import current_app
                    current_app.logger.error(
                        f"❌ قطعة الغيار '{product.name}' بدون تكلفة - تم تجاهلها من حساب تكاليف الخدمات"
                    )
                    if product.id not in [p['id'] for p in products_without_cost]:
                        products_without_cost.append({
                            'id': product.id,
                            'name': product.name,
                            'qty_sold': qty_used,
                            'in_service': True
                        })
                    continue
                
                total_service_costs += qty_used * unit_cost
        
        # 6. صافي الربح الحقيقي
        gross_profit_sales = total_sales - total_cogs  # ربح المبيعات
        gross_profit_services = total_services - total_service_costs  # ربح الخدمات
        total_gross_profit = gross_profit_sales + gross_profit_services
        net_profit = total_gross_profit - total_expenses  # الربح الصافي
        
        statistics = {
            "total_sales": total_sales,
            "total_cogs": total_cogs,
            "gross_profit_sales": gross_profit_sales,
            "total_services": total_services,
            "total_service_costs": total_service_costs,
            "gross_profit_services": gross_profit_services,
            "total_gross_profit": total_gross_profit,
            "total_revenue": total_sales + total_services,
            "total_expenses": total_expenses,
            "net_profit": net_profit,
            "profit_margin": (net_profit / (total_sales + total_services) * 100) if (total_sales + total_services) > 0 else 0,
            "cogs_details": cogs_details,
            "estimated_products_count": len(estimated_products),
            "estimated_products": estimated_products,
            "products_without_cost_count": len(products_without_cost),
            "products_without_cost": products_without_cost
        }
        
        return jsonify({
            "data": ledger_entries,
            "statistics": statistics
        })
        
    except Exception as e:
        import traceback
        print(f"Error in get_ledger_data: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e), "data": [], "statistics": {}}), 500

@ledger_bp.route("/accounts-summary", methods=["GET"], endpoint="get_accounts_summary")
@login_required
# @permission_required("manage_ledger")  # Commented out
def get_accounts_summary():
    """جلب ملخص الحسابات (ميزان المراجعة)"""
    try:
        from_date_str = request.args.get('from_date')
        to_date_str = request.args.get('to_date')
        
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d') if from_date_str else None
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if to_date_str else None
        
        accounts = []
        
        # 1. حساب المبيعات
        from models import fx_rate
        
        sales_query = Sale.query
        if from_date:
            sales_query = sales_query.filter(Sale.sale_date >= from_date)
        if to_date:
            sales_query = sales_query.filter(Sale.sale_date <= to_date)
        
        total_sales = 0.0
        for sale in sales_query.all():
            amount = float(sale.total_amount or 0)
            if sale.currency and sale.currency != 'ILS':
                try:
                    rate = fx_rate(sale.currency, 'ILS', sale.sale_date, raise_on_missing=False)
                    if rate > 0:
                        amount = float(amount * float(rate))
                    else:
                        from flask import current_app
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في ميزان المراجعة: {sale.currency}/ILS للبيع #{sale.id}")
                except Exception as e:
                    from flask import current_app
                    current_app.logger.error(f"❌ خطأ في تحويل العملة في ميزان المراجعة للبيع #{sale.id}: {str(e)}")
            total_sales += amount
        
        accounts.append({
            "name": "المبيعات",
            "debit_balance": total_sales,
            "credit_balance": 0.0
        })
        
        # 2. حساب الخدمات (الصيانة)
        services_query = ServiceRequest.query
        if from_date:
            services_query = services_query.filter(ServiceRequest.created_at >= from_date)
        if to_date:
            services_query = services_query.filter(ServiceRequest.created_at <= to_date)
        
        total_services = 0.0
        for service in services_query.all():
            # حساب إجمالي الخدمة
            parts_total = float(service.parts_total or 0)
            labor_total = float(service.labor_total or 0)
            discount = float(service.discount_total or 0)
            tax_rate = float(service.tax_rate or 0)
            
            subtotal = parts_total + labor_total - discount
            if subtotal < 0:
                subtotal = 0
            tax_amount = subtotal * (tax_rate / 100.0)
            service_total = subtotal + tax_amount
            
            # تحويل للشيقل
            service_currency = getattr(service, 'currency', 'ILS') or 'ILS'
            if service_currency != 'ILS':
                try:
                    rate = fx_rate(service_currency, 'ILS', service.created_at or datetime.utcnow(), raise_on_missing=False)
                    if rate > 0:
                        service_total = float(service_total * float(rate))
                    else:
                        from flask import current_app
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في ميزان المراجعة: {service_currency}/ILS للخدمة #{service.id}")
                except Exception as e:
                    from flask import current_app
                    current_app.logger.error(f"❌ خطأ في تحويل العملة في ميزان المراجعة للخدمة #{service.id}: {str(e)}")
            
            total_services += service_total
        
        accounts.append({
            "name": "الخدمات (الصيانة)",
            "debit_balance": total_services,
            "credit_balance": 0.0
        })
        
        # 3. حساب تكلفة البضاعة المباعة (COGS) - مع التحذيرات
        from models import SaleLine
        
        total_cogs = 0.0
        sale_lines_query = (
            db.session.query(SaleLine)
            .join(Sale, Sale.id == SaleLine.sale_id)
        )
        if from_date:
            sale_lines_query = sale_lines_query.filter(Sale.sale_date >= from_date)
        if to_date:
            sale_lines_query = sale_lines_query.filter(Sale.sale_date <= to_date)
        
        for line in sale_lines_query.all():
            if line.product:
                qty_sold = float(line.quantity or 0)
                product = line.product
                unit_cost = None
                
                # استخدام تكلفة فعلية أو تقدير محافظ
                if product.purchase_price and product.purchase_price > 0:
                    unit_cost = float(product.purchase_price)
                elif product.cost_after_shipping and product.cost_after_shipping > 0:
                    unit_cost = float(product.cost_after_shipping)
                elif product.cost_before_shipping and product.cost_before_shipping > 0:
                    unit_cost = float(product.cost_before_shipping)
                elif product.price and product.price > 0:
                    unit_cost = float(product.price) * 0.70  # تقدير: 70% من سعر البيع
                else:
                    unit_cost = 0  # في ميزان المراجعة نستخدم صفر
                
                total_cogs += qty_sold * unit_cost
        
        accounts.append({
            "name": "تكلفة البضاعة المباعة (COGS)",
            "debit_balance": 0.0,
            "credit_balance": total_cogs
        })
        
        # 4. حساب المشتريات والنفقات
        expenses_query = Expense.query
        if from_date:
            expenses_query = expenses_query.filter(Expense.date >= from_date)
        if to_date:
            expenses_query = expenses_query.filter(Expense.date <= to_date)
        
        total_expenses = 0.0
        for expense in expenses_query.all():
            amount = float(expense.amount or 0)
            if expense.currency and expense.currency != 'ILS':
                try:
                    rate = fx_rate(expense.currency, 'ILS', expense.date, raise_on_missing=False)
                    if rate > 0:
                        amount = float(amount * float(rate))
                    else:
                        from flask import current_app
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في ميزان المراجعة: {expense.currency}/ILS للمصروف #{expense.id}")
                except Exception as e:
                    from flask import current_app
                    current_app.logger.error(f"❌ خطأ في تحويل العملة في ميزان المراجعة للمصروف #{expense.id}: {str(e)}")
            total_expenses += amount
        
        accounts.append({
            "name": "المشتريات والنفقات",
            "debit_balance": 0.0,
            "credit_balance": total_expenses
        })
        
        # 3. حساب الخزينة (من الدفعات)
        payments_in_query = Payment.query.filter(Payment.direction == 'IN')
        payments_out_query = Payment.query.filter(Payment.direction == 'OUT')
        
        if from_date:
            payments_in_query = payments_in_query.filter(Payment.payment_date >= from_date)
            payments_out_query = payments_out_query.filter(Payment.payment_date >= from_date)
        if to_date:
            payments_in_query = payments_in_query.filter(Payment.payment_date <= to_date)
            payments_out_query = payments_out_query.filter(Payment.payment_date <= to_date)
        
        total_payments_in = 0.0
        for payment in payments_in_query.all():
            amount = float(payment.total_amount or 0)
            if payment.currency and payment.currency != 'ILS':
                try:
                    rate = fx_rate(payment.currency, 'ILS', payment.payment_date, raise_on_missing=False)
                    if rate > 0:
                        amount = float(amount * float(rate))
                    else:
                        from flask import current_app
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في حساب الخزينة: {payment.currency}/ILS للدفعة #{payment.id}")
                except Exception as e:
                    from flask import current_app
                    current_app.logger.error(f"❌ خطأ في تحويل العملة في حساب الخزينة للدفعة #{payment.id}: {str(e)}")
            total_payments_in += amount
        
        total_payments_out = 0.0
        for payment in payments_out_query.all():
            amount = float(payment.total_amount or 0)
            if payment.currency and payment.currency != 'ILS':
                try:
                    rate = fx_rate(payment.currency, 'ILS', payment.payment_date, raise_on_missing=False)
                    if rate > 0:
                        amount = float(amount * float(rate))
                    else:
                        from flask import current_app
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في حساب الخزينة: {payment.currency}/ILS للدفعة #{payment.id}")
                except Exception as e:
                    from flask import current_app
                    current_app.logger.error(f"❌ خطأ في تحويل العملة في حساب الخزينة للدفعة #{payment.id}: {str(e)}")
            total_payments_out += amount
        
        accounts.append({
            "name": "الخزينة",
            "debit_balance": total_payments_in,
            "credit_balance": total_payments_out
        })
        
        # 4. حساب المخزون (بالتكلفة الفعلية)
        total_stock_value = 0.0
        total_stock_qty = 0
        stock_levels = StockLevel.query.filter(StockLevel.quantity > 0).all()
        for stock in stock_levels:
            if stock.product:
                qty = float(stock.quantity or 0)
                # استخدام purchase_price (تكلفة الشراء) وليس selling_price
                cost = float(stock.product.purchase_price or stock.product.cost_after_shipping or stock.product.price or 0)
                total_stock_value += qty * cost
                total_stock_qty += int(qty)
        
        accounts.append({
            "name": "المخزون",
            "debit_balance": total_stock_value,
            "credit_balance": 0.0,
            "quantity": total_stock_qty,
            "note": f"قيمة {total_stock_qty} قطعة بالتكلفة الفعلية"
        })
        
        return jsonify(accounts)
        
    except Exception as e:
        import traceback
        print(f"Error in get_accounts_summary: {str(e)}")
        print(traceback.format_exc())
        return jsonify([]), 500

@ledger_bp.route("/receivables-summary", methods=["GET"], endpoint="get_receivables_summary")
@login_required
# @permission_required("manage_ledger")  # Commented out
def get_receivables_summary():
    """جلب ملخص الذمم (العملاء، الموردين، الشركاء)"""
    try:
        from_date_str = request.args.get('from_date')
        to_date_str = request.args.get('to_date')
        
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d') if from_date_str else None
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if to_date_str else None
        
        receivables = []
        
        # 1. العملاء (Customers)
        from models import fx_rate
        
        customers = Customer.query.all()
        for customer in customers:
            # حساب المبيعات للعميل
            sales_query = Sale.query.filter(Sale.customer_id == customer.id)
            if from_date:
                sales_query = sales_query.filter(Sale.sale_date >= from_date)
            if to_date:
                sales_query = sales_query.filter(Sale.sale_date <= to_date)
            
            total_sales = 0.0
            for sale in sales_query.all():
                amount = float(sale.total_amount or 0)
                if sale.currency and sale.currency != 'ILS':
                    try:
                        rate = fx_rate(sale.currency, 'ILS', sale.sale_date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                        else:
                            from flask import current_app
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم: {sale.currency}/ILS للبيع #{sale.id}")
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(f"❌ خطأ في تحويل العملة في ملخص الذمم للبيع #{sale.id}: {str(e)}")
                total_sales += amount
            
            # حساب الدفعات من العميل
            payments_query = Payment.query.filter(
                Payment.customer_id == customer.id,
                Payment.direction == 'IN'
            )
            if from_date:
                payments_query = payments_query.filter(Payment.payment_date >= from_date)
            if to_date:
                payments_query = payments_query.filter(Payment.payment_date <= to_date)
            
            total_payments = 0.0
            for payment in payments_query.all():
                amount = float(payment.total_amount or 0)
                if payment.currency and payment.currency != 'ILS':
                    try:
                        rate = fx_rate(payment.currency, 'ILS', payment.payment_date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                        else:
                            from flask import current_app
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم: {payment.currency}/ILS للدفعة #{payment.id}")
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(f"❌ خطأ في تحويل العملة في ملخص الذمم للدفعة #{payment.id}: {str(e)}")
                total_payments += amount
            
            if total_sales > 0 or total_payments > 0:
                receivables.append({
                    "name": customer.name,
                    "type": "customer",
                    "type_ar": "عميل",
                    "debit": total_sales,
                    "credit": total_payments
                })
        
        # 2. الموردين (Suppliers)
        suppliers = Supplier.query.all()
        for supplier in suppliers:
            # حساب المشتريات من المورد (النفقات)
            expenses_query = Expense.query.filter(
                Expense.payee_type == 'SUPPLIER',
                Expense.payee_entity_id == supplier.id
            )
            if from_date:
                expenses_query = expenses_query.filter(Expense.date >= from_date)
            if to_date:
                expenses_query = expenses_query.filter(Expense.date <= to_date)
            
            total_purchases = 0.0
            for expense in expenses_query.all():
                amount = float(expense.amount or 0)
                if expense.currency and expense.currency != 'ILS':
                    try:
                        rate = fx_rate(expense.currency, 'ILS', expense.date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                        else:
                            from flask import current_app
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم (موردين): {expense.currency}/ILS للمصروف #{expense.id}")
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(f"❌ خطأ في تحويل العملة في ملخص الذمم (موردين) للمصروف #{expense.id}: {str(e)}")
                total_purchases += amount
            
            # حساب الدفعات للمورد
            payments_query = Payment.query.filter(
                Payment.supplier_id == supplier.id,
                Payment.direction == 'OUT'
            )
            if from_date:
                payments_query = payments_query.filter(Payment.payment_date >= from_date)
            if to_date:
                payments_query = payments_query.filter(Payment.payment_date <= to_date)
            
            total_payments = 0.0
            for payment in payments_query.all():
                amount = float(payment.total_amount or 0)
                if payment.currency and payment.currency != 'ILS':
                    try:
                        rate = fx_rate(payment.currency, 'ILS', payment.payment_date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                        else:
                            from flask import current_app
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم (موردين): {payment.currency}/ILS للدفعة #{payment.id}")
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(f"❌ خطأ في تحويل العملة في ملخص الذمم (موردين) للدفعة #{payment.id}: {str(e)}")
                total_payments += amount
            
            if total_purchases > 0 or total_payments > 0:
                receivables.append({
                    "name": supplier.name,
                    "type": "supplier",
                    "type_ar": "مورد",
                    "debit": total_payments,
                    "credit": total_purchases
                })
        
        # 3. الشركاء (Partners)
        partners = Partner.query.all()
        for partner in partners:
            # حساب النفقات المرتبطة بالشريك
            expenses_query = Expense.query.filter(
                Expense.payee_type == 'PARTNER',
                Expense.payee_entity_id == partner.id
            )
            if from_date:
                expenses_query = expenses_query.filter(Expense.date >= from_date)
            if to_date:
                expenses_query = expenses_query.filter(Expense.date <= to_date)
            
            total_expenses = 0.0
            for expense in expenses_query.all():
                amount = float(expense.amount or 0)
                if expense.currency and expense.currency != 'ILS':
                    try:
                        rate = fx_rate(expense.currency, 'ILS', expense.date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                        else:
                            from flask import current_app
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم (شركاء): {expense.currency}/ILS للمصروف #{expense.id}")
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(f"❌ خطأ في تحويل العملة في ملخص الذمم (شركاء) للمصروف #{expense.id}: {str(e)}")
                total_expenses += amount
            
            # حساب الدفعات من/إلى الشريك
            payments_in_query = Payment.query.filter(
                Payment.partner_id == partner.id,
                Payment.direction == 'IN'
            )
            payments_out_query = Payment.query.filter(
                Payment.partner_id == partner.id,
                Payment.direction == 'OUT'
            )
            
            if from_date:
                payments_in_query = payments_in_query.filter(Payment.payment_date >= from_date)
                payments_out_query = payments_out_query.filter(Payment.payment_date >= from_date)
            if to_date:
                payments_in_query = payments_in_query.filter(Payment.payment_date <= to_date)
                payments_out_query = payments_out_query.filter(Payment.payment_date <= to_date)
            
            total_in = 0.0
            for payment in payments_in_query.all():
                amount = float(payment.total_amount or 0)
                if payment.currency and payment.currency != 'ILS':
                    try:
                        rate = fx_rate(payment.currency, 'ILS', payment.payment_date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                        else:
                            from flask import current_app
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم (شركاء): {payment.currency}/ILS للدفعة #{payment.id}")
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(f"❌ خطأ في تحويل العملة في ملخص الذمم (شركاء) للدفعة #{payment.id}: {str(e)}")
                total_in += amount
            
            total_out = 0.0
            for payment in payments_out_query.all():
                amount = float(payment.total_amount or 0)
                if payment.currency and payment.currency != 'ILS':
                    try:
                        rate = fx_rate(payment.currency, 'ILS', payment.payment_date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                        else:
                            from flask import current_app
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم (شركاء): {payment.currency}/ILS للدفعة #{payment.id}")
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(f"❌ خطأ في تحويل العملة في ملخص الذمم (شركاء) للدفعة #{payment.id}: {str(e)}")
                total_out += amount
            
            if total_in > 0 or total_out > 0 or total_expenses > 0:
                receivables.append({
                    "name": partner.name,
                    "type": "partner",
                    "type_ar": "شريك",
                    "debit": total_in + total_expenses,
                    "credit": total_out
                })
        
        return jsonify(receivables)
        
    except Exception as e:
        import traceback
        print(f"Error in get_receivables_summary: {str(e)}")
        print(traceback.format_exc())
        return jsonify([]), 500

@ledger_bp.route("/smart-assistant", methods=["POST"], endpoint="smart_assistant")
@login_required
# @permission_required("manage_ledger")  # Commented out
def smart_assistant():
    """
    المساعد المحاسبي الذكي - نقطة وصول موحدة
    يعيد التوجيه إلى المساعد الذكي المنفصل
    """
    from routes.ledger_ai_assistant import ask_question
    return ask_question()

@ledger_bp.route("/export", methods=["GET"], endpoint="export_ledger")
@login_required
# @permission_required("manage_ledger")  # Commented out
def export_ledger():
    """تصدير دفتر الأستاذ"""
    # يمكن إضافة منطق التصدير هنا
    return "تصدير دفتر الأستاذ - قريباً"

@ledger_bp.route("/transaction/<int:id>", methods=["GET"], endpoint="view_transaction")
@login_required
# @permission_required("manage_ledger")  # Commented out
def view_transaction(id):
    """عرض تفاصيل العملية"""
    # يمكن إضافة منطق عرض التفاصيل هنا
    return f"تفاصيل العملية رقم {id} - قريباً"

def _parse_dates():
    s_from = request.args.get("from", "").strip()
    s_to = request.args.get("to", "").strip()
    def _parse_one(s, end=False):
        if not s:
            return None
        try:
            if len(s) == 10:
                dt = datetime.strptime(s, "%Y-%m-%d")
                return dt.replace(hour=23, minute=59, second=59, microsecond=999999) if end else dt.replace(hour=0, minute=0, second=0, microsecond=0)
            return datetime.fromisoformat(s)
        except Exception:
            return None
    now = datetime.utcnow()
    if not s_from:
        dfrom = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        dfrom = _parse_one(s_from, end=False) or now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if not s_to:
        dto = now
    else:
        dto = _parse_one(s_to, end=True) or now
    dto_excl = dto + timedelta(microseconds=1)
    return dfrom, dto_excl

def _entity_filter(q):
    et = (request.args.get("entity_type") or "").strip()
    eid = request.args.get("entity_id", type=int)
    if et and eid:
        q = q.filter(GLBatch.entity_type == et.upper(), GLBatch.entity_id == eid)
    return q

def _get_pagination():
    page = request.args.get("page", type=int)
    per_page = request.args.get("per_page", type=int)
    if page and page > 0:
        pp = 50 if not per_page else max(1, min(per_page, 200))
        return page, pp
    return None, None

@ledger_bp.get("/trial-balance")
@login_required
# @permission_required("view_reports", "view_ledger")  # Commented out
def trial_balance():
    dfrom, dto = _parse_dates()
    q = (db.session.query(
            GLEntry.account.label("account"),
            func.coalesce(func.sum(GLEntry.debit), 0.0).label("debit"),
            func.coalesce(func.sum(GLEntry.credit), 0.0).label("credit")
        )
        .join(GLBatch, GLBatch.id == GLEntry.batch_id)
        .filter(GLBatch.posted_at >= dfrom, GLBatch.posted_at < dto)
    )
    q = _entity_filter(q)
    rows = q.group_by(GLEntry.account).order_by(GLEntry.account.asc()).all()
    data = []
    for r in rows:
        dr = float(r.debit or 0.0)
        cr = float(r.credit or 0.0)
        net = dr - cr
        side = "DR" if net >= 0 else "CR"
        data.append({"account": r.account, "debit": dr, "credit": cr, "net": abs(net), "side": side})
    return jsonify({"from": dfrom.isoformat(), "to": (dto - timedelta(microseconds=1)).isoformat(), "rows": data})

@ledger_bp.get("/account/<account>")
@login_required
# @permission_required("view_reports", "view_ledger")  # Commented out
def account_ledger(account):
    dfrom, dto = _parse_dates()
    q_open = (db.session.query(func.coalesce(func.sum(GLEntry.debit - GLEntry.credit), 0.0))
              .join(GLBatch, GLBatch.id == GLEntry.batch_id)
              .filter(GLEntry.account == account, GLBatch.posted_at < dfrom))
    q_open = _entity_filter(q_open)
    opening = float(q_open.scalar() or 0.0)
    base = (db.session.query(
                GLBatch.posted_at.label("posted_at"),
                GLBatch.source_type.label("source_type"),
                GLBatch.source_id.label("source_id"),
                GLBatch.purpose.label("purpose"),
                GLBatch.memo.label("memo"),
                GLBatch.entity_type.label("entity_type"),
                GLBatch.entity_id.label("entity_id"),
                GLEntry.debit.label("debit"),
                GLEntry.credit.label("credit"),
                GLEntry.ref.label("ref"),
                GLEntry.id.label("entry_id")
            )
            .join(GLBatch, GLBatch.id == GLEntry.batch_id)
            .filter(GLEntry.account == account, GLBatch.posted_at >= dfrom, GLBatch.posted_at < dto)
            .order_by(GLBatch.posted_at.asc(), GLEntry.id.asc()))
    base = _entity_filter(base)
    page, per_page = _get_pagination()
    if page:
        total = base.count()
        offset = (page - 1) * per_page
        rows = base.limit(per_page).offset(offset).all()
        running_start = opening
        if rows:
            first = rows[0]
            q_prefix = (db.session.query(func.coalesce(func.sum(GLEntry.debit - GLEntry.credit), 0.0))
                        .join(GLBatch, GLBatch.id == GLEntry.batch_id)
                        .filter(GLEntry.account == account,
                                or_(GLBatch.posted_at < first.posted_at,
                                    and_(GLBatch.posted_at == first.posted_at, GLEntry.id < first.entry_id))))
            q_prefix = _entity_filter(q_prefix).filter(GLBatch.posted_at >= dfrom, GLBatch.posted_at < dto)
            running_start += float(q_prefix.scalar() or 0.0)
        running = running_start
        lines = []
        for r in rows:
            dr = float(r.debit or 0.0)
            cr = float(r.credit or 0.0)
            running += (dr - cr)
            lines.append({
                "date": r.posted_at.isoformat(),
                "source": f"{r.source_type}:{r.source_id}",
                "purpose": r.purpose,
                "memo": r.memo,
                "ref": r.ref,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "debit": dr,
                "credit": cr,
                "balance": running
            })
        closing = None
        return jsonify({
            "account": account,
            "from": dfrom.isoformat(),
            "to": (dto - timedelta(microseconds=1)).isoformat(),
            "opening_balance": opening,
            "closing_balance": closing,
            "page": page,
            "per_page": per_page,
            "total": total,
            "lines": lines
        })
    rows = base.all()
    running = opening
    lines = []
    for r in rows:
        dr = float(r.debit or 0.0)
        cr = float(r.credit or 0.0)
        running += (dr - cr)
        lines.append({
            "date": r.posted_at.isoformat(),
            "source": f"{r.source_type}:{r.source_id}",
            "purpose": r.purpose,
            "memo": r.memo,
            "ref": r.ref,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "debit": dr,
            "credit": cr,
            "balance": running
        })
    return jsonify({
        "account": account,
        "from": dfrom.isoformat(),
        "to": (dto - timedelta(microseconds=1)).isoformat(),
        "opening_balance": opening,
        "closing_balance": running,
        "lines": lines
    })

@ledger_bp.get("/entity")
@login_required
# @permission_required("view_reports", "view_ledger")  # Commented out
def entity_ledger():
    dfrom, dto = _parse_dates()
    et = (request.args.get("entity_type") or "").upper().strip()
    eid = request.args.get("entity_id", type=int)
    if not (et and eid):
        return jsonify({"error": "entity_type & entity_id مطلوبان"}), 400
    base = (db.session.query(
                GLBatch.posted_at.label("posted_at"),
                GLBatch.source_type.label("source_type"),
                GLBatch.source_id.label("source_id"),
                GLBatch.purpose.label("purpose"),
                GLBatch.memo.label("memo"),
                GLEntry.account.label("account"),
                GLEntry.debit.label("debit"),
                GLEntry.credit.label("credit"),
                GLEntry.ref.label("ref"),
                GLEntry.id.label("entry_id")
            )
            .join(GLBatch, GLBatch.id == GLEntry.batch_id)
            .filter(GLBatch.entity_type == et, GLBatch.entity_id == eid,
                    GLBatch.posted_at >= dfrom, GLBatch.posted_at < dto)
            .order_by(GLBatch.posted_at.asc(), GLEntry.id.asc()))
    total_dr_q = (db.session.query(func.coalesce(func.sum(GLEntry.debit), 0.0))
                  .join(GLBatch, GLBatch.id == GLEntry.batch_id)
                  .filter(GLBatch.entity_type == et, GLBatch.entity_id == eid,
                          GLBatch.posted_at >= dfrom, GLBatch.posted_at < dto))
    total_cr_q = (db.session.query(func.coalesce(func.sum(GLEntry.credit), 0.0))
                  .join(GLBatch, GLBatch.id == GLEntry.batch_id)
                  .filter(GLBatch.entity_type == et, GLBatch.entity_id == eid,
                          GLBatch.posted_at >= dfrom, GLBatch.posted_at < dto))
    page, per_page = _get_pagination()
    if page:
        total = base.count()
        rows = base.limit(per_page).offset((page - 1) * per_page).all()
        items = []
        for r in rows:
            dr = float(r.debit or 0.0)
            cr = float(r.credit or 0.0)
            items.append({
                "date": r.posted_at.isoformat(),
                "source": f"{r.source_type}:{r.source_id}",
                "purpose": r.purpose,
                "memo": r.memo,
                "account": r.account,
                "debit": dr,
                "credit": cr,
                "ref": r.ref
            })
        return jsonify({
            "entity_type": et,
            "entity_id": eid,
            "from": dfrom.isoformat(),
            "to": (dto - timedelta(microseconds=1)).isoformat(),
            "total_debit": float(total_dr_q.scalar() or 0.0),
            "total_credit": float(total_cr_q.scalar() or 0.0),
            "page": page,
            "per_page": per_page,
            "total": total,
            "lines": items
        })
    rows = base.all()
    total_dr = float(total_dr_q.scalar() or 0.0)
    total_cr = float(total_cr_q.scalar() or 0.0)
    items = []
    for r in rows:
        dr = float(r.debit or 0.0)
        cr = float(r.credit or 0.0)
        items.append({
            "date": r.posted_at.isoformat(),
            "source": f"{r.source_type}:{r.source_id}",
            "purpose": r.purpose,
            "memo": r.memo,
            "account": r.account,
            "debit": dr,
            "credit": cr,
            "ref": r.ref
        })
    return jsonify({
        "entity_type": et,
        "entity_id": eid,
        "from": dfrom.isoformat(),
        "to": (dto - timedelta(microseconds=1)).isoformat(),
        "total_debit": total_dr,
        "total_credit": total_cr,
        "lines": items
    })
