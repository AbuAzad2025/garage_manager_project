# File: reports.py

from datetime import date
from sqlalchemy import and_, func, cast, Date, Numeric
from sqlalchemy.orm import joinedload
from extensions import db, mail
from models import Customer, Expense, OnlinePreOrder, Payment, Sale, ServiceRequest, Invoice


def advanced_report(model, joins=None, date_field=None, start_date=None, end_date=None,
                    filters=None, like_filters=None, columns=None, group_by=None, aggregates=None):
    """دالة عامة لإنشاء التقارير مع فلترة وتجميع ديناميكي"""
    try:
        q = model.query
        if joins:
            for rel in joins:
                q = q.options(joinedload(rel))

        # فلترة التاريخ
        if date_field and (start_date or end_date):
            field = getattr(model, date_field, None)
            if not field:
                raise ValueError(f"Invalid date field: {date_field}")
            if start_date and end_date:
                q = q.filter(cast(field, Date).between(start_date, end_date))
            elif start_date:
                q = q.filter(cast(field, Date) >= start_date)
            else:
                q = q.filter(cast(field, Date) <= end_date)

        # فلترة دقيقة
        if filters:
            for fname, value in filters.items():
                field = getattr(model, fname, None)
                if field is not None:
                    if hasattr(value, '__iter__') and not isinstance(value, str):
                        q = q.filter(field.in_(value))
                    else:
                        q = q.filter(field == value)

        # فلترة like
        if like_filters:
            for fname, pattern in like_filters.items():
                field = getattr(model, fname, None)
                if field is not None:
                    q = q.filter(field.ilike(f"%{pattern}%"))

        if group_by:
            gb = [getattr(model, f) for f in group_by if hasattr(model, f)]
            q = q.group_by(*gb)

        # تجهيز البيانات
        data = []
        for obj in q.all():
            row = {col: getattr(obj, col, None) for col in (columns or obj.__table__.columns.keys())}
            data.append(row)

        # الملخص
        summary = {}
        if aggregates:
            for func_name, fields in aggregates.items():
                for f in fields:
                    fld = getattr(model, f, None)
                    if fld:
                        agg_func = getattr(func, func_name, None)
                        if agg_func:
                            summary[f'{func_name}_{f}'] = db.session.query(agg_func(fld)).scalar() or 0

        return {'data': data, 'summary': summary}

    except Exception as e:
        raise RuntimeError(f"Report generation failed: {e}")


# ✅ تقارير محددة
def expense_report(start_date: date, end_date: date):
    return advanced_report(
        Expense, date_field='date', start_date=start_date, end_date=end_date,
        aggregates={'sum': ['amount'], 'count': ['id']}
    )


def shop_report(start_date: date, end_date: date):
    return advanced_report(
        OnlinePreOrder, date_field='created_at', start_date=start_date, end_date=end_date,
        aggregates={'sum': ['prepaid_amount', 'total_amount'], 'count': ['id']}
    )


def sales_report(start_date: date, end_date: date):
    """تقرير المبيعات محسّن - يستخدم حقل total_amount الفعلي بدل الـ hybrid property"""
    try:
        q = db.session.query(
            cast(Sale.sale_date, Date).label('day'),
            func.sum(func.coalesce(Sale.total_amount, 0)).label('revenue')
        ).filter(cast(Sale.sale_date, Date).between(start_date, end_date)) \
         .group_by('day').order_by('day')

        rows = q.all()
        return {
            'daily_labels': [r.day.strftime('%Y-%m-%d') for r in rows],
            'daily_values': [float(r.revenue or 0) for r in rows],
            'total_revenue': sum(float(r.revenue or 0) for r in rows)
        }
    except Exception as e:
        raise RuntimeError(f"Sales report failed: {e}")


def service_report(start_date: date, end_date: date):
    return advanced_report(
        ServiceRequest, date_field='start_time', start_date=start_date, end_date=end_date,
        aggregates={'count': ['id']}
    )


def ar_aging_report(start_date: date, end_date: date):
    """تقرير أعمار الذمم"""
    try:
        q = db.session.query(
            Customer.name,
            (func.coalesce(func.sum(Invoice.total_amount), 0) -
             func.coalesce(func.sum(Payment.total_amount), 0)).label('balance')
        ).outerjoin(Invoice, Invoice.customer_id == Customer.id) \
         .outerjoin(Payment, Payment.customer_id == Customer.id) \
         .group_by(Customer.name)

        return {'data': [{'customer': name, 'balance': float(bal or 0)} for name, bal in q.all()]}
    except Exception as e:
        raise RuntimeError(f"AR aging report failed: {e}")
