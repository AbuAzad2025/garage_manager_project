# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, List, Tuple
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for, abort, current_app
from flask_login import current_user, login_required
from sqlalchemy import func, or_, desc, extract, case, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from extensions import db
from models import Sale, SaleLine, Invoice, Customer, Product, AuditLog, Warehouse, User, Payment, StockLevel
from forms import SaleForm
from utils import permission_required
from decimal import Decimal, ROUND_HALF_UP

sales_bp = Blueprint("sales_bp", __name__, url_prefix="/sales", template_folder="templates/sales")

TWOPLACES = Decimal("0.01")

def D(x):
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))

def line_total_decimal(qty, unit_price, discount_rate):
    q = D(qty)
    p = D(unit_price)
    dr = D(discount_rate or 0)
    one = Decimal("1")
    hundred = Decimal("100")
    total = q * p * (one - dr / hundred)
    return total.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

def money_fmt(value):
    v = value if isinstance(value, Decimal) else D(value or 0)
    return f"{v:,.2f}"

STATUS_MAP = {
    "DRAFT": ("مسودة", "bg-warning text-dark"),
    "CONFIRMED": ("مؤكدة", "bg-primary"),
    "CANCELLED": ("ملغاة", "bg-secondary"),
    "REFUNDED": ("مرتجعة", "bg-info"),
}
PAYMENT_STATUS_MAP = {
    "PENDING": ("معلّق", "bg-warning"),
    "COMPLETED": ("مكتمل", "bg-success"),
    "FAILED": ("فشل", "bg-danger"),
    "REFUNDED": ("مرتجع", "bg-info"),
}
PAYMENT_METHOD_MAP = {"cash": "نقدي", "cheque": "شيك", "card": "بطاقة", "bank": "تحويل بنكي", "online": "دفع إلكتروني"}

def _get_or_404(model, ident, options: Optional[Iterable[Any]] = None):
    q = db.session.query(model)
    if options:
        for opt in options:
            q = q.options(opt)
        obj = q.filter_by(id=ident).first()
    else:
        obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj

def _format_sale(s: Sale) -> None:
    s.customer_name = s.customer.name if s.customer else "-"
    s.seller_name = s.seller.username if s.seller else "-"
    s.date = s.sale_date
    s.date_iso = s.sale_date.strftime("%Y-%m-%d") if s.sale_date else "-"
    s.total_fmt = f"{float(getattr(s, 'total_amount', 0) or 0):,.2f}"
    s.paid_fmt = f"{float(getattr(s, 'total_paid', 0) or 0):,.2f}"
    s.balance_fmt = f"{float(getattr(s, 'balance_due', 0) or 0):,.2f}"
    lbl, cls = STATUS_MAP.get(s.status, (s.status, ""))
    s.status_label, s.status_class = lbl, cls

def sale_to_dict(s: Sale) -> Dict[str, Any]:
    return {
        "id": s.id,
        "sale_number": s.sale_number,
        "customer_id": s.customer_id,
        "seller_id": s.seller_id,
        "sale_date": s.sale_date.strftime("%Y-%m-%d") if s.sale_date else None,
        "status": s.status,
        "currency": s.currency,
        "tax_rate": float(s.tax_rate or 0),
        "shipping_cost": float(getattr(s, "shipping_cost", 0) or 0),
        "discount_total": float(getattr(s, "discount_total", 0) or 0),
        "notes": s.notes,
        "lines": [
            {
                "product_id": ln.product_id,
                "warehouse_id": ln.warehouse_id,
                "quantity": ln.quantity,
                "unit_price": float(ln.unit_price or 0),
                "discount_rate": float(ln.discount_rate or 0),
                "tax_rate": float(ln.tax_rate or 0),
            }
            for ln in s.lines
        ],
    }

def _log(s: Sale, action: str, old: Optional[dict] = None, new: Optional[dict] = None) -> None:
    log = AuditLog(
        model_name="Sale",
        record_id=s.id,
        action=action,
        old_data=json.dumps(old, ensure_ascii=False) if old else None,
        new_data=json.dumps(new, ensure_ascii=False) if new else None,
        user_id=current_user.id if current_user.is_authenticated else None,
    )
    now = datetime.utcnow()
    for fld in ("timestamp", "created_at", "logged_at"):
        if hasattr(AuditLog, fld):
            setattr(log, fld, now)
            break
    db.session.add(log)
    db.session.flush()

