# File: routes/customers.py

import csv
import io
import json
import re
import decimal
from decimal import Decimal
from datetime import datetime
from functools import wraps
from dateutil.relativedelta import relativedelta

from flask import (
    Blueprint, flash, jsonify, redirect,
    render_template, request, Response,
    url_for, abort, current_app
)
from flask_login import current_user, login_required
from sqlalchemy import or_, func
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from extensions import db
from forms import CustomerForm, CustomerImportForm, ExportContactsForm
from models import (
    Customer, AuditLog, Invoice,
    Payment, Sale, SaleLine,
    Product, ProductCategory
)
from utils import (
    permission_required, send_whatsapp_message,
    generate_pdf_report, generate_excel_report,
    generate_vcf, generate_csv_contacts,
    generate_excel_contacts
)

customers_bp = Blueprint(
    'customers_bp', __name__,
    url_prefix='/customers',
    template_folder='templates/customers'
)

def _get_or_404(model, ident, *options):
    if options:
        q = db.session.query(model)
        for opt in options:
            q = q.options(opt)
        obj = q.filter_by(id=ident).first()
    else:
        obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

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

# ---------------------- Helpers ----------------------
def _serialize_dates(d):
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in d.items()}

from datetime import datetime as _dt

def log_customer_action(cust, action, old_data=None, new_data=None):
    old_json = json.dumps(old_data, ensure_ascii=False) if old_data else None
    new_json = json.dumps(new_data, ensure_ascii=False, cls=CustomEncoder) if new_data else None
    entry = AuditLog(
        timestamp   = _dt.utcnow(),
        model_name  = 'Customer',
        customer_id = cust.id,
        record_id   = cust.id,
        user_id     = current_user.id if getattr(current_user, 'is_authenticated', False) else None,
        action      = action,
        old_data    = old_json,
        new_data    = new_json,
        ip_address  = request.remote_addr,
        user_agent  = request.headers.get('User-Agent'),
    )
    db.session.add(entry)
    db.session.flush()

# ---------------------- List / Detail / Analytics ----------------------
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

    page     = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    pagination = q.order_by(Customer.id.desc()).paginate(page=page, per_page=per_page, error_out=False)

    args = request.args.to_dict(flat=True)
    args.pop('page', None)

    if not pagination.items:
        flash("⚠️ لا توجد بيانات لعرضها", "info")
        return render_template('customers/list.html', customers=[], pagination=pagination, args=args)

    return render_template('customers/list.html', customers=pagination.items, pagination=pagination, args=args)

@customers_bp.route('/<int:customer_id>', methods=['GET'], endpoint='customer_detail')
@login_required
@permission_required('manage_customers')
def customer_detail(customer_id):
    customer = db.session.get(Customer, customer_id) or abort(404)
    return render_template('customers/detail.html', customer=customer)

@customers_bp.route('/<int:customer_id>/analytics', methods=['GET'], endpoint='customer_analytics')
@login_required
@permission_required('manage_customers')
def customer_analytics(customer_id):
    customer = db.session.get(Customer, customer_id) or abort(404)

    invoices = Invoice.query.filter_by(customer_id=customer_id).all()
    payments = Payment.query.filter_by(customer_id=customer_id).all()

    total_purchases = sum((inv.total_amount or Decimal('0')) for inv in invoices)
    total_payments  = sum((p.total_amount   or Decimal('0')) for p   in payments)
    avg_purchase    = (total_purchases / len(invoices)) if invoices else Decimal('0')

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
        .filter(Sale.customer_id == customer_id)
        .group_by(ProductCategory.name)
        .all()
    )
    purchase_categories = [
        {
            'name': name,
            'count': count,
            'total': total,
            'percentage': (float(total) / float(total_purchases) * 100.0) if total_purchases else 0.0
        }
        for name, count, total in cats
    ]

    today  = datetime.utcnow()
    months = [(today - relativedelta(months=i)).strftime('%Y-%m') for i in reversed(range(6))]

    pm = {m: Decimal('0') for m in months}
    for inv in invoices:
        if inv.invoice_date:
            m = inv.invoice_date.strftime('%Y-%m')
            if m in pm:
                pm[m] += (inv.total_amount or Decimal('0'))
    purchases_months = [{'month': m, 'total': float(pm[m])} for m in months]

    paym = {m: Decimal('0') for m in months}
    for p in payments:
        if getattr(p, 'payment_date', None):
            m = p.payment_date.strftime('%Y-%m')
            if m in paym:
                paym[m] += (p.total_amount or Decimal('0'))
    payments_months = [{'month': m, 'total': float(paym[m])} for m in months]

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

