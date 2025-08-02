# shipments.py
from datetime import datetime
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, abort, jsonify
)
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_
from extensions import db
from forms import ShipmentForm
from models import (
    Shipment, ShipmentItem, ShipmentPartner,
    Partner, Product, Warehouse
)
from utils import permission_required, format_currency

shipments_bp = Blueprint(
    "shipments",
    __name__,
    url_prefix="/shipments",
    template_folder="templates/shipments"
)


def _prepare_form(form: ShipmentForm):
    """تهيئة QuerySelectFields الديناميكية"""
    form.partner_links.partner_id.query = Partner.query.order_by(Partner.name).all()
    form.items.product_id.query       = Product.query.order_by(Product.name).all()
    form.items.warehouse_id.query     = Warehouse.query.order_by(Warehouse.name).all()


@shipments_bp.route("/", methods=["GET"], endpoint="list_shipments")
@login_required
@permission_required("manage_shipments")
def list_shipments():
    """📦 قائمة الشحنات مع دعم البحث وPagination وJSON للـ DataTables"""
    q = Shipment.query
    status = request.args.get("status")
    search = request.args.get("search", "")

    if status:
        q = q.filter(Shipment.status == status)
    if search:
        q = q.filter(or_(
            Shipment.shipment_number.ilike(f"%{search}%"),
            Shipment.tracking_number.ilike(f"%{search}%"),
            Shipment.origin.ilike(f"%{search}%"),
            Shipment.destination.ilike(f"%{search}%")
        ))

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    pagination = q.order_by(Shipment.expected_arrival.desc()) \
                  .paginate(page=page, per_page=per_page, error_out=False)

    if request.is_json or request.args.get("format") == "json":
        return jsonify({
            "data": [{
                "id": s.id,
                "number": s.shipment_number,
                "status": s.status,
                "origin": s.origin,
                "destination": s.destination,
                "expected_arrival": s.expected_arrival.isoformat() if s.expected_arrival else None,
                "total_value": format_currency(s.total_value or 0)
            } for s in pagination.items],
            "meta": {
                "page": pagination.page,
                "pages": pagination.pages,
                "total": pagination.total
            }
        })

    return render_template(
        "shipments/list.html",
        shipments=pagination.items,
        pagination=pagination,
        search=search,
        status=status
    )


@shipments_bp.route("/create", methods=["GET", "POST"], endpoint="create_shipment")
@login_required
@permission_required("manage_shipments")
def create_shipment():
    """➕ إنشاء شحنة جديدة"""
    form = ShipmentForm()
    _prepare_form(form)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render_template("shipments/_form.html", form=form)

    if form.validate_on_submit():
        # رقم شحنة فريد
        last = Shipment.query.order_by(Shipment.id.desc()).first()
        next_id = last.id + 1 if last else 1
        shipment_number = f"SH-{datetime.utcnow():%Y%m%d}-{next_id:04d}"

        sh = Shipment(
            shipment_number=shipment_number,
            origin=form.origin.data,
            destination=form.destination.data,
            carrier=form.carrier.data,
            tracking_number=form.tracking_number.data,
            shipment_date=form.shipment_date.data,
            expected_arrival=form.expected_arrival.data,
            actual_arrival=form.actual_arrival.data,
            status=form.status.data,
            value_before=form.value_before.data,
            shipping_cost=form.shipping_cost.data,
            customs=form.customs.data,
            vat=form.vat.data,
            insurance=form.insurance.data,
            total_value=form.total_value.data,
            notes=form.notes.data
        )
        db.session.add(sh)

        for entry in form.partner_links.entries:
            ln = entry.form
            sh.partner_links.append(ShipmentPartner(
                partner_id=ln.partner_id.data.id,
                share_percentage=ln.share_percentage.data or 0,
                share_amount=ln.share_amount.data or 0
            ))

        for entry in form.items.entries:
            itm = entry.form
            sh.items.append(ShipmentItem(
                product_id=itm.product_id.data.id,
                warehouse_id=itm.warehouse_id.data.id,
                quantity=itm.quantity.data,
                unit_cost=itm.unit_cost.data or 0
            ))

        try:
            db.session.commit()
            flash("✅ تم إنشاء الشحنة بنجاح", "success")
            return redirect(url_for("shipments.list_shipments"))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"⚠️ خطأ: {e}", "danger")

    return render_template("shipments/form.html", form=form, action="create")


