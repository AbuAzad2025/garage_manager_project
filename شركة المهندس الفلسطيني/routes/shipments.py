
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, abort
)
from flask_login import login_required
from flask_wtf.csrf import generate_csrf

from sqlalchemy import or_, func, desc, asc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from extensions import db
from forms import ShipmentForm
from models import (
    Shipment, ShipmentItem, ShipmentPartner,
    Partner, Product, Warehouse
)
import utils

shipments_bp = Blueprint("shipments_bp", __name__, url_prefix="/shipments")

@shipments_bp.app_context_processor
def _inject_utils():
    return dict(format_currency=utils.format_currency)

from utils import D as _D, _q2

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
    from models import StockLevel, Warehouse, WarehouseType
    for it in items:
        pid = int(it.get("product_id") or 0)
        wid = int(it.get("warehouse_id") or 0)
        qty = int(it.get("quantity") or 0)
        if not (pid and wid and qty > 0):
            continue
        
        # التحقق من نوع المستودع
        warehouse = db.session.get(Warehouse, wid)
        if not warehouse:
            continue
            
        # إذا كان المستودع من نوع PARTNER، تأكد من وجود شريك
        if warehouse.warehouse_type == WarehouseType.PARTNER.value:
            if not warehouse.partner_id:
                raise ValueError(f"مستودع الشريك {warehouse.name} غير مربوط بشريك")
        
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
    from models import StockLevel, Warehouse, WarehouseType
    for it in items:
        pid = int(it.get("product_id") or 0)
        wid = int(it.get("warehouse_id") or 0)
        qty = int(it.get("quantity") or 0)
        if not (pid and wid and qty > 0):
            continue
        
        # التحقق من نوع المستودع
        warehouse = db.session.get(Warehouse, wid)
        if not warehouse:
            continue
            
        # إذا كان المستودع من نوع PARTNER، تأكد من وجود شريك
        if warehouse.warehouse_type == WarehouseType.PARTNER.value:
            if not warehouse.partner_id:
                raise ValueError(f"مستودع الشريك {warehouse.name} غير مربوط بشريك")
        
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

def _ensure_partner_warehouse(warehouse_id):
    """تأكد من أن المستودع مربوط بشريك إذا كان من نوع PARTNER"""
    from models import Warehouse, WarehouseType
    warehouse = db.session.get(Warehouse, warehouse_id)
    if not warehouse:
        raise ValueError("warehouse_not_found")
    if warehouse.warehouse_type == WarehouseType.PARTNER.value:
        if not warehouse.partner_id:
            raise ValueError("partner_warehouse_requires_partner")
    return warehouse

@shipments_bp.route("/", methods=["GET"], endpoint="list_shipments")
@login_required
# @permission_required("manage_warehouses")  # Commented out
def list_shipments():
    q = db.session.query(Shipment).filter(Shipment.is_archived == False).options(
        joinedload(Shipment.items),
        joinedload(Shipment.partners).joinedload(ShipmentPartner.partner),
        joinedload(Shipment.destination_warehouse),
    )

    status = (request.args.get("status") or "").strip().upper()
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
    pagination = q.order_by(
        Shipment.expected_arrival.desc().nullslast(),
        Shipment.id.desc(),
    ).paginate(page=page, per_page=per_page, error_out=False)

    def _status_label(st):
        return {
            "DRAFT": "مسودة",
            "PENDING": "قيد الانتظار",
            "IN_TRANSIT": "قيد النقل",
            "IN_CUSTOMS": "في الجمارك",
            "ARRIVED": "وصلت",
            "DELIVERED": "تم التسليم",
            "CANCELLED": "ملغاة",
            "RETURNED": "مرتجعة",
            "CREATED": "مُنشأة"
        }.get((st or "").upper(), st)

    if _wants_json():
        return jsonify({
            "data": [
                {
                    "id": s.id,
                    "number": s.shipment_number,
                    "status": s.status,
                    "status_label": _status_label(s.status),
                    "origin": s.origin,
                    "destination": (s.destination_warehouse.name if s.destination_warehouse else (s.destination or None)),
                    "expected_arrival": s.expected_arrival.isoformat() if s.expected_arrival else None,
                    "total_value": float(s.total_value or 0),
                    "items_count": len(s.items or []),
                    "partners_count": len(s.partners or []),
                }
                for s in pagination.items
            ],
            "meta": {
                "page": pagination.page,
                "pages": pagination.pages,
                "per_page": per_page,
                "total": pagination.total,
            },
        })

    return render_template(
        "warehouses/shipments.html",
        shipments=pagination.items,
        pagination=pagination,
        search=search,
        status=status,
    )