def _available_expr():
    return (StockLevel.quantity - func.coalesce(StockLevel.reserved_quantity, 0))

def _available_qty(product_id: int, warehouse_id: int) -> int:
    row = (
        db.session.query(_available_expr().label("avail"))
        .filter(StockLevel.product_id == product_id, StockLevel.warehouse_id == warehouse_id)
        .first()
    )
    return int(row.avail or 0) if row else 0

def _auto_pick_warehouse(product_id: int, required_qty: int, preferred_wid: Optional[int] = None) -> Optional[int]:
    if preferred_wid:
        if _available_qty(product_id, preferred_wid) >= required_qty:
            return preferred_wid
    order_expr = case(
        (Warehouse.warehouse_type == "MAIN", 0),
        (Warehouse.warehouse_type == "INVENTORY", 1),
        (Warehouse.warehouse_type == "PARTNER", 2),
        (Warehouse.warehouse_type == "EXCHANGE", 3),
        else_=9,
    )
    row = (
        db.session.query(StockLevel.warehouse_id, Warehouse.warehouse_type, _available_expr().label("avail"))
        .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
        .filter(StockLevel.product_id == product_id)
        .filter(_available_expr() >= required_qty)
        .order_by(order_expr.asc(), Warehouse.id.asc())
        .first()
    )
    return int(row.warehouse_id) if row else None

def _lock_stock_rows(pairs: List[Tuple[int, int]]) -> None:
    if not pairs:
        return
    conds = [and_(StockLevel.product_id == pid, StockLevel.warehouse_id == wid) for (pid, wid) in pairs]
    db.session.query(StockLevel).filter(or_(*conds)).with_for_update(nowait=False).all()

def _collect_requirements_from_lines(lines: Iterable[SaleLine]) -> Dict[Tuple[int, int], int]:
    req: Dict[Tuple[int, int], int] = {}
    for ln in lines:
        pid = int(ln.product_id or 0)
        wid = int(ln.warehouse_id or 0)
        qty = int(ln.quantity or 0)
        if pid and wid and qty > 0:
            key = (pid, wid)
            req[key] = req.get(key, 0) + qty
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
            raise ValueError(f"الكمية غير متوفرة للمنتج ID={pid} في المخزن {wid}.")
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
        current_reserved = int(rec.reserved_quantity or 0)
        new_reserved = max(0, current_reserved - qty)
        rec.reserved_quantity = new_reserved
        db.session.flush()

def _resolve_lines_from_form(form: SaleForm, require_stock: bool) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    lines_payload: List[Dict[str, Any]] = []
    for ent in form.lines.entries:
        ln = ent.form
        pid = int(ln.product_id.data) if ln.product_id.data else 0
        wid = int(ln.warehouse_id.data) if ln.warehouse_id.data else 0
        qty = int(ln.quantity.data or 0)
        if not (pid and qty > 0):
            continue
        chosen_wid = wid or _auto_pick_warehouse(pid, qty, preferred_wid=None)
        if wid and _available_qty(pid, wid) < qty:
            auto_wid = _auto_pick_warehouse(pid, qty, preferred_wid=None)
            chosen_wid = auto_wid or wid
        if require_stock:
            if not chosen_wid:
                return [], f"لا يوجد مخزن مناسب متاح للمنتج ID={pid} بالكمية المطلوبة."
            if _available_qty(pid, chosen_wid) < qty:
                return [], f"الكمية غير متوفرة للمنتج ID={pid} في المخازن بالكمية: {qty}."
        line_dict = dict(
            product_id=pid,
            warehouse_id=int(chosen_wid) if chosen_wid else (wid or None),
            quantity=qty,
            unit_price=float(ln.unit_price.data or 0),
            discount_rate=float(ln.discount_rate.data or 0),
            tax_rate=float(ln.tax_rate.data or 0),
            note=(ln.note.data or "").strip() or None,
        )
        lines_payload.append(line_dict)
    if require_stock and not lines_payload:
        return [], "لا توجد أسطر صالحة للحفظ."
    return lines_payload, None

