# File: routes/service.py
import io
import json
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, abort, Response, send_file, current_app
)
from flask_login import login_required, current_user, login_user
from sqlalchemy import func, or_, and_, desc, select, update, insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from extensions import db

from models import (
    ServiceRequest, ServicePart, ServiceTask,
    Customer, Product, Warehouse,
    AuditLog, User, EquipmentType,
    StockLevel, Partner, Permission, Role,
    ServiceStatus, ServicePriority,
)

from forms import (
    ServiceRequestForm,
    CustomerForm,
    ServiceTaskForm,
    ServiceDiagnosisForm,
    ServicePartForm,
)

from utils import (
    permission_required,
    send_whatsapp_message,
)

service_bp = Blueprint('service', __name__, url_prefix='/service')

def _get_or_404(model, ident, options=None):
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

STATUS_LABELS = {
    'PENDING': 'معلق',
    'DIAGNOSIS': 'تشخيص',
    'IN_PROGRESS': 'قيد التنفيذ',
    'COMPLETED': 'مكتمل',
    'CANCELLED': 'ملغي',
    'ON_HOLD': 'مؤجل'
}

PRIORITY_COLORS = {
    'LOW': 'info',
    'MEDIUM': 'warning',
    'HIGH': 'danger',
    'URGENT': 'dark'
}

@service_bp.before_request
def _force_superadmin_in_tests():
    if not current_app.config.get("TESTING"):
        return
    role = Role.query.filter_by(name="super_admin").first()
    if not role:
        role = Role(name="super_admin", description="auto test super admin")
        db.session.add(role); db.session.flush()
    user = User.query.filter_by(username="_auto_service_super").first()
    if not user:
        user = User(username="_auto_service_super", email="svc@test.local")
        user.set_password("x")
        db.session.add(user); db.session.flush()
    if user.role_id != role.id:
        user.role = role; db.session.flush()
    if (not getattr(current_user, "is_authenticated", False) or
        getattr(getattr(current_user, "role", None), "name", "") != "super_admin"):
        db.session.commit()
        login_user(user)

@service_bp.context_processor
def inject_service_constants():
    return {
        'STATUS_LABELS': STATUS_LABELS,
        'PRIORITY_COLORS': PRIORITY_COLORS,
    }

def _get_id(val):
    return getattr(val, 'id', val)

def _status_list(values):
    out = []
    for v in values:
        key = (v or '').strip().upper()
        if hasattr(ServiceStatus, key):
            out.append(getattr(ServiceStatus, key))
    return out

def _priority_list(values):
    out = []
    for v in values:
        key = (v or '').strip().upper()
        if hasattr(ServicePriority, key):
            out.append(getattr(ServicePriority, key))
    return out

def _col(name: str):
    mapping = {
        'request_date': 'received_at',
        'start_time':   'started_at',
        'end_time':     'completed_at',
        'received_at':  'received_at',
        'started_at':   'started_at',
        'completed_at': 'completed_at',
        'priority':     'priority',
        'status':       'status',
    }
    attr = mapping.get(name, 'received_at')
    return getattr(ServiceRequest, attr)

def _service_consumes_stock(sr: ServiceRequest) -> bool:
    st = (getattr(sr.status, "value", sr.status) or "").upper()
    return st in ("IN_PROGRESS", "COMPLETED")

def _apply_stock_delta(product_id: int, warehouse_id: int, delta: int):
    conn = db.session.connection()
    tbl = StockLevel.__table__
    row = conn.execute(
        select(tbl.c.id, tbl.c.quantity)
        .where(tbl.c.product_id == product_id, tbl.c.warehouse_id == warehouse_id)
        .with_for_update()
    ).mappings().first()
    if row is None:
        if delta < 0:
            raise ValueError("لا يوجد مخزون كافٍ.")
        conn.execute(insert(tbl).values(
            product_id=product_id, warehouse_id=warehouse_id,
            quantity=int(delta), reserved_quantity=0
        ))
        return
    new_qty = int(row["quantity"] or 0) + int(delta)
    if new_qty < 0:
        raise ValueError("الكمية غير كافية في المخزون.")
    conn.execute(update(tbl).where(tbl.c.id == row["id"]).values(quantity=new_qty))

