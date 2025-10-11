from __future__ import annotations
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from werkzeug.exceptions import BadRequest
from flask import Blueprint, Response, flash, jsonify, render_template, request, current_app, redirect, url_for
from sqlalchemy.orm import class_mapper
from sqlalchemy import func, cast, Date, desc, or_
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import inspect as sa_inspect
from extensions import db
from flask_login import login_required
from utils import permission_required
from sqlalchemy.exc import SQLAlchemyError
import inspect as pyinspect

from models import (
    Customer, Supplier, Partner, Product, Warehouse, StockLevel, Expense,
    OnlinePreOrder, OnlinePayment, OnlineCart, Sale, SaleStatus, ServiceRequest, InvoiceStatus, Invoice, Payment,
    Shipment, PaymentDirection, PaymentStatus, PaymentSplit, PreOrder, ServicePart, ServiceTask
)
reports_bp = Blueprint('reports_bp', __name__, url_prefix='/reports')

from reports import (
    advanced_report, ap_aging_report, ar_aging_report,
    payment_summary_report_ils, sales_report_ils, service_reports_report, top_products_report
)

def _parse_date(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def _parse_date_like(x):
    if x is None:
        return None
    if isinstance(x, date):
        return x
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, str):
        try:
            return datetime.strptime(x.strip(), "%Y-%m-%d").date()
        except Exception:
            return None
    return None

_MODEL_LOOKUP = {
    "Sale": Sale,
    "Expense": Expense,
    "Invoice": Invoice,
    "Payment": Payment,
    "ServiceRequest": ServiceRequest,
    "OnlinePreOrder": OnlinePreOrder,
    "OnlinePayment": OnlinePayment,
    "Shipment": Shipment,
    "Customer": Customer,
    "Supplier": Supplier,
    "Partner": Partner,
    "Product": Product,
    "Warehouse": Warehouse,
    "StockLevel": StockLevel,
}

_DEFAULT_DATE_FIELD = {
    "Sale": "sale_date",
    "Expense": "date",
    "Invoice": "invoice_date",
    "Payment": "payment_date",
    "ServiceRequest": "received_at",
    "OnlinePreOrder": "created_at",
    "OnlinePayment": "created_at",
    "Shipment": "shipment_date",
    "Customer": "created_at",
    "Supplier": "created_at",
    "Partner": "created_at",
    "Product": "created_at",
    "Warehouse": "created_at",
    "StockLevel": "updated_at",
}

MODEL_LABELS = {
    "Sale": "المبيعات",
    "Expense": "المصاريف",
    "Invoice": "الفواتير",
    "Payment": "المدفوعات",
    "ServiceRequest": "طلبات الصيانة",
    "OnlinePreOrder": "الطلبات المسبقة (أونلاين)",
    "OnlinePayment": "مدفوعات أونلاين",
    "Shipment": "الشحنات",
    "Customer": "العملاء",
    "Supplier": "الموردون",
    "Partner": "الشركاء",
    "Product": "المنتجات",
    "Warehouse": "المستودعات",
    "StockLevel": "المخزون",
}

FIELD_LABELS: Dict[str, str] = {
    "id": "المعرف",
    "sale_number": "رقم الفاتورة",
    "sale_date": "اليوم",
    "customer_id": "العميل",
    "seller_id": "المندوب",
    "preorder_id": "طلب مسبق",
    "status": "الحالة",
    "payment_status": "حالة الدفع",
    "currency": "العملة",
    "discount_total": "إجمالي الخصم",
    "tax_rate": "نسبة الضريبة",
    "total_amount": "الإجمالي",
    "shipping_cost": "تكلفة الشحن",
    "billing_address": "عنوان الفاتورة",
    "shipping_address": "عنوان الشحن",
    "notes": "ملاحظات",
    "created_at": "تاريخ الإنشاء",
    "updated_at": "آخر تحديث",
    "date": "التاريخ",
    "type_id": "نوع المصروف",
    "amount": "المبلغ",
    "employee_id": "الوظف",
    "warehouse_id": "المستودع",
    "partner_id": "الشريك",
    "desc": "الوصف",
    "is_paid": "مدفوع؟",
    "invoice_date": "تاريخ الفاتورة",
    "total_invoiced": "إجمالي الفواتير",
    "net_balance": "الصافي",
    "total_paid": "المدفوع",
    "balance": "الرصيد",
    "payment_date": "تاريخ الدفع",
    "method": "طريقة الدفع",
    "received_at": "تاريخ الاستلام",
    "priority": "الأولوية",
    "mechanic_id": "الميكانيكي",
    "service_cost": "تكلفة الخدمة",
    "shipment_date": "تاريخ الشحنة",
    "number": "رقم الشحنة",
    "origin": "المنشأ",
    "destination": "الوجهة",
    "carrier": "الناقل",
    "tracking": "رقم التتبع",
    "value_before": "قيمة قبل التكاليف",
    "total_value": "القيمة الإجمالية",
    "product": "المنتج",
    "warehouse": "المستودع",
    "quantity": "الكمية",
    "reserved": "محجوز",
    "available": "المتوفر",
    "min_stock": "الحد الأدنى",
    "max_stock": "الحد الأقصى",
    "sales": "المبيعات",
    "sales_by_day": "مبيعات حسب اليوم",
    "date_range": "نطاق التاريخ",
    "start_date": "من",
    "end_date": "إلى",
    "refresh": "تحديث",
    "sales_table": "جدول المبيعات",
    "grand_total": "الإجمالي",
    "ap_aging": "أعمار الذمم (الموردون)",
    "ar_aging": "أعمار الذمم (العملاء)",
    "supplier": "المورد",
    "customer": "العميل",
    "customers": "العملاء",
    "service_reports": "تقارير الصيانة",
    "total_requests": "عدد الطلبات",
    "completed": "مكتملة",
    "revenue": "الإيراد",
    "parts": "قطع",
    "labor": "أجور",
    "total": "الإجمالي",
    "payments_summary": "ملخص المدفوعات حسب طريقة الدفع",
    "payment_method": "طريقة الدفع",
}

