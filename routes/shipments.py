from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required

from sqlalchemy import or_, func, desc, asc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from extensions import db
from forms import ShipmentForm
from models import Shipment, ShipmentItem, ShipmentPartner, Partner, Product, Warehouse
from utils import permission_required, format_currency

shipments_bp = Blueprint("shipments_bp", __name__, url_prefix="/shipments")

@shipments_bp.app_context_processor
def _inject_utils():
    return dict(format_currency=format_currency)

_TWOPLACES = Decimal("0.01")

def _D(x):
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")

def _q2(x):
    return _D(x).quantize(_TWOPLACES, rounding=ROUND_HALF_UP)

def _norm_currency(v):
    return (v or "USD").strip().upper()

def _wants_json() -> bool:
    accept = request.headers.get("Accept", "")
    return ("application/json" in accept and "text/html" not in accept) or ((request.args.get("format") or "").lower() == "json")

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

def _compute_totals(sh: Shipment) -> Decimal:
    items_total = sum((_q2(it.quantity) * _q2(it.unit_cost)) for it in sh.items)
    sh.value_before = _q2(items_total)
    extras = _q2(sh.shipping_cost) + _q2(sh.customs) + _q2(sh.vat) + _q2(sh.insurance)
    sh.currency = _norm_currency(sh.currency)
    return _q2(items_total + extras)

_compute_shipment_totals = _compute_totals

def _norm_status(v):
    if hasattr(v, "data"):
        v = v.data
    if v is None:
        return "DRAFT"
    if hasattr(v, "value"):
        v = v.value
    return str(v).upper()

def _landed_allocation(items, extras_total):
    total_value = sum(_q2(it.quantity) * _q2(it.unit_cost) for it in items)
    if total_value <= 0 or _q2(extras_total) <= 0:
        return {i: Decimal("0.00") for i, _ in enumerate(items)}
    alloc = {}
    rem = _q2(extras_total)
    for idx, it in enumerate(items):
        base = _q2(it.quantity) * _q2(it.unit_cost)
        share = (base / total_value) * _q2(extras_total)
        share_q = _q2(share)
        alloc[idx] = share_q
        rem -= share_q
    keys = list(alloc.keys())
    k = 0
    while rem != Decimal("0.00") and keys:
        step = Decimal("0.01") if rem > 0 else Decimal("-0.01")
        alloc[keys[k % len(keys)]] += step
        rem -= step
        k += 1
    return alloc

def _apply_arrival_items(items):
    from models import StockLevel
    for it in items:
        pid = int(it.get("product_id") or 0)
        wid = int(it.get("warehouse_id") or 0)
        qty = int(it.get("quantity") or 0)
        if not (pid and wid and qty > 0):
            continue
        sl = (
            db.session.query(StockLevel)
            .filter_by(product_id=pid, warehouse_id=wid)
            .with_for_update(read=False)
            .first()
        )
        if not sl:
            sl = StockLevel(product_id=pid, warehouse_id=wid, quantity=0, reserved_quantity=0)
            db.session.add(sl)
            db.session.flush()
        new_qty = int(sl.quantity or 0) + qty
        reserved = int(getattr(sl, "reserved_quantity", 0) or 0)
        if new_qty < reserved:
            raise ValueError("insufficient stock")
        sl.quantity = new_qty
        db.session.flush()

def _reverse_arrival_items(items):
    from models import StockLevel
    for it in items:
        pid = int(it.get("product_id") or 0)
        wid = int(it.get("warehouse_id") or 0)
        qty = int(it.get("quantity") or 0)
        if not (pid and wid and qty > 0):
            continue
        sl = (
            db.session.query(StockLevel)
            .filter_by(product_id=pid, warehouse_id=wid)
            .with_for_update(read=False)
            .first()
        )
        if not sl:
            raise ValueError("insufficient stock")
        reserved = int(getattr(sl, "reserved_quantity", 0) or 0)
        new_qty = int(sl.quantity or 0) - qty
        if new_qty < 0 or new_qty < reserved:
            raise ValueError("insufficient stock")
        sl.quantity = new_qty
        db.session.flush()

