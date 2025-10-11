# reports.py - Reports Module
# Location: /garage_manager/reports.py
# Description: Report generation and analytics functionality

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
    Customer, Supplier, Product, Warehouse, SaleLine, Expense, Invoice,
    OnlinePreOrder, Payment, PaymentSplit, PaymentDirection, PaymentStatus,
    Sale, SaleStatus, ServiceRequest, ServiceStatus, InvoiceStatus,
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


def customer_balance_report_ils(customer_ids: list = None) -> Dict:
    """تقرير أرصدة العملاء بالشيكل"""
    try:
        from utils import get_entity_balance_in_ils, format_currency_in_ils
        
        if customer_ids is None:
            customers = db.session.query(Customer).all()
            customer_ids = [c.id for c in customers]
        
        report_data = []
        total_balance_ils = Decimal("0.00")
        
        for customer_id in customer_ids:
            customer = db.session.get(Customer, customer_id)
            if not customer:
                continue
            
            balance_ils = get_entity_balance_in_ils("CUSTOMER", customer_id)
            
            report_data.append({
                'customer_id': customer_id,
                'customer_name': customer.name,
                'customer_currency': customer.currency,
                'balance_ils': balance_ils,
                'formatted_balance': format_currency_in_ils(balance_ils),
                'credit_limit': customer.credit_limit,
                'credit_status': customer.credit_status
            })
            
            total_balance_ils += balance_ils
        
        return {
            'report_type': 'customer_balance_report_ils',
            'base_currency': 'ILS',
            'total_customers': len(customer_ids),
            'total_balance_ils': total_balance_ils,
            'formatted_total': format_currency_in_ils(total_balance_ils),
            'customers': report_data,
            'generated_at': datetime.utcnow()
        }
    except Exception as e:
        return {
            'error': str(e),
            'generated_at': datetime.utcnow()
        }


def supplier_balance_report_ils(supplier_ids: list = None) -> Dict:
    """تقرير أرصدة الموردين بالشيكل"""
    try:
        from utils import get_entity_balance_in_ils, format_currency_in_ils
        
        if supplier_ids is None:
            suppliers = db.session.query(Supplier).all()
            supplier_ids = [s.id for s in suppliers]
        
        report_data = []
        total_balance_ils = Decimal("0.00")
        
        for supplier_id in supplier_ids:
            supplier = db.session.get(Supplier, supplier_id)
            if not supplier:
                continue
            
            balance_ils = get_entity_balance_in_ils("SUPPLIER", supplier_id)
            
            report_data.append({
                'supplier_id': supplier_id,
                'supplier_name': supplier.name,
                'supplier_currency': supplier.currency,
                'balance_ils': balance_ils,
                'formatted_balance': format_currency_in_ils(balance_ils),
                'is_local': supplier.is_local
            })
            
            total_balance_ils += balance_ils
        
        return {
            'report_type': 'supplier_balance_report_ils',
            'base_currency': 'ILS',
            'total_suppliers': len(supplier_ids),
            'total_balance_ils': total_balance_ils,
            'formatted_total': format_currency_in_ils(total_balance_ils),
            'suppliers': report_data,
            'generated_at': datetime.utcnow()
        }
    except Exception as e:
        return {
            'error': str(e),
            'generated_at': datetime.utcnow()
        }


