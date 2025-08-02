# File: routes/customers.py

import csv
import io
import json
from datetime import datetime
from functools import wraps
from dateutil.relativedelta import relativedelta

from flask import (
    Blueprint, flash, jsonify, redirect,
    render_template, request, Response,
    url_for, abort
)
from flask_login import current_user, login_required
from sqlalchemy import or_, func
from sqlalchemy.exc import SQLAlchemyError

from extensions import db, mail
from forms import CustomerForm, CustomerImportForm, ExportContactsForm
from models import (
    Customer, AuditLog, Invoice,
    Payment, Sale, SaleLine,
    Product, ProductCategory
)
from utils import (
    permission_required, send_whatsapp_message,
    send_email_notification,
    generate_pdf_report, generate_excel_report,
    generate_vcf, generate_csv_contacts,
    generate_excel_contacts
)

customers_bp = Blueprint(
    'customers', __name__,
    url_prefix='/customers',
    template_folder='templates/customers'
)

# ---------------------- Rate Limiting ----------------------
_last_attempts = {}
def rate_limit(max_attempts=5, window=60):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            ip = request.remote_addr
            now = datetime.utcnow().timestamp()
            attempts = [t for t in _last_attempts.get(ip, []) if now - t < window]
            if len(attempts) >= max_attempts:
                abort(429, "محاولات كثيرة جدًا، حاول لاحقًا.")
            attempts.append(now)
            _last_attempts[ip] = attempts
            return f(*args, **kwargs)
        return wrapper
    return decorator

# ---------------------- Helper Functions ----------------------
def _serialize_dates(d):
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in d.items()}


# ---------------------- Audit Logging ----------------------
def log_customer_action(cust, action, old_data=None, new_data=None):
    if old_data is not None:
        old_data = json.dumps(old_data, ensure_ascii=False)
    if new_data is not None:
        new_data = json.dumps(new_data, ensure_ascii=False)
    entry = AuditLog(
        user_id=current_user.id,
        customer_id=cust.id,
        action=action,
        old_data=old_data,
        new_data=new_data
    )
    db.session.add(entry)
    db.session.commit()

