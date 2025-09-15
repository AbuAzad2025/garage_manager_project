from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple
from flask import Blueprint, Response, current_app, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from extensions import csrf, db, limiter
from utils import _get_user_permissions, _q, _query_limit, permission_required, search_model, super_only
from barcodes import validate_barcode
from forms import EquipmentTypeForm
from models import (
    Customer,
    Employee,
    EquipmentType,
    ExchangeTransaction,
    Expense,
    Invoice,
    OnlinePreOrder,
    Partner,
    Payment,
    Permission,
    PreOrder,
    Product,
    ProductCategory,
    ProductPartnerShare,
    Role,
    Sale,
    SaleLine,
    ServiceRequest,
    Shipment,
    ShipmentItem,
    ShipmentPartner,
    StockLevel,
    Supplier,
    SupplierLoanSettlement,
    Transfer,
    User,
    Warehouse,
    WarehousePartnerShare,
    WarehouseType,
)

bp = Blueprint("api", __name__, url_prefix="/api")

_TWOPLACES = Decimal("0.01")


def _limit(default: int = 20, max_value: int = 100) -> int:
    return _query_limit(default, max_value)


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


def _compute_shipment_totals(sh: Shipment):
    items_total = sum((_q2(it.quantity) * _q2(it.unit_cost)) for it in sh.items)
    sh.value_before = _q2(items_total)
    extras = _q2(sh.shipping_cost) + _q2(sh.customs) + _q2(sh.vat) + _q2(sh.insurance)
    sh.total_value = _q2(items_total + extras)
    sh.currency = _norm_currency(sh.currency)


def _landed_allocation(items, extras_total):
    total_value = sum(_q2(it.quantity) * _q2(it.unit_cost) for it in items)
    if total_value <= 0 or _q2(extras_total) <= 0:
        return {i: Decimal("0.00") for i, _ in enumerate(items)}
    alloc = {}
    rem = _q2(extras_total)
    for idx, it in enumerate(items):
        base = _q2(it.quantity) * _q2(it.unit_cost)
        share_q = _q2((base / total_value) * _q2(extras_total))
        alloc[idx] = share_q
        rem -= share_q
    keys = list(alloc.keys())
    k = 0
    while rem != Decimal("0.00") and keys:
        alloc[keys[k % len(keys)]] += Decimal("0.01") if rem > 0 else Decimal("-0.01")
        rem -= Decimal("0.01") if rem > 0 else Decimal("-0.01")
        k += 1
    return alloc


def _apply_arrival_items(items):
    for it in items:
        pid, wid, qty = int(it.get("product_id") or 0), int(it.get("warehouse_id") or 0), int(it.get("quantity") or 0)
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
    for it in items:
        pid, wid, qty = int(it.get("product_id") or 0), int(it.get("warehouse_id") or 0), int(it.get("quantity") or 0)
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


def _available_expr():
    return StockLevel.quantity - func.coalesce(StockLevel.reserved_quantity, 0)


def _available_qty(product_id: int, warehouse_id: int) -> int:
    row = (
        db.session.query(_available_expr().label("avail"))
        .filter(StockLevel.product_id == product_id, StockLevel.warehouse_id == warehouse_id)
        .first()
    )
    return int(row.avail or 0) if row else 0


def _auto_pick_warehouse(product_id: int, required_qty: int, preferred_wid: Optional[int] = None) -> Optional[int]:
    if preferred_wid and _available_qty(product_id, preferred_wid) >= required_qty:
        return preferred_wid
    row = (
        db.session.query(StockLevel.warehouse_id, _available_expr().label("avail"))
        .filter(StockLevel.product_id == product_id)
        .filter(_available_expr() >= required_qty)
        .order_by(StockLevel.warehouse_id.asc())
        .first()
    )
    return int(row.warehouse_id) if row else None


def _lock_stock_rows(pairs: List[Tuple[int, int]]) -> None:
    if not pairs:
        return
    conds = [((StockLevel.product_id == pid) & (StockLevel.warehouse_id == wid)) for (pid, wid) in pairs]
    db.session.query(StockLevel).filter(or_(*conds)).with_for_update(nowait=False).all()


def _collect_requirements_from_lines(lines: Iterable[SaleLine]) -> Dict[Tuple[int, int], int]:
    req = {}
    for ln in lines:
        pid, wid, qty = int(ln.product_id or 0), int(ln.warehouse_id or 0), int(ln.quantity or 0)
        if pid and wid and qty > 0:
            req[(pid, wid)] = req.get((pid, wid), 0) + qty
    return req


def _reserve_stock(sale: Sale) -> None:
    if (getattr(sale, "status", "") or "").upper() != "CONFIRMED":
        return
    req = _collect_requirements_from_lines(sale.lines or [])
    if not req:
        return
    _lock_stock_rows(list(req.keys()))
    for (pid, wid), qty in req.items():
        rec = (
            db.session.query(StockLevel)
            .filter_by(product_id=pid, warehouse_id=wid)
            .with_for_update(nowait=False)
            .first()
        )
        if not rec:
            rec = StockLevel(product_id=pid, warehouse_id=wid, quantity=0, reserved_quantity=0)
            db.session.add(rec)
            db.session.flush()
        available = int(rec.quantity or 0) - int(rec.reserved_quantity or 0)
        if available < qty:
            raise ValueError(f"insufficient:{pid}:{wid}")
        rec.reserved_quantity = int(rec.reserved_quantity or 0) + qty
        db.session.flush()


def _release_stock(sale: Sale) -> None:
    req = _collect_requirements_from_lines(sale.lines or [])
    if not req:
        return
    _lock_stock_rows(list(req.keys()))
    for (pid, wid), qty in req.items():
        rec = (
            db.session.query(StockLevel)
            .filter_by(product_id=pid, warehouse_id=wid)
            .with_for_update(nowait=False)
            .first()
        )
        if not rec:
            continue
        rec.reserved_quantity = max(0, int(rec.reserved_quantity or 0) - qty)
        db.session.flush()


def _safe_generate_number_after_flush(sale: Sale) -> None:
    if not getattr(sale, "sale_number", None):
        sale.sale_number = f"INV-{datetime.utcnow():%Y%m%d}-{sale.id:04d}"
        db.session.flush()


def sale_to_dict(s: Sale) -> Dict[str, Any]:
    return {
        "id": s.id,
        "sale_number": s.sale_number,
        "customer_id": s.customer_id,
        "seller_id": s.seller_id,
        "sale_date": s.sale_date.isoformat() if getattr(s, "sale_date", None) else None,
        "status": s.status,
        "currency": s.currency,
        "tax_rate": float(getattr(s, "tax_rate", 0) or 0),
        "shipping_cost": float(getattr(s, "shipping_cost", 0) or 0),
        "discount_total": float(getattr(s, "discount_total", 0) or 0),
        "notes": getattr(s, "notes", None),
        "total_amount": float(getattr(s, "total_amount", 0) or 0),
        "total_paid": float(getattr(s, "total_paid", 0) or 0),
        "balance_due": float(getattr(s, "balance_due", 0) or 0),
        "lines": [
            {
                "product_id": ln.product_id,
                "warehouse_id": ln.warehouse_id,
                "quantity": int(ln.quantity or 0),
                "unit_price": float(ln.unit_price or 0),
                "discount_rate": float(ln.discount_rate or 0),
                "tax_rate": float(ln.tax_rate or 0),
                "note": getattr(ln, "note", None),
            }
            for ln in (s.lines or [])
        ],
    }


def _number_of(o, attr: Optional[str] = None, fallback_prefix: Optional[str] = None) -> str:
    if attr and getattr(o, attr, None):
        return str(getattr(o, attr))
    for cand in (
        "invoice_number",
        "service_number",
        "sale_number",
        "shipment_number",
        "order_number",
        "payment_number",
        "receipt_number",
        "reference",
        "cart_id",
        "tax_invoice_number",
    ):
        v = getattr(o, cand, None)
        if v:
            return str(v)
    if fallback_prefix:
        return f"{fallback_prefix}-{getattr(o, 'id', '')}"
    return str(getattr(o, "id", ""))


def normalize_email(s: Optional[str]) -> Optional[str]:
    s = (s or "").strip().lower()
    return s or None


def normalize_phone(s: Optional[str]) -> Optional[str]:
    raw = (s or "").strip()
    if not raw:
        return None
    keep = []
    for i, ch in enumerate(raw):
        if ch.isdigit() or (ch == "+" and i == 0):
            keep.append(ch)
    out = "".join(keep)
    return out or None


@bp.get("/me")
@login_required
def me():
    role_name = getattr(getattr(current_user, "role", None), "name", None)
    perms = sorted(list(_get_user_permissions(current_user) or []))
    return jsonify(
        {
            "id": current_user.id,
            "username": getattr(current_user, "username", None),
            "email": getattr(current_user, "email", None),
            "role": role_name,
            "permissions": perms,
        }
    )


@bp.get("/permissions.json")
@super_only
def permissions_json():
    rows = Permission.query.order_by(Permission.name.asc()).all()

    def _row(p):
        return {
            "id": p.id,
            "code": getattr(p, "code", None) or getattr(p, "name", None),
            "name": getattr(p, "name", None),
            "ar_name": getattr(p, "ar_name", None),
            "category": getattr(p, "category", None),
            "aliases": getattr(p, "aliases", None),
        }

    return jsonify([_row(p) for p in rows])


