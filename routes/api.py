from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required
from sqlalchemy import or_, func
from typing import Callable, Iterable, List, Dict, Any, Optional
from sqlalchemy.exc import IntegrityError

from extensions import db, limiter, csrf
from models import (
    Customer, Supplier, Partner, Product, Warehouse, User, Employee,
    Invoice, ServiceRequest, SupplierLoanSettlement, ProductCategory, Payment,
    EquipmentType, StockLevel, Sale, Shipment, Transfer, PreOrder,
    OnlinePreOrder, Expense
)

bp = Blueprint("api", __name__, url_prefix="/api")

def _q() -> str:
    return (request.args.get("q") or "").strip()

def _limit(default: int = 20, max_: int = 50) -> int:
    try:
        n = int(request.args.get("limit", default))
    except Exception:
        n = default
    return max(1, min(n, max_))

def _number_of(o, attr: Optional[str] = None, fallback_prefix: Optional[str] = None) -> str:
    if attr and getattr(o, attr, None):
        return str(getattr(o, attr))
    for cand in (
        "invoice_number", "service_number", "sale_number", "shipment_number",
        "order_number", "payment_number", "receipt_number",
        "reference", "cart_id", "tax_invoice_number"
    ):
        v = getattr(o, cand, None)
        if v:
            return str(v)
    if fallback_prefix:
        return f"{fallback_prefix}-{getattr(o, 'id', '')}"
    return str(getattr(o, "id", ""))