# ---------------------- Routes ----------------------
@customers_bp.route('/', methods=['GET'], endpoint='list_customers')
@login_required
@permission_required('manage_customers')
def list_customers():
    q = Customer.query
    if name := request.args.get('name'):
        q = q.filter(Customer.name.ilike(f"%{name}%"))
    if phone := request.args.get('phone'):
        q = q.filter(Customer.phone.ilike(f"%{phone}%"))
    if category := request.args.get('category'):
        q = q.filter(Customer.category == category)
    if 'is_active' in request.args:
        q = q.filter(Customer.is_active == (request.args.get('is_active') == '1'))

    # pagination parameters
    page     = request.args.get('page',     1,  type=int)
    per_page = request.args.get('per_page', 20, type=int)
    pagination = q.order_by(Customer.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # prepare args without 'page'
    args = request.args.to_dict(flat=True)
    args.pop('page', None)

    return render_template(
        'customers/list.html',
        customers = pagination.items,
        pagination = pagination,
        args = args
    )

@customers_bp.route('/<int:id>', methods=['GET'], endpoint='customer_detail')
@login_required
@permission_required('manage_customers')
def customer_detail(id):
    customer = Customer.query.get_or_404(id)
    return render_template('customers/detail.html', customer=customer)

# ---------------------- Analytics ----------------------
@customers_bp.route('/<int:id>/analytics', methods=['GET'], endpoint='customer_analytics')
@login_required
@permission_required('manage_customers')
def customer_analytics(id):
    customer = Customer.query.get_or_404(id)
    invoices = Invoice.query.filter_by(customer_id=id).all()
    payments = Payment.query.filter_by(customer_id=id).all()

    total_purchases = sum(inv.total_amount for inv in invoices)
    total_payments = sum(p.total_amount for p in payments)
    avg_purchase = (total_purchases / len(invoices)) if invoices else 0

    cats = (
        db.session.query(
            ProductCategory.name.label('name'),
            func.count(SaleLine.id).label('count'),
            func.sum(SaleLine.quantity * SaleLine.unit_price).label('total')
        )
        .select_from(SaleLine)
        .join(Sale, Sale.id == SaleLine.sale_id)
        .join(Product, Product.id == SaleLine.product_id)
        .join(ProductCategory, ProductCategory.id == Product.category_id)
        .filter(Sale.customer_id == id)
        .group_by(ProductCategory.name)
        .all()
    )
    purchase_categories = [
        {
            'name': name,
            'count': count,
            'total': total,
            'percentage': (total / total_purchases * 100) if total_purchases else 0
        }
        for name, count, total in cats
    ]

    today = datetime.utcnow()
    months = [(today - relativedelta(months=i)).strftime('%Y-%m') for i in reversed(range(6))]
    pm = {m: 0 for m in months}
    for inv in invoices:
        m = inv.invoice_date.strftime('%Y-%m')
        if m in pm:
            pm[m] += inv.total_amount
    purchases_months = [{'month': m, 'total': pm[m]} for m in months]

    paym = {m: 0 for m in months}
    for p in payments:
        m = p.payment_date.strftime('%Y-%m')
        if m in paym:
            paym[m] += p.total_amount
    payments_months = [{'month': m, 'total': paym[m]} for m in months]

    return render_template(
        'customers/analytics.html',
        customer=customer,
        total_purchases=total_purchases,
        total_payments=total_payments,
        avg_purchase=avg_purchase,
        purchase_categories=purchase_categories,
        purchases_months=purchases_months,
        payments_months=payments_months
    )

# ---------------------- Create ----------------------
@customers_bp.route('/new', methods=['GET', 'POST'], endpoint='create_customer')
@login_required
@permission_required('manage_customers')
def create_customer():
    form = CustomerForm()
    if form.validate_on_submit():
        cust = Customer(
            name=form.name.data,
            phone=form.phone.data,
            email=form.email.data,
            address=form.address.data,
            whatsapp=form.whatsapp.data,
            category=form.category.data,
            credit_limit=form.credit_limit.data or 0,
            discount_rate=form.discount_rate.data or 0,
            is_active=form.is_active.data,
            is_online=form.is_online.data,
            notes=form.notes.data
        )
        if form.password.data:
            cust.set_password(form.password.data)

        db.session.add(cust)
        try:
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ أثناء إضافة العميل: {e}', 'danger')
            return render_template('customers/new.html', form=form)

        log_customer_action(cust, 'CREATE', None, form.data)
        flash('تمت إضافة العميل بنجاح', 'success')
        return redirect(url_for('customers.list_customers'))

    return render_template('customers/new.html', form=form)

# ---------------------- Edit ----------------------
@customers_bp.route('/<int:id>/edit', methods=['GET', 'POST'], endpoint='edit_customer')
@login_required
@permission_required('manage_customers')
def edit_customer(id):
    cust = Customer.query.get_or_404(id)
    form = CustomerForm(obj=cust)
    if form.validate_on_submit():
        old = cust.to_dict()
        form.populate_obj(cust)
        if form.password.data:
            cust.set_password(form.password.data)
        try:
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ أثناء تعديل العميل: {e}', 'danger')
            return render_template('customers/edit.html', form=form, customer=cust)

        log_customer_action(cust, 'UPDATE', old, cust.to_dict())
        flash('تم تعديل بيانات العميل', 'success')
        return redirect(url_for('customers.customer_detail', id=id))

    return render_template('customers/edit.html', form=form, customer=cust)

# ---------------------- Delete ----------------------
@customers_bp.route('/<int:id>/delete', methods=['POST'], endpoint='delete_customer')
@login_required
@permission_required('manage_customers')
def delete_customer(id):
    cust = Customer.query.get_or_404(id)
    old = cust.to_dict()
    log_customer_action(cust, 'DELETE', old, None)
    db.session.delete(cust)
    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ أثناء حذف العميل: {e}', 'danger')
        return redirect(url_for('customers.list_customers'))

    flash('تم حذف العميل', 'warning')
    return redirect(url_for('customers.list_customers'))

# ---------------------- Import ----------------------
@customers_bp.route('/import', methods=['GET', 'POST'], endpoint='import_customers')
@login_required
@permission_required('manage_customers')
def import_customers():
    form = CustomerImportForm()
    if form.validate_on_submit():
        reader = csv.DictReader(io.StringIO(form.csv_file.data.read().decode('utf-8')))
        count, errors = 0, []
        for i, row in enumerate(reader, 1):
            try:
                c = Customer(
                    name=row['name'], 
                    phone=row.get('phone'), 
                    email=row.get('email'),
                    address=row.get('address'),
                    whatsapp=row.get('whatsapp'),
                    category=row.get('category', 'عادي'),
                    is_active=row.get('is_active', 'True').lower() == 'true',
                    notes=row.get('notes')
                )
                if row.get('password'): c.set_password(row['password'])
                db.session.add(c); db.session.commit()
                log_customer_action(c, "import", None, row); count += 1
            except Exception as e:
                db.session.rollback(); errors.append(f"سطر {i}: {e}")
        flash(f'تم استيراد {count} عميل', 'success')
        if errors: flash('; '.join(errors), 'warning')
        return redirect(url_for('customers.list_customers'))
    return render_template('customers/import.html', form=form)

# ---------------------- WhatsApp Notification ----------------------
@customers_bp.route('/<int:id>/send_whatsapp', methods=['GET'], endpoint='customer_whatsapp')
@login_required
@permission_required('manage_customers')
def customer_whatsapp(id):
    c = Customer.query.get_or_404(id)
    send_whatsapp_message(c.whatsapp, f"رصيدك الحالي: {c.balance:,.2f}")
    flash('تم إرسال رسالة واتساب', 'success')
    return redirect(url_for('customers.customer_detail', id=id))

def export_customers_csv(customers):
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'ID', 'Name', 'Category', 'Balance', 'Credit Limit',
        'Created At', 'Last Activity', 'Status', 'Phone', 'Email'
    ])
    
    # Data
    for c in customers:
        writer.writerow([
            c.id, c.name, c.category, c.balance, c.credit_limit,
            c.created_at, c.last_activity,
            'نشط' if c.is_active else 'غير نشط',
            c.phone, c.email
        ])
    
    response = Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=customers_export.csv'}
    )
    return response

