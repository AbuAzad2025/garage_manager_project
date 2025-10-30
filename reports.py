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
        import utils
        
        if customer_ids is None:
            customers = db.session.query(Customer).all()
            customer_ids = [c.id for c in customers]
        
        report_data = []
        total_balance_ils = Decimal("0.00")
        
        for customer_id in customer_ids:
            customer = db.session.get(Customer, customer_id)
            if not customer:
                continue
            
            balance_ils = utils.get_entity_balance_in_ils("CUSTOMER", customer_id)
            
            report_data.append({
                'customer_id': customer_id,
                'customer_name': customer.name,
                'customer_currency': customer.currency,
                'balance_ils': balance_ils,
                'formatted_balance': utils.format_currency_in_ils(balance_ils),
                'credit_limit': customer.credit_limit,
                'credit_status': customer.credit_status
            })
            
            total_balance_ils += balance_ils
        
        return {
            'report_type': 'customer_balance_report_ils',
            'base_currency': 'ILS',
            'total_customers': len(customer_ids),
            'total_balance_ils': total_balance_ils,
            'formatted_total': utils.format_currency_in_ils(total_balance_ils),
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
        import utils
        
        if supplier_ids is None:
            suppliers = db.session.query(Supplier).all()
            supplier_ids = [s.id for s in suppliers]
        
        report_data = []
        total_balance_ils = Decimal("0.00")
        
        for supplier_id in supplier_ids:
            supplier = db.session.get(Supplier, supplier_id)
            if not supplier:
                continue
            
            balance_ils = utils.get_entity_balance_in_ils("SUPPLIER", supplier_id)
            
            report_data.append({
                'supplier_id': supplier_id,
                'supplier_name': supplier.name,
                'supplier_currency': supplier.currency,
                'balance_ils': balance_ils,
                'formatted_balance': utils.format_currency_in_ils(balance_ils),
                'is_local': supplier.is_local
            })
            
            total_balance_ils += balance_ils
        
        return {
            'report_type': 'supplier_balance_report_ils',
            'base_currency': 'ILS',
            'total_suppliers': len(supplier_ids),
            'total_balance_ils': total_balance_ils,
            'formatted_total': utils.format_currency_in_ils(total_balance_ils),
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
        import utils
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
        method_breakdown = {}  # تجميع حسب طريقة الدفع
        
        for payment in payments:
            amount = Decimal(str(payment.total_amount or 0))
            currency = payment.currency or "ILS"
            direction = payment.direction
            method = payment.method or "UNKNOWN"  # طريقة الدفع
            
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
            
            # تجميع حسب طريقة الدفع
            if method not in method_breakdown:
                method_breakdown[method] = Decimal("0.00")
            method_breakdown[method] += amount_ils
        
        net_balance_ils = total_incoming_ils - total_outgoing_ils
        
        # تحويل method_breakdown إلى lists للقالب
        methods = list(method_breakdown.keys())
        totals_by_method = [float(method_breakdown[m]) for m in methods]
        
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
                'formatted_incoming': utils.format_currency_in_ils(total_incoming_ils),
                'formatted_outgoing': utils.format_currency_in_ils(total_outgoing_ils),
                'formatted_net': utils.format_currency_in_ils(net_balance_ils)
            },
            'currency_breakdown': currency_breakdown,
            'methods': methods,
            'totals_by_method': totals_by_method,
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
        import utils
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
                'formatted_total': utils.format_currency_in_ils(total_revenue_ils),
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
    
    # جلب كل المبيعات مع تحويل العملات
    from models import convert_amount
    
    sales = Sale.query.filter(*filters).filter(
        Sale.status.in_(allowed_statuses),
        ~Sale.status.in_(excluded_statuses)
    ).all()
    
    day_to_sum: dict[str, Decimal] = {}
    for sale in sales:
        amt = Decimal(str(sale.total_amount or 0))
        
        if sale.currency == "ILS":
            amt_ils = amt
        else:
            try:
                amt_ils = convert_amount(amt, sale.currency, "ILS", sale.sale_date)
            except:
                amt_ils = Decimal('0.00')
        
        # تحديد اليوم
        if sale.sale_date:
            day_key = sale.sale_date.date().isoformat() if hasattr(sale.sale_date, 'date') else str(sale.sale_date)
        else:
            day_key = datetime.now().date().isoformat()
        
        if day_key not in day_to_sum:
            day_to_sum[day_key] = Decimal('0.00')
        day_to_sum[day_key] += amt_ils
    
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
    """تقرير ملخص المدفوعات مع تحويل العملات"""
    from models import convert_amount
    from collections import defaultdict
    
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
    
    # جلب الدفعات مع Splits
    payments_with_splits = (
        db.session.query(Payment, PaymentSplit)
        .join(PaymentSplit, PaymentSplit.payment_id == Payment.id)
        .filter(*base_filters)
        .all()
    )
    
    # جلب الدفعات بدون Splits
    payments_no_splits = (
        db.session.query(Payment)
        .outerjoin(PaymentSplit, PaymentSplit.payment_id == Payment.id)
        .filter(*base_filters)
        .filter(PaymentSplit.id.is_(None))
        .all()
    )
    
    agg = defaultdict(lambda: Decimal('0.00'))
    
    # معالجة الدفعات مع Splits
    for payment, split in payments_with_splits:
        method = str(split.method) if split.method else "other"
        amt = Decimal(str(split.amount or 0))
        
        if payment.currency == "ILS":
            amt_ils = amt
        else:
            try:
                amt_ils = convert_amount(amt, payment.currency, "ILS", payment.payment_date)
            except:
                amt_ils = Decimal('0.00')
        
        agg[method] += amt_ils
    
    # معالجة الدفعات بدون Splits
    for payment in payments_no_splits:
        method = str(payment.method) if payment.method else "other"
        amt = Decimal(str(payment.total_amount or 0))
        
        if payment.currency == "ILS":
            amt_ils = amt
        else:
            try:
                amt_ils = convert_amount(amt, payment.currency, "ILS", payment.payment_date)
            except:
                amt_ils = Decimal('0.00')
        
        agg[method] += amt_ils
    
    # تحويل للصيغة النهائية
    methods = sorted(agg.keys())
    totals = [round(float(agg[m]), 2) for m in methods]
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
    from decimal import Decimal
    
    services_filtered = db.session.query(ServiceRequest).filter(date_cond).all()
    revenue = Decimal('0.00')
    parts = Decimal('0.00')
    labor = Decimal('0.00')
    
    for srv in services_filtered:
        if srv.currency == "ILS":
            revenue += Decimal(str(srv.total_amount or 0))
            parts += Decimal(str(srv.parts_total or 0))
            labor += Decimal(str(srv.labor_total or 0))
        else:
            try:
                revenue += convert_amount(Decimal(str(srv.total_amount or 0)), srv.currency, "ILS", srv.received_at)
                parts += convert_amount(Decimal(str(srv.parts_total or 0)), srv.currency, "ILS", srv.received_at)
                labor += convert_amount(Decimal(str(srv.labor_total or 0)), srv.currency, "ILS", srv.received_at)
            except:
                pass
    
    revenue = float(revenue)
    parts = float(parts)
    labor = float(labor)
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
    from decimal import Decimal
    
    as_of = _parse_date_like(end_date) or date.today()
    
    invoices = db.session.query(Invoice).filter(
        Invoice.customer_id.isnot(None),
        Invoice.cancelled_at.is_(None)
    ).all()
    
    bucket_keys = ("0-30", "31-60", "61-90", "90+")
    acc = defaultdict(lambda: {k: Decimal('0.00') for k in bucket_keys} | {"total": Decimal('0.00')})
    
    for inv in invoices:
        inv_amt = Decimal(str(inv.total_amount or 0))
        if inv.currency != "ILS":
            try:
                inv_amt = convert_amount(inv_amt, inv.currency, "ILS", inv.invoice_date)
            except:
                continue
        
        payments = db.session.query(Payment).filter(
            Payment.invoice_id == inv.id,
            Payment.status == PaymentStatus.COMPLETED.value,
            Payment.direction == PaymentDirection.IN.value,
            cast(Payment.payment_date, Date) <= as_of
        ).all()
        
        paid_amt = Decimal('0.00')
        for p in payments:
            p_amt = Decimal(str(p.total_amount or 0))
            if p.currency != "ILS":
                try:
                    p_amt = convert_amount(p_amt, p.currency, "ILS", p.payment_date)
                except:
                    continue
            paid_amt += p_amt
        
        outstanding = inv_amt - paid_amt
        if outstanding <= 0:
            continue
        
        cust = db.session.get(Customer, inv.customer_id)
        if not cust:
            continue
        
        ref_dt = inv.invoice_date or inv.created_at
        if isinstance(ref_dt, datetime):
            ref_d = ref_dt.date()
        elif isinstance(ref_dt, date):
            ref_d = ref_dt
        else:
            ref_d = as_of
        
        days = max((as_of - ref_d).days, 0) if (as_of and ref_d) else 0
        b = age_bucket(days)
        acc[cust.name][b] += outstanding
        acc[cust.name]["total"] += outstanding
    
    data = []
    for name in sorted(acc.keys()):
        item = {
            "customer": name,
            "balance": float(round(acc[name]["total"], 2)),
            "buckets": {k: float(round(acc[name][k], 2)) for k in bucket_keys},
        }
        data.append(item)
    
    totals = {k: Decimal('0.00') for k in bucket_keys} | {"total": Decimal('0.00')}
    for v in acc.values():
        for k in bucket_keys:
            totals[k] += v[k]
        totals["total"] += v["total"]
    totals = {k: float(round(v, 2)) for k, v in totals.items()}
    
    return {"as_of": as_of.isoformat(), "data": data, "totals": totals}

def ap_aging_report(start_date=None, end_date=None):
    from decimal import Decimal
    
    as_of = _parse_date_like(end_date) or date.today()
    
    invoices = db.session.query(Invoice).filter(
        Invoice.supplier_id.isnot(None),
        Invoice.cancelled_at.is_(None)
    ).all()
    
    bucket_keys = ("0-30", "31-60", "61-90", "90+")
    acc = defaultdict(lambda: {k: Decimal('0.00') for k in bucket_keys} | {"total": Decimal('0.00')})
    
    for inv in invoices:
        inv_amt = Decimal(str(inv.total_amount or 0))
        if inv.currency != "ILS":
            try:
                inv_amt = convert_amount(inv_amt, inv.currency, "ILS", inv.invoice_date)
            except:
                continue
        
        payments = db.session.query(Payment).filter(
            Payment.invoice_id == inv.id,
            Payment.status == PaymentStatus.COMPLETED.value,
            Payment.direction == PaymentDirection.OUT.value,
            cast(Payment.payment_date, Date) <= as_of
        ).all()
        
        paid_amt = Decimal('0.00')
        for p in payments:
            p_amt = Decimal(str(p.total_amount or 0))
            if p.currency != "ILS":
                try:
                    p_amt = convert_amount(p_amt, p.currency, "ILS", p.payment_date)
                except:
                    continue
            paid_amt += p_amt
        
        outstanding = inv_amt - paid_amt
        if outstanding <= 0:
            continue
        
        supplier = db.session.get(Supplier, inv.supplier_id)
        if not supplier:
            continue
        
        ref_dt = inv.invoice_date or inv.created_at
        if isinstance(ref_dt, datetime):
            ref_d = ref_dt.date()
        elif isinstance(ref_dt, date):
            ref_d = ref_dt
        else:
            ref_d = as_of
        
        days = max((as_of - ref_d).days, 0) if (as_of and ref_d) else 0
        b = age_bucket(days)
        acc[supplier.name][b] += outstanding
        acc[supplier.name]["total"] += outstanding
    
    data = []
    for name in sorted(acc.keys()):
        item = {
            "supplier": name,
            "balance": float(round(acc[name]["total"], 2)),
            "buckets": {k: float(round(acc[name][k], 2)) for k in bucket_keys},
        }
        data.append(item)
    
    totals = {k: Decimal('0.00') for k in bucket_keys} | {"total": Decimal('0.00')}
    for v in acc.values():
        for k in bucket_keys:
            totals[k] += v[k]
        totals["total"] += v["total"]
    totals = {k: float(round(v, 2)) for k, v in totals.items()}
    
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
    rows_raw = q.all()
    
    rows_with_ils = []
    for r in rows_raw:
        lines = db.session.query(SaleLine).join(Sale).filter(
            SaleLine.product_id == r.product_id,
            Sale.status == SaleStatus.CONFIRMED.value,
            lower, upper
        ).all()
        
        revenue_ils = Decimal('0.00')
        for line in lines:
            sale = line.sale
            line_amt = Decimal(str(line.quantity or 0)) * Decimal(str(line.unit_price or 0))
            line_amt *= (Decimal('1') - Decimal(str(line.discount_rate or 0)) / Decimal('100'))
            line_amt *= (Decimal('1') + Decimal(str(line.tax_rate or 0)) / Decimal('100'))
            
            if sale.currency == "ILS":
                revenue_ils += line_amt
            else:
                try:
                    revenue_ils += convert_amount(line_amt, sale.currency, "ILS", sale.sale_date)
                except:
                    pass
        
        rows_with_ils.append({
            "product_id": r.product_id,
            "name": r.name,
            "qty": r.qty,
            "revenue": float(revenue_ils),
            "revenue_ils": float(revenue_ils),
            "avg_unit_price": float(r.avg_unit_price or 0),
            "orders_count": r.orders_count,
            "first_sale": r.first_sale,
            "last_sale": r.last_sale,
            "warehouse_name": getattr(r, "warehouse_name", None) if want_group else None
        })
    
    rows_with_ils.sort(key=lambda x: x["revenue_ils"], reverse=True)
    rows = rows_with_ils[:int(limit or 20)]
    
    total_revenue = float(sum(r["revenue_ils"] for r in rows))
    total_qty = int(sum(r["qty"] for r in rows))
    max_qty = max((r["qty"] for r in rows), default=0)
    def _rank_label(idx: int) -> str:
        return ("الأول" if idx == 1 else "الثاني" if idx == 2 else "الثالث" if idx == 3 else f"المرتبة {idx}")
    data: list[dict] = []
    for i, r in enumerate(rows, start=1):
        if isinstance(r, dict):
            qty = int(r.get("qty", 0) or 0)
            rev = float(r.get("revenue_ils", 0) or 0)
            gross = 0.0
            discount = 0.0
            orders_count = int(r.get("orders_count", 0) or 0)
            avg_price = float(r.get("avg_unit_price", 0) or 0)
        else:
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
            if isinstance(r, dict):
                item["warehouse_name"] = r.get("warehouse_name") or "—"
            else:
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
        import utils
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

            balance_ils = utils.get_entity_balance_in_ils("PARTNER", partner_id)

            report_data.append({
                'partner_id': partner_id,
                'partner_name': partner.name,
                'partner_currency': partner.currency,
                'balance_ils': balance_ils,
                'formatted_balance': utils.format_currency_in_ils(balance_ils),
                'share_percentage': partner.share_percentage,
                'contact_info': partner.contact_info
            })

            total_balance_ils += balance_ils

        return {
            'report_type': 'partner_balance_report_ils',
            'base_currency': 'ILS',
            'total_partners': len(partner_ids),
            'total_balance_ils': total_balance_ils,
            'formatted_total': utils.format_currency_in_ils(total_balance_ils),
            'partners': report_data,
            'generated_at': datetime.utcnow()
        }
    except Exception as e:
        return {
            'error': str(e),
            'generated_at': datetime.utcnow()
        }
