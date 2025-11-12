
# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from datetime import datetime
import math
from typing import Any, Dict, Iterable, Optional, List, Tuple
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for, abort, current_app, Response
from flask_login import current_user, login_required
from sqlalchemy import func, or_, desc, extract, case, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from extensions import db
from models import Sale, SaleLine, Invoice, Customer, Product, AuditLog, Warehouse, User, Payment, StockLevel
from forms import SaleForm
import utils
from utils import D, line_total_decimal, money_fmt, archive_record, restore_record  # Import from utils package
from decimal import Decimal, ROUND_HALF_UP

# تعريف TWOPLACES للتقريب العشري
TWOPLACES = Decimal('0.01')

sales_bp = Blueprint("sales_bp", __name__, url_prefix="/sales", template_folder="templates/sales")

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
    if getattr(s, "seller_employee", None):
        s.seller_name = s.seller_employee.name or "-"
    elif getattr(s, "seller", None):
        s.seller_name = getattr(s.seller, "username", None) or getattr(s.seller, "name", None) or "-"
    else:
        s.seller_name = "-"
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
        "seller_employee_id": s.seller_employee_id,
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
            # إنشاء StockLevel جديد إذا لم يكن موجوداً
            rec = StockLevel(product_id=pid, warehouse_id=wid, quantity=0, reserved_quantity=0)
            db.session.add(rec)
            try:
                db.session.flush()
            except Exception as e:
                current_app.logger.error(f"خطأ في إنشاء StockLevel: {str(e)}")
                raise ValueError(f"لا يمكن حجز المخزون للمنتج {pid} في المستودع {wid}")
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

def _deduct_stock(sale: Sale) -> None:
    """
    خصم المخزون الفعلي عند اكتمال البيع/الدفع
    يخصم من quantity و reserved_quantity معاً
    """
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
        
        # خصم من الكمية الفعلية
        new_quantity = max(0, int(rec.quantity or 0) - qty)
        
        # خصم من الكمية المحجوزة أيضاً
        current_reserved = int(rec.reserved_quantity or 0)
        new_reserved = max(0, current_reserved - qty)
        
        rec.quantity = new_quantity
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
            line_receiver=(ln.line_receiver.data or "").strip() or None,
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
            line_receiver=d.get("line_receiver"),
            note=d.get("note"),
        ))
    db.session.flush()

def _safe_generate_number_after_flush(sale: Sale) -> None:
    if not sale.sale_number:
        sale.sale_number = f"INV-{datetime.utcnow():%Y%m%d}-{sale.id:04d}"
        db.session.flush()

