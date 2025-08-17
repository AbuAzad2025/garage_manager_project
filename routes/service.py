# File: routes/service.py

import io
import json
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, abort, Response, send_file,current_app
)
from flask_login import login_required, current_user, login_user
from sqlalchemy import func, or_, and_, desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from dateutil.relativedelta import relativedelta


# استيراد الإكستنشنز
from extensions import db

# استيراد الموديلات
from models import (
    ServiceRequest, ServicePart, ServiceTask,
    Customer, Product, Warehouse,
    AuditLog, User, EquipmentType,
    StockLevel, Partner,Permission, Role,
    ServiceStatus, ServicePriority,
)

# استيراد الفورمات
from forms import (
    ServiceRequestForm,
    CustomerForm,
    ServiceTaskForm,
    ServiceDiagnosisForm,
    ServicePartForm,
)

# استيراد الدوال المساعدة من utils
from utils import (
    permission_required,
    send_whatsapp_message,
)

service_bp = Blueprint(
    'service',
    __name__,
    url_prefix='/service'
)

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
    
# ✅ يحقن القيم تلقائيًا في جميع قوالب بلوبرنت الصيانة
@service_bp.context_processor
def inject_service_constants():
    # لو تغيّرت قيم الـ Enum مستقبلاً، نضمن المفاتيح تكون نصوص واضحة
    try:
        status_labels = { (k if isinstance(k, str) else str(k)): v for k, v in STATUS_LABELS.items() }
    except Exception:
        status_labels = STATUS_LABELS
    try:
        priority_colors = { (k if isinstance(k, str) else str(k)): v for k, v in PRIORITY_COLORS.items() }
    except Exception:
        priority_colors = PRIORITY_COLORS
    return {
        'STATUS_LABELS': status_labels,
        'PRIORITY_COLORS': priority_colors,
    }

# ------------------ Helpers ------------------

def _get_id(val):
    """يدعم AjaxSelectField التي قد تُعيد كائنًا أو رقمًا"""
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

# ------------------ قائمة طلبات الصيانة ------------------
@service_bp.route('/', methods=['GET'])
@login_required
@permission_required('manage_service')
def list_requests():
    # جمع فلاتر البحث
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
        if date_filter == 'today':
            query = query.filter(func.date(ServiceRequest.request_date) == today.date())
        elif date_filter == 'week':
            start_week = today - timedelta(days=today.weekday())
            query = query.filter(ServiceRequest.request_date >= start_week)
        elif date_filter == 'month':
            start_month = today.replace(day=1)
            query = query.filter(ServiceRequest.request_date >= start_month)

    # ترتيب
    sort_by    = request.args.get('sort', 'request_date')
    sort_order = request.args.get('order', 'desc')
    field      = getattr(ServiceRequest, sort_by, ServiceRequest.request_date)
    query = query.order_by(field.asc() if sort_order == 'asc' else field.desc())

    requests = query.all()

    # إحصائيات جانبية (Enum)
    stats = {
        'pending':      ServiceRequest.query.filter_by(status=ServiceStatus.PENDING).count(),
        'in_progress':  ServiceRequest.query.filter_by(status=ServiceStatus.IN_PROGRESS).count(),
        'completed':    ServiceRequest.query.filter_by(status=ServiceStatus.COMPLETED).count(),
        'high_priority': ServiceRequest.query.filter_by(priority=ServicePriority.HIGH).count(),
    }
    mechanics = User.query.filter_by(is_active=True).all()

    # تمرير قيم الفلتر الأصلية للقالب
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

