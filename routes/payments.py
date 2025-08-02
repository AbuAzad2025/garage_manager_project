# File: routes/payments.py
import csv, io, json
from datetime import datetime

from flask import (
    Blueprint, flash, redirect, render_template,
    request, url_for, jsonify, send_file
)
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from extensions import db
from models import (
    Payment, PaymentSplit,
    Customer, Supplier, Partner,
    AuditLog, Invoice, InvoiceStatus,
    PaymentStatus, PaymentDirection,
    ProductSupplierLoan, WarehousePartnerShare, ProductPartnerShare
)
from forms import PaymentForm, splitEntryForm
from utils import permission_required, generate_pdf_report as generate_payment_receipt_pdf

payments_bp = Blueprint(
    'payments', __name__,
    url_prefix='/payments',
    template_folder='templates/payments'
)

@payments_bp.route('/', methods=['GET'], endpoint='index')
@login_required
@permission_required('manage_payments')
def index():
    q = Payment.query
    for fld in ('entity_type','status','direction','method'):
        if val := request.args.get(fld):
            q = q.filter(getattr(Payment, fld)==val)
    if start := request.args.get('start_date'):
        q = q.filter(Payment.payment_date>=start)
    if end := request.args.get('end_date'):
        q = q.filter(Payment.payment_date<=end)

    page     = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    pagination = q.order_by(Payment.payment_date.desc())\
                  .paginate(page=page, per_page=per_page, error_out=False)
    payments = pagination.items

    args = request.args.to_dict(flat=True)
    args.pop('page', None)

    total_paid = db.session.query(func.coalesce(func.sum(Payment.total_amount), 0)).scalar()

    return render_template(
        'payments/list.html',
        payments    = payments,
        total_paid  = total_paid,
        pagination  = pagination,
        args        = args,
        entity      = None,
        entity_name = 'كل الجهات'
    )
def log_audit(action, payment, details=""):
    db.session.add(AuditLog(
        model_name="Payment",
        record_id=payment.id,
        user_id=current_user.id,
        action=action,
        old_data="",
        new_data=details
    ))
    db.session.commit()
    
def update_entity_balance(entity_type, entity_id):
    if entity_type == 'customer' and entity_id:
        customer = Customer.query.get(entity_id)
        if customer:
            total_invoiced = db.session.query(
                func.coalesce(func.sum(Invoice.total_amount), 0)
            ).filter(
                Invoice.customer_id == customer.id,
                Invoice.status != InvoiceStatus.CANCELLED
            ).scalar()
            total_paid = db.session.query(
                func.coalesce(func.sum(Payment.total_amount), 0)
            ).filter(
                Payment.customer_id == customer.id,
                Payment.status == PaymentStatus.COMPLETED
            ).scalar()
            customer.balance = float(total_invoiced) - float(total_paid)
            db.session.add(customer)
    elif entity_type == 'supplier' and entity_id:
        supplier = Supplier.query.get(entity_id)
        if supplier:
            total_loans = db.session.query(
                func.coalesce(func.sum(ProductSupplierLoan.loan_value), 0)
            ).filter(
                ProductSupplierLoan.supplier_id == supplier.id
            ).scalar()
            total_paid = db.session.query(
                func.coalesce(func.sum(Payment.total_amount), 0)
            ).filter(
                Payment.supplier_id == supplier.id,
                Payment.status == PaymentStatus.COMPLETED,
                Payment.direction == PaymentDirection.OUTGOING
            ).scalar()
            supplier.balance = float(total_loans) - float(total_paid)
            db.session.add(supplier)
    elif entity_type == 'partner' and entity_id:
        partner = Partner.query.get(entity_id)
        if partner:
            wh_shares = db.session.query(
                func.coalesce(func.sum(WarehousePartnerShare.share_amount), 0)
            ).filter(
                WarehousePartnerShare.partner_id == partner.id
            ).scalar()
            pr_shares = db.session.query(
                func.coalesce(func.sum(ProductPartnerShare.share_amount), 0)
            ).filter(
                ProductPartnerShare.partner_id == partner.id
            ).scalar()
            total_shares = float(wh_shares) + float(pr_shares)
            total_withdrawals = db.session.query(
                func.coalesce(func.sum(Payment.total_amount), 0)
            ).filter(
                Payment.partner_id == partner.id,
                Payment.status == PaymentStatus.COMPLETED,
                Payment.direction == PaymentDirection.OUTGOING
            ).scalar()
            partner.balance = total_shares - float(total_withdrawals)
            db.session.add(partner)