METHOD_LABELS_DEFAULT = {
    "cash": "نقدي",
    "card": "بطاقة",
    "bank": "حوالة بنكية",
    "BANK": "حوالة بنكية",
    "CHEQUE": "شيك",
    "cheque": "شيك",
    "online": "أونلاين",
    "other": "أخرى",
}

def _ensure_model(name: str):
    model = _MODEL_LOOKUP.get(name)
    if not model:
        raise BadRequest("نموذج غير معروف")
    return model

def _model_columns(model) -> List[str]:
    return [c.key for c in class_mapper(model).columns]

def _model_all_fields(model):
    cols = set(c.key for c in class_mapper(model).columns)
    hybrids = []
    for name in dir(model):
        if name.startswith("_") or name in cols:
            continue
        attr = pyinspect.getattr_static(model, name, None)
        if isinstance(attr, hybrid_property):
            hybrids.append(name)
    return sorted(list(cols.union(hybrids)))

def _is_selectable_field(model, name):
    mapper_cols = {c.key for c in class_mapper(model).columns}
    if name in mapper_cols:
        return True
    attr = pyinspect.getattr_static(model, name, None)
    if isinstance(attr, hybrid_property):
        try:
            _ = getattr(model, name).expression
            return True
        except Exception:
            return False
    return False

def _sanitize_fields(fields: List[str], allowed: List[str]) -> List[str]:
    allowed_set = set(allowed or [])
    return [f for f in (fields or []) if f in allowed_set]

def _sanitize_likes(like_filters: Dict[str, str], allowed: List[str]) -> Dict[str, str]:
    allowed_set = set(allowed or [])
    return {k: v for k, v in (like_filters or {}).items() if k in allowed_set and v not in (None, "")}

def _clamp_limit(v: Optional[int], default: int = 1000, max_v: int = 10000) -> int:
    try:
        n = int(v if v is not None else default)
    except Exception:
        n = default
    return max(1, min(n, max_v))

@reports_bp.route("/", methods=["GET"], endpoint="universal")
@reports_bp.route("", methods=["GET"], endpoint="index")
def reports_index():
    return render_template("reports/index.html", model_names=list(_MODEL_LOOKUP.keys()), defaults=_DEFAULT_DATE_FIELD, FIELD_LABELS=FIELD_LABELS, MODEL_LABELS=MODEL_LABELS)

@reports_bp.route("/dynamic", methods=["GET", "POST"])
def dynamic_report():
    model_names = list(_MODEL_LOOKUP.keys())
    if request.method == "POST":
        table = (request.form.get("table") or "").strip()
        selected_fields = request.form.getlist("selected_fields") or []
        date_field = (request.form.get("date_field") or "").strip()
        start_date = _parse_date(request.form.get("start_date"))
        end_date = _parse_date(request.form.get("end_date"))
        limit = _clamp_limit(request.form.get("limit"))
        try:
            model = _ensure_model(table)
        except BadRequest as e:
            flash(str(e), "danger")
            return render_template("reports/dynamic.html", data=None, summary=None, columns=selected_fields, model_names=model_names, selected_table=None, defaults=_DEFAULT_DATE_FIELD, date_field=date_field, start_date=request.form.get("start_date", ""), end_date=request.form.get("end_date", ""), like_filters={}, limit=limit, FIELD_LABELS=FIELD_LABELS, MODEL_LABELS=MODEL_LABELS), 400
        cols = [c for c in _model_all_fields(model) if _is_selectable_field(model, c)]
        all_fields = _model_all_fields(model)
        selected_fields = _sanitize_fields(selected_fields, all_fields) or None
        like_filters = {k: v for k, v in request.form.items() if k not in {"csrf_token", "table", "date_field", "start_date", "end_date", "selected_fields", "limit"} and v not in (None, "")}
        like_filters = _sanitize_likes(like_filters, cols)
        if date_field and date_field not in cols:
            date_field = ""
        if not date_field:
            df = _DEFAULT_DATE_FIELD.get(table)
            date_field = df if df in cols else None
        try:
            rpt = advanced_report(model=model, date_field=date_field or None, start_date=start_date, end_date=end_date, filters=None, like_filters=like_filters or None, columns=selected_fields, aggregates={"count": ["id"]})
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("reports/dynamic.html", data=None, summary=None, columns=(selected_fields or []), model_names=model_names, selected_table=table, defaults=_DEFAULT_DATE_FIELD, date_field=(date_field or ""), start_date=request.form.get("start_date", ""), end_date=request.form.get("end_date", ""), like_filters=like_filters, limit=limit, FIELD_LABELS=FIELD_LABELS, MODEL_LABELS=MODEL_LABELS), 400
        data = rpt.get("data") or []
        if limit:
            data = data[:limit]
        return render_template("reports/dynamic.html", data=data, summary=rpt.get("summary") or {}, columns=(selected_fields or []), model_names=model_names, selected_table=table, defaults=_DEFAULT_DATE_FIELD, date_field=(date_field or ""), start_date=request.form.get("start_date", ""), end_date=request.form.get("end_date", ""), like_filters=like_filters, limit=limit, FIELD_LABELS=FIELD_LABELS, MODEL_LABELS=MODEL_LABELS)
    selected_table = model_names[0] if model_names else None
    return render_template("reports/dynamic.html", data=None, summary=None, columns=[], model_names=model_names, selected_table=selected_table, defaults=_DEFAULT_DATE_FIELD, date_field=_DEFAULT_DATE_FIELD.get(selected_table, "") if selected_table else "", start_date="", end_date="", like_filters={}, limit=1000, FIELD_LABELS=FIELD_LABELS, MODEL_LABELS=MODEL_LABELS)

