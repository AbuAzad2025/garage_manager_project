# File: routes/api.py
# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required
from sqlalchemy import or_

from extensions import db, limiter
from models import (
    Customer, Supplier, Partner, Product, Warehouse, User, Employee,
    Invoice, ServiceRequest, SupplierLoanSettlement, ProductCategory, Payment,
    EquipmentType
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

def _as_options(rows, label_attr: str = "name", extra=None):
    extra = extra or (lambda o: {})
    out = []
    for o in rows:
        label = getattr(o, label_attr, None)
        if not label:
            for cand in ("name","username","invoice_number","service_number","sale_number","cart_id","order_number"):
                label = getattr(o, cand, None)
                if label:
                    break
        if not label:
            label = str(getattr(o, "id", ""))
        out.append({"id": o.id, "text": str(label), **extra(o)})
    return out

@bp.get("/customers")
@bp.get("/search_customers", endpoint="search_customers")
@login_required
@limiter.limit("60/minute")
def customers():
    q = _q()
    qry = Customer.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Customer.name.ilike(like), Customer.phone.ilike(like), Customer.email.ilike(like)))
    rows = qry.order_by(Customer.name).limit(_limit()).all()
    return jsonify(_as_options(rows, "name"))

@bp.get("/suppliers")
@bp.get("/search_suppliers")
@login_required
@limiter.limit("60/minute")
def suppliers():
    q = _q()
    qry = Supplier.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Supplier.name.ilike(like), Supplier.phone.ilike(like), Supplier.identity_number.ilike(like)))
    rows = qry.order_by(Supplier.name).limit(_limit()).all()
    return jsonify(_as_options(rows, "name"))

@bp.get("/partners")
@bp.get("/search_partners")
@login_required
@limiter.limit("60/minute")
def partners():
    q = _q()
    qry = Partner.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Partner.name.ilike(like), Partner.phone_number.ilike(like), Partner.identity_number.ilike(like)))
    rows = qry.order_by(Partner.name).limit(_limit()).all()
    return jsonify(_as_options(rows, "name"))

@bp.get("/products")
@bp.get("/search_products", endpoint="search_products")
@login_required
@limiter.limit("60/minute")
def products():
    q = _q()
    qry = Product.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.part_number.ilike(like),
                Product.barcode.ilike(like),
            )
        )
    rows = qry.order_by(Product.name).limit(_limit()).all()
    return jsonify(_as_options(rows, "name", extra=lambda p: {"price": float(p.price or 0), "sku": p.sku}))

@bp.get("/search_categories")
@login_required
@limiter.limit("60/minute")
def categories():
    q = _q()
    qry = ProductCategory.query
    if q:
        qry = qry.filter(ProductCategory.name.ilike(f"%{q}%"))
    rows = qry.order_by(ProductCategory.name).limit(_limit()).all()
    return jsonify(_as_options(rows, "name"))

@bp.get("/warehouses")
@bp.get("/search_warehouses", endpoint="search_warehouses")
@login_required
@limiter.limit("60/minute")
def warehouses():
    q = _q()
    qry = Warehouse.query
    if q:
        qry = qry.filter(Warehouse.name.ilike(f"%{q}%"))
    rows = qry.order_by(Warehouse.name).limit(_limit()).all()
    return jsonify(_as_options(rows, "name"))

@bp.get("/users")
@login_required
@limiter.limit("60/minute")
def users():
    q = _q()
    qry = User.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(User.username.ilike(like), User.email.ilike(like)))
    rows = qry.order_by(User.username).limit(_limit()).all()
    return jsonify(_as_options(rows, "username"))

@bp.get("/employees")
@login_required
@limiter.limit("60/minute")
def employees():
    q = _q()
    qry = Employee.query
    if q:
        qry = qry.filter(Employee.name.ilike(f"%{q}%"))
    rows = qry.order_by(Employee.name).limit(_limit()).all()
    return jsonify(_as_options(rows, "name"))

@bp.get("/equipment_types")
@bp.get("/search_equipment_types")
@login_required
@limiter.limit("60/minute")
def equipment_types():
    q = _q()
    qry = EquipmentType.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            or_(
                EquipmentType.name.ilike(like),
                EquipmentType.model_number.ilike(like),
                EquipmentType.chassis_number.ilike(like),
            )
        )
    rows = qry.order_by(EquipmentType.name).limit(_limit()).all()
    return jsonify(_as_options(rows, "name"))

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

@bp.get("/services")
@login_required
@limiter.limit("60/minute")
def services():
    q = _q()
    qry = ServiceRequest.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(ServiceRequest.service_number.ilike(like), ServiceRequest.vehicle_vrn.ilike(like)))
    rows = qry.order_by(ServiceRequest.id.desc()).limit(_limit()).all()
    return jsonify([{"id": s.id, "text": s.service_number or f"SVC-{s.id}"} for s in rows])

@bp.get("/loan_settlements")
@login_required
@limiter.limit("60/minute")
def loan_settlements():
    q = _q()
    qry = SupplierLoanSettlement.query
    if q.isdigit():
        qry = qry.filter(SupplierLoanSettlement.id == int(q))
    rows = qry.order_by(SupplierLoanSettlement.id.desc()).limit(_limit()).all()
    return jsonify([{"id": x.id, "text": f"Settlement #{x.id}", "amount": float(x.settled_price or 0)} for x in rows])

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
