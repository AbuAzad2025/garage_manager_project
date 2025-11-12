
from __future__ import annotations
import os
import sqlite3
from datetime import date, datetime, timedelta, time
from decimal import Decimal
from typing import List, Tuple

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, send_file, send_from_directory, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, case
from sqlalchemy.orm import load_only, joinedload

from extensions import db
from forms import RestoreForm
from models import (
    Check,
    CheckStatus,
    Customer,
    ExchangeTransaction,
    Invoice,
    Note,
    Payment,
    PaymentDirection,
    PaymentStatus,
    Product,
    Sale,
    SaleStatus,
    ServiceRequest,
    Supplier,
    Partner,
    StockLevel,
    Expense,
)
from models import convert_amount, fx_rate
import utils
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
    today_sales_rows: List[Tuple] = []
    today_revenue = Decimal('0.00')
    revenue_labels = []
    revenue_values = []
    week_revenue = 0.0

    # حساب الوارد والصادر - يشمل المبيعات + الدفعات
    fx_cache: dict[tuple[str, date | None], Decimal] = {}

    def _to_ils(amount, currency, fx_used, at_dt) -> Decimal:
        value = Decimal(str(amount or 0))
        code = (currency or "ILS").upper()
        if code == "ILS":
            return value
        if fx_used:
            try:
                return value * Decimal(str(fx_used))
            except Exception:
                pass
        try:
            key = (code, at_dt.date() if isinstance(at_dt, datetime) else None)
            rate = fx_cache.get(key)
            if rate is None:
                rate = fx_rate(code, "ILS", at_dt, raise_on_missing=False)
                if rate and rate > 0:
                    fx_cache[key] = Decimal(str(rate))
                else:
                    rate = None
            if rate and rate > 0:
                return value * Decimal(str(rate))
        except Exception:
            pass
        try:
            return convert_amount(value, code, "ILS", at_dt)
        except Exception:
            return value

    if _has_perm("manage_sales"):
        recent_sales = (
            Sale.query.options(
                load_only(
                    Sale.id,
                    Sale.sale_number,
                    Sale.sale_date,
                    Sale.total_amount,
                    Sale.currency,
                    Sale.customer_id,
                    Sale.status,
                    Sale.payment_status,
                ),
                joinedload(Sale.customer).load_only(Customer.name),
            )
            .order_by(Sale.sale_date.desc())
            .limit(5)
            .all()
        )
        try:
            srep = sales_report(start, end) or {}
        except Exception:
            srep = {}
        revenue_labels = srep.get("daily_labels", [])
        revenue_values = srep.get("daily_values", [])
        week_revenue = float(srep.get("total_revenue", 0) or 0)
        today_sales_rows = (
            db.session.query(
                Sale.total_amount,
                Sale.currency,
                Sale.fx_rate_used,
                Sale.sale_date,
            )
            .filter(
                Sale.status == SaleStatus.CONFIRMED.value,
                Sale.sale_date >= day_start_dt,
                Sale.sale_date < day_end_dt,
            )
            .all()
        )

        for amt, currency, fx_used, sale_dt in today_sales_rows:
            today_revenue += _to_ils(amt, currency, fx_used, sale_dt)

    today_incoming = Decimal('0.00')
    today_outgoing = Decimal('0.00')
    week_incoming = Decimal('0.00')
    week_outgoing = Decimal('0.00')

    # 1️⃣ إضافة المبيعات المؤكدة لليوم (وارد)
    if _has_perm("manage_sales") and today_sales_rows:
        for amount, currency, fx_used, sale_dt in today_sales_rows:
            today_incoming += _to_ils(amount, currency, fx_used, sale_dt)
    
    # 2️⃣ إضافة الدفعات اليومية (وارد/صادر)
    today_payments = (
        db.session.query(
            Payment.total_amount,
            Payment.currency,
            Payment.fx_rate_used,
            Payment.payment_date,
            Payment.direction,
        )
        .filter(
        Payment.payment_date >= day_start_dt,
        Payment.payment_date < day_end_dt,
        Payment.status == PaymentStatus.COMPLETED.value,
        )
        .all()
    )

    for amount, currency, fx_used, pay_dt, direction in today_payments:
        try:
            amt_ils = _to_ils(amount, currency, fx_used, pay_dt)

            if direction == PaymentDirection.IN.value:
                today_incoming += amt_ils
            else:
                today_outgoing += amt_ils
        except Exception:
            pass
    
    # 3️⃣ إضافة المصاريف اليومية (صادر)
    today_expenses = (
        db.session.query(
            Expense.amount,
            Expense.currency,
            Expense.date,
        )
        .filter(
        Expense.date >= day_start_dt.date(),
        Expense.date < day_end_dt.date(),
        )
        .all()
    )
    
    for amount, currency, exp_date in today_expenses:
        try:
            today_outgoing += _to_ils(amount, currency, None, datetime.combine(exp_date, time.min))
        except Exception:
            pass
    
    # 4️⃣ إضافة فواتير الموردين المستحقة (صادر)
    today_invoices = (
        db.session.query(
            Invoice.total_amount,
            Invoice.currency,
            Invoice.fx_rate_used,
            Invoice.invoice_date,
        )
        .filter(
        Invoice.invoice_date >= day_start_dt,
        Invoice.invoice_date < day_end_dt,
        )
        .all()
    )
    
    for amount, currency, fx_used, inv_date in today_invoices:
        try:
            today_outgoing += _to_ils(amount, currency, fx_used, inv_date)
        except Exception:
            pass

    today_net = float(today_incoming - today_outgoing)
    today_revenue = float(today_revenue)
    today_incoming = float(today_incoming)
    today_outgoing = float(today_outgoing)

    # 3️⃣ حساب الوارد/الصادر الأسبوعي (مبيعات + دفعات)
    
    # المبيعات الأسبوعية
    if _has_perm("manage_sales"):
        week_sales_rows = (
            db.session.query(
                Sale.total_amount,
                Sale.currency,
                Sale.fx_rate_used,
                Sale.sale_date,
            )
            .filter(
            Sale.status == "CONFIRMED",
            Sale.sale_date >= week_start_dt,
            Sale.sale_date < week_end_dt,
            )
            .all()
        )
        
        for amount, currency, fx_used, sale_dt in week_sales_rows:
            week_incoming += _to_ils(amount, currency, fx_used, sale_dt)
    
    # الدفعات الأسبوعية
    week_payments = (
        db.session.query(
            Payment.total_amount,
            Payment.currency,
            Payment.fx_rate_used,
            Payment.payment_date,
            Payment.direction,
        )
        .filter(
        Payment.payment_date >= week_start_dt,
        Payment.payment_date < week_end_dt,
        Payment.status == PaymentStatus.COMPLETED.value,
        )
        .all()
    )

    for amount, currency, fx_used, pay_dt, direction in week_payments:
        try:
            amt_ils = _to_ils(amount, currency, fx_used, pay_dt)

            if direction == PaymentDirection.IN.value:
                week_incoming += amt_ils
            else:
                week_outgoing += amt_ils
        except Exception:
            pass
    
    # المصاريف الأسبوعية (صادر)
    week_expenses = (
        db.session.query(
            Expense.amount,
            Expense.currency,
            Expense.date,
        )
        .filter(
        Expense.date >= week_start_dt.date(),
        Expense.date < week_end_dt.date(),
        )
        .all()
    )
    
    for amount, currency, exp_date in week_expenses:
        try:
            week_outgoing += _to_ils(amount, currency, None, datetime.combine(exp_date, time.min))
        except Exception:
            pass
    
    # الفواتير الأسبوعية (صادر)
    week_invoices = (
        db.session.query(
            Invoice.total_amount,
            Invoice.currency,
            Invoice.fx_rate_used,
            Invoice.invoice_date,
        )
        .filter(
        Invoice.invoice_date >= week_start_dt,
        Invoice.invoice_date < week_end_dt,
        )
        .all()
    )
    
    for amount, currency, fx_used, inv_date in week_invoices:
        try:
            week_outgoing += _to_ils(amount, currency, fx_used, inv_date)
        except Exception:
            pass

    week_net = float(week_incoming - week_outgoing)
    week_incoming = float(week_incoming)
    week_outgoing = float(week_outgoing)

    # حساب الدفعات اليومية مع تحويل العملات
    from collections import defaultdict
    daily_payments = defaultdict(lambda: {'incoming': Decimal('0.00'), 'outgoing': Decimal('0.00')})
    
    all_week_payments = (
        db.session.query(
            Payment.total_amount,
            Payment.currency,
            Payment.fx_rate_used,
            Payment.payment_date,
            Payment.direction,
        )
        .filter(
        Payment.payment_date >= week_start_dt,
        Payment.payment_date < week_end_dt,
        Payment.status == PaymentStatus.COMPLETED.value
        )
        .all()
    )
    
    for amount, currency, fx_used, pay_dt, direction in all_week_payments:
        day_key = pay_dt.date() if pay_dt else today
        amt_ils = _to_ils(amount, currency, fx_used, pay_dt)
        
        if direction == PaymentDirection.IN.value:
            daily_payments[day_key]['incoming'] += amt_ils
        else:
            daily_payments[day_key]['outgoing'] += amt_ils
    
    payments_day_labels = sorted([str(d) for d in daily_payments.keys()])
    payments_in_values = [float(daily_payments[datetime.strptime(d, '%Y-%m-%d').date()]['incoming']) for d in payments_day_labels]
    payments_out_values = [float(daily_payments[datetime.strptime(d, '%Y-%m-%d').date()]['outgoing']) for d in payments_day_labels]
    payments_net_values = [i - o for i, o in zip(payments_in_values, payments_out_values)]

    dashboard_alerts: List[dict] = []
    now = datetime.utcnow()
    today = now.date()
    week_ahead = today + timedelta(days=7)

    try:
        overdue_checks = (
            Check.query.options(
                load_only(
                    Check.id,
                    Check.check_number,
                    Check.check_due_date,
                    Check.amount,
                    Check.currency,
                    Check.direction,
                    Check.fx_rate_issue,
                ),
                joinedload(Check.customer).load_only(Customer.name),
                joinedload(Check.supplier).load_only(Supplier.name),
                joinedload(Check.partner).load_only(Partner.name),
            )
            .filter(
                Check.is_archived.is_(False),
                Check.status == CheckStatus.PENDING.value,
                Check.check_due_date < now,
            )
            .order_by(Check.check_due_date.asc())
            .limit(5)
            .all()
        )

        for chk in overdue_checks:
            days_overdue = max((today - chk.check_due_date.date()).days, 0)
            amount_ils = _to_ils(chk.amount, chk.currency, chk.fx_rate_issue, chk.check_due_date)
            dashboard_alerts.append({
                "category": "الشيكات",
                "severity": "danger",
                "icon": "fas fa-money-check-alt",
                "title": f"شيك متأخر {days_overdue} يوم",
                "message": f"{chk.entity_name} - رقم {chk.check_number}",
                "amount_display": f"{float(amount_ils):,.2f} ₪",
                "link": url_for('checks.index'),
                "meta": chk.check_due_date.strftime('%Y-%m-%d'),
            })

        upcoming_checks = (
            Check.query.options(
                load_only(
                    Check.id,
                    Check.check_number,
                    Check.check_due_date,
                    Check.amount,
                    Check.currency,
                    Check.direction,
                    Check.fx_rate_issue,
                ),
                joinedload(Check.customer).load_only(Customer.name),
                joinedload(Check.supplier).load_only(Supplier.name),
                joinedload(Check.partner).load_only(Partner.name),
            )
            .filter(
                Check.is_archived.is_(False),
                Check.status == CheckStatus.PENDING.value,
                Check.check_due_date.between(now, datetime.combine(week_ahead, datetime.max.time())),
            )
            .order_by(Check.check_due_date.asc())
            .limit(5)
            .all()
        )

        for chk in upcoming_checks:
            days_left = max((chk.check_due_date.date() - today).days, 0)
            amount_ils = _to_ils(chk.amount, chk.currency, chk.fx_rate_issue, chk.check_due_date)
            dashboard_alerts.append({
                "category": "الشيكات",
                "severity": "warning",
                "icon": "fas fa-calendar-check",
                "title": f"شيك مستحق خلال {days_left} يوم",
                "message": f"{chk.entity_name} - رقم {chk.check_number}",
                "amount_display": f"{float(amount_ils):,.2f} ₪",
                "link": url_for('checks.index'),
                "meta": chk.check_due_date.strftime('%Y-%m-%d'),
            })
    except Exception as exc:
        current_app.logger.warning(f"Dashboard check alerts error: {exc}")

    try:
        due_ils_expr = func.sum(Sale.balance_due * func.coalesce(Sale.fx_rate_used, 1)).label("due_ils")
        customer_debts = (
            db.session.query(
                Customer.id,
                Customer.name,
                due_ils_expr,
                func.count(Sale.id).label("sale_count"),
                func.max(Sale.sale_date).label("last_sale"),
            )
            .join(Customer, Customer.id == Sale.customer_id)
            .filter(
                Sale.status == SaleStatus.CONFIRMED.value,
                Sale.balance_due > 0,
            )
            .group_by(Customer.id, Customer.name)
            .order_by(due_ils_expr.desc())
            .limit(5)
            .all()
        )

        for cust_id, cust_name, due_ils, sale_count, last_sale in customer_debts:
            if due_ils and due_ils > 0:
                dashboard_alerts.append({
                    "category": "الذمم",
                    "severity": "warning",
                    "icon": "fas fa-user-clock",
                    "title": f"دين على العميل {cust_name}",
                    "message": f"عدد الفواتير المفتوحة: {sale_count}",
                    "amount_display": f"{float(due_ils):,.2f} ₪",
                    "link": url_for('customers_bp.list_customers', name=cust_name),
                    "meta": last_sale.strftime('%Y-%m-%d') if last_sale else None,
                })
    except Exception as exc:
        current_app.logger.warning(f"Dashboard customer debt alerts error: {exc}")

    try:
        recent_expenses = (
            db.session.query(
                Expense.id,
                Expense.description,
                Expense.amount,
                Expense.currency,
                Expense.date,
            )
            .filter(
                Expense.date >= today - timedelta(days=7),
                Expense.amount > 0,
            )
            .order_by(Expense.amount.desc(), Expense.date.desc())
            .limit(5)
            .all()
        )

        expense_threshold = Decimal("5000")
        for exp_id, description, amount, currency, exp_date in recent_expenses:
            amount_ils = _to_ils(amount, currency, None, datetime.combine(exp_date, time.min))
            if amount_ils >= expense_threshold:
                dashboard_alerts.append({
                    "category": "المصاريف",
                    "severity": "info",
                    "icon": "fas fa-wallet",
                    "title": "مصروف مرتفع مسجل",
                    "message": description or f"مصروف رقم {exp_id}",
                    "amount_display": f"{float(amount_ils):,.2f} ₪",
                    "link": url_for('expenses_bp.list_expenses'),
                    "meta": exp_date.strftime('%Y-%m-%d'),
                })
    except Exception as exc:
        current_app.logger.warning(f"Dashboard expense alerts error: {exc}")

    severity_order = {"danger": 0, "warning": 1, "info": 2, "primary": 3}
    dashboard_alerts.sort(key=lambda item: (
        severity_order.get(item.get("severity"), 99),
        0 if item.get("category") == "الشيكات" else 1
    ))
    check_alerts = [a for a in dashboard_alerts if a.get("category") == "الشيكات"]
    general_alerts = [a for a in dashboard_alerts if a.get("category") != "الشيكات"]

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
        dashboard_alerts=dashboard_alerts,
        check_alerts=check_alerts,
        general_alerts=general_alerts,
    )