def _as_options(rows: Iterable[Any], label_attr: str = "name",
                extra: Optional[Callable[[Any], Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    extra = extra or (lambda o: {})
    out: List[Dict[str, Any]] = []
    for o in rows:
        label = getattr(o, label_attr, None)
        if not label:
            for cand in ("name", "username", "invoice_number", "service_number", "sale_number",
                         "shipment_number", "order_number", "cart_id", "payment_number", "reference"):
                label = getattr(o, cand, None)
                if label:
                    break
        if not label:
            label = str(getattr(o, "id", ""))
        out.append({"id": o.id, "text": str(label), **extra(o)})
    return out

def _ilike_filters(model, fields: List[str], q: str):
    like = f"%{q}%"
    return [getattr(model, f).ilike(like) for f in fields if hasattr(model, f)]

def search_model(model, fields: List[str], label_attr: str = "name",
                 default_order_attr: Optional[str] = None,
                 limit_default: int = 20, limit_max: int = 50,
                 extra: Optional[Callable[[Any], Dict[str, Any]]] = None):
    q = _q()
    qry = model.query
    if q:
        qry = qry.filter(or_(*_ilike_filters(model, fields, q)))
    order_attr = default_order_attr or label_attr
    order_col = getattr(model, order_attr, getattr(model, "id"))
    rows = qry.order_by(order_col).limit(_limit(default=limit_default, max_=limit_max)).all()
    return jsonify(_as_options(rows, label_attr, extra=extra))

@bp.get("/customers")
@bp.get("/search_customers", endpoint="search_customers")
@login_required
@limiter.limit("60/minute")
def customers():
    return search_model(Customer, ["name", "phone", "email"], label_attr="name")

@bp.post("/customers")
@login_required
@limiter.limit("30/minute")
def create_customer_api():
    name = (request.form.get("name") or "").strip()
    email = normalize_email(request.form.get("email"))
    phone = normalize_phone(request.form.get("phone"))
    whatsapp = normalize_phone(request.form.get("whatsapp"))
    address = (request.form.get("address") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    discount_rate = request.form.get("discount_rate", type=float) or 0
    credit_limit = request.form.get("credit_limit", type=float) or 0
    is_online = bool(request.form.get("is_online"))
    is_active = bool(request.form.get("is_active", "1"))

    if not name or not email:
        return jsonify(success=False, error="الاسم والبريد مطلوبان"), 400

    try:
        c = Customer(
            name=name, email=email, phone=phone, whatsapp=whatsapp,
            address=address, notes=notes, discount_rate=discount_rate,
            credit_limit=credit_limit, is_online=is_online, is_active=is_active
        )
        pwd = (request.form.get("password") or "").strip()
        if pwd:
            c.set_password(pwd)
        db.session.add(c)
        db.session.commit()
        return jsonify(success=True, id=c.id, name=c.name, text=c.name)
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(success=False, error="فشل حفظ العميل"), 500

@bp.get("/suppliers")
@bp.get("/search_suppliers", endpoint="search_suppliers")
@login_required
@limiter.limit("60/minute")
def suppliers():
    return search_model(
        Supplier,
        ["name", "phone", "identity_number"],
        label_attr="name",
        default_order_attr="name"
    )

@bp.get("/suppliers/<int:id>")
@login_required
@limiter.limit("60/minute")
def get_supplier(id):
    supplier = Supplier.query.get_or_404(id)
    return jsonify({
        "success": True,
        "supplier": {
            "id": supplier.id,
            "name": supplier.name,
            "phone": supplier.phone,
        }
    })

@bp.get("/partners")
@bp.get("/search_partners", endpoint="search_partners")
@login_required
@limiter.limit("60/minute")
def partners():
    return search_model(Partner, ["name", "phone_number", "identity_number"], label_attr="name")

@bp.get("/products")
@bp.get("/search_products", endpoint="search_products")
@login_required
@limiter.limit("60/minute")
def products():
    return search_model(
        Product,
        ["name", "sku", "part_number", "barcode"],
        label_attr="name",
        extra=lambda p: {"price": float(p.price or 0), "sku": p.sku}
    )

@bp.get("/products/<int:pid>/info")
@login_required
@limiter.limit("60/minute")
def product_info(pid: int):
    p = db.session.get(Product, pid)
    if not p:
        return jsonify({"error": "Not Found"}), 404
    wid = request.args.get("warehouse_id", type=int)
    available = None
    if wid:
        sl = StockLevel.query.filter_by(product_id=pid, warehouse_id=wid).first()
        available = (sl.quantity if sl else 0)
    return jsonify({
        "id": p.id, "name": p.name, "sku": p.sku,
        "price": float(p.price or 0),
        "available": (int(available) if available is not None else None),
    })

@bp.post("/categories", endpoint="create_category")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
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
    db.session.commit()
    return jsonify({"id": c.id, "text": c.name}), 201

@bp.get("/search_categories", endpoint="search_categories")
@login_required
@limiter.limit("60/minute")
def categories():
    return search_model(ProductCategory, ["name"], label_attr="name")

@bp.get("/warehouses")
@bp.get("/search_warehouses", endpoint="search_warehouses")
@login_required
@limiter.limit("60/minute")
def warehouses():
    return search_model(Warehouse, ["name"], label_attr="name")

@bp.get("/warehouses/<int:wid>/products")
@login_required
@limiter.limit("60/minute")
def products_by_warehouse(wid: int):
    rows = (
        db.session.query(Product, StockLevel.quantity)
        .join(StockLevel, StockLevel.product_id == Product.id)
        .filter(StockLevel.warehouse_id == wid, StockLevel.quantity > 0)
        .order_by(Product.name)
        .limit(_limit(default=100, max_=200))
        .all()
    )
    return jsonify([
        {
            "id": p.id, "text": p.name, "price": float(p.price or 0),
            "sku": p.sku, "available": int(qty or 0),
        } for p, qty in rows
    ])

@bp.get("/users")
@login_required
@limiter.limit("60/minute")
def users():
    return search_model(User, ["username", "email"], label_attr="username")

@bp.get("/employees")
@login_required
@limiter.limit("60/minute")
def employees():
    return search_model(Employee, ["name"], label_attr="name")

@bp.get("/equipment_types")
@bp.get("/search_equipment_types", endpoint="search_equipment_types")
@login_required
@limiter.limit("60/minute")
def equipment_types():
    return search_model(EquipmentType, ["name", "model_number", "chassis_number"], label_attr="name")


@bp.post("/equipment_types", endpoint="create_equipment_type")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
def create_equipment_type():
    data = request.get_json(silent=True) or request.form or {}
    name = (data.get("name") or "").strip()
    model_number = (data.get("model_number") or "").strip() or None
    chassis_number = (data.get("chassis_number") or "").strip() or None
    category = (data.get("category") or "").strip() or None
    notes = (data.get("notes") or "").strip() or None

    if not name:
        return jsonify({"error": "الاسم مطلوب"}), 400

    exists = EquipmentType.query.filter(func.lower(EquipmentType.name) == name.lower()).first()
    if exists:
        return jsonify({"id": exists.id, "text": exists.name, "dupe": True}), 200

    it = EquipmentType(
        name=name,
        model_number=model_number,
        chassis_number=chassis_number,
        category=category,
        notes=notes
    )

    try:
        db.session.add(it)
        db.session.commit()
        return jsonify({"id": it.id, "text": it.name}), 201
    except IntegrityError:
        db.session.rollback()
        exists = EquipmentType.query.filter(func.lower(EquipmentType.name) == name.lower()).first()
        if exists:
            return jsonify({"id": exists.id, "text": exists.name, "dupe": True}), 200
        return jsonify({"error": "اسم النوع موجود مسبقًا."}), 409
    except Exception:
        db.session.rollback()
        current_app.logger.exception("create_equipment_type failed")
        return jsonify({"error": "خطأ غير متوقع."}), 500


@bp.get("/invoices")
@login_required
@limiter.limit("60/minute")
def invoices():
    q = _q()
    qry = Invoice.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Invoice.invoice_number.ilike(like), Invoice.currency.ilike(like)))
    rows = qry.order_by(Invoice.id.desc()).limit(_limit()).all()
    return jsonify([
        {
            "id": i.id,
            "text": _number_of(i, "invoice_number", "INV"),
            "number": _number_of(i, "invoice_number", "INV"),
            "total": float(i.total_amount or 0),
            "status": getattr(i.status, "value", i.status),
        } for i in rows
    ])

@bp.get("/services")
@login_required
@limiter.limit("60/minute")
def services():
    q = _q()
    qry = ServiceRequest.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(
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
        ))
    rows = qry.order_by(ServiceRequest.id.desc()).limit(_limit()).all()
    return jsonify([
        {
            "id": s.id,
            "text": _number_of(s, "service_number", "SVC"),
            "number": _number_of(s, "service_number", "SVC"),
        } for s in rows
    ])

@bp.get("/sales")
@login_required
@limiter.limit("60/minute")
def sales():
    q = _q()
    qry = Sale.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Sale.sale_number.ilike(like),))
    rows = qry.order_by(Sale.id.desc()).limit(_limit()).all()
    return jsonify([
        {
            "id": s.id,
            "text": _number_of(s, "sale_number", "SAL"),
            "number": _number_of(s, "sale_number", "SAL"),
            "total": float(s.total_amount or 0),
            "status": getattr(s.status, "value", s.status),
            "payment_status": getattr(s.payment_status, "value", s.payment_status),
        } for s in rows
    ])