def _attach_lines(sale: Sale, lines_payload: List[Dict[str, Any]]) -> None:
    if getattr(sale, "id", None):
        SaleLine.query.filter_by(sale_id=sale.id).delete(synchronize_session=False)
        db.session.flush()
    for d in lines_payload:
        db.session.add(SaleLine(
            sale_id=sale.id,
            product_id=d["product_id"],
            warehouse_id=d.get("warehouse_id"),
            quantity=d["quantity"],
            unit_price=d["unit_price"],
            discount_rate=d.get("discount_rate", 0),
            tax_rate=d.get("tax_rate", 0),
            note=d.get("note"),
        ))
    db.session.flush()

def _safe_generate_number_after_flush(sale: Sale) -> None:
    if not sale.sale_number:
        sale.sale_number = f"INV-{datetime.utcnow():%Y%m%d}-{sale.id:04d}"
        db.session.flush()

@sales_bp.route("/dashboard")
@login_required
@permission_required("manage_sales")
def dashboard():
    total_sales = db.session.query(func.count(Sale.id)).scalar() or 0
    total_revenue = db.session.query(func.coalesce(func.sum(Sale.total_amount), 0)).scalar() or 0
    pending_sales = db.session.query(func.count(Sale.id)).filter(Sale.status == "DRAFT").scalar() or 0
    top_customers = (
        db.session.query(Customer.name, func.sum(Sale.total_amount).label("spent"))
        .join(Sale, Sale.customer_id == Customer.id)
        .group_by(Customer.id)
        .order_by(desc("spent"))
        .limit(5).all()
    )
    top_products = (
        db.session.query(
            Product.name,
            func.sum(SaleLine.quantity).label("sold"),
            func.coalesce(func.sum(
                SaleLine.quantity * SaleLine.unit_price *
                (1 - func.coalesce(SaleLine.discount_rate, 0) / 100.0)
            ), 0).label("revenue")
        )
        .join(SaleLine, SaleLine.product_id == Product.id)
        .group_by(Product.id)
        .order_by(desc("sold"))
        .limit(5).all()
    )
    y = extract("year", Sale.sale_date); m = extract("month", Sale.sale_date)
    monthly = (
        db.session.query(y.label("y"), m.label("m"), func.count(Sale.id), func.sum(Sale.total_amount))
        .group_by(y, m).order_by(y, m).all()
    )
    months, counts, revenue = [], [], []
    for yy, mm, cnt, total in monthly:
        months.append(f"{int(mm)}/{int(yy)}")
        counts.append(int(cnt))
        revenue.append(float(total or 0))
    return render_template("sales/dashboard.html",
                           total_sales=total_sales, total_revenue=total_revenue, pending_sales=pending_sales,
                           top_customers=top_customers, top_products=top_products,
                           months=months, sales_count=counts, revenue=revenue)

@sales_bp.route("/", endpoint="list_sales")
@sales_bp.route("/", endpoint="index")
@login_required
@permission_required("manage_sales")
def list_sales():
    f = request.args
    subtotals = (
        db.session.query(
            Sale.id.label("sale_id"),
            func.coalesce(
                func.sum(
                    SaleLine.quantity * SaleLine.unit_price *
                    (1 - func.coalesce(SaleLine.discount_rate, 0) / 100.0) *
                    (1 + func.coalesce(SaleLine.tax_rate, 0) / 100.0)
                ),
                0,
            ).label("calc_total"),
        )
        .outerjoin(SaleLine, SaleLine.sale_id == Sale.id)
        .group_by(Sale.id).subquery()
    )
    q = (Sale.query
         .options(joinedload(Sale.customer), joinedload(Sale.seller))
         .outerjoin(subtotals, subtotals.c.sale_id == Sale.id)
         .outerjoin(Customer))
    st = f.get("status", "all").upper()
    if st and st != "ALL":
        q = q.filter(Sale.status == st)
    cust = (f.get("customer") or "").strip()
    if cust:
        q = q.filter(or_(Customer.name.ilike(f"%{cust}%"), Customer.phone.ilike(f"%{cust}%")))
    df = (f.get("date_from") or "").strip()
    dt = (f.get("date_to") or "").strip()
    try:
        if df:
            q = q.filter(Sale.sale_date >= datetime.fromisoformat(df))
        if dt:
            q = q.filter(Sale.sale_date <= datetime.fromisoformat(dt))
    except ValueError:
        pass
    inv = (f.get("invoice_no") or "").strip()
    if inv:
        q = q.filter(Sale.sale_number.ilike(f"%{inv}%"))
    sort = f.get("sort", "date")
    order = f.get("order", "desc")
    if sort == "total":
        fld = subtotals.c.calc_total
    elif sort == "customer":
        fld = Customer.name
    else:
        fld = Sale.sale_date
    q = q.order_by(fld.asc() if order == "asc" else fld.desc())
    page = int(f.get("page", 1))
    pag = q.paginate(page=page, per_page=20, error_out=False)
    sales = pag.items
    for s in sales:
        _format_sale(s)
    return render_template("sales/list.html", sales=sales, pagination=pag,
                           warehouses=Warehouse.query.order_by(Warehouse.name).all(),
                           customers=Customer.query.order_by(Customer.name).limit(100).all(),
                           sellers=User.query.filter_by(is_active=True).order_by(User.username).all(),
                           status_map=STATUS_MAP)