@main_bp.route("/backup_db", methods=["GET"], endpoint="backup_db")
@login_required
# @utils.permission_required("backup_database")  # Commented out - function not available
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
# @utils.permission_required("restore_database")  # Commented out - function not available
def restore_db():
    is_prod = (current_app.config.get("ENV") == "production" or current_app.config.get("FLASK_ENV") == "production")
    role_name = str(getattr(getattr(current_user, "role", None), "name", "")).lower()
    if is_prod and role_name != "super_admin":
        if request.is_json or request.headers.get('Accept') == 'application/json':
            return jsonify({"success": False, "message": "غير مسموح بالاستعادة في بيئة الإنتاج إلا لمستخدم super_admin فقط"}), 403
        flash("❌ غير مسموح بالاستعادة في بيئة الإنتاج إلا لمستخدم super_admin فقط.", "danger")
        return redirect(url_for("main.dashboard"))

    form = RestoreForm()
    if form.validate_on_submit() or (request.method == 'POST' and 'db_file' in request.files):
        uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if not uri.startswith("sqlite:///"):
            if request.is_json or request.headers.get('Accept') == 'application/json':
                return jsonify({"success": False, "message": "قاعدة البيانات ليست SQLite"}), 400
            flash("قاعدة البيانات ليست SQLite.", "warning")
            return redirect(url_for("main.restore_db"))
        db_path = uri.replace("sqlite:///", "")
        try:
            db_file = form.db_file.data if form.validate_on_submit() else request.files.get('db_file')
            if not db_file:
                raise ValueError("لم يتم تحديد ملف")
            
            db.session.commit()
            db.session.remove()
            db.engine.dispose()
            db_file.save(db_path)
            
            if request.is_json or request.headers.get('Accept') == 'application/json':
                return jsonify({"success": True, "message": "تمت الاستعادة بنجاح"}), 200
            flash("✅ تمت الاستعادة بنجاح. قد تحتاج لإعادة تشغيل التطبيق.", "success")
            return redirect(url_for("main.dashboard"))
        except Exception as e:
            if request.is_json or request.headers.get('Accept') == 'application/json':
                return jsonify({"success": False, "message": f"خطأ أثناء الاستعادة: {str(e)}"}), 500
            flash("❌ خطأ أثناء الاستعادة.", "danger")
            return redirect(url_for("main.restore_db"))
    return render_template("restore_db.html", form=form)