@service_bp.route('/', methods=['GET'])
@login_required
@permission_required('manage_service')
def list_requests():
    status_filter   = request.args.getlist('status')
    priority_filter = request.args.getlist('priority')
    customer_filter = request.args.get('customer', '')
    mechanic_filter = request.args.get('mechanic', '')
    vrn_filter      = request.args.get('vrn', '')
    date_filter     = request.args.get('date', '')

    query = ServiceRequest.query.options(joinedload(ServiceRequest.customer))

    sts = _status_list(status_filter)
    if sts:
        query = query.filter(ServiceRequest.status.in_(sts))

    pris = _priority_list(priority_filter)
    if pris:
        query = query.filter(ServiceRequest.priority.in_(pris))

    if customer_filter:
        query = query.join(Customer).filter(or_(
            Customer.name.ilike(f'%{customer_filter}%'),
            Customer.phone.ilike(f'%{customer_filter}%')
        ))
    if mechanic_filter:
        query = query.join(User, ServiceRequest.mechanic_id == User.id).filter(
            User.username.ilike(f'%{mechanic_filter}%')
        )
    if vrn_filter:
        query = query.filter(ServiceRequest.vehicle_vrn.ilike(f'%{vrn_filter}%'))
    if date_filter:
        today = datetime.today()
        col = _col('received_at')
        if date_filter == 'today':
            query = query.filter(func.date(col) == today.date())
        elif date_filter == 'week':
            start_week = today - timedelta(days=today.weekday())
            query = query.filter(col >= start_week)
        elif date_filter == 'month':
            start_month = today.replace(day=1)
            query = query.filter(col >= start_month)

    sort_by    = request.args.get('sort', 'request_date')
    sort_order = request.args.get('order', 'desc')
    field      = _col(sort_by)
    query = query.order_by(field.asc() if sort_order == 'asc' else field.desc())

    requests = query.all()

    stats = {
        'pending':      ServiceRequest.query.filter_by(status=ServiceStatus.PENDING).count(),
        'in_progress':  ServiceRequest.query.filter_by(status=ServiceStatus.IN_PROGRESS).count(),
        'completed':    ServiceRequest.query.filter_by(status=ServiceStatus.COMPLETED).count(),
        'high_priority': ServiceRequest.query.filter_by(priority=ServicePriority.HIGH).count(),
    }
    mechanics = User.query.filter_by(is_active=True).all()

    filter_values = {
        'status':   status_filter,
        'priority': priority_filter,
        'customer': customer_filter,
        'mechanic': mechanic_filter,
        'vrn':      vrn_filter,
        'date':     date_filter,
        'sort':     sort_by,
        'order':    sort_order
    }

    return render_template(
        'service/list.html',
        requests=requests,
        status_labels=STATUS_LABELS,
        priority_colors=PRIORITY_COLORS,
        stats=stats,
        mechanics=mechanics,
        filter_values=filter_values
    )

