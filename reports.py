# File: reports.py
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import Date, func, cast
from sqlalchemy.orm import joinedload

from extensions import db
from models import (
    Customer,
    Expense,
    OnlinePreOrder,
    Payment,
    Sale,
    ServiceRequest,
    Invoice,
)

# ------------------------- أدوات مساعدة -------------------------

def age_bucket(days) -> str:
    """يرجع سلة الأعمار حسب عدد الأيام: 0-30 / 31-60 / 61-90 / 90+."""
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
    """يدخل datetime/date/str أو None → يرجّع date أو None."""
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

# ------------------------- محرّك تقرير عام -------------------------

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
    """دالة عامة لإنشاء التقارير مع فلترة وتجميع ديناميكي."""
    q = model.query

    if joins:
        for rel in joins:
            q = q.options(joinedload(rel))

    # فلترة التاريخ
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

    # فلترة دقيقة
    if filters:
        for k, v in filters.items():
            field = getattr(model, k, None)
            if field is not None:
                if hasattr(v, "__iter__") and not isinstance(v, str):
                    q = q.filter(field.in_(v))
                else:
                    q = q.filter(field == v)

    # فلترة like
    if like_filters:
        for k, pat in like_filters.items():
            field = getattr(model, k, None)
            if field is not None:
                q = q.filter(field.ilike(f"%{pat}%"))

    # تجميع
    if group_by:
        gb = [getattr(model, f) for f in group_by if hasattr(model, f)]
        if gb:
            q = q.group_by(*gb)

    # جلب البيانات
    data = []
    cols = columns or [c.name for c in model.__table__.columns]
    for obj in q.all():
        data.append({col: getattr(obj, col, None) for col in cols})

    # الملخص
    summary = {}
    if aggregates:
        for func_name, fields in aggregates.items():
            agg_func = getattr(func, func_name, None)
            if not agg_func:
                continue
            for f in fields:
                fld = getattr(model, f, None)
                if fld is not None:
                    summary[f"{func_name}_{f}"] = db.session.query(agg_func(fld)).scalar() or 0

    return {"data": data, "summary": summary}

# ------------------------- تقارير جاهزة -------------------------

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
    """ملخّص المدفوعات حسب طريقة الدفع خلال فترة زمنية."""
    start_date = _parse_date_like(start_date) or date.min
    end_date = _parse_date_like(end_date) or date.max

    q = (
        db.session.query(
            Payment.method.label("method"),
            func.sum(func.coalesce(Payment.total_amount, 0)).label("total"),
        )
        .filter(Payment.status == "COMPLETED")
        .filter(cast(Payment.payment_date, Date).between(start_date, end_date))
        .group_by(Payment.method)
        .order_by(Payment.method)
    )
    rows = q.all()
    return {
        "methods": [r.method for r in rows],
        "totals": [float(r.total) for r in rows],
        "grand_total": sum(float(r.total) for r in rows),
    }


def sales_report(start_date: date | None, end_date: date | None):
    """تقرير المبيعات المحسّن (يقبل None للفلاتر)."""
    start_date = _parse_date_like(start_date) or date.min
    end_date = _parse_date_like(end_date) or date.max

    q = (
        db.session.query(
            cast(Sale.sale_date, Date).label("day"),
            func.sum(func.coalesce(Sale.total_amount, 0)).label("revenue"),
        )
        .filter(cast(Sale.sale_date, Date).between(start_date, end_date))
        .group_by("day")
        .order_by("day")
    )
    rows = q.all()
    return {
        "daily_labels": [r.day.strftime("%Y-%m-%d") for r in rows],
        "daily_values": [float(r.revenue) for r in rows],
        "total_revenue": sum(float(r.revenue) for r in rows),
    }


def service_report(start_date: date, end_date: date):
    return advanced_report(
        model=ServiceRequest,
        date_field="start_time",
        start_date=start_date,
        end_date=end_date,
        aggregates={"count": ["id"]},
    )

# ------------------------- أعمار الذمم -------------------------

def ar_aging_report(start_date=None, end_date=None):
    """
    تقرير أعمار الذمم:
    - as_of = end_date (إن وُجد) وإلا تاريخ اليوم.
    - السلال: 0-30, 31-60, 61-90, 90+.
    - يحتسب الرصيد المفتوح لكل فاتورة: invoice.total - sum(payments COMPLETED for that invoice).
    - يُعيد {"as_of", "data": [...], "totals": {...}}.
    """
    as_of = _parse_date_like(end_date) or date.today()

    # اختيار عمود التاريخ المرجعي للفوترة (due_date ثم invoice_date ثم date/created_at/updated_at)
    ref_cols = []
    for attr in ("due_date", "invoice_date", "date", "created_at", "updated_at"):
        col = getattr(Invoice, attr, None)
        if col is not None:
            ref_cols.append(col)
    ref_date_expr = func.coalesce(*ref_cols) if ref_cols else func.current_date()

    # فواتير فعّالة فقط (استبعاد الملغاة/المستردة)
    inv_base = (
        db.session.query(
            Invoice.id.label("invoice_id"),
            Invoice.customer_id.label("customer_id"),
            func.coalesce(Invoice.total_amount, 0).label("inv_total"),
            ref_date_expr.label("ref_date"),
        )
        .filter(~Invoice.status.in_(["CANCELLED", "REFUNDED"]))
        .subquery()
    )

    # مجموع المدفوعات المكتملة لكل فاتورة
    pay_agg = (
        db.session.query(
            Payment.invoice_id.label("invoice_id"),
            func.coalesce(func.sum(Payment.total_amount), 0).label("paid"),
        )
        .filter(Payment.status == "COMPLETED")
        .group_by(Payment.invoice_id)
        .subquery()
    )

    # صفوف على مستوى الفاتورة الواحدة
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

    # تجميع على مستوى الزبون في سلال الأعمار
    bucket_keys = ("0-30", "31-60", "61-90", "90+")
    acc = defaultdict(lambda: {k: 0.0 for k in bucket_keys} | {"total": 0.0})

    for name, outstanding, ref_dt in rows:
        if not outstanding:
            continue
        outstanding = float(outstanding)
        if outstanding <= 0:
            continue

        # ref_dt -> date
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

    # payload
    data = []
    for name in sorted(acc.keys()):
        item = {
            "customer": name,
            "balance": round(acc[name]["total"], 2),
            "buckets": {k: round(acc[name][k], 2) for k in bucket_keys},
        }
        data.append(item)

    # مجاميع عامة
    totals = {k: 0.0 for k in bucket_keys} | {"total": 0.0}
    for v in acc.values():
        for k in bucket_keys:
            totals[k] += v[k]
        totals["total"] += v["total"]
    totals = {k: round(v, 2) for k, v in totals.items()}

    return {"as_of": as_of.isoformat(), "data": data, "totals": totals}