def payment_summary_report_ils(start_date: date = None, end_date: date = None) -> Dict:
    """تقرير ملخص المدفوعات بالشيكل"""
    try:
        from utils import format_currency_in_ils
        from models import convert_amount
        
        if start_date is None:
            start_date = date.today().replace(day=1)
        if end_date is None:
            end_date = date.today()
        
        # الحصول على المدفوعات في الفترة
        payments = db.session.query(Payment).filter(
            and_(
                Payment.status == PaymentStatus.COMPLETED.value,
                cast(Payment.payment_date, Date).between(start_date, end_date)
            )
        ).all()
        
        total_incoming_ils = Decimal("0.00")
        total_outgoing_ils = Decimal("0.00")
        currency_breakdown = {}
        
        for payment in payments:
            amount = Decimal(str(payment.total_amount or 0))
            currency = payment.currency or "ILS"
            direction = payment.direction
            
            # تحويل للشيكل
            if currency == "ILS":
                amount_ils = amount
            else:
                try:
                    amount_ils = convert_amount(amount, currency, "ILS", payment.payment_date)
                except Exception as e:
                    # تسجيل الخطأ وتجاهل المبلغ من التحليل
                    try:
                        from flask import current_app
                        current_app.logger.error(f"❌ خطأ في تحويل العملة في تقرير الدفعات للدفعة #{payment.id}: {str(e)}")
                    except:
                        pass
                    continue
            
            # إضافة للتحليل
            if direction == PaymentDirection.IN.value:
                total_incoming_ils += amount_ils
            else:
                total_outgoing_ils += amount_ils
            
            # تفصيل العملة
            if currency not in currency_breakdown:
                currency_breakdown[currency] = {
                    'total_incoming': Decimal("0.00"),
                    'total_outgoing': Decimal("0.00"),
                    'net_balance': Decimal("0.00"),
                    'converted_to_ils': Decimal("0.00")
                }
            
            if direction == PaymentDirection.IN.value:
                currency_breakdown[currency]['total_incoming'] += amount
            else:
                currency_breakdown[currency]['total_outgoing'] += amount
            
            currency_breakdown[currency]['net_balance'] = (
                currency_breakdown[currency]['total_incoming'] - 
                currency_breakdown[currency]['total_outgoing']
            )
            currency_breakdown[currency]['converted_to_ils'] += amount_ils
        
        net_balance_ils = total_incoming_ils - total_outgoing_ils
        
        return {
            'report_type': 'payment_summary_report_ils',
            'base_currency': 'ILS',
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'totals': {
                'total_incoming_ils': total_incoming_ils,
                'total_outgoing_ils': total_outgoing_ils,
                'net_balance_ils': net_balance_ils,
                'formatted_incoming': format_currency_in_ils(total_incoming_ils),
                'formatted_outgoing': format_currency_in_ils(total_outgoing_ils),
                'formatted_net': format_currency_in_ils(net_balance_ils)
            },
            'currency_breakdown': currency_breakdown,
            'total_payments': len(payments),
            'generated_at': datetime.utcnow()
        }
    except Exception as e:
        return {
            'error': str(e),
            'generated_at': datetime.utcnow()
        }

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
    sd = _parse_date_like(start_date)
    ed = _parse_date_like(end_date)
    if date_field and (sd or ed):
        fld = getattr(model, date_field, None)
        if fld is None:
            raise ValueError(f"Invalid date field: {date_field}")
        if sd and ed:
            q = q.filter(cast(fld, Date).between(sd, ed))
        elif sd:
            q = q.filter(cast(fld, Date) >= sd)
        else:
            q = q.filter(cast(fld, Date) <= ed)
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
        cols = [c for c in columns if hasattr(model, c)]
    else:
        cols = list(allowed)
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

def sales_report_ils(start_date: date | None, end_date: date | None, tz_name: str = "Asia/Hebron") -> dict:
    """تقرير المبيعات مع تحويل العملات للشيكل"""
    try:
        from utils import format_currency_in_ils
        from models import convert_amount
        
        TZ = ZoneInfo(tz_name)
        sd = _parse_date_like(start_date)
        ed = _parse_date_like(end_date)
        if sd and ed and ed < sd:
            sd, ed = ed, sd
        
        # الحصول على المبيعات في الفترة
        filters = []
        if sd:
            start_dt_local = datetime.combine(sd, _t.min).replace(tzinfo=TZ)
            filters.append(Sale.sale_date >= start_dt_local.replace(tzinfo=None))
        if ed:
            try:
                ed_plus1 = ed + timedelta(days=1)
                end_dt_local = datetime.combine(ed_plus1, _t.min).replace(tzinfo=TZ)
            except OverflowError:
                end_dt_local = datetime.combine(ed, _t.max).replace(tzinfo=TZ)
            filters.append(Sale.sale_date < end_dt_local.replace(tzinfo=None))
        
        allowed_statuses = (SaleStatus.CONFIRMED.value,)
        excluded_statuses = (SaleStatus.CANCELLED.value, SaleStatus.REFUNDED.value)
        
        sales = db.session.query(Sale).filter(*filters).filter(
            Sale.status.in_(allowed_statuses)
        ).filter(~Sale.status.in_(excluded_statuses)).all()
        
        total_revenue_ils = Decimal("0.00")
        currency_breakdown = {}
        daily_revenue = {}
        
        for sale in sales:
            amount = Decimal(str(sale.total_amount or 0))
            currency = sale.currency or "ILS"
            sale_date = sale.sale_date.date()
            
            # تحويل للشيكل
            if currency == "ILS":
                amount_ils = amount
            else:
                try:
                    amount_ils = convert_amount(amount, currency, "ILS", sale.sale_date)
                except Exception as e:
                    # تسجيل الخطأ وتجاهل المبلغ من التحليل
                    try:
                        from flask import current_app
                        current_app.logger.error(f"❌ خطأ في تحويل العملة في تقرير المبيعات للبيع #{sale.id}: {str(e)}")
                    except:
                        pass
                    continue
            
            total_revenue_ils += amount_ils
            
            # تجميع حسب العملة
            if currency not in currency_breakdown:
                currency_breakdown[currency] = {
                    'total_original': Decimal("0.00"),
                    'total_ils': Decimal("0.00"),
                    'count': 0
                }
            currency_breakdown[currency]['total_original'] += amount
            currency_breakdown[currency]['total_ils'] += amount_ils
            currency_breakdown[currency]['count'] += 1
            
            # تجميع يومي
            date_key = sale_date.isoformat()
            if date_key not in daily_revenue:
                daily_revenue[date_key] = Decimal("0.00")
            daily_revenue[date_key] += amount_ils
        
        return {
            'report_type': 'sales_report_ils',
            'base_currency': 'ILS',
            'period': {
                'start_date': sd,
                'end_date': ed
            },
            'totals': {
                'total_revenue_ils': total_revenue_ils,
                'formatted_total': format_currency_in_ils(total_revenue_ils),
                'total_sales': len(sales)
            },
            'currency_breakdown': currency_breakdown,
            'daily_revenue': daily_revenue,
            'generated_at': datetime.utcnow()
        }
    except Exception as e:
        return {
            'error': str(e),
            'generated_at': datetime.utcnow()
        }

