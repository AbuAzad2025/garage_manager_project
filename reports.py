from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, time as _t
from decimal import Decimal
from typing import Dict
from zoneinfo import ZoneInfo

from sqlalchemy import Date, and_, cast, func, desc
from sqlalchemy.orm import joinedload

from extensions import db
from models import (
    Customer,
    Supplier,
    Product,
    SaleLine,
    Expense,
    Invoice,
    OnlinePreOrder,
    Payment,
    PaymentDirection,
    PaymentStatus,
    Sale,
    SaleStatus,
    ServiceRequest,
    ServiceStatus,
    InvoiceStatus,
)


def age_bucket(days) -> str:
    try:
        d = int(days)
    except Exception:
        d = 0
    d = max(d, 0)
    if d <= 30:
        return "0-30"
    if d <= 60:
        return "31-60"
    if d <= 90:
        return "61-90"
    return "90+"


def _parse_date_like(d):
    if not d:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, str):
        try:
            return date.fromisoformat(d)
        except Exception:
            return None
    return None


def _allowed_columns(model) -> set[str]:
    return {c.name for c in model.__table__.columns}


def advanced_report(
    model,
    joins=None,
    date_field=None,
    start_date: date | None = None,
    end_date: date | None = None,
    filters=None,
    like_filters=None,
    columns=None,
    group_by=None,
    aggregates=None,
):
    q = model.query
    if joins:
        for rel in joins:
            q = q.options(joinedload(rel))
    start_date = _parse_date_like(start_date)
    end_date = _parse_date_like(end_date)
    if date_field and (start_date or end_date):
        fld = getattr(model, date_field, None)
        if fld is None:
            raise ValueError(f"Invalid date field: {date_field}")
        if start_date and end_date:
            q = q.filter(cast(fld, Date).between(start_date, end_date))
        elif start_date:
            q = q.filter(cast(fld, Date) >= start_date)
        else:
            q = q.filter(cast(fld, Date) <= end_date)
    if filters:
        for k, v in filters.items():
            fld = getattr(model, k, None)
            if fld is not None:
                if hasattr(v, "__iter__") and not isinstance(v, str):
                    q = q.filter(fld.in_(v))
                else:
                    q = q.filter(fld == v)
    if like_filters:
        for k, pat in like_filters.items():
            fld = getattr(model, k, None)
            if fld is not None and pat not in (None, ""):
                q = q.filter(fld.ilike(f"%{pat}%"))
    if group_by:
        gb = [getattr(model, f) for f in group_by if hasattr(model, f)]
        if gb:
            q = q.group_by(*gb)
    allowed = _allowed_columns(model)
    if columns:
        cols = [c for c in columns if c in allowed]
    else:
        cols = sorted(allowed)
    objs = q.all()
    data = [{col: getattr(obj, col, None) for col in cols} for obj in objs]
    summary: Dict[str, float] = {}
    if aggregates:
        for func_name, fields in aggregates.items():
            agg_func = getattr(func, func_name, None)
            if not agg_func:
                continue
            for f in fields:
                fld = getattr(model, f, None)
                if fld is None:
                    continue
                val = q.with_entities(agg_func(fld)).scalar()
                summary[f"{func_name}_{f}"] = float(val or 0)
    return {"data": data, "summary": summary}


def expense_report(start_date: date, end_date: date):
    return advanced_report(
        model=Expense,
        date_field="date",
        start_date=start_date,
        end_date=end_date,
        aggregates={"sum": ["amount"], "count": ["id"]},
    )


def shop_report(start_date: date, end_date: date):
    return advanced_report(
        model=OnlinePreOrder,
        date_field="created_at",
        start_date=start_date,
        end_date=end_date,
        aggregates={"sum": ["prepaid_amount", "total_amount"], "count": ["id"]},
    )


def payment_summary_report(start_date: date | None, end_date: date | None):
    start_date = _parse_date_like(start_date) or date.min
    end_date = _parse_date_like(end_date) or date.max
    q = (
        db.session.query(
            Payment.method.label("method"),
            func.sum(func.coalesce(Payment.total_amount, 0)).label("total"),
        )
        .filter(Payment.status == PaymentStatus.COMPLETED.value)
        .filter(Payment.direction == PaymentDirection.INCOMING.value)
        .filter(cast(Payment.payment_date, Date).between(start_date, end_date))
        .group_by(Payment.method)
        .order_by(Payment.method)
    )
    rows = q.all()
    return {
        "methods": [r.method for r in rows],
        "totals": [float(r.total or 0) for r in rows],
        "grand_total": sum(float(r.total or 0) for r in rows),
    }