# ---------------------- Create / Edit / Delete ----------------------
@customers_bp.route('/create', methods=['GET'], endpoint='create_form')
@login_required
@permission_required('manage_customers')
def create_form():
    form = CustomerForm()
    return render_template('customers/new.html', form=form)

@customers_bp.route('/create', methods=['POST'], endpoint='create_customer')
@login_required
@permission_required('manage_customers')
def create_customer():
    form = CustomerForm()
    if not form.validate_on_submit():
        current_app.logger.warning("CustomerForm errors: %s", form.errors)
        if form.errors:
            msgs = '; '.join(f"{k}: {', '.join(v)}" for k, v in form.errors.items())
            flash(f"تحقق من الحقول: {msgs}", "warning")
        return render_template('customers/new.html', form=form), 400

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
    if getattr(form, 'password', None) and form.password.data:
        cust.set_password(form.password.data)

    db.session.add(cust)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('بريد أو هاتف مكرر (Unique constraint).', 'danger')
        current_app.logger.exception("IntegrityError while creating customer")
        return render_template('customers/new.html', form=form), 409
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ أثناء إضافة العميل: {e}', 'danger')
        current_app.logger.exception("SQLAlchemyError while creating customer")
        return render_template('customers/new.html', form=form), 500

    log_customer_action(cust, 'CREATE', None, form.data)
    flash('تم إنشاء العميل بنجاح', 'success')
    return redirect(url_for('customers_bp.list_customers'))

@customers_bp.route('/<int:customer_id>/edit', methods=['GET', 'POST'], endpoint='edit_customer')
@login_required
@permission_required('manage_customers')
def edit_customer(customer_id):
    cust = db.session.get(Customer, customer_id) or abort(404)
    form = CustomerForm(obj=cust)

    if request.method == 'POST':
        if form.validate_on_submit():
            old = cust.to_dict() if hasattr(cust, 'to_dict') else None
            if getattr(form, 'password', None) and form.password.data:
                cust.set_password(form.password.data)
            cust.name           = form.name.data
            cust.phone          = form.phone.data
            cust.email          = form.email.data
            cust.address        = form.address.data
            cust.whatsapp       = form.whatsapp.data
            cust.category       = form.category.data
            cust.credit_limit   = form.credit_limit.data or 0
            cust.discount_rate  = form.discount_rate.data or 0
            cust.is_active      = form.is_active.data
            cust.is_online      = form.is_online.data
            cust.notes          = form.notes.data

            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('بريد أو هاتف مكرر (Unique constraint).', 'danger')
                current_app.logger.exception("IntegrityError while editing customer")
                return render_template('customers/edit.html', form=form, customer=cust), 409
            except SQLAlchemyError as e:
                db.session.rollback()
                flash(f'❌ خطأ أثناء تعديل العميل: {e}', 'danger')
                current_app.logger.exception("SQLAlchemyError while editing customer")
                return render_template('customers/edit.html', form=form, customer=cust), 500

            log_customer_action(cust, 'UPDATE', old, cust.to_dict() if hasattr(cust, 'to_dict') else None)
            flash('تم تعديل بيانات العميل', 'success')
            return redirect(url_for('customers_bp.customer_detail', customer_id=customer_id))

        current_app.logger.warning("CustomerForm errors (edit): %s", form.errors)
        if form.errors:
            msgs = '; '.join(f"{k}: {', '.join(v)}" for k, v in form.errors.items())
            flash(f"تحقق من الحقول: {msgs}", "warning")
        return render_template('customers/edit.html', form=form, customer=cust), 400

    return render_template('customers/edit.html', form=form, customer=cust)

@customers_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('manage_customers')
def delete_customer(id):
    customer = db.session.get(Customer, id) or abort(404)
    if getattr(customer, 'invoices', None) or getattr(customer, 'payments', None):
        flash("لا يمكن حذف العميل لأنه مرتبط بفواتير أو دفعات.", "danger")
        return redirect(url_for("customers_bp.list_customers"))
    try:
        db.session.delete(customer)
        db.session.commit()
        flash("تم حذف العميل", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"❌ خطأ أثناء حذف العميل: {e}", "danger")
    return redirect(url_for("customers_bp.list_customers"))