# ---------------------- Export VCF ----------------------
@customers_bp.route('/<int:id>/export_vcf', methods=['GET'], endpoint='export_customer_vcf')
@login_required
@permission_required('manage_customers')
def export_customer_vcf(id):
    c = Customer.query.get_or_404(id)
    vcf = f"BEGIN:VCARD\nVERSION:3.0\nN:{c.name}\nTEL:{c.phone or ''}\nEMAIL:{c.email or ''}\nEND:VCARD"
    return Response(vcf, mimetype='text/vcard', headers={'Content-Disposition': f'attachment; filename={c.name}.vcf'})

# ---------------------- Account Statement ----------------------
@customers_bp.route('/<int:id>/account_statement', methods=['GET'], endpoint='account_statement')
@login_required
@permission_required('manage_customers')
def account_statement(id):
    c = Customer.query.get_or_404(id)

    # جلب الفواتير عن طريق استعلام مستقل (يدعم order_by)
    invoices = Invoice.query \
        .filter_by(customer_id=c.id) \
        .order_by(Invoice.invoice_date) \
        .all()

    # دفعات العميل (بالترتيب الزمني)
    payments = Payment.query \
        .filter_by(customer_id=c.id) \
        .order_by(Payment.payment_date) \
        .all()

    total_inv = sum(inv.total_amount for inv in invoices)
    total_pay = sum(p.total_amount for p in payments)
    balance   = total_inv - total_pay

    return render_template(
        'customers/account_statement.html',
        customer       = c,
        invoices       = invoices,
        payments       = payments,
        total_invoices = total_inv,
        total_payments = total_pay,
        balance        = balance
    )