@reports_bp.route("/below_min_stock", endpoint="below_min_stock_report")
@login_required
def below_min_stock_report():
    try:
        q = (
            db.session.query(
                Product,
                func.coalesce(func.sum(StockLevel.quantity), 0).label("on_hand")
            )
            .join(StockLevel, StockLevel.product_id == Product.id)
            .filter(Product.is_active.is_(True))
            .filter(Product.min_qty.isnot(None))
            .group_by(Product.id)
        )
        rows = q.all()
        data = []
        for p, on_hand in rows:
            if p.min_qty and on_hand < p.min_qty:
                data.append({
                    "id": p.id,
                    "name": p.name,
                    "on_hand": int(on_hand),
                    "min_qty": p.min_qty,
                })
        return render_template(
            "reports/below_min_stock.html",
            data=data,
            FIELD_LABELS=FIELD_LABELS,
            MODEL_LABELS=MODEL_LABELS,
        )
    except SQLAlchemyError as err:
        current_app.logger.error("DB error: %s", err)
        flash("خطأ في قاعدة البيانات", "danger")
        return redirect(url_for("reports_bp.index"))

@reports_bp.route("/shipments", methods=["GET"], endpoint="shipments")
@login_required
@permission_required("view_inventory")
def shipments_report():
    start_str = request.args.get("start")
    end_str = request.args.get("end")
    start = None
    end = None
    try:
        if start_str:
            start = datetime.strptime(start_str, "%Y-%m-%d").date()
        if end_str:
            end = datetime.strptime(end_str, "%Y-%m-%d").date()
    except Exception:
        flash("❌ صيغة التاريخ غير صحيحة", "danger")
    q = db.session.query(Shipment)
    if start:
        q = q.filter(Shipment.shipment_date >= start)
    if end:
        q = q.filter(Shipment.shipment_date <= end)
    rows = q.order_by(Shipment.shipment_date.desc()).all()
    totals = {
        "shipments": len(rows),
        "value_before": sum(float(s.value_before or 0) for s in rows),
        "total_value": sum(float(s.total_value or 0) for s in rows),
    }
    return render_template(
        "reports/shipments.html",
        data=rows,
        totals=totals,
        start=start_str,
        end=end_str,
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

@reports_bp.route("/online", endpoint="online")
@login_required
def online_report():
    orders_count = db.session.query(func.count(OnlinePreOrder.id)).scalar() or 0
    orders_total = db.session.query(func.coalesce(func.sum(OnlinePreOrder.total_amount), 0)).scalar() or 0
    payments_total = db.session.query(func.coalesce(func.sum(OnlinePayment.amount), 0)).filter(OnlinePayment.status == "SUCCESS").scalar() or 0
    carts_active = db.session.query(func.count(OnlineCart.id)).filter(OnlineCart.status == "ACTIVE").scalar() or 0
    return render_template(
        "reports/online.html",
        orders_count=orders_count,
        orders_total=orders_total,
        payments_total=payments_total,
        carts_active=carts_active,
        FIELD_LABELS=FIELD_LABELS
    )

@reports_bp.route("/sales", methods=["GET"])
def sales():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    rpt = sales_report_ils(start, end)
    return render_template("reports/sales.html", **rpt, start=request.args.get("start", ""), end=request.args.get("end", ""), FIELD_LABELS=FIELD_LABELS, MODEL_LABELS=MODEL_LABELS)

@reports_bp.route("/payments-summary", methods=["GET"], strict_slashes=False)
def payments_summary():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    rpt = payment_summary_report_ils(start, end)
    method_labels = {m: METHOD_LABELS_DEFAULT.get(m.upper(), METHOD_LABELS_DEFAULT.get(m, m)) for m in rpt.get("methods", [])}
    return render_template(
        "reports/payments.html",
        **rpt,
        METHOD_LABELS=method_labels,
        start=request.args.get("start", ""),
        end=request.args.get("end", ""),
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

@reports_bp.route("/ar-aging", methods=["GET"])
def ar_aging():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    rpt = ar_aging_report(start_date=start, end_date=end)
    return render_template("reports/ar_aging.html", data=rpt.get("data", []), totals=rpt.get("totals", {}), as_of=rpt.get("as_of"), start=request.args.get("start", ""), end=request.args.get("end", ""), FIELD_LABELS=FIELD_LABELS, MODEL_LABELS=MODEL_LABELS)

@reports_bp.route("/inventory", methods=["GET"], endpoint="inventory")
@login_required
@permission_required("view_inventory")
def inventory_report():
    from models import Warehouse, StockLevel, Product
    from sqlalchemy.orm import joinedload
    search = (request.args.get("q") or "").strip()
    whs = Warehouse.query.order_by(Warehouse.name).all()
    wh_ids = [w.id for w in whs]
    q = (
        db.session.query(StockLevel)
        .join(Product, StockLevel.product_id == Product.id)
        .filter(StockLevel.warehouse_id.in_(wh_ids))
        .options(joinedload(StockLevel.product))
        .order_by(Product.name.asc())
    )
    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.part_number.ilike(like),
            )
        )
    rows = q.all()
    pivot = {}
    for sl in rows:
        pid = sl.product_id
        p = sl.product
        if pid not in pivot:
            pivot[pid] = {
                "product": p,
                "by": {wid: {"on": 0, "res": 0} for wid in wh_ids},
                "total": 0,
            }
        on = int(sl.quantity or 0)
        res = int(getattr(sl, "reserved_quantity", 0) or 0)
        pivot[pid]["by"][sl.warehouse_id] = {"on": on, "res": res}
        pivot[pid]["total"] += on
    rows_data = sorted(pivot.values(), key=lambda d: (d["product"].name or "").lower())
    return render_template(
        "reports/inventory.html",
        warehouses=whs,
        rows=rows_data,
        search=search,
        FIELD_LABELS=FIELD_LABELS,
    )

