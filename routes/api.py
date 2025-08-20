# File: routes/api.py
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required
from sqlalchemy import or_
from typing import Callable, Iterable, List, Dict, Any, Optional

from extensions import db, limiter
from models import (
    Customer, Supplier, Partner, Product, Warehouse, User, Employee,
    Invoice, ServiceRequest, SupplierLoanSettlement, ProductCategory, Payment,
    EquipmentType, StockLevel, Sale, Shipment, Transfer, PreOrder,
    OnlinePreOrder, Expense
)

bp = Blueprint("api", __name__, url_prefix="/api")

# -------------------- Helpers --------------------

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

# -------------------- Customers / Suppliers / Partners --------------------

@bp.get("/customers")
@bp.get("/search_customers", endpoint="search_customers")
@login_required
@limiter.limit("60/minute")
def customers():
    return search_model(Customer, ["name", "phone", "email"], label_attr="name")

@bp.get("/suppliers")
@bp.get("/search_suppliers", endpoint="search_suppliers")
@login_required
@limiter.limit("60/minute")
def suppliers():
    return search_model(Supplier, ["name", "phone", "identity_number"], label_attr="name")

@bp.get("/partners")
@bp.get("/search_partners", endpoint="search_partners")
@login_required
@limiter.limit("60/minute")
def partners():
    return search_model(Partner, ["name", "phone_number", "identity_number"], label_attr="name")

# -------------------- Products & Categories --------------------

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

@bp.get("/search_categories")
@login_required
@limiter.limit("60/minute")
def categories():
    return search_model(ProductCategory, ["name"], label_attr="name")

# -------------------- Warehouses --------------------

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

# -------------------- Users / Employees / Equipment --------------------

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

# -------------------- Invoices (returns `number`) --------------------

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

# -------------------- Services (returns `number`) --------------------

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

# -------------------- Sales (returns `number`) --------------------

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

# -------------------- Shipments (returns `number`) --------------------

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

# -------------------- Transfers (returns `number`) --------------------

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

# -------------------- PreOrders (returns `number`) --------------------

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

# -------------------- Online PreOrders (returns `number`) --------------------

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

# -------------------- Expenses (returns `number`) --------------------

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

# -------------------- Supplier Loan Settlements --------------------

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

# -------------------- Payments (returns `number`) --------------------

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

# -------------------- Errors --------------------

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