def sales_report(start_date: date | None, end_date: date | None, tz_name: str = "Asia/Hebron") -> dict:
    TZ = ZoneInfo(tz_name)
    sd = _parse_date_like(start_date)
    ed = _parse_date_like(end_date)
    if sd and ed and ed < sd:
        sd, ed = ed, sd
    engine = db.engine.name
    if engine == "postgresql":
        sale_day = func.date_trunc("day", func.timezone(tz_name, Sale.sale_date))
    else:
        sale_day = cast(Sale.sale_date, Date)
    filters = []
    if sd:
        start_dt_local = datetime.combine(sd, _t.min).replace(tzinfo=TZ)
        if engine == "postgresql":
            filters.append(Sale.sale_date >= start_dt_local.astimezone(ZoneInfo("UTC")))
        else:
            filters.append(Sale.sale_date >= start_dt_local.replace(tzinfo=None))
    if ed:
        try:
            ed_plus1 = ed + timedelta(days=1)
            end_dt_local = datetime.combine(ed_plus1, _t.min).replace(tzinfo=TZ)
        except OverflowError:
            end_dt_local = datetime.combine(ed, _t.max).replace(tzinfo=TZ)
        if engine == "postgresql":
            filters.append(Sale.sale_date < end_dt_local.astimezone(ZoneInfo("UTC")))
        else:
            filters.append(Sale.sale_date < end_dt_local.replace(tzinfo=None))
    allowed_statuses = (SaleStatus.CONFIRMED.value,)
    excluded_statuses = (SaleStatus.CANCELLED.value, SaleStatus.REFUNDED.value)
    q = (
        db.session.query(
            sale_day.label("day"),
            func.coalesce(func.sum(Sale.total_amount), 0).label("revenue"),
        )
        .filter(*filters)
        .filter(Sale.status.in_(allowed_statuses))
        .filter(~Sale.status.in_(excluded_statuses))
        .group_by("day")
        .order_by("day")
    )
    rows = q.all()
    day_to_sum: dict[date, Decimal] = {}
    for d, v in rows:
        dd = d.date() if hasattr(d, "date") else d
        day_to_sum[dd] = Decimal(str(v or 0))
    total = sum(day_to_sum.values(), Decimal("0"))
    labels: list[str] = []
    values: list[float] = []
    if sd and ed:
        cur = sd
        while cur <= ed:
            val = day_to_sum.get(cur, Decimal("0"))
            labels.append(cur.isoformat())
            values.append(float(val))
            cur += timedelta(days=1)
    else:
        for d in sorted(day_to_sum.keys()):
            labels.append(d.isoformat())
            values.append(float(day_to_sum[d]))
    return {"daily_labels": labels, "daily_values": values, "total_revenue": float(total)}


def service_reports_report(start_date: date | None, end_date: date | None) -> dict:
    start_date = _parse_date_like(start_date) or date.min
    end_date = _parse_date_like(end_date) or date.max
    if end_date < start_date:
        start_date, end_date = end_date, start_date
    date_cond = cast(ServiceRequest.received_at, Date).between(start_date, end_date)
    total = db.session.query(func.count(ServiceRequest.id)).filter(date_cond).scalar() or 0
    completed = (
        db.session.query(func.count(ServiceRequest.id))
        .filter(date_cond, ServiceRequest.status == ServiceStatus.COMPLETED.value)
        .scalar()
        or 0
    )
    revenue = db.session.query(func.coalesce(func.sum(ServiceRequest.total_amount), 0)).filter(date_cond).scalar() or 0
    parts = db.session.query(func.coalesce(func.sum(ServiceRequest.parts_total), 0)).filter(date_cond).scalar() or 0
    labor = db.session.query(func.coalesce(func.sum(ServiceRequest.labor_total), 0)).filter(date_cond).scalar() or 0
    rows_q = (
        db.session.query(
            ServiceRequest.service_number.label("number"),
            ServiceRequest.status.label("status"),
            ServiceRequest.priority.label("priority"),
            ServiceRequest.received_at.label("received_at"),
            ServiceRequest.customer_id.label("customer_id"),
            ServiceRequest.mechanic_id.label("mechanic_id"),
            func.coalesce(ServiceRequest.total_amount, 0).label("total"),
        )
        .filter(date_cond)
        .order_by(ServiceRequest.received_at.desc(), ServiceRequest.id.desc())
    )
    data = []
    for r in rows_q.all():
        rec_at = r.received_at.isoformat() if r.received_at else None
        data.append(
            {
                "number": r.number,
                "status": getattr(r.status, "value", r.status),
                "priority": getattr(r.priority, "value", r.priority),
                "received_at": rec_at,
                "customer_id": r.customer_id,
                "mechanic_id": r.mechanic_id,
                "total": float(r.total or 0),
            }
        )
    return {"total": int(total), "completed": int(completed), "revenue": float(revenue or 0), "parts": float(parts or 0), "labor": float(labor or 0), "data": data}


