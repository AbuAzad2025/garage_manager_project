# File: routes/sales.py

import io, json
from datetime import datetime
from dateutil.relativedelta import relativedelta

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, Response, url_for
from flask_login import current_user, login_required

from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from extensions import db
from models import (
    Sale, SaleLine, Invoice, InvoiceLine,
    Customer, Product, ProductCategory, AuditLog,
    Warehouse, User
)
from forms import SaleForm, SaleLineForm, InvoiceForm, InvoiceLineForm
from utils import permission_required, send_whatsapp_message, generate_pdf_report as generate_invoice_pdf

sales_bp = Blueprint('sales', __name__, url_prefix='/sales', template_folder='templates/sales')

# ========================== الخرائط ==========================
STATUS_MAP = {
    'draft':    ('مسودة', 'bg-warning text-dark'),
    'confirmed':('مؤكدة','bg-primary'),
    'paid':     ('مدفوعة','bg-success'),
    'on_hold':  ('مؤجلة','bg-info'),
    'cancelled':('ملغاة','bg-secondary'),
    'shipped':  ('تم الشحن','bg-info'),
    'delivered':('تم التسليم','bg-success'),
    'returned': ('مرتجعة','bg-danger')
}

PAYMENT_STATUS_MAP = {
    'pending':   ('معلق', 'bg-warning'),
    'completed': ('مكتمل','bg-success'),
    'failed':    ('فشل',  'bg-danger'),
    'refunded':  ('مرتجع','bg-info'),
    'cancelled': ('ملغى', 'bg-secondary')
}

PAYMENT_METHOD_MAP = {
    'cash':           'نقدي',
    'check':          'شيك',
    'credit_card':    'بطاقة ائتمان',
    'bank_transfer':  'تحويل بنكي',
    'mobile_payment': 'دفع جوال'
}

# ========================== دوال مساعدة ==========================
def _format_sale(s: Sale):
    s.balance_formatted = f"{s.balance_due:,.2f}"
    s.customer_name     = s.customer.name if s.customer else '-'
    s.date_iso          = s.date.strftime('%Y-%m-%d') if s.date else '-'
    lbl, cls            = STATUS_MAP.get(s.status, (s.status, ''))
    s.status_label, s.status_class = lbl, cls
    s.total_formatted   = f"{s.total:,.2f}"
    s.seller_name       = s.seller.username if s.seller else '-'

def sale_to_dict(s: Sale):
    return {
        'sale_number': s.sale_number,
        'customer_id': s.customer_id,
        'date': s.date_iso,
        'status': s.status,
        'currency': s.currency,
        'shipping_cost': float(s.shipping_cost or 0),
        'notes': s.notes,
        'lines': [
            {
                'product_id': ln.product_id,
                'warehouse_id': ln.warehouse_id,
                'quantity': ln.quantity,
                'unit_price': float(ln.unit_price),
                'discount_rate': ln.discount_rate,
                'tax_rate': ln.tax_rate
            } for ln in s.lines
        ]
    }

def log_sale_action(s: Sale, action: str, old=None, new=None):
    log = AuditLog(
        model_name='Sale', record_id=s.id, action=action,
        old_data=json.dumps(old, ensure_ascii=False) if old else None,
        new_data=json.dumps(new, ensure_ascii=False) if new else None,
        user_id=current_user.id
    )
    db.session.add(log)
    db.session.commit()

def reserve_stock_for_sale(sale: Sale):
    for line in sale.lines:
        stock = StockLevel.query.filter_by(product_id=line.product_id, warehouse_id=line.warehouse_id).first()
        if not stock or stock.quantity < line.quantity:
            return False
        stock.quantity -= line.quantity
        stock.product.reserved_quantity += line.quantity
    return True

def release_stock_for_sale(sale: Sale):
    for line in sale.lines:
        stock = StockLevel.query.filter_by(product_id=line.product_id, warehouse_id=line.warehouse_id).first()
        if stock:
            stock.quantity += line.quantity
            stock.product.reserved_quantity -= line.quantity