shipments_bp.add_url_rule("/", endpoint="shipments", view_func=list_shipments)


def _parse_dt(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

@shipments_bp.route("/data", methods=["GET"])
@login_required
# @permission_required("manage_warehouses")  # Commented out
def shipments_data():
    from flask_wtf.csrf import generate_csrf

    draw   = int(request.args.get("draw", 1))
    start  = int(request.args.get("start", 0))
    length = int(request.args.get("length", 10))

    f_status = (request.args.get("status") or "").strip().upper()
    f_from   = _parse_dt(request.args.get("from") or request.args.get("search[from]", "") or "")
    f_to     = _parse_dt(request.args.get("to") or request.args.get("search[to]", "") or "")
    f_dest   = (request.args.get("destination") or "").strip()
    f_extra  = (request.args.get("search_extra") or request.args.get("search[value]", "") or "").strip()

    base_q = db.session.query(Shipment).options(joinedload(Shipment.destination_warehouse))
    total_count = db.session.query(func.count(Shipment.id)).scalar()
    q = base_q

    if f_status:
        q = q.filter(Shipment.status == f_status)
    if f_from:
        q = q.filter(Shipment.expected_arrival >= datetime.combine(f_from, datetime.min.time()))
    if f_to:
        q = q.filter(Shipment.expected_arrival <= datetime.combine(f_to, datetime.max.time()))
    if f_dest:
        like = f"%{f_dest}%"
        q = q.filter(or_(
            Shipment.destination.ilike(like),
            Shipment.destination_warehouse.has(Warehouse.name.ilike(like))
        ))
    if f_extra:
        like = f"%{f_extra}%"
        q = q.filter(or_(
            Shipment.shipment_number.ilike(like),
            Shipment.tracking_number.ilike(like),
            Shipment.origin.ilike(like),
            Shipment.carrier.ilike(like),
            Shipment.destination.ilike(like),
            Shipment.destination_warehouse.has(Warehouse.name.ilike(like))
        ))

    order_col_index = int(request.args.get("order[0][column]", 3) or 3)
    order_dir = (request.args.get("order[0][dir]") or "desc").lower()
    col_map = {
        0: Shipment.id,
        1: Shipment.shipment_number,
        2: Shipment.destination,
        3: Shipment.expected_arrival,
        4: Shipment.status,
        5: Shipment.value_before
    }
    order_col = col_map.get(order_col_index, Shipment.expected_arrival)
    q = q.order_by(desc(order_col) if order_dir == "desc" else asc(order_col))

    filtered_count = q.with_entities(func.count(Shipment.id)).scalar()
    rows = q.offset(start).limit(length).all()

    csrf_token = generate_csrf()

    def _status_label(st):
        st = (st or "").upper()
        return {
            "DRAFT": "مسودة",
            "IN_TRANSIT": "في الطريق",
            "ARRIVED": "واصل",
            "CANCELLED": "ملغاة",
            "CREATED": "مُنشأة"
        }.get(st, st)

    data = []
    for s in rows:
        actions_html = f"""
        <div class="btn-group btn-group-sm" role="group">
            <a href="{url_for('shipments_bp.shipment_detail', id=s.id)}" class="btn btn-info" title="تفاصيل"><i class="fa fa-eye"></i></a>
            <a href="{url_for('shipments_bp.edit_shipment', id=s.id)}" class="btn btn-warning" title="تعديل"><i class="fa fa-edit"></i></a>
            <form method="POST" action="{url_for('shipments_bp.delete_shipment', id=s.id)}" style="display:inline;" onsubmit="return confirm('تأكيد الحذف؟');">
                <input type="hidden" name="csrf_token" value="{csrf_token}">
                <button type="submit" class="btn btn-danger" title="حذف"><i class="fa fa-trash"></i></button>
            </form>
        </div>
        """
        data.append({
            "id": s.id,
            "number": s.shipment_number,
            "status": s.status,
            "status_label": _status_label(s.status),
            "origin": s.origin,
            "destination": (s.destination_warehouse.name if s.destination_warehouse else (s.destination or None)),
            "expected_arrival": s.expected_arrival.isoformat() if s.expected_arrival else None,
            "total_value": float(s.total_value or 0),
            "actions": actions_html,
        })

    return jsonify({
        "draw": draw,
        "recordsTotal": total_count,
        "recordsFiltered": filtered_count,
        "data": data
    })

@shipments_bp.route("/create", methods=["GET", "POST"], endpoint="create_shipment")
@login_required
# @permission_required("manage_warehouses")  # Commented out
def create_shipment():
    form = ShipmentForm()
    pre_dest_id = request.args.get("destination_id", type=int)

    if request.method == "GET":
        if not form.shipment_date.data:
            form.shipment_date.data = datetime.utcnow()
        if not form.expected_arrival.data:
            form.expected_arrival.data = datetime.utcnow() + timedelta(days=14)

    if request.method == "POST":
        def _blank_item(f):
            return not (f.product_id.data and (f.warehouse_id.data or form.destination_id.data) and (f.quantity.data or 0) > 0)
        def _blank_partner(f):
            return not f.partner_id.data
        if hasattr(form, "items"):
            form.items.entries[:] = [e for e in form.items.entries if not _blank_item(getattr(e, "form", e))]
        if hasattr(form, "partners"):
            form.partners.entries[:] = [e for e in form.partners.entries if not _blank_partner(getattr(e, "form", e))]

    if pre_dest_id and not form.destination_id.data:
        dest_prefill = db.session.get(Warehouse, pre_dest_id)
        if dest_prefill:
            form.destination_id.data = dest_prefill

    if request.method == "POST" and not form.validate_on_submit():
        if _wants_json():
            return jsonify({"ok": False, "errors": form.errors}), 422
        for field, errors in form.errors.items():
            for err in errors:
                flash(f"❌ {form[field].label.text}: {err}", "danger")
        return render_template("warehouses/shipment_form.html", form=form, shipment=None)

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

        acc_items = {}
        for entry in getattr(form.items, "entries", []):
            f = getattr(entry, "form", entry)
            pid = f.product_id.data
            wid = f.warehouse_id.data or (dest_obj.id if dest_obj else None)
            if not pid or not wid:
                continue
            qty = f.quantity.data or 0
            if qty <= 0:
                continue
            uc = Decimal(str(f.unit_cost.data or 0))
            dec = Decimal(str(f.declared_value.data or 0))
            notes = getattr(f, "notes", None)
            notes_val = notes.data if notes is not None else None
            key = (pid, wid)
            it = acc_items.get(key) or {"qty": 0, "cost_total": Decimal("0"), "declared": Decimal("0"), "notes": None}
            it["qty"] += qty
            it["cost_total"] += Decimal(qty) * uc
            it["declared"] += dec
            it["notes"] = notes_val if notes_val else it["notes"]
            acc_items[key] = it

        for (pid, wid), v in acc_items.items():
            qty = v["qty"]
            unit_cost = (v["cost_total"] / Decimal(qty)) if qty else Decimal("0")
            sh.items.append(ShipmentItem(
                product_id=pid,
                warehouse_id=wid,
                quantity=qty,
                unit_cost=float(unit_cost),
                declared_value=float(v["declared"]),
                notes=v["notes"],
            ))

        acc_partners = {}
        for entry in getattr(form.partners, "entries", []):
            f = getattr(entry, "form", entry)
            pid = f.partner_id.data
            if not pid:
                continue
            p = acc_partners.get(pid) or {
                "share_percentage": Decimal("0"),
                "share_amount": Decimal("0"),
                "identity_number": None,
                "phone_number": None,
                "address": None,
                "unit_price_before_tax": Decimal("0"),
                "expiry_date": None,
                "notes": None,
            }
            p["share_percentage"] += Decimal(str(f.share_percentage.data or 0))
            p["share_amount"] += Decimal(str(f.share_amount.data or 0))
            p["unit_price_before_tax"] += Decimal(str(f.unit_price_before_tax.data or 0))
            p["identity_number"] = f.identity_number.data or p["identity_number"]
            p["phone_number"] = f.phone_number.data or p["phone_number"]
            p["address"] = f.address.data or p["address"]
            p["expiry_date"] = f.expiry_date.data or p["expiry_date"]
            p["notes"] = f.notes.data or p["notes"]
            acc_partners[pid] = p

        for pid, v in acc_partners.items():
            sh.partners.append(ShipmentPartner(
                partner_id=pid,
                share_percentage=float(v["share_percentage"]),
                share_amount=float(v["share_amount"]),
                identity_number=v["identity_number"],
                phone_number=v["phone_number"],
                address=v["address"],
                unit_price_before_tax=float(v["unit_price_before_tax"]),
                expiry_date=v["expiry_date"],
                notes=v["notes"],
            ))

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
            flash("✅ تم إنشاء الشحنة بنجاح", "success")
            dest_id = sh.destination_id or (dest_obj.id if dest_obj else None)
            return redirect(url_for("warehouse_bp.detail", warehouse_id=dest_id)) if dest_id else redirect(url_for("shipments_bp.list_shipments"))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"❌ خطأ أثناء إنشاء الشحنة: {e}", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"❌ تعذر إتمام العملية: {e}", "danger")

    return render_template("warehouses/shipment_form.html", form=form, shipment=None)
