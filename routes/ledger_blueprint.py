
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template, current_app
from flask_login import login_required
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, and_, or_, desc
from extensions import db
import utils
from models import (
    Sale, Expense, Payment, ServiceRequest, 
    Customer, Supplier, Partner,
    Product, StockLevel, GLBatch, GLEntry, Account,
    Invoice, PreOrder, Shipment, Employee,
    PaymentEntityType
)

csrf = CSRFProtect()

ledger_bp = Blueprint("ledger", __name__, url_prefix="/ledger")


def extract_entity_from_batch(batch: GLBatch):
    """
    🧠 دالة ذكية لاستخراج الجهة المرتبطة من القيد المحاسبي
    
    تستخرج الجهة من:
    1. entity_type و entity_id إذا كانا موجودين
    2. source_type و source_id للبحث في الجداول الأصلية
    3. التحليل الذكي للمدفوعات والمبيعات والفواتير
    
    Returns:
        tuple: (entity_name, entity_type_ar, entity_id, entity_type_code)
    """
    # محاولة 1: استخدام entity_type و entity_id المباشرة
    if batch.entity_type and batch.entity_id:
        entity_type = batch.entity_type.upper()
        entity_id = batch.entity_id
        
        try:
            if entity_type == 'CUSTOMER':
                customer = db.session.get(Customer, entity_id)
                if customer:
                    return (customer.name, 'عميل', customer.id, 'CUSTOMER')
            
            elif entity_type == 'SUPPLIER':
                supplier = db.session.get(Supplier, entity_id)
                if supplier:
                    return (supplier.name, 'مورد', supplier.id, 'SUPPLIER')
            
            elif entity_type == 'PARTNER':
                partner = db.session.get(Partner, entity_id)
                if partner:
                    return (partner.name, 'شريك', partner.id, 'PARTNER')
            
            elif entity_type == 'EMPLOYEE':
                employee = db.session.get(Employee, entity_id)
                if employee:
                    return (employee.name, 'موظف', employee.id, 'EMPLOYEE')
        except Exception as e:
            current_app.logger.warning(f"⚠️ خطأ في استخراج الجهة من entity_type: {e}")
    
    # محاولة 2: استخراج من source_type و source_id
    if batch.source_type and batch.source_id:
        source_type = batch.source_type.upper()
        source_id = batch.source_id
        
        try:
            # PAYMENT - استخراج من الدفعة
            if source_type == 'PAYMENT':
                payment = db.session.get(Payment, source_id)
                if payment:
                    if payment.customer_id:
                        customer = db.session.get(Customer, payment.customer_id)
                        if customer:
                            return (customer.name, 'عميل', customer.id, 'CUSTOMER')
                    
                    elif payment.supplier_id:
                        supplier = db.session.get(Supplier, payment.supplier_id)
                        if supplier:
                            return (supplier.name, 'مورد', supplier.id, 'SUPPLIER')
                    
                    elif payment.partner_id:
                        partner = db.session.get(Partner, payment.partner_id)
                        if partner:
                            return (partner.name, 'شريك', partner.id, 'PARTNER')
            
            # SALE - استخراج من المبيعة
            elif source_type == 'SALE':
                sale = db.session.get(Sale, source_id)
                if sale and sale.customer_id:
                    customer = db.session.get(Customer, sale.customer_id)
                    if customer:
                        return (customer.name, 'عميل', customer.id, 'CUSTOMER')
            
            # INVOICE - استخراج من الفاتورة
            elif source_type == 'INVOICE':
                invoice = db.session.get(Invoice, source_id)
                if invoice:
                    if invoice.customer_id:
                        customer = db.session.get(Customer, invoice.customer_id)
                        if customer:
                            return (customer.name, 'عميل', customer.id, 'CUSTOMER')
                    elif invoice.supplier_id:
                        supplier = db.session.get(Supplier, invoice.supplier_id)
                        if supplier:
                            return (supplier.name, 'مورد', supplier.id, 'SUPPLIER')
            
            # EXPENSE - استخراج من المصروف
            elif source_type == 'EXPENSE':
                expense = db.session.get(Expense, source_id)
                if expense:
                    if expense.employee_id:
                        employee = db.session.get(Employee, expense.employee_id)
                        if employee:
                            return (employee.name, 'موظف', employee.id, 'EMPLOYEE')
                    elif expense.partner_id:
                        partner = db.session.get(Partner, expense.partner_id)
                        if partner:
                            return (partner.name, 'شريك', partner.id, 'PARTNER')
                    elif expense.paid_to:
                        return (expense.paid_to, 'جهة', None, 'OTHER')
                    elif expense.payee_name:
                        return (expense.payee_name, 'جهة', None, 'OTHER')
            
            # SERVICE - استخراج من طلب الصيانة
            elif source_type == 'SERVICE':
                service = db.session.get(ServiceRequest, source_id)
                if service and service.customer_id:
                    customer = db.session.get(Customer, service.customer_id)
                    if customer:
                        return (customer.name, 'عميل', customer.id, 'CUSTOMER')
            
            # PREORDER - استخراج من الطلب المسبق
            elif source_type == 'PREORDER':
                preorder = db.session.get(PreOrder, source_id)
                if preorder:
                    if preorder.customer_id:
                        customer = db.session.get(Customer, preorder.customer_id)
                        if customer:
                            return (customer.name, 'عميل', customer.id, 'CUSTOMER')
                    elif preorder.supplier_id:
                        supplier = db.session.get(Supplier, preorder.supplier_id)
                        if supplier:
                            return (supplier.name, 'مورد', supplier.id, 'SUPPLIER')
            
            # SHIPMENT - استخراج من الشحنة
            elif source_type == 'SHIPMENT':
                shipment = db.session.get(Shipment, source_id)
                if shipment and shipment.supplier_id:
                    supplier = db.session.get(Supplier, shipment.supplier_id)
                    if supplier:
                        return (supplier.name, 'مورد', supplier.id, 'SUPPLIER')
                        
        except Exception as e:
            current_app.logger.warning(f"⚠️ خطأ في استخراج الجهة من source_type {source_type}: {e}")
    
    # لا توجد جهة مرتبطة
    return ('—', '', None, None)

@ledger_bp.route("/", methods=["GET"], endpoint="index")
@login_required
# @permission_required("manage_ledger")  # Commented out
def ledger_index():
    """صفحة الدفتر الرئيسية"""
    return render_template("ledger/index.html")

@ledger_bp.route("/chart-of-accounts", methods=["GET"], endpoint="chart_of_accounts")
@login_required
def chart_of_accounts():
    """دليل الحسابات المحاسبية - واجهة مبسطة"""
    return render_template("ledger/chart_of_accounts.html")