# ✅ دالة جديدة لتوحيد إعداد الخيارات
def populate_sale_form_choices(form):
    form.seller_id.choices   = [(u.id, u.username) for u in User.query.filter_by(is_active=True)]
    form.customer_id.choices = [(c.id, c.name) for c in Customer.query.order_by(Customer.name)]
    form.currency.choices    = [('ILS','شيكل'),('USD','دولار'),('EUR','يورو'),('SAR','ريال')]

# ========================== لوحة تحكم المبيعات ==========================
@sales_bp.route('/dashboard')
@login_required
@permission_required('manage_sales')
def sales_dashboard():
    total_sales   = Sale.query.count()
    total_revenue = db.session.query(func.sum(Sale.total)).scalar() or 0
    pending_sales = Sale.query.filter_by(status='draft').count()

    top_customers = db.session.query(Customer.name, func.sum(Sale.total).label('spent')) \
        .join(Sale).group_by(Customer.id).order_by(desc('spent')).limit(5).all()

    top_products = db.session.query(Product.name,
        func.sum(SaleLine.quantity).label('sold'),
        func.sum(SaleLine.quantity * SaleLine.unit_price).label('revenue')) \
        .join(SaleLine).group_by(Product.id).order_by(desc('sold')).limit(5).all()

    monthly = db.session.query(extract('year', Sale.date).label('y'),
        extract('month', Sale.date).label('m'),
        func.count(Sale.id).label('cnt'),
        func.sum(Sale.total).label('sum')).group_by('y','m').order_by('y','m').all()

    months, counts, revenue = [], [], []
    for rec in monthly:
        months.append(f"{int(rec.m)}/{int(rec.y)}")
        counts.append(rec.cnt)
        revenue.append(float(rec.sum or 0))

    return render_template('sales/dashboard.html',
        total_sales=total_sales, total_revenue=total_revenue,
        pending_sales=pending_sales, top_customers=top_customers,
        top_products=top_products, months=months,
        sales_count=counts, revenue=revenue
    )

# ========================== قائمة المبيعات ==========================
@sales_bp.route('/', endpoint='list_sales')
@login_required
@permission_required('manage_sales')
def list_sales():
    f = request.args

    # subquery لحساب total لكل فاتورة في قاعدة البيانات
    subtotals = (
        db.session.query(
            Sale.id.label('sale_id'),
            func.coalesce(
                func.sum(
                    SaleLine.quantity
                    * SaleLine.unit_price
                    * (1 - SaleLine.discount_rate/100)
                    * (1 + SaleLine.tax_rate/100)
                ),
                0
            ).label('calc_total')
        )
        .join(SaleLine, SaleLine.sale_id == Sale.id)
        .group_by(Sale.id)
        .subquery()
    )

    # الاستعلام الرئيسي مع الربط بالـ subquery
    q = (
        Sale.query
        .options(joinedload(Sale.customer), joinedload(Sale.seller))
        .outerjoin(subtotals, subtotals.c.sale_id == Sale.id)
    )

    # تطبيق الفلاتر
    if (st := f.get('status', 'all')) != 'all':
        q = q.filter(Sale.status == st)
    if cust := f.get('customer', ''):
        q = q.join(Customer).filter(or_(
            Customer.name.ilike(f"%{cust}%"),
            Customer.phone.ilike(f"%{cust}%")
        ))
    if df := f.get('date_from', ''):
        try:
            q = q.filter(Sale.date >= datetime.fromisoformat(df))
        except ValueError:
            pass
    if dt := f.get('date_to', ''):
        try:
            q = q.filter(Sale.date <= datetime.fromisoformat(dt))
        except ValueError:
            pass
    if inv := f.get('invoice_no', ''):
        q = q.filter(Sale.sale_number.ilike(f"%{inv}%"))

    # ترتيب النتائج
    sort, order = f.get('sort', 'date'), f.get('order', 'desc')
    if sort == 'total':
        fld = subtotals.c.calc_total
    else:
        sql_fields = {
            'date':     Sale.created_at,
            'customer': Customer.name
        }
        fld = sql_fields.get(sort, Sale.sale_number)
    q = q.order_by(fld.asc() if order == 'asc' else fld.desc())

    # تصفح الصفحات
    page = int(f.get('page', 1))
    pag  = q.paginate(page=page, per_page=20, error_out=False)
    sales = pag.items

    # تنسيق كل سجل
    for s in sales:
        _format_sale(s)

    return render_template(
        'sales/list.html',
        sales=sales,
        pagination=pag,
        warehouses=Warehouse.query.all(),
        customers=Customer.query.order_by(Customer.name).limit(100).all(),
        sellers=User.query.filter_by(is_active=True).all(),
        status_map=STATUS_MAP
    )