@bp.get("/permissions.csv")
@super_only
def permissions_csv():
    rows = Permission.query.order_by(Permission.name.asc()).all()
    import io, csv

    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["id", "code", "name", "ar_name", "category", "aliases"])
    for p in rows:
        w.writerow(
            [
                p.id,
                getattr(p, "code", None) or getattr(p, "name", None),
                getattr(p, "name", None),
                getattr(p, "ar_name", None),
                getattr(p, "category", None),
                getattr(p, "aliases", None),
            ]
        )
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=permissions.csv"},
    )


@bp.get("/search_categories", endpoint="search_categories")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_inventory", "view_inventory")
def search_categories():
    q = (request.args.get("q") or "").strip()
    limit = min(int(request.args.get("limit", 20)), 50)
    query = ProductCategory.query
    if q:
        query = query.filter(func.lower(ProductCategory.name).like(f"%{q.lower()}%"))
    results = query.order_by(ProductCategory.name).limit(limit).all()
    return jsonify({"results": [{"id": c.id, "text": c.name} for c in results]})


@bp.get("/customers")
@bp.get("/search_customers", endpoint="search_customers")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_customers", "add_customer")
def customers():
    return search_model(Customer, ["name", "phone", "email"], label_attr="name")


@bp.post("/customers")
@login_required
@limiter.limit("30/minute")
@permission_required("manage_customers", "add_customer")
def create_customer_api():
    data = request.get_json(silent=True) or request.form or {}
    name = (data.get("name") or "").strip()
    email = normalize_email(data.get("email"))
    phone = normalize_phone(data.get("phone"))
    whatsapp = normalize_phone(data.get("whatsapp"))
    address = (data.get("address") or "").strip()
    notes = (data.get("notes") or "").strip()
    discount_rate = data.get("discount_rate", 0)
    try:
        discount_rate = float(discount_rate or 0)
    except Exception:
        discount_rate = 0.0
    credit_limit = data.get("credit_limit", 0)
    try:
        credit_limit = float(credit_limit or 0)
    except Exception:
        credit_limit = 0.0
    is_online = bool(data.get("is_online"))
    is_active = bool(data.get("is_active", "1"))
    if not name or not email:
        return jsonify({"error": "الاسم والبريد مطلوبان"}), 400
    try:
        c = Customer(
            name=name,
            email=email,
            phone=phone,
            whatsapp=whatsapp,
            address=address,
            notes=notes,
            discount_rate=discount_rate,
            credit_limit=credit_limit,
            is_online=is_online,
            is_active=is_active,
        )
        pwd = (data.get("password") or "").strip()
        if pwd:
            c.set_password(pwd)
        db.session.add(c)
        db.session.commit()
        return jsonify({"id": c.id, "text": c.name}), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "فشل حفظ العميل"}), 500


@bp.get("/search_suppliers", endpoint="search_suppliers")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_vendors", "add_supplier", "view_inventory", "manage_inventory", "view_warehouses")
def search_suppliers():
    if not current_user.is_authenticated:
        return jsonify({"error": "Unauthorized"}), 401
    q = (request.args.get("q") or "").strip()
    limit = min(int(request.args.get("limit", 20) or 20), 50)
    sid = (request.args.get("id") or "").strip()
    if sid.isdigit():
        s = db.session.get(Supplier, int(sid))
        if not s:
            return jsonify({"results": []})
        return jsonify(
            {
                "results": [
                    {
                        "id": s.id,
                        "text": s.name,
                        "name": s.name,
                        "phone": s.phone,
                        "identity_number": s.identity_number,
                    }
                ]
            }
        )
    qry = Supplier.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            or_(
                func.lower(Supplier.name).like(f"%{q.lower()}%"),
                Supplier.phone.ilike(like),
                Supplier.identity_number.ilike(like),
                Supplier.email.ilike(like),
            )
        )
    rows = qry.order_by(Supplier.name.asc()).limit(limit).all()
    return jsonify(
        {
            "results": [
                {
                    "id": s.id,
                    "text": s.name,
                    "name": s.name,
                    "phone": s.phone,
                    "identity_number": s.identity_number,
                }
                for s in rows
            ]
        }
    )


@bp.post("/suppliers", endpoint="create_supplier")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_vendors", "add_supplier")
def create_supplier():
    data = request.get_json(silent=True) or request.form or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    identity_number = (data.get("identity_number") or "").strip()
    address = (data.get("address") or "").strip()
    notes = (data.get("notes") or "").strip()
    if not name:
        return jsonify({"error": "الاسم مطلوب"}), 400
    try:
        s = Supplier(name=name, phone=phone, identity_number=identity_number, address=address, notes=notes)
        db.session.add(s)
        db.session.commit()
        return jsonify({"id": s.id, "text": s.name}), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "فشل حفظ المورد"}), 500


@bp.get("/suppliers/<int:id>")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_vendors", "add_supplier")
def get_supplier(id):
    s = Supplier.query.get_or_404(id)
    return jsonify(
        {
            "id": s.id,
            "name": s.name,
            "phone": s.phone,
            "identity_number": s.identity_number,
            "address": s.address,
            "notes": s.notes,
        }
    )


@bp.put("/suppliers/<int:id>")
@bp.patch("/suppliers/<int:id>", endpoint="update_supplier")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_vendors", "add_supplier")
def update_supplier(id):
    s = Supplier.query.get_or_404(id)
    data = request.get_json(silent=True) or request.form or {}
    s.name = (data.get("name") or s.name).strip()
    s.phone = (data.get("phone") or s.phone).strip()
    s.identity_number = (data.get("identity_number") or s.identity_number).strip()
    s.address = (data.get("address") or s.address).strip()
    s.notes = (data.get("notes") or s.notes).strip()
    try:
        db.session.commit()
        return jsonify({"id": s.id, "text": s.name})
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "فشل تحديث المورد"}), 500


@bp.delete("/suppliers/<int:id>", endpoint="delete_supplier")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_vendors", "add_supplier")
def delete_supplier(id):
    s = Supplier.query.get_or_404(id)
    try:
        db.session.delete(s)
        db.session.commit()
        return jsonify({"success": True})
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "فشل حذف المورد"}), 500


@bp.get("/search_partners", endpoint="search_partners")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_vendors", "add_partner", "view_inventory", "manage_inventory", "view_warehouses")
def search_partners():
    if not current_user.is_authenticated:
        return jsonify({"error": "Unauthorized"}), 401
    q = (request.args.get("q") or "").strip()
    limit = min(int(request.args.get("limit", 20) or 20), 50)
    pid = (request.args.get("id") or "").strip()
    if pid.isdigit():
        p = db.session.get(Partner, int(pid))
        if not p:
            return jsonify({"results": []})
        return jsonify(
            {
                "results": [
                    {
                        "id": p.id,
                        "text": p.name,
                        "name": p.name,
                        "phone": p.phone_number,
                        "identity_number": p.identity_number,
                    }
                ]
            }
        )
    qry = Partner.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            or_(
                func.lower(Partner.name).like(f"%{q.lower()}%"),
                Partner.phone_number.ilike(like),
                Partner.identity_number.ilike(like),
                Partner.email.ilike(like),
            )
        )
    rows = qry.order_by(Partner.name.asc()).limit(limit).all()
    return jsonify(
        {
            "results": [
                {
                    "id": p.id,
                    "text": p.name,
                    "name": p.name,
                    "phone": p.phone_number,
                    "identity_number": p.identity_number,
                }
                for p in rows
            ]
        }
    )


@bp.post("/partners", endpoint="create_partner")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_vendors", "add_partner")
def create_partner():
    data = request.get_json(silent=True) or request.form or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone_number") or "").strip()
    identity_number = (data.get("identity_number") or "").strip()
    address = (data.get("address") or "").strip()
    notes = (data.get("notes") or "").strip()
    if not name:
        return jsonify({"error": "الاسم مطلوب"}), 400
    try:
        p = Partner(name=name, phone_number=phone, identity_number=identity_number, address=address, notes=notes)
        db.session.add(p)
        db.session.commit()
        return jsonify({"id": p.id, "text": p.name}), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "فشل حفظ الشريك"}), 500


@bp.get("/partners/<int:id>")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_vendors", "add_partner")
def get_partner(id):
    p = Partner.query.get_or_404(id)
    return jsonify(
        {"id": p.id, "name": p.name, "phone": p.phone_number, "identity_number": p.identity_number, "address": p.address, "notes": p.notes}
    )


@bp.put("/partners/<int:id>")
@bp.patch("/partners/<int:id>", endpoint="update_partner")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_vendors", "add_partner")
def update_partner(id):
    p = Partner.query.get_or_404(id)
    data = request.get_json(silent=True) or request.form or {}
    p.name = (data.get("name") or p.name).strip()
    p.phone_number = (data.get("phone_number") or p.phone_number).strip()
    p.identity_number = (data.get("identity_number") or p.identity_number).strip()
    p.address = (data.get("address") or p.address).strip()
    p.notes = (data.get("notes") or p.notes).strip()
    try:
        db.session.commit()
        return jsonify({"id": p.id, "text": p.name})
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "فشل تحديث الشريك"}), 500


@bp.delete("/partners/<int:id>", endpoint="delete_partner")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_vendors", "add_partner")
def delete_partner(id):
    p = Partner.query.get_or_404(id)
    try:
        db.session.delete(p)
        db.session.commit()
        return jsonify({"success": True})
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "فشل حذف الشريك"}), 500