# ---------------------- Import ----------------------
@customers_bp.route('/import', methods=['GET', 'POST'], endpoint='import_customers')
@login_required
@permission_required('manage_customers')
def import_customers():
    form = CustomerImportForm()
    if request.method == 'GET' or not form.validate_on_submit():
        return render_template('customers/import.html', form=form)

    file_data = form.csv_file.data.read().decode('utf-8')
    reader = csv.DictReader(io.StringIO(file_data))
    count, errors = 0, []

    for i, row in enumerate(reader, 1):
        try:
            name  = (row.get('name') or '').strip()
            phone = (row.get('phone') or '').strip()
            email = (row.get('email') or '').strip()
            if not name or not phone or not email:
                raise ValueError("حقول مطلوبة مفقودة: name / phone / email")

            if len(phone) > 20:
                raise ValueError("الهاتف يجب ألا يتجاوز 20 خانة")
            whatsapp = (row.get('whatsapp') or '').strip()
            if len(whatsapp) > 20:
                raise ValueError("واتساب يجب ألا يتجاوز 20 خانة")
            address = (row.get('address') or '').strip()
            if len(address) > 200:
                raise ValueError("العنوان يجب ألا يتجاوز 200 خانة")
            notes = (row.get('notes') or '').strip()
            if len(notes) > 500:
                raise ValueError("الملاحظات يجب ألا تتجاوز 500 خانة")

            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                raise ValueError("صيغة البريد الإلكتروني غير صحيحة")

            category = (row.get('category') or 'عادي').strip()
            if category not in ('عادي', 'فضي', 'ذهبي', 'مميز'):
                category = 'عادي'

            credit_limit_raw  = (row.get('credit_limit') or '').strip()
            discount_rate_raw = (row.get('discount_rate') or '').strip()
            credit_limit = float(credit_limit_raw) if credit_limit_raw else 0.0
            if credit_limit < 0:
                raise ValueError("حد الائتمان يجب أن يكون ≥ 0")
            discount_rate = float(discount_rate_raw) if discount_rate_raw else 0.0
            if not (0.0 <= discount_rate <= 100.0):
                raise ValueError("معدل الخصم يجب أن يكون بين 0 و100")

            if Customer.query.filter(or_(
                Customer.phone == phone,
                Customer.email == email
            )).first():
                raise ValueError("هاتف أو بريد مستخدم مسبقًا")

            is_active = str(row.get('is_active', 'True')).strip().lower() in ('true','1','yes','y','on')

            c = Customer(
                name=name,
                phone=phone,
                email=email,
                address=address,
                whatsapp=whatsapp,
                category=category,
                credit_limit=credit_limit,
                discount_rate=discount_rate,
                is_active=is_active,
                notes=notes
            )
            if row.get('password'):
                c.set_password(row['password'])

            # معاملة متداخلة لكل سجل لمنع إسقاط الدفعة كاملة عند أول خطأ
            with db.session.begin_nested():
                db.session.add(c)
                db.session.flush()
                log_customer_action(c, "IMPORT", None, row)
                count += 1

        except IntegrityError:
            db.session.rollback()
            errors.append(f"سطر {i}: قيمة مكررة (Unique).")
        except Exception as e:
            db.session.rollback()
            errors.append(f"سطر {i}: {e}")

    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        errors.append(f"فشل حفظ الدفعة: {e}")

    flash(f'تم استيراد {count} عميل', 'success')
    if errors:
        flash('; '.join(errors), 'warning')
    return redirect(url_for('customers_bp.list_customers'))

# ---------------------- Messaging ----------------------
@customers_bp.route('/<int:customer_id>/send_whatsapp', methods=['GET'], endpoint='customer_whatsapp')
@login_required
@permission_required('manage_customers')
def customer_whatsapp(customer_id):
    c = db.session.get(Customer, customer_id) or abort(404)
    if c.whatsapp:
        send_whatsapp_message(c.whatsapp, f"رصيدك الحالي: {getattr(c, 'balance', 0):,.2f}")
        flash('تم إرسال رسالة واتساب', 'success')
    else:
        flash('لا يوجد رقم واتساب للعميل', 'warning')
    return redirect(url_for('customers_bp.customer_detail', customer_id=customer_id))

# ---------------------- VCF (single) ----------------------
@customers_bp.route('/<int:customer_id>/export_vcf', methods=['GET'], endpoint='export_customer_vcf')
@login_required
@permission_required('manage_customers')
def export_customer_vcf(customer_id):
    c = db.session.get(Customer, customer_id) or abort(404)
    safe_name = re.sub(r'[^A-Za-z0-9_.-]+', '_', (c.name or 'contact')).strip('_') or 'contact'
    vcf = (
        "BEGIN:VCARD\r\nVERSION:3.0\r\n"
        f"FN:{c.name}\r\n"
        f"TEL:{c.phone or ''}\r\n"
        f"EMAIL:{c.email or ''}\r\n"
        "END:VCARD\r\n"
    )
    return Response(
        vcf,
        mimetype='text/vcard; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={safe_name}.vcf'}
    )