# ========================== إنشاء فاتورة جديدة ==========================
@sales_bp.route('/new', methods=['GET','POST'], endpoint='create_sale')
@login_required
@permission_required('manage_sales')
def create_sale():
    form = SaleForm()
    populate_sale_form_choices(form)

    if form.validate_on_submit():
        last = Sale.query.order_by(Sale.id.desc()).first()
        sid  = (last.id+1) if last else 1
        num  = f"INV-{datetime.utcnow():%Y%m%d}-{sid:04d}"
        sale = Sale(
            sale_number=num, customer_id=form.customer_id.data,
            seller_id=form.seller_id.data, date=form.date.data or datetime.utcnow(),
            status=form.status.data, currency=form.currency.data,
            tax_rate=form.tax_rate.data or 0, shipping_cost=form.shipping_cost.data or 0,
            notes=form.notes.data
        )
        db.session.add(sale); db.session.flush()

        for ent in form.lines.entries:
            ln = ent.form
            if not ln.product_id.data or ln.quantity.data<=0: continue
            line = SaleLine(
                sale_id=sale.id, product_id=ln.product_id.data, warehouse_id=ln.warehouse_id.data,
                quantity=ln.quantity.data, unit_price=ln.unit_price.data,
                discount_rate=ln.discount_rate.data or 0, tax_rate=ln.tax_rate.data or 0
            )
            stock = StockLevel.query.filter_by(product_id=line.product_id, warehouse_id=line.warehouse_id).first()
            if not stock or stock.quantity < line.quantity:
                flash(f"❌ مخزون غير كافٍ للمنتج {line.product.name}", 'danger')
                db.session.rollback()
                return render_template('sales/form.html', form=form, products=Product.query.all(), warehouses=Warehouse.query.all(), title="إنشاء فاتورة جديدة")
            stock.quantity -= line.quantity
            stock.product.reserved_quantity += line.quantity
            db.session.add(line)

        try:
            db.session.commit()
            log_sale_action(sale, 'add', None, sale_to_dict(sale))
            flash('✅ تم إنشاء الفاتورة بنجاح.', 'success')
            return redirect(url_for('sales.sale_detail', id=sale.id))
        except SQLAlchemyError:
            db.session.rollback()
            flash('❌ خطأ أثناء الحفظ', 'danger')

    return render_template('sales/form.html', form=form, products=Product.query.all(), warehouses=Warehouse.query.all(), title="إنشاء فاتورة جديدة")