@bp.get("/barcode/validate", endpoint="barcode_validate")
@login_required
@limiter.limit("120/minute")
def barcode_validate():
    code = (request.args.get("code") or "").strip()
    r = validate_barcode(code)
    exists = False
    if r.get("normalized"):
        exists = db.session.query(Product.id).filter_by(barcode=r["normalized"]).first() is not None
    return jsonify(
        {
            "input": code,
            "normalized": r.get("normalized"),
            "valid": bool(r.get("valid")),
            "suggested": r.get("suggested"),
            "exists": bool(exists),
        }
    )


@bp.get("/products/barcode/<code>")
@login_required
@limiter.limit("60/minute")
@permission_required("view_parts", "view_inventory", "manage_inventory")
def product_by_barcode(code: str):
    r = validate_barcode(code)
    conds = []
    if r.get("normalized"):
        conds.append(Product.barcode == r["normalized"])
    conds.append(Product.barcode == code)
    if not r.get("valid"):
        conds.append(Product.part_number == code)
        conds.append(Product.sku == code)
    p = Product.query.filter(or_(*conds)).limit(1).first()
    if not p:
        body = {"error": "Not Found"}
        if r.get("suggested"):
            body["suggested"] = r["suggested"]
        return jsonify(body), 404
    return jsonify(
        {
            "id": p.id,
            "name": p.name,
            "sku": p.sku,
            "part_number": p.part_number,
            "barcode": p.barcode,
            "price": float(p.price or 0),
        }
    )


@bp.get("/products/<int:pid>/info")
@login_required
@limiter.limit("60/minute")
@permission_required("view_parts", "view_inventory", "manage_inventory")
def product_info(pid: int):
    p = db.session.get(Product, pid)
    if not p:
        return jsonify({"error": "Not Found"}), 404
    wid = request.args.get("warehouse_id", type=int)
    available = None
    if wid:
        sl = StockLevel.query.filter_by(product_id=pid, warehouse_id=wid).first()
        available = sl.quantity if sl else 0
    return jsonify(
        {"id": p.id, "name": p.name, "sku": p.sku, "price": float(p.price or 0), "available": (int(available) if available is not None else None)}
    )


@bp.post("/categories", endpoint="create_category")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_inventory")
def create_category():
    data = request.get_json(silent=True) or request.form or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "الاسم مطلوب"}), 400
    exists = ProductCategory.query.filter(func.lower(ProductCategory.name) == name.lower()).first()
    if exists:
        return jsonify({"id": exists.id, "text": exists.name, "dupe": True}), 200
    c = ProductCategory(name=name)
    db.session.add(c)
    try:
        db.session.commit()
        return jsonify({"id": c.id, "text": c.name}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@bp.get("/warehouses", endpoint="warehouses")
@login_required
@limiter.limit("60/minute")
@permission_required("view_warehouses", "manage_warehouses", "view_inventory", "manage_inventory")
def api_warehouses():
    return _warehouses_handler()


@bp.get("/search_warehouses", endpoint="search_warehouses")
@login_required
@limiter.limit("60/minute")
@permission_required("view_warehouses", "manage_warehouses", "view_inventory", "manage_inventory")
def api_search_warehouses():
    return _warehouses_handler()


def _warehouses_handler():
    q = (request.args.get("q") or "").strip()
    supplier_id = request.args.get("supplier_id", type=int)
    type_param = (request.args.get("type") or "").strip().upper()
    active_only_arg = request.args.get("active_only")
    if active_only_arg is None:
        active_only_arg = "1"
    qry = Warehouse.query
    if active_only_arg in {"1", "true", "True"}:
        qry = qry.filter(Warehouse.is_active.is_(True))
    if type_param:
        qry = qry.filter(Warehouse.warehouse_type == type_param)
    if supplier_id:
        qry = qry.filter(Warehouse.supplier_id == supplier_id)
    if q:
        like = f"%{q}%"
        qry = qry.filter(Warehouse.name.ilike(like))
    rows = qry.order_by(Warehouse.name.asc()).limit(_query_limit(20, 50)).all()
    return jsonify(
        {
            "results": [
                {
                    "id": w.id,
                    "text": w.name,
                    "supplier_id": w.supplier_id,
                    "warehouse_type": getattr(w.warehouse_type, "value", w.warehouse_type),
                    "is_active": bool(w.is_active),
                }
                for w in rows
            ]
        }
    )


@bp.put("/warehouses/<int:id>")
@bp.patch("/warehouses/<int:id>", endpoint="api_update_warehouse")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_warehouses")
def api_update_warehouse(id):
    w = Warehouse.query.get_or_404(id)
    data = request.get_json(silent=True) or request.form or {}

    def _i(v):
        try:
            return int(v) if v not in (None, "", "None") else None
        except Exception:
            return None

    name = data.get("name")
    if name is not None:
        w.name = name.strip()
    wt = data.get("warehouse_type")
    if wt is not None:
        w.warehouse_type = wt.strip().upper()
    loc = data.get("location")
    if loc is not None:
        w.location = loc.strip() or None
    parent_id = _i(data.get("parent_id"))
    partner_id = _i(data.get("partner_id"))
    supplier_id = _i(data.get("supplier_id"))
    share_percent = data.get("share_percent")
    capacity = data.get("capacity")
    is_active = data.get("is_active")
    if parent_id is not None:
        w.parent_id = parent_id
    if partner_id is not None:
        w.partner_id = partner_id
    if supplier_id is not None:
        w.supplier_id = supplier_id
    try:
        if share_percent not in (None, "", "None"):
            w.share_percent = float(share_percent)
    except Exception:
        pass
    try:
        if str(capacity or "").strip() != "":
            w.capacity = int(capacity)
    except Exception:
        pass
    if is_active is not None:
        w.is_active = bool(is_active)
    wt_effective = getattr(w.warehouse_type, "value", w.warehouse_type)
    if wt_effective == WarehouseType.EXCHANGE.value and not w.supplier_id:
        return jsonify({"success": False, "error": "مخزن التبادل يتطلب تعيين المورد."}), 400
    try:
        db.session.commit()
        return jsonify({"success": True, "id": w.id, "name": w.name})
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.delete("/warehouses/<int:id>", endpoint="api_delete_warehouse")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_warehouses")
def api_delete_warehouse(id):
    w = Warehouse.query.get_or_404(id)
    try:
        db.session.delete(w)
        db.session.commit()
        return jsonify({"success": True})
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.get("/products", endpoint="products")
@login_required
@limiter.limit("60/minute")
@permission_required("view_parts", "view_inventory", "manage_inventory")
def api_products():
    return search_model(
        Product,
        ["name", "sku", "part_number", "barcode"],
        label_attr="name",
        serializer=lambda p: {
            "id": p.id,
            "text": p.name,
            "name": p.name,
            "price": float(p.price or 0),
            "sku": p.sku,
        },
    )


@bp.get("/search_products", endpoint="search_products")
@login_required
@limiter.limit("60/minute")
@permission_required("view_parts", "view_inventory", "manage_inventory")
def api_search_products():
    return api_products()

@bp.get("/warehouses/<int:wid>/products", endpoint="products_by_warehouse")
@login_required
@limiter.limit("60/minute")
@permission_required("view_inventory", "view_warehouses", "manage_inventory")
def api_products_by_warehouse(wid: int):
    q = (request.args.get("q") or "").strip()
    selected_ids = request.args.getlist("warehouse_ids", type=int) or []
    sum_ids = selected_ids or [wid]

    qry = (
        db.session.query(
            Product,
            StockLevel.quantity.label("qty_curr"),
        )
        .join(
            StockLevel,
            (StockLevel.product_id == Product.id) & (StockLevel.warehouse_id == wid),
            isouter=True
        )
    )
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.part_number.ilike(like),
                Product.brand.ilike(like),
            )
        )

    rows = qry.order_by(Product.name.asc()).limit(_limit(200, 500)).all()

    totals_map = {}
    if sum_ids:
        trows = (
            db.session.query(StockLevel.product_id, func.coalesce(func.sum(StockLevel.quantity), 0))
            .filter(StockLevel.warehouse_id.in_(sum_ids))
            .group_by(StockLevel.product_id)
            .all()
        )
        totals_map = {pid: int(t or 0) for pid, t in trows}

    results = []
    for p, qty_curr in rows:
        label = f"{p.name} (متاح: {totals_map.get(p.id, int(qty_curr or 0))})"
        results.append({
            "id": p.id,
            "text": label,
            "sku": p.sku,
            "part_number": getattr(p, "part_number", None),
            "brand": getattr(p, "brand", None),
            "purchase_price": float(getattr(p, "purchase_price", 0) or 0),
            "selling_price": float(getattr(p, "selling_price", 0) or 0),
            "price": float(getattr(p, "price", 0) or 0),
            "online_price": float(getattr(p, "online_price", 0) or 0),
            "quantity": int(qty_curr or 0),
            "total_quantity": totals_map.get(p.id, int(qty_curr or 0)),
        })

    return jsonify({"results": results})