def sales_report(start_date: date | None, end_date: date | None, tz_name: str = "Asia/Hebron") -> dict:
    TZ = ZoneInfo(tz_name)
    sd = _parse_date_like(start_date)
    ed = _parse_date_like(end_date)
    if sd and ed and ed < sd:
        sd, ed = ed, sd
    engine = db.engine.name
    if engine == "postgresql":
        day_expr = func.to_char(func.timezone(tz_name, Sale.sale_date), "YYYY-MM-DD")
    elif engine in ("mysql", "mariadb"):
        day_expr = func.date_format(Sale.sale_date, "%Y-%m-%d")
    else:
        day_expr = func.strftime("%Y-%m-%d", Sale.sale_date)
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
            day_expr.label("day"),
            func.coalesce(func.sum(Sale.total_amount), 0).label("revenue"),
        )
        .filter(*filters)
        .filter(Sale.status.in_(allowed_statuses))
        .filter(~Sale.status.in_(excluded_statuses))
        .group_by("day")
        .order_by("day")
    )
    rows = q.all()
    day_to_sum: dict[str, Decimal] = {}
    for d, v in rows:
        key = str(d)
        day_to_sum[key] = Decimal(str(v or 0))
    total = sum(day_to_sum.values(), Decimal("0"))
    labels: list[str] = []
    values: list[float] = []
    if sd and ed:
        cur = sd
        while cur <= ed:
            k = cur.isoformat()
            labels.append(k)
            values.append(float(day_to_sum.get(k, Decimal("0"))))
            cur += timedelta(days=1)
    else:
        for k in sorted(day_to_sum.keys()):
            labels.append(k)
            values.append(float(day_to_sum[k]))
    return {"daily_labels": labels, "daily_values": values, "total_revenue": float(total)}

def expense_report(start_date: date | None, end_date: date | None):
    return advanced_report(
        model=Expense,
        date_field="date",
        start_date=start_date,
        end_date=end_date,
        aggregates={"sum": ["amount"], "count": ["id"]},
    )

def shop_report(start_date: date | None, end_date: date | None):
    return advanced_report(
        model=OnlinePreOrder,
        date_field="created_at",
        start_date=start_date,
        end_date=end_date,
        aggregates={"sum": ["prepaid_amount", "total_amount"], "count": ["id"]},
    )