@shipments_bp.route("/<int:id>/edit", methods=["GET", "POST"], endpoint="edit_shipment")
@login_required
# @permission_required("manage_warehouses")  # Commented out
def edit_shipment(id: int):
    sh = _sa_get_or_404(Shipment, id, options=[joinedload(Shipment.items), joinedload(Shipment.partners)])
    old_status = (sh.status or "").upper()
    old_items = _items_snapshot(sh)
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

    if request.method == "POST":
        def _blank_item(f):
            return not (f.product_id.data and f.warehouse_id.data and (f.quantity.data or 0) > 0)
        def _blank_partner(f):
            return not f.partner_id.data
        if hasattr(form, "items"):
            form.items.entries[:] = [e for e in form.items.entries if not _blank_item(getattr(e, "form", e))]
        if hasattr(form, "partners"):
            form.partners.entries[:] = [e for e in form.partners.entries if not _blank_partner(getattr(e, "form", e))]

    if request.method == "POST" and not form.validate_on_submit():
        if _wants_json():
            return jsonify({"ok": False, "errors": form.errors}), 422
        for field, errors in form.errors.items():
            for err in errors:
                flash(f"❌ {form[field].label.text}: {err}", "danger")
        return render_template("warehouses/shipment_form.html", form=form, shipment=sh)

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

        acc_partners = {}
        for entry in getattr(form.partners, "entries", []):
            f = getattr(entry, "form", entry)
            pid = f.partner_id.data
            if not pid:
                continue
            p = acc_partners.get(pid) or {
                "share_percentage": Decimal("0"),
                "share_amount": Decimal("0"),
                "identity_number": None,
                "phone_number": None,
                "address": None,
                "unit_price_before_tax": Decimal("0"),
                "expiry_date": None,
                "notes": None,
            }
            sp = f.share_percentage.data or 0
            sa = f.share_amount.data or 0
            p["share_percentage"] = Decimal(p["share_percentage"]) + Decimal(str(sp))
            p["share_amount"] = Decimal(p["share_amount"]) + Decimal(str(sa))
            p["identity_number"] = f.identity_number.data or p["identity_number"]
            p["phone_number"] = f.phone_number.data or p["phone_number"]
            p["address"] = f.address.data or p["address"]
            p["unit_price_before_tax"] = Decimal(p["unit_price_before_tax"]) + Decimal(str(f.unit_price_before_tax.data or 0))
            p["expiry_date"] = f.expiry_date.data or p["expiry_date"]
            p["notes"] = f.notes.data or p["notes"]
            acc_partners[pid] = p

        for pid, v in acc_partners.items():
            sh.partners.append(ShipmentPartner(
                partner_id=pid,
                share_percentage=float(v["share_percentage"]),
                share_amount=float(v["share_amount"]),
                identity_number=v["identity_number"],
                phone_number=v["phone_number"],
                address=v["address"],
                unit_price_before_tax=float(v["unit_price_before_tax"]),
                expiry_date=v["expiry_date"],
                notes=v["notes"],
            ))

        acc_items = {}
        for entry in getattr(form.items, "entries", []):
            f = getattr(entry, "form", entry)
            pid = f.product_id.data
            wid = f.warehouse_id.data
            if not pid or not wid:
                continue
            qty = f.quantity.data or 0
            uc = Decimal(str(f.unit_cost.data or 0))
            dec = Decimal(str(f.declared_value.data or 0))
            notes = getattr(f, "notes", None)
            notes_val = notes.data if notes is not None else None
            key = (pid, wid)
            it = acc_items.get(key) or {"qty": 0, "cost_total": Decimal("0"), "declared": Decimal("0"), "notes": None}
            it["qty"] += qty
            it["cost_total"] += Decimal(qty) * uc
            it["declared"] += dec
            it["notes"] = notes_val if notes_val else it["notes"]
            acc_items[key] = it

        for (pid, wid), v in acc_items.items():
            qty = v["qty"]
            unit_cost = (v["cost_total"] / Decimal(qty)) if qty else Decimal("0")
            sh.items.append(ShipmentItem(
                product_id=pid,
                warehouse_id=wid,
                quantity=qty,
                unit_cost=float(unit_cost),
                declared_value=float(v["declared"]),
                notes=v["notes"],
            ))

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

            flash("✅ تم تحديث بيانات الشحنة", "success")
            dest_id = sh.destination_id
            return redirect(url_for("warehouse_bp.detail", warehouse_id=dest_id)) if dest_id else redirect(url_for("shipments_bp.list_shipments"))
        except SQLAlchemyError as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({"ok": False, "error": str(e)}), 500
            flash(f"❌ خطأ أثناء التحديث: {e}", "danger")
        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({"ok": False, "error": str(e)}), 400
            flash(f"❌ خطأ أثناء ضبط المخزون: {e}", "danger")

    return render_template("warehouses/shipment_form.html", form=form, shipment=sh)