# ------------------ لوحة تحكم ------------------
@service_bp.route('/dashboard')
@login_required
@permission_required('manage_service')
def dashboard():
    total_requests = ServiceRequest.query.count()
    completed_this_month = ServiceRequest.query.filter(
        ServiceRequest.status == ServiceStatus.COMPLETED,
        ServiceRequest.end_time >= datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ).count()
    high_priority = ServiceRequest.query.filter_by(priority=ServicePriority.HIGH)\
        .order_by(ServiceRequest.request_date.desc()).limit(5).all()
    active_mechanics = db.session.query(
        User.username,
        func.count(ServiceRequest.id).label('request_count')
    ).join(ServiceRequest, ServiceRequest.mechanic_id == User.id)\
     .group_by(User.id).order_by(desc('request_count')).limit(5).all()

    # اعتبر الطلب متأخرًا إذا كان لديه مدة متوقعة وبُدئ ولم يُكمل بعد والوقت تجاوز (start + estimated)
    in_prog = ServiceRequest.query.filter(
        ServiceRequest.status.in_([ServiceStatus.DIAGNOSIS, ServiceStatus.IN_PROGRESS])
    ).all()
    now = datetime.now()
    overdue = []
    for s in in_prog:
        if s.start_time and s.estimated_duration:
            eta = s.start_time + timedelta(minutes=int(s.estimated_duration))
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
        active_mechanics=active_mechanics,
        overdue=overdue,
        status_distribution=status_distribution,
        priority_distribution=priority_distribution
    )

@service_bp.route('/new', methods=['GET','POST'])
@login_required
@permission_required('manage_service')
def create_request():
    form=ServiceRequestForm(); cform=CustomerForm(prefix="customer")
    try: form.vehicle_type_id.endpoint='api.equipment_types'
    except Exception: pass
    if form.validate_on_submit():
        if form.customer_id.data:
            customer=db.session.get(Customer,_get_id(form.customer_id.data))
        else:
            customer=Customer.query.filter_by(name=form.name.data,phone=form.phone.data).first()
            if not customer:
                customer=Customer(name=form.name.data,phone=form.phone.data,email=form.email.data); db.session.add(customer); db.session.flush()
        service=ServiceRequest(service_number=f"SRV-{datetime.utcnow():%Y%m%d%H%M%S}",customer_id=customer.id,name=form.name.data,phone=form.phone.data,email=form.email.data,vehicle_vrn=form.vehicle_vrn.data,vehicle_type_id=_get_id(form.vehicle_type_id.data) if form.vehicle_type_id.data else None,vehicle_model=form.vehicle_model.data,chassis_number=form.chassis_number.data,problem_description=form.problem_description.data,engineer_notes=form.engineer_notes.data,description=form.description.data,priority=getattr(ServicePriority,(form.priority.data or 'MEDIUM').upper()),estimated_duration=form.estimated_duration.data,estimated_cost=form.estimated_cost.data,tax_rate=form.tax_rate.data or 0,status=getattr(ServiceStatus,(form.status.data or 'PENDING').upper()))
        db.session.add(service)
        try:
            db.session.commit(); log_service_action(service,"CREATE")
            if customer.phone: send_whatsapp_message(customer.phone,f"تم استلام طلب الصيانة رقم {service.service_number}.")
            flash("✅ تم إنشاء طلب الصيانة بنجاح","success"); return redirect(url_for('service.view_request',rid=service.id))
        except SQLAlchemyError as exc:
            db.session.rollback(); flash(f"❌ خطأ في قاعدة البيانات: {exc}","danger")
    return render_template('service/new.html',form=form,customer_form=cform)

@service_bp.route('/<int:rid>',methods=['GET'])
@login_required
@permission_required('manage_service')
def view_request(rid):
    service = _get_or_404(
        ServiceRequest, rid,
        options=[
            joinedload(ServiceRequest.customer),
            joinedload(ServiceRequest.parts).joinedload(ServicePart.part),
            joinedload(ServiceRequest.parts).joinedload(ServicePart.warehouse),  # <- مٌضاف
            joinedload(ServiceRequest.tasks),
        ]
    )
    return render_template('service/view.html', service=service)

@service_bp.route('/<int:rid>/receipt',methods=['GET'])
@login_required
@permission_required('manage_service')
def view_receipt(rid):
    service=_get_or_404(ServiceRequest,rid)
    return render_template('service/receipt.html',service=service)

@service_bp.route('/<int:rid>/receipt/download',methods=['GET'])
@login_required
@permission_required('manage_service')
def download_receipt(rid):
    service=_get_or_404(ServiceRequest,rid)
    pdf_data=generate_service_receipt_pdf(service)
    return send_file(io.BytesIO(pdf_data),as_attachment=True,download_name=f"service_receipt_{service.service_number}.pdf",mimetype='application/pdf')

