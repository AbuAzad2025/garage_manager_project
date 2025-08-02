from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required
from flask_wtf import FlaskForm
from sqlalchemy import or_, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from extensions import db
from forms import SupplierForm, PartnerForm
from models import Supplier, Partner, Payment, PaymentEntityType, PaymentDirection
from utils import permission_required

# مجرد Form فارغ لاستخدامه بهدف تمرير csrf_token إلى القوالب
class CSRFProtectForm(FlaskForm):
    pass

vendors_bp = Blueprint('vendors', __name__, url_prefix='/vendors')

@vendors_bp.route('/suppliers', methods=['GET'], endpoint='suppliers_list')
@login_required
@permission_required('manage_vendors')
def suppliers_list():
    form = CSRFProtectForm()
    s = request.args.get('search', '').strip()
    q = Supplier.query
    if s:
        term = f"%{s}%"
        q = q.filter(or_(
            Supplier.name.ilike(term),
            Supplier.phone.ilike(term),
            Supplier.identity_number.ilike(term)
        ))
    suppliers = q.order_by(Supplier.name).all()
    return render_template(
        'vendors/suppliers/list.html',
        suppliers=suppliers,
        search=s,
        form=form
    )

@vendors_bp.route('/suppliers/new', methods=['GET', 'POST'], endpoint='suppliers_create')
@login_required
@permission_required('manage_vendors')
def suppliers_create():
    form = SupplierForm()
    if form.validate_on_submit():
        supplier = Supplier()
        form.populate_obj(supplier)
        db.session.add(supplier)
        try:
            db.session.commit()
            flash('✅ تم إضافة المورد بنجاح', 'success')
            return redirect(url_for('vendors.suppliers_list'))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ أثناء إضافة المورد: {e}', 'danger')
    # مرر supplier=None حتى يظهر شريط الأزرار والإحصاءات في قالب form
    return render_template(
        'vendors/suppliers/form.html',
        form=form,
        supplier=None
    )

@vendors_bp.route('/suppliers/<int:id>/edit', methods=['GET', 'POST'], endpoint='suppliers_edit')
@login_required
@permission_required('manage_vendors')
def suppliers_edit(id):
    supplier = Supplier.query.get_or_404(id)
    form = SupplierForm(obj=supplier)
    if form.validate_on_submit():
        form.populate_obj(supplier)
        try:
            db.session.commit()
            flash('✅ تم تحديث المورد بنجاح', 'success')
            return redirect(url_for('vendors.suppliers_list'))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ أثناء تحديث المورد: {e}', 'danger')
    return render_template('vendors/suppliers/form.html', form=form, supplier=supplier)