def ar_aging_report(start_date=None, end_date=None):
    as_of = _parse_date_like(end_date) or date.today()
    ref_cols = []
    for attr in ("due_date", "invoice_date", "date", "created_at", "updated_at"):
        col = getattr(Invoice, attr, None)
        if col is not None:
            ref_cols.append(col)
    ref_date_expr = func.coalesce(*ref_cols) if ref_cols else func.current_date()
    inv_base = (
        db.session.query(
            Invoice.id.label("invoice_id"),
            Invoice.customer_id.label("customer_id"),
            func.coalesce(Invoice.total_amount, 0).label("inv_total"),
            ref_date_expr.label("ref_date"),
        )
        .filter(Invoice.customer_id.isnot(None))
        .filter(~Invoice.status.in_([InvoiceStatus.CANCELLED.value, InvoiceStatus.REFUNDED.value]))
        .filter(cast(ref_date_expr, Date) <= as_of)
        .subquery()
    )
    pay_agg = (
        db.session.query(
            Payment.invoice_id.label("invoice_id"),
            func.coalesce(func.sum(Payment.total_amount), 0).label("paid"),
        )
        .filter(Payment.status == PaymentStatus.COMPLETED.value)
        .filter(Payment.direction == PaymentDirection.INCOMING.value)
        .filter(cast(Payment.payment_date, Date) <= as_of)
        .group_by(Payment.invoice_id)
        .subquery()
    )
    rows = (
        db.session.query(
            Customer.name,
            (inv_base.c.inv_total - func.coalesce(pay_agg.c.paid, 0)).label("outstanding"),
            inv_base.c.ref_date,
        )
        .join(Customer, Customer.id == inv_base.c.customer_id)
        .outerjoin(pay_agg, pay_agg.c.invoice_id == inv_base.c.invoice_id)
        .all()
    )
    bucket_keys = ("0-30", "31-60", "61-90", "90+")
    acc = defaultdict(lambda: {k: 0.0 for k in bucket_keys} | {"total": 0.0})
    for name, outstanding, ref_dt in rows:
        if not outstanding:
            continue
        outstanding = float(outstanding or 0)
        if outstanding <= 0:
            continue
        if isinstance(ref_dt, datetime):
            ref_d = ref_dt.date()
        elif isinstance(ref_dt, date):
            ref_d = ref_dt
        else:
            ref_d = as_of
        days = max((as_of - ref_d).days, 0) if (as_of and ref_d) else 0
        b = age_bucket(days)
        acc[name][b] += outstanding
        acc[name]["total"] += outstanding
    data = []
    for name in sorted(acc.keys()):
        item = {
            "customer": name,
            "balance": round(acc[name]["total"], 2),
            "buckets": {k: round(acc[name][k], 2) for k in bucket_keys},
        }
        data.append(item)
    totals = {k: 0.0 for k in bucket_keys} | {"total": 0.0}
    for v in acc.values():
        for k in bucket_keys:
            totals[k] += v[k]
        totals["total"] += v["total"]
    totals = {k: round(v, 2) for k, v in totals.items()}
    return {"as_of": as_of.isoformat(), "data": data, "totals": totals}