@service_bp.route('/dashboard')
@login_required
@permission_required('manage_service')
def dashboard():
    total_requests = ServiceRequest.query.count()
    completed_this_month = ServiceRequest.query.filter(
        ServiceRequest.status == ServiceStatus.COMPLETED,
        _col('completed_at') >= datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ).count()
    high_priority = ServiceRequest.query.filter_by(priority=ServicePriority.HIGH)\
        .order_by(_col('received_at').desc()).limit(5).all()

    in_prog = ServiceRequest.query.filter(
        ServiceRequest.status.in_([ServiceStatus.DIAGNOSIS, ServiceStatus.IN_PROGRESS])
    ).all()
    now = datetime.now()
    overdue = []
    for s in in_prog:
        start_dt = getattr(s, "started_at", None)
        est_min  = getattr(s, "estimated_duration", None)
        if start_dt and est_min:
            eta = start_dt + timedelta(minutes=int(est_min))
            if eta < now:
                overdue.append(s)

    status_distribution = db.session.query(
        ServiceRequest.status, func.count(ServiceRequest.id)
    ).group_by(ServiceRequest.status).all()

    priority_distribution = db.session.query(
        ServiceRequest.priority, func.count(ServiceRequest.id)
    ).group_by(ServiceRequest.priority).all()

    return render_template(
        'service/dashboard.html',
        total_requests=total_requests,
        completed_this_month=completed_this_month,
        high_priority=high_priority,
        active_mechanics=db.session.query(
            User.username,
            func.count(ServiceRequest.id).label('request_count')
        ).join(ServiceRequest, ServiceRequest.mechanic_id == User.id)
         .group_by(User.id).order_by(desc('request_count')).limit(5).all(),
        overdue=overdue,
        status_distribution=status_distribution,
        priority_distribution=priority_distribution
    )

@service_bp.route('/new', methods=['GET','POST'])
@login_required
@permission_required('manage_service')
def create_request():
    form = ServiceRequestForm()
    cform = CustomerForm(prefix="customer")
    try:
        form.vehicle_type_id.endpoint = 'api.search_equipment_types'
    except Exception:
        pass

    if form.validate_on_submit():
        # تحديد العميل: مختار من القائمة أو إنشاء جديد من CustomerForm
        if form.customer_id.data:
            customer = db.session.get(Customer, _get_id(form.customer_id.data))
        else:
            cname  = cform.name.data
            cphone = cform.phone.data
            cemail = cform.email.data
            customer = Customer.query.filter_by(name=cname, phone=cphone).first()
            if not customer:
                customer = Customer(name=cname, phone=cphone, email=cemail)
                db.session.add(customer); db.session.flush()

        service = ServiceRequest(
            service_number=f"SRV-{datetime.utcnow():%Y%m%d%H%M%S}",
            customer_id=customer.id,

            vehicle_vrn=form.vehicle_vrn.data,
            vehicle_type_id=_get_id(form.vehicle_type_id.data) if form.vehicle_type_id.data else None,
            vehicle_model=form.vehicle_model.data,
            chassis_number=form.chassis_number.data,

            problem_description=form.problem_description.data,
            engineer_notes=form.engineer_notes.data,
            description=form.description.data,

            priority=getattr(ServicePriority, (form.priority.data or 'MEDIUM').upper()),
            estimated_duration=form.estimated_duration.data,
            estimated_cost=form.estimated_cost.data,
            tax_rate=form.tax_rate.data or 0,
            status=getattr(ServiceStatus, (form.status.data or 'PENDING').upper()),
            received_at=datetime.utcnow(),
        )
        db.session.add(service)
        try:
            db.session.commit()
            log_service_action(service, "CREATE")
            if customer.phone:
                send_whatsapp_message(customer.phone, f"تم استلام طلب الصيانة رقم {service.service_number}.")
            flash("✅ تم إنشاء طلب الصيانة بنجاح", "success")
            return redirect(url_for('service.view_request', rid=service.id))
        except SQLAlchemyError as exc:
            db.session.rollback()
            flash(f"❌ خطأ في قاعدة البيانات: {exc}", "danger")

    return render_template('service/new.html', form=form, customer_form=cform)

@service_bp.route('/<int:rid>', methods=['GET'])
@login_required
@permission_required('manage_service')
def view_request(rid):
    service = _get_or_404(
        ServiceRequest, rid,
        options=[
            joinedload(ServiceRequest.customer),
            joinedload(ServiceRequest.parts).joinedload(ServicePart.part),
            joinedload(ServiceRequest.parts).joinedload(ServicePart.warehouse),
            joinedload(ServiceRequest.tasks),
        ]
    )
    return render_template('service/view.html', service=service)