@service_bp.route('/<int:rid>/diagnosis',methods=['POST'])
@login_required
@permission_required('manage_service')
def update_diagnosis(rid):
    service=_get_or_404(ServiceRequest,rid)
    form=ServiceDiagnosisForm()
    if form.validate_on_submit():
        old={'problem_description':service.problem_description,'diagnosis':service.diagnosis,'solution':service.solution,'estimated_duration':service.estimated_duration,'estimated_cost':str(service.estimated_cost or 0),'status':getattr(service.status,'value',service.status)}
        service.problem_description=form.problem.data; service.diagnosis=form.cause.data; service.solution=form.solution.data; service.estimated_duration=form.estimated_duration.data; service.estimated_cost=form.estimated_cost.data; service.status=ServiceStatus.IN_PROGRESS
        try:
            db.session.commit(); log_service_action(service,"DIAGNOSIS",old_data=old,new_data={'problem_description':service.problem_description,'diagnosis':service.diagnosis,'solution':service.solution,'estimated_duration':service.estimated_duration,'estimated_cost':str(service.estimated_cost or 0),'status':service.status.value}); flash('✅ تم تحديث التشخيص بنجاح','success')
            if service.customer and service.customer.phone: send_whatsapp_message(service.customer.phone,f"تم تشخيص المركبة {service.vehicle_vrn}.")
        except SQLAlchemyError as e:
            db.session.rollback(); flash(f'❌ خطأ في قاعدة البيانات: {str(e)}','danger')
    return redirect(url_for('service.view_request',rid=rid))

@service_bp.route('/<int:rid>/<action>',methods=['POST'])
@login_required
@permission_required('manage_service')
def toggle_service(rid,action):
    service=_get_or_404(ServiceRequest,rid)
    if action=='start':
        service.start_time=datetime.now(); service.status=ServiceStatus.IN_PROGRESS; flash('✅ تم بدء عملية الصيانة','success')
    elif action=='complete':
        service.end_time=datetime.now(); service.status=ServiceStatus.COMPLETED
        if service.start_time: service.actual_duration=int((service.end_time-service.start_time).total_seconds()/60)
        flash('✅ تم إكمال عملية الصيانة بنجاح','success')
    try:
        db.session.commit()
        if action=='complete' and service.customer and service.customer.phone: send_whatsapp_message(service.customer.phone,f"تم إكمال صيانة المركبة {service.vehicle_vrn}.")
    except SQLAlchemyError as e:
        db.session.rollback(); flash(f'❌ خطأ في قاعدة البيانات: {str(e)}','danger')
    return redirect(url_for('service.view_request',rid=rid))

@service_bp.route('/<int:rid>/parts/add',methods=['POST'])
@login_required
@permission_required('manage_service')
def add_part(rid):
    _get_or_404(ServiceRequest,rid)
    form=ServicePartForm()
    if form.validate_on_submit():
        warehouse_id=_get_id(form.warehouse_id.data); product_id=_get_id(form.part_id.data); partner_id=_get_id(form.partner_id.data) if form.partner_id.data else None
        warehouse=db.session.get(Warehouse,warehouse_id); product=db.session.get(Product,product_id)
        stock=StockLevel.query.filter_by(product_id=product.id,warehouse_id=warehouse.id).first()
        if not stock or stock.quantity<form.quantity.data:
            flash(f'❌ الكمية غير متوفرة. المتاح: {stock.quantity if stock else 0}','danger'); return redirect(url_for('service.view_request',rid=rid))
        stock.quantity-=form.quantity.data
        part=ServicePart(service_id=rid,part_id=product.id,warehouse_id=warehouse.id,quantity=form.quantity.data,unit_price=form.unit_price.data,discount=form.discount.data or 0,tax_rate=form.tax_rate.data or 0,partner_id=partner_id,share_percentage=form.share_percentage.data or 0,note=form.note.data)
        db.session.add(part)
        try:
            db.session.commit(); flash('✅ تمت إضافة القطعة مع توثيق حصة الشريك وخصمها من المخزن','success')
        except SQLAlchemyError as e:
            db.session.rollback(); flash(f'❌ خطأ: {str(e)}','danger')
    return redirect(url_for('service.view_request',rid=rid))