@bp.get("/warehouses/inventory")
@login_required
@limiter.limit("60/minute")
@permission_required("view_inventory")
def api_inventory_summary():
    ids = request.args.getlist("warehouse_ids", type=int)
    q = _q()
    wh_ids = ids or [w.id for w in Warehouse.query.order_by(Warehouse.name).all()]
    if not wh_ids:
        return jsonify({"data": []})
    qry = (
        db.session.query(
            Product.id.label("pid"),
            Product.name,
            Product.sku,
            func.coalesce(func.sum(StockLevel.quantity), 0).label("on_hand"),
            func.coalesce(func.sum(func.coalesce(StockLevel.reserved_quantity, 0)), 0).label("reserved"),
        )
        .join(StockLevel, StockLevel.product_id == Product.id)
        .filter(StockLevel.warehouse_id.in_(wh_ids))
        .group_by(Product.id, Product.name, Product.sku)
        .order_by(Product.name.asc())
    )
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    rows = qry.limit(_limit(200, 500))
    data = []
    for pid, name, sku, on_hand, reserved in rows:
        on_hand = int(on_hand or 0)
        reserved = int(reserved or 0)
        data.append({"product_id": pid, "name": name, "sku": sku, "on_hand": on_hand, "reserved": reserved, "available": max(on_hand - reserved, 0)})
    return jsonify({"data": data, "warehouse_ids": wh_ids})

@bp.patch("/products/<int:id>", endpoint="update_product")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_inventory")
def update_product(id: int):
    p = Product.query.get_or_404(id)
    data = request.get_json(silent=True) or {}

    def _num(v):
        try:
            return float(v)
        except Exception:
            return None

    # نصوص
    for f in ["sku", "part_number", "brand", "online_name", "commercial_name", "description"]:
        if f in data:
            setattr(p, f, (data.get(f) or None) or None)

    # أرقام/أسعار
    for f in ["purchase_price", "selling_price", "price", "online_price", "min_price", "max_price",
              "unit_price_before_tax", "cost_before_shipping", "cost_after_shipping", "tax_rate"]:
        if f in data:
            v = _num(data.get(f))
            setattr(p, f, v if v is not None else getattr(p, f))

    try:
        db.session.commit()
        return jsonify({
            "success": True,
            "product": {
                "id": p.id,
                "sku": p.sku,
                "part_number": p.part_number,
                "brand": p.brand,
                "purchase_price": float(p.purchase_price or 0),
                "selling_price": float(p.selling_price or 0),
                "price": float(p.price or 0),
                "online_price": float(p.online_price or 0),
            }
        })
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400

@bp.post("/warehouses/<int:warehouse_id>/stock")
@login_required
@csrf.exempt
@limiter.limit("60/minute")
@permission_required("manage_inventory")
def update_stock(warehouse_id: int):
    data = request.get_json(silent=True) or request.form

    def _to_int(v, default=None):
        try:
            if v in (None, "", "None"):
                return default
            return int(float(v))
        except Exception:
            return default

    pid = _to_int(data.get("product_id"))
    quantity = _to_int(data.get("quantity"), 0)
    min_stock = _to_int(data.get("min_stock"))
    max_stock = _to_int(data.get("max_stock"))
    if pid is None:
        return jsonify({"success": False, "errors": {"product_id": ["قيمة غير صالحة"]}}), 400
    sl = StockLevel.query.filter_by(warehouse_id=warehouse_id, product_id=pid).first()
    if not sl:
        sl = StockLevel(warehouse_id=warehouse_id, product_id=pid, quantity=0, reserved_quantity=0)
        db.session.add(sl)
    if quantity is not None:
        sl.quantity = max(0, quantity)
    if min_stock is not None:
        sl.min_stock = max(0, min_stock)
    if max_stock is not None:
        sl.max_stock = max(0, max_stock)
    try:
        db.session.commit()
        alert = "below_min" if (sl.quantity or 0) <= (sl.min_stock or 0) else None
        return jsonify(
            {
                "success": True,
                "quantity": int(sl.quantity or 0),
                "min_stock": int(sl.min_stock or 0),
                "max_stock": int(sl.max_stock or 0),
                "alert": alert,
            }
        ), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.post("/warehouses/<int:warehouse_id>/transfer")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_inventory", "manage_warehouses", "warehouse_transfer")
def transfer_between_warehouses(warehouse_id: int):
    data = request.get_json(silent=True) or request.form

    def _i(name):
        v = data.get(name)
        try:
            return int(v) if v is not None and str(v).strip() != "" else None
        except Exception:
            return None

    pid = _i("product_id")
    sid = _i("source_id") or warehouse_id
    did = _i("destination_id")
    try:
        qty = int(float(data.get("quantity", 0)))
    except Exception:
        qty = 0
    notes = (data.get("notes") or "").strip() or None
    if not (pid and sid and did and qty > 0) or sid == did:
        return jsonify({"success": False, "errors": {"form": "invalid"}}), 400
    if sid != warehouse_id:
        return jsonify({"success": False, "errors": {"warehouse": "mismatch"}}), 400
    src = StockLevel.query.filter_by(warehouse_id=sid, product_id=pid).first()
    available = int((src.quantity or 0) - (src.reserved_quantity or 0)) if src else 0
    if available < qty:
        return jsonify({"success": False, "error": "insufficient_stock", "available": max(available, 0)}), 400
    src.quantity = (src.quantity or 0) - qty
    dst = StockLevel.query.filter_by(warehouse_id=did, product_id=pid).first()
    if not dst:
        dst = StockLevel(warehouse_id=did, product_id=pid, quantity=0, reserved_quantity=0)
        db.session.add(dst)
    dst.quantity = (dst.quantity or 0) + qty
    t = Transfer(
        product_id=pid,
        source_id=sid,
        destination_id=did,
        quantity=qty,
        direction="OUT",
        user_id=getattr(current_user, "id", None),
    )
    setattr(t, "_skip_stock_apply", True)
    db.session.add(t)
    try:
        db.session.commit()
        return jsonify({"success": True, "transfer_id": t.id}), 200
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"success": False, "error": "db_error"}), 500


@bp.get("/warehouses/<int:warehouse_id>/partner_shares")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_inventory")
def get_partner_shares(warehouse_id: int):
    rows = WarehousePartnerShare.query.filter_by(warehouse_id=warehouse_id).all()
    if not rows:
        rows = (
            ProductPartnerShare.query.join(StockLevel, StockLevel.product_id == ProductPartnerShare.product_id)
            .filter(StockLevel.warehouse_id == warehouse_id)
            .all()
        )
    data = []
    for s in rows:
        partner = getattr(s, "partner", None)
        product = getattr(s, "product", None)
        pct = float(getattr(s, "share_percentage", getattr(s, "share_percent", 0)) or 0)
        amt = float(getattr(s, "share_amount", 0) or 0)
        data.append(
            {
                "id": getattr(s, "id", None),
                "product_id": getattr(product, "id", None),
                "product": product.name if product else None,
                "partner_id": getattr(partner, "id", None),
                "partner": partner.name if partner else None,
                "share_percentage": pct,
                "share_amount": amt,
                "notes": getattr(s, "notes", "") or "",
            }
        )
    return jsonify({"success": True, "shares": data}), 200


@bp.post("/warehouses/<int:warehouse_id>/partner_shares")
@login_required
@csrf.exempt
@limiter.limit("60/minute")
@permission_required("manage_inventory")
def update_partner_shares(warehouse_id: int):
    payload = request.get_json(silent=True) or {}
    updates = payload.get("shares", [])
    if not isinstance(updates, list):
        return jsonify({"success": False, "error": "invalid_payload"}), 400
    try:
        valid_products = {sl.product_id for sl in StockLevel.query.filter_by(warehouse_id=warehouse_id).all()}
        for item in updates:
            pid = item.get("product_id")
            prt = item.get("partner_id")
            if not (isinstance(pid, int) and isinstance(prt, int)):
                continue
            if valid_products and pid not in valid_products:
                continue
            pct = float(item.get("share_percentage", item.get("share_percent", 0)) or 0)
            try:
                amt = float(item.get("share_amount", 0) or 0)
            except Exception:
                amt = 0.0
            notes = (item.get("notes") or "").strip() or None
            row = WarehousePartnerShare.query.filter_by(warehouse_id=warehouse_id, product_id=pid, partner_id=prt).first()
            if row:
                row.share_percentage = pct
                row.share_amount = amt
                row.notes = notes
            else:
                db.session.add(
                    WarehousePartnerShare(
                        warehouse_id=warehouse_id,
                        product_id=pid,
                        partner_id=prt,
                        share_percentage=pct,
                        share_amount=amt,
                        notes=notes,
                    )
                )
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.get("/invoices")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_sales", "view_reports")
def invoices():
    q = _q()
    qry = Invoice.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Invoice.invoice_number.ilike(like), Invoice.currency.ilike(like)))
    rows = qry.order_by(Invoice.id.desc()).limit(_limit()).all()
    return jsonify(
        [
            {
                "id": i.id,
                "text": _number_of(i, "invoice_number", "INV"),
                "number": _number_of(i, "invoice_number", "INV"),
                "total": float(i.total_amount or 0),
                "status": getattr(i.status, "value", i.status),
            }
            for i in rows
        ]
    )


@bp.get("/services")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_service")
def services():
    q = _q()
    qry = ServiceRequest.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            or_(
                ServiceRequest.service_number.ilike(like),
                ServiceRequest.vehicle_vrn.ilike(like),
                ServiceRequest.vehicle_model.ilike(like),
                ServiceRequest.chassis_number.ilike(like),
                ServiceRequest.description.ilike(like),
                ServiceRequest.engineer_notes.ilike(like),
                ServiceRequest.problem_description.ilike(like),
                ServiceRequest.diagnosis.ilike(like),
                ServiceRequest.resolution.ilike(like),
                ServiceRequest.notes.ilike(like),
            )
        )
    rows = qry.order_by(ServiceRequest.id.desc()).limit(_limit()).all()
    return jsonify(
        [{"id": s.id, "text": _number_of(s, "service_number", "SVC"), "number": _number_of(s, "service_number", "SVC")} for s in rows]
    )