# ===== Create =====
@payments_bp.route("/create", methods=["GET", "POST"], endpoint='create_payment')
@login_required
@permission_required('manage_payments')
def create_payment():
    # تعديل: دعم entity_id وتحديث الأرصدة بعد الإنشاء
    form = PaymentForm()
    form.payment_date.data = datetime.utcnow().date()
    entity_type = request.args.get('entity_type')
    entity_id = request.args.get('entity_id')
    entity_info = None

    if entity_type:
        form.entity_type.data = entity_type
    if entity_id:
        try:
            form.entity_id.data = int(entity_id)
        except (ValueError, TypeError):
            pass

    if entity_type and entity_id:
        if entity_type == 'sale':
            sale = Sale.query.get(int(entity_id))
            if sale:
                form.customer_id.data = sale.customer
                form.total_amount.data = sale.balance_due
                form.reference.data = f"دفعة للفاتورة {sale.sale_number}"
                entity_info = {
                    'type': 'sale', 'number': sale.sale_number,
                    'date': sale.sale_date.strftime('%Y-%m-%d'),
                    'total': sale.total, 'paid': sale.total_paid,
                    'balance': sale.balance_due, 'currency': sale.currency
                }
        elif entity_type == 'invoice':
            invoice = Invoice.query.get(int(entity_id))
            if invoice:
                if invoice.customer:
                    form.customer_id.data = invoice.customer
                form.total_amount.data = invoice.balance_due
                form.reference.data = f"دفعة للفاتورة {invoice.invoice_number}"
                entity_info = {
                    'type': 'invoice', 'number': invoice.invoice_number,
                    'date': invoice.invoice_date.strftime('%Y-%m-%d'),
                    'total': invoice.total_amount, 'paid': invoice.total_paid,
                    'balance': invoice.balance_due, 'currency': 'ILS'
                }
        elif entity_type == 'customer':
            customer = Customer.query.get(int(entity_id))
            if customer:
                form.customer_id.data = customer
                entity_info = {'type': 'customer', 'name': customer.name, 'balance': customer.balance}
        elif entity_type == 'supplier':
            supplier = Supplier.query.get(int(entity_id))
            if supplier:
                form.supplier_id.data = supplier
                form.total_amount.data = supplier.balance
                entity_info = {'type': 'supplier', 'name': supplier.name, 'balance': supplier.balance}
        elif entity_type == 'partner':
            partner = Partner.query.get(int(entity_id))
            if partner:
                form.partner_id.data = partner
                form.total_amount.data = partner.balance
                entity_info = {'type': 'partner', 'name': partner.name, 'balance': partner.balance}

    if form.validate_on_submit():
        try:
            payment = Payment(
                total_amount=form.total_amount.data,
                currency=form.currency.data,
                method=form.method.data,
                payment_date=form.payment_date.data,
                reference=form.reference.data,
                notes=form.notes.data,
                status=form.status.data,
                direction=form.direction.data,
                entity_type=form.entity_type.data,
                customer_id=form.customer_id.data.id if form.customer_id.data else None,
                supplier_id=form.supplier_id.data.id if form.supplier_id.data else None,
                partner_id=form.partner_id.data.id if form.partner_id.data else None,
            )
            db.session.add(payment)
            db.session.flush()
            # إنشاء دفعات جزئية
            for s in form.splits.data:
                split = PaymentSplit(
                    payment_id=payment.id,
                    method=s['method'],
                    amount=s['amount'],
                    details={
                        'check_number': s.get('check_number'),
                        'check_bank': s.get('check_bank'),
                        'due_date': str(s.get('check_due_date')) if s.get('check_due_date') else None,
                        'card_number': s.get('card_number'),
                        'bank_transfer_ref': s.get('bank_transfer_ref')
                    }
                )
                db.session.add(split)
            # تحديث الأرصدة
            if payment.customer_id:
                update_entity_balance('customer', payment.customer_id)
            if payment.supplier_id:
                update_entity_balance('supplier', payment.supplier_id)
            if payment.partner_id:
                update_entity_balance('partner', payment.partner_id)
            db.session.commit()
            log_audit('CREATE', payment, 'Payment created with splits')
            flash('✅ تم تسجيل الدفعة وتحديث الرصيد بنجاح', 'success')
            return redirect(url_for('payments.view_payment', payment_id=payment.id))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ في الحفظ: {e}', 'danger')

    return render_template('payments/create.html', form=form, entity_info=entity_info, payment=None)