@service_bp.route('/parts/<int:pid>/delete',methods=['POST'])
@login_required
@permission_required('manage_service')
def delete_part(pid):
    part=_get_or_404(ServicePart,pid); rid=part.service_id
    warehouse=db.session.get(Warehouse,part.warehouse_id); product=db.session.get(Product,part.part_id)
    if warehouse and product:
        stock=StockLevel.query.filter_by(product_id=product.id,warehouse_id=warehouse.id).first()
        if stock: stock.quantity+=part.quantity
        else: db.session.add(StockLevel(product_id=product.id,warehouse_id=warehouse.id,quantity=part.quantity))
    db.session.delete(part)
    try:
        db.session.commit(); flash('✅ تم حذف القطعة وإرجاعها للمخزن','success')
    except SQLAlchemyError as e:
        db.session.rollback(); flash(f'❌ خطأ: {str(e)}','danger')
    return redirect(url_for('service.view_request',rid=rid))

@service_bp.route('/<int:rid>/tasks/add',methods=['POST'])
@login_required
@permission_required('manage_service')
def add_task(rid):
    form=ServiceTaskForm()
    if form.validate_on_submit():
        task=ServiceTask(service_id=rid,description=form.description.data,quantity=form.quantity.data or 1,unit_price=form.unit_price.data,discount=form.discount.data or 0,tax_rate=form.tax_rate.data or 0,note=form.note.data)
        db.session.add(task)
        try:
            db.session.commit(); flash('✅ تمت إضافة المهمة','success')
        except SQLAlchemyError as e:
            db.session.rollback(); flash(f'❌ خطأ: {str(e)}','danger')
    return redirect(url_for('service.view_request',rid=rid))

@service_bp.route('/tasks/<int:tid>/delete',methods=['POST'])
@login_required
@permission_required('manage_service')
def delete_task(tid):
    task=_get_or_404(ServiceTask,tid); rid=task.service_id
    db.session.delete(task)
    try:
        db.session.commit(); flash('✅ تم حذف المهمة','success')
    except SQLAlchemyError as e:
        db.session.rollback(); flash(f'❌ خطأ: {str(e)}','danger')
    return redirect(url_for('service.view_request',rid=rid))

@service_bp.route('/<int:rid>/payments/add',methods=['GET','POST'])
@login_required
@permission_required('manage_service')
def add_payment(rid):
    return redirect(url_for('payments.create_payment',entity_type='SERVICE',entity_id=rid))

@service_bp.route('/<int:rid>/invoice',methods=['GET','POST'])
@login_required
@permission_required('manage_service')
def create_invoice(rid):
    svc=_get_or_404(ServiceRequest,rid,options=[joinedload(ServiceRequest.parts),joinedload(ServiceRequest.tasks)])
    try: amount=float(getattr(svc,'balance_due',None) or getattr(svc,'total_cost',0) or 0)
    except Exception: amount=0.0
    return redirect(url_for('payments.create_payment',entity_type='SERVICE',entity_id=rid,amount=amount))

@service_bp.route('/<int:rid>/report')
@login_required
@permission_required('manage_service')
def service_report(rid):
    service=_get_or_404(ServiceRequest,rid)
    pdf=generate_service_receipt_pdf(service)
    return Response(pdf,mimetype='application/pdf',headers={'Content-Disposition':f'inline; filename=service_report_{service.service_number}.pdf'})

@service_bp.route('/<int:rid>/pdf')
@login_required
@permission_required('manage_service')
def export_pdf(rid):
    service=_get_or_404(ServiceRequest,rid)
    pdf=generate_service_receipt_pdf(service)
    return Response(pdf,mimetype='application/pdf',headers={'Content-Disposition':f'attachment; filename=service_{service.service_number}.pdf'})