# ---------------------- Account Statement ----------------------
@customers_bp.route('/<int:customer_id>/account_statement', methods=['GET'], endpoint='account_statement')
@login_required
@permission_required('manage_customengers')
def account_statement(customer_id):
    c = db.session.get(Customer, customer_id) or abort(404)
    invoices = Invoice.query.filter_by(customer_id=customer_id).order_by(Invoice.invoice_date).all()
    payments = Payment.query.filter_by(customer_id=customer_id).order_by(Payment.payment_date).all()

    total_inv = sum((inv.total_amount or Decimal('0')) for inv in invoices)
    total_pay = sum((p.total_amount   or Decimal('0')) for p   in payments)
    balance   = total_inv - total_pay

    return render_template(
        'customers/account_statement.html',
        customer=c,
        invoices=invoices,
        payments=payments,
        total_invoices=total_inv,
        total_payments=total_pay,
        balance=balance
    )

# ---------------------- API ----------------------
@customers_bp.route('/api/all', methods=['GET'], endpoint='api_customers')
@login_required
@permission_required('manage_customers')
def api_customers():
    q = Customer.query
    if term := request.args.get('q'):
        q = q.filter(or_(
            Customer.name.ilike(f"%{term}%"),
            Customer.phone.ilike(f"%{term}%")
        ))
    pagination = q.order_by(Customer.name).paginate(
        page=request.args.get('page', 1, type=int),
        per_page=request.args.get('per_page', 20, type=int),
        error_out=False
    )
    return jsonify({
        'results': [{'id': c.id, 'text': c.name} for c in pagination.items],
        'pagination': {'more': pagination.has_next}
    })

# ---------------------- Advanced Filter ----------------------
@customers_bp.route('/advanced_filter', methods=['GET'], endpoint='advanced_filter')
@login_required
@permission_required('manage_customers')
def advanced_filter():
    q = Customer.query
    if balance_min := request.args.get('balance_min'):
        q = q.filter(Customer.balance >= float(balance_min))
    if balance_max := request.args.get('balance_max'):
        q = q.filter(Customer.balance <= float(balance_max))

    # تواريخ بصيغة ISO
    if created_at_min := request.args.get('created_at_min'):
        try:
            q = q.filter(Customer.created_at >= datetime.fromisoformat(created_at_min))
        except ValueError:
            pass
    if created_at_max := request.args.get('created_at_max'):
        try:
            q = q.filter(Customer.created_at <= datetime.fromisoformat(created_at_max))
        except ValueError:
            pass
    if last_activity_min := request.args.get('last_activity_min'):
        try:
            q = q.filter(Customer.last_activity >= datetime.fromisoformat(last_activity_min))
        except ValueError:
            pass
    if last_activity_max := request.args.get('last_activity_max'):
        try:
            q = q.filter(Customer.last_activity <= datetime.fromisoformat(last_activity_max))
        except ValueError:
            pass

    if category := request.args.get('category'):
        q = q.filter(Customer.category == category)
    if status := request.args.get('status'):
        if status == 'active':
            q = q.filter(Customer.is_active.is_(True))
        elif status == 'inactive':
            q = q.filter(Customer.is_active.is_(False))
        elif status == 'credit_hold':
            q = q.filter(Customer.balance > Customer.credit_limit)

    pagination = q.order_by(Customer.id.desc()).paginate(
        page=request.args.get('page', 1, type=int),
        per_page=request.args.get('per_page', 20, type=int),
        error_out=False
    )
    customers = pagination.items

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

    return render_template('customers/advanced_filter.html', customers=customers, pagination=pagination)

# ---------------------- Export Reports ----------------------
@customers_bp.route('/export', methods=['GET'], endpoint='export_customers')
@login_required
@permission_required('manage_customers')
def export_customers():
    format_type = request.args.get('format', 'pdf')
    customers = Customer.query.all()
    if format_type == 'pdf':
        return generate_pdf_report(customers)
    elif format_type == 'excel':
        return generate_excel_report(customers)
    return jsonify([c.to_dict() for c in customers])

# ---------------------- Export Contacts ----------------------
@customers_bp.route('/export/contacts', methods=['GET', 'POST'], endpoint='export_contacts')
@login_required
@permission_required('manage_customers')
def export_contacts():
    form = ExportContactsForm()
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
        else:
            return generate_excel_contacts(customers, fields)

    return render_template(
        'customers/vcf_export.html',
        form=form,
        customers=Customer.query.order_by(Customer.name).all()
    )