# ===== View =====
@payments_bp.route('/<int:payment_id>', methods=['GET'], endpoint='view_payment')
@login_required
@permission_required('manage_payments')
def view_payment(payment_id):
    payment = Payment.query.options(
        joinedload(Payment.customer), joinedload(Payment.supplier),
        joinedload(Payment.partner), joinedload(Payment.shipment),
        joinedload(Payment.expense), joinedload(Payment.loan_settlement),
        joinedload(Payment.sale), joinedload(Payment.invoice),
        joinedload(Payment.preorder), joinedload(Payment.service),
        joinedload(Payment.splits)
    ).get_or_404(payment_id)
    return render_template('payments/view.html', payment=payment)

@payments_bp.route('/<int:payment_id>/edit', methods=['GET', 'POST'], endpoint='edit_payment')
@login_required
@permission_required('manage_payments')
def edit_payment(payment_id):
    # تعديل: تعيين entity_id الصحيح في وضع GET
    payment = Payment.query.get_or_404(payment_id)
    form = PaymentForm(obj=payment)

    if request.method == 'GET':
        form.entity_type.data = payment.entity_type
        if payment.entity_type == 'sale':
            form.entity_id.data = payment.sale_id
        elif payment.entity_type == 'invoice':
            form.entity_id.data = payment.invoice_id
        elif payment.entity_type == 'customer':
            form.entity_id.data = payment.customer_id
        elif payment.entity_type == 'supplier':
            form.entity_id.data = payment.supplier_id
        elif payment.entity_type == 'partner':
            form.entity_id.data = payment.partner_id
        form.splits.entries.clear()
        for s in payment.splits:
            sf = splitEntryForm()
            sf.method.data = s.method
            sf.amount.data = s.amount
            sf.check_number.data = s.details.get('check_number')
            sf.check_bank.data = s.details.get('check_bank')
            sf.check_due_date.data = s.details.get('due_date')
            sf.card_number.data = s.details.get('card_number')
            sf.bank_transfer_ref.data = s.details.get('bank_transfer_ref')
            form.splits.append_entry(sf.data)

    if form.validate_on_submit():
        try:
            for field in [
                'total_amount', 'currency', 'method', 'payment_date',
                'reference', 'notes', 'status', 'direction', 'entity_type'
            ]:
                setattr(payment, field, getattr(form, field).data)
            payment.customer_id = form.customer_id.data.id if form.customer_id.data else None
            payment.supplier_id = form.supplier_id.data.id if form.supplier_id.data else None
            payment.partner_id = form.partner_id.data.id if form.partner_id.data else None
            payment.shipment_id = form.shipment_id.data.id if form.shipment_id.data else None
            payment.expense_id = form.expense_id.data.id if form.expense_id.data else None
            payment.loan_settlement_id = form.loan_settlement_id.data.id if form.loan_settlement_id.data else None

            for old in list(payment.splits):
                db.session.delete(old)
            for s in form.splits.data:
                split = PaymentSplit(
                    payment_id=payment.id,
                    method=s['method'],
                    amount=s['amount'],
                    details={
                        'check_number': s.get('check_number'),
                        'check_bank': s.get('check_bank'),
                        'due_date': str(s.get('check_due_date')) if s.get('check_due_date') else None,
                        'card_number': s.get('card_number'),
                        'bank_transfer_ref': s.get('bank_transfer_ref')
                    }
                )
                db.session.add(split)

            # إعادة تحديث الأرصدة
            if payment.customer_id:
                update_entity_balance('customer', payment.customer_id)
            if payment.supplier_id:
                update_entity_balance('supplier', payment.supplier_id)
            if payment.partner_id:
                update_entity_balance('partner', payment.partner_id)

            db.session.commit()
            log_audit('UPDATE', payment, 'Payment updated with recalculated balances')
            flash('✅ تم تحديث الدفعة والأرصدة بنجاح', 'success')
            return redirect(url_for('payments.view_payment', payment_id=payment.id))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ في التحديث: {e}', 'danger')

    return render_template('payments/edit.html', form=form, payment=payment)