@shipments_bp.route("/<int:id>/edit", methods=["GET", "POST"], endpoint="edit_shipment")
@login_required
@permission_required("manage_shipments")
def edit_shipment(id):
    """✏️ تعديل شحنة"""
    sh = Shipment.query.get_or_404(id)
    form = ShipmentForm(obj=sh)
    _prepare_form(form)

    if request.method == "GET":
        form.partner_links.entries.clear()
        for p in sh.partner_links:
            form.partner_links.append_entry({
                "partner_id": p.partner_id,
                "share_percentage": p.share_percentage,
                "share_amount": p.share_amount
            })
        form.items.entries.clear()
        for i in sh.items:
            form.items.append_entry({
                "product_id": i.product_id,
                "warehouse_id": i.warehouse_id,
                "quantity": i.quantity,
                "unit_cost": i.unit_cost
            })

    if form.validate_on_submit():
        sh.origin            = form.origin.data
        sh.destination       = form.destination.data
        sh.carrier           = form.carrier.data
        sh.tracking_number   = form.tracking_number.data
        sh.shipment_date     = form.shipment_date.data
        sh.expected_arrival  = form.expected_arrival.data
        sh.actual_arrival    = form.actual_arrival.data
        sh.status            = form.status.data
        sh.value_before      = form.value_before.data
        sh.shipping_cost     = form.shipping_cost.data
        sh.customs           = form.customs.data
        sh.vat               = form.vat.data
        sh.insurance         = form.insurance.data
        sh.total_value       = form.total_value.data
        sh.notes             = form.notes.data

        sh.partner_links.clear()
        for entry in form.partner_links.entries:
            ln = entry.form
            sh.partner_links.append(ShipmentPartner(
                partner_id=ln.partner_id.data.id,
                share_percentage=ln.share_percentage.data or 0,
                share_amount=ln.share_amount.data or 0
            ))
        sh.items.clear()
        for entry in form.items.entries:
            itm = entry.form
            sh.items.append(ShipmentItem(
                product_id=itm.product_id.data.id,
                warehouse_id=itm.warehouse_id.data.id,
                quantity=itm.quantity.data,
                unit_cost=itm.unit_cost.data or 0
            ))

        try:
            db.session.commit()
            flash("✅ تم تحديث بيانات الشحنة", "success")
            return redirect(url_for("shipments.shipment_detail", id=id))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"⚠️ خطأ: {e}", "danger")

    return render_template("shipments/form.html", form=form, shipment=sh, action="edit")


@shipments_bp.route("/<int:id>/delete", methods=["POST"], endpoint="delete_shipment")
@login_required
@permission_required("manage_shipments")
def delete_shipment(id):
    """🗑️ حذف شحنة"""
    sh = Shipment.query.get_or_404(id)
    sh.partner_links.clear()
    sh.items.clear()
    db.session.flush()
    db.session.delete(sh)
    try:
        db.session.commit()
        flash("⚠️ تم حذف الشحنة بنجاح", "warning")
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"خطأ أثناء الحذف: {e}", "danger")
    return redirect(url_for("shipments.list_shipments"))


@shipments_bp.route("/<int:id>", methods=["GET"], endpoint="shipment_detail")
@login_required
@permission_required("manage_shipments")
def shipment_detail(id):
    """📄 تفاصيل الشحنة مع دفعاتها"""
    sh = Shipment.query.options(
        db.joinedload(Shipment.items),
        db.joinedload(Shipment.partner_links).joinedload(ShipmentPartner.partner),
        db.joinedload(Shipment.payments)
    ).get_or_404(id)
    total_paid = sum(p.amount for p in sh.payments)
    return render_template(
        "shipments/detail.html",
        shipment=sh,
        total_paid=total_paid,
        format_currency=format_currency
    )


@shipments_bp.route("/<int:id>/payments", methods=["GET"], endpoint="shipment_payments")
@login_required
@permission_required("manage_shipments")
def shipment_payments(id):
    """💰 دفعات شحنة معينة (تكامل مع بلوبيرنت الدفع الموحد)"""
    sh = Shipment.query.get_or_404(id)
    payments = sh.payments.order_by(Shipment.payments.property.mapper.class_.payment_date.desc()).all()
    total_paid = sum(p.amount for p in payments)
    return render_template(
        "payments/list.html",
        entity=sh,
        payments=payments,
        total_paid=total_paid,
        entity_type="shipment",
        entity_name="الشحنة"
    )


@shipments_bp.route("/<int:id>/pay_customs", methods=["POST"], endpoint="pay_customs")
@login_required
@permission_required("manage_shipments")
def pay_customs(id):
    """
    🔸 دفع جمارك الشحنة عبر النظام الموحد.
    يوجه المستخدم إلى نموذج إنشاء دفعة مسبق التهيئة.
    """
    sh = Shipment.query.get_or_404(id)
    if not sh.customs or sh.customs <= 0:
        flash("لا توجد جمارك للدفع لهذه الشحنة.", "warning")
        return redirect(url_for("shipments.shipment_detail", id=id))

    return redirect(
        url_for(
            "payments.create_payment",
            entity_type="shipment_customs",
            entity_id=sh.id,
            amount=sh.customs
        )
    )
