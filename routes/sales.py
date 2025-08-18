# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
    abort,
)
from flask_login import current_user, login_required
from sqlalchemy import func, or_, desc, extract
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from extensions import db
from models import (
    Sale,
    SaleLine,
    Invoice,
    Customer,
    Product,
    AuditLog,
    Warehouse,
    User,
    StockLevel,
    Payment,
)
from forms import SaleForm
from utils import permission_required

# ---- Labels / Maps -----------------------------------------------------------
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
PAYMENT_METHOD_MAP = {
    "cash": "نقدي",
    "cheque": "شيك",
    "card": "بطاقة",
    "bank": "تحويل بنكي",
    "online": "دفع إلكتروني",
}

sales_bp = Blueprint(
    "sales_bp",
    __name__,
    url_prefix="/sales",
    template_folder="templates/sales",
)

# ---- Helpers ----------------------------------------------------------------

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
    db.session.add(
        AuditLog(
            model_name="Sale",
            record_id=s.id,
            action=action,
            old_data=json.dumps(old, ensure_ascii=False) if old else None,
            new_data=json.dumps(new, ensure_ascii=False) if new else None,
            user_id=current_user.id if current_user.is_authenticated else None,
            timestamp=datetime.utcnow(),
        )
    )
    db.session.flush()


def _reserve_stock(sale: Sale) -> None:
    for ln in sale.lines:
        st = StockLevel.query.filter_by(
            product_id=ln.product_id, warehouse_id=ln.warehouse_id
        ).first()
        if not st or (st.quantity or 0) < ln.quantity:
            raise ValueError(
                f"مخزون غير كافٍ للمنتج: {ln.product.name if ln.product else ln.product_id}"
            )
        st.quantity = (st.quantity or 0) - ln.quantity
        if hasattr(st, "reserved_quantity"):
            st.reserved_quantity = (st.reserved_quantity or 0) + ln.quantity


def _release_stock(sale: Sale) -> None:
    for ln in sale.lines:
        st = StockLevel.query.filter_by(
            product_id=ln.product_id, warehouse_id=ln.warehouse_id
        ).first()
        if st:
            st.quantity = (st.quantity or 0) + ln.quantity
            if hasattr(st, "reserved_quantity"):
                st.reserved_quantity = max((st.reserved_quantity or 0) - ln.quantity, 0)


# ---- Views ------------------------------------------------------------------

@sales_bp.route("/dashboard")
@login_required
@permission_required("manage_sales")
def dashboard():
    total_sales = db.session.query(func.count(Sale.id)).scalar() or 0
    total_revenue = (
        db.session.query(func.coalesce(func.sum(Sale.total_amount), 0)).scalar() or 0
    )
    pending_sales = (
        db.session.query(func.count(Sale.id)).filter(Sale.status == "DRAFT").scalar() or 0
    )

    top_customers = (
        db.session.query(Customer.name, func.sum(Sale.total_amount).label("spent"))
        .join(Sale, Sale.customer_id == Customer.id)
        .group_by(Customer.id)
        .order_by(desc("spent"))
        .limit(5)
        .all()
    )

    top_products = (
        db.session.query(
            Product.name,
            func.sum(SaleLine.quantity).label("sold"),
            func.sum(SaleLine.quantity * SaleLine.unit_price).label("revenue"),
        )
        .join(SaleLine, SaleLine.product_id == Product.id)
        .group_by(Product.id)
        .order_by(desc("sold"))
        .limit(5)
        .all()
    )

    y = extract("year", Sale.sale_date)
    m = extract("month", Sale.sale_date)
    monthly = (
        db.session.query(y.label("y"), m.label("m"), func.count(Sale.id), func.sum(Sale.total_amount))
        .group_by(y, m)
        .order_by(y, m)
        .all()
    )
    months, counts, revenue = [], [], []
    for yy, mm, cnt, total in monthly:
        months.append(f"{int(mm)}/{int(yy)}")
        counts.append(int(cnt))
        revenue.append(float(total or 0))

    return render_template(
        "sales/dashboard.html",
        total_sales=total_sales,
        total_revenue=total_revenue,
        pending_sales=pending_sales,
        top_customers=top_customers,
        top_products=top_products,
        months=months,
        sales_count=counts,
        revenue=revenue,
    )