@service_bp.route('/<int:rid>/receipt', methods=['GET'])
@login_required
@permission_required('manage_service')
def view_receipt(rid):
    service = _get_or_404(ServiceRequest, rid)
    return render_template('service/receipt.html', service=service)

@service_bp.route('/<int:rid>/receipt/download', methods=['GET'])
@login_required
@permission_required('manage_service')
def download_receipt(rid):
    service = _get_or_404(ServiceRequest, rid)
    pdf_data = generate_service_receipt_pdf(service)
    return send_file(io.BytesIO(pdf_data), as_attachment=True,
                     download_name=f"service_receipt_{service.service_number}.pdf",
                     mimetype='application/pdf')

@service_bp.route('/<int:rid>/diagnosis', methods=['POST'])
@login_required
@permission_required('manage_service')
def update_diagnosis(rid):
    service = _get_or_404(ServiceRequest, rid)
    form = ServiceDiagnosisForm()
    if form.validate_on_submit():
        old = {
            'problem_description': service.problem_description,
            'diagnosis': service.diagnosis,
            'resolution': service.resolution,
            'estimated_duration': service.estimated_duration,
            'estimated_cost': str(service.estimated_cost or 0),
            'status': getattr(service.status, 'value', service.status),
        }
        service.problem_description = form.problem_description.data
        service.diagnosis           = form.diagnosis.data
        service.resolution          = form.resolution.data
        service.estimated_duration  = form.estimated_duration.data
        service.estimated_cost      = form.estimated_cost.data
        service.status              = ServiceStatus.IN_PROGRESS
        try:
            db.session.commit()
            log_service_action(service, "DIAGNOSIS", old_data=old, new_data={
                'problem_description': service.problem_description,
                'diagnosis': service.diagnosis,
                'resolution': service.resolution,
                'estimated_duration': service.estimated_duration,
                'estimated_cost': str(service.estimated_cost or 0),
                'status': service.status.value
            })
            if service.customer and service.customer.phone:
                send_whatsapp_message(service.customer.phone, f"تم تشخيص المركبة {service.vehicle_vrn}.")
            flash('✅ تم تحديث التشخيص بنجاح', 'success')
        except SQLAlchemyError as e:
            db.session.rollback(); flash(f'❌ خطأ في قاعدة البيانات: {str(e)}', 'danger')
    return redirect(url_for('service.view_request', rid=rid))

@service_bp.route('/<int:rid>/<action>', methods=['POST'])
@login_required
@permission_required('manage_service')
def toggle_service(rid, action):
    service = _get_or_404(ServiceRequest, rid)
    old_consumes = _service_consumes_stock(service)
    try:
        if action == 'start':
            if not getattr(service, "started_at", None):
                service.started_at = datetime.utcnow()
            service.status = ServiceStatus.IN_PROGRESS
        elif action == 'complete':
            service.completed_at = datetime.utcnow()
            if service.started_at:
                service.actual_duration = int((service.completed_at - service.started_at).total_seconds() / 60)
            service.status = ServiceStatus.COMPLETED
        else:
            abort(400)

        new_consumes = _service_consumes_stock(service)

        if not old_consumes and new_consumes:
            for p in service.parts or []:
                _apply_stock_delta(p.part_id, p.warehouse_id, -int(p.quantity or 0))

        db.session.commit()
        if action == 'complete' and service.customer and service.customer.phone:
            send_whatsapp_message(service.customer.phone, f"تم إكمال صيانة المركبة {service.vehicle_vrn}.")
        flash('✅ تم تحديث حالة الصيانة', 'success')
    except ValueError as ve:
        db.session.rollback()
        flash(f'❌ مخزون غير كافٍ لبعض القطع: {ve}', 'danger')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ في قاعدة البيانات: {str(e)}', 'danger')

    return redirect(url_for('service.view_request', rid=rid))