def _resolve_unit_price(product_id: int, warehouse_id: Optional[int]) -> float:
    prod = db.session.get(Product, product_id)
    try:
        return float(getattr(prod, "price", 0) or 0)
    except Exception:
        return 0.0

@sales_bp.route("/new", methods=["GET", "POST"], endpoint="create_sale")
@login_required
@permission_required("manage_sales")
def create_sale():
    form = SaleForm()
    if request.method == "POST" and not form.validate_on_submit():
        current_app.logger.warning("Sale form errors: %s", form.errors)
        current_app.logger.debug("POST data: %r", request.form.to_dict(flat=False))
    if form.validate_on_submit():
        try:
            target_status = (form.status.data or "DRAFT").upper()
            require_stock = (target_status == "CONFIRMED")
            lines_payload, err = _resolve_lines_from_form(form, require_stock=require_stock)
            if err:
                flash(f"❌ {err}", "danger")
                return render_template("sales/form.html", form=form, title="إنشاء فاتورة جديدة",
                                       products=Product.query.order_by(Product.name).all(),
                                       warehouses=Warehouse.query.order_by(Warehouse.name).all())
            for d in lines_payload:
                if (d.get("unit_price") or 0) <= 0:
                    d["unit_price"] = _resolve_unit_price(d["product_id"], d.get("warehouse_id"))
            if require_stock:
                pairs = [(d["product_id"], d["warehouse_id"]) for d in lines_payload if d.get("warehouse_id")]
                _lock_stock_rows(pairs)
            sale = Sale(
                sale_number=None,
                customer_id=form.customer_id.data,
                seller_id=form.seller_id.data,
                sale_date=form.sale_date.data or datetime.utcnow(),
                status=target_status,
                currency=(form.currency.data or "ILS").upper(),
                tax_rate=form.tax_rate.data or 0,
                discount_total=form.discount_total.data or 0,
                shipping_cost=form.shipping_cost.data or 0,
                notes=form.notes.data
            )
            db.session.add(sale)
            db.session.flush()
            _safe_generate_number_after_flush(sale)
            _attach_lines(sale, lines_payload)
            db.session.flush()
            if require_stock:
                _reserve_stock(sale)
            _log(sale, "CREATE", None, sale_to_dict(sale))
            db.session.commit()
            flash("✅ تم إنشاء الفاتورة.", "success")
            return redirect(url_for("sales_bp.sale_detail", id=sale.id))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"❌ خطأ قاعدة بيانات أثناء الحفظ: {e}", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"❌ خطأ أثناء الحفظ: {e}", "danger")
    return render_template("sales/form.html", form=form, title="إنشاء فاتورة جديدة",
                           products=Product.query.order_by(Product.name).all(),
                           warehouses=Warehouse.query.order_by(Warehouse.name).all())