@bp.get("/sales")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_sales", "view_reports")
def sales():
    q = _q()
    qry = Sale.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Sale.sale_number.ilike(like),))
    rows = qry.order_by(Sale.id.desc()).limit(_limit()).all()
    return jsonify(
        [
            {
                "id": s.id,
                "text": _number_of(s, "sale_number", "SAL"),
                "number": _number_of(s, "sale_number", "SAL"),
                "total": float(s.total_amount or 0),
                "status": getattr(s.status, "value", s.status),
                "payment_status": getattr(s.payment_status, "value", s.payment_status),
            }
            for s in rows
        ]
    )


@bp.get("/shipments")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_shipments", "view_reports")
def shipments():
    q = _q()
    qry = Shipment.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Shipment.shipment_number.ilike(like), Shipment.tracking_number.ilike(like)))
    rows = qry.order_by(Shipment.id.desc()).limit(_limit()).all()
    return jsonify(
        [
            {
                "id": sh.id,
                "text": _number_of(sh, "shipment_number", "SHP"),
                "number": _number_of(sh, "shipment_number", "SHP"),
                "status": sh.status,
                "value": float((sh.value_before or 0) or 0),
            }
            for sh in rows
        ]
    )

@bp.get("/search_employees", endpoint="search_employees")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_employees", "manage_expenses")
def search_employees():
    q = (request.args.get("q") or "").strip()
    limit = min(int(request.args.get("limit", 20)), 50)
    sid = (request.args.get("id") or "").strip()
    if sid.isdigit():
        e = db.session.get(Employee, int(sid))
        if not e:
            return jsonify({"results": []})
        label = e.name or f"#{e.id}"
        return jsonify({"results": [{"id": e.id, "text": label, "name": e.name, "phone": e.phone, "email": e.email}]})
    qry = Employee.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Employee.name.ilike(like), Employee.phone.ilike(like), Employee.email.ilike(like)))
    rows = qry.order_by(Employee.name.asc(), Employee.id.asc()).limit(limit).all()
    out = []
    for e in rows:
        label = e.name or f"#{e.id}"
        out.append({"id": e.id, "text": label, "name": e.name, "phone": e.phone, "email": e.email})
    return jsonify({"results": out})


@bp.get("/search_utility_accounts", endpoint="search_utility_accounts")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_expenses", "view_inventory")
def search_utility_accounts():
    q = (request.args.get("q") or "").strip()
    limit = min(int(request.args.get("limit", 20)), 50)
    typ = (request.args.get("type") or "").strip().upper()
    active_only = (request.args.get("active_only", "1") or "1") not in {"0", "false", "False"}
    aid = (request.args.get("id") or "").strip()
    if aid.isdigit():
        a = db.session.get(UtilityAccount, int(aid))
        if not a or (active_only and not a.is_active) or (typ and a.utility_type != typ):
            return jsonify({"results": []})
        label = a.alias or f"{a.provider} - {a.account_no or a.meter_no or a.id}"
        return jsonify({"results": [{"id": a.id, "text": label, "alias": a.alias, "provider": a.provider}]})
    qry = UtilityAccount.query
    if active_only:
        qry = qry.filter(UtilityAccount.is_active.is_(True))
    if typ:
        qry = qry.filter(UtilityAccount.utility_type == typ)
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(UtilityAccount.alias.ilike(like),
                             UtilityAccount.provider.ilike(like),
                             UtilityAccount.account_no.ilike(like),
                             UtilityAccount.meter_no.ilike(like)))
    rows = qry.order_by(UtilityAccount.alias.asc().nulls_last(), UtilityAccount.provider.asc(), UtilityAccount.id.asc()).limit(limit).all()
    out = []
    for a in rows:
        label = a.alias or f"{a.provider} - {a.account_no or a.meter_no or a.id}"
        out.append({"id": a.id, "text": label})
    return jsonify({"results": out})


@bp.get("/search_stock_adjustments", endpoint="search_stock_adjustments")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_inventory", "manage_expenses")
def search_stock_adjustments():
    q = (request.args.get("q") or "").strip()
    limit = min(int(request.args.get("limit", 20)), 50)
    reason = (request.args.get("reason") or "").strip().upper()
    warehouse_id = request.args.get("warehouse_id", type=int)
    sid = (request.args.get("id") or "").strip()
    def rlabel(x):
        return "تالف" if x == "DAMAGED" else ("استخدام داخلي" if x == "STORE_USE" else (x or ""))
    if sid.isdigit():
        sa = db.session.get(StockAdjustment, int(sid))
        if not sa:
            return jsonify({"results": []})
        if reason and sa.reason != reason:
            return jsonify({"results": []})
        if warehouse_id and sa.warehouse_id != warehouse_id:
            return jsonify({"results": []})
        dt = sa.date.strftime("%Y-%m-%d") if sa.date else ""
        label = f"#{sa.id} — {rlabel(sa.reason)} — {dt}"
        return jsonify({"results": [{"id": sa.id, "text": label, "total_cost": float(sa.total_cost or 0)}]})
    qry = StockAdjustment.query
    if reason:
        qry = qry.filter(StockAdjustment.reason == reason)
    if warehouse_id:
        qry = qry.filter(StockAdjustment.warehouse_id == warehouse_id)
    if q and q.isdigit():
        qry = qry.filter(StockAdjustment.id == int(q))
    rows = qry.order_by(StockAdjustment.id.desc()).limit(limit).all()
    out = []
    for sa in rows:
        dt = sa.date.strftime("%Y-%m-%d") if sa.date else ""
        label = f"#{sa.id} — {rlabel(sa.reason)} — {dt}"
        out.append({"id": sa.id, "text": label, "total_cost": float(sa.total_cost or 0)})
    return jsonify({"results": out})


@bp.get("/stock_adjustments/<int:id>/total", endpoint="stock_adjustment_total")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_inventory", "manage_expenses")
def stock_adjustment_total(id: int):
    sa = db.session.get(StockAdjustment, id)
    if not sa:
        return jsonify({"error": "Not Found"}), 404
    total = float(sa.total_cost or 0)
    return jsonify({"id": id, "total_cost": total, "amount": total})