# ========================== تفاصيل الفاتورة ==========================
@sales_bp.route('/<int:id>', methods=['GET'], endpoint='sale_detail')
@login_required
@permission_required('manage_sales')
def sale_detail(id):
    sale = Sale.query.options(
        joinedload(Sale.customer),
        joinedload(Sale.seller),
        joinedload(Sale.lines).joinedload(SaleLine.product),
        joinedload(Sale.lines).joinedload(SaleLine.warehouse),
        joinedload(Sale.payments)
    ).get_or_404(id)
    _format_sale(sale)

    for ln in sale.lines:
        ln.product_name = ln.product.name
        ln.warehouse_name = ln.warehouse.name
        ln.line_total = (ln.unit_price * ln.quantity * (1 - ln.discount_rate/100)) * (1 + ln.tax_rate/100)
        ln.line_total_fmt = f"{ln.line_total:,.2f}"

    for p in sale.payments:
        p.date_formatted = p.payment_date.strftime('%Y-%m-%d')
        st, cl = PAYMENT_STATUS_MAP.get(p.status, (p.status, ''))
        p.status_label, p.status_class = st, cl
        p.method_label = PAYMENT_METHOD_MAP.get(p.method, p.method)

    balance_fmt = f"{sale.total - sale.total_paid:,.2f}"
    invoice = Invoice.query.filter_by(sale_id=id).first()

    return render_template('sales/detail.html',
        sale=sale, balance_formatted=balance_fmt, invoice=invoice,
        PAYMENT_METHOD_MAP=PAYMENT_METHOD_MAP, PAYMENT_STATUS_MAP=PAYMENT_STATUS_MAP
    )

# ========================== سجل الدفعات ==========================
@sales_bp.route('/<int:id>/payments', endpoint='sale_payments')
@login_required
@permission_required('manage_sales')
def sale_payments(id):
    sale = Sale.query.options(joinedload(Sale.payments)).get_or_404(id)
    _format_sale(sale)

    for p in sale.payments:
        st, cl = PAYMENT_STATUS_MAP.get(p.status, (p.status, ''))
        p.status_label, p.status_class = st, cl
        p.method_label = PAYMENT_METHOD_MAP.get(p.method, p.method)

    return render_template('sales/payments.html', sale=sale, payments=sale.payments)

# ========================== تعديل فاتورة ==========================
@sales_bp.route('/<int:id>/edit', methods=['GET','POST'], endpoint='edit_sale')
@login_required
@permission_required('manage_sales')
def edit_sale(id):
    sale = Sale.query.get_or_404(id)
    if sale.status in ['paid', 'cancelled']:
        flash('❌ لا يمكن تعديل فاتورة مدفوعة أو ملغاة.', 'danger')
        return redirect(url_for('sales.sale_detail', id=id))

    old = sale_to_dict(sale)
    form = SaleForm(obj=sale)
    populate_sale_form_choices(form)

    # تعبئة البنود
    for idx, ln in enumerate(sale.lines):
        if idx >= len(form.lines.entries): form.lines.append_entry()
        e = form.lines.entries[idx].form
        e.product_id.data, e.warehouse_id.data = ln.product_id, ln.warehouse_id
        e.quantity.data, e.unit_price.data = ln.quantity, ln.unit_price
        e.discount_rate.data, e.tax_rate.data = ln.discount_rate, ln.tax_rate

    if form.validate_on_submit():
        release_stock_for_sale(sale)
        sale.customer_id, sale.seller_id = form.customer_id.data, form.seller_id.data
        sale.date = form.date.data or sale.date
        sale.status, sale.currency = form.status.data, form.currency.data
        sale.tax_rate, sale.shipping_cost = form.tax_rate.data or 0, form.shipping_cost.data or 0
        sale.notes = form.notes.data

        SaleLine.query.filter_by(sale_id=sale.id).delete()

        for ent in form.lines.entries:
            ln = ent.form
            if not ln.product_id.data or ln.quantity.data <= 0: continue
            line = SaleLine(
                sale_id=sale.id, product_id=ln.product_id.data,
                warehouse_id=ln.warehouse_id.data, quantity=ln.quantity.data,
                unit_price=ln.unit_price.data, discount_rate=ln.discount_rate.data or 0,
                tax_rate=ln.tax_rate.data or 0
            )
            stock = StockLevel.query.filter_by(product_id=line.product_id, warehouse_id=line.warehouse_id).first()
            if not stock or stock.quantity < line.quantity:
                flash(f"❌ مخزون غير كافٍ للمنتج {line.product.name}", 'danger')
                db.session.rollback()
                return render_template('sales/form.html', form=form, sale=sale, products=Product.query.all(), warehouses=Warehouse.query.all(), title="تعديل الفاتورة")
            stock.quantity -= line.quantity
            stock.product.reserved_quantity += line.quantity
            db.session.add(line)

        try:
            db.session.commit()
            log_sale_action(sale, 'edit', old, sale_to_dict(sale))
            flash('✅ تم التعديل بنجاح.', 'success')
            return redirect(url_for('sales.sale_detail', id=id))
        except SQLAlchemyError:
            db.session.rollback()
            flash('❌ خطأ أثناء التعديل', 'danger')

    return render_template('sales/form.html', form=form, sale=sale, products=Product.query.all(), warehouses=Warehouse.query.all(), title="تعديل الفاتورة")

