from flask import Blueprint, request, jsonify, current_app, Response
from flask_login import login_required, current_user
from sqlalchemy import or_, func
from typing import Callable, Iterable, List, Dict, Any, Optional
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from extensions import db, limiter, csrf
from models import (
    Customer, Supplier, Partner, Product, Warehouse, User, Employee,
    Invoice, ServiceRequest, SupplierLoanSettlement, ProductCategory, Payment,
    EquipmentType, StockLevel, Sale, Shipment, Transfer, PreOrder,
    OnlinePreOrder, Expense, Permission
)
from utils import permission_required, super_only, _get_user_permissions
from barcodes import normalize_barcode, validate_barcode

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
    for cand in ("invoice_number", "service_number", "sale_number", "shipment_number", "order_number", "payment_number", "receipt_number", "reference", "cart_id", "tax_invoice_number"):
        v = getattr(o, cand, None)
        if v:
            return str(v)
    if fallback_prefix:
        return f"{fallback_prefix}-{getattr(o, 'id', '')}"
    return str(getattr(o, "id", ""))

def _as_options(rows: Iterable[Any], label_attr: str = "name", extra: Optional[Callable[[Any], Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    extra = extra or (lambda o: {})
    out: List[Dict[str, Any]] = []
    for o in rows:
        label = getattr(o, label_attr, None)
        if not label:
            for cand in ("name", "username", "invoice_number", "service_number", "sale_number", "shipment_number", "order_number", "cart_id", "payment_number", "reference"):
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

def search_model(model, fields: List[str], label_attr: str = "name", default_order_attr: Optional[str] = None, limit_default: int = 20, limit_max: int = 50, extra: Optional[Callable[[Any], Dict[str, Any]]] = None):
    q = _q()
    qry = model.query
    if q:
        qry = qry.filter(or_(*_ilike_filters(model, fields, q)))
    order_attr = default_order_attr or label_attr
    order_col = getattr(model, order_attr, getattr(model, "id"))
    rows = qry.order_by(order_col).limit(_limit(default=limit_default, max_=limit_max)).all()
    return jsonify(_as_options(rows, label_attr, extra=extra))

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
    role_name = (getattr(getattr(current_user, "role", None), "name", None))
    perms = sorted(list(_get_user_permissions(current_user) or []))
    return jsonify({"id": current_user.id, "username": getattr(current_user, "username", None), "email": getattr(current_user, "email", None), "role": role_name, "permissions": perms})

@bp.get("/permissions.json")
@super_only
def permissions_json():
    rows = Permission.query.order_by(Permission.name.asc()).all()
    def _row(p):
        return {"id": p.id, "code": getattr(p, "code", None) or getattr(p, "name", None), "name": getattr(p, "name", None), "ar_name": getattr(p, "ar_name", None), "category": getattr(p, "category", None), "aliases": getattr(p, "aliases", None)}
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
        w.writerow([p.id, getattr(p, "code", None) or getattr(p, "name", None), getattr(p, "name", None), getattr(p, "ar_name", None), getattr(p, "category", None), getattr(p, "aliases", None)])
    return Response(buf.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=permissions.csv"})

@bp.get("/customers")
@bp.get("/search_customers", endpoint="search_customers")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_customers", "manage_customurers", "add_customer")
def customers():
    return search_model(Customer, ["name", "phone", "email"], label_attr="name")

@bp.post("/customers")
@login_required
@limiter.limit("30/minute")
@permission_required("manage_customers", "manage_customurers", "add_customer")
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
        return jsonify(success=False, error="الاسم والبريد مطلوبان"), 400
    try:
        c = Customer(name=name, email=email, phone=phone, whatsapp=whatsapp, address=address, notes=notes, discount_rate=discount_rate, credit_limit=credit_limit, is_online=is_online, is_active=is_active)
        pwd = (data.get("password") or "").strip()
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
@permission_required("manage_vendors", "add_supplier")
def suppliers():
    return search_model(Supplier, ["name", "phone", "identity_number"], label_attr="name", default_order_attr="name")

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
        return jsonify(success=False, error="الاسم مطلوب"), 400
    try:
        supplier = Supplier(name=name, phone=phone, identity_number=identity_number, address=address, notes=notes)
        db.session.add(supplier)
        db.session.commit()
        return jsonify(success=True, id=supplier.id, name=supplier.name), 201
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(success=False, error="فشل حفظ المورد"), 500

@bp.get("/suppliers/<int:id>")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_vendors", "add_supplier")
def get_supplier(id):
    supplier = Supplier.query.get_or_404(id)
    return jsonify({"success": True, "supplier": {"id": supplier.id, "name": supplier.name, "phone": supplier.phone}})

@bp.get("/partners")
@bp.get("/search_partners", endpoint="search_partners")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_vendors", "add_partner")
def partners():
    return search_model(Partner, ["name", "phone_number", "identity_number"], label_attr="name")

@bp.get("/products")
@bp.get("/search_products", endpoint="search_products")
@login_required
@limiter.limit("60/minute")
@permission_required("view_parts", "view_inventory", "manage_inventory")
def products():
    return search_model(Product, ["name", "sku", "part_number", "barcode"], label_attr="name", extra=lambda p: {"price": float(p.price or 0), "sku": p.sku})

@bp.get("/barcode/validate", endpoint="barcode_validate")
@login_required
@limiter.limit("120/minute")
def barcode_validate():
    code = (request.args.get("code") or "").strip()
    r = validate_barcode(code)
    exists = False
    if r.get("normalized"):
        exists = db.session.query(Product.id).filter_by(barcode=r["normalized"]).first() is not None
    return jsonify({"input": code, "normalized": r.get("normalized"), "valid": bool(r.get("valid")), "suggested": r.get("suggested"), "exists": bool(exists)})

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
    return jsonify({"id": p.id, "name": p.name, "sku": p.sku, "part_number": p.part_number, "barcode": p.barcode, "price": float(p.price or 0)})

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
        available = (sl.quantity if sl else 0)
    return jsonify({"id": p.id, "name": p.name, "sku": p.sku, "price": float(p.price or 0), "available": (int(available) if available is not None else None)})

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
    db.session.commit()
    return jsonify({"id": c.id, "text": c.name}), 201

@bp.get("/search_categories", endpoint="search_categories")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_inventory", "view_inventory")
def categories():
    return search_model(ProductCategory, ["name"], label_attr="name")

@bp.get("/warehouses")
@bp.get("/search_warehouses", endpoint="search_warehouses")
@login_required
@limiter.limit("60/minute")
@permission_required("view_warehouses", "manage_warehouses", "view_inventory", "manage_inventory")
def warehouses():
    return search_model(Warehouse, ["name"], label_attr="name")

@bp.get("/warehouses/<int:wid>/products")
@login_required
@limiter.limit("60/minute")
@permission_required("view_inventory", "view_warehouses", "manage_inventory")
def products_by_warehouse(wid: int):
    rows = (
        db.session.query(Product, StockLevel.quantity)
        .join(StockLevel, StockLevel.product_id == Product.id)
        .filter(StockLevel.warehouse_id == wid, StockLevel.quantity > 0)
        .order_by(Product.name)
        .limit(_limit(default=100, max_=200))
        .all()
    )
    return jsonify([{"id": p.id, "text": p.name, "price": float(p.price or 0), "sku": p.sku, "available": int(qty or 0)} for p, qty in rows])

@bp.get("/users")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_users")
def users():
    return search_model(User, ["username", "email"], label_attr="username")

@bp.get("/employees")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_service")
def employees():
    return search_model(Employee, ["name"], label_attr="name")

@bp.get("/equipment_types")
@bp.get("/search_equipment_types", endpoint="search_equipment_types")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_service")
def equipment_types():
    return search_model(EquipmentType, ["name", "model_number", "chassis_number"], label_attr="name")

@bp.post("/equipment_types", endpoint="create_equipment_type")
@login_required
@csrf.exempt
@limiter.limit("30/minute")
@permission_required("manage_service")
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
    it = EquipmentType(name=name, model_number=model_number, chassis_number=chassis_number, category=category, notes=notes)
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
@permission_required("manage_sales", "view_reports")
def invoices():
    q = _q()
    qry = Invoice.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Invoice.invoice_number.ilike(like), Invoice.currency.ilike(like)))
    rows = qry.order_by(Invoice.id.desc()).limit(_limit()).all()
    return jsonify([{"id": i.id, "text": _number_of(i, "invoice_number", "INV"), "number": _number_of(i, "invoice_number", "INV"), "total": float(i.total_amount or 0), "status": getattr(i.status, "value", i.status)} for i in rows])

@bp.get("/services")
@login_required
@limiter.limit("60/minute")
@permission_required("manage_service")
def services():
    q = _q()
    qry = ServiceRequest.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(ServiceRequest.service_number.ilike(like), ServiceRequest.vehicle_vrn.ilike(like), ServiceRequest.vehicle_model.ilike(like), ServiceRequest.chassis_number.ilike(like), ServiceRequest.description.ilike(like), ServiceRequest.engineer_notes.ilike(like), ServiceRequest.problem_description.ilike(like), ServiceRequest.diagnosis.ilike(like), ServiceRequest.resolution.ilike(like), ServiceRequest.notes.ilike(like)))
    rows = qry.order_by(ServiceRequest.id.desc()).limit(_limit()).all()
    return jsonify([{"id": s.id, "text": _number_of(s, "service_number", "SVC"), "number": _number_of(s, "service_number", "SVC")} for s in rows])

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
    return jsonify([{"id": s.id, "text": _number_of(s, "sale_number", "SAL"), "number": _number_of(s, "sale_number", "SAL"), "total": float(s.total_amount or 0), "status": getattr(s.status, "value", s.status), "payment_status": getattr(s.payment_status, "value", s.payment_status)} for s in rows])

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
    return jsonify([{"id": sh.id, "text": _number_of(sh, "shipment_number", "SHP"), "number": _number_of(sh, "shipment_number", "SHP"), "status": sh.status, "value": float((sh.value_before or 0) or 0)} for sh in rows])

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
    return jsonify([{"id": t.id, "text": _number_of(t, "reference", "TRF"), "number": _number_of(t, "reference", "TRF"), "product_id": t.product_id, "source_id": t.source_id, "destination_id": t.destination_id} for t in rows])

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
    return jsonify([{"id": po.id, "text": _number_of(po, "reference", "PO"), "number": _number_of(po, "reference", "PO"), "status": getattr(po.status, "value", po.status), "total": float(po.total_before_tax or 0)} for po in rows])

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
    return jsonify([{"id": o.id, "text": _number_of(o, "order_number", "OPR"), "number": _number_of(o, "order_number", "OPR"), "status": o.status, "payment_status": o.payment_status, "total": float(o.total_amount or 0)} for o in rows])

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
    return jsonify([{"id": e.id, "text": _number_of(e, "tax_invoice_number", "EXP"), "number": _number_of(e, "tax_invoice_number", "EXP"), "amount": float(e.amount or 0), "currency": e.currency} for e in rows])

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
    return jsonify([{"id": x.id, "text": f"Settlement #{x.id}", "number": f"SET-{x.id}", "amount": float(x.settled_price or 0)} for x in rows])

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
    return jsonify([{"id": p.id, "text": _number_of(p, "payment_number", "PMT"), "number": _number_of(p, "payment_number", "PMT"), "amount": float(p.total_amount or 0), "status": getattr(p.status, "value", p.status), "method": getattr(p.method, "value", p.method)} for p in rows])

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