@main_bp.route("/automated-backup-status", methods=["GET"], endpoint="automated_backup_status")
@login_required
def automated_backup_status():
    role_name = str(getattr(getattr(current_user, "role", None), "name", "")).lower()
    if role_name not in ["super_admin", "owner"]:
        # إرجاع بيانات فارغة بدون خطأ للمستخدمين العاديين
        return jsonify({"enabled": False, "next_run": None, "schedule": "غير متاح"})
    
    from extensions import scheduler
    jobs = scheduler.get_jobs()
    backup_job = next((job for job in jobs if job.id == 'automated_daily_backup'), None)
    
    if backup_job:
        return jsonify({
            "enabled": True,
            "next_run": backup_job.next_run_time.isoformat() if backup_job.next_run_time else None,
            "schedule": "يومياً الساعة 3:00 صباحاً"
        })
    else:
        return jsonify({
            "enabled": False,
            "next_run": None,
            "schedule": "غير مفعّل"
        })

@main_bp.route("/toggle-automated-backup", methods=["POST"], endpoint="toggle_automated_backup")
@login_required
def toggle_automated_backup():
    role_name = str(getattr(getattr(current_user, "role", None), "name", "")).lower()
    if role_name != "super_admin":
        flash("❌ غير مسموح", "danger")
        return redirect(url_for("main.dashboard"))
    
    from extensions import scheduler
    jobs = scheduler.get_jobs()
    backup_job = next((job for job in jobs if job.id == 'automated_daily_backup'), None)
    
    if backup_job:
        scheduler.remove_job('automated_daily_backup')
        flash("✅ تم تعطيل النسخ الاحتياطي التلقائي", "success")
    else:
        scheduler.add_job(
            func=perform_automated_backup,
            trigger='cron',
            hour=3,
            minute=0,
            id='automated_daily_backup',
            name='النسخ الاحتياطي اليومي التلقائي',
            replace_existing=True
        )
        flash("✅ تم تفعيل النسخ الاحتياطي التلقائي (يومياً الساعة 3:00 صباحاً)", "success")
    
    return redirect(url_for("main.dashboard"))