@sales_bp.route("/dashboard")
@login_required
# @permission_required("manage_sales")  # Commented out - function not available
def dashboard():
    from decimal import Decimal
    from models import convert_amount
    
    total_sales = db.session.query(func.count(Sale.id)).scalar() or 0
    
    all_sales = db.session.query(Sale).all()
    total_revenue = Decimal('0.00')
    for s in all_sales:
        amt = Decimal(str(s.total_amount or 0))
        if s.currency == "ILS":
            total_revenue += amt
        else:
            try:
                total_revenue += convert_amount(amt, s.currency, "ILS", s.sale_date)
            except Exception:
                pass
    total_revenue = float(total_revenue)
    
    pending_sales = db.session.query(func.count(Sale.id)).filter(Sale.status == "DRAFT").scalar() or 0
    
    customers = db.session.query(Customer).all()
    top_customers_data = []
    for cust in customers:
        cust_sales = db.session.query(Sale).filter(Sale.customer_id == cust.id).all()
        spent = Decimal('0.00')
        for s in cust_sales:
            amt = Decimal(str(s.total_amount or 0))
            if s.currency == "ILS":
                spent += amt
            else:
                try:
                    spent += convert_amount(amt, s.currency, "ILS", s.sale_date)
                except Exception:
                    pass
        if spent > 0:
            top_customers_data.append((cust.name, float(spent)))
    top_customers_data.sort(key=lambda x: x[1], reverse=True)
    top_customers = top_customers_data[:5]
    
    products = db.session.query(Product).all()
    top_products_data = []
    for prod in products:
        lines = db.session.query(SaleLine).join(Sale).filter(
            SaleLine.product_id == prod.id,
            Sale.status == SaleStatus.CONFIRMED
        ).all()
        sold = sum(int(l.quantity or 0) for l in lines)
        revenue_prod = Decimal('0.00')
        for l in lines:
            sale = l.sale
            line_amt = Decimal(str(l.quantity or 0)) * Decimal(str(l.unit_price or 0)) * (Decimal('1') - Decimal(str(l.discount_rate or 0)) / Decimal('100'))
            if sale.currency == "ILS":
                revenue_prod += line_amt
            else:
                try:
                    revenue_prod += convert_amount(line_amt, sale.currency, "ILS", sale.sale_date)
                except Exception:
                    pass
        if sold > 0:
            top_products_data.append((prod.name, sold, float(revenue_prod)))
    top_products_data.sort(key=lambda x: x[1], reverse=True)
    top_products = top_products_data[:5]
    
    y = extract("year", Sale.sale_date)
    m = extract("month", Sale.sale_date)
    monthly_raw = db.session.query(y.label("y"), m.label("m"), func.count(Sale.id)).group_by(y, m).order_by(y, m).all()
    
    monthly_revenue = {}
    for s in all_sales:
        if not s.sale_date:
            continue
        ym = (s.sale_date.year, s.sale_date.month)
        if ym not in monthly_revenue:
            monthly_revenue[ym] = Decimal('0.00')
        amt = Decimal(str(s.total_amount or 0))
        if s.currency == "ILS":
            monthly_revenue[ym] += amt
        else:
            try:
                monthly_revenue[ym] += convert_amount(amt, s.currency, "ILS", s.sale_date)
            except Exception:
                pass
    
    months, counts, revenue = [], [], []
    for yy, mm, cnt in monthly_raw:
        months.append(f"{int(mm)}/{int(yy)}")
        counts.append(int(cnt))
        revenue.append(float(monthly_revenue.get((yy, mm), Decimal('0.00'))))
    return render_template("sales/dashboard.html",
                           total_sales=total_sales, total_revenue=total_revenue, pending_sales=pending_sales,
                           top_customers=top_customers, top_products=top_products,
                           months=months, sales_count=counts, revenue=revenue)