# ===== Delete =====
@payments_bp.route('/<int:payment_id>/delete', methods=['POST'], endpoint='delete_payment')
@login_required
@permission_required('manage_payments')
def delete_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    try:
        entity_type = payment.entity_type
        cust_id = payment.customer_id
        supp_id = payment.supplier_id
        part_id = payment.partner_id

        db.session.delete(payment)
        db.session.commit()

        # تحديث الكيانات بعد الحذف
        if entity_type == 'sale':
            sale = Sale.query.get(payment_id)
            if sale:
                sale.update_payment_status()
                db.session.add(sale)
        elif entity_type == 'invoice':
            invoice = Invoice.query.get(payment_id)
            if invoice:
                invoice.update_status()
                db.session.add(invoice)
        elif entity_type == 'preorder':
            preorder = PreOrder.query.get(payment_id)
            if preorder:
                preorder.status = PreOrderStatus.PENDING
                db.session.add(preorder)
        elif entity_type == 'service':
            service = ServiceRequest.query.get(payment_id)
            if service:
                service.status = ServiceStatus.PENDING
                db.session.add(service)

        # إعادة تحديث الأرصدة
        if cust_id:
            update_entity_balance('customer', cust_id)
        if supp_id:
            update_entity_balance('supplier', supp_id)
        if part_id:
            update_entity_balance('partner', part_id)

        db.session.commit()
        log_audit('DELETE', payment, 'Payment deleted and balances recalculated')
        flash('✅ تم حذف الدفعة وتحديث الأرصدة بنجاح', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ في الحذف: {e}', 'danger')

    return redirect(url_for('payments.index'))

# ===== Receipt: عرض الوصل بصيغة HTML =====
@payments_bp.route('/<int:payment_id>/receipt', methods=['GET'], endpoint='view_receipt')
@login_required
@permission_required('manage_payments')
def view_receipt(payment_id):
    payment = Payment.query.options(
        joinedload(Payment.customer),
        joinedload(Payment.supplier),
        joinedload(Payment.partner),
        joinedload(Payment.sale),
    ).get_or_404(payment_id)

    sale_info = None
    if payment.sale_id:
        sale = Sale.query.get(payment.sale_id)
        if sale:
            sale_info = {
                'number':   sale.sale_number,
                'date':     sale.sale_date.strftime('%Y-%m-%d'),
                'total':    sale.total_amount,
                'paid':     sale.total_paid,
                'balance':  sale.balance_due,
                'currency': sale.currency
            }

    return render_template(
        'payments/receipt.html',
        payment   = payment,
        now       = datetime.utcnow(),
        sale_info = sale_info
    )


# ===== Receipt: تنزيل الوصل كـ PDF =====
@payments_bp.route('/<int:payment_id>/receipt/download', methods=['GET'], endpoint='download_receipt')
@login_required
@permission_required('manage_payments')
def download_receipt(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    pdf_result = generate_payment_receipt_pdf(payment)

    # إذا عادت bytes
    if isinstance(pdf_result, (bytes, bytearray)):
        return Response(
            pdf_result,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename=payment_receipt_{payment_id}.pdf'}
        )

    # وإلا نرسل مسار الملف
    return send_file(
        pdf_result,
        as_attachment    = True,
        download_name    = f'payment_receipt_{payment_id}.pdf'
    )

# ===== Entity Fields Partial =====
@payments_bp.route('/split/<int:split_id>/delete', methods=['DELETE'], endpoint='delete_split')
@login_required
@permission_required('manage_payments')
def delete_split(split_id):
    split = PaymentSplit.query.get_or_404(split_id)
    try:
        db.session.delete(split)
        db.session.commit()
        return jsonify(status='success')
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify(status='error', message=str(e)), 400

@payments_bp.route('/entity-fields', methods=['GET'], endpoint='entity_fields')
@login_required
@permission_required('manage_payments')
def entity_fields():
    # تعديل: دعم entity_id وتعيين الحقل المناسب وفقًا لنوع الكيان
    entity_type = request.args.get('type', 'customer')
    entity_id = request.args.get('entity_id')
    form = PaymentForm()
    form.entity_type.data = entity_type
    if entity_id:
        try:
            eid = int(entity_id)
            if entity_type == 'customer':
                customer = Customer.query.get(eid)
                if customer:
                    form.customer_id.data = customer
            elif entity_type == 'supplier':
                supplier = Supplier.query.get(eid)
                if supplier:
                    form.supplier_id.data = supplier
            elif entity_type == 'partner':
                partner = Partner.query.get(eid)
                if partner:
                    form.partner_id.data = partner
        except (ValueError, TypeError):
            pass
    return render_template('payments/_entity_fields.html', form=form)