@bp.get("/shipments")
@login_required
@limiter.limit("60/minute")
def shipments():
    q = _q()
    qry = Shipment.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Shipment.shipment_number.ilike(like), Shipment.tracking_number.ilike(like)))
    rows = qry.order_by(Shipment.id.desc()).limit(_limit()).all()
    return jsonify([
        {
            "id": sh.id,
            "text": _number_of(sh, "shipment_number", "SHP"),
            "number": _number_of(sh, "shipment_number", "SHP"),
            "status": sh.status,
            "value": float((sh.value_before or 0) or 0),
        } for sh in rows
    ])

@bp.get("/transfers")
@login_required
@limiter.limit("60/minute")
def transfers():
    q = _q()
    qry = Transfer.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Transfer.reference.ilike(like),))
    rows = qry.order_by(Transfer.id.desc()).limit(_limit()).all()
    return jsonify([
        {
            "id": t.id,
            "text": _number_of(t, "reference", "TRF"),
            "number": _number_of(t, "reference", "TRF"),
            "product_id": t.product_id,
            "source_id": t.source_id,
            "destination_id": t.destination_id,
        } for t in rows
    ])


@bp.post("/suppliers")
@login_required
def create_supplier():
    payload = request.form or request.json or {}
    name = (payload.get("name") or "").strip()
    identity = (payload.get("identity_number") or "").strip() or None
    phone = (payload.get("phone") or "").strip() or None

    try:
        if identity:
            existing = Supplier.query.filter_by(identity_number=identity).first()
            if existing:
                return jsonify(success=True, id=existing.id, text=existing.name, name=existing.name), 200

        s = Supplier(
            name=name,
            identity_number=identity,
            phone=phone,
            is_local=True,
            currency="ILS",
        )
        db.session.add(s)
        db.session.commit()
        return jsonify(success=True, id=s.id, text=s.name, name=s.name), 201

    except IntegrityError:
        db.session.rollback()
        if identity:
            exists = Supplier.query.filter_by(identity_number=identity).first()
            if exists:
                return jsonify(success=True, id=exists.id, text=exists.name, name=exists.name), 200
        return jsonify(success=False, error="رقم المورّد التعريفي موجود مسبقًا."), 409

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("create_supplier failed")
        return jsonify(success=False, error="خطأ غير متوقع."), 500