@shipments_bp.route("/<int:id>/delete", methods=["POST"], endpoint="delete_shipment")
@login_required
# @permission_required("manage_warehouses")  # Commented out
def delete_shipment(id: int):
    sh = _sa_get_or_404(Shipment, id, options=[joinedload(Shipment.items), joinedload(Shipment.partners)])
    dest_id = sh.destination_id
    try:
        # إذا وصلت الشحنة، لازم نرجع المخزون قبل الحذف
        if (sh.status or "").upper() == "ARRIVED":
            _reverse_arrival_items(_items_snapshot(sh))

        # تنظيف العلاقات قبل الحذف
        sh.partners.clear()
        sh.items.clear()
        db.session.flush()

        db.session.delete(sh)
        db.session.commit()

        if _wants_json():
            return jsonify({"ok": True, "message": f"🚮 تم حذف الشحنة رقم {sh.shipment_number or sh.id}"}), 200

        flash(f"🚮 تم حذف الشحنة رقم {sh.shipment_number or sh.id}", "warning")
    except SQLAlchemyError as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({"ok": False, "error": str(e)}), 500
        flash(f"❌ خطأ من قاعدة البيانات أثناء الحذف: {e}", "danger")
    except Exception as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(f"❌ خطأ غير متوقع أثناء الحذف: {e}", "danger")

    return redirect(url_for("warehouse_bp.detail", warehouse_id=dest_id)) if dest_id else redirect(url_for("shipments_bp.list_shipments"))

