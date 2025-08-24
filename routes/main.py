# routes/main.py
import os
import sqlite3
from datetime import date, datetime, timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    send_file,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import Date, cast, func

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
)
from utils import permission_required
from reports import sales_report, ar_aging_report

main_bp = Blueprint("main", __name__, template_folder="templates")


@main_bp.route("/favicon.ico")
def favicon():
    return send_from_directory(
        current_app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon"
    )


@main_bp.route("/", methods=["GET"], endpoint="dashboard")
@login_required
def dashboard():
    today = date.today()
    start = today - timedelta(days=6)
    end = today

    inv_rows = (
        db.session.query(
            Product,
            func.coalesce(func.sum(StockLevel.quantity), 0).label("on_hand_sum"),
        )
        .outerjoin(StockLevel, StockLevel.product_id == Product.id)
        .group_by(Product.id)
        .all()
    )
    for p, qty in inv_rows:
        setattr(p, "on_hand", int(qty))
    low_stock = [p for p, qty in inv_rows if qty <= (p.min_qty or 0)]
    inventory_total = int(sum(qty for _, qty in inv_rows))

    pending_exchanges = ExchangeTransaction.query.filter_by(direction="OUT").count()
    partner_stock = (
        db.session.query(func.count(Product.id))
        .join(Supplier, Supplier.id == Product.supplier_local_id)
        .scalar()
        or 0
    )

    recent_sales = []
    today_revenue = 0.0
    revenue_labels = []
    revenue_values = []
    week_revenue = 0.0
    if current_user.has_permission("manage_sales"):
        recent_sales = Sale.query.order_by(Sale.sale_date.desc()).limit(5).all()
        try:
            srep = sales_report(start, end) or {}
        except Exception:
            srep = {}
        revenue_labels = srep.get("daily_labels", [])
        revenue_values = srep.get("daily_values", [])
        week_revenue = float(srep.get("total_revenue", 0) or 0)
        today_revenue = float(
            db.session.query(func.coalesce(func.sum(Sale.total_amount), 0))
            .filter(cast(Sale.sale_date, Date) == today, Sale.status == "CONFIRMED")
            .scalar()
            or 0
        )

    recent_services = []
    if current_user.has_permission("manage_service"):
        q = ServiceRequest.query.order_by(ServiceRequest.created_at.desc())
        if current_user.role and (current_user.role.name or "").lower() == "mechanic":
            q = q.filter_by(mechanic_id=current_user.id)
        recent_services = q.limit(5).all()
        for s in recent_services:
            if not hasattr(s, "started_at"):
                s.started_at = getattr(s, "start_time", None)

    recent_notes = []
    service_metrics = {"day_labels": [], "day_counts": []}
    customer_metrics = {}
    if current_user.has_permission("view_reports"):
        rows = (
            db.session.query(
                cast(ServiceRequest.start_time, Date).label("day"),
                func.count(ServiceRequest.id).label("cnt"),
            )
            .filter(cast(ServiceRequest.start_time, Date).between(start, end))
            .group_by("day")
            .order_by("day")
            .all()
        )
        service_metrics = {
            "day_labels": [r.day.strftime("%Y-%m-%d") for r in rows],
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
    )


@main_bp.route("/backup_db", methods=["GET"], endpoint="backup_db")
@login_required
@permission_required("backup_database")
def backup_db():
    # 🔒 تحقق من البيئة والصلاحية
    is_prod = (current_app.config.get("ENV") == "production" or 
               current_app.config.get("FLASK_ENV") == "production")
    role_name = str(getattr(getattr(current_user, "role", None), "name", "")).lower()
    if is_prod and role_name != "super_admin":
        flash("❌ غير مسموح بالنسخ الاحتياطي في بيئة الإنتاج إلا لمستخدم super_admin فقط.", "danger")
        return redirect(url_for("main.dashboard"))

    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    if uri.startswith("sqlite:///"):
        db_path = uri.replace("sqlite:///", "")
        if db_path in (":memory:", "") or not os.path.exists(db_path):
            raw = db.engine.raw_connection()
            out_path = os.path.join(current_app.instance_path, f"backup_{ts}.sql")
            os.makedirs(current_app.instance_path, exist_ok=True)
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    for line in raw.iterdump():
                        f.write(f"{line}\n")
            finally:
                raw.close()
            return send_file(
                out_path, as_attachment=True, download_name=f"backup_{ts}.sql"
            )
        out_path = os.path.join(current_app.instance_path, f"backup_{ts}.db")
        os.makedirs(current_app.instance_path, exist_ok=True)
        db.session.commit()
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(out_path)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        return send_file(
            out_path, as_attachment=True, download_name=os.path.basename(out_path)
        )
    flash("قاعدة البيانات ليست SQLite.", "warning")
    return redirect(url_for("main.dashboard")), 303

@main_bp.route("/restore_db", methods=["GET", "POST"], endpoint="restore_db")
@login_required
@permission_required("restore_database")
def restore_db():
    # 🔒 تحقق من البيئة والصلاحية
    is_prod = (current_app.config.get("ENV") == "production" or 
               current_app.config.get("FLASK_ENV") == "production")
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
