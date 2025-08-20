# File: routes/api.py
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required
from sqlalchemy import or_
from typing import Callable, Iterable, List, Dict, Any, Optional

from extensions import db, limiter
from models import (
    Customer, Supplier, Partner, Product, Warehouse, User, Employee,
    Invoice, ServiceRequest, SupplierLoanSettlement, ProductCategory, Payment,
    EquipmentType, StockLevel
)

bp = Blueprint("api", __name__, url_prefix="/api")


# -------------------- Helpers --------------------

def _q() -> str:
    """Read search query from ?q=..."""
    return (request.args.get("q") or "").strip()


def _limit(default: int = 20, max_: int = 50) -> int:
    """Safe limit parser with clamp."""
    try:
        n = int(request.args.get("limit", default))
    except Exception:
        n = default
    return max(1, min(n, max_))


def _as_options(rows: Iterable[Any], label_attr: str = "name", extra: Optional[Callable[[Any], Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """
    Convert ORM rows to [{id, text, ...extra}] for select2-like UIs.
    Tries common label fallbacks if label_attr is missing.
    """
    extra = extra or (lambda o: {})
    out: List[Dict[str, Any]] = []
    for o in rows:
        label = getattr(o, label_attr, None)
        if not label:
            # Common fallbacks
            for cand in ("name", "username", "invoice_number", "service_number", "sale_number", "cart_id", "order_number"):
                label = getattr(o, cand, None)
                if label:
                    break
        if not label:
            label = str(getattr(o, "id", ""))

        out.append({"id": o.id, "text": str(label), **extra(o)})
    return out


def _ilike_filters(model, fields: List[str], q: str):
    """Build OR ILIKE filters for given model fields."""
    like = f"%{q}%"
    return [getattr(model, f).ilike(like) for f in fields if hasattr(model, f)]


def search_model(model, fields: List[str], label_attr: str = "name", default_order_attr: Optional[str] = None, limit_default: int = 20, limit_max: int = 50, extra: Optional[Callable[[Any], Dict[str, Any]]] = None):
    """
    Generic search endpoint builder.
    - model: SQLAlchemy model
    - fields: list of field names to ILIKE
    - label_attr: used for display text
    - default_order_attr: if None, uses label_attr
    """
    q = _q()
    qry = model.query
    if q:
        qry = qry.filter(or_(*_ilike_filters(model, fields, q)))
    order_attr = default_order_attr or label_attr
    qry = qry.order_by(getattr(model, order_attr))
    rows = qry.limit(_limit(default=limit_default, max_=limit_max)).all()
    return jsonify(_as_options(rows, label_attr, extra=extra))


# -------------------- Customers --------------------

@bp.get("/customers")
@bp.get("/search_customers", endpoint="search_customers")
@login_required
@limiter.limit("60/minute")
def customers():
    return search_model(Customer, ["name", "phone", "email"], label_attr="name")


# -------------------- Suppliers --------------------

@bp.get("/suppliers")
@bp.get("/search_suppliers", endpoint="search_suppliers")
@login_required
@limiter.limit("60/minute")
def suppliers():
    # Supplier has identity_number & phone
    return search_model(Supplier, ["name", "phone", "identity_number"], label_attr="name")


# -------------------- Partners --------------------

@bp.get("/partners")
@bp.get("/search_partners", endpoint="search_partners")
@login_required
@limiter.limit("60/minute")
def partners():
    # Partner has phone_number & identity_number
    return search_model(Partner, ["name", "phone_number", "identity_number"], label_attr="name")


# -------------------- Products --------------------

@bp.get("/products")
@bp.get("/search_products", endpoint="search_products")
@login_required
@limiter.limit("60/minute")
def products():
    # Keep extra info (price, sku) in options
    return search_model(
        Product,
        ["name", "sku", "part_number", "barcode"],
        label_attr="name",
        extra=lambda p: {"price": float(p.price or 0), "sku": p.sku}
    )


@bp.get("/products/<int:pid>/info", endpoint="product_info")
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
        "id": p.id,
        "name": p.name,
        "sku": p.sku,
        "price": float(p.price or 0),
        "available": (int(available) if available is not None else None),
    })


# -------------------- Categories --------------------

@bp.get("/search_categories", endpoint="categories")
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
            "id": p.id,
            "text": p.name,
            "price": float(p.price or 0),
            "sku": p.sku,
            "available": int(qty or 0),
        } for p, qty in rows
    ])


# -------------------- Users --------------------

@bp.get("/users")
@login_required
@limiter.limit("60/minute")
def users():
    return search_model(User, ["username", "email"], label_attr="username")


# -------------------- Employees --------------------

@bp.get("/employees")
@login_required
@limiter.limit("60/minute")
def employees():
    return search_model(Employee, ["name"], label_attr="name")


# -------------------- Equipment Types --------------------

@bp.get("/equipment_types")
@bp.get("/search_equipment_types", endpoint="search_equipment_types")
@login_required
@limiter.limit("60/minute")
def equipment_types():
    return search_model(EquipmentType, ["name", "model_number", "chassis_number"], label_attr="name")


# -------------------- Invoices --------------------

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
    return jsonify(
        [
            {
                "id": i.id,
                "text": i.invoice_number or f"INV-{i.id}",
                "number": i.invoice_number or f"INV-{i.id}",
                "total": float(i.total_amount or 0),
                "status": getattr(i.status, "value", i.status),
            }
            for i in rows
        ]
    )


# -------------------- Services --------------------

@bp.get("/services")
@login_required
@limiter.limit("60/minute")
def services():
    """
    Search services by service_number or textual fields.
    (Removed non-existent ServiceRequest.vehicle_vrn)
    """
    q = _q()
    qry = ServiceRequest.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            or_(
                ServiceRequest.service_number.ilike(like),
                ServiceRequest.problem_description.ilike(like),
                ServiceRequest.diagnosis.ilike(like),
                ServiceRequest.resolution.ilike(like),
                ServiceRequest.notes.ilike(like),
            )
        )
    rows = qry.order_by(ServiceRequest.id.desc()).limit(_limit()).all()
    return jsonify([{"id": s.id, "text": s.service_number or f"SVC-{s.id}"} for s in rows])


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
            "amount": float(x.settled_price or 0)
        }
        for x in rows
    ])


# -------------------- Payments --------------------

@bp.get("/search_payments")
@login_required
@limiter.limit("60/minute")
def search_payments():
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
                "text": p.payment_number or f"PMT-{p.id}",
                "amount": float(p.total_amount or 0),
                "status": getattr(p.status, "value", p.status),
                "method": getattr(p.method, "value", p.method),
            }
            for p in rows
        ]
    )


# -------------------- Error Handlers --------------------

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