@shipments_bp.route("/<int:id>", methods=["GET"], endpoint="shipment_detail")
@login_required
# @permission_required("manage_warehouses")  # Commented out
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

    # احسب المبالغ المدفوعة
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

    # رسائل تحذيرية بناءً على حالة الشحنة
    alerts = []
    status = (sh.status or "").upper()
    if status == "CANCELLED":
        alerts.append({"level": "warning", "msg": "⚠️ هذه الشحنة ملغاة ولا يمكن تعديلها."})
    elif status == "DRAFT":
        alerts.append({"level": "info", "msg": "✏️ هذه الشحنة ما زالت في وضع المسودة."})
    elif status == "IN_TRANSIT":
        alerts.append({"level": "info", "msg": "🚚 الشحنة في الطريق."})
    elif status == "ARRIVED":
        alerts.append({"level": "success", "msg": "📦 الشحنة وصلت وتم اعتمادها."})

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
                },
                "alerts": alerts,
            }
        )

    # في حالة HTML نمرر التنبيهات للقالب
    return render_template(
        "warehouses/shipment_detail.html",
        shipment=sh,
        total_paid=total_paid,
        alerts=alerts,
        format_currency=utils.format_currency,
    )

@shipments_bp.route("/<int:id>/mark-arrived", methods=["POST"], endpoint="mark_arrived")
@login_required
# @permission_required("manage_warehouses")  # Commented out
def mark_arrived(id: int):
    sh = _sa_get_or_404(Shipment, id, options=[joinedload(Shipment.items)])
    if (sh.status or "").upper() == "ARRIVED":
        msg = f"📦 الشحنة {sh.shipment_number or sh.id} معلّمة بواصل مسبقاً"
        if _wants_json():
            return jsonify({"ok": False, "error": msg}), 400
        flash(msg, "info")
        return redirect(url_for("shipments_bp.shipment_detail", id=sh.id))
    try:
        # التحقق من المستودعات قبل اعتماد الوصول
        for item in sh.items:
            if item.warehouse_id:
                _ensure_partner_warehouse(item.warehouse_id)
        
        _apply_arrival_items([
            {"product_id": it.product_id, "warehouse_id": it.warehouse_id, "quantity": it.quantity}
            for it in sh.items
        ])
        sh.status = "ARRIVED"
        sh.actual_arrival = sh.actual_arrival or datetime.utcnow()
        _compute_totals(sh)
        db.session.commit()
        msg = f"✅ تم اعتماد وصول الشحنة {sh.shipment_number or sh.id} وتحديث المخزون"
        if _wants_json():
            return jsonify({"ok": True, "shipment_id": sh.id, "status": sh.status, "message": msg}), 200
        flash(msg, "success")
    except Exception as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({"ok": False, "error": str(e)}), 500
        flash(f"❌ تعذّر اعتماد الوصول: {e}", "danger")
    return redirect(url_for("shipments_bp.shipment_detail", id=sh.id))