@sales_bp.route("/<int:id>", methods=["GET"], endpoint="sale_detail")
@login_required
@permission_required("manage_sales")
def sale_detail(id: int):
    sale = _get_or_404(Sale, id, options=[
        joinedload(Sale.customer), joinedload(Sale.seller),
        joinedload(Sale.lines).joinedload(SaleLine.product),
        joinedload(Sale.lines).joinedload(SaleLine.warehouse),
        joinedload(Sale.payments),
    ])
    _format_sale(sale)
    for ln in sale.lines:
        ln.product_name = ln.product.name if ln.product else "-"
        ln.warehouse_name = ln.warehouse.name if ln.warehouse else "-"
        base_total = line_total_decimal(ln.quantity, ln.unit_price, ln.discount_rate)
        tr = D(getattr(ln, "tax_rate", 0))
        tax_amount = (base_total * tr / Decimal("100")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        line_with_tax = (base_total + tax_amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        ln.line_total_fmt = money_fmt(line_with_tax)
    for p in sale.payments:
        p.date_formatted = p.payment_date.strftime("%Y-%m-%d") if getattr(p, "payment_date", None) else "-"
        lbl, cls = PAYMENT_STATUS_MAP.get(p.status, (p.status, ""))
        p.status_label, p.status_class = lbl, cls
        p.method_label = PAYMENT_METHOD_MAP.get(getattr(p, "method", ""), getattr(p, "method", ""))
    invoice = Invoice.query.filter_by(sale_id=id).first()
    return render_template(
        "sales/detail.html",
        sale=sale,
        invoice=invoice,
        status_map=STATUS_MAP,
        payment_method_map=PAYMENT_METHOD_MAP,
        payment_status_map=PAYMENT_STATUS_MAP,
    )

@sales_bp.route("/<int:id>/payments", methods=["GET"], endpoint="sale_payments")
@login_required
@permission_required("manage_sales")
def sale_payments(id: int):
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    q = (Payment.query.options(joinedload(Payment.splits))
         .filter(Payment.sale_id == id)
         .order_by(Payment.payment_date.desc(), Payment.id.desc()))
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    sale = db.session.get(Sale, id) or abort(404)
    total_paid = getattr(sale, "total_paid", 0)
    if request.headers.get("Accept", "").startswith("application/json"):
        return jsonify({
            "payments": [p.to_dict() for p in pagination.items],
            "total_pages": pagination.pages,
            "current_page": pagination.page,
            "entity": {"type": "SALE", "id": id},
            "total_paid": float(total_paid),
        })
    return render_template(
        "payments/list.html",
        payments=pagination.items,
        pagination=pagination,
        entity_type="SALE",
        entity_id=id,
        total_paid=total_paid
    )

@sales_bp.route("/<int:id>/edit", methods=["GET", "POST"], endpoint="edit_sale")
@login_required
@permission_required("manage_sales")
def edit_sale(id: int):
    sale = _get_or_404(Sale, id)
    if sale.status in ("CANCELLED", "REFUNDED"):
        flash("❌ لا يمكن تعديل فاتورة ملغاة/مرتجعة.", "danger")
        return redirect(url_for("sales_bp.sale_detail", id=sale.id))
    old = sale_to_dict(sale)
    form = SaleForm(obj=sale)
    if request.method == "GET":
        while len(form.lines.entries) < len(sale.lines):
            form.lines.append_entry()
        for idx, ln in enumerate(sale.lines):
            e = form.lines.entries[idx].form
            e.product_id.data = ln.product_id
            e.warehouse_id.data = ln.warehouse_id
            e.quantity.data = ln.quantity
            e.unit_price.data = ln.unit_price
            e.discount_rate.data = ln.discount_rate
            e.tax_rate.data = ln.tax_rate
            e.note.data = ln.note
    if request.method == "POST" and not form.validate_on_submit():
        current_app.logger.warning("Sale form errors (edit): %s", form.errors)
        current_app.logger.debug("POST data (edit): %r", request.form.to_dict(flat=False))
    if form.validate_on_submit():
        try:
            was_confirmed = (sale.status == "CONFIRMED")
            if was_confirmed:
                _release_stock(sale)
            target_status = (form.status.data or sale.status or "DRAFT").upper()
            require_stock = (target_status == "CONFIRMED")
            lines_payload, err = _resolve_lines_from_form(form, require_stock=require_stock)
            if err:
                if was_confirmed:
                    _reserve_stock(sale)
                flash(f"❌ {err}", "danger")
                return render_template("sales/form.html", form=form, sale=sale, title="تعديل الفاتورة",
                                       products=Product.query.order_by(Product.name).all(),
                                       warehouses=Warehouse.query.order_by(Warehouse.name).all())
            for d in lines_payload:
                if (d.get("unit_price") or 0) <= 0:
                    d["unit_price"] = _resolve_unit_price(d["product_id"], d.get("warehouse_id"))
            if require_stock:
                pairs = [(d["product_id"], d["warehouse_id"]) for d in lines_payload if d.get("warehouse_id")]
                _lock_stock_rows(pairs)
            sale.customer_id = form.customer_id.data
            sale.seller_id = form.seller_id.data
            sale.sale_date = form.sale_date.data or sale.sale_date
            sale.status = target_status or sale.status
            sale.currency = (form.currency.data or sale.currency or "ILS").upper()
            sale.tax_rate = form.tax_rate.data or 0
            sale.discount_total = form.discount_total.data or 0
            sale.shipping_cost = form.shipping_cost.data or 0
            sale.notes = form.notes.data
            _attach_lines(sale, lines_payload)
            db.session.flush()
            if require_stock:
                _reserve_stock(sale)
            _log(sale, "UPDATE", old, sale_to_dict(sale))
            db.session.commit()
            flash("✅ تم التعديل بنجاح.", "success")
            return redirect(url_for("sales_bp.sale_detail", id=sale.id))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"❌ خطأ قاعدة بيانات أثناء التعديل: {e}", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"❌ خطأ أثناء التعديل: {e}", "danger")
    return render_template("sales/form.html", form=form, sale=sale, title="تعديل الفاتورة",
                           products=Product.query.order_by(Product.name).all(),
                           warehouses=Warehouse.query.order_by(Warehouse.name).all())

@sales_bp.route("/quick", methods=["POST"])
@login_required
@permission_required("manage_sales")
def quick_sell():
    try:
        pid = int(request.form.get("product_id") or 0)
        wid = int(request.form.get("warehouse_id") or 0)
        qty = int(float(request.form.get("quantity") or 0))
        price_raw = request.form.get("unit_price")
        price = float(price_raw) if price_raw not in (None, "",) else 0.0
        customer_id = int(request.form.get("customer_id") or 0)
        seller_id = int(request.form.get("seller_id") or (current_user.id or 0))
        status = (request.form.get("status") or "DRAFT").upper()
        if not (pid and qty > 0 and customer_id and seller_id):
            flash("بيانات غير مكتملة للبيع السريع.", "danger")
            return redirect(url_for("sales_bp.list_sales"))
        chosen_wid = wid or _auto_pick_warehouse(pid, qty, preferred_wid=None)
        if status == "CONFIRMED":
            if not chosen_wid:
                flash("لا يوجد مخزن مناسب متاح لهذه الكمية.", "danger")
                return redirect(url_for("sales_bp.list_sales"))
            if _available_qty(pid, chosen_wid) < qty:
                flash("الكمية غير متوفرة في المخازن.", "danger")
                return redirect(url_for("sales_bp.list_sales"))
            _lock_stock_rows([(pid, chosen_wid)])
        if price <= 0:
            price = _resolve_unit_price(pid, chosen_wid)
        sale = Sale(
            sale_number=None,
            customer_id=customer_id,
            seller_id=seller_id,
            sale_date=datetime.utcnow(),
            status=status,
            currency="ILS"
        )
        db.session.add(sale)
        db.session.flush()
        _safe_generate_number_after_flush(sale)
        db.session.add(SaleLine(
            sale_id=sale.id, product_id=pid, warehouse_id=chosen_wid, quantity=qty,
            unit_price=price, discount_rate=0, tax_rate=0
        ))
        db.session.flush()
        if status == "CONFIRMED":
            _reserve_stock(sale)
        _log(sale, "CREATE", None, sale_to_dict(sale))
        db.session.commit()
        flash("✅ تم إنشاء فاتورة سريعة.", "success")
        return redirect(url_for("sales_bp.sale_detail", id=sale.id))
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"❌ فشل البيع السريع (قاعدة البيانات): {e}", "danger")
        return redirect(url_for("sales_bp.list_sales"))
    except Exception as e:
        db.session.rollback()
        flash(f"❌ فشل البيع السريع: {e}", "danger")
        return redirect(url_for("sales_bp.list_sales"))