def payment_summary_report(start_date, end_date):
    sd = _parse_date_like(start_date) or date.min
    ed = _parse_date_like(end_date) or date.max
    if ed < sd:
        sd, ed = ed, sd
    ref_date = Payment.payment_date
    base_filters = [
        Payment.status == PaymentStatus.COMPLETED.value,
        Payment.direction == PaymentDirection.IN.value,
        cast(ref_date, Date).between(sd, ed),
    ]
    split_rows = (
        db.session.query(
            func.coalesce(cast(PaymentSplit.method, db.String()), "other").label("method"),
            func.coalesce(func.sum(PaymentSplit.amount), 0).label("total"),
        )
        .join(Payment, Payment.id == PaymentSplit.payment_id)
        .filter(*base_filters)
        .group_by(func.coalesce(cast(PaymentSplit.method, db.String()), "other"))
        .all()
    )
    no_split_rows = (
        db.session.query(
            func.coalesce(cast(Payment.method, db.String()), "other").label("method"),
            func.coalesce(func.sum(Payment.total_amount), 0).label("total"),
        )
        .outerjoin(PaymentSplit, PaymentSplit.payment_id == Payment.id)
        .filter(*base_filters)
        .filter(PaymentSplit.id.is_(None))
        .group_by(func.coalesce(cast(Payment.method, db.String()), "other"))
        .all()
    )
    agg = {}
    for r in split_rows + no_split_rows:
        key = (getattr(r, "method", None) or "other").upper()
        agg[key] = agg.get(key, 0.0) + float(getattr(r, "total") or 0.0)
    methods = sorted(agg.keys())
    totals = [round(agg[m], 2) for m in methods]
    grand_total = round(sum(totals), 2)
    return {"methods": methods, "totals": totals, "grand_total": grand_total}

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
        .filter(Payment.direction == PaymentDirection.IN.value)
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
        .filter(Payment.direction == PaymentDirection.OUT.value)
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

def top_products_report(
    start_date: date | None,
    end_date: date | None,
    limit: int = 20,
    tz_name: str = "Asia/Hebron",
    warehouse_id: int | None = None,
    group_by_warehouse: bool = False,
) -> dict:
    TZ = ZoneInfo(tz_name)
    sd = _parse_date_like(start_date) or date.min
    ed = _parse_date_like(end_date) or date.max
    if ed < sd:
        sd, ed = ed, sd
    start_dt_local = datetime.combine(sd, _t.min).replace(tzinfo=TZ)
    try:
        _ed_plus1 = ed + timedelta(days=1)
        end_dt_local = datetime.combine(_ed_plus1, _t.min).replace(tzinfo=TZ)
        use_lt_end = True
    except OverflowError:
        end_dt_local = datetime.combine(ed, _t.max).replace(tzinfo=TZ)
        use_lt_end = False
    engine = db.engine.name
    if engine == "postgresql":
        lower = Sale.sale_date >= start_dt_local.astimezone(ZoneInfo("UTC"))
        upper = (Sale.sale_date < end_dt_local.astimezone(ZoneInfo("UTC"))) if use_lt_end else (Sale.sale_date <= end_dt_local.astimezone(ZoneInfo("UTC")))
    else:
        lower = Sale.sale_date >= start_dt_local.replace(tzinfo=None)
        upper = (Sale.sale_date < end_dt_local.replace(tzinfo=None)) if use_lt_end else (Sale.sale_date <= end_dt_local.replace(tzinfo=None))
    gross_expr = (SaleLine.quantity * SaleLine.unit_price)
    disc_expr = gross_expr * (func.coalesce(SaleLine.discount_rate, 0) / 100.0)
    net_before_tax_expr = (gross_expr - disc_expr)
    tax_expr = net_before_tax_expr * (func.coalesce(SaleLine.tax_rate, 0) / 100.0)
    net_revenue_expr = net_before_tax_expr + tax_expr
    sum_qty = func.coalesce(func.sum(SaleLine.quantity), 0.0)
    sum_gross = func.coalesce(func.sum(gross_expr), 0.0)
    sum_discount = func.coalesce(func.sum(disc_expr), 0.0)
    sum_net = func.coalesce(func.sum(net_revenue_expr), 0.0)
    weighted_price = func.coalesce(
        func.sum(SaleLine.unit_price * SaleLine.quantity) / func.nullif(func.sum(SaleLine.quantity), 0),
        0.0,
    )
    can_group_by_wh = hasattr(SaleLine, "warehouse_id")
    want_group = bool(group_by_warehouse and can_group_by_wh)
    want_filter = bool(warehouse_id and can_group_by_wh)
    select_cols = [
        Product.id.label("product_id"),
        Product.name.label("name"),
        sum_qty.label("qty"),
        sum_gross.label("gross"),
        sum_discount.label("discount"),
        sum_net.label("revenue"),
        weighted_price.label("avg_unit_price"),
        func.count(func.distinct(Sale.id)).label("orders_count"),
        func.min(Sale.sale_date).label("first_sale"),
        func.max(Sale.sale_date).label("last_sale"),
    ]
    if want_group:
        select_cols.append(Warehouse.name.label("warehouse_name"))
    q = (
        db.session.query(*select_cols)
        .join(SaleLine, SaleLine.product_id == Product.id)
        .join(Sale, SaleLine.sale_id == Sale.id)
        .filter(lower, upper)
        .filter(Sale.status == SaleStatus.CONFIRMED.value)
    )
    if want_group or want_filter:
        q = q.outerjoin(Warehouse, Warehouse.id == SaleLine.warehouse_id)
    if want_filter:
        q = q.filter(Warehouse.id == int(warehouse_id))
    if want_group:
        q = q.group_by(Product.id, Product.name, Warehouse.name)
    else:
        q = q.group_by(Product.id, Product.name)
    q = q.order_by(desc("revenue")).limit(int(limit or 20))
    rows = q.all()
    total_revenue = float(sum((float(getattr(r, "revenue", 0) or 0) for r in rows)) or 0.0)
    total_qty = int(sum((int(getattr(r, "qty", 0) or 0) for r in rows)) or 0)
    max_qty = max((int(getattr(r, "qty", 0) or 0) for r in rows), default=0)
    def _rank_label(idx: int) -> str:
        return ("الأول" if idx == 1 else "الثاني" if idx == 2 else "الثالث" if idx == 3 else f"المرتبة {idx}")
    data: list[dict] = []
    for i, r in enumerate(rows, start=1):
        qty = int(getattr(r, "qty", 0) or 0)
        rev = float(getattr(r, "revenue", 0) or 0)
        gross = float(getattr(r, "gross", 0) or 0)
        discount = float(getattr(r, "discount", 0) or 0)
        orders_count = int(getattr(r, "orders_count", 0) or 0)
        avg_price = float(getattr(r, "avg_unit_price", 0) or 0)
        share = (rev / total_revenue * 100.0) if total_revenue > 0 else 0.0
        if i <= 3 and rev > 0:
            reason = "ضمن الأعلى إيرادًا"
        elif qty == max_qty and qty > 0:
            reason = "أعلى كمية مباعة"
        elif share >= 10:
            reason = "حصة إيراد كبيرة"
        elif orders_count >= 5:
            reason = "مكرر الطلب من العملاء"
        else:
            reason = "أداء جيد ضمن الفترة"
        item = {
            "id": i,
            "rank_label": _rank_label(i),
            "product_id": getattr(r, "product_id", None),
            "name": getattr(r, "name", None),
            "qty": qty,
            "revenue": round(rev, 2),
            "revenue_share": round(share, 2),
            "gross": round(gross, 2),
            "discount": round(discount, 2),
            "avg_unit_price": round(avg_price, 2),
            "orders_count": orders_count,
            "first_sale": (getattr(r, "first_sale", None).isoformat() if getattr(r, "first_sale", None) else None),
            "last_sale": (getattr(r, "last_sale", None).isoformat() if getattr(r, "last_sale", None) else None),
            "reason": reason,
        }
        if want_group:
            item["warehouse_name"] = getattr(r, "warehouse_name", None) or "—"
        data.append(item)
    return {
        "data": data,
        "can_group_by_warehouse": can_group_by_wh,
        "meta": {
            "start_date": sd.isoformat(),
            "end_date": ed.isoformat(),
            "total_revenue": round(total_revenue, 2),
            "total_qty": total_qty,
            "count": len(data),
            "warehouse_id": int(warehouse_id) if warehouse_id else None,
            "group_by_warehouse": bool(group_by_warehouse and can_group_by_wh),
        },
    }