@shipments_bp.route("/<int:id>/cancel", methods=["POST"], endpoint="cancel_shipment")
@login_required
# @permission_required("manage_warehouses")  # Commented out
def cancel_shipment(id: int):
    sh = _sa_get_or_404(Shipment, id, options=[joinedload(Shipment.items)])
    try:
        if (sh.status or "").upper() == "ARRIVED":
            # التحقق من المستودعات قبل إلغاء الوصول
            for item in sh.items:
                if item.warehouse_id:
                    _ensure_partner_warehouse(item.warehouse_id)
            
            _reverse_arrival_items(_items_snapshot(sh))
        sh.status = "CANCELLED"
        db.session.commit()
        msg = f"⚠️ تم إلغاء الشحنة {sh.shipment_number or sh.id}"
        if _wants_json():
            return jsonify({"ok": True, "shipment_id": sh.id, "status": sh.status, "message": msg}), 200
        flash(msg, "warning")
    except Exception as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({"ok": False, "error": str(e)}), 500
        flash(f"❌ تعذّر الإلغاء: {e}", "danger")
    return redirect(url_for("shipments_bp.shipment_detail", id=sh.id))


@shipments_bp.route("/<int:id>/mark-in-transit", methods=["POST"])
@login_required
# @permission_required("manage_warehouses")  # Commented out
def mark_in_transit(id):
    sh = _sa_get_or_404(Shipment, id)
    if (sh.status or "").upper() == "IN_TRANSIT":
        if _wants_json():
            return jsonify({"ok": True, "message": "already_in_transit"})
        flash("✅ الشحنة في الطريق بالفعل", "info")
    else:
        try:
            # التحقق من المستودعات قبل وضع الشحنة في الطريق
            for item in sh.items:
                if item.warehouse_id:
                    _ensure_partner_warehouse(item.warehouse_id)
            
            sh.status = "IN_TRANSIT"
            db.session.commit()
            if _wants_json():
                return jsonify({"ok": True, "message": "marked_in_transit"})
            flash("✅ تم وضع الشحنة في الطريق", "success")
        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({"ok": False, "error": str(e)}), 500
            flash(f"❌ تعذّر التحديث: {e}", "danger")
    return redirect(url_for("shipments_bp.shipment_detail", id=sh.id))