def ap_aging_report(start_date=None, end_date=None):
    as_of = _parse_date_like(end_date) or date.today()
    ref_cols = []
    for attr in ("due_date", "invoice_date", "date", "created_at", "updated_at"):
        col = getattr(Invoice, attr, None)
        if col is not None:
            ref_cols.append(col)
    ref_date_expr = func.coalesce(*ref_cols) if ref_cols else func.current_date()
    inv_base = (
        db.session.query(
            Invoice.id.label("invoice_id"),
            Invoice.supplier_id.label("supplier_id"),
            func.coalesce(Invoice.total_amount, 0).label("inv_total"),
            ref_date_expr.label("ref_date"),
        )
        .filter(Invoice.supplier_id.isnot(None))
        .filter(~Invoice.status.in_([InvoiceStatus.CANCELLED.value, InvoiceStatus.REFUNDED.value]))
        .filter(cast(ref_date_expr, Date) <= as_of)
        .subquery()
    )
    pay_agg = (
        db.session.query(
            Payment.invoice_id.label("invoice_id"),
            func.coalesce(func.sum(Payment.total_amount), 0).label("paid"),
        )
        .filter(Payment.status == PaymentStatus.COMPLETED.value)
        .filter(Payment.direction == PaymentDirection.OUTGOING.value)
        .filter(cast(Payment.payment_date, Date) <= as_of)
        .group_by(Payment.invoice_id)
        .subquery()
    )
    rows = (
        db.session.query(
            Supplier.name,
            (inv_base.c.inv_total - func.coalesce(pay_agg.c.paid, 0)).label("outstanding"),
            inv_base.c.ref_date,
        )
        .join(Supplier, Supplier.id == inv_base.c.supplier_id)
        .outerjoin(pay_agg, pay_agg.c.invoice_id == inv_base.c.invoice_id)
        .all()
    )
    bucket_keys = ("0-30", "31-60", "61-90", "90+")
    acc = defaultdict(lambda: {k: 0.0 for k in bucket_keys} | {"total": 0.0})
    for name, outstanding, ref_dt in rows:
        if not outstanding:
            continue
        outstanding = float(outstanding or 0)
        if outstanding <= 0:
            continue
        if isinstance(ref_dt, datetime):
            ref_d = ref_dt.date()
        elif isinstance(ref_dt, date):
            ref_d = ref_dt
        else:
            ref_d = as_of
        days = max((as_of - ref_d).days, 0) if (as_of and ref_d) else 0
        b = age_bucket(days)
        acc[name][b] += outstanding
        acc[name]["total"] += outstanding
    data = []
    for name in sorted(acc.keys()):
        item = {
            "supplier": name,
            "balance": round(acc[name]["total"], 2),
            "buckets": {k: round(acc[name][k], 2) for k in bucket_keys},
        }
        data.append(item)
    totals = {k: 0.0 for k in bucket_keys} | {"total": 0.0}
    for v in acc.values():
        for k in bucket_keys:
            totals[k] += v[k]
        totals["total"] += v["total"]
    totals = {k: round(v, 2) for k, v in totals.items()}
    return {"as_of": as_of.isoformat(), "data": data, "totals": totals}


def top_products_report(start_date: date | None, end_date: date | None, limit: int = 20, tz_name: str = "Asia/Hebron") -> dict:
    TZ = ZoneInfo(tz_name)
    start_date = start_date or date.min
    end_date = end_date or date.max
    if end_date < start_date:
        start_date, end_date = end_date, start_date
    start_dt_local = datetime.combine(start_date, _t.min).replace(tzinfo=TZ)
    end_dt_local = datetime.combine(end_date + timedelta(days=1), _t.min).replace(tzinfo=TZ)
    engine = db.engine.name
    if engine == "postgresql":
        date_filter_lower = Sale.sale_date >= start_dt_local.astimezone(ZoneInfo("UTC"))
        date_filter_upper = Sale.sale_date < end_dt_local.astimezone(ZoneInfo("UTC"))
    else:
        date_filter_lower = Sale.sale_date >= start_dt_local.replace(tzinfo=None)
        date_filter_upper = Sale.sale_date < end_dt_local.replace(tzinfo=None)
    value_expr = (SaleLine.quantity * SaleLine.unit_price) * (1 - (func.coalesce(SaleLine.discount_rate, 0) / 100.0)) * (1 + (func.coalesce(SaleLine.tax_rate, 0) / 100.0))
    q = (
        db.session.query(
            Product.id.label("product_id"),
            Product.name.label("name"),
            func.coalesce(func.sum(SaleLine.quantity), 0).label("qty"),
            func.coalesce(func.sum(value_expr), 0).label("revenue"),
        )
        .join(SaleLine, SaleLine.product_id == Product.id)
        .join(Sale, SaleLine.sale_id == Sale.id)
        .filter(and_(date_filter_lower, date_filter_upper))
        .filter(Sale.status == SaleStatus.CONFIRMED.value)
        .group_by(Product.id, Product.name)
        .order_by(desc("revenue"))
        .limit(int(limit or 20))
    )
    rows = q.all()
    data = []
    rank = 1
    for r in rows:
        data.append({"id": rank, "name": r.name, "qty": int(r.qty or 0), "revenue": float(r.revenue or 0), "product_id": r.product_id})
        rank += 1
    return {"data": data}
