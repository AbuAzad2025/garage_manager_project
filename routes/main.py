# routes/main.py
from __future__ import annotations
import os
import sqlite3
from datetime import date, datetime, timedelta, time

from flask import Blueprint, current_app, flash, redirect, render_template, send_file, send_from_directory, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, case

from extensions import db
from forms import RestoreForm
from models import (
    ExchangeTransaction,
    Note,
    Product,
    Sale,
    ServiceRequest,
    Supplier,
    StockLevel,
    Payment,
    PaymentDirection,
    PaymentStatus,
)
from utils import permission_required
from reports import sales_report, ar_aging_report

main_bp = Blueprint("main", __name__, template_folder="templates")


def _has_perm(code: str) -> bool:
    try:
        fn = getattr(current_user, "has_permission", None)
        if callable(fn):
            return bool(fn(code))
    except Exception:
        pass
    return False

@main_bp.app_context_processor
def _inject_sidebar_helpers():
    def has_any(*codes) -> bool:
        return any(_has_perm(c) for c in codes)
    role_name = str(getattr(getattr(current_user, "role", None), "name", "")).lower()
    is_super = (role_name == "super_admin") or bool(getattr(current_user, "is_super_admin", False))
    return {
        "has_perm": _has_perm,
        "has_any": has_any,
        "shop_is_super_admin": is_super,
    }

