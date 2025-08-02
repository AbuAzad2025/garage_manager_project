# File: routes/invoices.py

import json
from datetime import datetime

from flask import (
    Blueprint, abort, flash, jsonify, redirect,
    render_template, request, url_for
)
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from extensions import db, mail
from forms import InvoiceForm, InvoiceLineForm
from models import (
    AuditLog, Customer, Invoice, InvoiceLine,
    Payment, PreOrder, Sale, ServiceRequest, Supplier, Partner
)
from utils import permission_required

invoices_bp = Blueprint(
    'invoices',
    __name__,
    url_prefix='/invoices',
    template_folder='templates/invoices'
)

# خريطة الحالة → (علامة، CSS)
INVOICE_STATUS = {
    'PENDING':   ('معلقة',    'bg-warning text-dark'),
    'PAID':      ('مدفوعة',   'bg-success'),
    'CANCELLED': ('ملغاة',    'bg-secondary'),
}

def _format_invoice(inv: Invoice):
    """تهيئة حقول العرض في القالب."""
    lbl, cls = INVOICE_STATUS.get(inv.status, (inv.status, ''))
    inv.status_label = lbl
    inv.status_class = cls
    inv.date_fmt    = inv.date.strftime('%Y-%m-%d') if inv.date else '-'
    inv.due_fmt     = inv.due_date.strftime('%Y-%m-%d') if inv.due_date else '-'
    inv.total_fmt   = f"{inv.total_amount:,.2f}"

def invoice_to_dict(inv: Invoice):
    """تحويل الفاتورة إلى dict لتسجيل الـ audit."""
    data = {
        'invoice_number': inv.invoice_number,
        'source':         inv.source,
        'status':         inv.status,
        'date':           inv.date_fmt,
        'due_date':       inv.due_fmt,
        'is_cancelled':   inv.is_cancelled,
        'total_amount':   float(inv.total_amount or 0),
        'lines': [
            {
                'description': ln.description,
                'quantity':    float(ln.quantity),
                'unit_price':  float(ln.unit_price),
                'tax_rate':    float(ln.tax_rate),
                'discount':    float(ln.discount)
            }
            for ln in inv.lines
        ]
    }
    # علاقات المصدر
    if inv.sale_id:    data['sale_id'] = inv.sale_id
    if inv.service_id: data['service_id'] = inv.service_id
    if inv.preorder_id:data['preorder_id'] = inv.preorder_id
    if inv.supplier_id:data['supplier_id'] = inv.supplier_id
    if inv.partner_id: data['partner_id']  = inv.partner_id
    return data

def log_invoice_action(inv: Invoice, action: str, old=None, new=None):
    entry = AuditLog(
        user_id     = current_user.id,
        invoice_id  = inv.id,
        action      = action,
        old_data    = json.dumps(old, ensure_ascii=False) if old else None,
        new_data    = json.dumps(new, ensure_ascii=False) if new else None
    )
    db.session.add(entry)
    db.session.commit()


@invoices_bp.route('/', methods=['GET'], endpoint='list_invoices')
@login_required
@permission_required('manage_invoices')
def list_invoices():
    """قائمة الفواتير مع فلاتر. يدعم JSON."""
    q = Invoice.query
    if cust := request.args.get('customer'):
        q = q.join(Customer).filter(Customer.name.ilike(f"%{cust}%"))
    if status := request.args.get('status'):
        q = q.filter(Invoice.status == status)
    if source := request.args.get('source'):
        q = q.filter(Invoice.source == source)

    invoices = q.order_by(Invoice.date.desc()).all()
    for inv in invoices:
        _format_invoice(inv)

    if request.args.get('format') == 'json' or request.is_json:
        return jsonify([{
            'id':             inv.id,
            'invoice_number': inv.invoice_number,
            'customer':       inv.customer.name if inv.customer else '-',
            'date':           inv.date_fmt,
            'status':         inv.status,
            'total':          inv.total_fmt
        } for inv in invoices])

    return render_template('invoices/list.html', invoices=invoices)