@sales_bp.route("/", endpoint="list_sales")
@sales_bp.route("/", endpoint="index")
@login_required
# @permission_required("manage_sales")  # Commented out - function not available
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
         .filter(Sale.is_archived == False)
        .options(joinedload(Sale.customer), joinedload(Sale.seller), joinedload(Sale.seller_employee))
         .outerjoin(subtotals, subtotals.c.sale_id == Sale.id)
         .outerjoin(Customer))
    st = (f.get("status") or "").upper().strip()
    status_filter_enabled = bool(st and st != "ALL")
    if status_filter_enabled:
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
    ordered_query = q.order_by(fld.asc() if order == "asc" else fld.desc())

    per_page = 20
    page = max(1, int(f.get("page", 1)))

    print_mode = request.args.get("print") == "1"
    scope_param = request.args.get("scope")
    print_scope = scope_param or ("page" if print_mode else "all")
    range_start = request.args.get("range_start", type=int)
    range_end = request.args.get("range_end", type=int)
    target_page = request.args.get("page_number", type=int)

    all_sales = ordered_query.all()

    total_filtered = len(all_sales)
    total_pages = math.ceil(total_filtered / per_page) if total_filtered else 1

    range_start_value = range_start or 1
    if range_start_value < 1:
        range_start_value = 1
    range_end_value = range_end or (total_filtered if total_filtered else 1)
    if range_end_value < range_start_value:
        range_end_value = range_start_value
    target_page_value = target_page or 1
    if target_page_value < 1:
        target_page_value = 1
    if target_page_value > total_pages:
        target_page_value = total_pages if total_pages else 1

    if print_mode:
        if print_scope == "all":
            sales_list = list(all_sales)
            row_offset = 0
        elif print_scope == "range":
            start_idx = range_start_value - 1
            end_idx = min(total_filtered, range_end_value)
            sales_list = all_sales[start_idx:end_idx]
            row_offset = start_idx
        else:
            row_offset = (target_page_value - 1) * per_page
            start_idx = row_offset
            end_idx = start_idx + per_page
            sales_list = all_sales[start_idx:end_idx]
        pag = None
    else:
        pag = ordered_query.paginate(page=page, per_page=per_page, error_out=False)
        sales_list = list(pag.items)
        row_offset = (pag.page - 1) * pag.per_page if pag else 0
    for s in sales_list:
        _format_sale(s)
    
    # حساب الملخصات الحقيقية
    from models import fx_rate
    
    # جلب جميع المبيعات (بدون pagination) لحساب الملخصات
    all_sales_query = Sale.query.filter(Sale.is_archived.is_(False))
    if status_filter_enabled:
        all_sales_query = all_sales_query.filter(Sale.status == st)
    if cust:
        all_sales_query = all_sales_query.join(Customer).filter(
            or_(Customer.name.ilike(f"%{cust}%"), Customer.phone.ilike(f"%{cust}%"))
        )
    try:
        if df:
            all_sales_query = all_sales_query.filter(Sale.sale_date >= datetime.fromisoformat(df))
        if dt:
            all_sales_query = all_sales_query.filter(Sale.sale_date <= datetime.fromisoformat(dt))
    except Exception:
        pass
    
    all_sales = all_sales_query.all()
    
    # حساب الإحصائيات بدقة
    def _to_ils(value, currency, fx_used, at_date):
        amount = Decimal(str(value or 0))
        code = (currency or "ILS").upper()
        if code != "ILS":
            if fx_used:
                try:
                    amount *= Decimal(str(fx_used))
                except Exception:
                    pass
            else:
                try:
                    rate = fx_rate(code, "ILS", at_date, raise_on_missing=False)
                    if rate and rate > 0:
                        amount *= Decimal(str(rate))
                except Exception:
                    pass
        return float(amount)
    
    total_sales = 0.0
    total_paid = 0.0
    total_pending = 0.0
    sales_by_status: dict[str, dict[str, float | int]] = {}
    contributing_sales = 0
    
    for sale in all_sales:
        status = (sale.status or "DRAFT").upper()
        
        sale_amount = _to_ils(sale.total_amount, sale.currency, getattr(sale, "fx_rate_used", None), sale.sale_date)
        balance_amount = _to_ils(sale.balance_due, sale.currency, getattr(sale, "fx_rate_used", None), sale.sale_date)
        refund_amount = _to_ils(sale.refunded_total, sale.currency, getattr(sale, "fx_rate_used", None), sale.sale_date)
        
        paid_amount = 0.0
        for payment in getattr(sale, "payments", []) or []:
            if (payment.direction or "").upper() != "IN":
                continue
            if (payment.status or "").upper() != "COMPLETED":
                continue
            paid_amount += _to_ils(payment.total_amount, payment.currency, getattr(payment, "fx_rate_used", None), payment.payment_date)
        
        net_amount = sale_amount
        if status == "REFUNDED":
            net_amount = max(sale_amount - refund_amount, 0.0)
            balance_amount = 0.0
        
        if status == "CONFIRMED":
            total_sales += net_amount
            total_paid += paid_amount
            total_pending += max(balance_amount, 0.0)
            contributing_sales += 1
        elif status not in ("DRAFT", "CANCELLED", "REFUNDED"):
            total_sales += net_amount
            total_paid += paid_amount
            total_pending += max(balance_amount, 0.0)
            contributing_sales += 1
        elif status == "REFUNDED":
            total_paid += min(paid_amount, net_amount)
        
        status_entry = sales_by_status.setdefault(status, {"count": 0, "amount": 0.0})
        status_entry["count"] += 1
        status_entry["amount"] += net_amount
    
    average_sale = total_sales / contributing_sales if contributing_sales else 0.0
    
    summary = {
        'total_sales': total_sales,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'average_sale': average_sale,
        'sales_count': contributing_sales,
        'sales_by_status': sales_by_status
    }
    
    query_args = request.args.to_dict()
    for key in ["page", "print", "scope", "range_start", "range_end", "page_number"]:
        query_args.pop(key, None)

    context = {
        "sales": sales_list,
        "pagination": pag,
        "warehouses": Warehouse.query.order_by(Warehouse.name).all(),
        "customers": Customer.query.order_by(Customer.name).limit(100).all(),
        "sellers": User.query.filter_by(is_active=True).order_by(User.username).all(),
        "status_map": STATUS_MAP,
        "summary": summary,
        "query_args": query_args,
        "print_mode": print_mode,
        "print_scope": print_scope,
        "range_start": range_start_value,
        "range_end": range_end_value,
        "target_page": target_page_value,
        "total_filtered": total_filtered,
        "total_pages": total_pages if total_pages else 1,
        "per_page": per_page,
        "row_offset": row_offset,
        "generated_at": datetime.utcnow(),
        "pdf_export": False,
        "show_actions": not print_mode,
    }

    if print_mode:
        context["pdf_export"] = True
        try:
            from weasyprint import HTML

            html_output = render_template("sales/list.html", **context)
            pdf_bytes = HTML(string=html_output, base_url=request.url_root).write_pdf()
            filename = f"sales_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.pdf"
            return Response(
                pdf_bytes,
                mimetype="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{filename}"'},
            )
        except Exception as exc:
            current_app.logger.error("sales_print_pdf_error: %s", exc)
            context["pdf_export"] = False

    return render_template("sales/list.html", **context)