def _items_snapshot(sh):
    return [
        {
            "product_id": int(i.product_id or 0),
            "warehouse_id": int(i.warehouse_id or 0),
            "quantity": int(i.quantity or 0),
        }
        for i in sh.items
    ]

@shipments_bp.route("/", methods=["GET"], endpoint="list_shipments")
@login_required
@permission_required("manage_warehouses")
def list_shipments():
    q = db.session.query(Shipment).options(
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
        q = q.filter(
            or_(
                Shipment.shipment_number.ilike(like),
                Shipment.tracking_number.ilike(like),
                Shipment.origin.ilike(like),
                Shipment.carrier.ilike(like),
                Shipment.destination.ilike(like),
                Shipment.destination_warehouse.has(Warehouse.name.ilike(like)),
            )
        )
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    pagination = q.order_by(
        Shipment.expected_arrival.desc().nullslast(),
        Shipment.id.desc(),
    ).paginate(page=page, per_page=per_page, error_out=False)
    if _wants_json():
        return jsonify(
            {
                "data": [
                    {
                        "id": s.id,
                        "number": s.shipment_number,
                        "status": s.status,
                        "origin": s.origin,
                        "destination": (s.destination_warehouse.name if s.destination_warehouse else (s.destination or None)),
                        "expected_arrival": s.expected_arrival.isoformat() if s.expected_arrival else None,
                        "total_value": float(s.total_value or 0),
                    }
                    for s in pagination.items
                ],
                "meta": {"page": pagination.page, "pages": pagination.pages, "total": pagination.total},
            }
        )
    return render_template("warehouses/shipments.html", shipments=pagination.items, pagination=pagination, search=search, status=status)

shipments_bp.add_url_rule("/", endpoint="shipments", view_func=list_shipments)

def _parse_dt(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

@shipments_bp.route("/data", methods=["GET"])
@login_required
@permission_required("manage_warehouses")
def shipments_data():
    draw   = int(request.args.get("draw", 1))
    start  = int(request.args.get("start", 0))
    length = int(request.args.get("length", 10))
    f_status = (request.args.get("status") or "").strip().upper()
    f_from   = _parse_dt(request.args.get("from") or request.args.get("search[from]", "") or "")
    f_to     = _parse_dt(request.args.get("to") or request.args.get("search[to]", "") or "")
    f_dest   = (request.args.get("destination") or "").strip()
    f_extra  = (request.args.get("search_extra") or request.args.get("search[value]", "") or "").strip()

    base_q = db.session.query(Shipment).options(joinedload(Shipment.destination_warehouse))
    total_count = base_q.count()
    q = base_q

    if f_status:
        q = q.filter(Shipment.status == f_status)
    if f_from:
        q = q.filter(Shipment.expected_arrival >= datetime.combine(f_from, datetime.min.time()))
    if f_to:
        q = q.filter(Shipment.expected_arrival <= datetime.combine(f_to, datetime.max.time()))
    if f_dest:
        like = f"%{f_dest}%"
        q = q.filter(or_(Shipment.destination.ilike(like), Shipment.destination_warehouse.has(Warehouse.name.ilike(like))))
    if f_extra:
        like = f"%{f_extra}%"
        q = q.filter(
            or_(
                Shipment.shipment_number.ilike(like),
                Shipment.tracking_number.ilike(like),
                Shipment.origin.ilike(like),
                Shipment.carrier.ilike(like),
                Shipment.destination.ilike(like),
                Shipment.destination_warehouse.has(Warehouse.name.ilike(like)),
            )
        )

    order_col_index = int(request.args.get("order[0][column]", 3) or 3)
    order_dir = (request.args.get("order[0][dir]") or "desc").lower()
    col_map = {1: Shipment.shipment_number, 3: Shipment.expected_arrival, 4: Shipment.status, 5: Shipment.total_value}
    order_col = col_map.get(order_col_index, Shipment.expected_arrival)
    q = q.order_by(desc(order_col) if order_dir == "desc" else asc(order_col))

    filtered_count = q.count()
    rows = q.offset(start).limit(length).all()

    data = []
    for s in rows:
        actions_html = f"""
        <div class="btn-group btn-group-sm" role="group">
            <a href="{url_for('shipments_bp.shipment_detail', id=s.id)}" class="btn btn-info" title="تفاصيل"><i class="fa fa-eye"></i></a>
            <a href="{url_for('shipments_bp.edit_shipment', id=s.id)}" class="btn btn-warning" title="تعديل"><i class="fa fa-edit"></i></a>
            <form method="POST" action="{url_for('shipments_bp.delete_shipment', id=s.id)}" style="display:inline;" onsubmit="return confirm('تأكيد الحذف؟');">
                <button type="submit" class="btn btn-danger" title="حذف"><i class="fa fa-trash"></i></button>
            </form>
        </div>
        """
        data.append({
            "id": s.id,
            "number": s.shipment_number,
            "status": s.status,
            "origin": s.origin,
            "destination": (s.destination_warehouse.name if s.destination_warehouse else (s.destination or None)),
            "expected_arrival": s.expected_arrival.isoformat() if s.expected_arrival else None,
            "total_value": float(s.total_value or 0),
            "actions": actions_html,
        })

    return jsonify({"draw": draw, "recordsTotal": total_count, "recordsFiltered": filtered_count, "data": data})


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
        if not form.shipment_date.data:
            form.shipment_date.data = datetime.utcnow()
        if not form.expected_arrival.data:
            form.expected_arrival.data = datetime.utcnow() + timedelta(days=14)

    if pre_dest_id and not form.destination_id.data:
        dest_prefill = db.session.get(Warehouse, pre_dest_id)
        if dest_prefill:
            form.destination_id.data = dest_prefill

    if form.validate_on_submit():
        dest_obj = form.destination_id.data
        sh = Shipment(
            shipment_number=form.shipment_number.data or None,
            shipment_date=form.shipment_date.data or datetime.utcnow(),
            expected_arrival=form.expected_arrival.data,
            actual_arrival=form.actual_arrival.data,
            origin=form.origin.data or None,
            destination_id=(form.destination_id.data.id if getattr(form.destination_id.data, "id", None) else (form.destination_id.data if isinstance(form.destination_id.data, int) else None)),
            carrier=form.carrier.data or None,
            tracking_number=form.tracking_number.data or None,
            status=_norm_status(form.status.data),
            shipping_cost=form.shipping_cost.data,
            customs=form.customs.data,
            vat=form.vat.data,
            insurance=form.insurance.data,
            notes=form.notes.data or None,
            currency=_norm_currency(getattr(form, "currency", None) and form.currency.data),
            sale_id=(form.sale_id.data.id if getattr(form, "sale_id", None) and getattr(form.sale_id.data, "id", None) else None),
        )

        db.session.add(sh)
        db.session.flush()

        for entry in getattr(form.items, "entries", []):
            f = getattr(entry, "form", entry)
            wid = f.warehouse_id.data or (dest_obj.id if dest_obj else None)
            db.session.add(
                ShipmentItem(
                    shipment_id=sh.id,
                    product_id=f.product_id.data,
                    warehouse_id=wid,
                    quantity=f.quantity.data,
                    unit_cost=f.unit_cost.data or 0,
                    declared_value=f.declared_value.data or 0,
                    notes=f.notes.data or None,
                )
            )

        for entry in getattr(form.partners, "entries", []):
            f = getattr(entry, "form", entry)
            if f.partner_id.data:
                db.session.add(
                    ShipmentPartner(
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
                    )
                )

        db.session.flush()

        extras_total = _q2(sh.shipping_cost) + _q2(sh.customs) + _q2(sh.vat) + _q2(sh.insurance)
        alloc = _landed_allocation(sh.items, extras_total)
        for idx, it in enumerate(sh.items):
            extra = alloc.get(idx, Decimal("0.00"))
            it.landed_extra_share = _q2(extra)
            qty = _q2(it.quantity)
            base_total = qty * _q2(it.unit_cost)
            landed_total = base_total + _q2(extra)
            it.landed_unit_cost = _q2((landed_total / qty) if qty > 0 else 0)

        _compute_shipment_totals(sh)

        if (sh.status or "").upper() == "ARRIVED":
            _apply_arrival_items(
                [{"product_id": it.product_id, "warehouse_id": it.warehouse_id, "quantity": it.quantity} for it in sh.items]
            )

        try:
            db.session.commit()
            flash("تم إنشاء الشحنة بنجاح", "success")
            dest_id = sh.destination_id or (dest_obj.id if dest_obj else None)
            return redirect(url_for("warehouse_bp.detail", warehouse_id=dest_id)) if dest_id else redirect(url_for("shipments_bp.list_shipments"))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"خطأ أثناء إنشاء الشحنة: {e}", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"تعذر إتمام العملية: {e}", "danger")

    return render_template("warehouses/shipment_form.html", form=form, shipment=None)

@shipments_bp.route("/<int:id>/edit", methods=["GET", "POST"], endpoint="edit_shipment")
@login_required
@permission_required("manage_warehouses")
def edit_shipment(id: int):
    sh = _sa_get_or_404(Shipment, id, options=[joinedload(Shipment.items), joinedload(Shipment.partners)])
    old_status = (sh.status or "").upper()
    old_items = _items_snapshot(sh)
    form = ShipmentForm(obj=sh)

    if request.method == "GET":
        form.partners.entries.clear()
        for p in sh.partners:
            form.partners.append_entry(
                {
                    "partner_id": p.partner_id,
                    "share_percentage": p.share_percentage,
                    "share_amount": p.share_amount,
                    "identity_number": p.identity_number,
                    "phone_number": p.phone_number,
                    "address": p.address,
                    "unit_price_before_tax": p.unit_price_before_tax,
                    "expiry_date": p.expiry_date,
                    "notes": p.notes,
                }
            )
        if not getattr(form.partners, "entries", []):
            form.partners.append_entry({})

        form.items.entries.clear()
        for i in sh.items:
            form.items.append_entry(
                {
                    "product_id": i.product_id,
                    "warehouse_id": i.warehouse_id,
                    "quantity": i.quantity,
                    "unit_cost": i.unit_cost,
                    "declared_value": i.declared_value,
                    "notes": i.notes,
                }
            )
        if not getattr(form.items, "entries", []):
            form.items.append_entry({})

    if request.method == "POST" and not form.validate_on_submit():
        if _wants_json():
            return jsonify({"ok": False, "errors": form.errors}), 422
        flash("تحقق من الحقول المطلوبة", "danger")

    if form.validate_on_submit():
        dest_obj = form.destination_id.data
        sh.shipment_number = form.shipment_number.data or sh.shipment_number or None
        sh.shipment_date = form.shipment_date.data
        sh.expected_arrival = form.expected_arrival.data
        sh.actual_arrival = form.actual_arrival.data
        sh.origin = form.origin.data
        sh.destination_id = (dest_obj.id if dest_obj else None)
        sh.carrier = form.carrier.data
        sh.tracking_number = form.tracking_number.data
        sh.status = _norm_status(form.status.data)
        sh.shipping_cost = form.shipping_cost.data
        sh.customs = form.customs.data
        sh.vat = form.vat.data
        sh.insurance = form.insurance.data
        sh.notes = form.notes.data
        sh.currency = _norm_currency(getattr(form, "currency", None) and form.currency.data)
        sh.sale_id = (form.sale_id.data.id if getattr(form, "sale_id", None) and form.sale_id.data else None)

        sh.partners.clear()
        sh.items.clear()
        db.session.flush()

        for entry in getattr(form.partners, "entries", []):
            f = getattr(entry, "form", entry)
            if f.partner_id.data:
                sh.partners.append(
                    ShipmentPartner(
                        partner_id=f.partner_id.data,
                        share_percentage=f.share_percentage.data or 0,
                        share_amount=f.share_amount.data or 0,
                        identity_number=f.identity_number.data,
                        phone_number=f.phone_number.data,
                        address=f.address.data,
                        unit_price_before_tax=f.unit_price_before_tax.data or 0,
                        expiry_date=f.expiry_date.data,
                        notes=f.notes.data,
                    )
                )

        for entry in getattr(form.items, "entries", []):
            f = getattr(entry, "form", entry)
            sh.items.append(
                ShipmentItem(
                    product_id=f.product_id.data,
                    warehouse_id=f.warehouse_id.data,
                    quantity=f.quantity.data,
                    unit_cost=f.unit_cost.data or 0,
                    declared_value=f.declared_value.data or 0,
                    notes=(f.notes.data or None),
                )
            )

        db.session.flush()

        extras_total = _q2(sh.shipping_cost) + _q2(sh.customs) + _q2(sh.vat) + _q2(sh.insurance)
        alloc = _landed_allocation(sh.items, extras_total)
        for idx, it in enumerate(sh.items):
            extra = alloc.get(idx, Decimal("0.00"))
            it.landed_extra_share = _q2(extra)
            qty = _q2(it.quantity)
            base_total = qty * _q2(it.unit_cost)
            landed_total = base_total + _q2(extra)
            it.landed_unit_cost = _q2((landed_total / qty) if qty > 0 else 0)

        _compute_shipment_totals(sh)

        new_items = _items_snapshot(sh)
        new_status = (sh.status or "").upper()

        try:
            if old_status == "ARRIVED" and new_status != "ARRIVED":
                _reverse_arrival_items(old_items)
            elif old_status != "ARRIVED" and new_status == "ARRIVED":
                _apply_arrival_items(new_items)
            elif old_status == "ARRIVED" and new_status == "ARRIVED":
                _reverse_arrival_items(old_items)
                _apply_arrival_items(new_items)

            db.session.commit()

            if _wants_json():
                return jsonify({"ok": True, "shipment_id": sh.id, "number": sh.shipment_number})

            flash("تم تحديث بيانات الشحنة", "success")
            dest_id = sh.destination_id
            return redirect(url_for("warehouse_bp.detail", warehouse_id=dest_id)) if dest_id else redirect(url_for("shipments_bp.list_shipments"))
        except SQLAlchemyError as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({"ok": False, "error": str(e)}), 500
            flash(f"خطأ أثناء التحديث: {e}", "danger")
        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({"ok": False, "error": str(e)}), 400
            flash(f"خطأ أثناء ضبط المخزون: {e}", "danger")

    return render_template("warehouses/shipment_form.html", form=form, shipment=sh)

@shipments_bp.route("/<int:id>/delete", methods=["POST"], endpoint="delete_shipment")
@login_required
@permission_required("manage_warehouses")
def delete_shipment(id: int):
    sh = _sa_get_or_404(Shipment, id, options=[joinedload(Shipment.items)])
    dest_id = sh.destination_id
    try:
        if (sh.status or "").upper() == "ARRIVED":
            _reverse_arrival_items(_items_snapshot(sh))
        sh.partners.clear()
        sh.items.clear()
        db.session.flush()
        db.session.delete(sh)
        db.session.commit()
        if _wants_json():
            return jsonify({"ok": True})
        flash("تم حذف الشحنة", "warning")
    except SQLAlchemyError as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({"ok": False, "error": str(e)}), 500
        flash(f"خطأ أثناء الحذف: {e}", "danger")
    except Exception as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(f"خطأ أثناء ضبط المخزون: {e}", "danger")
    return redirect(url_for("warehouse_bp.detail", warehouse_id=dest_id)) if dest_id else redirect(url_for("shipments_bp.list_shipments"))

@shipments_bp.route("/<int:id>", methods=["GET"], endpoint="shipment_detail")
@login_required
@permission_required("manage_warehouses")
def shipment_detail(id: int):
    sh = _sa_get_or_404(
        Shipment,
        id,
        options=[
            joinedload(Shipment.items).joinedload(ShipmentItem.product),
            joinedload(Shipment.partners).joinedload(ShipmentPartner.partner),
            joinedload(Shipment.destination_warehouse),
        ],
    )
    try:
        from models import Payment, PaymentStatus
        total_paid = (
            db.session.query(func.coalesce(func.sum(Payment.total_amount), 0.0))
            .filter(Payment.shipment_id == sh.id, Payment.status == PaymentStatus.COMPLETED.value)
            .scalar()
            or 0.0
        )
    except Exception:
        total_paid = sum(float(p.total_amount or 0) for p in getattr(sh, "payments", []))
    if _wants_json():
        return jsonify(
            {
                "shipment": {
                    "id": sh.id,
                    "number": sh.shipment_number,
                    "status": sh.status,
                    "origin": sh.origin,
                    "destination": (sh.destination_warehouse.name if sh.destination_warehouse else (sh.destination or None)),
                    "expected_arrival": sh.expected_arrival.isoformat() if sh.expected_arrival else None,
                    "total_value": float(sh.total_value or 0),
                    "items": [
                        {
                            "product": (it.product.name if it.product else None),
                            "warehouse_id": it.warehouse_id,
                            "quantity": it.quantity,
                            "unit_cost": float(it.unit_cost or 0),
                            "declared_value": float(it.declared_value or 0),
                            "landed_extra_share": float(it.landed_extra_share or 0),
                            "landed_unit_cost": float(it.landed_unit_cost or 0),
                            "notes": it.notes,
                        }
                        for it in sh.items
                    ],
                    "partners": [
                        {
                            "partner": (ln.partner.name if ln.partner else None),
                            "share_percentage": float(ln.share_percentage or 0),
                            "share_amount": float(ln.share_amount or 0),
                        }
                        for ln in sh.partners
                    ],
                    "total_paid": float(total_paid or 0),
                }
            }
        )
    return render_template("warehouses/shipment_detail.html", shipment=sh, total_paid=total_paid, format_currency=format_currency)

@shipments_bp.route("/<int:id>/mark-arrived", methods=["POST"])
@login_required
@permission_required("manage_warehouses")
def mark_arrived(id:int):
    sh = _sa_get_or_404(Shipment, id, options=[joinedload(Shipment.items)])
    if (sh.status or "").upper() == "ARRIVED":
        flash("الشحنة معلّمة بواصل مسبقاً", "info")
        return redirect(url_for("shipments_bp.shipment_detail", id=sh.id))
    try:
        _apply_arrival_items([{"product_id": it.product_id, "warehouse_id": it.warehouse_id, "quantity": it.quantity} for it in sh.items])
        sh.status = "ARRIVED"
        sh.actual_arrival = sh.actual_arrival or datetime.utcnow()
        _compute_totals(sh)
        db.session.commit()
        flash("تم اعتماد وصول الشحنة وتحديث المخزون", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"تعذّر اعتماد الوصول: {e}", "danger")
    return redirect(url_for("shipments_bp.shipment_detail", id=sh.id))

@shipments_bp.route("/<int:id>/cancel", methods=["POST"])
@login_required
@permission_required("manage_warehouses")
def cancel_shipment(id:int):
    sh = _sa_get_or_404(Shipment, id, options=[joinedload(Shipment.items)])
    try:
        if (sh.status or "").upper() == "ARRIVED":
            _reverse_arrival_items(_items_snapshot(sh))
        sh.status = "CANCELLED"
        db.session.commit()
        flash("تم إلغاء الشحنة", "warning")
    except Exception as e:
        db.session.rollback()
        flash(f"تعذّر الإلغاء: {e}", "danger")
    return redirect(url_for("shipments_bp.shipment_detail", id=sh.id))