# ---------------------- API ----------------------
@customers_bp.route('/api/all', methods=['GET'], endpoint='api_customers')
@login_required
@permission_required('manage_customers')
def api_customers():
    q = Customer.query
    if term := request.args.get('q'): q = q.filter(or_(Customer.name.ilike(f"%{term}%"), Customer.phone.ilike(f"%{term}%")))
    pagination = q.order_by(Customer.name).paginate(page=request.args.get('page', 1, type=int), per_page=request.args.get('per_page', 20, type=int), error_out=False)
    return jsonify({'results':[{'id':c.id,'text':c.name} for c in pagination.items],'pagination':{'more':pagination.has_next}})

# ---------------------- Advanced Filter ----------------------
@customers_bp.route('/advanced_filter', methods=['GET'], endpoint='advanced_filter')
@login_required
@permission_required('manage_customers')
def advanced_filter():
    q = Customer.query

    # —————— Apply filters ——————
    if balance_min := request.args.get('balance_min'):
        q = q.filter(Customer.balance >= float(balance_min))
    if balance_max := request.args.get('balance_max'):
        q = q.filter(Customer.balance <= float(balance_max))
    if created_at_min := request.args.get('created_at_min'):
        q = q.filter(Customer.created_at >= created_at_min)
    if created_at_max := request.args.get('created_at_max'):
        q = q.filter(Customer.created_at <= created_at_max)
    if last_activity_min := request.args.get('last_activity_min'):
        q = q.filter(Customer.last_activity >= last_activity_min)
    if last_activity_max := request.args.get('last_activity_max'):
        q = q.filter(Customer.last_activity <= last_activity_max)
    if category := request.args.get('category'):
        q = q.filter(Customer.category == category)
    if status := request.args.get('status'):
        if status == 'active':
            q = q.filter(Customer.is_active == True)
        elif status == 'inactive':
            q = q.filter(Customer.is_active == False)
        elif status == 'credit_hold':
            q = q.filter(Customer.balance > Customer.credit_limit)

    # —————— Pagination (so your template's pagination.pages works) ——————
    pagination = q.order_by(Customer.id.desc()).paginate(
        page=request.args.get('page', 1, type=int),
        per_page=request.args.get('per_page', 20, type=int),
        error_out=False
    )
    customers = pagination.items

    # —————— CSV Export ——————
    if request.args.get('format') == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Name', 'Phone', 'Email', 'Balance', 'Category', 'Status'])
        for c in customers:
            st = 'نشط' if c.is_active else 'غير نشط'
            if c.balance > c.credit_limit:
                st = 'معلق ائتمانيًا'
            writer.writerow([c.id, c.name, c.phone, c.email, c.balance, c.category, st])
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=customers_advanced_filter.csv'}
        )

    # —————— Render template with pagination ——————
    return render_template(
        'customers/advanced_filter.html',
        customers=customers,
        pagination=pagination
    )

# ---------------------- Export Reports ----------------------
@customers_bp.route('/export', methods=['GET'])
def export_customers():
    format_type = request.args.get('format', 'pdf')
    customers = Customer.query.all()
    
    if format_type == 'pdf':
        # توليد PDF باستخدام ReportLab
        return generate_pdf_report(customers)
    elif format_type == 'excel':
        # توليد Excel باستخدام pandas
        return generate_excel_report(customers)
    
    return jsonify([c.to_dict() for c in customers])

@customers_bp.route('/export/contacts', methods=['GET', 'POST'], endpoint='export_contacts')
@login_required
@permission_required('manage_customers')
def export_contacts():
    form = ExportContactsForm()
    # إعداد اختيارات العملاء ديناميكيًا
    form.customer_ids.choices = [
        (c.id, f"{c.name} — {c.phone or ''}")
        for c in Customer.query.order_by(Customer.name).all()
    ]

    if form.validate_on_submit():
        ids    = form.customer_ids.data
        fields = form.fields.data
        fmt    = form.format.data

        customers = Customer.query.filter(Customer.id.in_(ids)).all()
        if fmt == 'vcf':
            return generate_vcf(customers, fields)
        elif fmt == 'csv':
            return generate_csv_contacts(customers, fields)
        else:  # excel
            return generate_excel_contacts(customers, fields)

    # عند GET أو فشل التحقق
    return render_template(
        'customers/vcf_export.html',
        form=form,
        customers=Customer.query.order_by(Customer.name).all()
    )