@shipments_bp.route("/<int:id>/mark-in-customs", methods=["POST"])
@login_required
# @permission_required("manage_warehouses")  # Commented out
def mark_in_customs(id):
    sh = _sa_get_or_404(Shipment, id)
    if (sh.status or "").upper() == "IN_CUSTOMS":
        if _wants_json():
            return jsonify({"ok": True, "message": "already_in_customs"})
        flash("✅ الشحنة في الجمارك بالفعل", "info")
    else:
        try:
            # التحقق من المستودعات قبل وضع الشحنة في الجمارك
            for item in sh.items:
                if item.warehouse_id:
                    _ensure_partner_warehouse(item.warehouse_id)
            
            sh.status = "IN_CUSTOMS"
            db.session.commit()
            if _wants_json():
                return jsonify({"ok": True, "message": "marked_in_customs"})
            flash("✅ تم وضع الشحنة في الجمارك", "success")
        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({"ok": False, "error": str(e)}), 500
            flash(f"❌ تعذّر التحديث: {e}", "danger")
    return redirect(url_for("shipments_bp.shipment_detail", id=sh.id))


@shipments_bp.route("/<int:id>/mark-delivered", methods=["POST"])
@login_required
# @permission_required("manage_warehouses")  # Commented out
def mark_delivered(id):
    sh = _sa_get_or_404(Shipment, id)
    if (sh.status or "").upper() == "DELIVERED":
        if _wants_json():
            return jsonify({"ok": True, "message": "already_delivered"})
        flash("✅ الشحنة مسلمة بالفعل", "info")
    else:
        try:
            # التحقق من المستودعات قبل تسليم الشحنة
            for item in sh.items:
                if item.warehouse_id:
                    _ensure_partner_warehouse(item.warehouse_id)
            
            sh.status = "DELIVERED"
            sh.delivered_date = datetime.utcnow()
            db.session.commit()
            if _wants_json():
                return jsonify({"ok": True, "message": "marked_delivered"})
            flash("✅ تم تسليم الشحنة", "success")
        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({"ok": False, "error": str(e)}), 500
            flash(f"❌ تعذّر التحديث: {e}", "danger")
    return redirect(url_for("shipments_bp.shipment_detail", id=sh.id))


@shipments_bp.route("/<int:id>/mark-returned", methods=["POST"])
@login_required
# @permission_required("manage_warehouses")  # Commented out
def mark_returned(id):
    sh = _sa_get_or_404(Shipment, id)
    if (sh.status or "").upper() == "RETURNED":
        if _wants_json():
            return jsonify({"ok": True, "message": "already_returned"})
        flash("✅ الشحنة مرتجعة بالفعل", "info")
    else:
        try:
            # التحقق من المستودعات قبل إرجاع الشحنة
            for item in sh.items:
                if item.warehouse_id:
                    _ensure_partner_warehouse(item.warehouse_id)
            
            sh.status = "RETURNED"
            db.session.commit()
            if _wants_json():
                return jsonify({"ok": True, "message": "marked_returned"})
            flash("✅ تم إرجاع الشحنة", "success")
        except Exception as e:
            db.session.rollback()
            if _wants_json():
                return jsonify({"ok": False, "error": str(e)}), 500
            flash(f"❌ تعذّر التحديث: {e}", "danger")
    return redirect(url_for("shipments_bp.shipment_detail", id=sh.id))


@shipments_bp.route("/<int:id>/update-delivery-attempt", methods=["POST"])
@login_required
# @permission_required("manage_warehouses")  # Commented out
def update_delivery_attempt(id):
    sh = _sa_get_or_404(Shipment, id)
    data = request.get_json(silent=True) or {}
    
    try:
        sh.delivery_attempts = (sh.delivery_attempts or 0) + 1
        sh.last_delivery_attempt = datetime.utcnow()
        if data.get("notes"):
            sh.notes = (sh.notes or "") + f"\nمحاولة تسليم #{sh.delivery_attempts}: {data.get('notes')}"
        db.session.commit()
        if _wants_json():
            return jsonify({"ok": True, "message": "delivery_attempt_updated"})
        flash("✅ تم تحديث محاولة التسليم", "success")
    except Exception as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({"ok": False, "error": str(e)}), 500
        flash(f"❌ تعذّر التحديث: {e}", "danger")
    return redirect(url_for("shipments_bp.shipment_detail", id=sh.id))