@bp.post("/shipments")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_warehouses")
def create_shipment_api():
    data = request.get_json(silent=True) or {}
    sh = Shipment(
        shipment_number=(data.get("shipment_number") or None),
        shipment_date=data.get("shipment_date"),
        expected_arrival=data.get("expected_arrival"),
        actual_arrival=data.get("actual_arrival"),
        origin=data.get("origin"),
        destination_id=(int(data["destination_id"]) if str(data.get("destination_id", "")).isdigit() else None),
        destination=(data.get("destination") or None),
        carrier=data.get("carrier"),
        tracking_number=data.get("tracking_number"),
        status=data.get("status"),
        shipping_cost=_D(data.get("shipping_cost")),
        customs=_D(data.get("customs")),
        vat=_D(data.get("vat")),
        insurance=_D(data.get("insurance")),
        currency=_norm_currency(data.get("currency")),
        notes=(data.get("notes") or None),
        sale_id=(int(data["sale_id"]) if str(data.get("sale_id", "")).isdigit() else None),
    )
    db.session.add(sh)
    db.session.flush()
    for it in (data.get("items") or []):
        db.session.add(
            ShipmentItem(
                shipment_id=sh.id,
                product_id=int(it["product_id"]),
                warehouse_id=int(it["warehouse_id"]),
                quantity=_D(it.get("quantity")),
                unit_cost=_D(it.get("unit_cost")),
                declared_value=_D(it.get("declared_value")),
                notes=(it.get("notes") or None),
            )
        )
    for ln in (data.get("partners") or []):
        if not ln.get("partner_id"):
            continue
        db.session.add(
            ShipmentPartner(
                shipment_id=sh.id,
                partner_id=int(ln["partner_id"]),
                share_percentage=float(ln.get("share_percentage") or 0),
                share_amount=float(ln.get("share_amount") or 0),
                identity_number=ln.get("identity_number"),
                phone_number=ln.get("phone_number"),
                address=ln.get("address"),
                unit_price_before_tax=_D(ln.get("unit_price_before_tax")),
                expiry_date=ln.get("expiry_date"),
                notes=ln.get("notes"),
                role=ln.get("role"),
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
        _apply_arrival_items(_items_snapshot(sh))
    try:
        db.session.commit()
        return jsonify({"success": True, "id": sh.id}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.get("/shipments/<int:id>")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_warehouses", "view_reports")
def get_shipment_api(id: int):
    sh = db.session.query(Shipment).filter_by(id=id).first()
    if not sh:
        return jsonify({"error": "Not Found"}), 404
    return jsonify(
        {
            "id": sh.id,
            "number": sh.shipment_number,
            "status": sh.status,
            "origin": sh.origin,
            "destination_id": sh.destination_id,
            "expected_arrival": (sh.expected_arrival.isoformat() if sh.expected_arrival else None),
            "total_value": float(sh.total_value or 0),
            "items": [
                {
                    "product_id": it.product_id,
                    "warehouse_id": it.warehouse_id,
                    "quantity": float(it.quantity or 0),
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
                    "partner_id": ln.partner_id,
                    "share_percentage": float(ln.share_percentage or 0),
                    "share_amount": float(ln.share_amount or 0),
                    "identity_number": ln.identity_number,
                    "phone_number": ln.phone_number,
                    "address": ln.address,
                    "unit_price_before_tax": float(ln.unit_price_before_tax or 0),
                    "expiry_date": (ln.expiry_date.isoformat() if getattr(ln, "expiry_date", None) else None),
                    "notes": ln.notes,
                    "role": getattr(ln, "role", None),
                }
                for ln in sh.partners
            ],
        }
    )


@bp.patch("/shipments/<int:id>")
@bp.put("/shipments/<int:id>", endpoint="update_shipment_api")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_warehouses")
def update_shipment_api(id: int):
    sh = db.session.query(Shipment).filter_by(id=id).first()
    if not sh:
        return jsonify({"error": "Not Found"}), 404
    old_status = (sh.status or "").upper()
    old_items = _items_snapshot(sh)
    data = request.get_json(silent=True) or {}
    for k in ["shipment_number", "origin", "carrier", "tracking_number", "status", "notes", "destination"]:
        if k in data:
            setattr(sh, k, (data.get(k) or None))
    for k in ["shipment_date", "expected_arrival", "actual_arrival", "currency"]:
        if k in data:
            setattr(sh, k, data.get(k))
    if "destination_id" in data:
        sh.destination_id = int(data["destination_id"]) if str(data["destination_id"]).isdigit() else None
    for k in ["shipping_cost", "customs", "vat", "insurance"]:
        if k in data:
            setattr(sh, k, _D(data.get(k)))
    if "sale_id" in data:
        sh.sale_id = int(data["sale_id"]) if str(data["sale_id"]).isdigit() else None
    if "items" in data:
        sh.items.clear()
        db.session.flush()
        for it in (data.get("items") or []):
            sh.items.append(
                ShipmentItem(
                    product_id=int(it["product_id"]),
                    warehouse_id=int(it["warehouse_id"]),
                    quantity=_D(it.get("quantity")),
                    unit_cost=_D(it.get("unit_cost")),
                    declared_value=_D(it.get("declared_value")),
                    notes=(it.get("notes") or None),
                )
            )
    if "partners" in data:
        sh.partners.clear()
        db.session.flush()
        for ln in (data.get("partners") or []):
            if not ln.get("partner_id"):
                continue
            sh.partners.append(
                ShipmentPartner(
                    partner_id=int(ln["partner_id"]),
                    share_percentage=float(ln.get("share_percentage") or 0),
                    share_amount=float(ln.get("share_amount") or 0),
                    identity_number=ln.get("identity_number"),
                    phone_number=ln.get("phone_number"),
                    address=ln.get("address"),
                    unit_price_before_tax=_D(ln.get("unit_price_before_tax")),
                    expiry_date=ln.get("expiry_date"),
                    notes=ln.get("notes"),
                    role=ln.get("role"),
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
        return jsonify({"success": True, "id": sh.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.post("/shipments/<int:id>/mark-arrived")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_warehouses")
def api_mark_arrived(id: int):
    sh = db.session.query(Shipment).filter_by(id=id).first()
    if not sh:
        return jsonify({"error": "Not Found"}), 404
    if (sh.status or "").upper() == "ARRIVED":
        return jsonify({"success": True, "message": "already_arrived"})
    try:
        _apply_arrival_items(_items_snapshot(sh))
        sh.status = "ARRIVED"
        sh.actual_arrival = sh.actual_arrival or datetime.utcnow()
        _compute_shipment_totals(sh)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.post("/shipments/<int:id>/cancel")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_warehouses")
def api_cancel_shipment(id: int):
    sh = db.session.query(Shipment).filter_by(id=id).first()
    if not sh:
        return jsonify({"error": "Not Found"}), 404
    try:
        if (sh.status or "").upper() == "ARRIVED":
            _reverse_arrival_items(_items_snapshot(sh))
        sh.status = "CANCELLED"
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.delete("/shipments/<int:id>")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_warehouses")
def delete_shipment_api(id: int):
    sh = db.session.query(Shipment).filter_by(id=id).first()
    if not sh:
        return jsonify({"error": "Not Found"}), 404
    try:
        if (sh.status or "").upper() == "ARRIVED":
            _reverse_arrival_items(_items_snapshot(sh))
        sh.partners.clear()
        sh.items.clear()
        db.session.flush()
        db.session.delete(sh)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.get("/transfers")
@login_required
@limiter.limit("60/minute")
@permission_required("warehouse_transfer", "manage_inventory")
def transfers():
    q = _q()
    qry = Transfer.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Transfer.reference.ilike(like),))
    rows = qry.order_by(Transfer.id.desc()).limit(_limit()).all()
    return jsonify(
        [
            {
                "id": t.id,
                "text": _number_of(t, "reference", "TRF"),
                "number": _number_of(t, "reference", "TRF"),
                "product_id": t.product_id,
                "source_id": t.source_id,
                "destination_id": t.destination_id,
            }
            for t in rows
        ]
    )


@bp.get("/preorders")
@login_required
@limiter.limit("60/minute")
@permission_required("view_preorders", "manage_inventory")
def preorders():
    q = _q()
    qry = PreOrder.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(PreOrder.reference.ilike(like),))
    rows = qry.order_by(PreOrder.id.desc()).limit(_limit()).all()
    return jsonify(
        [
            {
                "id": po.id,
                "text": _number_of(po, "reference", "PO"),
                "number": _number_of(po, "reference", "PO"),
                "status": getattr(po.status, "value", po.status),
                "total": float(po.total_before_tax or 0),
            }
            for po in rows
        ]
    )


@bp.get("/online_preorders")
@login_required
@limiter.limit("60/minute")
@permission_required("view_preorders")
def online_preorders():
    q = _q()
    qry = OnlinePreOrder.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(OnlinePreOrder.order_number.ilike(like),))
    rows = qry.order_by(OnlinePreOrder.id.desc()).limit(_limit()).all()
    return jsonify(
        [
            {
                "id": o.id,
                "text": _number_of(o, "order_number", "OPR"),
                "number": _number_of(o, "order_number", "OPR"),
                "status": o.status,
                "payment_status": o.payment_status,
                "total": float(o.total_amount or 0),
            }
            for o in rows
        ]
    )


@bp.get("/expenses")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_expenses")
def expenses():
    q = _q()
    qry = Expense.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Expense.tax_invoice_number.ilike(like), Expense.description.ilike(like)))
    rows = qry.order_by(Expense.id.desc()).limit(_limit()).all()
    return jsonify(
        [
            {
                "id": e.id,
                "text": _number_of(e, "tax_invoice_number", "EXP"),
                "number": _number_of(e, "tax_invoice_number", "EXP"),
                "amount": float(e.amount or 0),
                "currency": e.currency,
            }
            for e in rows
        ]
    )


@bp.get("/loan_settlements")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_vendors")
def loan_settlements():
    q = _q()
    qry = SupplierLoanSettlement.query
    if q.isdigit():
        qry = qry.filter(SupplierLoanSettlement.id == int(q))
    rows = qry.order_by(SupplierLoanSettlement.id.desc()).limit(_limit()).all()
    return jsonify(
        [{"id": x.id, "text": f"Settlement #{x.id}", "number": f"SET-{x.id}", "amount": float(x.settled_price or 0)} for x in rows]
    )


@bp.get("/payments")
@bp.get("/search_payments", endpoint="search_payments")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_payments", "view_reports")
def payments():
    q = _q()
    qry = Payment.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Payment.payment_number.ilike(like), Payment.receipt_number.ilike(like)))
    rows = qry.order_by(Payment.id.desc()).limit(_limit()).all()
    return jsonify(
        [
            {
                "id": p.id,
                "text": _number_of(p, "payment_number", "PMT"),
                "number": _number_of(p, "payment_number", "PMT"),
                "amount": float(p.total_amount or 0),
                "status": getattr(p.status, "value", p.status),
                "method": getattr(p.method, "value", p.method),
            }
            for p in rows
        ]
    )


@bp.get("/sales/<int:id>")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_sales", "view_reports")
def get_sale(id: int):
    s = db.session.query(Sale).options(joinedload(Sale.lines)).filter_by(id=id).first()
    if not s:
        return jsonify({"error": "Not Found"}), 404
    return jsonify({"sale": sale_to_dict(s)})