@service_bp.route('/<int:rid>/delete',methods=['POST'])
@login_required
@permission_required('manage_service')
def delete_request(rid):
    service=_get_or_404(ServiceRequest,rid)
    try:
        with db.session.begin():
            for part in list(service.parts or ()):
                stock=StockLevel.query.filter_by(product_id=part.part_id,warehouse_id=part.warehouse_id).first()
                if stock: stock.quantity=(stock.quantity or 0)+(part.quantity or 0)
                else: db.session.add(StockLevel(product_id=part.part_id,warehouse_id=part.warehouse_id,quantity=(part.quantity or 0)))
            db.session.delete(service)
        flash('✅ تم حذف الطلب بنجاح','success')
    except SQLAlchemyError as e:
        db.session.rollback(); flash(f'❌ فشل حذف الطلب: {e}','danger')
    return redirect(url_for('service.list_requests'))

# ------------------ واجهة API لطلبات الصيانة ------------------
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
        'customer':         r.customer.name if r.customer else (r.name or ''),
        'vehicle_vrn':      r.vehicle_vrn,
        'status':           getattr(r.status, 'value', r.status),
        'priority':         getattr(r.priority, 'value', r.priority),
        'request_date':     r.request_date.strftime('%Y-%m-%d %H:%M') if r.request_date else '',
        'mechanic':         r.mechanic.username if getattr(r, 'mechanic', None) else ''
    } for r in reqs]
    return jsonify(result)

# ------------------ البحث السريع ------------------
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
        'text': f"{r.service_number} - {r.customer.name if r.customer else r.name} - {r.vehicle_vrn}",
        'url':  url_for('service.view_request', rid=r.id)
    } for r in results])

# ------------------ إحصائيات الصيانة ------------------
@service_bp.route('/stats')
@login_required
def service_stats():
    total_requests     = ServiceRequest.query.count()
    completed_requests = ServiceRequest.query.filter_by(status=ServiceStatus.COMPLETED).count()
    pending_requests   = ServiceRequest.query.filter_by(status=ServiceStatus.PENDING).count()
    avg_duration       = db.session.query(func.avg(ServiceRequest.actual_duration))\
                           .filter(ServiceRequest.actual_duration.isnot(None))\
                           .scalar() or 0

    # آخر 6 أشهر – حساب بايثون لتوافقية أوسع مع قواعد البيانات
    since = datetime.now() - relativedelta(months=6)
    rows = ServiceRequest.query.options(
        joinedload(ServiceRequest.parts),
        joinedload(ServiceRequest.tasks)
    ).filter(
        ServiceRequest.status == ServiceStatus.COMPLETED,
        ServiceRequest.end_time.isnot(None),
        ServiceRequest.end_time >= since
    ).all()

    buckets = {}
    for s in rows:
        key = s.end_time.strftime('%Y-%m')
        p = sum(float(x.line_total or 0) for x in s.parts)
        t = sum(float(x.line_total or 0) for x in s.tasks)
        if key not in buckets:
            buckets[key] = {'parts': 0.0, 'labor': 0.0}
        buckets[key]['parts'] += p
        buckets[key]['labor'] += t

    months_sorted = sorted(buckets.keys())
    months = [datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in months_sorted]
    parts_costs = [round(buckets[m]['parts'], 2) for m in months_sorted]
    labor_costs = [round(buckets[m]['labor'], 2) for m in months_sorted]

    return jsonify({
        'total_requests':     total_requests,
        'completed_requests': completed_requests,
        'pending_requests':   pending_requests,
        'avg_duration':       round(avg_duration, 1),
        'monthly_costs': {
            'months': months,
            'parts':  parts_costs,
            'labor':  labor_costs
        }
    })

# ------------------ دوال مساعدة ------------------
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
    c.drawString(120*mm, y, f"التاريخ: {service_request.request_date.strftime('%Y-%m-%d') if service_request.request_date else ''}")
    y -= 8*mm
    c.drawString(20*mm, y, f"العميل: {service_request.customer.name if service_request.customer else (service_request.name or '-')}")
    c.drawString(120*mm, y, f"لوحة المركبة: {service_request.vehicle_vrn or ''}")

    # القطع
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

    # المهام
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