@reports_bp.route("/top-products", methods=["GET"])
def top_products():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    try:
        limit = int(request.args.get("limit") or 20)
    except Exception:
        limit = 20
    limit = _clamp_limit(limit, default=20, max_v=1000)
    warehouse_id = request.args.get("warehouse_id")
    group_by_warehouse = (request.args.get("group_by") == "warehouse")
    rpt = top_products_report(
        start, end,
        limit=limit,
        warehouse_id=int(warehouse_id) if warehouse_id else None,
        group_by_warehouse=group_by_warehouse,
    )
    warehouses = Warehouse.query.order_by(Warehouse.name.asc()).all()
    return render_template(
        "reports/top_products.html",
        data=rpt.get("data", []),
        start=request.args.get("start", ""),
        end=request.args.get("end", ""),
        limit=limit,
        warehouses=warehouses,
        selected_warehouse_id=(int(warehouse_id) if warehouse_id else None),
        group_by_warehouse=group_by_warehouse,
        can_group_by_warehouse=rpt.get("can_group_by_warehouse", False),
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

@reports_bp.route("/suppliers", methods=["GET"], endpoint="suppliers_report")
def suppliers_report():
    q = (
        db.session.query(
            Supplier.id,
            Supplier.name,
            func.coalesce(Supplier.balance, 0).label("balance"),
            func.coalesce(func.sum(Payment.total_amount), 0).label("total_paid"),
        )
        .outerjoin(
            Payment,
            (Payment.supplier_id == Supplier.id)
            & (Payment.status == PaymentStatus.COMPLETED.value)
            & (Payment.direction == PaymentDirection.OUT.value),
        )
        .group_by(Supplier.id, Supplier.name, Supplier.balance)
        .order_by(Supplier.name.asc())
    )
    data = []
    for r in q.all():
        paid = float(r.total_paid or 0)
        balance = float(r.balance or 0)
        net_balance = balance - paid
        data.append(
            {
                "id": r.id,
                "name": r.name,
                "total_paid": paid,
                "balance": balance,
                "net_balance": net_balance,
            }
        )
    return render_template(
        "reports/suppliers.html",
        data=data,
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

@reports_bp.route("/partners", methods=["GET"], endpoint="partners_report")
def partners_report():
    q = (
        db.session.query(
            Partner.id,
            Partner.name,
            func.coalesce(Partner.balance, 0).label("balance"),
            Partner.share_percentage,
            func.coalesce(func.sum(Payment.total_amount), 0).label("total_paid"),
        )
        .outerjoin(
            Payment,
            (Payment.partner_id == Partner.id)
            & (Payment.status == PaymentStatus.COMPLETED.value),
        )
        .group_by(Partner.id, Partner.name, Partner.balance, Partner.share_percentage)
        .order_by(Partner.name.asc())
    )
    data = []
    total_balance = total_paid = total_net = 0
    for r in q.all():
        paid = float(r.total_paid or 0)
        balance = float(r.balance or 0)
        net_balance = balance - paid
        share = float(r.share_percentage or 0)
        data.append(
            {
                "id": r.id,
                "name": r.name,
                "balance": balance,
                "total_paid": paid,
                "net_balance": net_balance,
                "share_percentage": share,
            }
        )
        total_balance += balance
        total_paid += paid
        total_net += net_balance
    totals = {
        "balance": total_balance,
        "total_paid": total_paid,
        "net_balance": total_net,
    }
    return render_template(
        "reports/partners.html",
        data=data,
        totals=totals,
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

@reports_bp.route("/customers", methods=["GET"], endpoint="customers_report")
def customers_report():
    sd = _parse_date(request.args.get("start"))
    ed = _parse_date(request.args.get("end"))
    if sd and ed and ed < sd:
        sd, ed = ed, sd
    start = sd or date.min
    end = ed or date.max
    inv_date = cast(Invoice.invoice_date, Date).between(start, end)
    sale_date = cast(Sale.sale_date, Date).between(start, end)
    srv_ref_dt = func.coalesce(ServiceRequest.completed_at, ServiceRequest.received_at, ServiceRequest.created_at)
    srv_date = cast(srv_ref_dt, Date).between(start, end)
    opre_date = cast(OnlinePreOrder.created_at, Date).between(start, end)
    pay_date = cast(Payment.payment_date, Date).between(start, end)
    inv_agg = (
        db.session.query(
            Invoice.customer_id.label("cid"),
            func.coalesce(func.sum(Invoice.total_amount), 0).label("total")
        )
        .filter(Invoice.customer_id.isnot(None))
        .filter(Invoice.status.in_([
            InvoiceStatus.UNPAID.value,
            InvoiceStatus.PARTIAL.value,
            InvoiceStatus.PAID.value,
        ]))
        .filter(inv_date)
        .group_by(Invoice.customer_id)
        .subquery()
    )
    sale_agg = (
        db.session.query(
            Sale.customer_id.label("cid"),
            func.coalesce(func.sum(Sale.total_amount), 0).label("total")
        )
        .filter(Sale.customer_id.isnot(None))
        .filter(Sale.status == SaleStatus.CONFIRMED.value)
        .filter(sale_date)
        .group_by(Sale.customer_id)
        .subquery()
    )
    srv_agg = (
        db.session.query(
            ServiceRequest.customer_id.label("cid"),
            func.coalesce(func.sum(ServiceRequest.total_amount), 0).label("total")
        )
        .filter(ServiceRequest.customer_id.isnot(None))
        .filter(srv_date)
        .group_by(ServiceRequest.customer_id)
        .subquery()
    )
    opre_agg = (
        db.session.query(
            OnlinePreOrder.customer_id.label("cid"),
            func.coalesce(func.sum(OnlinePreOrder.total_amount), 0).label("total")
        )
        .filter(OnlinePreOrder.customer_id.isnot(None))
        .filter(opre_date)
        .group_by(OnlinePreOrder.customer_id)
        .subquery()
    )
    pay_agg = (
        db.session.query(
            Payment.customer_id.label("cid"),
            func.coalesce(func.sum(Payment.total_amount), 0).label("total")
        )
        .filter(Payment.customer_id.isnot(None))
        .filter(Payment.direction == PaymentDirection.IN.value)
        .filter(Payment.status == PaymentStatus.COMPLETED.value)
        .filter(pay_date)
        .group_by(Payment.customer_id)
        .subquery()
    )
    q = (
        db.session.query(
            Customer.id.label("id"),
            Customer.name.label("name"),
            (
                func.coalesce(inv_agg.c.total, 0) +
                func.coalesce(sale_agg.c.total, 0) +
                func.coalesce(srv_agg.c.total, 0) +
                func.coalesce(opre_agg.c.total, 0)
            ).label("total_invoiced"),
            func.coalesce(pay_agg.c.total, 0).label("total_paid"),
        )
        .outerjoin(inv_agg, inv_agg.c.cid == Customer.id)
        .outerjoin(sale_agg, sale_agg.c.cid == Customer.id)
        .outerjoin(srv_agg,  srv_agg.c.cid  == Customer.id)
        .outerjoin(opre_agg, opre_agg.c.cid == Customer.id)
        .outerjoin(pay_agg,  pay_agg.c.cid  == Customer.id)
        .order_by(desc("total_invoiced"), Customer.name.asc())
    )
    rows = q.all()
    data = []
    for r in rows:
        invoiced = float(r.total_invoiced or 0)
        paid = float(r.total_paid or 0)
        balance = invoiced - paid
        data.append({
            "id": r.id,
            "name": r.name,
            "total_invoiced": invoiced,
            "total_paid": paid,
            "balance": balance,
        })
    return render_template(
        "reports/customers.html",
        data=data,
        start=request.args.get("start", ""),
        end=request.args.get("end", ""),
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

@reports_bp.route("/expenses", methods=["GET"], endpoint="expenses_report")
def expenses_report():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    q = Expense.query
    if start:
        q = q.filter(Expense.date >= start)
    if end:
        q = q.filter(Expense.date <= end)
    q = q.order_by(Expense.date.desc())
    rows = q.all()
    total = sum(float(e.amount or 0) for e in rows)
    type_labels, type_values = [], []
    by_type = {}
    for e in rows:
        k = e.type_id or "غير محدد"
        by_type[k] = by_type.get(k, 0) + float(e.amount or 0)
    for k, v in by_type.items():
        type_labels.append(str(k))
        type_values.append(v)
    emp_labels, emp_values = [], []
    by_emp = {}
    for e in rows:
        k = e.employee_id or "غير محدد"
        by_emp[k] = by_emp.get(k, 0) + float(e.amount or 0)
    for k, v in by_emp.items():
        emp_labels.append(str(k))
        emp_values.append(v)
    return render_template(
        "reports/expenses.html",
        data=rows,
        total_amount=total,
        start=request.args.get("start", ""),
        end=request.args.get("end", ""),
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
        type_labels=type_labels,
        type_values=type_values,
        emp_labels=emp_labels,
        emp_values=emp_values,
    )

@reports_bp.route("/ap-aging", methods=["GET"])
def ap_aging():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    rpt = ap_aging_report(start_date=start, end_date=end)
    return render_template("reports/ap_aging.html", data=rpt.get("data", []), totals=rpt.get("totals", {}), as_of=rpt.get("as_of"), start=request.args.get("start", ""), end=request.args.get("end", ""), FIELD_LABELS=FIELD_LABELS, MODEL_LABELS=MODEL_LABELS)

@reports_bp.route("/api/model_fields", methods=["GET"])
def model_fields():
    model_name = (request.args.get("model") or "").strip()
    if not model_name:
        return jsonify({"models": list(_MODEL_LOOKUP.keys())}), 200
    model = _MODEL_LOOKUP.get(model_name)
    if not model:
        return jsonify({"error": "Unknown model", "models": list(_MODEL_LOOKUP.keys())}), 404
    mapper = sa_inspect(model)
    columns = [col.key for col in mapper.columns]
    lower = {c: c.lower() for c in columns}
    date_fields = [c for c in columns if ("date" in lower[c]) or (lower[c].endswith("_at")) or ("created_at" in lower[c]) or ("updated_at" in lower[c])]
    all_fields = _model_all_fields(model)
    return jsonify({"columns": columns, "date_fields": date_fields, "all_fields": all_fields}), 200

@reports_bp.route("/service-reports", methods=["GET"])
def service_reports():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    rpt = service_reports_report(start, end)
    return render_template("reports/service_reports.html", total=rpt.get("total", 0), completed=rpt.get("completed", 0), revenue=rpt.get("revenue", 0.0), parts=rpt.get("parts", 0.0), labor=rpt.get("labor", 0.0), data=rpt.get("data", []), start=request.args.get("start", ""), end=request.args.get("end", ""), FIELD_LABELS=FIELD_LABELS, MODEL_LABELS=MODEL_LABELS)

@reports_bp.route("/api/dynamic", methods=["POST"])
def api_dynamic():
    payload = request.get_json(silent=True) or {}
    table = (payload.get("table") or "").strip()
    model = _ensure_model(table)
    cols = [c for c in _model_all_fields(model) if _is_selectable_field(model, c)]
    all_fields = _model_all_fields(model)
    columns = _sanitize_fields(payload.get("columns") or [], all_fields) or None
    like_filters = _sanitize_likes(payload.get("like_filters") or {}, cols) or None
    date_field = (payload.get("date_field") or "").strip()
    if date_field and date_field not in cols:
        date_field = ""
    if not date_field:
        df = _DEFAULT_DATE_FIELD.get(table)
        date_field = df if df in cols else None
    limit = _clamp_limit(payload.get("limit"), default=1000, max_v=10000)
    rpt = advanced_report(
        model=model,
        date_field=date_field or None,
        start_date=_parse_date(payload.get("start_date")),
        end_date=_parse_date(payload.get("end_date")),
        filters=payload.get("filters"),
        like_filters=like_filters,
        columns=columns,
        aggregates=payload.get("aggregates"),
    )
    data = (rpt.get("data") or [])[:limit]
    return jsonify({"data": data, "summary": rpt.get("summary") or {}}), 200

def _csv_from_rows(rows: List[Dict[str, Any]]):
    if not rows:
        return ""
    import io, csv
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return output.getvalue()

@reports_bp.route("/export/dynamic.csv", methods=["POST"])
def export_dynamic_csv():
    table = (request.form.get("table") or "").strip()
    model = _ensure_model(table)
    cols = [c for c in _model_all_fields(model) if _is_selectable_field(model, c)]
    all_fields = _model_all_fields(model)
    selected_fields = request.form.getlist("selected_fields") or []
    selected_fields = _sanitize_fields(selected_fields, all_fields) or None
    date_field = (request.form.get("date_field") or "").strip()
    if date_field and date_field not in cols:
        date_field = ""
    if not date_field:
        df = _DEFAULT_DATE_FIELD.get(table)
        date_field = df if df in cols else None
    like_filters = {k: v for k, v in request.form.items() if k not in {"table", "date_field", "start_date", "end_date", "csrf_token", "selected_fields"} and v not in (None, "")}
    like_filters = _sanitize_likes(like_filters, cols)
    rpt = advanced_report(model=model, date_field=date_field or None, start_date=_parse_date(request.form.get("start_date")), end_date=_parse_date(request.form.get("end_date")), like_filters=like_filters or None, columns=selected_fields, aggregates={"count": ["id"]})
    csv_text = _csv_from_rows(rpt.get("data") or [])
    return Response(csv_text, mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=dynamic_report.csv"})

@reports_bp.route("/export/ar_aging.csv", methods=["GET"])
def export_ar_aging_csv():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    rpt = ar_aging_report(start_date=start, end_date=end)
    rows = []
    for item in rpt.get("data", []):
        row = {
            "customer": item.get("customer"),
            "0-30": item.get("buckets", {}).get("0-30", 0),
            "31-60": item.get("buckets", {}).get("31-60", 0),
            "61-90": item.get("buckets", {}).get("61-90", 0),
            "90+": item.get("buckets", {}).get("90+", 0),
            "total": item.get("balance", 0),
        }
        rows.append(row)
    csv_text = _csv_from_rows(rows)
    return Response(csv_text, mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=ar_aging.csv"})

@reports_bp.route("/export/ap_aging.csv", methods=["GET"])
def export_ap_aging_csv():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    rpt = ap_aging_report(start_date=start, end_date=end)
    rows = []
    for item in rpt.get("data", []):
        row = {
            "supplier": item.get("supplier"),
            "0-30": item.get("buckets", {}).get("0-30", 0),
            "31-60": item.get("buckets", {}).get("31-60", 0),
            "61-90": item.get("buckets", {}).get("61-90", 0),
            "90+": item.get("buckets", {}).get("90+", 0),
            "total": item.get("balance", 0),
        }
        rows.append(row)
    csv_text = _csv_from_rows(rows)
    return Response(csv_text, mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=ap_aging.csv"})

# كشف مفصل للعميل
@reports_bp.route("/customer-detail/<int:customer_id>", methods=["GET"])
@login_required
@permission_required("view_customers")
def customer_detail_report(customer_id):
    """كشف مفصل للعميل يظهر جميع المعاملات"""
    customer = Customer.query.get_or_404(customer_id)

    # تاريخ البداية والنهاية
    start_date = _parse_date(request.args.get("start"))
    end_date = _parse_date(request.args.get("end"))

    # جميع المبيعات
    sales_query = Sale.query.filter(Sale.customer_id == customer_id)
    if start_date:
        sales_query = sales_query.filter(Sale.sale_date >= start_date)
    if end_date:
        sales_query = sales_query.filter(Sale.sale_date <= end_date)
    sales = sales_query.order_by(Sale.sale_date.desc()).all()

    # جميع الفواتير
    invoices_query = Invoice.query.filter(Invoice.customer_id == customer_id)
    if start_date:
        invoices_query = invoices_query.filter(Invoice.invoice_date >= start_date)
    if end_date:
        invoices_query = invoices_query.filter(Invoice.invoice_date <= end_date)
    invoices = invoices_query.order_by(Invoice.invoice_date.desc()).all()

    # جميع طلبات الصيانة
    services_query = ServiceRequest.query.filter(ServiceRequest.customer_id == customer_id)
    if start_date:
        services_query = services_query.filter(ServiceRequest.received_at >= start_date)
    if end_date:
        services_query = services_query.filter(ServiceRequest.received_at <= end_date)
    services = services_query.order_by(ServiceRequest.received_at.desc()).all()

    # جميع المدفوعات
    payments_query = Payment.query.filter(
        Payment.customer_id == customer_id,
        Payment.direction == PaymentDirection.IN.value
    )
    if start_date:
        payments_query = payments_query.filter(Payment.payment_date >= start_date)
    if end_date:
        payments_query = payments_query.filter(Payment.payment_date <= end_date)
    payments = payments_query.order_by(Payment.payment_date.desc()).all()

    # جميع الطلبات المسبقة
    preorders_query = OnlinePreOrder.query.filter(OnlinePreOrder.customer_id == customer_id)
    if start_date:
        preorders_query = preorders_query.filter(OnlinePreOrder.created_at >= start_date)
    if end_date:
        preorders_query = preorders_query.filter(OnlinePreOrder.created_at <= end_date)
    preorders = preorders_query.order_by(OnlinePreOrder.created_at.desc()).all()

    # حساب الإجماليات
    total_sales = sum(float(s.total_amount or 0) for s in sales)
    total_invoices = sum(float(i.total_amount or 0) for i in invoices)
    total_services = sum(float(s.total_amount or 0) for s in services)
    total_payments = sum(float(p.total_amount or 0) for p in payments)
    total_preorders = sum(float(p.total_amount or 0) for p in preorders)

    # الرصيد الحالي
    current_balance = float(customer.balance or 0)

    return render_template(
        "reports/customer_detail.html",
        customer=customer,
        sales=sales,
        invoices=invoices,
        services=services,
        payments=payments,
        preorders=preorders,
        total_sales=total_sales,
        total_invoices=total_invoices,
        total_services=total_services,
        total_payments=total_payments,
        total_preorders=total_preorders,
        current_balance=current_balance,
        start_date=request.args.get("start", ""),
        end_date=request.args.get("end", ""),
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

# كشف مفصل للمورد
@reports_bp.route("/supplier-detail/<int:supplier_id>", methods=["GET"])
@login_required
@permission_required("view_suppliers")
def supplier_detail_report(supplier_id):
    """كشف مفصل للمورد يظهر جميع المعاملات"""
    supplier = Supplier.query.get_or_404(supplier_id)

    # تاريخ البداية والنهاية
    start_date = _parse_date(request.args.get("start"))
    end_date = _parse_date(request.args.get("end"))

    # جميع المدفوعات للمورد
    payments_query = Payment.query.filter(
        Payment.supplier_id == supplier_id,
        Payment.direction == PaymentDirection.OUT.value
    )
    if start_date:
        payments_query = payments_query.filter(Payment.payment_date >= start_date)
    if end_date:
        payments_query = payments_query.filter(Payment.payment_date <= end_date)
    payments = payments_query.order_by(Payment.payment_date.desc()).all()

    # الشحنات - في هذا النظام الشحنات مرتبطة بالشركاء فقط وليس بالموردين
    shipments = []

    # جميع المصاريف المتعلقة بالمورد
    # Expense يستخدم payee_type و payee_entity_id بدلاً من supplier_id مباشرة
    expenses_query = Expense.query.filter(
        Expense.payee_type == 'SUPPLIER',
        Expense.payee_entity_id == supplier_id
    )
    if start_date:
        expenses_query = expenses_query.filter(Expense.date >= start_date)
    if end_date:
        expenses_query = expenses_query.filter(Expense.date <= end_date)
    expenses = expenses_query.order_by(Expense.date.desc()).all()

    # حساب الإجماليات
    total_payments = sum(float(p.total_amount or 0) for p in payments)
    total_shipments = sum(float(s.total_value or 0) for s in shipments)
    total_expenses = sum(float(e.amount or 0) for e in expenses)

    # الرصيد الحالي
    current_balance = float(supplier.balance or 0)

    return render_template(
        "reports/supplier_detail.html",
        supplier=supplier,
        payments=payments,
        shipments=shipments,
        expenses=expenses,
        total_payments=total_payments,
        total_shipments=total_shipments,
        total_expenses=total_expenses,
        current_balance=current_balance,
        start_date=request.args.get("start", ""),
        end_date=request.args.get("end", ""),
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

# كشف مفصل للشريك
@reports_bp.route("/partner-detail/<int:partner_id>", methods=["GET"])
@login_required
@permission_required("view_partners")
def partner_detail_report(partner_id):
    """كشف مفصل للشريك يظهر جميع المعاملات"""
    partner = Partner.query.get_or_404(partner_id)

    # تاريخ البداية والنهاية
    start_date = _parse_date(request.args.get("start"))
    end_date = _parse_date(request.args.get("end"))

    # جميع المدفوعات للشريك
    payments_query = Payment.query.filter(
        Payment.partner_id == partner_id,
        Payment.direction == PaymentDirection.OUT.value
    )
    if start_date:
        payments_query = payments_query.filter(Payment.payment_date >= start_date)
    if end_date:
        payments_query = payments_query.filter(Payment.payment_date <= end_date)
    payments = payments_query.order_by(Payment.payment_date.desc()).all()

    # جميع المبيعات التي شارك فيها الشريك (من خلال PreOrder)
    preorders_query = PreOrder.query.filter(PreOrder.partner_id == partner_id)
    if start_date:
        preorders_query = preorders_query.filter(PreOrder.created_at >= start_date)
    if end_date:
        preorders_query = preorders_query.filter(PreOrder.created_at <= end_date)
    preorders = preorders_query.order_by(PreOrder.created_at.desc()).all()

    # جميع قطع الغيار في طلبات الصيانة التي شارك فيها الشريك
    service_parts_query = ServicePart.query.filter(ServicePart.partner_id == partner_id)
    if start_date:
        service_parts_query = service_parts_query.filter(ServicePart.created_at >= start_date)
    if end_date:
        service_parts_query = service_parts_query.filter(ServicePart.created_at <= end_date)
    service_parts = service_parts_query.order_by(ServicePart.created_at.desc()).all()

    # جميع المبيعات (بدون فلتر partner_id لأن Sale لا يحتوي على هذا الحقل)
    sales = []

    # جميع المصاريف المتعلقة بالشريك
    expenses_query = Expense.query.filter(Expense.partner_id == partner_id)
    if start_date:
        expenses_query = expenses_query.filter(Expense.date >= start_date)
    if end_date:
        expenses_query = expenses_query.filter(Expense.date <= end_date)
    expenses = expenses_query.order_by(Expense.date.desc()).all()

    # حساب الإجماليات
    total_payments = sum(float(p.total_amount or 0) for p in payments)
    total_preorders = sum(float(p.total_amount or 0) for p in preorders)
    total_service_parts = sum(float(sp.quantity * sp.unit_price or 0) for sp in service_parts)
    total_expenses = sum(float(e.amount or 0) for e in expenses)

    # الرصيد الحالي
    current_balance = float(partner.balance or 0)

    # حساب حصة الشريك من الطلبات المسبقة وقطع الغيار
    partner_share = (float(partner.share_percentage or 0) / 100) * (total_preorders + total_service_parts) if partner.share_percentage else 0

    return render_template(
        "reports/partner_detail.html",
        partner=partner,
        payments=payments,
        preorders=preorders,
        service_parts=service_parts,
        expenses=expenses,
        total_payments=total_payments,
        total_preorders=total_preorders,
        total_service_parts=total_service_parts,
        total_expenses=total_expenses,
        partner_share=partner_share,
        current_balance=current_balance,
        start_date=request.args.get("start", ""),
        end_date=request.args.get("end", ""),
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )