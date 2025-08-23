# -*- coding: utf-8 -*-
from datetime import datetime
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from extensions import db
from forms import ShipmentForm
from models import Shipment, ShipmentItem, ShipmentPartner, Partner, Product, Warehouse
from utils import permission_required, format_currency

shipments_bp = Blueprint("shipments_bp", __name__, url_prefix="/shipments")


def _apply_arrival(sh: Shipment) -> None:
    from models import StockLevel
    for it in sh.items:
        if not (it.product_id and it.warehouse_id and (it.quantity or 0) > 0):
            continue
        sl = StockLevel.query.filter_by(product_id=it.product_id, warehouse_id=it.warehouse_id).first()
        if not sl:
            sl = StockLevel(product_id=it.product_id, warehouse_id=it.warehouse_id, quantity=0, reserved_quantity=0)
            db.session.add(sl)
            db.session.flush()
        sl.quantity = (sl.quantity or 0) + int(it.quantity or 0)


def _wants_json() -> bool:
    accept = request.headers.get("Accept", "")
    return ("application/json" in accept and "text/html" not in accept) or (request.args.get("format") == "json")


def _sa_get_or_404(model, ident, options=None):
    if options:
        q = db.session.query(model)
        for opt in (options if isinstance(options, (list, tuple)) else (options,)):
            q = q.options(opt)
        obj = q.filter_by(id=ident).first()
    else:
        obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj


def _next_shipment_number() -> str:
    last = Shipment.query.order_by(Shipment.id.desc()).first()
    next_id = (last.id + 1) if last else 1
    return f"SH-{datetime.utcnow():%Y%m%d}-{next_id:04d}"


def _D(x):
    try:
        return Decimal(str(x or 0))
    except Exception:
        return Decimal(0)


def _compute_totals(sh: Shipment) -> None:
    items_total = sum((_D(it.quantity) * _D(it.unit_cost)) for it in sh.items)
    sh.value_before = items_total
    extras = _D(sh.shipping_cost) + _D(sh.customs) + _D(sh.vat) + _D(sh.insurance)
    sh.total_value = items_total + extras


@shipments_bp.route("/", methods=["GET"], endpoint="list_shipments")
@login_required
@permission_required("manage_warehouses")
def list_shipments():
    q = Shipment.query.options(
        joinedload(Shipment.items),
        joinedload(Shipment.partners).joinedload(ShipmentPartner.partner),
        joinedload(Shipment.destination_warehouse),
    )
    status = (request.args.get("status") or "").strip()
    search = (request.args.get("search") or "").strip()
    if status:
        q = q.filter(Shipment.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            Shipment.shipment_number.ilike(like),
            Shipment.tracking_number.ilike(like),
            Shipment.origin.ilike(like),
            Shipment.carrier.ilike(like),
            Shipment.destination.ilike(like),
            Shipment.destination_warehouse.has(Warehouse.name.ilike(like)),
        ))
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    pagination = q.order_by(Shipment.expected_arrival.desc()).paginate(page=page, per_page=per_page, error_out=False)
    if _wants_json():
        return jsonify({
            "data": [{
                "id": s.id,
                "number": s.shipment_number,
                "status": s.status,
                "origin": s.origin,
                "destination": (s.destination_warehouse.name if s.destination_warehouse else (s.destination or None)),
                "expected_arrival": s.expected_arrival.isoformat() if s.expected_arrival else None,
                "total_value": float(s.total_value or 0),
            } for s in pagination.items],
            "meta": {"page": pagination.page, "pages": pagination.pages, "total": pagination.total}
        })
    return render_template("warehouses/shipments.html", shipments=pagination.items, pagination=pagination, search=search, status=status)


shipments_bp.add_url_rule("/", endpoint="shipments", view_func=list_shipments)


