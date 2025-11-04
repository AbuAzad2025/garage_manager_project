
from __future__ import annotations
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from werkzeug.exceptions import BadRequest
from flask import Blueprint, Response, flash, jsonify, render_template, request, current_app, redirect, url_for
from sqlalchemy.orm import class_mapper, joinedload
from sqlalchemy import func, cast, Date, desc, or_, and_
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import inspect as sa_inspect
from extensions import db
from flask_login import login_required
import utils
from sqlalchemy.exc import SQLAlchemyError
import inspect as pyinspect

from models import (
    Customer, Supplier, Partner, Product, Warehouse, StockLevel, Expense,
    OnlinePreOrder, OnlinePayment, OnlineCart, Sale, SaleStatus, ServiceRequest, ServiceStatus, InvoiceStatus, Invoice, Payment,
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
# @permission_required("view_inventory")  # Commented out - function not available
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
@login_required
def sales():
    return sales_advanced_report()

@reports_bp.route("/payments-summary", methods=["GET"], strict_slashes=False)
@login_required
def payments_summary():
    return payments_advanced_report()


@reports_bp.route("/invoices", methods=["GET"], strict_slashes=False)
@login_required
def invoices_report():
    from datetime import datetime
    from decimal import Decimal
    
    sd = _parse_date(request.args.get("start_date"))
    ed = _parse_date(request.args.get("end_date"))
    customer_id = request.args.get("customer_id")
    kind = request.args.get("kind")
    status_filter = request.args.get("status")
    
    if sd and ed and ed < sd:
        sd, ed = ed, sd
    
    query = Invoice.query.options(
        joinedload(Invoice.customer),
        joinedload(Invoice.supplier),
        joinedload(Invoice.partner),
        joinedload(Invoice.lines)
    )
    
    if sd:
        start_dt = datetime.combine(sd, datetime.min.time())
        query = query.filter(Invoice.invoice_date >= start_dt)
    if ed:
        end_dt = datetime.combine(ed, datetime.max.time())
        query = query.filter(Invoice.invoice_date <= end_dt)
    if customer_id:
        query = query.filter(Invoice.customer_id == int(customer_id))
    if kind:
        query = query.filter(Invoice.kind == kind)
    if status_filter:
        query = query.filter(Invoice.status == status_filter)
    
    invoices = query.order_by(Invoice.invoice_date.desc()).all()
    
    total_amount = Decimal('0')
    total_paid = Decimal('0')
    balance_due = Decimal('0')
    overdue_count = 0
    credit_notes = 0
    
    today = datetime.now().date()
    for inv in invoices:
        total_amount += Decimal(str(inv.computed_total or 0))
        total_paid += Decimal(str(inv.total_paid or 0))
        balance_due += Decimal(str(inv.computed_total or 0)) - Decimal(str(inv.total_paid or 0))
        
        if inv.due_date and inv.due_date.date() < today and inv.status != 'PAID':
            overdue_count += 1
        if inv.kind == 'CREDIT_NOTE':
            credit_notes += 1
    
    summary = {
        'total_invoices': len(invoices),
        'total_amount': float(total_amount),
        'total_paid': float(total_paid),
        'balance_due': float(balance_due),
        'overdue_count': overdue_count,
        'credit_notes': credit_notes
    }
    
    all_customers = Customer.query.filter_by(is_archived=False).order_by(Customer.name).all()
    
    return render_template(
        "reports/invoices.html",
        invoices=invoices,
        summary=summary,
        all_customers=all_customers
    )


@reports_bp.route("/preorders", methods=["GET"], strict_slashes=False)
@login_required
def preorders_report():
    from datetime import datetime
    from decimal import Decimal
    
    sd = _parse_date(request.args.get("start_date"))
    ed = _parse_date(request.args.get("end_date"))
    customer_id = request.args.get("customer_id")
    status_filter = request.args.get("status")
    
    if sd and ed and ed < sd:
        sd, ed = ed, sd
    
    query = PreOrder.query.options(
        joinedload(PreOrder.customer),
        joinedload(PreOrder.product)
    )
    
    if sd:
        start_dt = datetime.combine(sd, datetime.min.time())
        query = query.filter(PreOrder.preorder_date >= start_dt)
    if ed:
        end_dt = datetime.combine(ed, datetime.max.time())
        query = query.filter(PreOrder.preorder_date <= end_dt)
    if customer_id:
        query = query.filter(PreOrder.customer_id == int(customer_id))
    if status_filter:
        query = query.filter(PreOrder.status == status_filter)
    
    preorders = query.order_by(PreOrder.preorder_date.desc()).all()
    
    total_amount = Decimal('0')
    total_paid = Decimal('0')
    balance_due = Decimal('0')
    
    for pre in preorders:
        total_amount += Decimal(str(pre.total_amount or 0))
        total_paid += Decimal(str(pre.total_paid or 0))
        balance_due += Decimal(str(pre.balance_due or 0))
    
    summary = {
        'total_preorders': len(preorders),
        'total_amount': float(total_amount),
        'total_paid': float(total_paid),
        'balance_due': float(balance_due)
    }
    
    all_customers = Customer.query.filter_by(is_archived=False).order_by(Customer.name).all()
    
    return render_template(
        "reports/preorders.html",
        preorders=preorders,
        summary=summary,
        all_customers=all_customers
    )


@reports_bp.route("/profit-loss", methods=["GET"], strict_slashes=False)
@login_required
def profit_loss_report():
    from datetime import datetime, timedelta
    from decimal import Decimal
    
    sd = _parse_date(request.args.get("start_date"))
    ed = _parse_date(request.args.get("end_date"))
    
    if sd and ed and ed < sd:
        sd, ed = ed, sd
    
    query_sales = Sale.query.filter(Sale.status == 'CONFIRMED')
    query_services = ServiceRequest.query.filter(ServiceRequest.status == 'COMPLETED')
    query_expenses = Expense.query
    
    if sd:
        start_dt = datetime.combine(sd, datetime.min.time())
        query_sales = query_sales.filter(Sale.sale_date >= start_dt)
        query_services = query_services.filter(ServiceRequest.created_at >= start_dt)
        query_expenses = query_expenses.filter(Expense.created_at >= start_dt)
    
    if ed:
        end_dt = datetime.combine(ed, datetime.max.time())
        query_sales = query_sales.filter(Sale.sale_date <= end_dt)
        query_services = query_services.filter(ServiceRequest.created_at <= end_dt)
        query_expenses = query_expenses.filter(Expense.created_at <= end_dt)
    
    sales = query_sales.all()
    services = query_services.all()
    expenses = query_expenses.all()
    
    sales_revenue = sum(Decimal(str(s.total_amount or 0)) for s in sales)
    service_revenue = sum(Decimal(str(s.total_amount or 0)) for s in services)
    other_revenue = Decimal('0')
    
    total_revenue = sales_revenue + service_revenue + other_revenue
    
    operational_expenses = Decimal('0')
    salary_expenses = Decimal('0')
    other_expenses_total = Decimal('0')
    
    for exp in expenses:
        exp_amount = Decimal(str(exp.amount or 0))
        if hasattr(exp, 'expense_type') and exp.expense_type:
            type_name = getattr(exp.expense_type, 'name', '')
            if 'رواتب' in type_name or 'راتب' in type_name:
                salary_expenses += exp_amount
            else:
                operational_expenses += exp_amount
        else:
            other_expenses_total += exp_amount
    
    total_expenses = operational_expenses + salary_expenses + other_expenses_total
    net_profit = total_revenue - total_expenses
    profit_margin = (float(net_profit) / float(total_revenue) * 100) if total_revenue > 0 else 0
    
    data = {
        'total_revenue': float(total_revenue),
        'sales_revenue': float(sales_revenue),
        'service_revenue': float(service_revenue),
        'other_revenue': float(other_revenue),
        'total_expenses': float(total_expenses),
        'operational_expenses': float(operational_expenses),
        'salary_expenses': float(salary_expenses),
        'other_expenses': float(other_expenses_total),
        'net_profit': float(net_profit),
        'profit_margin': profit_margin
    }
    
    return render_template(
        "reports/profit_loss.html",
        data=data,
        start_date=sd.isoformat() if sd else '',
        end_date=ed.isoformat() if ed else ''
    )


@reports_bp.route("/cash-flow", methods=["GET"], strict_slashes=False)
@login_required
def cash_flow_report():
    from datetime import datetime
    from decimal import Decimal
    
    sd = _parse_date(request.args.get("start_date"))
    ed = _parse_date(request.args.get("end_date"))
    
    if sd and ed and ed < sd:
        sd, ed = ed, sd
    
    query_pay_in = Payment.query.filter(
        Payment.direction == PaymentDirection.IN.value,
        Payment.status == PaymentStatus.COMPLETED.value
    )
    query_pay_out = Payment.query.filter(
        Payment.direction == PaymentDirection.OUT.value,
        Payment.status == PaymentStatus.COMPLETED.value
    )
    query_expenses = Expense.query
    
    if sd:
        start_dt = datetime.combine(sd, datetime.min.time())
        query_pay_in = query_pay_in.filter(Payment.created_at >= start_dt)
        query_pay_out = query_pay_out.filter(Payment.created_at >= start_dt)
        query_expenses = query_expenses.filter(Expense.created_at >= start_dt)
    
    if ed:
        end_dt = datetime.combine(ed, datetime.max.time())
        query_pay_in = query_pay_in.filter(Payment.created_at <= end_dt)
        query_pay_out = query_pay_out.filter(Payment.created_at <= end_dt)
        query_expenses = query_expenses.filter(Expense.created_at <= end_dt)
    
    payments_in = query_pay_in.all()
    payments_out = query_pay_out.all()
    expenses = query_expenses.all()
    
    customer_payments = sum(Decimal(str(p.total_amount or 0)) for p in payments_in)
    cash_sales = Decimal('0')
    other_inflow = Decimal('0')
    
    total_inflow = customer_payments + cash_sales + other_inflow
    
    supplier_payments = sum(Decimal(str(p.total_amount or 0)) for p in payments_out)
    
    salaries_paid = Decimal('0')
    expenses_paid = Decimal('0')
    other_outflow = Decimal('0')
    
    for exp in expenses:
        exp_amount = Decimal(str(exp.amount or 0))
        if hasattr(exp, 'expense_type') and exp.expense_type:
            type_name = getattr(exp.expense_type, 'name', '')
            if 'رواتب' in type_name or 'راتب' in type_name:
                salaries_paid += exp_amount
            else:
                expenses_paid += exp_amount
        else:
            other_outflow += exp_amount
    
    total_outflow = supplier_payments + salaries_paid + expenses_paid + other_outflow
    net_cash_flow = total_inflow - total_outflow
    
    data = {
        'total_inflow': float(total_inflow),
        'customer_payments': float(customer_payments),
        'cash_sales': float(cash_sales),
        'other_inflow': float(other_inflow),
        'total_outflow': float(total_outflow),
        'supplier_payments': float(supplier_payments),
        'salaries_paid': float(salaries_paid),
        'expenses_paid': float(expenses_paid),
        'other_outflow': float(other_outflow),
        'net_cash_flow': float(net_cash_flow)
    }
    
    return render_template(
        "reports/cash_flow.html",
        data=data,
        start_date=sd.isoformat() if sd else '',
        end_date=ed.isoformat() if ed else ''
    )


@reports_bp.route("/payments/advanced", methods=["GET"], endpoint="payments_advanced_report")
@login_required
def payments_advanced_report():
    """تقرير المدفوعات الشامل الاحترافي"""
    from decimal import Decimal
    from collections import defaultdict
    
    sd = _parse_date(request.args.get("start_date"))
    ed = _parse_date(request.args.get("end_date"))
    direction_filter = request.args.get("direction")
    method_filter = request.args.get("method")
    status_filter = request.args.get("status")
    
    if sd and ed and ed < sd:
        sd, ed = ed, sd
    
    query = Payment.query.options(
        db.joinedload(Payment.customer),
        db.joinedload(Payment.supplier),
        db.joinedload(Payment.partner)
    )
    
    if sd:
        start_dt = datetime.combine(sd, datetime.min.time())
        query = query.filter(Payment.payment_date >= start_dt)
    if ed:
        end_dt = datetime.combine(ed, datetime.max.time())
        query = query.filter(Payment.payment_date <= end_dt)
    
    if direction_filter:
        query = query.filter(Payment.direction == direction_filter)
    
    if method_filter:
        query = query.filter(Payment.method == method_filter)
    
    if status_filter:
        query = query.filter(Payment.status == status_filter)
    else:
        query = query.filter(Payment.status == PaymentStatus.COMPLETED)
    
    payments = query.order_by(Payment.payment_date.desc()).all()
    
    total_in = Decimal('0.00')
    total_out = Decimal('0.00')
    total_amount = Decimal('0.00')
    completed_count = 0
    method_stats_dict = defaultdict(lambda: Decimal('0.00'))
    
    for payment in payments:
        amount = Decimal(str(payment.total_amount or 0))
        total_amount += amount
        
        if payment.status == PaymentStatus.COMPLETED:
            completed_count += 1
            
        if payment.direction == PaymentDirection.IN:
            total_in += amount
        else:
            total_out += amount
        
        method_key = payment.method.value if payment.method else 'OTHER'
        method_stats_dict[method_key] += amount
    
    method_labels = {
        'CASH': 'نقدي',
        'BANK_TRANSFER': 'تحويل بنكي',
        'CHECK': 'شيك',
        'CREDIT_CARD': 'بطاقة ائتمان',
        'OTHER': 'أخرى'
    }
    
    method_stats = [
        {'method': k, 'label': method_labels.get(k, k), 'total': float(v)}
        for k, v in sorted(method_stats_dict.items(), key=lambda x: x[1], reverse=True)
    ]
    
    summary = {
        'total_payments': len(payments),
        'total_in': float(total_in),
        'total_out': float(total_out),
        'net_flow': float(total_in - total_out),
        'total_amount': float(total_amount),
        'avg_payment': float(total_amount / len(payments)) if len(payments) > 0 else 0,
        'completed_count': completed_count
    }
    
    return render_template(
        "reports/payments_summary.html",
        payments=payments,
        summary=summary,
        method_stats=method_stats,
        show_charts=True,
                         FIELD_LABELS=FIELD_LABELS, 
        MODEL_LABELS=MODEL_LABELS
    )


@reports_bp.route("/payments-summary-old", methods=["GET"], strict_slashes=False)
def payments_summary_old():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    rpt = payment_summary_report_ils(start, end)
    
    # استخراج البيانات من التقرير
    methods = rpt.get("methods", [])
    totals = [float(t) for t in rpt.get("totals_by_method", [])]
    grand_total = sum(totals)
    
    method_labels = {m: METHOD_LABELS_DEFAULT.get(m.upper(), METHOD_LABELS_DEFAULT.get(m, m)) for m in methods}
    return render_template(
        "reports/payments.html",
        methods=methods,
        totals=totals,
        grand_total=grand_total,
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
# @permission_required("view_inventory")  # Commented out - function not available
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
    # استخدام Supplier.balance المحدّث تلقائياً
    q = Supplier.query.order_by(Supplier.name.asc()).all()
    
    data = []
    total_balance = 0
    for supplier in q:
        balance = float(supplier.balance or 0)
        data.append(
            {
                "id": supplier.id,
                "name": supplier.name,
                "balance": balance,
            }
        )
        total_balance += balance
    
    totals = {
        "balance": total_balance,
    }
    return render_template(
        "reports/suppliers.html",
        data=data,
        totals=totals,
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

@reports_bp.route("/partners", methods=["GET"], endpoint="partners_report")
def partners_report():
    q = Partner.query.order_by(Partner.name.asc()).all()
    
    data = []
    total_balance = 0
    total_paid = 0
    for partner in q:
        balance = float(partner.balance or 0)
        share = float(partner.share_percentage or 0)
        paid = 0
        data.append(
            {
                "id": partner.id,
                "name": partner.name,
                "balance": balance,
                "total_paid": paid,
                "net_balance": balance - paid,
                "share_percentage": share,
            }
        )
        total_balance += balance
        total_paid += paid
    
    totals = {
        "balance": total_balance,
        "total_paid": total_paid,
        "net_balance": total_balance - total_paid,
    }
    return render_template(
        "reports/partners.html",
        data=data,
        totals=totals,
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

@reports_bp.route("/customers", methods=["GET"], endpoint="customers_report")
@login_required
def customers_report():
    return customers_advanced_report()


@reports_bp.route("/customers/advanced", methods=["GET"], endpoint="customers_advanced_report")
@login_required
def customers_advanced_report():
    """تقرير العملاء الشامل الاحترافي"""
    from decimal import Decimal
    from models import convert_amount
    from sqlalchemy import or_
    
    search = request.args.get('search', '').strip()
    balance_status = request.args.get('balance_status', '')
    
    query = Customer.query
    
    if search:
        query = query.filter(
            or_(
                Customer.name.ilike(f'%{search}%'),
                Customer.phone.ilike(f'%{search}%'),
                Customer.email.ilike(f'%{search}%')
            )
        )
    
    all_customers = query.all()
    customers_data = []
    
    total_invoiced_sum = Decimal('0.00')
    total_paid_sum = Decimal('0.00')
    total_invoices_count = 0
    
    for cust in all_customers:
        invoiced_ils = Decimal('0.00')
        paid_ils = Decimal('0.00')
        invoice_count = 0
        last_transaction = None
        
        invoices = db.session.query(Invoice).filter(
            Invoice.customer_id == cust.id,
            Invoice.cancelled_at.is_(None)
        ).all()
        invoice_count += len(invoices)
        for inv in invoices:
            amt = Decimal(str(inv.total_amount or 0))
            invoiced_ils += amt
            if not last_transaction or (inv.invoice_date and inv.invoice_date > last_transaction):
                last_transaction = inv.invoice_date
        
        sales = db.session.query(Sale).filter(
            Sale.customer_id == cust.id,
            Sale.status == SaleStatus.CONFIRMED
        ).all()
        invoice_count += len(sales)
        for s in sales:
            amt = Decimal(str(s.total_amount or 0))
            invoiced_ils += amt
            if not last_transaction or (s.sale_date and s.sale_date > last_transaction):
                last_transaction = s.sale_date
        
        services = db.session.query(ServiceRequest).filter(
            ServiceRequest.customer_id == cust.id
        ).all()
        invoice_count += len(services)
        for srv in services:
            amt = Decimal(str(srv.total_amount or 0))
            invoiced_ils += amt
            if not last_transaction or (srv.received_at and srv.received_at > last_transaction):
                last_transaction = srv.received_at
        
        payments = db.session.query(Payment).filter(
            Payment.customer_id == cust.id,
            Payment.direction == PaymentDirection.IN.value,
            Payment.status == PaymentStatus.COMPLETED.value
        ).all()
        for p in payments:
            amt = Decimal(str(p.total_amount or 0))
            paid_ils += amt
            if not last_transaction or (p.payment_date and p.payment_date > last_transaction):
                last_transaction = p.payment_date
        
        balance = invoiced_ils - paid_ils
        
        if balance_status == 'debit' and balance <= 0:
            continue
        elif balance_status == 'credit' and balance >= 0:
            continue
        elif balance_status == 'zero' and balance != 0:
            continue
        
        if invoiced_ils != 0 or paid_ils != 0:
            total_invoiced_sum += invoiced_ils
            total_paid_sum += paid_ils
            total_invoices_count += invoice_count
            
            customers_data.append({
                'id': cust.id,
                'name': cust.name,
                'phone': cust.phone or '',
                'email': cust.email or '',
                'stats': {
                    'total_invoiced': float(invoiced_ils),
                    'total_paid': float(paid_ils),
                    'invoice_count': invoice_count,
                    'last_transaction': last_transaction
                }
            })
    
    customers_data.sort(key=lambda x: x['stats']['total_invoiced'] - x['stats']['total_paid'], reverse=True)
    
    summary = {
        'total_customers': len(customers_data),
        'total_invoiced': float(total_invoiced_sum),
        'total_paid': float(total_paid_sum),
        'total_balance': float(total_invoiced_sum - total_paid_sum),
        'avg_invoice': float(total_invoiced_sum / len(customers_data)) if len(customers_data) > 0 else 0,
        'payment_ratio': float(total_paid_sum / total_invoiced_sum * 100) if total_invoiced_sum > 0 else 0,
        'total_invoices': total_invoices_count
    }
    
    top_customers = sorted(customers_data, key=lambda x: x['stats']['total_invoiced'], reverse=True)[:5]
    
    all_customers_data = []
    for c in customers_data:
        all_customers_data.append({
            'id': c['id'],
            'name': c['name'],
            'phone': c['phone'],
            'email': c['email'],
            'total_invoiced': c['stats']['total_invoiced'],
            'total_paid': c['stats']['total_paid'],
            'balance': c['stats']['total_invoiced'] - c['stats']['total_paid'],
        })
    
    return render_template(
        "reports/customers.html",
        data=all_customers_data,
        totals={
            'invoiced': summary['total_invoiced'],
            'paid': summary['total_paid'],
            'balance': summary['total_balance']
        },
        start=request.args.get("start_date", ""),
        end=request.args.get("end_date", ""),
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS
    )


@reports_bp.route("/sales/advanced", methods=["GET"], endpoint="sales_advanced_report")
@login_required
def sales_advanced_report():
    """تقرير المبيعات الشامل الاحترافي"""
    from decimal import Decimal
    from collections import defaultdict
    from sqlalchemy.orm import joinedload
    
    sd = _parse_date(request.args.get("start_date"))
    ed = _parse_date(request.args.get("end_date"))
    customer_id = request.args.get("customer_id")
    status_filter = request.args.get("status")
    
    if sd and ed and ed < sd:
        sd, ed = ed, sd
    
    query = Sale.query.options(
        joinedload(Sale.customer),
        joinedload(Sale.lines)
    )
    
    if sd:
        start_dt = datetime.combine(sd, datetime.min.time())
        query = query.filter(Sale.sale_date >= start_dt)
    if ed:
        end_dt = datetime.combine(ed, datetime.max.time())
        query = query.filter(Sale.sale_date <= end_dt)
    
    if customer_id:
        try:
            query = query.filter(Sale.customer_id == int(customer_id))
        except:
            pass
    
    if status_filter:
        query = query.filter(Sale.status == status_filter)
    else:
        query = query.filter(Sale.status == SaleStatus.CONFIRMED)
    
    sales = query.order_by(Sale.sale_date.desc()).all()
    
    total_revenue = Decimal('0.00')
    total_items = 0
    total_quantity = 0
    daily_sales_dict = defaultdict(lambda: Decimal('0.00'))
    product_sales_dict = defaultdict(lambda: {'quantity': 0, 'revenue': Decimal('0.00')})
    
    for sale in sales:
        total_revenue += Decimal(str(sale.total_amount or 0))
        total_items += len(sale.lines)
        
        for line in sale.lines:
            total_quantity += line.quantity or 0
            line_amount = Decimal(str(line.net_amount or 0))
            
            if sale.sale_date:
                date_key = sale.sale_date.date().isoformat()
                daily_sales_dict[date_key] += line_amount
            
            if line.product:
                product_sales_dict[line.product.id]['name'] = line.product.name
                product_sales_dict[line.product.id]['quantity'] += line.quantity or 0
                product_sales_dict[line.product.id]['revenue'] += line_amount
    
    summary = {
        'total_sales': len(sales),
        'total_revenue': float(total_revenue),
        'avg_sale': float(total_revenue / len(sales)) if len(sales) > 0 else 0,
        'total_items': total_items,
        'total_quantity': total_quantity,
        'avg_item_value': float(total_revenue / total_items) if total_items > 0 else 0
    }
    
    daily_sales = [{'date': d, 'total': float(v)} for d, v in sorted(daily_sales_dict.items())]
    
    top_products = sorted([
        {'id': pid, 'name': pdata.get('name', 'منتج'), 'quantity': pdata['quantity'], 'revenue': float(pdata['revenue'])}
        for pid, pdata in product_sales_dict.items()
    ], key=lambda x: x['revenue'], reverse=True)[:5]
    
    all_customers = Customer.query.order_by(Customer.name).all()
    
    return render_template(
        "reports/sales.html",
        sales=sales,
        summary=summary,
        daily_sales=daily_sales,
        top_products=top_products,
        all_customers=all_customers,
        show_charts=True,
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS
    )


@reports_bp.route("/expenses", methods=["GET"], endpoint="expenses_report")
def expenses_report():
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    tab = (request.args.get("tab") or "expenses").strip()
    
    # فلاتر إضافية
    expense_type = (request.args.get("type") or "").strip()  # نوع المصروف (id أو اسم)
    employee_id = request.args.get("employee_id")  # الموظف (Employee.id)
    warehouse_id = request.args.get("warehouse_id")  # المستودع (Warehouse.id)
    partner_id = request.args.get("partner_id")  # الشريك (Partner.id)
    is_paid = request.args.get("is_paid")  # حالة الدفع
    
    q = Expense.query
    if start:
        q = q.filter(Expense.date >= start)
    if end:
        q = q.filter(Expense.date <= end)
    
    # تطبيق الفلاتر الإضافية
    if expense_type:
        # دعم الفلترة بالمعرّف أو الاسم
        from models import ExpenseType as _ET
        try:
            et_id = int(expense_type)
            q = q.filter(Expense.type_id == et_id)
        except Exception:
            q = q.join(_ET, Expense.type_id == _ET.id).filter(_ET.name.ilike(f"%{expense_type}%"))
    if employee_id:
        try:
            q = q.filter(Expense.employee_id == int(employee_id))
        except Exception:
            pass
    if warehouse_id:
        try:
            q = q.filter(Expense.warehouse_id == int(warehouse_id))
        except Exception:
            pass
    if partner_id:
        try:
            q = q.filter(Expense.partner_id == int(partner_id))
        except Exception:
            pass
    if is_paid in ['true', '1']:
        q = q.filter(Expense.is_paid == True)
    elif is_paid in ['false', '0']:
        q = q.filter(Expense.is_paid == False)
    
    q = q.order_by(Expense.date.desc())
    rows = q.all()
    total = sum(float(e.amount or 0) for e in rows)
    
    # تجميع حسب النوع
    type_labels, type_values = [], []
    by_type = {}
    for e in rows:
        k = e.type_id or "غير محدد"
        by_type[k] = by_type.get(k, 0) + float(e.amount or 0)
    for k, v in by_type.items():
        type_labels.append(str(k))
        type_values.append(v)
    
    # تجميع حسب الموظف
    emp_labels, emp_values = [], []
    by_emp = {}
    for e in rows:
        k = e.employee_id or "غير محدد"
        by_emp[k] = by_emp.get(k, 0) + float(e.amount or 0)
    for k, v in by_emp.items():
        emp_labels.append(str(k))
        emp_values.append(v)
    
    # جلب قوائم للفلاتر
    from models import Employee, Warehouse, Partner, ExpenseType
    employees = Employee.query.order_by(Employee.name).all()
    warehouses = Warehouse.query.order_by(Warehouse.name).all()
    partners = Partner.query.order_by(Partner.name).all()
    expense_types = ExpenseType.query.filter_by(is_active=True).order_by(ExpenseType.name).all()
    
    # تبويب المقبوضات حسب الجامع (المستخدم)
    receipts_rows = []
    receipts_total = 0.0
    if tab == "receipts":
        from models import User
        pq = db.session.query(
            Payment.created_by.label("uid"),
            func.coalesce(func.count(Payment.id), 0).label("count"),
            func.coalesce(func.sum(Payment.total_amount), 0).label("total")
        ).filter(
            Payment.direction == PaymentDirection.IN.value,
            Payment.status == PaymentStatus.COMPLETED.value
        )
        if start:
            pq = pq.filter(Payment.payment_date >= start)
        if end:
            pq = pq.filter(Payment.payment_date <= end)
        pq = pq.group_by(Payment.created_by)
        agg = pq.all()
        # جلب أسماء المستخدمين دفعة واحدة
        uid_to_name = {}
        if agg:
            uids = [r.uid for r in agg if r.uid]
            if uids:
                users = db.session.query(User.id, User.username).filter(User.id.in_(uids)).all()
                uid_to_name = {u.id: u.username for u in users}
        receipts_rows = [
            {
                "user_id": r.uid or 0,
                "user_name": uid_to_name.get(r.uid or 0, "—"),
                "payments_count": int(r.count or 0),
                "total_amount": float(r.total or 0),
            }
            for r in agg
        ]
        receipts_total = sum(x["total_amount"] for x in receipts_rows)

    # تصدير CSV عند الطلب
    if (request.args.get("export") or "").lower() == "csv":
        if tab == "receipts":
            csv_text = _csv_from_rows([
                {
                    "user_id": row.get("user_id"),
                    "user_name": row.get("user_name"),
                    "payments_count": row.get("payments_count"),
                    "total_amount": row.get("total_amount"),
                }
                for row in receipts_rows
            ])
            return Response(csv_text, mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=receipts_by_user.csv"})
        # بناء صفوف مشابهة لجدول العرض
        csv_rows = []
        for e in rows:
            csv_rows.append({
                "id": e.id,
                "date": (e.date.strftime('%Y-%m-%d') if getattr(e, 'date', None) else ''),
                "type": (e.type.name if getattr(e, 'type', None) else e.type_id),
                "amount": float(e.amount or 0),
                "currency": e.currency or '',
                "employee": (e.employee.name if getattr(e, 'employee', None) else ''),
                "warehouse": (e.warehouse.name if getattr(e, 'warehouse', None) else ''),
                "partner": (e.partner.name if getattr(e, 'partner', None) else ''),
                "description": getattr(e, 'desc', None) or getattr(e, 'description', '') or '',
                "is_paid": 'YES' if getattr(e, 'is_paid', False) else 'NO',
            })
        csv_text = _csv_from_rows(csv_rows)
        return Response(csv_text, mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=expenses.csv"})

    return render_template(
        "reports/expenses.html",
        data=rows,
        total_amount=total,
        start=request.args.get("start", ""),
        end=request.args.get("end", ""),
        tab=tab,
        selected_type=expense_type or "",
        selected_employee_id=int(employee_id) if employee_id else None,
        selected_warehouse_id=int(warehouse_id) if warehouse_id else None,
        selected_partner_id=int(partner_id) if partner_id else None,
        selected_is_paid=is_paid or "",
        employees=employees,
        warehouses=warehouses,
        partners=partners,
        expense_types=expense_types,
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
        type_labels=type_labels,
        type_values=type_values,
        emp_labels=emp_labels,
        emp_values=emp_values,
        receipts_rows=receipts_rows,
        receipts_total=receipts_total,
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
# @permission_required("view_customers")  # Commented out - function not available
def customer_detail_report(customer_id):
    """كشف مفصل للعميل يظهر جميع المعاملات"""
    customer = Customer.query.get_or_404(customer_id)

    # تاريخ البداية والنهاية
    start_date = _parse_date(request.args.get("start"))
    end_date = _parse_date(request.args.get("end"))

    # جميع المبيعات - ⚡ محسّن بـ eager loading
    sales_query = Sale.query.filter(Sale.customer_id == customer_id).options(
        joinedload(Sale.lines).joinedload(SaleLine.product),
        joinedload(Sale.lines).joinedload(SaleLine.warehouse),
        joinedload(Sale.payments)
    )
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

    # جميع طلبات الصيانة - ⚡ محسّن بـ eager loading
    services_query = ServiceRequest.query.filter(ServiceRequest.customer_id == customer_id).options(
        joinedload(ServiceRequest.parts).joinedload(ServicePart.part),
        joinedload(ServiceRequest.parts).joinedload(ServicePart.warehouse),
        joinedload(ServiceRequest.tasks),
        joinedload(ServiceRequest.payments)
    )
    if start_date:
        services_query = services_query.filter(ServiceRequest.received_at >= start_date)
    if end_date:
        services_query = services_query.filter(ServiceRequest.received_at <= end_date)
    services = services_query.order_by(ServiceRequest.received_at.desc()).all()

    # جميع المدفوعات (نشطة + مؤرشفة للرصيد المحاسبي الحقيقي)
    payments_query = Payment.query.filter(
        Payment.customer_id == customer_id,
        Payment.direction == PaymentDirection.IN.value,
        Payment.status == PaymentStatus.COMPLETED.value  # ✅ فلترة الدفعات المكتملة فقط
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
    total_sales = Decimal('0.00')
    for s in sales:
        amt = Decimal(str(s.total_amount or 0))
        if s.currency and s.currency != "ILS":
            try:
                amt = convert_amount(amt, s.currency, "ILS", s.sale_date)
            except:
                pass
        total_sales += amt
    
    total_invoices = Decimal('0.00')
    for i in invoices:
        amt = Decimal(str(i.total_amount or 0))
        if i.currency and i.currency != "ILS":
            try:
                amt = convert_amount(amt, i.currency, "ILS", i.invoice_date)
            except:
                pass
        total_invoices += amt
    
    total_services = Decimal('0.00')
    for s in services:
        amt = Decimal(str(s.total_amount or 0))
        if s.currency and s.currency != "ILS":
            try:
                amt = convert_amount(amt, s.currency, "ILS", s.received_at)
            except:
                pass
        total_services += amt
    
    total_payments = Decimal('0.00')
    for p in payments:
        amt = Decimal(str(p.total_amount or 0))
        if p.currency and p.currency != "ILS":
            try:
                amt = convert_amount(amt, p.currency, "ILS", p.payment_date)
            except:
                pass
        total_payments += amt
    
    total_preorders = Decimal('0.00')
    for p in preorders:
        amt = Decimal(str(p.total_amount or 0))
        if hasattr(p, 'currency') and p.currency and p.currency != "ILS":
            try:
                amt = convert_amount(amt, p.currency, "ILS", p.created_at)
            except:
                pass
        total_preorders += amt

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
# @permission_required("view_suppliers")  # Commented out - function not available
def supplier_detail_report(supplier_id):
    """كشف مفصل للمورد يظهر جميع المعاملات"""
    supplier = Supplier.query.get_or_404(supplier_id)

    # تاريخ البداية والنهاية
    start_date = _parse_date(request.args.get("start"))
    end_date = _parse_date(request.args.get("end"))

    # جميع الدفعات (OUT و IN)
    payments_out_query = Payment.query.options(
        joinedload(Payment.sale)
    ).filter(
        Payment.supplier_id == supplier_id,
        Payment.direction == PaymentDirection.OUT.value,
        Payment.status == PaymentStatus.COMPLETED.value
    )
    if start_date:
        payments_out_query = payments_out_query.filter(Payment.payment_date >= start_date)
    if end_date:
        payments_out_query = payments_out_query.filter(Payment.payment_date <= end_date)
    payments_out = payments_out_query.order_by(Payment.payment_date.desc()).all()
    
    payments_in_query = Payment.query.options(
        joinedload(Payment.sale)
    ).filter(
        Payment.supplier_id == supplier_id,
        Payment.direction == PaymentDirection.IN.value,
        Payment.status == PaymentStatus.COMPLETED.value
    )
    if start_date:
        payments_in_query = payments_in_query.filter(Payment.payment_date >= start_date)
    if end_date:
        payments_in_query = payments_in_query.filter(Payment.payment_date <= end_date)
    payments_in = payments_in_query.order_by(Payment.payment_date.desc()).all()

    # حركات التوريد (ExchangeTransaction)
    from models import ExchangeTransaction
    exchange_query = ExchangeTransaction.query.options(
        joinedload(ExchangeTransaction.product)
    ).filter(
        ExchangeTransaction.supplier_id == supplier_id
    )
    if start_date:
        exchange_query = exchange_query.filter(ExchangeTransaction.created_at >= start_date)
    if end_date:
        exchange_query = exchange_query.filter(ExchangeTransaction.created_at <= end_date)
    exchange_transactions = exchange_query.order_by(ExchangeTransaction.created_at.desc()).all()

    # المبيعات للمورد (كعميل)
    sales = []
    if supplier.customer_id:
        from models import Sale, SaleStatus, SaleLine
        sales_query = Sale.query.options(
            joinedload(Sale.lines).joinedload(SaleLine.product)
        ).filter(
            Sale.customer_id == supplier.customer_id,
            Sale.status == SaleStatus.CONFIRMED.value
        )
        if start_date:
            sales_query = sales_query.filter(Sale.sale_date >= start_date)
        if end_date:
            sales_query = sales_query.filter(Sale.sale_date <= end_date)
        sales = sales_query.order_by(Sale.sale_date.desc()).all()

    # الصيانة للمورد (كعميل)
    services = []
    if supplier.customer_id:
        from models import ServiceRequest, ServicePart, ServiceTask
        services_query = ServiceRequest.query.options(
            joinedload(ServiceRequest.parts),
            joinedload(ServiceRequest.tasks)
        ).filter(
            ServiceRequest.customer_id == supplier.customer_id,
            ServiceRequest.status == ServiceStatus.COMPLETED.value
        )
        if start_date:
            services_query = services_query.filter(ServiceRequest.received_at >= start_date)
        if end_date:
            services_query = services_query.filter(ServiceRequest.received_at <= end_date)
        services = services_query.order_by(ServiceRequest.received_at.desc()).all()

    # الحجوزات المسبقة للمورد (كعميل)
    preorders = []
    if supplier.customer_id:
        preorders_query = PreOrder.query.options(
            joinedload(PreOrder.product)
        ).filter(
            PreOrder.customer_id == supplier.customer_id,
            PreOrder.status.in_(['CONFIRMED', 'COMPLETED'])
        )
        if start_date:
            preorders_query = preorders_query.filter(PreOrder.preorder_date >= start_date)
        if end_date:
            preorders_query = preorders_query.filter(PreOrder.preorder_date <= end_date)
        preorders = preorders_query.order_by(PreOrder.preorder_date.desc()).all()

    # جميع المصاريف المتعلقة بالمورد
    expenses_query = Expense.query.filter(
        or_(
            Expense.supplier_id == supplier_id,
            and_(Expense.payee_type == 'SUPPLIER', Expense.payee_entity_id == supplier_id)
        )
    )
    if start_date:
        expenses_query = expenses_query.filter(Expense.date >= start_date)
    if end_date:
        expenses_query = expenses_query.filter(Expense.date <= end_date)
    expenses = expenses_query.order_by(Expense.date.desc()).all()

    # استخدام التسوية الذكية
    from routes.supplier_settlements import _calculate_smart_supplier_balance
    from datetime import datetime
    
    date_from = start_date if start_date else datetime(2024, 1, 1)
    date_to = end_date if end_date else datetime.now()
    
    try:
        balance_data = _calculate_smart_supplier_balance(supplier_id, date_from, date_to)
    except Exception as e:
        balance_data = {"success": False, "error": str(e)}
    
    # حساب الإجماليات
    from decimal import Decimal
    
    if balance_data and balance_data.get("success"):
        total_exchange_in = Decimal(str(balance_data.get("rights", {}).get("exchange_items", {}).get("total_value_ils", 0)))
        total_payments_out = Decimal(str(balance_data.get("payments", {}).get("total_paid", 0)))
        total_payments_in = Decimal(str(balance_data.get("payments", {}).get("total_received", 0)))
        total_obligations = Decimal(str(balance_data.get("obligations", {}).get("total", 0)))
    else:
        total_payments_out = sum(Decimal(str(p.total_amount or 0)) for p in payments_out)
        total_payments_in = sum(Decimal(str(p.total_amount or 0)) for p in payments_in)
        total_exchange_in = sum(Decimal(str((tx.quantity or 0) * (tx.unit_cost or 0))) for tx in exchange_transactions if tx.direction in ['IN', 'PURCHASE', 'CONSIGN_IN'])
        total_obligations = Decimal('0.00')
    
    total_exchange_out = sum(Decimal(str((tx.quantity or 0) * (tx.unit_cost or 0))) for tx in exchange_transactions if tx.direction in ['OUT', 'RETURN', 'CONSIGN_OUT'])
    total_sales = sum(Decimal(str(s.total_amount or 0)) for s in sales)
    total_services = sum(Decimal(str(s.total_amount or 0)) for s in services)
    total_preorders = sum(Decimal(str(p.total_amount or 0)) for p in preorders)
    
    total_expenses = Decimal('0.00')
    for e in expenses:
        amt = Decimal(str(e.amount or 0))
        if e.currency and e.currency != "ILS":
            try:
                amt = convert_amount(amt, e.currency, "ILS", e.date)
            except:
                pass
        total_expenses += amt

    # الرصيد الحالي
    current_balance = float(supplier.balance or 0)

    return render_template(
        "reports/supplier_detail.html",
        supplier=supplier,
        payments_out=payments_out,
        payments_in=payments_in,
        exchange_transactions=exchange_transactions,
        sales=sales,
        services=services,
        preorders=preorders,
        expenses=expenses,
        balance_data=balance_data,
        total_payments_out=float(total_payments_out),
        total_payments_in=float(total_payments_in),
        total_exchange_in=float(total_exchange_in),
        total_exchange_out=float(total_exchange_out),
        total_sales=float(total_sales),
        total_services=float(total_services),
        total_preorders=float(total_preorders),
        total_expenses=float(total_expenses),
        total_obligations=float(total_obligations),
        current_balance=current_balance,
        start_date=request.args.get("start", ""),
        end_date=request.args.get("end", ""),
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )

# كشف مفصل للشريك
@reports_bp.route("/partner-detail/<int:partner_id>", methods=["GET"])
@login_required
# @permission_required("view_partners")  # Commented out - function not available
def partner_detail_report(partner_id):
    """كشف مفصل للشريك يظهر جميع المعاملات"""
    partner = Partner.query.get_or_404(partner_id)

    # تاريخ البداية والنهاية
    start_date = _parse_date(request.args.get("start"))
    end_date = _parse_date(request.args.get("end"))

    # جميع الدفعات (OUT و IN)
    payments_out_query = Payment.query.options(
        joinedload(Payment.sale)
    ).filter(
        Payment.partner_id == partner_id,
        Payment.direction == PaymentDirection.OUT.value,
        Payment.status == PaymentStatus.COMPLETED.value
    )
    if start_date:
        payments_out_query = payments_out_query.filter(Payment.payment_date >= start_date)
    if end_date:
        payments_out_query = payments_out_query.filter(Payment.payment_date <= end_date)
    payments_out = payments_out_query.order_by(Payment.payment_date.desc()).all()
    
    payments_in_query = Payment.query.options(
        joinedload(Payment.sale)
    ).filter(
        Payment.partner_id == partner_id,
        Payment.direction == PaymentDirection.IN.value,
        Payment.status == PaymentStatus.COMPLETED.value
    )
    if start_date:
        payments_in_query = payments_in_query.filter(Payment.payment_date >= start_date)
    if end_date:
        payments_in_query = payments_in_query.filter(Payment.payment_date <= end_date)
    payments_in = payments_in_query.order_by(Payment.payment_date.desc()).all()

    # المبيعات للشريك (كعميل)
    sales = []
    if partner.customer_id:
        from models import Sale, SaleStatus, SaleLine
        sales_query = Sale.query.options(
            joinedload(Sale.lines).joinedload(SaleLine.product)
        ).filter(
            Sale.customer_id == partner.customer_id,
            Sale.status == SaleStatus.CONFIRMED.value
        )
        if start_date:
            sales_query = sales_query.filter(Sale.sale_date >= start_date)
        if end_date:
            sales_query = sales_query.filter(Sale.sale_date <= end_date)
        sales = sales_query.order_by(Sale.sale_date.desc()).all()

    # الصيانة للشريك (كعميل)
    services = []
    if partner.customer_id:
        from models import ServiceRequest, ServicePart, ServiceTask
        services_query = ServiceRequest.query.options(
            joinedload(ServiceRequest.parts),
            joinedload(ServiceRequest.tasks)
        ).filter(
            ServiceRequest.customer_id == partner.customer_id,
            ServiceRequest.status == ServiceStatus.COMPLETED.value
        )
        if start_date:
            services_query = services_query.filter(ServiceRequest.received_at >= start_date)
        if end_date:
            services_query = services_query.filter(ServiceRequest.received_at <= end_date)
        services = services_query.order_by(ServiceRequest.received_at.desc()).all()

    # الحجوزات المسبقة التي شارك فيها الشريك
    preorders_query = PreOrder.query.options(
        joinedload(PreOrder.product)
    ).filter(PreOrder.partner_id == partner_id)
    if start_date:
        preorders_query = preorders_query.filter(PreOrder.created_at >= start_date)
    if end_date:
        preorders_query = preorders_query.filter(PreOrder.created_at <= end_date)
    preorders = preorders_query.order_by(PreOrder.created_at.desc()).all()

    # قطع الغيار في طلبات الصيانة التي شارك فيها الشريك
    service_parts_query = ServicePart.query.options(
        joinedload(ServicePart.part),
        joinedload(ServicePart.request)
    ).filter(ServicePart.partner_id == partner_id)
    if start_date:
        service_parts_query = service_parts_query.filter(ServicePart.created_at >= start_date)
    if end_date:
        service_parts_query = service_parts_query.filter(ServicePart.created_at <= end_date)
    service_parts = service_parts_query.order_by(ServicePart.created_at.desc()).all()

    # جميع المصاريف المتعلقة بالشريك
    expenses_query = Expense.query.filter(
        or_(
            Expense.partner_id == partner_id,
            and_(Expense.payee_type == 'PARTNER', Expense.payee_entity_id == partner_id)
        )
    )
    if start_date:
        expenses_query = expenses_query.filter(Expense.date >= start_date)
    if end_date:
        expenses_query = expenses_query.filter(Expense.date <= end_date)
    expenses = expenses_query.order_by(Expense.date.desc()).all()
    
    # ✅ استخدام التسوية الذكية للحصول على بيانات دقيقة
    from routes.partner_settlements import _calculate_smart_partner_balance
    from datetime import datetime
    
    date_from = start_date if start_date else datetime(2024, 1, 1)
    date_to = end_date if end_date else datetime.now()
    
    try:
        balance_data = _calculate_smart_partner_balance(partner_id, date_from, date_to)
    except Exception as e:
        balance_data = {"success": False, "error": str(e)}

    # حساب الإجماليات من البيانات الذكية
    from decimal import Decimal
    
    if balance_data and balance_data.get("success"):
        total_inventory = Decimal(str(balance_data.get("rights", {}).get("inventory", {}).get("total_ils", 0)))
        total_sales_share = Decimal(str(balance_data.get("rights", {}).get("sales", {}).get("total_ils", 0)))
        total_payments_out = Decimal(str(balance_data.get("payments", {}).get("total_paid", 0)))
        total_payments_in = Decimal(str(balance_data.get("payments", {}).get("total_received", 0)))
        total_obligations = Decimal(str(balance_data.get("obligations", {}).get("total", 0)))
        inventory = balance_data.get("rights", {}).get("inventory", {}).get("items", [])
    else:
        # fallback للطريقة القديمة
        total_payments_out = sum(Decimal(str(p.total_amount or 0)) for p in payments_out)
        total_payments_in = sum(Decimal(str(p.total_amount or 0)) for p in payments_in)
        total_inventory = Decimal('0.00')
        total_sales_share = Decimal('0.00')
        total_obligations = Decimal('0.00')
        inventory = []
    
    total_sales = sum(Decimal(str(s.total_amount or 0)) for s in sales)
    total_services = sum(Decimal(str(s.total_amount or 0)) for s in services)
    total_preorders = sum(Decimal(str(p.total_amount or 0)) for p in preorders)
    total_service_parts = sum(Decimal(str(sp.quantity * sp.unit_price or 0)) for sp in service_parts)
    
    total_expenses = Decimal('0.00')
    for e in expenses:
        amt = Decimal(str(e.amount or 0))
        if e.currency and e.currency != "ILS":
            try:
                amt = convert_amount(amt, e.currency, "ILS", e.date)
            except:
                pass
        total_expenses += amt

    # الرصيد الحالي
    current_balance = float(partner.balance or 0)

    # حساب حصة الشريك
    partner_share = (float(partner.share_percentage or 0) / 100) * (float(total_preorders) + float(total_service_parts)) if partner.share_percentage else 0

    return render_template(
        "reports/partner_detail.html",
        partner=partner,
        payments_out=payments_out,
        payments_in=payments_in,
        sales=sales,
        services=services,
        preorders=preorders,
        service_parts=service_parts,
        expenses=expenses,
        inventory=inventory,
        balance_data=balance_data,  # ✅ إضافة البيانات الذكية
        total_payments_out=float(total_payments_out),
        total_payments_in=float(total_payments_in),
        total_sales=float(total_sales),
        total_services=float(total_services),
        total_preorders=float(total_preorders),
        total_service_parts=float(total_service_parts),
        total_expenses=float(total_expenses),
        total_inventory=float(total_inventory),
        total_sales_share=float(total_sales_share),  # ✅ نصيب المبيعات
        total_obligations=float(total_obligations),   # ✅ الالتزامات
        partner_share=partner_share,
        current_balance=current_balance,
        start_date=request.args.get("start", ""),
        end_date=request.args.get("end", ""),
        FIELD_LABELS=FIELD_LABELS,
        MODEL_LABELS=MODEL_LABELS,
    )