@bp.get("/preorders")
@login_required
@limiter.limit("60/minute")
def preorders():
    q = _q()
    qry = PreOrder.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(PreOrder.reference.ilike(like),))
    rows = qry.order_by(PreOrder.id.desc()).limit(_limit()).all()
    return jsonify([
        {
            "id": po.id,
            "text": _number_of(po, "reference", "PO"),
            "number": _number_of(po, "reference", "PO"),
            "status": getattr(po.status, "value", po.status),
            "total": float((po.total_before_tax or 0) + 0),
        } for po in rows
    ])

@bp.get("/online_preorders")
@login_required
@limiter.limit("60/minute")
def online_preorders():
    q = _q()
    qry = OnlinePreOrder.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(OnlinePreOrder.order_number.ilike(like),))
    rows = qry.order_by(OnlinePreOrder.id.desc()).limit(_limit()).all()
    return jsonify([
        {
            "id": o.id,
            "text": _number_of(o, "order_number", "OPR"),
            "number": _number_of(o, "order_number", "OPR"),
            "status": o.status,
            "payment_status": o.payment_status,
            "total": float(o.total_amount or 0),
        } for o in rows
    ])

@bp.get("/expenses")
@login_required
@limiter.limit("60/minute")
def expenses():
    q = _q()
    qry = Expense.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Expense.tax_invoice_number.ilike(like), Expense.description.ilike(like)))
    rows = qry.order_by(Expense.id.desc()).limit(_limit()).all()
    return jsonify([
        {
            "id": e.id,
            "text": _number_of(e, "tax_invoice_number", "EXP"),
            "number": _number_of(e, "tax_invoice_number", "EXP"),
            "amount": float(e.amount or 0),
            "currency": e.currency,
        } for e in rows
    ])

@bp.get("/loan_settlements")
@login_required
@limiter.limit("60/minute")
def loan_settlements():
    q = _q()
    qry = SupplierLoanSettlement.query
    if q.isdigit():
        qry = qry.filter(SupplierLoanSettlement.id == int(q))
    rows = qry.order_by(SupplierLoanSettlement.id.desc()).limit(_limit()).all()
    return jsonify([
        {
            "id": x.id,
            "text": f"Settlement #{x.id}",
            "number": f"SET-{x.id}",
            "amount": float(x.settled_price or 0),
        } for x in rows
    ])

@bp.get("/payments")
@bp.get("/search_payments", endpoint="search_payments")
@login_required
@limiter.limit("60/minute")
def payments():
    q = _q()
    qry = Payment.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Payment.payment_number.ilike(like), Payment.receipt_number.ilike(like)))
    rows = qry.order_by(Payment.id.desc()).limit(_limit()).all()
    return jsonify([
        {
            "id": p.id,
            "text": _number_of(p, "payment_number", "PMT"),
            "number": _number_of(p, "payment_number", "PMT"),
            "amount": float(p.total_amount or 0),
            "status": getattr(p.status, "value", p.status),
            "method": getattr(p.method, "value", p.method),
        } for p in rows
    ])

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