@sales_bp.route("/", endpoint="list_sales")  # alias للحفاظ على الروابط القديمة
@sales_bp.route("/", endpoint="index")        # alias إضافي إن استُخدم في أماكن أخرى
@login_required
@permission_required("manage_sales")
def list_sales():
    f = request.args

    # Subtotal per sale (يأخذ الخصم والضريبة على مستوى السطر)
    subtotals = (
        db.session.query(
            Sale.id.label("sale_id"),
            func.coalesce(
                func.sum(
                    SaleLine.quantity
                    * SaleLine.unit_price
                    * (1 - (SaleLine.discount_rate or 0) / 100.0)
                    * (1 + (SaleLine.tax_rate or 0) / 100.0)
                ),
                0,
            ).label("calc_total"),
        )
        .outerjoin(SaleLine, SaleLine.sale_id == Sale.id)
        .group_by(Sale.id)
        .subquery()
    )

    # نضمّن Customer كـ outerjoin مرة واحدة لتسهيل الفرز/البحث
    q = (
        Sale.query.options(joinedload(Sale.customer), joinedload(Sale.seller))
        .outerjoin(subtotals, subtotals.c.sale_id == Sale.id)
        .outerjoin(Customer)
    )

    # فلاتر
    st = f.get("status", "all").upper()
    if st and st != "ALL":
        q = q.filter(Sale.status == st)

    cust = (f.get("customer") or "").strip()
    if cust:
        q = q.filter(
            or_(Customer.name.ilike(f"%{cust}%"), Customer.phone.ilike(f"%{cust}%"))
        )

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

    # ترتيب
    sort = f.get("sort", "date")
    order = f.get("order", "desc")
    if sort == "total":
        fld = subtotals.c.calc_total
    elif sort == "customer":
        fld = Customer.name
    else:
        fld = Sale.sale_date
    q = q.order_by(fld.asc() if order == "asc" else fld.desc())

    # صفحات
    page = int(f.get("page", 1))
    pag = q.paginate(page=page, per_page=20, error_out=False)
    sales = pag.items
    for s in sales:
        _format_sale(s)

    return render_template(
        "sales/list.html",
        sales=sales,
        pagination=pag,
        warehouses=Warehouse.query.order_by(Warehouse.name).all(),
        customers=Customer.query.order_by(Customer.name).limit(100).all(),
        sellers=User.query.filter_by(is_active=True).order_by(User.username).all(),
        status_map=STATUS_MAP,
    )


@sales_bp.route("/new", methods=["GET", "POST"], endpoint="create_sale")
@login_required
@permission_required("manage_sales")
def create_sale():
    form = SaleForm()
    if form.validate_on_submit():
        last = Sale.query.order_by(Sale.id.desc()).first()
        seq = (last.id + 1) if last else 1
        number = f"INV-{datetime.utcnow():%Y%m%d}-{seq:04d}"

        sale = Sale(
            sale_number=number,
            customer_id=form.customer_id.data,
            seller_id=form.seller_id.data,
            sale_date=form.sale_date.data or datetime.utcnow(),
            status=form.status.data or "DRAFT",
            currency=form.currency.data,
            tax_rate=form.tax_rate.data or 0,
            discount_total=form.discount_total.data or 0,
            shipping_cost=form.shipping_cost.data or 0,
            notes=form.notes.data,
        )
        db.session.add(sale)
        db.session.flush()

        for ent in form.lines.entries:
            ln = ent.form
            if not ln.product_id.data or (ln.quantity.data or 0) <= 0:
                continue
            db.session.add(
                SaleLine(
                    sale_id=sale.id,
                    product_id=ln.product_id.data,
                    warehouse_id=ln.warehouse_id.data,
                    quantity=ln.quantity.data,
                    unit_price=ln.unit_price.data,
                    discount_rate=ln.discount_rate.data or 0,
                    tax_rate=ln.tax_rate.data or 0,
                    note=ln.note.data,
                )
            )
        try:
            db.session.flush()
            sale.total_amount = sale.total  # يفترض وجود خاصية hybrid/properties
            _reserve_stock(sale)
            _log(sale, "CREATE", None, sale_to_dict(sale))
            db.session.commit()
            flash("✅ تم إنشاء الفاتورة.", "success")
            return redirect(url_for("sales_bp.sale_detail", id=sale.id))
        except Exception as e:  # يشمل ValueError من المخزون
            db.session.rollback()
            flash(f"❌ خطأ أثناء الحفظ: {e}", "danger")

    return render_template(
        "sales/form.html",
        form=form,
        title="إنشاء فاتورة جديدة",
        products=Product.query.order_by(Product.name).all(),
        warehouses=Warehouse.query.order_by(Warehouse.name).all(),
    )


@sales_bp.route("/<int:id>", methods=["GET"], endpoint="sale_detail")
@login_required
@permission_required("manage_sales")
def sale_detail(id: int):
    sale = _get_or_404(
        Sale,
        id,
        options=[
            joinedload(Sale.customer),
            joinedload(Sale.seller),
            joinedload(Sale.lines).joinedload(SaleLine.product),
            joinedload(Sale.lines).joinedload(SaleLine.warehouse),
            joinedload(Sale.payments),
        ],
    )
    _format_sale(sale)

    for ln in sale.lines:
        ln.product_name = ln.product.name if ln.product else "-"
        ln.warehouse_name = ln.warehouse.name if ln.warehouse else "-"
        ln.line_total = float(
            ln.quantity * ln.unit_price * (1 - (ln.discount_rate or 0) / 100.0)
        )
        ln.line_total *= (1 + (ln.tax_rate or 0) / 100.0)
        ln.line_total_fmt = f"{ln.line_total:,.2f}"

    for p in sale.payments:
        p.date_formatted = (
            p.payment_date.strftime("%Y-%m-%d") if getattr(p, "payment_date", None) else "-"
        )
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

    q = (
        Payment.query.options(joinedload(Payment.splits))
        .filter(Payment.sale_id == id)
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
    )
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    if request.headers.get("Accept", "").startswith("application/json"):
        return jsonify(
            {
                "payments": [p.to_dict() for p in pagination.items],
                "total_pages": pagination.pages,
                "current_page": pagination.page,
                "entity": {"type": "SALE", "id": id},
            }
        )

    return render_template(
        "payments/list.html",
        payments=pagination.items,
        pagination=pagination,
        entity_type="SALE",
        entity_id=id,
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
        # ضمن عدد إدخالات يساوي عدد الأسطر الحالية
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

    if form.validate_on_submit():
        try:
            # فك الحجز القديم قبل التعديل
            _release_stock(sale)

            sale.customer_id = form.customer_id.data
            sale.seller_id = form.seller_id.data
            sale.sale_date = form.sale_date.data or sale.sale_date
            sale.status = form.status.data or sale.status
            sale.currency = form.currency.data
            sale.tax_rate = form.tax_rate.data or 0
            sale.discount_total = form.discount_total.data or 0
            sale.shipping_cost = form.shipping_cost.data or 0
            sale.notes = form.notes.data

            # حذف أسطر قديمة (synchronize_session=False لتفادي مشاكل state)
            SaleLine.query.filter_by(sale_id=sale.id).delete(synchronize_session=False)
            db.session.flush()

            for ent in form.lines.entries:
                ln = ent.form
                if not ln.product_id.data or (ln.quantity.data or 0) <= 0:
                    continue
                db.session.add(
                    SaleLine(
                        sale_id=sale.id,
                        product_id=ln.product_id.data,
                        warehouse_id=ln.warehouse_id.data,
                        quantity=ln.quantity.data,
                        unit_price=ln.unit_price.data,
                        discount_rate=ln.discount_rate.data or 0,
                        tax_rate=ln.tax_rate.data or 0,
                        note=ln.note.data,
                    )
                )

            db.session.flush()
            sale.total_amount = sale.total
            _reserve_stock(sale)
            _log(sale, "UPDATE", old, sale_to_dict(sale))
            db.session.commit()
            flash("✅ تم التعديل بنجاح.", "success")
            return redirect(url_for("sales_bp.sale_detail", id=sale.id))
        except Exception as e:
            db.session.rollback()
            flash(f"❌ خطأ أثناء التعديل: {e}", "danger")

    return render_template(
        "sales/form.html",
        form=form,
        sale=sale,
        title="تعديل الفاتورة",
        products=Product.query.order_by(Product.name).all(),
        warehouses=Warehouse.query.order_by(Warehouse.name).all(),
    )


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
        "REFUNDED": set(),
    }
    if status not in valid.get(sale.status, set()):
        flash("❌ حالة غير صالحة لهذا السجل.", "danger")
        return redirect(url_for("sales_bp.sale_detail", id=sale.id))

    try:
        if status == "CANCELLED":
            _release_stock(sale)
        sale.status = status
        db.session.commit()
        flash("✅ تم تحديث الحالة.", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"❌ خطأ أثناء تحديث الحالة: {e}", "danger")

    return redirect(url_for("sales_bp.sale_detail", id=sale.id))


@sales_bp.route("/<int:id>/payments/add", methods=["GET", "POST"], endpoint="add_payment")
@login_required
@permission_required("manage_sales")
def add_payment(id: int):
    # تصحيح اسم الـ blueprint المستهدف ليتوافق مع التسجيل في app.py
    return redirect(url_for("payments_bp.create_payment", entity_type="SALE", entity_id=id))


@sales_bp.route("/payments/<int:pid>/delete", methods=["POST"], endpoint="delete_payment")
@login_required
@permission_required("manage_sales")
def delete_payment(pid: int):
    return redirect(url_for("payments_bp.delete_payment", payment_id=pid))


@sales_bp.route("/<int:id>/invoice", methods=["GET"], endpoint="generate_invoice")
@login_required
@permission_required("manage_sales")
def generate_invoice(id: int):
    sale = _get_or_404(
        Sale,
        id,
        options=[
            joinedload(Sale.customer),
            joinedload(Sale.seller),
            joinedload(Sale.lines).joinedload(SaleLine.product),
            joinedload(Sale.lines).joinedload(SaleLine.warehouse),
        ],
    )
    return render_template("sales/receipt.html", sale=sale)