@ledger_bp.route("/accounts", methods=["GET"], endpoint="get_accounts")
@login_required
def get_accounts():
    """API: جلب جميع الحسابات المحاسبية"""
    try:
        accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
        
        accounts_list = []
        for acc in accounts:
            accounts_list.append({
                'id': acc.id,
                'code': acc.code,
                'name': acc.name,
                'type': acc.type,
                'is_active': acc.is_active
            })
        
        return jsonify({
            'success': True,
            'accounts': accounts_list,
            'total': len(accounts_list)
        })
    except Exception as e:
        current_app.logger.error(f"خطأ في جلب الحسابات: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@ledger_bp.route("/manual-entry", methods=["POST"], endpoint="create_manual_entry")
@login_required
def create_manual_entry():
    """إنشاء قيد يدوي (Manual Journal Entry)"""
    try:
        from flask_login import current_user
        from decimal import Decimal
        
        data = request.get_json()
        
        # استخراج البيانات
        entry_date = data.get('date')
        amount = Decimal(str(data.get('amount', 0)))
        description = data.get('description', '').strip()
        debit_account = data.get('debit_account', '').strip()
        credit_account = data.get('credit_account', '').strip()
        
        # التحقق
        if not all([entry_date, amount, description, debit_account, credit_account]):
            return jsonify({'success': False, 'error': 'جميع الحقول مطلوبة'}), 400
        
        if amount <= 0:
            return jsonify({'success': False, 'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400
        
        if debit_account == credit_account:
            return jsonify({'success': False, 'error': 'لا يمكن أن يكون الحساب نفسه في الطرفين'}), 400
        
        # التحقق من وجود الحسابات
        debit_acc = Account.query.filter_by(code=debit_account, is_active=True).first()
        credit_acc = Account.query.filter_by(code=credit_account, is_active=True).first()
        
        if not debit_acc or not credit_acc:
            return jsonify({'success': False, 'error': 'حساب غير صحيح أو غير نشط'}), 400
        
        # إنشاء GLBatch
        from datetime import datetime
        posted_at = datetime.strptime(entry_date, '%Y-%m-%d')
        
        ref_number = f"MAN-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        # استخدام timestamp كـ source_id فريد لكل قيد يدوي
        unique_source_id = int(datetime.now().timestamp() * 1000)
        
        batch = GLBatch(
            source_type='MANUAL',
            source_id=unique_source_id,
            purpose='MANUAL_ENTRY',
            posted_at=posted_at,
            currency='ILS',
            memo=description,
            status='POSTED',
            entity_type=None,
            entity_id=None
        )
        db.session.add(batch)
        db.session.flush()
        
        # إنشاء GLEntry - المدين
        entry_debit = GLEntry(
            batch_id=batch.id,
            account=debit_account,
            debit=amount,
            credit=0,
            currency='ILS',
            ref=ref_number
        )
        db.session.add(entry_debit)
        
        # إنشاء GLEntry - الدائن
        entry_credit = GLEntry(
            batch_id=batch.id,
            account=credit_account,
            debit=0,
            credit=amount,
            currency='ILS',
            ref=ref_number
        )
        db.session.add(entry_credit)
        
        db.session.commit()
        
        current_app.logger.info(f"✅ تم إنشاء قيد يدوي: {description} - {amount} ₪")
        
        return jsonify({
            'success': True,
            'message': 'تم حفظ القيد اليدوي بنجاح',
            'batch_id': batch.id,
            'batch_code': batch.code
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"❌ خطأ في إنشاء قيد يدوي: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@ledger_bp.route("/data", methods=["GET"], endpoint="get_ledger_data")
@login_required
# @permission_required("manage_ledger")  # Commented out
def get_ledger_data():
    """جلب بيانات دفتر الأستاذ من قاعدة البيانات الحقيقية"""
    try:
        from models import fx_rate
        
        from_date_str = request.args.get('from_date')
        to_date_str = request.args.get('to_date')
        transaction_type = request.args.get('transaction_type', '').strip()
        
        # تحليل التواريخ
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d') if from_date_str else None
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if to_date_str else None
        
        ledger_entries = []
        running_balance = 0.0
        
        # 0. الرصيد الافتتاحي لجميع العملاء/الموردين/الشركاء
        if not transaction_type or transaction_type == 'opening':
            opening_total = 0.0
            
            # جمع الرصيد الافتتاحي للعملاء
            customers_opening = db.session.query(
                func.coalesce(func.sum(Customer.opening_balance), 0)
            ).scalar() or 0
            opening_total += float(customers_opening)
            
            # جمع الرصيد الافتتاحي للموردين
            suppliers_opening = db.session.query(
                func.coalesce(func.sum(Supplier.opening_balance), 0)
            ).scalar() or 0
            opening_total += float(suppliers_opening)
            
            # جمع الرصيد الافتتاحي للشركاء
            partners_opening = db.session.query(
                func.coalesce(func.sum(Partner.opening_balance), 0)
            ).scalar() or 0
            opening_total += float(partners_opening)
            
            if opening_total != 0:
                # موجب = له علينا → دائن
                # سالب = عليه لنا → مدين
                if opening_total < 0:  # سالب = عليه = مدين
                    debit_val = abs(opening_total)
                    credit_val = 0.0
                    running_balance += abs(opening_total)
                else:  # موجب = له = دائن
                    debit_val = 0.0
                    credit_val = opening_total
                    running_balance -= opening_total
                
                opening_date = from_date.strftime('%Y-%m-%d') if from_date else '2024-01-01'
                ledger_entries.append({
                    "id": 0,
                    "date": opening_date,
                    "transaction_number": "OPENING-BALANCE",
                    "type": "opening",
                    "type_ar": "رصيد افتتاحي",
                    "description": f"الرصيد الافتتاحي الإجمالي (عملاء + موردين + شركاء)",
                    "debit": debit_val,
                    "credit": credit_val,
                    "balance": running_balance,
                    "entity_name": "—",
                    "entity_type": ""
                })
        
        # 1. المخزون الحالي - يُعرض دائماً بغض النظر عن الفترة
        if True:  # نعرض المخزون دائماً
            # حساب قيمة المخزون كقيد افتتاحي
            total_stock_value = 0.0
            total_stock_qty = 0
            
            # جلب المخزون مجمّع حسب المنتج
            stock_summary = (
                db.session.query(
                    Product.id,
                    Product.name,
                    Product.price,
                    Product.currency,
                    func.sum(StockLevel.quantity).label('total_qty')
                )
                .join(StockLevel, StockLevel.product_id == Product.id)
                .filter(StockLevel.quantity > 0)
                .group_by(Product.id, Product.name, Product.price, Product.currency)
                .all()
            )
            
            for row in stock_summary:
                qty = float(row.total_qty or 0)
                price = float(row.price or 0)
                product_currency = row.currency
                
                # تحويل للشيقل - استخدام تاريخ اليوم دائماً
                if product_currency and product_currency != 'ILS' and price > 0:
                    try:
                        rate = fx_rate(product_currency, 'ILS', datetime.utcnow(), raise_on_missing=False)
                        if rate and rate > 0:
                            price = float(price * float(rate))
                    except Exception:
                        pass
                
                total_stock_value += qty * price
                total_stock_qty += int(qty)
            
            if total_stock_value > 0:
                running_balance += total_stock_value
                # استخدام التاريخ الأقدم أو اليوم
                stock_date = from_date.strftime('%Y-%m-%d') if from_date else datetime.utcnow().strftime('%Y-%m-%d')
                ledger_entries.append({
                    "id": 0,
                    "date": stock_date,
                    "transaction_number": "STOCK-VALUE",
                    "type": "opening",
                    "type_ar": "قيمة المخزون",
                    "description": f"قيمة المخزون الحالي ({total_stock_qty} قطعة من {len(stock_summary)} منتج)",
                    "debit": total_stock_value,
                    "credit": 0.0,
                    "balance": running_balance,
                    "entity_name": "—",
                    "entity_type": ""
                })
        
        # 1. المبيعات (Sales)
        if not transaction_type or transaction_type == 'sale':
            sales_query = Sale.query.filter(Sale.status == 'CONFIRMED')
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
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود: {sale.currency}/ILS في المبيعات #{sale.id} - استخدام المبلغ الأصلي")
                    except Exception as e:
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
                    "balance": running_balance,
                    "entity_name": customer_name,
                    "entity_type": "عميل"
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
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود: {expense.currency}/ILS في المصروف #{expense.id} - استخدام المبلغ الأصلي")
                    except Exception as e:
                        current_app.logger.error(f"❌ خطأ في تحويل العملة للمصروف #{expense.id}: {str(e)}")
                running_balance -= credit
                
                exp_type = expense.type.name if expense.type else "مصروف"
                
                # تحديد الجهة المرتبطة بالمصروف
                expense_entity_name = "غير محدد"
                expense_entity_type = ""
                if expense.employee:
                    expense_entity_name = expense.employee.name
                    expense_entity_type = "موظف"
                elif expense.partner:
                    expense_entity_name = expense.partner.name
                    expense_entity_type = "شريك"
                elif expense.paid_to:
                    expense_entity_name = expense.paid_to
                    expense_entity_type = "جهة"
                elif expense.payee_name:
                    expense_entity_name = expense.payee_name
                    expense_entity_type = "جهة"
                
                ledger_entries.append({
                    "id": expense.id,
                    "date": expense.date.strftime('%Y-%m-%d'),
                    "transaction_number": f"EXP-{expense.id}",
                    "type": "expense",
                    "type_ar": exp_type,
                    "description": expense.description or f"مصروف - {exp_type}",
                    "debit": 0.0,
                    "credit": credit,
                    "balance": running_balance,
                    "entity_name": expense_entity_name,
                    "entity_type": expense_entity_type
                })
        
        # 3. الدفعات (Payments)
        if not transaction_type or transaction_type == 'payment':
            # ✅ إضافة الشيكات المعطلة والمرتدة للتوثيق
            payments_query = Payment.query.filter(
                Payment.status.in_(['COMPLETED', 'PENDING', 'BOUNCED', 'FAILED', 'REJECTED'])
            )
            if from_date:
                payments_query = payments_query.filter(Payment.payment_date >= from_date)
            if to_date:
                payments_query = payments_query.filter(Payment.payment_date <= to_date)
            
            for payment in payments_query.order_by(Payment.payment_date).all():
                from models import fx_rate as get_fx_rate
                
                # ✅ فحص حالة الدفعة
                payment_status = getattr(payment, 'status', 'COMPLETED')
                is_bounced = payment_status in ['BOUNCED', 'FAILED', 'REJECTED']
                is_pending = payment_status == 'PENDING'
                
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
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود: {payment.currency}/ILS في الدفعة #{payment.id} - استخدام المبلغ الأصلي")
                    except Exception as e:
                        current_app.logger.error(f"❌ خطأ في تحويل العملة للدفعة #{payment.id}: {str(e)}")
                
                # تحديد الاتجاه - الشيكات المرتدة تعكس القيد
                if is_bounced:
                    # الشيك المرتد = زي increase في الرصيد للمدين (نفس الفاتورة/البيع)
                    # يعتمد على الاتجاه الأصلي
                    if payment.direction == 'OUT':
                        debit = amount  # عكس: كان دائن، صار مدين
                        credit = 0.0
                        running_balance += debit
                    else:
                        credit = amount  # عكس: كان مدين، صار دائن
                        debit = 0.0
                        running_balance -= credit
                elif payment.direction == 'OUT':
                    credit = amount
                    debit = 0.0
                    running_balance -= credit
                else:
                    debit = amount
                    credit = 0.0
                    running_balance += debit
                
                # 🧠 استخراج الجهة بذكاء باستخدام الدالة الذكية
                # إنشاء GLBatch وهمي لاستخدام دالة extract_entity_from_batch
                temp_batch = GLBatch(
                    source_type='PAYMENT',
                    source_id=payment.id,
                    entity_type=None,
                    entity_id=None
                )
                entity_name, entity_type, _, _ = extract_entity_from_batch(temp_batch)
                if payment.entity_type:
                    et_raw = (payment.entity_type or '').upper()
                    try:
                        entity_enum = PaymentEntityType(et_raw)
                    except Exception:
                        entity_enum = None
                    if entity_enum == PaymentEntityType.EXPENSE:
                        if payment.customer_id:
                            customer = db.session.get(Customer, payment.customer_id)
                            if customer:
                                entity_name = customer.name
                                entity_type = 'عميل'
                        elif payment.supplier_id:
                            supplier = db.session.get(Supplier, payment.supplier_id)
                            if supplier:
                                entity_name = supplier.name
                                entity_type = 'مورد'
                        elif payment.partner_id:
                            partner = db.session.get(Partner, payment.partner_id)
                            if partner:
                                entity_name = partner.name
                                entity_type = 'شريك'
                
                # ✅ بناء الوصف مع تفاصيل الشيك
                method_value = getattr(payment, 'method', 'cash')
                if hasattr(method_value, 'value'):
                    method_value = method_value.value
                method_raw = str(method_value).lower()
                
                description_parts = []
                if payment.entity_type and payment.entity_type.upper() == "EXPENSE":
                    extra_parts = []
                    if payment.reference:
                        extra_parts.append(payment.reference)
                    if getattr(payment, "notes", ""):
                        extra_parts.append(payment.notes)
                    if payment.expense_id:
                        expense = db.session.get(Expense, payment.expense_id)
                        if expense:
                            expense_type = getattr(expense.type, "name", "") if getattr(expense, "type", None) else ""
                            if expense_type:
                                extra_parts.append(f"نوع المصروف: {expense_type}")
                            elif expense.description:
                                extra_parts.append(expense.description)
                    extra_text = " | ".join([p for p in extra_parts if p])
                    if extra_text:
                        description_parts.append(f"مصروف: {extra_text}")
                else:
                    description_parts.append(f"دفعة - {entity_name}")
                
                # ✅ إضافة تفاصيل الشيك
                if method_raw == 'cheque':
                    check_number = getattr(payment, 'check_number', None)
                    check_bank = getattr(payment, 'check_bank', None)
                    check_due_date = getattr(payment, 'check_due_date', None)
                    
                    if check_number:
                        description_parts.append(f"شيك #{check_number}")
                    else:
                        description_parts.append("شيك")
                    
                    if check_bank:
                        description_parts.append(f"- {check_bank}")
                    
                    if check_due_date:
                        # datetime مستورد في أعلى الملف
                        if isinstance(check_due_date, datetime):
                            check_due_date_str = check_due_date.strftime('%Y-%m-%d')
                        else:
                            check_due_date_str = str(check_due_date)
                        description_parts.append(f"استحقاق: {check_due_date_str}")
                    
                    # ✅ إضافة حالة الشيك
                    if is_bounced:
                        description_parts.append("- ❌ مرتد")
                    elif is_pending:
                        description_parts.append("- ⏳ معلق")
                else:
                    # ✅ طريقة الدفع بالعربي
                    method_arabic = {
                        'cash': 'نقداً',
                        'card': 'بطاقة',
                        'bank': 'تحويل بنكي',
                        'online': 'إلكتروني'
                    }.get(method_raw, method_raw)
                    description_parts.append(f"({method_arabic})")
                
                if payment.reference:
                    description_parts.append(f"- {payment.reference}")
                if getattr(payment, "notes", ""):
                    description_parts.append(f"- {payment.notes}")
                
                description = " ".join(description_parts)
                
                # ✅ تحديد نوع القيد حسب الحالة
                if is_bounced:
                    entry_type = "check_bounced"
                    type_ar = "شيك مرتد"
                elif is_pending and method_raw == 'cheque':
                    entry_type = "check_pending"
                    type_ar = "شيك معلق"
                else:
                    entry_type = "payment"
                    type_ar = "دفعة"
                
                ledger_entries.append({
                    "id": payment.id,
                    "date": payment.payment_date.strftime('%Y-%m-%d'),
                    "transaction_number": f"PAY-{payment.id}",
                    "type": entry_type,
                    "type_ar": type_ar,
                    "description": description,
                    "debit": debit,
                    "credit": credit,
                    "balance": running_balance,
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "payment_details": {
                        "method": method_raw,
                        "check_number": getattr(payment, 'check_number', None),
                        "check_bank": getattr(payment, 'check_bank', None),
                        "check_due_date": getattr(payment, 'check_due_date', None),
                        "status": payment_status
                    }
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
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود: {service_currency}/ILS في الخدمة #{service.id}")
                    except Exception as e:
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
                    "balance": running_balance,
                    "entity_name": customer_name,
                    "entity_type": "عميل"
                })
        
        # 5. القيود اليدوية (Manual Journal Entries)
        if not transaction_type or transaction_type in ['manual', 'journal']:
            manual_batches_query = GLBatch.query.filter(GLBatch.source_type == 'MANUAL')
            if from_date:
                manual_batches_query = manual_batches_query.filter(GLBatch.posted_at >= from_date)
            if to_date:
                manual_batches_query = manual_batches_query.filter(GLBatch.posted_at <= to_date)
            
            for batch in manual_batches_query.order_by(GLBatch.posted_at).all():
                # 🧠 استخراج الجهة المرتبطة بذكاء
                entity_name, entity_type_ar, entity_id_extracted, entity_type_code = extract_entity_from_batch(batch)
                
                # جلب القيود الفرعية لهذا القيد
                entries = GLEntry.query.filter_by(batch_id=batch.id).all()
                
                for entry in entries:
                    debit = float(entry.debit or 0)
                    credit = float(entry.credit or 0)
                    
                    if debit > 0:
                        running_balance += debit
                    else:
                        running_balance -= credit
                    
                    # جلب اسم الحساب
                    account = Account.query.filter_by(code=entry.account).first()
                    account_name = account.name if account else f"حساب {entry.account}"
                    
                    ledger_entries.append({
                        "id": f"MANUAL-{batch.id}-{entry.id}",
                        "date": batch.posted_at.strftime('%Y-%m-%d'),
                        "transaction_number": f"MAN-{batch.id}",
                        "type": "manual",
                        "type_ar": "قيد يدوي",
                        "description": f"{batch.memo} - {account_name}",
                        "debit": debit,
                        "credit": credit,
                        "balance": running_balance,
                        "entity_name": entity_name,  # ✅ استخدام الجهة المستخرجة بذكاء
                        "entity_type": entity_type_ar,  # ✅ استخدام نوع الجهة بالعربي
                        "manual_details": {
                            "batch_id": batch.id,
                            "account_code": entry.account,
                            "account_name": account_name,
                            "ref": entry.ref
                        }
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
        sales_query = Sale.query.filter(Sale.status == 'CONFIRMED')
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
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في إحصائيات دفتر الأستاذ: {sale.currency}/ILS للبيع #{sale.id}")
                except Exception as e:
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
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في إحصائيات دفتر الأستاذ: {expense.currency}/ILS للمصروف #{expense.id}")
                except Exception as e:
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
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في إحصائيات دفتر الأستاذ: {service_currency}/ILS للخدمة #{service.id}")
                except Exception as e:
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
        
        # 6. حساب الحجوزات المسبقة
        from models import PreOrder
        
        preorders_query = PreOrder.query
        if from_date:
            preorders_query = preorders_query.filter(PreOrder.created_at >= from_date)
        if to_date:
            preorders_query = preorders_query.filter(PreOrder.created_at <= to_date)
        
        total_preorders = 0.0
        for preorder in preorders_query.all():
            amount = float(preorder.total_amount or 0)
            preorder_currency = getattr(preorder, 'currency', 'ILS') or 'ILS'
            if preorder_currency != 'ILS':
                try:
                    rate = fx_rate(preorder_currency, 'ILS', preorder.created_at or datetime.utcnow(), raise_on_missing=False)
                    if rate > 0:
                        amount = float(amount * float(rate))
                except Exception as e:
                    current_app.logger.warning(f"⚠️ خطأ في تحويل عملة الحجز المسبق #{preorder.id}: {str(e)}")
            total_preorders += amount
        
        # 7. حساب قيمة المخزون (مجمّع حسب المنتج)
        total_stock_value_stats = 0.0
        total_stock_qty_stats = 0
        
        stock_summary_stats = (
            db.session.query(
                Product.id,
                Product.name,
                Product.price,
                Product.currency,
                func.sum(StockLevel.quantity).label('total_qty')
            )
            .join(StockLevel, StockLevel.product_id == Product.id)
            .filter(StockLevel.quantity > 0)
            .group_by(Product.id, Product.name, Product.price, Product.currency)
            .all()
        )
        
        for row in stock_summary_stats:
            qty = float(row.total_qty or 0)
            price = float(row.price or 0)
            product_currency = row.currency
            
            # تحويل للشيقل
            if product_currency and product_currency != 'ILS' and price > 0:
                try:
                    rate = fx_rate(product_currency, 'ILS', datetime.utcnow(), raise_on_missing=False)
                    if rate and rate > 0:
                        price = float(price * float(rate))
                except Exception:
                    pass
            
            total_stock_value_stats += qty * price
            total_stock_qty_stats += int(qty)
        
        # 8. صافي الربح الحقيقي
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
            "total_preorders": total_preorders,
            "total_stock_value": total_stock_value_stats,
            "total_stock_qty": total_stock_qty_stats,
            "cogs_details": cogs_details,
            "estimated_products_count": len(estimated_products),
            "estimated_products": estimated_products,
            "products_without_cost_count": len(products_without_cost),
            "products_without_cost": products_without_cost
        }
        
        # حساب إجماليات البيانات (لدفتر الأستاذ)
        ledger_totals = {
            'total_debit': sum([entry['debit'] for entry in ledger_entries]),
            'total_credit': sum([entry['credit'] for entry in ledger_entries]),
            'final_balance': ledger_entries[-1]['balance'] if ledger_entries else 0
        }
        
        return jsonify({
            "data": ledger_entries,
            "statistics": statistics,
            "totals": ledger_totals
        })
        
    except Exception as e:
        import traceback
        current_app.logger.error(f"Error in get_ledger_data: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e), "data": [], "statistics": {}}), 500

@ledger_bp.route("/accounts-summary", methods=["GET"], endpoint="get_accounts_summary")
@login_required
# @permission_required("manage_ledger")  # Commented out
def get_accounts_summary():
    """جلب ملخص الحسابات (ميزان المراجعة)"""
    try:
        from models import fx_rate
        
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
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في ميزان المراجعة: {sale.currency}/ILS للبيع #{sale.id}")
                except Exception as e:
                    current_app.logger.error(f"❌ خطأ في تحويل العملة في ميزان المراجعة للبيع #{sale.id}: {str(e)}")
            total_sales += amount
        
        accounts.append({
            "name": "المبيعات",
            "debit_balance": 0.0,
            "credit_balance": total_sales
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
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في ميزان المراجعة: {service_currency}/ILS للخدمة #{service.id}")
                except Exception as e:
                    current_app.logger.error(f"❌ خطأ في تحويل العملة في ميزان المراجعة للخدمة #{service.id}: {str(e)}")
            
            total_services += service_total
        
        accounts.append({
            "name": "الخدمات (الصيانة)",
            "debit_balance": 0.0,
            "credit_balance": total_services
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
            "debit_balance": total_cogs,
            "credit_balance": 0.0
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
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في ميزان المراجعة: {expense.currency}/ILS للمصروف #{expense.id}")
                except Exception as e:
                    current_app.logger.error(f"❌ خطأ في تحويل العملة في ميزان المراجعة للمصروف #{expense.id}: {str(e)}")
            total_expenses += amount
        
        accounts.append({
            "name": "المشتريات والنفقات",
            "debit_balance": total_expenses,
            "credit_balance": 0.0
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
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في حساب الخزينة: {payment.currency}/ILS للدفعة #{payment.id}")
                except Exception as e:
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
                        current_app.logger.warning(f"⚠️ سعر صرف مفقود في حساب الخزينة: {payment.currency}/ILS للدفعة #{payment.id}")
                except Exception as e:
                    current_app.logger.error(f"❌ خطأ في تحويل العملة في حساب الخزينة للدفعة #{payment.id}: {str(e)}")
            total_payments_out += amount
        
        accounts.append({
            "name": "الخزينة",
            "debit_balance": total_payments_in,
            "credit_balance": total_payments_out
        })
        
        # 4. حساب المخزون مجمّع حسب المنتج
        total_stock_value = 0.0
        total_stock_qty = 0
        
        stock_summary = (
            db.session.query(
                Product.id,
                Product.name,
                Product.price,
                Product.currency,
                func.sum(StockLevel.quantity).label('total_qty')
            )
            .join(StockLevel, StockLevel.product_id == Product.id)
            .filter(StockLevel.quantity > 0)
            .group_by(Product.id, Product.name, Product.price, Product.currency)
            .all()
        )
        
        for row in stock_summary:
            qty = float(row.total_qty or 0)
            price = float(row.price or 0)
            product_currency = row.currency
            
            # تحويل للشيقل - استخدام تاريخ اليوم دائماً
            if product_currency and product_currency != 'ILS' and price > 0:
                try:
                    rate = fx_rate(product_currency, 'ILS', datetime.utcnow(), raise_on_missing=False)
                    if rate and rate > 0:
                        price = float(price * float(rate))
                except Exception:
                    pass
            
            total_stock_value += qty * price
            total_stock_qty += int(qty)
        
        accounts.append({
            "name": "المخزون",
            "debit_balance": total_stock_value,
            "credit_balance": 0.0,
            "quantity": total_stock_qty,
            "note": f"قيمة {total_stock_qty} قطعة"
        })
        
        # حساب إجماليات ميزان المراجعة من الباكند
        accounts_totals = {
            'total_debit': sum([acc['debit_balance'] for acc in accounts]),
            'total_credit': sum([acc['credit_balance'] for acc in accounts]),
            'net_balance': sum([acc['debit_balance'] for acc in accounts]) - sum([acc['credit_balance'] for acc in accounts])
        }
        
        return jsonify({
            'accounts': accounts,
            'totals': accounts_totals
        })
        
    except Exception as e:
        import traceback
        error_msg = f"Error in get_accounts_summary: {str(e)}"
        current_app.logger.error(error_msg)
        current_app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

@ledger_bp.route("/receivables-detailed-summary", methods=["GET"], endpoint="get_receivables_detailed_summary")
@login_required
# @permission_required("manage_ledger")  # Commented out
def get_receivables_detailed_summary():
    """جلب ملخص الذمم التفصيلي مع أعمار الديون"""
    try:
        from_date_str = request.args.get('from_date')
        to_date_str = request.args.get('to_date')
        
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d') if from_date_str else None
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if to_date_str else None
        
        receivables = []
        today = datetime.utcnow()
        
        # 1. العملاء (Customers) مع أعمار الديون
        from models import fx_rate
        
        customers = Customer.query.all()
        for customer in customers:
            from decimal import Decimal
            from models import convert_amount, SaleReturn, PreOrder, OnlinePreOrder, ServiceRequest, Invoice
            
            total_receivable = Decimal('0.00')
            total_paid = Decimal('0.00')
            oldest_date = None
            last_payment_date = None
            
            sales_query = Sale.query.filter(Sale.customer_id == customer.id, Sale.status == 'CONFIRMED')
            if from_date:
                sales_query = sales_query.filter(Sale.sale_date >= from_date)
            if to_date:
                sales_query = sales_query.filter(Sale.sale_date <= to_date)
            
            for s in sales_query.all():
                amt = Decimal(str(s.total_amount or 0))
                if s.currency == "ILS":
                    total_receivable += amt
                else:
                    try:
                        total_receivable += convert_amount(amt, s.currency, "ILS", s.sale_date)
                    except Exception:
                        pass
                if oldest_date is None or (s.sale_date and s.sale_date < oldest_date):
                    oldest_date = s.sale_date
            
            invoices_query = Invoice.query.filter(Invoice.customer_id == customer.id, Invoice.cancelled_at.is_(None))
            if from_date:
                invoices_query = invoices_query.filter(Invoice.invoice_date >= from_date)
            if to_date:
                invoices_query = invoices_query.filter(Invoice.invoice_date <= to_date)
            
            for inv in invoices_query.all():
                amt = Decimal(str(inv.total_amount or 0))
                if inv.currency == "ILS":
                    total_receivable += amt
                else:
                    try:
                        total_receivable += convert_amount(amt, inv.currency, "ILS", inv.invoice_date)
                    except Exception:
                        pass
                ref_dt = inv.invoice_date or inv.created_at
                if oldest_date is None or (ref_dt and ref_dt < oldest_date):
                    oldest_date = ref_dt
            
            services_query = ServiceRequest.query.filter(ServiceRequest.customer_id == customer.id)
            if from_date:
                services_query = services_query.filter(ServiceRequest.received_at >= from_date)
            if to_date:
                services_query = services_query.filter(ServiceRequest.received_at <= to_date)
            
            for srv in services_query.all():
                amt = Decimal(str(srv.total_amount or 0))
                if srv.currency == "ILS":
                    total_receivable += amt
                else:
                    try:
                        total_receivable += convert_amount(amt, srv.currency, "ILS", srv.received_at)
                    except Exception:
                        pass
                ref_dt = srv.received_at or srv.created_at
                if oldest_date is None or (ref_dt and ref_dt < oldest_date):
                    oldest_date = ref_dt
            
            preorders_query = PreOrder.query.filter(PreOrder.customer_id == customer.id, PreOrder.status != 'CANCELLED')
            if from_date:
                preorders_query = preorders_query.filter(PreOrder.preorder_date >= from_date)
            if to_date:
                preorders_query = preorders_query.filter(PreOrder.preorder_date <= to_date)
            
            for p in preorders_query.all():
                amt = Decimal(str(p.total_amount or 0))
                if p.currency == "ILS":
                    total_receivable += amt
                else:
                    try:
                        total_receivable += convert_amount(amt, p.currency, "ILS", p.preorder_date)
                    except Exception:
                        pass
                ref_dt = p.preorder_date or p.created_at
                if oldest_date is None or (ref_dt and ref_dt < oldest_date):
                    oldest_date = ref_dt
            
            online_orders_query = OnlinePreOrder.query.filter(OnlinePreOrder.customer_id == customer.id, OnlinePreOrder.payment_status != 'CANCELLED')
            if from_date:
                online_orders_query = online_orders_query.filter(OnlinePreOrder.created_at >= from_date)
            if to_date:
                online_orders_query = online_orders_query.filter(OnlinePreOrder.created_at <= to_date)
            
            for oo in online_orders_query.all():
                amt = Decimal(str(oo.total_amount or 0))
                if oo.currency == "ILS":
                    total_receivable += amt
                else:
                    try:
                        total_receivable += convert_amount(amt, oo.currency, "ILS", oo.created_at)
                    except Exception:
                        pass
                if oldest_date is None or (oo.created_at and oo.created_at < oldest_date):
                    oldest_date = oo.created_at
            
            returns_query = SaleReturn.query.filter(SaleReturn.customer_id == customer.id, SaleReturn.status == 'CONFIRMED')
            if from_date:
                returns_query = returns_query.filter(SaleReturn.created_at >= from_date)
            if to_date:
                returns_query = returns_query.filter(SaleReturn.created_at <= to_date)
            
            for r in returns_query.all():
                amt = Decimal(str(r.total_amount or 0))
                if r.currency == "ILS":
                    total_receivable -= amt
                else:
                    try:
                        total_receivable -= convert_amount(amt, r.currency, "ILS", r.created_at)
                    except Exception:
                        pass
            
            payments_in_direct = Payment.query.filter(Payment.customer_id == customer.id, Payment.direction == 'IN', Payment.status.in_(['COMPLETED', 'PENDING']))
            payments_in_from_sales = Payment.query.join(Sale, Payment.sale_id == Sale.id).filter(Sale.customer_id == customer.id, Payment.direction == 'IN', Payment.status.in_(['COMPLETED', 'PENDING']))
            payments_in_from_invoices = Payment.query.join(Invoice, Payment.invoice_id == Invoice.id).filter(Invoice.customer_id == customer.id, Payment.direction == 'IN', Payment.status.in_(['COMPLETED', 'PENDING']))
            payments_in_from_services = Payment.query.join(ServiceRequest, Payment.service_id == ServiceRequest.id).filter(ServiceRequest.customer_id == customer.id, Payment.direction == 'IN', Payment.status.in_(['COMPLETED', 'PENDING']))
            payments_in_from_preorders = Payment.query.join(PreOrder, Payment.preorder_id == PreOrder.id).filter(PreOrder.customer_id == customer.id, Payment.direction == 'IN', Payment.status.in_(['COMPLETED', 'PENDING']))
            payments_out_direct = Payment.query.filter(Payment.customer_id == customer.id, Payment.direction == 'OUT', Payment.status.in_(['COMPLETED', 'PENDING']))
            payments_out_from_sales = Payment.query.join(Sale, Payment.sale_id == Sale.id).filter(Sale.customer_id == customer.id, Payment.direction == 'OUT', Payment.status.in_(['COMPLETED', 'PENDING']))
            
            if from_date:
                payments_in_direct = payments_in_direct.filter(Payment.payment_date >= from_date)
                payments_in_from_sales = payments_in_from_sales.filter(Payment.payment_date >= from_date)
                payments_in_from_invoices = payments_in_from_invoices.filter(Payment.payment_date >= from_date)
                payments_in_from_services = payments_in_from_services.filter(Payment.payment_date >= from_date)
                payments_in_from_preorders = payments_in_from_preorders.filter(Payment.payment_date >= from_date)
                payments_out_direct = payments_out_direct.filter(Payment.payment_date >= from_date)
                payments_out_from_sales = payments_out_from_sales.filter(Payment.payment_date >= from_date)
            if to_date:
                payments_in_direct = payments_in_direct.filter(Payment.payment_date <= to_date)
                payments_in_from_sales = payments_in_from_sales.filter(Payment.payment_date <= to_date)
                payments_in_from_invoices = payments_in_from_invoices.filter(Payment.payment_date <= to_date)
                payments_in_from_services = payments_in_from_services.filter(Payment.payment_date <= to_date)
                payments_in_from_preorders = payments_in_from_preorders.filter(Payment.payment_date <= to_date)
                payments_out_direct = payments_out_direct.filter(Payment.payment_date <= to_date)
                payments_out_from_sales = payments_out_from_sales.filter(Payment.payment_date <= to_date)
            
            seen_payment_ids = set()
            payments_all = []
            for p in (payments_in_direct.all() + payments_in_from_sales.all() + payments_in_from_invoices.all() + payments_in_from_services.all() + payments_in_from_preorders.all() + payments_out_direct.all() + payments_out_from_sales.all()):
                if p.id not in seen_payment_ids:
                    seen_payment_ids.add(p.id)
                    payments_all.append(p)
            
            for p in payments_all:
                amt = Decimal(str(p.total_amount or 0))
                if p.currency == "ILS":
                    converted = amt
                else:
                    try:
                        converted = convert_amount(amt, p.currency, "ILS", p.payment_date)
                    except Exception:
                        continue
                
                if p.direction == 'IN':
                    total_paid += converted
                elif p.direction == 'OUT':
                    total_paid -= converted
                
                if not last_payment_date or (p.payment_date and p.payment_date > last_payment_date):
                    last_payment_date = p.payment_date
            
            balance = total_receivable - total_paid
            if balance == 0:
                continue
            
            days_overdue = 0
            if balance > 0 and oldest_date:
                days_overdue = (today - oldest_date).days
            
            last_transaction = last_payment_date if last_payment_date else oldest_date
            last_transaction_str = last_transaction.strftime('%Y-%m-%d') if last_transaction else None
            
            receivables.append({
                "name": customer.name,
                "type": "customer",
                "type_ar": "عميل",
                "debit": float(total_receivable),
                "credit": float(total_paid),
                "days_overdue": days_overdue,
                "last_transaction": last_transaction_str
            })
        
        # 2. الموردين (Suppliers) مع أعمار الديون
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
            oldest_expense_date = None
            
            for expense in expenses_query.all():
                amount = float(expense.amount or 0)
                if expense.currency and expense.currency != 'ILS':
                    try:
                        rate = fx_rate(expense.currency, 'ILS', expense.date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                    except Exception:
                        pass
                total_purchases += amount
                
                if not oldest_expense_date or expense.date < oldest_expense_date:
                    oldest_expense_date = expense.date
            
            # حساب الدفعات للمورد
            payments_query = Payment.query.filter(
                Payment.supplier_id == supplier.id,
                Payment.direction == 'OUT',
                Payment.status == 'COMPLETED'
            )
            if from_date:
                payments_query = payments_query.filter(Payment.payment_date >= from_date)
            if to_date:
                payments_query = payments_query.filter(Payment.payment_date <= to_date)
            
            total_payments = 0.0
            last_payment_date = None
            
            for payment in payments_query.all():
                amount = float(payment.total_amount or 0)
                if payment.currency and payment.currency != 'ILS':
                    try:
                        rate = fx_rate(payment.currency, 'ILS', payment.payment_date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                    except Exception:
                        pass
                total_payments += amount
                
                if not last_payment_date or payment.payment_date > last_payment_date:
                    last_payment_date = payment.payment_date
            
            # حساب عمر الدين
            days_overdue = 0
            if total_purchases > total_payments and oldest_expense_date:
                days_overdue = (today - oldest_expense_date).days
            
            # آخر حركة
            last_transaction = last_payment_date if last_payment_date else oldest_expense_date
            last_transaction_str = last_transaction.strftime('%Y-%m-%d') if last_transaction else None
            
            if total_purchases > 0 or total_payments > 0:
                receivables.append({
                    "name": supplier.name,
                    "type": "supplier",
                    "type_ar": "مورد",
                    "debit": total_payments,
                    "credit": total_purchases,
                    "days_overdue": days_overdue,
                    "last_transaction": last_transaction_str
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
            oldest_expense_date = None
            
            for expense in expenses_query.all():
                amount = float(expense.amount or 0)
                if expense.currency and expense.currency != 'ILS':
                    try:
                        rate = fx_rate(expense.currency, 'ILS', expense.date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                    except Exception:
                        pass
                total_expenses += amount
                
                if not oldest_expense_date or expense.date < oldest_expense_date:
                    oldest_expense_date = expense.date
            
            # حساب الدفعات من/إلى الشريك
            payments_in_query = Payment.query.filter(
                Payment.partner_id == partner.id,
                Payment.direction == 'IN',
                Payment.status == 'COMPLETED'
            )
            payments_out_query = Payment.query.filter(
                Payment.partner_id == partner.id,
                Payment.direction == 'OUT',
                Payment.status == 'COMPLETED'
            )
            
            if from_date:
                payments_in_query = payments_in_query.filter(Payment.payment_date >= from_date)
                payments_out_query = payments_out_query.filter(Payment.payment_date >= from_date)
            if to_date:
                payments_in_query = payments_in_query.filter(Payment.payment_date <= to_date)
                payments_out_query = payments_out_query.filter(Payment.payment_date <= to_date)
            
            total_in = 0.0
            total_out = 0.0
            last_payment_date = None
            
            for payment in payments_in_query.all():
                amount = float(payment.total_amount or 0)
                if payment.currency and payment.currency != 'ILS':
                    try:
                        rate = fx_rate(payment.currency, 'ILS', payment.payment_date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                    except Exception:
                        pass
                total_in += amount
                
                if not last_payment_date or payment.payment_date > last_payment_date:
                    last_payment_date = payment.payment_date
            
            for payment in payments_out_query.all():
                amount = float(payment.total_amount or 0)
                if payment.currency and payment.currency != 'ILS':
                    try:
                        rate = fx_rate(payment.currency, 'ILS', payment.payment_date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                    except Exception:
                        pass
                total_out += amount
                
                if not last_payment_date or payment.payment_date > last_payment_date:
                    last_payment_date = payment.payment_date
            
            # حساب عمر الدين
            days_overdue = 0
            balance = (total_in + total_expenses) - total_out
            if balance > 0 and oldest_expense_date:
                days_overdue = (today - oldest_expense_date).days
            
            # آخر حركة
            last_transaction = last_payment_date if last_payment_date else oldest_expense_date
            last_transaction_str = last_transaction.strftime('%Y-%m-%d') if last_transaction else None
            
            if total_in > 0 or total_out > 0 or total_expenses > 0:
                receivables.append({
                    "name": partner.name,
                    "type": "partner",
                    "type_ar": "شريك",
                    "debit": total_in + total_expenses,
                    "credit": total_out,
                    "days_overdue": days_overdue,
                    "last_transaction": last_transaction_str
                })
        
        # حساب إجماليات الذمم من الباكند
        receivables_totals = {
            'total_debit': sum([r['debit'] for r in receivables]),
            'total_credit': sum([r['credit'] for r in receivables]),
            'net_balance': sum([r['debit'] for r in receivables]) - sum([r['credit'] for r in receivables])
        }
        
        return jsonify({
            'receivables': receivables,
            'totals': receivables_totals
        })
        
    except Exception as e:
        import traceback
        current_app.logger.error(f"Error in get_receivables_detailed_summary: {str(e)}")
        current_app.logger.error(traceback.format_exc())
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
            sales_query = Sale.query.filter(
                Sale.customer_id == customer.id,
                Sale.status == 'CONFIRMED'
            )
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
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم: {sale.currency}/ILS للبيع #{sale.id}")
                    except Exception as e:
                        current_app.logger.error(f"❌ خطأ في تحويل العملة في ملخص الذمم للبيع #{sale.id}: {str(e)}")
                total_sales += amount
            
            # حساب الدفعات من العميل
            payments_query = Payment.query.filter(
                Payment.customer_id == customer.id,
                Payment.direction == 'IN',
                Payment.status == 'COMPLETED'  # ✅ فلترة الدفعات المكتملة فقط
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
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم: {payment.currency}/ILS للدفعة #{payment.id}")
                    except Exception as e:
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
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم (موردين): {expense.currency}/ILS للمصروف #{expense.id}")
                    except Exception as e:
                        current_app.logger.error(f"❌ خطأ في تحويل العملة في ملخص الذمم (موردين) للمصروف #{expense.id}: {str(e)}")
                total_purchases += amount
            
            # حساب الدفعات للمورد
            payments_query = Payment.query.filter(
                Payment.supplier_id == supplier.id,
                Payment.direction == 'OUT',
                Payment.status == 'COMPLETED'
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
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم (موردين): {payment.currency}/ILS للدفعة #{payment.id}")
                    except Exception as e:
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
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم (شركاء): {expense.currency}/ILS للمصروف #{expense.id}")
                    except Exception as e:
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
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم (شركاء): {payment.currency}/ILS للدفعة #{payment.id}")
                    except Exception as e:
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
                            current_app.logger.warning(f"⚠️ سعر صرف مفقود في ملخص الذمم (شركاء): {payment.currency}/ILS للدفعة #{payment.id}")
                    except Exception as e:
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
            
            # 🧠 استخراج الجهة بذكاء من batch
            batch_obj = GLBatch(
                source_type=r.source_type,
                source_id=r.source_id,
                entity_type=r.entity_type,
                entity_id=r.entity_id
            )
            entity_name, entity_type_ar, _, _ = extract_entity_from_batch(batch_obj)
            
            lines.append({
                "date": r.posted_at.isoformat(),
                "source": f"{r.source_type}:{r.source_id}",
                "purpose": r.purpose,
                "memo": r.memo,
                "ref": r.ref,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "entity_name": entity_name,  # ✅ إضافة اسم الجهة
                "entity_type_ar": entity_type_ar,  # ✅ إضافة نوع الجهة بالعربي
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
        
        # 🧠 استخراج الجهة بذكاء من batch
        batch_obj = GLBatch(
            source_type=r.source_type,
            source_id=r.source_id,
            entity_type=r.entity_type,
            entity_id=r.entity_id
        )
        entity_name, entity_type_ar, _, _ = extract_entity_from_batch(batch_obj)
        
        lines.append({
            "date": r.posted_at.isoformat(),
            "source": f"{r.source_type}:{r.source_id}",
            "purpose": r.purpose,
            "memo": r.memo,
            "ref": r.ref,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "entity_name": entity_name,  # ✅ إضافة اسم الجهة
            "entity_type_ar": entity_type_ar,  # ✅ إضافة نوع الجهة بالعربي
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
    
    # 🧠 الحصول على اسم الجهة
    entity_name = "—"
    if et == 'CUSTOMER':
        customer = db.session.get(Customer, eid)
        entity_name = customer.name if customer else f"عميل #{eid}"
    elif et == 'SUPPLIER':
        supplier = db.session.get(Supplier, eid)
        entity_name = supplier.name if supplier else f"مورد #{eid}"
    elif et == 'PARTNER':
        partner = db.session.get(Partner, eid)
        entity_name = partner.name if partner else f"شريك #{eid}"
    elif et == 'EMPLOYEE':
        employee = db.session.get(Employee, eid)
        entity_name = employee.name if employee else f"موظف #{eid}"
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
            "entity_name": entity_name,  # ✅ إضافة اسم الجهة
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
        "entity_name": entity_name,  # ✅ إضافة اسم الجهة
        "from": dfrom.isoformat(),
        "to": (dto - timedelta(microseconds=1)).isoformat(),
        "total_debit": total_dr,
        "total_credit": total_cr,
        "lines": items
    })


@ledger_bp.route("/batch/<int:batch_id>", methods=["GET"], endpoint="get_batch_details")
@login_required
# @permission_required("manage_ledger")  # Commented out
def get_batch_details(batch_id):
    """جلب تفاصيل قيد محاسبي (GLBatch + Entries)"""
    try:
        # جلب القيد
        batch = GLBatch.query.get(batch_id)
        if not batch:
            return jsonify({"success": False, "error": "القيد غير موجود"}), 404
        
        # 🧠 استخراج الجهة المرتبطة بذكاء
        entity_name, entity_type_ar, entity_id_extracted, entity_type_code = extract_entity_from_batch(batch)
        
        # جلب القيود الفرعية
        entries = GLEntry.query.filter_by(batch_id=batch_id).all()
        
        entries_list = []
        for entry in entries:
            account = Account.query.filter_by(code=entry.account).first()
            entries_list.append({
                "account_code": entry.account,
                "account_name": account.name if account else entry.account,
                "debit": float(entry.debit or 0),
                "credit": float(entry.credit or 0),
                "ref": entry.ref
            })
        
        return jsonify({
            "success": True,
            "batch": {
                "id": batch.id,
                "code": batch.code,
                "source_type": batch.source_type,
                "source_id": batch.source_id,
                "purpose": batch.purpose,
                "memo": batch.memo,
                "posted_at": batch.posted_at.isoformat() if batch.posted_at else None,
                "currency": batch.currency,
                "status": batch.status,
                "entity_name": entity_name,  # ✅ إضافة اسم الجهة
                "entity_type": entity_type_ar,  # ✅ إضافة نوع الجهة بالعربي
                "entity_id": entity_id_extracted,  # ✅ إضافة معرف الجهة
                "entity_type_code": entity_type_code  # ✅ إضافة كود نوع الجهة
            },
            "entries": entries_list,
            "total_debit": sum(e["debit"] for e in entries_list),
            "total_credit": sum(e["credit"] for e in entries_list)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