# ========================== حذف فاتورة ==========================
@sales_bp.route('/<int:id>/delete', methods=['POST'], endpoint='delete_sale')
@login_required
@permission_required('manage_sales')
def delete_sale(id):
    sale = Sale.query.get_or_404(id)
    if sale.status == 'paid':
        flash('❌ لا يمكن حذف فاتورة مدفوعة.', 'danger')
        return redirect(url_for('sales.sale_detail', id=id))

    try:
        release_stock_for_sale(sale)
        log_sale_action(sale, 'delete', sale_to_dict(sale), None)
        db.session.delete(sale)
        db.session.commit()
        flash('✅ تم حذف الفاتورة.', 'warning')
    except SQLAlchemyError:
        db.session.rollback()
        flash('❌ خطأ أثناء الحذف', 'danger')

    return redirect(url_for('sales.list_sales'))

# ========================== تغيير حالة الفاتورة ==========================
@sales_bp.route('/<int:id>/status/<status>', methods=['POST'])
@login_required
@permission_required('manage_sales')
def change_sale_status(id, status):
    sale = Sale.query.get_or_404(id)
    valid = {
        'draft': ['confirmed','cancelled'],
        'confirmed': ['paid','shipped','cancelled'],
        'shipped': ['delivered','returned'],
        'paid': ['delivered','returned'],
        'on_hold': ['confirmed','cancelled']
    }
    if status not in valid.get(sale.status, []):
        flash('❌ حالة غير صالحة.', 'danger')
        return redirect(url_for('sales.sale_detail', id=id))

    if status == 'cancelled': release_stock_for_sale(sale)
    if status == 'paid': sale.payment_status = 'paid'
    sale.status = status

    try:
        db.session.commit()
        flash(f'✅ تم تغيير الحالة إلى {status}', 'success')
    except SQLAlchemyError:
        db.session.rollback()
        flash('❌ خطأ أثناء تحديث الحالة', 'danger')

    return redirect(url_for('sales.sale_detail', id=id))

# ========================== ربط الدفع الموحد ==========================
@sales_bp.route('/<int:id>/payments/add', methods=['GET','POST'], endpoint='add_payment')
@login_required
@permission_required('manage_sales')
def redirect_to_unified_add(id):
    return redirect(url_for('payments.create_payment', entity_type='sale', entity_id=id))

@sales_bp.route('/payments/<int:pid>/delete', methods=['POST'], endpoint='delete_payment')
@login_required
@permission_required('manage_sales')
def redirect_to_unified_delete(pid):
    return redirect(url_for('payments.delete_payment', payment_id=pid))

# ========================== إنشاء PDF ==========================
@sales_bp.route('/<int:id>/invoice')
@login_required
@permission_required('manage_sales')
def generate_invoice(id):
    sale = Sale.query.get_or_404(id)
    pdf = generate_invoice_pdf(sale)
    return Response(pdf, mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename=invoice_{sale.sale_number}.pdf'})