@shipments_bp.route("/create", methods=["GET", "POST"], endpoint="create_shipment")
@login_required
@permission_required("manage_warehouses")
def create_shipment():
    form = ShipmentForm()
    pre_dest_id = request.args.get("destination_id", type=int)

    if request.method == "GET":
        if not getattr(form.items, "entries", []):
            form.items.append_entry()
        if not getattr(form.partners, "entries", []):
            form.partners.append_entry()

    if pre_dest_id and not form.destination_id.data:
        dest_obj = db.session.get(Warehouse, pre_dest_id)
        if dest_obj:
            form.destination_id.data = dest_obj

    if form.validate_on_submit():
        dest_obj = form.destination_id.data
        sh = Shipment(
            shipment_number=form.shipment_number.data or _next_shipment_number(),
            shipment_date=form.shipment_date.data,
            expected_arrival=form.expected_arrival.data,
            actual_arrival=form.actual_arrival.data,
            origin=form.origin.data,
            destination_id=(dest_obj.id if dest_obj else None),
            carrier=form.carrier.data,
            tracking_number=form.tracking_number.data,
            status=form.status.data,
            value_before=None,
            shipping_cost=form.shipping_cost.data,
            customs=form.customs.data,
            vat=form.vat.data,
            insurance=form.insurance.data,
            total_value=None,
            notes=form.notes.data,
            currency=form.currency.data,
            sale_id=(form.sale_id.data.id if form.sale_id.data else None),
        )
        db.session.add(sh)
        db.session.flush()

        for entry in getattr(form.items, "entries", []):
            f = getattr(entry, "form", entry)
            db.session.add(ShipmentItem(
                shipment_id=sh.id,
                product_id=f.product_id.data,
                warehouse_id=f.warehouse_id.data,
                quantity=f.quantity.data,
                unit_cost=f.unit_cost.data or 0,
                declared_value=f.declared_value.data or 0,
                notes=(f.notes.data or None),
            ))

        for entry in getattr(form.partners, "entries", []):
            f = getattr(entry, "form", entry)
            if f.partner_id.data:
                db.session.add(ShipmentPartner(
                    shipment_id=sh.id,
                    partner_id=f.partner_id.data,
                    share_percentage=f.share_percentage.data or 0,
                    share_amount=f.share_amount.data or 0,
                    identity_number=f.identity_number.data,
                    phone_number=f.phone_number.data,
                    address=f.address.data,
                    unit_price_before_tax=f.unit_price_before_tax.data or 0,
                    expiry_date=f.expiry_date.data,
                    notes=f.notes.data,
                    role=f.role.data,
                ))

        _compute_totals(sh)

        if (sh.status or "").upper() == "ARRIVED":
            _apply_arrival(sh)

        try:
            db.session.commit()
            flash("✅ تم إنشاء الشحنة بنجاح", "success")
            dest_id = sh.destination_id or (dest_obj.id if dest_obj else None)
            return redirect(url_for("warehouse_bp.detail", warehouse_id=dest_id)) if dest_id else redirect(url_for("shipments_bp.list_shipments"))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"⚠️ خطأ أثناء إنشاء الشحنة: {e}", "danger")

    return render_template("warehouses/shipment_form.html", form=form, shipment=None)