def _resolve_unit_price(product_id: int, warehouse_id: Optional[int]) -> float:
    prod = db.session.get(Product, product_id)
    try:
        return float(getattr(prod, "price", 0) or 0)
    except Exception:
        return 0.0

@sales_bp.route("/new", methods=["GET", "POST"], endpoint="create_sale")
@login_required
# @permission_required("manage_sales")  # Commented out - function not available
def create_sale():
    form = SaleForm()
    if request.method == "POST" and not form.validate_on_submit():
        current_app.logger.warning("Sale form errors: %s", form.errors)
        current_app.logger.debug("POST data: %r", request.form.to_dict(flat=False))
    if form.validate_on_submit():
        try:
            # دائماً مؤكد - لا حاجة لاختيار الحالة
            target_status = "CONFIRMED"
            require_stock = True
            lines_payload, err = _resolve_lines_from_form(form, require_stock=require_stock)
            if err:
                flash(f"❌ {err}", "danger")
                return render_template("sales/form.html", form=form, title="إنشاء فاتورة جديدة",
                                       products=Product.query.order_by(Product.name).all(),
                                       warehouses=Warehouse.query.order_by(Warehouse.name).all())
            # جلب السعر التلقائي فقط إذا كان 0 أو سالب
            for d in lines_payload:
                if (d.get("unit_price") or 0) <= 0:
                    d["unit_price"] = _resolve_unit_price(d["product_id"], d.get("warehouse_id"))
            if require_stock:
                pairs = [(d["product_id"], d["warehouse_id"]) for d in lines_payload if d.get("warehouse_id")]
                _lock_stock_rows(pairs)
            # تنظيف notes من أي قيم غير صحيحة
            notes_raw = str(form.notes.data or '').strip()
            if notes_raw in ('[]', '{}', 'null', 'None', ''):
                notes_clean = None
            else:
                notes_clean = notes_raw or None
            
            sale = Sale(
                sale_number=None,
                customer_id=form.customer_id.data,
                seller_id=current_user.id if current_user and current_user.is_authenticated else None,
                seller_employee_id=form.seller_employee_id.data,
                sale_date=form.sale_date.data or datetime.utcnow(),
                status=target_status,  # دائماً CONFIRMED
                payment_status="PENDING",  # دائماً PENDING عند الإنشاء
                currency=(form.currency.data or "ILS").upper(),
                tax_rate=form.tax_rate.data or 0,
                discount_total=form.discount_total.data or 0,
                shipping_cost=form.shipping_cost.data or 0,
                notes=notes_clean
            )
            # إضافة receiver_name بشكل آمن
            if hasattr(Sale, 'receiver_name'):
                sale.receiver_name = form.receiver_name.data
            db.session.add(sale)
            db.session.flush()
            _safe_generate_number_after_flush(sale)
            _attach_lines(sale, lines_payload)
            db.session.flush()
            # الفاتورة مؤكدة - خصم المخزون مباشرة بدون حجز
            if require_stock and target_status == "CONFIRMED":
                _deduct_stock(sale)
            _log(sale, "CREATE", None, sale_to_dict(sale))
            
            # تسجيل ضريبة VAT تلقائياً
            if sale.tax_rate and sale.tax_rate > 0:
                try:
                    from utils import create_tax_entry
                    subtotal = float(sale.total_amount or 0) / (1 + float(sale.tax_rate) / 100)
                    create_tax_entry(
                        entry_type='OUTPUT_VAT',
                        transaction_type='SALE',
                        transaction_id=sale.id,
                        base_amount=subtotal,
                        tax_rate=float(sale.tax_rate),
                        reference=sale.sale_number,
                        customer_id=sale.customer_id,
                        currency=sale.currency
                    )
                except Exception as e:
                    current_app.logger.warning(f'⚠️ Tax entry failed: {e}')
            
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
# @permission_required("manage_sales")  # Commented out - function not available
def sale_detail(id: int):
    sale = _get_or_404(Sale, id, options=[
        joinedload(Sale.customer), joinedload(Sale.seller), joinedload(Sale.seller_employee),
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
# @permission_required("manage_sales")  # Commented out - function not available
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
# @permission_required("manage_sales")  # Commented out - function not available
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
            e.line_receiver.data = ln.line_receiver if hasattr(ln, 'line_receiver') else None
            e.note.data = ln.note
    if request.method == "POST" and not form.validate_on_submit():
        current_app.logger.warning("Sale form errors (edit): %s", form.errors)
        current_app.logger.debug("POST data (edit): %r", request.form.to_dict(flat=False))
    if form.validate_on_submit():
        try:
            was_confirmed = (sale.status == "CONFIRMED")
            if was_confirmed:
                _release_stock(sale)
            # الحالة دائماً CONFIRMED (تم حذف حقل status من الفورم)
            target_status = "CONFIRMED"
            require_stock = True
            lines_payload, err = _resolve_lines_from_form(form, require_stock=require_stock)
            if err:
                if was_confirmed:
                    _reserve_stock(sale)
                flash(f"❌ {err}", "danger")
                return render_template("sales/form.html", form=form, sale=sale, title="تعديل الفاتورة",
                                       products=Product.query.order_by(Product.name).all(),
                                       warehouses=Warehouse.query.order_by(Warehouse.name).all())
            # جلب السعر التلقائي فقط إذا كان 0 أو سالب
            for d in lines_payload:
                if (d.get("unit_price") or 0) <= 0:
                    d["unit_price"] = _resolve_unit_price(d["product_id"], d.get("warehouse_id"))
            if require_stock:
                pairs = [(d["product_id"], d["warehouse_id"]) for d in lines_payload if d.get("warehouse_id")]
                _lock_stock_rows(pairs)
            sale.customer_id = form.customer_id.data
            sale.seller_employee_id = form.seller_employee_id.data
            sale.sale_date = form.sale_date.data or sale.sale_date
            sale.status = target_status or sale.status
            sale.currency = (form.currency.data or sale.currency or "ILS").upper()
            sale.tax_rate = form.tax_rate.data or 0
            sale.discount_total = form.discount_total.data or 0
            sale.shipping_cost = form.shipping_cost.data or 0
            # حقل receiver_name - آمن حتى لو مفقود
            if hasattr(sale, 'receiver_name'):
                sale.receiver_name = form.receiver_name.data
            # تنظيف notes من أي قيم غير صحيحة
            notes_raw = str(form.notes.data or '').strip()
            if notes_raw in ('[]', '{}', 'null', 'None', ''):
                sale.notes = None
            else:
                sale.notes = notes_raw or None
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
# @permission_required("manage_sales")  # Commented out - function not available
def quick_sell():
    try:
        pid = int(request.form.get("product_id") or 0)
        wid = int(request.form.get("warehouse_id") or 0)
        qty = int(float(request.form.get("quantity") or 0))
        price_raw = request.form.get("unit_price")
        price = float(price_raw) if price_raw not in (None, "",) else 0.0
        customer_id = int(request.form.get("customer_id") or 0)
        seller_id = int(request.form.get("seller_id") or (current_user.id or 0))
        seller_employee_id_raw = request.form.get("seller_employee_id")
        seller_employee_id = int(seller_employee_id_raw) if seller_employee_id_raw and seller_employee_id_raw.isdigit() else None
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
            seller_employee_id=seller_employee_id,
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
# @permission_required("manage_sales")  # Commented out - function not available
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
# @permission_required("manage_sales")  # Commented out - function not available
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
@sales_bp.route("/<int:id>/receipt", methods=["GET"], endpoint="sale_receipt")
@login_required
# @permission_required("manage_sales")  # Commented out - function not available
def generate_invoice(id: int):
    sale = _get_or_404(Sale, id, options=[
        joinedload(Sale.customer), joinedload(Sale.seller), joinedload(Sale.seller_employee),
        joinedload(Sale.lines).joinedload(SaleLine.product),
        joinedload(Sale.lines).joinedload(SaleLine.warehouse),
    ])
    lines = []
    subtotal = Decimal("0.00")
    for ln in sale.lines:
        qty_dec = D(getattr(ln, "quantity", 0))
        unit_dec = D(getattr(ln, "unit_price", 0))
        rate_dec = D(getattr(ln, "discount_rate", 0))
        gross_total = (qty_dec * unit_dec).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        discount_amount = (gross_total * rate_dec / D(100)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        base_total = line_total_decimal(ln.quantity, ln.unit_price, ln.discount_rate)
        tr = D(getattr(ln, "tax_rate", 0))
        tax_amount = (base_total * tr / Decimal("100")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        line_total = (base_total + tax_amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        lines.append({
            "obj": ln,
            "gross_total": gross_total,
            "discount_rate": rate_dec,
            "discount_rate_display": f"{float(rate_dec or 0):.2f}",
            "discount_amount": discount_amount,
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
    
    # التحقق من نوع القالب (بسيط أو ملون)
    use_simple = request.args.get('simple', '').strip().lower() in ('1', 'true', 'yes')
    template_name = "sales/receipt_simple.html" if use_simple else "sales/receipt.html"
    
    return render_template(
        template_name,
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

@sales_bp.route("/archive/<int:sale_id>", methods=["POST"])
@login_required
# @permission_required("manage_sales")  # Commented out - function not available
def archive_sale(sale_id):
    # Debug logging removed to avoid Unicode errors
    
    try:
        from models import Archive
        
        sale = Sale.query.get_or_404(sale_id)
        
        reason = request.form.get('reason', 'أرشفة تلقائية')
        
        utils.archive_record(sale, reason, current_user.id)
        flash(f'تم أرشفة المبيعة رقم {sale_id} بنجاح', 'success')
        return redirect(url_for('sales_bp.list_sales'))
        
    except Exception as e:
        import traceback
        
        db.session.rollback()
        flash(f'خطأ في أرشفة المبيعة: {str(e)}', 'error')
        return redirect(url_for('sales_bp.list_sales'))

@sales_bp.route('/restore/<int:sale_id>', methods=['POST'])
@login_required
# @permission_required('manage_sales')  # Commented out - function not available
def restore_sale(sale_id):
    """استعادة مبيعة"""
    # Debug logging removed to avoid Unicode errors
    
    try:
        sale = Sale.query.get_or_404(sale_id)
        
        if not sale.is_archived:
            flash('المبيعة غير مؤرشفة', 'warning')
            return redirect(url_for('sales_bp.list_sales'))
        
        # البحث عن الأرشيف
        from models import Archive
        archive = Archive.query.filter_by(
            record_type='sales',
            record_id=sale_id
        ).first()
        
        if archive:
            utils.restore_record(archive.id)
        
        flash(f'تم استعادة المبيعة رقم {sale_id} بنجاح', 'success')
        print(f"🎉 [SALE RESTORE] تمت العملية بنجاح - إعادة توجيه...")
        return redirect(url_for('sales_bp.list_sales'))
        
    except Exception as e:
        import traceback
        
        db.session.rollback()
        flash(f'خطأ في استعادة المبيعة: {str(e)}', 'error')
        return redirect(url_for('sales_bp.list_sales'))