@main_bp.route("/favicon.ico")
def favicon():
    return send_from_directory(current_app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon")

@main_bp.route("/", methods=["GET"], endpoint="dashboard")
@login_required
def dashboard():
    today = date.today()
    start = today - timedelta(days=6)
    end = today

    # حدود زمنية دقيقة لليوم والأسبوع (Exclusive للحد الأعلى)
    day_start_dt = datetime.combine(today, time.min)
    day_end_dt = datetime.combine(today + timedelta(days=1), time.min)
    week_start_dt = datetime.combine(start, time.min)
    week_end_dt = datetime.combine(end + timedelta(days=1), time.min)

    inv_rows = (
        db.session.query(Product, func.coalesce(func.sum(StockLevel.quantity), 0).label("on_hand_sum"))
        .outerjoin(StockLevel, StockLevel.product_id == Product.id)
        .group_by(Product.id)
        .all()
    )
    for p, qty in inv_rows:
        setattr(p, "on_hand", int(qty))
    low_stock = [p for p, qty in inv_rows if qty <= (p.min_qty or 0)]
    inventory_total = int(sum(qty for _, qty in inv_rows))

    pending_exchanges = ExchangeTransaction.query.filter_by(direction="OUT").count()
    partner_stock = (db.session.query(func.count(Product.id)).join(Supplier, Supplier.id == Product.supplier_local_id).scalar() or 0)

    recent_sales = []
    today_revenue = 0.0
    revenue_labels = []
    revenue_values = []
    week_revenue = 0.0
    if _has_perm("manage_sales"):
        recent_sales = Sale.query.order_by(Sale.sale_date.desc()).limit(5).all()
        try:
            srep = sales_report(start, end) or {}
        except Exception:
            srep = {}
        revenue_labels = srep.get("daily_labels", [])
        revenue_values = srep.get("daily_values", [])
        week_revenue = float(srep.get("total_revenue", 0) or 0)
        # حساب إيرادات اليوم مع تحويل العملات للشيكل
        today_sales = Sale.query.filter(
            Sale.status == "CONFIRMED",
            Sale.sale_date >= day_start_dt,
            Sale.sale_date < day_end_dt,
        ).all()

        today_revenue = 0.0
        for sale in today_sales:
            try:
                from models import fx_rate
                amount = float(sale.total_amount or 0)
                if sale.currency and sale.currency != 'ILS':
                    rate = fx_rate(sale.currency, 'ILS', sale.sale_date, raise_on_missing=False)
                    if rate > 0:
                        amount = float(amount * rate)
                today_revenue += amount
            except Exception as e:
                today_revenue += float(sale.total_amount or 0)

    # حساب الدفعات مع تحويل العملات للشيكل
    today_incoming = 0.0
    today_outgoing = 0.0
    week_incoming = 0.0
    week_outgoing = 0.0

    # الدفعات اليومية
    today_payments = Payment.query.filter(
        Payment.payment_date >= day_start_dt,
        Payment.payment_date < day_end_dt,
        Payment.status == PaymentStatus.COMPLETED.value,
    ).all()

    for payment in today_payments:
        try:
            from models import fx_rate
            from decimal import Decimal
            amount = float(payment.total_amount or 0)

            # استخدام fx_rate_used إذا كان موجوداً
            if payment.fx_rate_used:
                fx_rate_value = float(payment.fx_rate_used) if isinstance(payment.fx_rate_used, Decimal) else payment.fx_rate_used
                amount *= float(fx_rate_value)
            elif payment.currency and payment.currency != 'ILS':
                rate = fx_rate(payment.currency, 'ILS', payment.payment_date, raise_on_missing=False)
                if rate > 0:
                    amount = float(amount * float(rate))

            if payment.direction == PaymentDirection.IN.value:
                today_incoming += amount
            else:
                today_outgoing += amount
        except Exception as e:
            if payment.direction == PaymentDirection.IN.value:
                today_incoming += float(payment.total_amount or 0)
            else:
                today_outgoing += float(payment.total_amount or 0)

    today_net = today_incoming - today_outgoing

    # الدفعات الأسبوعية
    week_payments = Payment.query.filter(
        Payment.payment_date >= week_start_dt,
        Payment.payment_date < week_end_dt,
        Payment.status == PaymentStatus.COMPLETED.value,
    ).all()

    for payment in week_payments:
        try:
            from models import fx_rate
            from decimal import Decimal
            amount = float(payment.total_amount or 0)

            # استخدام fx_rate_used إذا كان موجوداً
            if payment.fx_rate_used:
                fx_rate_value = float(payment.fx_rate_used) if isinstance(payment.fx_rate_used, Decimal) else payment.fx_rate_used
                amount *= float(fx_rate_value)
            elif payment.currency and payment.currency != 'ILS':
                rate = fx_rate(payment.currency, 'ILS', payment.payment_date, raise_on_missing=False)
                if rate > 0:
                    amount = float(amount * float(rate))

            if payment.direction == PaymentDirection.IN.value:
                week_incoming += amount
            else:
                week_outgoing += amount
        except Exception as e:
            if payment.direction == PaymentDirection.IN.value:
                week_incoming += float(payment.total_amount or 0)
            else:
                week_outgoing += float(payment.total_amount or 0)

    week_net = week_incoming - week_outgoing

    pay_rows = (
        db.session.query(
            func.date(Payment.payment_date).label("day"),
            func.coalesce(
                func.sum(
                    case(
                        (Payment.direction == PaymentDirection.IN.value, Payment.total_amount),
                        else_=0,
                    )
                ),
                0,
            ).label("incoming"),
            func.coalesce(
                func.sum(
                    case(
                        (Payment.direction == PaymentDirection.OUT.value, Payment.total_amount),
                        else_=0,
                    )
                ),
                0,
            ).label("outgoing"),
        )
        .filter(
            Payment.payment_date >= week_start_dt,
            Payment.payment_date < week_end_dt,
            Payment.status == PaymentStatus.COMPLETED.value,
        )
        .group_by("day")
        .order_by("day")
        .all()
    )
    payments_day_labels = [str(r.day) for r in pay_rows]
    payments_in_values = [float(r.incoming or 0) for r in pay_rows]
    payments_out_values = [float(r.outgoing or 0) for r in pay_rows]
    payments_net_values = [i - o for i, o in zip(payments_in_values, payments_out_values)]

    recent_services = []
    if _has_perm("manage_service"):
        q = ServiceRequest.query
        if current_user.role and (current_user.role.name or "").lower() == "mechanic":
            q = q.filter_by(mechanic_id=current_user.id)
        done_statuses = ("COMPLETED", "CANCELLED", "CLOSED", "DELIVERED", "FINISHED")
        q = q.filter(~ServiceRequest.status.in_(done_statuses)).order_by(ServiceRequest.created_at.desc())
        recent_services = q.all()
        for s in recent_services:
            if not hasattr(s, "started_at"):
                s.started_at = getattr(s, "start_time", None)

    recent_notes = []
    service_metrics = {"day_labels": [], "day_counts": []}
    customer_metrics = {}
    if _has_perm("view_reports"):
        rows = (
            db.session.query(func.date(ServiceRequest.start_time).label("day"), func.count(ServiceRequest.id).label("cnt"))
            .filter(ServiceRequest.start_time >= week_start_dt, ServiceRequest.start_time < week_end_dt)
            .group_by("day")
            .order_by("day")
            .all()
        )
        service_metrics = {
            "day_labels": [str(r.day) for r in rows],
            "day_counts": [int(r.cnt) for r in rows],
        }
        recent_notes = Note.query.order_by(Note.created_at.desc()).limit(5).all()
        try:
            customer_metrics = ar_aging_report(start, end)
        except Exception:
            customer_metrics = {}

    return render_template(
        "dashboard.html",
        low_stock=low_stock,
        inventory_total=inventory_total,
        pending_exchanges=pending_exchanges,
        partner_stock=partner_stock,
        today_revenue=today_revenue,
        revenue_labels=revenue_labels,
        revenue_values=revenue_values,
        week_revenue=week_revenue,
        recent_sales=recent_sales,
        recent_services=recent_services,
        service_metrics=service_metrics,
        recent_notes=recent_notes,
        customer_metrics=customer_metrics,
        today_incoming=today_incoming,
        today_outgoing=today_outgoing,
        today_net=today_net,
        week_incoming=week_incoming,
        week_outgoing=week_outgoing,
        week_net=week_net,
        payments_day_labels=payments_day_labels,
        payments_in_values=payments_in_values,
        payments_out_values=payments_out_values,
        payments_net_values=payments_net_values,
    )

@main_bp.route("/backup_db", methods=["GET"], endpoint="backup_db")
@login_required
@permission_required("backup_database")
def backup_db():
    is_prod = (current_app.config.get("ENV") == "production" or current_app.config.get("FLASK_ENV") == "production")
    role_name = str(getattr(getattr(current_user, "role", None), "name", "")).lower()
    if is_prod and role_name != "super_admin":
        flash("❌ غير مسموح بالنسخ الاحتياطي في بيئة الإنتاج إلا لمستخدم super_admin فقط.", "danger")
        return redirect(url_for("main.dashboard"))

    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    db_dir = current_app.config.get("BACKUP_DB_DIR")
    sql_dir = current_app.config.get("BACKUP_SQL_DIR")
    os.makedirs(db_dir, exist_ok=True)
    os.makedirs(sql_dir, exist_ok=True)

    if not uri.startswith("sqlite:///"):
        flash("قاعدة البيانات ليست SQLite.", "warning")
        return redirect(url_for("main.dashboard")), 303

    db_path = uri.replace("sqlite:///", "")
    if not db_path or not os.path.exists(db_path):
        raw = db.engine.raw_connection()
        sql_path = os.path.join(sql_dir, f"backup_{ts}.sql")
        try:
            with open(sql_path, "w", encoding="utf-8") as f:
                for line in raw.iterdump():
                    f.write(f"{line}\n")
        finally:
            raw.close()
        return send_file(sql_path, as_attachment=True, download_name=os.path.basename(sql_path))

    db_out = os.path.join(db_dir, f"backup_{ts}.db")
    sql_out = os.path.join(sql_dir, f"backup_{ts}.sql")

    db.session.commit()
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(db_out)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()

    conn = sqlite3.connect(db_path)
    try:
        with open(sql_out, "w", encoding="utf-8") as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
    finally:
        conn.close()

    return send_file(db_out, as_attachment=True, download_name=os.path.basename(db_out))

@main_bp.route("/restore_db", methods=["GET", "POST"], endpoint="restore_db")
@login_required
@permission_required("restore_database")
def restore_db():
    is_prod = (current_app.config.get("ENV") == "production" or current_app.config.get("FLASK_ENV") == "production")
    role_name = str(getattr(getattr(current_user, "role", None), "name", "")).lower()
    if is_prod and role_name != "super_admin":
        flash("❌ غير مسموح بالاستعادة في بيئة الإنتاج إلا لمستخدم super_admin فقط.", "danger")
        return redirect(url_for("main.dashboard"))

    form = RestoreForm()
    if form.validate_on_submit():
        uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if not uri.startswith("sqlite:///"):
            flash("قاعدة البيانات ليست SQLite.", "warning")
            return redirect(url_for("main.restore_db"))
        db_path = uri.replace("sqlite:///", "")
        try:
            db.session.commit()
            db.session.remove()
            db.engine.dispose()
            form.db_file.data.save(db_path)
            flash("✅ تمت الاستعادة بنجاح. قد تحتاج لإعادة تشغيل التطبيق.", "success")
            return redirect(url_for("main.dashboard"))
        except Exception:
            flash("❌ خطأ أثناء الاستعادة.", "danger")
            return redirect(url_for("main.restore_db"))
    return render_template("restore_db.html", form=form)
