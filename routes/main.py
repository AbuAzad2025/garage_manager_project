# routes/main.py

import os
from io import BytesIO
from datetime import date, datetime, timedelta

from flask import (
    Blueprint, abort, current_app, flash,
    redirect, render_template, send_file, url_for
)
from flask_login import current_user, login_required
from sqlalchemy import func, cast, Date

import reports
from extensions import db, mail
from forms import RestoreForm
from models import (
    Customer, ExchangeTransaction, Note, Product, Sale,
    ServiceRequest, Supplier
)
from utils import permission_required

main_bp = Blueprint('main', __name__, template_folder='templates')


@main_bp.route('/', methods=['GET'], endpoint='dashboard')
@login_required
def dashboard():
    """لوحة التحكم الرئيسية مع عرض إحصائيات المبيعات والصيانة"""
    # الحالة الأساسية
    today = date.today()
    start = today - timedelta(days=6)
    end = today

    # -- المخزون والتنبيهات
    low_stock = Product.query.filter(Product.on_hand < Product.min_qty).all()
    inventory_total = db.session.query(
        func.coalesce(func.sum(Product.on_hand), 0)
    ).scalar()
    pending_exchanges = ExchangeTransaction.query.filter_by(direction='OUT').count()
    partner_stock = db.session.query(func.count(Product.id)) \
        .join(Supplier, Supplier.id == Product.supplier_local_id) \
        .scalar() or 0

    # -- مبيعات اليوم والإيرادات الأسبوعية
    recent_sales = []
    today_revenue = 0
    revenue_labels = []
    revenue_values = []
    if current_user.has_permission('manage_sales'):
        recent_sales = Sale.query.order_by(Sale.created_at.desc()).limit(5).all()
        sales_data = reports.sales_report(start, end)
        today_revenue = sales_data['total_revenue']
        revenue_labels = sales_data['daily_labels']
        revenue_values = sales_data['daily_values']

    # -- طلبات الصيانة الأخيرة
    recent_services = []
    if current_user.has_permission('manage_service'):
        q = ServiceRequest.query.order_by(ServiceRequest.created_at.desc())
        # إذا كان الفني فقط، نظِّم على أساس معرّف الفني
        if current_user.role and current_user.role.name.lower() == 'mechanic':
            q = q.filter_by(mechanic_id=current_user.id)
        recent_services = q.limit(5).all()

    # -- إحصائيات الصيانة الأسبوعية
    service_metrics = {'day_labels': [], 'day_counts': []}
    if current_user.has_permission('view_reports'):
        rows = (
            db.session.query(
                cast(ServiceRequest.start_time, Date).label('day'),
                func.count(ServiceRequest.id).label('cnt')
            )
            .filter(cast(ServiceRequest.start_time, Date).between(start, end))
            .group_by('day')
            .order_by('day')
            .all()
        )
        service_metrics = {
            'day_labels': [r.day.strftime('%Y-%m-%d') for r in rows],
            'day_counts': [r.cnt for r in rows]
        }

    # -- الملاحظات الأخيرة
    recent_notes = []
    if current_user.has_permission('view_reports'):
        recent_notes = Note.query.order_by(Note.created_at.desc()).limit(5).all()

    # -- تقرير شيكات العملاء (مؤجلات الدفع)
    customer_metrics = {}
    if current_user.has_permission('view_reports'):
        customer_metrics = reports.ar_aging_report(start, end)

    return render_template(
        'dashboard.html',
        low_stock=low_stock,
        inventory_total=inventory_total,
        pending_exchanges=pending_exchanges,
        partner_stock=partner_stock,
        today_revenue=today_revenue,
        revenue_labels=revenue_labels,
        revenue_values=revenue_values,
        recent_sales=recent_sales,
        recent_services=recent_services,
        service_metrics=service_metrics,
        recent_notes=recent_notes,
        customer_metrics=customer_metrics
    )


@main_bp.route('/backup_db', methods=['GET'], endpoint='backup_db')
@login_required
@permission_required('backup_database')
def backup_db():
    """تحميل نسخة احتياطية من قاعدة البيانات SQLite"""
    uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    prefix = 'sqlite:///'

    if not uri.startswith(prefix):
        abort(400)

    db_path = uri[len(prefix):]
    if not os.path.exists(db_path):
        abort(500)

    db.session.commit()
    with open(db_path, 'rb') as f:
        data = f.read()

    buf = BytesIO(data)
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return send_file(
        buf,
        as_attachment=True,
        download_name=f'backup_{timestamp}.db',
        mimetype='application/octet-stream'
    )


@main_bp.route('/restore_db', methods=['GET', 'POST'], endpoint='restore_db')
@login_required
@permission_required('restore_database')
def restore_db():
    """استعادة نسخة احتياطية من قاعدة البيانات SQLite"""
    form = RestoreForm()
    if form.validate_on_submit():
        db_file = form.db_file.data
        uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        prefix = 'sqlite:///'

        if not uri.startswith(prefix):
            flash('قاعدة البيانات ليست SQLite.', 'danger')
            return redirect(url_for('main.restore_db'))

        db_path = uri[len(prefix):]
        try:
            db_file.save(db_path)
            flash('تمت استعادة النسخة الاحتياطية بنجاح. أعد تشغيل التطبيق.', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception:
            flash('خطأ أثناء استعادة النسخة.', 'danger')
            return redirect(url_for('main.restore_db'))

    return render_template('restore_db.html', form=form)