@sales_bp.route("/<int:id>/delete", methods=["POST"], endpoint="delete_sale")
@login_required
@permission_required("manage_sales")
def delete_sale(id: int):
    sale = _get_or_404(Sale, id)
    if getattr(sale, "total_paid", 0) > 0:
        flash("❌ لا يمكن حذف فاتورة عليها دفعات.", "danger")
        return redirect(url_for("sales_bp.sale_detail", id=sale.id))
    try:
        _release_stock(sale)
        _log(sale, "DELETE", sale_to_dict(sale), None)
        db.session.delete(sale)
        db.session.commit()
        flash("✅ تم حذف الفاتورة.", "warning")
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"❌ خطأ أثناء الحذف: {e}", "danger")
    return redirect(url_for("sales_bp.list_sales"))

@sales_bp.route("/<int:id>/status/<status>", methods=["POST"], endpoint="change_status")
@login_required
@permission_required("manage_sales")
def change_status(id: int, status: str):
    sale = _get_or_404(Sale, id)
    status = (status or "").upper()
    valid = {
        "DRAFT": {"CONFIRMED", "CANCELLED"},
        "CONFIRMED": {"CANCELLED", "REFUNDED"},
        "CANCELLED": set(),
        "REFUNDED": set()
    }
    if status not in valid.get(sale.status, set()):
        flash("❌ حالة غير صالحة لهذا السجل.", "danger")
        return redirect(url_for("sales_bp.sale_detail", id=sale.id))
    try:
        if status == "CONFIRMED":
            lines = SaleLine.query.filter_by(sale_id=sale.id).all()
            pairs = []
            for ln in lines:
                pid, wid, qty = ln.product_id, ln.warehouse_id, int(ln.quantity or 0)
                if not wid:
                    wid = _auto_pick_warehouse(pid, qty, preferred_wid=None)
                    if not wid:
                        raise ValueError(f"لا يوجد مخزن مناسب متاح للمنتج ID={pid}.")
                    ln.warehouse_id = wid
                if _available_qty(pid, wid) < qty:
                    raise ValueError(f"الكمية غير متوفرة للمنتج ID={pid} في المخزن المحدد.")
                pairs.append((pid, wid))
            db.session.flush()
            _lock_stock_rows(pairs)
            sale.status = "CONFIRMED"
            db.session.flush()
            _reserve_stock(sale)
        elif status == "CANCELLED":
            _release_stock(sale)
            sale.status = "CANCELLED"
        elif status == "REFUNDED":
            _release_stock(sale)
            sale.status = "REFUNDED"
        db.session.commit()
        flash("✅ تم تحديث الحالة.", "success")
    except (SQLAlchemyError, ValueError) as e:
        db.session.rollback()
        flash(f"❌ خطأ أثناء تحديث الحالة: {e}", "danger")
    return redirect(url_for("sales_bp.sale_detail", id=sale.id))