@invoices_bp.route('/new', methods=['GET', 'POST'], endpoint='invoice_new')
@login_required
@permission_required('manage_invoices')
def invoice_new():
    """إنشاء فاتورة يدوية أو مستمدة من بيع/صيانة/حجز."""
    form = InvoiceForm()
    # تهيئة خطوط الفاتورة
    for e in form.lines.entries:
        e.form.__class__ = InvoiceLineForm

    # تعبئة أولية عبر query params
    if request.method == 'GET':
        form.source.data = request.args.get('source', 'manual')
        if sid := request.args.get('sale_id', type=int):
            form.sale_id.data = sid
            form.customer_id.data = Sale.query.get(sid).customer_id
        if srv := request.args.get('service_id', type=int):
            form.service_id.data = srv
            form.customer_id.data = ServiceRequest.query.get(srv).customer_id
        if pid := request.args.get('preorder_id', type=int):
            form.preorder_id.data = pid
            form.customer_id.data = PreOrder.query.get(pid).customer_id
        if sup := request.args.get('supplier_id', type=int):
            form.supplier_id.data = sup
        if prt := request.args.get('partner_id', type=int):
            form.partner_id.data = prt

    if form.validate_on_submit():
        # رقم فاتورة فريد
        last = Invoice.query.order_by(Invoice.id.desc()).first()
        nid = (last.id + 1) if last else 1
        inv_no = f"INV-{datetime.utcnow():%Y%m%d}-{nid:04d}"

        inv = Invoice(
            invoice_number = inv_no,
            source         = form.source.data,
            customer_id    = form.customer_id.data.id,
            supplier_id    = getattr(form.supplier_id.data, 'id', None),
            partner_id     = getattr(form.partner_id.data, 'id', None),
            sale_id        = form.sale_id.data or None,
            service_id     = form.service_id.data or None,
            preorder_id    = form.preorder_id.data or None,
            date           = form.date.data or datetime.utcnow(),
            due_date       = form.due_date.data,
            status         = form.status.data,
            is_cancelled   = form.is_cancelled.data,
            total_amount   = 0
        )
        db.session.add(inv)
        db.session.flush()

        total = 0
        for entry in form.lines.entries:
            ln = entry.form
            line = InvoiceLine(
                invoice_id = inv.id,
                description= ln.description.data,
                quantity   = float(ln.quantity.data),
                unit_price = float(ln.unit_price.data),
                tax_rate   = float(ln.tax_rate.data or 0),
                discount   = float(ln.discount.data or 0)
            )
            db.session.add(line)
            total += line.line_total

        inv.total_amount = total
        try:
            db.session.commit()
            log_invoice_action(inv, 'add', None, invoice_to_dict(inv))
            flash('تم إنشاء الفاتورة بنجاح.', 'success')
            return redirect(url_for('invoices.invoice_detail', id=inv.id))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'خطأ أثناء إنشاء الفاتورة: {e}', 'danger')

    return render_template('invoices/form.html', form=form)


@invoices_bp.route('/<int:id>', methods=['GET', 'POST'], endpoint='invoice_detail')
@login_required
@permission_required('manage_invoices')
def invoice_detail(id):
    """عرض وتعديل الفاتورة."""
    inv = Invoice.query.get_or_404(id)
    _format_invoice(inv)

    form = InvoiceForm(obj=inv)
    for e in form.lines.entries:
        e.form.__class__ = InvoiceLineForm

    # تعبئة الخطوط في GET
    if request.method == 'GET':
        form.lines.entries.clear()
        for ln in inv.lines:
            e = form.lines.append_entry()
            e.form.description.data = ln.description
            e.form.quantity.data    = ln.quantity
            e.form.unit_price.data  = ln.unit_price
            e.form.tax_rate.data    = ln.tax_rate
            e.form.discount.data    = ln.discount

    payments = Payment.query.filter_by(invoice_id=id).order_by(Payment.created_at).all()

    if form.validate_on_submit():
        old = {'status': inv.status, 'total_amount': float(inv.total_amount)}

        inv.source       = form.source.data
        inv.customer_id  = form.customer_id.data.id
        inv.supplier_id  = getattr(form.supplier_id.data, 'id', None)
        inv.partner_id   = getattr(form.partner_id.data, 'id', None)
        inv.sale_id      = form.sale_id.data or None
        inv.service_id   = form.service_id.data or None
        inv.preorder_id  = form.preorder_id.data or None
        inv.date         = form.date.data or inv.date
        inv.due_date     = form.due_date.data
        inv.status       = form.status.data
        inv.is_cancelled = form.is_cancelled.data

        InvoiceLine.query.filter_by(invoice_id=id).delete()
        total = 0
        for entry in form.lines.entries:
            ln = entry.form
            line = InvoiceLine(
                invoice_id = id,
                description= ln.description.data,
                quantity   = float(ln.quantity.data),
                unit_price = float(ln.unit_price.data),
                tax_rate   = float(ln.tax_rate.data or 0),
                discount   = float(ln.discount.data or 0)
            )
            db.session.add(line)
            total += line.line_total

        inv.total_amount = total
        try:
            db.session.commit()
            log_invoice_action(inv, 'edit', old, {'status': inv.status, 'total_amount': total})
            flash('تم تعديل الفاتورة بنجاح.', 'success')
            return redirect(url_for('invoices.invoice_detail', id=id))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'خطأ أثناء التعديل: {e}', 'danger')

    return render_template('invoices/detail.html',
                           invoice=inv, form=form, payments=payments)


@invoices_bp.route('/<int:id>/delete', methods=['POST'], endpoint='invoice_delete')
@login_required
@permission_required('manage_invoices')
def invoice_delete(id):
    """حذف فاتورة."""
    inv = Invoice.query.get_or_404(id)
    try:
        log_invoice_action(inv, 'delete', invoice_to_dict(inv), None)
        db.session.delete(inv)
        db.session.commit()
        flash('تم حذف الفاتورة.', 'warning')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'حدث خطأ أثناء الحذف: {e}', 'danger')
    return redirect(url_for('invoices.list_invoices'))


@invoices_bp.route('/<int:id>/cancel', methods=['POST'], endpoint='invoice_cancel')
@login_required
@permission_required('manage_invoices')
def invoice_cancel(id):
    """إلغاء فاتورة مع تسجيل الحدث."""
    inv = Invoice.query.get_or_404(id)
    if inv.status != 'CANCELLED':
        inv.status = 'CANCELLED'
        try:
            db.session.commit()
            log_invoice_action(inv, 'cancel', None, {'status': 'CANCELLED'})
            flash('تم إلغاء الفاتورة.', 'info')
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'خطأ أثناء الإلغاء: {e}', 'danger')
    else:
        flash('الفاتورة ملغاة بالفعل.', 'warning')
    return redirect(url_for('invoices.invoice_detail', id=id))