@shipments_bp.route("/<int:id>/edit", methods=["GET", "POST"], endpoint="edit_shipment")
@login_required
@permission_required("manage_warehouses")
def edit_shipment(id: int):
    sh = _sa_get_or_404(Shipment, id, options=[joinedload(Shipment.items), joinedload(Shipment.partners)])
    old_status = (sh.status or "").upper()
    form = ShipmentForm(obj=sh)

    if request.method == "GET":
        form.partners.entries.clear()
        for p in sh.partners:
            form.partners.append_entry({
                "partner_id": p.partner_id,
                "share_percentage": p.share_percentage,
                "share_amount": p.share_amount,
                "identity_number": p.identity_number,
                "phone_number": p.phone_number,
                "address": p.address,
                "unit_price_before_tax": p.unit_price_before_tax,
                "expiry_date": p.expiry_date,
                "notes": p.notes,
                "role": getattr(p, "role", None),
            })
        form.items.entries.clear()
        for i in sh.items:
            form.items.append_entry({
                "product_id": i.product_id,
                "warehouse_id": i.warehouse_id,
                "quantity": i.quantity,
                "unit_cost": i.unit_cost,
                "declared_value": i.declared_value,
                "notes": i.notes,
            })

    if form.validate_on_submit():
        dest_obj = form.destination_id.data
        sh.shipment_number = form.shipment_number.data or sh.shipment_number or _next_shipment_number()
        sh.shipment_date = form.shipment_date.data
        sh.expected_arrival = form.expected_arrival.data
        sh.actual_arrival = form.actual_arrival.data
        sh.origin = form.origin.data
        sh.destination_id = (dest_obj.id if dest_obj else None)
        sh.carrier = form.carrier.data
        sh.tracking_number = form.tracking_number.data
        sh.status = form.status.data
        sh.shipping_cost = form.shipping_cost.data
        sh.customs = form.customs.data
        sh.vat = form.vat.data
        sh.insurance = form.insurance.data
        sh.notes = form.notes.data
        sh.currency = form.currency.data
        sh.sale_id = (form.sale_id.data.id if form.sale_id.data else None)

        sh.partners.clear()
        sh.items.clear()
        db.session.flush()

        for entry in getattr(form.partners, "entries", []):
            f = getattr(entry, "form", entry)
            if f.partner_id.data:
                sh.partners.append(ShipmentPartner(
                    partner_id=f.partner_id.data,
                    share_percentage=f.share_percentage.data or 0,
                    share_amount=f.share_amount.data or 0,
                    identity_number=f.identity_number.data,
                    phone_number=f.phone_number.data,
                    address=f.address.data,
                    unit_price_before_tax=f.unit_price_before_tax.data or 0,
                    expiry_date=f.expiry_date.data,
                    notes=f.notes.data,
                    role=f.role.data,
                ))

        for entry in getattr(form.items, "entries", []):
            f = getattr(entry, "form", entry)
            sh.items.append(ShipmentItem(
                product_id=f.product_id.data,
                warehouse_id=f.warehouse_id.data,
                quantity=f.quantity.data,
                unit_cost=f.unit_cost.data or 0,
                declared_value=f.declared_value.data or 0,
                notes=(f.notes.data or None),
            ))

        _compute_totals(sh)

        new_status = (sh.status or "").upper()
        if new_status == "ARRIVED" and old_status != "ARRIVED":
            _apply_arrival(sh)

        try:
            db.session.commit()
            flash("✅ تم تحديث بيانات الشحنة", "success")
            dest_id = sh.destination_id
            return redirect(url_for("warehouse_bp.detail", warehouse_id=dest_id)) if dest_id else redirect(url_for("shipments_bp.list_shipments"))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"⚠️ خطأ أثناء التحديث: {e}", "danger")

    return render_template("warehouses/shipment_form.html", form=form, shipment=sh)


@shipments_bp.route("/<int:id>/delete", methods=["POST"], endpoint="delete_shipment")
@login_required
@permission_required("manage_warehouses")
def delete_shipment(id: int):
    sh = _sa_get_or_404(Shipment, id)
    dest_id = sh.destination_id
    try:
        sh.partners.clear()
        sh.items.clear()
        db.session.flush()
        db.session.delete(sh)
        db.session.commit()
        flash("🗑️ تم حذف الشحنة", "warning")
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"خطأ أثناء الحذف: {e}", "danger")
    return redirect(url_for("warehouse_bp.detail", warehouse_id=dest_id)) if dest_id else redirect(url_for("shipments_bp.list_shipments"))


@shipments_bp.route("/<int:id>", methods=["GET"], endpoint="shipment_detail")
@login_required
@permission_required("manage_warehouses")
def shipment_detail(id: int):
    sh = _sa_get_or_404(Shipment, id, options=[
        joinedload(Shipment.items).joinedload(ShipmentItem.product),
        joinedload(Shipment.partners).joinedload(ShipmentPartner.partner),
        joinedload(Shipment.destination_warehouse),
    ])
    total_paid = sum(float(p.total_amount or 0) for p in getattr(sh, "payments", []))
    if _wants_json():
        return jsonify({
            "shipment": {
                "id": sh.id,
                "number": sh.shipment_number,
                "status": sh.status,
                "origin": sh.origin,
                "destination": (sh.destination_warehouse.name if sh.destination_warehouse else (sh.destination or None)),
                "expected_arrival": sh.expected_arrival.isoformat() if sh.expected_arrival else None,
                "total_value": float(sh.total_value or 0),
                "items": [{"product": (it.product.name if it.product else None), "warehouse_id": it.warehouse_id, "quantity": it.quantity, "unit_cost": float(it.unit_cost or 0), "declared_value": float(it.declared_value or 0), "notes": it.notes} for it in sh.items],
                "partners": [{"partner": (ln.partner.name if ln.partner else None), "share_percentage": float(ln.share_percentage or 0), "share_amount": float(ln.share_amount or 0)} for ln in sh.partners],
                "total_paid": total_paid,
            }
        })
    return render_template("warehouses/shipment_detail.html", shipment=sh, total_paid=total_paid, format_currency=format_currency)