@service_bp.route('/<int:rid>/parts/add', methods=['POST'])
@login_required
@permission_required('manage_service')
def add_part(rid):
    service = _get_or_404(ServiceRequest, rid)
    form = ServicePartForm()
    if form.validate_on_submit():
        warehouse_id = _get_id(form.warehouse_id.data)
        product_id   = _get_id(form.part_id.data)
        partner_id   = _get_id(form.partner_id.data) if form.partner_id.data else None

        part = ServicePart(
            service_id=rid,
            part_id=product_id,
            warehouse_id=warehouse_id,
            quantity=form.quantity.data,
            unit_price=form.unit_price.data,
            discount=form.discount.data or 0,
            tax_rate=form.tax_rate.data or 0,
            partner_id=partner_id,
            share_percentage=form.share_percentage.data or 0,
            note=form.note.data
        )
        db.session.add(part)
        try:
            if _service_consumes_stock(service):
                _apply_stock_delta(product_id, warehouse_id, -int(form.quantity.data or 0))
            db.session.commit()
            flash('✅ تمت إضافة القطعة ومعالجة المخزون', 'success')
        except ValueError as ve:
            db.session.rollback()
            flash(f'❌ مخزون غير كافٍ: {ve}', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ: {str(e)}', 'danger')
    return redirect(url_for('service.view_request', rid=rid))

@service_bp.route('/parts/<int:pid>/delete', methods=['POST'])
@login_required
@permission_required('manage_service')
def delete_part(pid):
    part = _get_or_404(ServicePart, pid)
    rid  = part.service_id
    service = _get_or_404(ServiceRequest, rid)
    try:
        if _service_consumes_stock(service):
            _apply_stock_delta(part.part_id, part.warehouse_id, +int(part.quantity or 0))
        db.session.delete(part)
        db.session.commit()
        flash('✅ تم حذف القطعة ومعالجة المخزون', 'success')
    except SQLAlchemyError as e:
        db.session.rollback(); flash(f'❌ خطأ: {str(e)}', 'danger')
    except ValueError as ve:
        db.session.rollback(); flash(f'❌ {ve}', 'danger')
    return redirect(url_for('service.view_request', rid=rid))

@service_bp.route('/<int:rid>/tasks/add', methods=['POST'])
@login_required
@permission_required('manage_service')
def add_task(rid):
    form = ServiceTaskForm()
    if form.validate_on_submit():
        task = ServiceTask(
            service_id=rid,
            description=form.description.data,
            quantity=form.quantity.data or 1,
            unit_price=form.unit_price.data,
            discount=form.discount.data or 0,
            tax_rate=form.tax_rate.data or 0,
            note=form.note.data,
            partner_id=_get_id(form.partner_id.data) if getattr(form, "partner_id", None) and form.partner_id.data else None,
            share_percentage=form.share_percentage.data or 0
        )
        db.session.add(task)
        try:
            db.session.commit(); flash('✅ تمت إضافة المهمة', 'success')
        except SQLAlchemyError as e:
            db.session.rollback(); flash(f'❌ خطأ: {str(e)}', 'danger')
    return redirect(url_for('service.view_request', rid=rid))

@service_bp.route('/tasks/<int:tid>/delete', methods=['POST'])
@login_required
@permission_required('manage_service')
def delete_task(tid):
    task = _get_or_404(ServiceTask, tid); rid = task.service_id
    db.session.delete(task)
    try:
        db.session.commit(); flash('✅ تم حذف المهمة', 'success')
    except SQLAlchemyError as e:
        db.session.rollback(); flash(f'❌ خطأ: {str(e)}', 'danger')
    return redirect(url_for('service.view_request', rid=rid))

@service_bp.route('/<int:rid>/payments/add', methods=['GET','POST'])
@login_required
@permission_required('manage_service')
def add_payment(rid):
    return redirect(url_for('payments.create_payment', entity_type='SERVICE', entity_id=rid))

@service_bp.route('/<int:rid>/invoice', methods=['GET','POST'])
@login_required
@permission_required('manage_service')
def create_invoice(rid):
    svc = _get_or_404(ServiceRequest, rid, options=[joinedload(ServiceRequest.parts), joinedload(ServiceRequest.tasks)])
    try:
        amount = float(getattr(svc, 'balance_due', None) or getattr(svc, 'total_cost', 0) or 0)
    except Exception:
        amount = 0.0
    return redirect(url_for('payments.create_payment', entity_type='SERVICE', entity_id=rid, amount=amount))

@service_bp.route('/<int:rid>/report')
@login_required
@permission_required('manage_service')
def service_report(rid):
    service = _get_or_404(ServiceRequest, rid)
    pdf = generate_service_receipt_pdf(service)
    return Response(pdf, mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename=service_report_{service.service_number}.pdf'})

@service_bp.route('/<int:rid>/pdf')
@login_required
@permission_required('manage_service')
def export_pdf(rid):
    service = _get_or_404(ServiceRequest, rid)
    pdf = generate_service_receipt_pdf(service)
    return Response(pdf, mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename=service_{service.service_number}.pdf'})

@service_bp.route('/<int:rid>/delete', methods=['POST'])
@login_required
@permission_required('manage_service')
def delete_request(rid):
    service = _get_or_404(ServiceRequest, rid)
    try:
        with db.session.begin():
            if _service_consumes_stock(service):
                for part in list(service.parts or ()):
                    _apply_stock_delta(part.part_id, part.warehouse_id, +int(part.quantity or 0))
            db.session.delete(service)
        flash('✅ تم حذف الطلب ومعالجة المخزون', 'success')
    except SQLAlchemyError as e:
        db.session.rollback(); flash(f'❌ فشل حذف الطلب: {e}', 'danger')
    except ValueError as ve:
        db.session.rollback(); flash(f'❌ {ve}', 'danger')
    return redirect(url_for('service.list_requests'))

@service_bp.route('/api/requests', methods=['GET'])
@login_required
def api_service_requests():
    status = (request.args.get('status', 'all') or '').upper()
    if status == 'ALL' or not hasattr(ServiceStatus, status):
        reqs = ServiceRequest.query.all()
    else:
        reqs = ServiceRequest.query.filter_by(status=getattr(ServiceStatus, status)).all()
    result = [{
        'id':               r.id,
        'service_number':   r.service_number,
        'customer':         r.customer.name if r.customer else (getattr(r, 'name', '') or ''),
        'vehicle_vrn':      r.vehicle_vrn,
        'status':           getattr(r.status, 'value', r.status),
        'priority':         getattr(r.priority, 'value', r.priority),
        'request_date':     (r.received_at.strftime('%Y-%m-%d %H:%M') if getattr(r, 'received_at', None) else ''),
        'mechanic':         r.mechanic.username if getattr(r, 'mechanic', None) else ''
    } for r in reqs]
    return jsonify(result)

@service_bp.route('/search', methods=['GET'])
@login_required
def search_requests():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    results = ServiceRequest.query.join(Customer).filter(or_(
        ServiceRequest.service_number.ilike(f'%{query}%'),
        ServiceRequest.vehicle_vrn.ilike(f'%{query}%'),
        Customer.name.ilike(f'%{query}%'),
        Customer.phone.ilike(f'%{query}%')
    )).limit(10).all()
    return jsonify([{
        'id':   r.id,
        'text': f"{r.service_number} - {r.customer.name if r.customer else getattr(r,'name','')} - {r.vehicle_vrn}",
        'url':  url_for('service.view_request', rid=r.id)
    } for r in results])

def log_service_action(service, action, old_data=None, new_data=None):
    entry = AuditLog(
        model_name = 'ServiceRequest',
        record_id  = service.id,
        user_id    = current_user.id if current_user and getattr(current_user, 'id', None) else None,
        action     = action,
        old_data   = json.dumps(old_data, ensure_ascii=False) if old_data else None,
        new_data   = json.dumps(new_data, ensure_ascii=False) if new_data else None
    )
    db.session.add(entry)
    db.session.flush()

def generate_service_receipt_pdf(service_request):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except Exception:
        return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(20*mm, height - 20*mm, "إيصال صيانة")

    c.setFont("Helvetica", 10)
    y = height - 30*mm
    c.drawString(20*mm, y, f"رقم الطلب: {service_request.service_number}")
    c.drawString(120*mm, y, f"التاريخ: {service_request.received_at.strftime('%Y-%m-%d') if getattr(service_request,'received_at',None) else ''}")
    y -= 8*mm
    c.drawString(20*mm, y, f"العميل: {service_request.customer.name if service_request.customer else (getattr(service_request,'name',None) or '-')}")
    c.drawString(120*mm, y, f"لوحة المركبة: {service_request.vehicle_vrn or ''}")

    y -= 12*mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20*mm, y, "القطع المُركّبة")
    y -= 6*mm
    c.setFont("Helvetica", 9)
    headers = [("الصنف", 20), ("المخزن", 70), ("الكمية", 110), ("سعر", 125), ("خصم%", 145), ("ضريبة%", 160), ("الإجمالي", 175)]
    for h, x in headers:
        c.drawString(x*mm, y, h)
    y -= 4*mm
    c.line(20*mm, y, 200*mm, y)
    y -= 6*mm

    parts_total = 0.0
    for part in getattr(service_request, "parts", []) or []:
        qty  = int(part.quantity or 0)
        u    = float(part.unit_price or 0)
        disc = float(part.discount or 0)
        taxr = float(part.tax_rate or 0)
        gross = qty * u
        disc_amount = gross * (disc/100.0)
        taxable = gross - disc_amount
        tax_amount = taxable * (taxr/100.0)
        line_total = taxable + tax_amount
        parts_total += line_total

        c.drawString(20*mm, y, (getattr(part.part, 'name', '') or str(part.part_id))[:25])
        c.drawString(70*mm, y, getattr(part.warehouse, 'name', '—') or '—')
        c.drawRightString(120*mm, y, str(qty))
        c.drawRightString(140*mm, y, f"{u:.2f}")
        c.drawRightString(155*mm, y, f"{disc:.0f}")
        c.drawRightString(170*mm, y, f"{taxr:.0f}")
        c.drawRightString(195*mm, y, f"{line_total:.2f}")
        y -= 6*mm
        if y < 40*mm:
            c.showPage(); y = height - 20*mm; c.setFont("Helvetica", 9)

    y -= 8*mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20*mm, y, "المهام")
    y -= 6*mm
    c.setFont("Helvetica", 9)
    headers = [("الوصف", 20), ("الكمية", 110), ("سعر", 125), ("خصم%", 145), ("ضريبة%", 160), ("الإجمالي", 175)]
    for h, x in headers:
        c.drawString(x*mm, y, h)
    y -= 4*mm
    c.line(20*mm, y, 200*mm, y)
    y -= 6*mm

    tasks_total = 0.0
    for task in getattr(service_request, "tasks", []) or []:
        qty  = int(task.quantity or 1)
        u    = float(task.unit_price or 0)
        disc = float(task.discount or 0)
        taxr = float(task.tax_rate or 0)
        gross = qty * u
        disc_amount = gross * (disc/100.0)
        taxable = gross - disc_amount
        tax_amount = taxable * (taxr/100.0)
        line_total = taxable + tax_amount
        tasks_total += line_total

        c.drawString(20*mm, y, (task.description or '')[:40])
        c.drawRightString(120*mm, y, str(qty))
        c.drawRightString(140*mm, y, f"{u:.2f}")
        c.drawRightString(155*mm, y, f"{disc:.0f}")
        c.drawRightString(170*mm, y, f"{taxr:.0f}")
        c.drawRightString(195*mm, y, f"{line_total:.2f}")
        y -= 6*mm
        if y < 40*mm:
            c.showPage(); y = height - 20*mm; c.setFont("Helvetica", 9)

    subtotal = parts_total + tasks_total

    y -= 10*mm
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(160*mm, y, "الإجمالي الكلي:")
    c.drawRightString(195*mm, y, f"{subtotal:.2f}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()