@vendors_bp.route('/suppliers/<int:id>/delete', methods=['POST'], endpoint='suppliers_delete')
@login_required
@permission_required('manage_vendors')
def suppliers_delete(id):
    supplier = Supplier.query.get_or_404(id)
    try:
        db.session.delete(supplier)
        db.session.commit()
        flash('✅ تم حذف المورد بنجاح', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ أثناء حذف المورد: {e}', 'danger')
    return redirect(url_for('vendors.suppliers_list'))

@vendors_bp.route('/suppliers/<int:id>/payments', methods=['GET'], endpoint='supplier_payments')
@login_required
@permission_required('manage_vendors')
def supplier_payments(id):
    supplier = Supplier.query.get_or_404(id)
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('ITEMS_PER_PAGE', 10)

    query = Payment.query.filter_by(
        supplier_id=id,
        entity_type=PaymentEntityType.SUPPLIER.value,
        direction=PaymentDirection.OUTGOING.value
    )
    pagination = query.order_by(Payment.payment_date.desc()) \
                      .paginate(page=page, per_page=per_page, error_out=False)

    total_paid = db.session.query(
        func.coalesce(func.sum(Payment.total_amount), 0)
    ).filter(
        Payment.supplier_id == id,
        Payment.entity_type == PaymentEntityType.SUPPLIER.value,
        Payment.direction == PaymentDirection.OUTGOING.value
    ).scalar()

    return render_template(
        'payments/list.html',
        entity=supplier,
        entity_type='supplier',
        entity_name='المورد',
        pagination=pagination,
        total_paid=total_paid
    )

@vendors_bp.route('/suppliers/<int:id>/pay', methods=['GET'], endpoint='supplier_pay')
@login_required
@permission_required('manage_vendors')
def supplier_pay(id):
    return redirect(url_for('payments.create_payment', entity_type='supplier', entity_id=id))

@vendors_bp.route('/partners', methods=['GET'], endpoint='partners_list')
@login_required
@permission_required('manage_vendors')
def partners_list():
    form = CSRFProtectForm()
    s = request.args.get('search', '').strip()
    q = Partner.query
    if s:
        term = f"%{s}%"
        q = q.filter(or_(
            Partner.name.ilike(term),
            Partner.phone_number.ilike(term),
            Partner.identity_number.ilike(term)
        ))
    partners = q.order_by(Partner.name).all()
    return render_template(
        'vendors/partners/list.html',
        partners=partners,
        search=s,
        form=form
    )

@vendors_bp.route('/partners/new', methods=['GET', 'POST'], endpoint='partners_create')
@login_required
@permission_required('manage_vendors')
def partners_create():
    form = PartnerForm()
    if form.validate_on_submit():
        partner = Partner()
        form.populate_obj(partner)
        db.session.add(partner)
        try:
            db.session.commit()
            flash('✅ تم إضافة الشريك بنجاح', 'success')
            return redirect(url_for('vendors.partners_list'))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ أثناء إضافة الشريك: {e}', 'danger')
    # تأكد من تمرير partner=None حتى يظهر شريط الأزرار والإحصاءات في قالب form
    return render_template(
        'vendors/partners/form.html',
        form=form,
        partner=None
    )
@vendors_bp.route('/partners/<int:id>/edit', methods=['GET', 'POST'], endpoint='partners_edit')
@login_required
@permission_required('manage_vendors')
def partners_edit(id):
    partner = Partner.query.get_or_404(id)
    form = PartnerForm(obj=partner)
    if form.validate_on_submit():
        form.populate_obj(partner)
        try:
            db.session.commit()
            flash('✅ تم تحديث الشريك بنجاح', 'success')
            return redirect(url_for('vendors.partners_list'))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ أثناء تحديث الشريك: {e}', 'danger')
    return render_template('vendors/partners/form.html', form=form, partner=partner)

@vendors_bp.route('/partners/<int:id>/delete', methods=['POST'], endpoint='partners_delete')
@login_required
@permission_required('manage_vendors')
def partners_delete(id):
    partner = Partner.query.get_or_404(id)
    try:
        db.session.delete(partner)
        db.session.commit()
        flash('✅ تم حذف الشريك بنجاح', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ أثناء حذف الشريك: {e}', 'danger')
    return redirect(url_for('vendors.partners_list'))

@vendors_bp.route('/partners/<int:id>/payments', methods=['GET'], endpoint='partner_payments')
@login_required
@permission_required('manage_vendors')
def partner_payments(id):
    partner = Partner.query.get_or_404(id)
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('ITEMS_PER_PAGE', 10)

    query = Payment.query.filter_by(
        partner_id=id,
        entity_type=PaymentEntityType.PARTNER.value,
        direction=PaymentDirection.OUTGOING.value
    )
    pagination = query.order_by(Payment.payment_date.desc()) \
                      .paginate(page=page, per_page=per_page, error_out=False)

    total_paid = db.session.query(
        func.coalesce(func.sum(Payment.total_amount), 0)
    ).filter(
        Payment.partner_id == id,
        Payment.entity_type == PaymentEntityType.PARTNER.value,
        Payment.direction == PaymentDirection.OUTGOING.value
    ).scalar()

    return render_template(
        'payments/list.html',
        entity=partner,
        entity_type='partner',
        entity_name='الشريك',
        pagination=pagination,
        total_paid=total_paid
    )

@vendors_bp.route('/partners/<int:id>/pay', methods=['GET'], endpoint='partner_pay')
@login_required
@permission_required('manage_vendors')
def partner_pay(id):
    return redirect(url_for('payments.create_payment', entity_type='partner', entity_id=id))