def partner_balance_report_ils(partner_ids: list = None) -> Dict:
    """تقرير أرصدة الشركاء بالشيكل"""
    try:
        from utils import get_entity_balance_in_ils, format_currency_in_ils
        from models import Partner

        if partner_ids is None:
            partners = db.session.query(Partner).all()
            partner_ids = [p.id for p in partners]

        report_data = []
        total_balance_ils = Decimal("0.00")

        for partner_id in partner_ids:
            partner = db.session.get(Partner, partner_id)
            if not partner:
                continue

            balance_ils = get_entity_balance_in_ils("PARTNER", partner_id)

            report_data.append({
                'partner_id': partner_id,
                'partner_name': partner.name,
                'partner_currency': partner.currency,
                'balance_ils': balance_ils,
                'formatted_balance': format_currency_in_ils(balance_ils),
                'share_percentage': partner.share_percentage,
                'contact_info': partner.contact_info
            })

            total_balance_ils += balance_ils

        return {
            'report_type': 'partner_balance_report_ils',
            'base_currency': 'ILS',
            'total_partners': len(partner_ids),
            'total_balance_ils': total_balance_ils,
            'formatted_total': format_currency_in_ils(total_balance_ils),
            'partners': report_data,
            'generated_at': datetime.utcnow()
        }
    except Exception as e:
        return {
            'error': str(e),
            'generated_at': datetime.utcnow()
        }