@sales_bp.route("/<int:id>/invoice", methods=["GET"], endpoint="generate_invoice")
@login_required
@permission_required("manage_sales")
def generate_invoice(id: int):
    sale = _get_or_404(Sale, id, options=[
        joinedload(Sale.customer), joinedload(Sale.seller),
        joinedload(Sale.lines).joinedload(SaleLine.product),
        joinedload(Sale.lines).joinedload(SaleLine.warehouse),
    ])
    lines = []
    subtotal = Decimal("0.00")
    for ln in sale.lines:
        base_total = line_total_decimal(ln.quantity, ln.unit_price, ln.discount_rate)
        tr = D(getattr(ln, "tax_rate", 0))
        tax_amount = (base_total * tr / Decimal("100")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        line_total = (base_total + tax_amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        lines.append({
            "obj": ln,
            "base_total": base_total,
            "tax_amount": tax_amount,
            "line_total": line_total,
        })
        subtotal += base_total
    sale_tax_rate = D(getattr(sale, "tax_rate", 0))
    sale_shipping = D(getattr(sale, "shipping_cost", 0))
    sale_discount_total = D(getattr(sale, "discount_total", 0))
    subtotal_after_discount = (subtotal - sale_discount_total).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    invoice_tax_amount = (subtotal_after_discount * sale_tax_rate / Decimal("100")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    grand_total = (subtotal_after_discount + invoice_tax_amount + sale_shipping).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return render_template(
        "sales/receipt.html",
        sale=sale,
        lines=lines,
        subtotal=subtotal,
        sale_discount_total=sale_discount_total,
        subtotal_after_discount=subtotal_after_discount,
        sale_tax_rate=sale_tax_rate,
        invoice_tax_amount=invoice_tax_amount,
        sale_shipping=sale_shipping,
        grand_total=grand_total,
        money_fmt=money_fmt,
    )