@bp.post("/sales")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_sales")
def create_sale_api():
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "DRAFT").upper()
    s = Sale(
        sale_number=None,
        customer_id=data.get("customer_id"),
        seller_id=data.get("seller_id") or getattr(current_user, "id", None),
        sale_date=data.get("sale_date") or datetime.utcnow(),
        status=status,
        currency=(data.get("currency") or "ILS").upper(),
        tax_rate=float(data.get("tax_rate") or 0),
        discount_total=_D(data.get("discount_total")),
        shipping_cost=_D(data.get("shipping_cost")),
        notes=(data.get("notes") or None),
    )
    db.session.add(s)
    db.session.flush()
    _safe_generate_number_after_flush(s)
    lines = []
    for it in (data.get("lines") or []):
        pid = int(it.get("product_id") or 0)
        qty = int(float(it.get("quantity") or 0))
        wid = it.get("warehouse_id")
        wid = int(wid) if str(wid or "").isdigit() else None
        if not (pid and qty > 0):
            continue
        chosen = wid or _auto_pick_warehouse(pid, qty, preferred_wid=None)
        if status == "CONFIRMED":
            if not chosen or _available_qty(pid, chosen) < qty:
                db.session.rollback()
                return jsonify({"success": False, "error": "insufficient_stock", "product_id": pid}), 400
        ln = SaleLine(
            sale_id=s.id,
            product_id=pid,
            warehouse_id=chosen,
            quantity=qty,
            unit_price=float(it.get("unit_price") or 0),
            discount_rate=float(it.get("discount_rate") or 0),
            tax_rate=float(it.get("tax_rate") or 0),
            note=(it.get("note") or None),
        )
        db.session.add(ln)
        lines.append((pid, chosen))
    if status == "CONFIRMED":
        _lock_stock_rows([(p, w) for (p, w) in lines if w])
        _reserve_stock(s)
    try:
        db.session.commit()
        return jsonify({"success": True, "id": s.id, "sale_number": s.sale_number}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.put("/sales/<int:id>")
@bp.patch("/sales/<int:id>", endpoint="update_sale_api")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_sales")
def update_sale_api(id: int):
    s = db.session.query(Sale).options(joinedload(Sale.lines)).filter_by(id=id).first()
    if not s:
        return jsonify({"error": "Not Found"}), 404
    old_status = (s.status or "").upper()
    data = request.get_json(silent=True) or {}
    if "customer_id" in data:
        s.customer_id = data.get("customer_id")
    if "seller_id" in data:
        s.seller_id = data.get("seller_id")
    if "sale_date" in data:
        s.sale_date = data.get("sale_date") or s.sale_date
    if "currency" in data:
        s.currency = (data.get("currency") or s.currency or "ILS").upper()
    if "tax_rate" in data:
        s.tax_rate = float(data.get("tax_rate") or 0)
    if "discount_total" in data:
        s.discount_total = _D(data.get("discount_total"))
    if "shipping_cost" in data:
        s.shipping_cost = _D(data.get("shipping_cost"))
    if "notes" in data:
        s.notes = data.get("notes") or None
    new_status = (data.get("status") or s.status or "DRAFT").upper()
    replace_lines = "lines" in data
    if replace_lines:
        if old_status == "CONFIRMED":
            _release_stock(s)
        SaleLine.query.where(SaleLine.sale_id == s.id).delete(synchronize_session=False)
        db.session.flush()
        pairs = []
        for it in (data.get("lines") or []):
            pid = int(it.get("product_id") or 0)
            qty = int(float(it.get("quantity") or 0))
            wid = it.get("warehouse_id")
            wid = int(wid) if str(wid or "").isdigit() else None
            if not (pid and qty > 0):
                continue
            chosen = wid or _auto_pick_warehouse(pid, qty, preferred_wid=None)
            if new_status == "CONFIRMED":
                if not chosen or _available_qty(pid, chosen) < qty:
                    db.session.rollback()
                    return jsonify({"success": False, "error": "insufficient_stock", "product_id": pid}), 400
            db.session.add(
                SaleLine(
                    sale_id=s.id,
                    product_id=pid,
                    warehouse_id=chosen,
                    quantity=qty,
                    unit_price=float(it.get("unit_price") or 0),
                    discount_rate=float(it.get("discount_rate") or 0),
                    tax_rate=float(it.get("tax_rate") or 0),
                    note=(it.get("note") or None),
                )
            )
            pairs.append((pid, chosen))
        if new_status == "CONFIRMED" and pairs:
            _lock_stock_rows(pairs)
    s.status = new_status
    try:
        if old_status != "CONFIRMED" and new_status == "CONFIRMED":
            _reserve_stock(s)
        elif old_status == "CONFIRMED" and new_status != "CONFIRMED":
            _release_stock(s)
        elif old_status == "CONFIRMED" and new_status == "CONFIRMED" and replace_lines:
            _reserve_stock(s)
        db.session.commit()
        return jsonify({"success": True, "id": s.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.post("/sales/<int:id>/status")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_sales")
def change_sale_status_api(id: int):
    s = db.session.query(Sale).options(joinedload(Sale.lines)).filter_by(id=id).first()
    if not s:
        return jsonify({"error": "Not Found"}), 404
    target = ((request.get_json(silent=True) or {}).get("status") or "").upper()
    valid = {"DRAFT": {"CONFIRMED", "CANCELLED"}, "CONFIRMED": {"CANCELLED", "REFUNDED"}, "CANCELLED": set(), "REFUNDED": set()}
    if target not in valid.get((s.status or "DRAFT").upper(), set()):
        return jsonify({"success": False, "error": "invalid_transition"}), 400
    try:
        if target == "CONFIRMED":
            pairs = []
            for ln in (s.lines or []):
                pid, wid, qty = ln.product_id, (ln.warehouse_id or _auto_pick_warehouse(ln.product_id, int(ln.quantity or 0))), int(ln.quantity or 0)
                if not wid or _available_qty(pid, wid) < qty:
                    return jsonify({"success": False, "error": "insufficient_stock", "product_id": pid}), 400
                ln.warehouse_id = wid
                pairs.append((pid, wid))
            db.session.flush()
            _lock_stock_rows(pairs)
            s.status = "CONFIRMED"
            _reserve_stock(s)
        elif target in ("CANCELLED", "REFUNDED"):
            _release_stock(s)
            s.status = target
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.delete("/sales/<int:id>")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_sales")
def delete_sale_api(id: int):
    s = db.session.query(Sale).filter_by(id=id).first()
    if not s:
        return jsonify({"error": "Not Found"}), 404
    try:
        if float(getattr(s, "total_paid", 0) or 0) > 0:
            return jsonify({"success": False, "error": "has_payments"}), 400
        _release_stock(s)
        db.session.delete(s)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.get("/sales/<int:id>/payments")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_sales", "view_reports")
def sale_payments_api(id: int):
    rows = (
        db.session.query(Payment)
        .filter(Payment.sale_id == id)
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
        .all()
    )
    return jsonify(
        {
            "sale_id": id,
            "payments": [
                {
                    "id": p.id,
                    "payment_date": (p.payment_date.isoformat() if getattr(p, "payment_date", None) else None),
                    "total_amount": float(p.total_amount or 0),
                    "currency": getattr(p, "currency", None),
                    "status": getattr(p, "status", None),
                    "method": getattr(p, "method", None),
                }
                for p in rows
            ],
        }
    )


@bp.post("/sales/quick")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_sales")
def quick_sell_api():
    d = request.get_json(silent=True) or {}
    pid = int(d.get("product_id") or 0)
    qty = int(float(d.get("quantity") or 0))
    wid = d.get("warehouse_id")
    wid = int(wid) if str(wid or "").isdigit() else None
    customer_id = int(d.get("customer_id") or 0)
    seller_id = int(d.get("seller_id") or (getattr(current_user, "id", 0) or 0))
    status = (d.get("status") or "DRAFT").upper()
    if not (pid and qty > 0 and customer_id and seller_id):
        return jsonify({"success": False, "error": "invalid"}), 400
    chosen = wid or _auto_pick_warehouse(pid, qty, preferred_wid=None)
    if status == "CONFIRMED":
        if not chosen or _available_qty(pid, chosen) < qty:
            return jsonify({"success": False, "error": "insufficient_stock"}), 400
        _lock_stock_rows([(pid, chosen)])
    price = float(d.get("unit_price") or 0) or float(getattr(db.session.get(Product, pid), "price", 0) or 0)
    s = Sale(
        sale_number=None,
        customer_id=customer_id,
        seller_id=seller_id,
        sale_date=datetime.utcnow(),
        status=status,
        currency=(d.get("currency") or "ILS").upper(),
    )
    db.session.add(s)
    db.session.flush()
    _safe_generate_number_after_flush(s)
    db.session.add(SaleLine(sale_id=s.id, product_id=pid, warehouse_id=chosen, quantity=qty, unit_price=price, discount_rate=0, tax_rate=0))
    db.session.flush()
    if status == "CONFIRMED":
        _reserve_stock(s)
    try:
        db.session.commit()
        return jsonify({"success": True, "id": s.id, "sale_number": s.sale_number}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.get("/exchange_transactions")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_inventory", "view_inventory", "view_warehouses")
def list_exchange_transactions():
    q = _q()
    qry = ExchangeTransaction.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            or_(
                ExchangeTransaction.notes.ilike(like),
                ExchangeTransaction.direction.ilike(like),
            )
        )
    rows = qry.order_by(ExchangeTransaction.id.desc()).limit(_limit(50, 200)).all()
    data = []
    for x in rows:
        data.append(
            {
                "id": x.id,
                "product_id": getattr(x, "product_id", None),
                "warehouse_id": getattr(x, "warehouse_id", None),
                "partner_id": getattr(x, "partner_id", None),
                "direction": getattr(x, "direction", None),
                "quantity": int(getattr(x, "quantity", 0) or 0),
                "unit_cost": float(getattr(x, "unit_cost", 0) or 0),
                "is_priced": bool(getattr(x, "is_priced", False)),
                "notes": getattr(x, "notes", None),
            }
        )
    return jsonify({"results": data})


def _ensure_exchange_warehouse(wid: int) -> Warehouse:
    wh = Warehouse.query.get(wid)
    if not wh:
        raise ValueError("warehouse_not_found")
    wt = getattr(wh.warehouse_type, "value", wh.warehouse_type)
    if wt != WarehouseType.EXCHANGE.value:
        raise ValueError("not_exchange_warehouse")
    if not getattr(wh, "supplier_id", None):
        raise ValueError("exchange_requires_supplier")
    return wh


def _stock_row_locked(pid: int, wid: int) -> StockLevel:
    rec = (
        db.session.query(StockLevel)
        .filter_by(product_id=pid, warehouse_id=wid)
        .with_for_update(nowait=False)
        .first()
    )
    if not rec:
        rec = StockLevel(product_id=pid, warehouse_id=wid, quantity=0, reserved_quantity=0)
        db.session.add(rec)
        db.session.flush()
    return rec


@bp.post("/exchange_transactions")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_inventory", "manage_warehouses")
def create_exchange_transaction():
    d = request.get_json(silent=True) or {}
    try:
        pid = int(d.get("product_id") or 0)
        wid = int(d.get("warehouse_id") or 0)
        partner_id = int(d.get("partner_id") or 0) or None
        direction = (d.get("direction") or "").strip().upper()
        qty = int(float(d.get("quantity") or 0))
        unit_cost = _D(d.get("unit_cost"))
        notes = (d.get("notes") or "").strip() or None
    except Exception:
        return jsonify({"success": False, "error": "invalid_payload"}), 400
    if not (pid and wid and direction in {"IN", "OUT", "ADJUSTMENT"} and qty > 0):
        return jsonify({"success": False, "error": "invalid"}), 400
    try:
        _ensure_exchange_warehouse(wid)
    except ValueError as e:
        code = str(e)
        msg = {
            "warehouse_not_found": "المخزن غير موجود",
            "not_exchange_warehouse": "يجب أن تكون الحركة على مخزن تبادل.",
            "exchange_requires_supplier": "مخزن التبادل يجب أن يكون مربوطًا بمورد.",
        }.get(code, "invalid_warehouse")
        return jsonify({"success": False, "error": msg}), 400
    priced = bool(unit_cost and unit_cost > 0)
    if direction == "ADJUSTMENT":
        if not priced:
            return jsonify({"success": False, "error": "هذه تسوية: أدخل تكلفة موجبة للوحدة."}), 400
    if direction == "OUT":
        avail = _available_qty(pid, wid)
        if avail < qty:
            return jsonify({"success": False, "error": "insufficient_stock", "available": max(avail, 0)}), 400
    xt = ExchangeTransaction(
        product_id=pid,
        warehouse_id=wid,
        partner_id=partner_id,
        direction=direction,
        quantity=qty,
        unit_cost=(unit_cost if priced else None),
        is_priced=bool(priced),
        notes=notes,
    )
    db.session.add(xt)
    db.session.flush()
    warning = None
    try:
        if direction == "IN":
            _lock_stock_rows([(pid, wid)])
            rec = _stock_row_locked(pid, wid)
            rec.quantity = int(rec.quantity or 0) + qty
            db.session.flush()
            if not priced:
                warning = "لم تُدخل تكلفة، ستُحفظ الحركة كغير مسعّرة وسيُطلب تسعيرها لاحقًا."
        elif direction == "OUT":
            _lock_stock_rows([(pid, wid)])
            rec = _stock_row_locked(pid, wid)
            available = int(rec.quantity or 0) - int(rec.reserved_quantity or 0)
            if available < qty:
                db.session.rollback()
                return jsonify({"success": False, "error": "insufficient_stock", "available": max(available, 0)}), 400
            rec.quantity = int(rec.quantity or 0) - qty
            db.session.flush()
            if not priced:
                warning = "لم تُدخل تكلفة لهذه الحركة."
        elif direction == "ADJUSTMENT":
            if not priced:
                db.session.rollback()
                return jsonify({"success": False, "error": "هذه تسوية: أدخل تكلفة موجبة للوحدة."}), 400
        db.session.commit()
        resp = {"success": True, "id": xt.id}
        if warning:
            resp["warning"] = warning
        return jsonify(resp), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.get("/exchange_transactions/<int:id>")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_inventory", "view_inventory")
def get_exchange_transaction(id: int):
    x = ExchangeTransaction.query.get(id)
    if not x:
        return jsonify({"error": "Not Found"}), 404
    return jsonify(
        {
            "id": x.id,
            "product_id": getattr(x, "product_id", None),
            "warehouse_id": getattr(x, "warehouse_id", None),
            "partner_id": getattr(x, "partner_id", None),
            "direction": getattr(x, "direction", None),
            "quantity": int(getattr(x, "quantity", 0) or 0),
            "unit_cost": float(getattr(x, "unit_cost", 0) or 0),
            "is_priced": bool(getattr(x, "is_priced", False)),
            "notes": getattr(x, "notes", None),
        }
    )


@bp.delete("/exchange_transactions/<int:id>")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_inventory", "manage_warehouses")
def delete_exchange_transaction(id: int):
    x = ExchangeTransaction.query.get(id)
    if not x:
        return jsonify({"error": "Not Found"}), 404
    pid = int(getattr(x, "product_id", 0) or 0)
    wid = int(getattr(x, "warehouse_id", 0) or 0)
    qty = int(getattr(x, "quantity", 0) or 0)
    direction = (getattr(x, "direction", "") or "").upper()
    try:
        if direction in {"IN", "OUT"} and pid and wid and qty > 0:
            _lock_stock_rows([(pid, wid)])
            rec = _stock_row_locked(pid, wid)
            if direction == "IN":
                reserved = int(rec.reserved_quantity or 0)
                new_qty = int(rec.quantity or 0) - qty
                if new_qty < 0 or new_qty < reserved:
                    return jsonify({"success": False, "error": "insufficient_stock_to_reverse"}), 400
                rec.quantity = new_qty
            elif direction == "OUT":
                rec.quantity = int(rec.quantity or 0) + qty
            db.session.flush()
        db.session.delete(x)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@bp.app_errorhandler(403)
def forbidden(e):
    return jsonify({"error": "Forbidden"}), 403


@bp.app_errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Too Many Requests", "detail": str(e.description)}), 429


@bp.app_errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not Found"}), 404


@bp.app_errorhandler(500)
def server_error(e):
    db.session.rollback()
    current_app.logger.exception("API 500: %s", getattr(e, "description", e))
    return jsonify({"error": "Server Error"}), 500


@bp.get("/users", endpoint="users")
@login_required
def api_search_users():
    q = (request.args.get("q") or "").strip()
    limit = min(int(request.args.get("limit", 20) or 20), 50)
    active_only = (request.args.get("active_only", "1") or "1") not in {"0", "false", "False"}
    role_names = [s.strip() for s in (request.args.get("role") or "").split(",") if s.strip()]
    role_ids = [int(s) for s in (request.args.get("role_id") or "").split(",") if s.strip().isdigit()]
    if request.args.get("id"):
        uid = request.args.get("id")
        if str(uid).isdigit():
            u = db.session.get(User, int(uid))
            if not u:
                return jsonify({"results": []})
            if active_only and not u.is_active:
                return jsonify({"results": []})
            if role_names or role_ids:
                if u.role is None:
                    return jsonify({"results": []})
                if role_names and u.role.name not in role_names:
                    return jsonify({"results": []})
                if role_ids and u.role_id not in role_ids:
                    return jsonify({"results": []})
            txt = (getattr(u, "username", "") or "").strip()
            disp = (getattr(u, "name", None) or "").strip()
            email = (getattr(u, "email", "") or "").strip()
            text = disp or txt or email or f"User #{u.id}"
            if email and email.lower() != text.lower():
                text = f"{text} ({email})"
            return jsonify({"results": [{"id": u.id, "text": text}]})
    qs = User.query
    if active_only:
        qs = qs.filter(User.is_active.is_(True))
    if role_names or role_ids:
        qs = qs.join(Role, isouter=False)
        if role_names:
            qs = qs.filter(Role.name.in_(role_names))
        if role_ids:
            qs = qs.filter(Role.id.in_(role_ids))
    if q:
        ilike = f"%{q}%"
        conds = [User.username.ilike(ilike), User.email.ilike(ilike)]
        if hasattr(User, "name"):
            conds.append(User.name.ilike(ilike))
        qs = qs.filter(or_(*conds))
    rows = qs.order_by(User.username.asc()).limit(limit).all()
    results = []
    for u in rows:
        txt = (getattr(u, "username", "") or "").strip()
        disp = (getattr(u, "name", None) or "").strip()
        email = (getattr(u, "email", "") or "").strip()
        text = disp or txt or email or f"User #{u.id}"
        if email and email.lower() != text.lower():
            text = f"{text} ({email})"
        results.append({"id": u.id, "text": text})
    return jsonify({"results": results})


@bp.get("/equipment-types/search")
@login_required
def search_equipment_types():
    q = (request.args.get("q") or "").strip()
    query = EquipmentType.query
    if q:
        query = query.filter(EquipmentType.name.ilike(f"%{q}%"))
    results = [{"id": et.id, "text": et.name} for et in query.order_by(EquipmentType.name).limit(20).all()]
    return jsonify(results)


@bp.post("/equipment-types/create")
@login_required
@csrf.exempt
def create_equipment_type():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "الاسم مطلوب"}), 400
    et = EquipmentType(
        name=name,
        model_number=(data.get("model") or "").strip() or None,
        chassis_number=(data.get("chassis_number") or "").strip() or None,
        category=(data.get("category") or "").strip() or None,
        notes=(data.get("notes") or "").strip() or None,
    )
    db.session.add(et)
    try:
        db.session.commit()
        return jsonify({"id": et.id, "text": et.name}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400