def perform_automated_backup():
    with current_app.app_context():
        try:
            uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            
            db_dir = current_app.config.get("BACKUP_DB_DIR")
            sql_dir = current_app.config.get("BACKUP_SQL_DIR")
            os.makedirs(db_dir, exist_ok=True)
            os.makedirs(sql_dir, exist_ok=True)
            
            if not uri.startswith("sqlite:///"):
                current_app.logger.warning("Automated backup: Database is not SQLite")
                return
            
            db_path = uri.replace("sqlite:///", "")
            if not os.path.exists(db_path):
                current_app.logger.warning(f"Automated backup: Database file not found: {db_path}")
                return
            
            db_out = os.path.join(db_dir, f"auto_backup_{ts}.db")
            sql_out = os.path.join(sql_dir, f"auto_backup_{ts}.sql")
            
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
            
            cleanup_old_backups(db_dir, sql_dir)
            
            current_app.logger.info(f"✅ Automated backup completed successfully: {db_out}")
            
        except Exception as e:
            current_app.logger.error(f"❌ Automated backup failed: {str(e)}")

def cleanup_old_backups(db_dir, sql_dir, keep_days=7, keep_weekly=4, keep_monthly=12):
    import time
    from pathlib import Path
    
    now = time.time()
    one_day = 86400
    one_week = 604800
    one_month = 2592000
    
    for directory in [db_dir, sql_dir]:
        if not os.path.exists(directory):
            continue
        
        files = []
        for f in Path(directory).glob("auto_backup_*"):
            if f.is_file():
                files.append((f, f.stat().st_mtime))
        
        files.sort(key=lambda x: x[1], reverse=True)
        
        daily_backups = []
        weekly_backups = []
        monthly_backups = []
        
        for filepath, mtime in files:
            age_days = (now - mtime) / one_day
            
            if age_days <= keep_days:
                daily_backups.append(filepath)
            elif age_days <= keep_days + (keep_weekly * 7):
                if len(weekly_backups) < keep_weekly:
                    weekly_backups.append(filepath)
                else:
                    try:
                        filepath.unlink()
                    except Exception:
                        pass
            elif age_days <= keep_days + (keep_weekly * 7) + (keep_monthly * 30):
                if len(monthly_backups) < keep_monthly:
                    monthly_backups.append(filepath)
                else:
                    try:
                        filepath.unlink()
                    except Exception:
                        pass
            else:
                try:
                    filepath.unlink()
                except Exception:
                    pass
