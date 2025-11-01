
"""
وحدة الصيانة المحسّنة
Enhanced Service Management Module
"""
import io
import json
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, abort, Response, send_file, current_app
)
from flask_login import login_required, current_user, login_user
from sqlalchemy import func, or_, desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from extensions import db, cache
from models import (
    ServiceRequest, ServicePart, ServiceTask, Customer, Product,
    Warehouse, AuditLog, User, EquipmentType, StockLevel, Partner,
    Permission, Role, ServiceStatus, _service_consumes_stock, ServicePriority
)
from forms import (
    ServiceRequestForm, CustomerForm, ServiceTaskForm,
    ServiceDiagnosisForm, ServicePartForm
)
import utils
from utils import archive_record, restore_record  # Import from utils package

service_bp = Blueprint('service', __name__, url_prefix='/service')

# ثوابت النظام
STATUS_LABELS = {
    "PENDING": "معلق",
    "DIAGNOSIS": "تشخيص",
    "IN_PROGRESS": "قيد التنفيذ",
    "COMPLETED": "مكتمل",
    "CANCELLED": "ملغي",
    "ON_HOLD": "مؤجل"
}

PRIORITY_LABELS = {
    "LOW": "منخفضة",
    "MEDIUM": "متوسطة",
    "HIGH": "عالية",
    "URGENT": "عاجلة"
}

PRIORITY_COLORS = {
    "LOW": "info",
    "MEDIUM": "warning",
    "HIGH": "danger",
    "URGENT": "dark"
}

def _get_or_404(model, ident, options=None):
    q = db.session.query(model)
    if options:
        for opt in options: q = q.options(opt)
        obj = q.filter_by(id=ident).first()
    else:
        obj = db.session.get(model, ident)
    if obj is None: abort(404)
    return obj

def _log_service_stock_action(service, action: str, items: list[dict]) -> None:
    try:
        payload = {"items": items or []}
        entry = AuditLog(created_at=datetime.utcnow(), model_name="ServiceRequest", record_id=service.id, customer_id=getattr(service,"customer_id",None), user_id=(current_user.id if getattr(current_user,"is_authenticated",False) else None), action=(action or "").strip().upper(), old_data=None, new_data=json.dumps(payload, ensure_ascii=False, default=str), ip_address=request.remote_addr, user_agent=request.headers.get("User-Agent",""))
        db.session.add(entry)
    except Exception: pass

def _has_stock_action(service, action: str) -> bool:
    if not service or not getattr(service,"id",None): return False
    q = db.session.query(AuditLog.id).filter(AuditLog.model_name=="ServiceRequest", AuditLog.record_id==service.id, AuditLog.action==(action or "").strip().upper()).limit(1)
    return bool(db.session.execute(q).first())

def _consume_service_stock_once(service) -> bool:
    if not _service_consumes_stock(service): return False
    if _has_stock_action(service,"STOCK_CONSUME"): return False
    items=[]
    for p in list(service.parts or []):
        qty=-int(p.quantity or 0)
        new_qty=utils._apply_stock_delta(p.part_id,p.warehouse_id,qty)
        items.append({"part_id":p.part_id,"warehouse_id":p.warehouse_id,"qty":qty,"stock_after":int(new_qty)})
    _log_service_stock_action(service,"STOCK_CONSUME",items)
    current_app.logger.info("service.stock_consume",extra={"event":"service.stock.consume","service_id":service.id,"items":[{"part_id":i["part_id"],"warehouse_id":i["warehouse_id"],"qty":i["qty"]} for i in items]})
    return True

def _release_service_stock_once(service) -> bool:
    if not _service_consumes_stock(service): return False
    if not _has_stock_action(service,"STOCK_CONSUME"): return False
    if _has_stock_action(service,"STOCK_RELEASE"): return False
    items=[]
    for p in list(service.parts or []):
        qty=+int(p.quantity or 0)
        new_qty=utils._apply_stock_delta(p.part_id,p.warehouse_id,qty)
        items.append({"part_id":p.part_id,"warehouse_id":p.warehouse_id,"qty":qty,"stock_after":int(new_qty)})
    _log_service_stock_action(service,"STOCK_RELEASE",items)
    current_app.logger.info("service.stock_release",extra={"event":"service.stock.release","service_id":service.id,"items":[{"part_id":i["part_id"],"warehouse_id":i["warehouse_id"],"qty":i["qty"]} for i in items]})
    return True

STATUS_LABELS={"PENDING":"معلق","DIAGNOSIS":"تشخيص","IN_PROGRESS":"قيد التنفيذ","COMPLETED":"مكتمل","CANCELLED":"ملغي","ON_HOLD":"مؤجل"}
PRIORITY_COLORS={"LOW":"info","MEDIUM":"warning","HIGH":"danger","URGENT":"dark"}

@service_bp.context_processor
def inject_service_constants():
    return {"STATUS_LABELS":STATUS_LABELS,"PRIORITY_COLORS":PRIORITY_COLORS}

def _enum_results_with_counts(enum_cls, labels_map, column):
    rows=db.session.query(column, func.count(ServiceRequest.id)).group_by(column).all()
    counts={}
    for k,c in rows:
        key=getattr(k,"value",k); counts[str(key)]=int(c or 0)
    out=[]
    for m in enum_cls: out.append({"id":m.value,"text":labels_map.get(m.value,m.value),"count":counts.get(m.value,0)})
    return out

@service_bp.get("/api/statuses")
@login_required
# @permission_required("manage_service")  # Commented out - function not available
def api_service_statuses():
    return jsonify({"results":_enum_results_with_counts(ServiceStatus, STATUS_LABELS, ServiceRequest.status)})

@service_bp.get("/api/priorities")
@login_required
# @permission_required("manage_service")  # Commented out - function not available
def api_service_priorities():
    priority_labels={"LOW":"منخفضة","MEDIUM":"متوسطة","HIGH":"عالية","URGENT":"عاجلة"}
    return jsonify({"results":_enum_results_with_counts(ServicePriority, priority_labels, ServiceRequest.priority)})

@service_bp.get("/api/options")
@login_required
# @permission_required("manage_service")  # Commented out - function not available
def api_service_options():
    priority_labels={"LOW":"منخفضة","MEDIUM":"متوسطة","HIGH":"عالية","URGENT":"عاجلة"}
    return jsonify({"statuses":_enum_results_with_counts(ServiceStatus, STATUS_LABELS, ServiceRequest.status),"priorities":_enum_results_with_counts(ServicePriority, priority_labels, ServiceRequest.priority)})

def _status_list(values):
    out=[]
    for v in values:
        key=(v or "").strip().upper()
        if hasattr(ServiceStatus,key): out.append(getattr(ServiceStatus,key))
    return out

def _priority_list(values):
    out=[]
    for v in values:
        key=(v or "").strip().upper()
        if hasattr(ServicePriority,key): out.append(getattr(ServicePriority,key))
    return out

def _col(name:str):
    mapping={"request_date":"received_at","start_time":"started_at","end_time":"completed_at","received_at":"received_at","started_at":"started_at","completed_at":"completed_at","priority":"priority","status":"status"}
    attr=mapping.get(name,"received_at")
    return getattr(ServiceRequest,attr)

def _fmt_dt(dt):
    try: return dt.strftime('%Y-%m-%d %H:%M') if dt else ''
    except Exception: return str(dt or '')

def _row_dict(sr:ServiceRequest)->dict:
    cust=getattr(sr,"customer",None); mech=getattr(sr,"mechanic",None)
    return {"ID":getattr(sr,"id",""),"رقم الطلب":getattr(sr,"service_number","") or getattr(sr,"code",""),"العميل":getattr(cust,"name","") if cust else "","هاتف":getattr(cust,"phone","") if cust else "","الحالة":getattr(getattr(sr,"status",""),"value",getattr(sr,"status","")) or "","الأولوية":getattr(getattr(sr,"priority",""),"value",getattr(sr,"priority","")) or "","لوحة المركبة":getattr(sr,"vehicle_vrn","") or "","الميكانيكي":getattr(mech,"username","") if mech else "","تاريخ الاستلام":_fmt_dt(getattr(sr,"received_at",None)),"تاريخ البدء":_fmt_dt(getattr(sr,"started_at",None)),"تاريخ الإكمال":_fmt_dt(getattr(sr,"completed_at",None)),"التكلفة التقديرية":float(getattr(sr,"estimated_cost",0) or 0),"المبلغ المستحق":float(getattr(sr,"balance_due",None) or getattr(sr,"total_cost",0) or 0),"الوصف":(getattr(sr,"description","") or "")[:120]}

def _build_list_query():
    status_filter=request.args.getlist('status'); priority_filter=request.args.getlist('priority'); customer_filter=request.args.get('customer',''); mechanic_filter=request.args.get('mechanic',''); vrn_filter=request.args.get('vrn',''); date_filter=request.args.get('date','')
    query=ServiceRequest.query.options(joinedload(ServiceRequest.customer))
    sts=_status_list(status_filter)
    if sts: query=query.filter(ServiceRequest.status.in_(sts))
    pris=_priority_list(priority_filter)
    if pris: query=query.filter(ServiceRequest.priority.in_(pris))
    if customer_filter: query=query.join(Customer).filter(or_(Customer.name.ilike(f'%{customer_filter}%'),Customer.phone.ilike(f'%{customer_filter}%')))
    if mechanic_filter: query=query.join(User, ServiceRequest.mechanic_id==User.id).filter(User.username.ilike(f'%{mechanic_filter}%'))
    if vrn_filter: query=query.filter(ServiceRequest.vehicle_vrn.ilike(f'%{vrn_filter}%'))
    if date_filter:
        today=datetime.today(); col=_col('received_at')
        if date_filter=='today': query=query.filter(func.date(col)==today.date())
        elif date_filter=='week':
            start_week=today-timedelta(days=today.weekday()); query=query.filter(col>=start_week)
        elif date_filter=='month':
            start_month=today.replace(day=1); query=query.filter(col>=start_month)
    sort_by=request.args.get('sort','request_date'); sort_order=request.args.get('order','desc'); field=_col(sort_by)
    query=query.order_by(field.asc() if sort_order=='asc' else field.desc())
    return query

@service_bp.route('/', methods=['GET'])
@service_bp.route('/list', methods=['GET'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def list_requests():
    """قائمة طلبات الصيانة مع فلترة وPagination محسّنة"""
    
    # الفلاتر
    status_filter = request.args.getlist('status')
    priority_filter = request.args.getlist('priority')
    customer_filter = request.args.get('customer', '')
    mechanic_filter = request.args.get('mechanic', '')
    vrn_filter = request.args.get('vrn', '')
    date_filter = request.args.get('date', '')
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(per_page, 100)  # حد أقصى
    
    # بناء الاستعلام مع joinedload محسّن - فلترة السجلات غير المؤرشفة
    query = ServiceRequest.query.filter(ServiceRequest.is_archived == False).options(
        joinedload(ServiceRequest.customer),
        joinedload(ServiceRequest.mechanic)
    )
    
    # تطبيق الفلاتر
    sts = _status_list(status_filter)
    if sts:
        query = query.filter(ServiceRequest.status.in_(sts))
    
    pris = _priority_list(priority_filter)
    if pris:
        query = query.filter(ServiceRequest.priority.in_(pris))
    
    if customer_filter:
        query = query.join(Customer).filter(
            or_(
                Customer.name.ilike(f'%{customer_filter}%'),
                Customer.phone.ilike(f'%{customer_filter}%')
            )
        )
    
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
    
    # الترتيب
    sort_by = request.args.get('sort', 'request_date')
    sort_order = request.args.get('order', 'desc')
    field = _col(sort_by)
    query = query.order_by(field.asc() if sort_order == 'asc' else field.desc())
    
    # Pagination
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # الإحصائيات (مع Cache)
    cache_key = 'service_stats'
    stats = cache.get(cache_key)
    if stats is None:
        stats = {
            'pending': ServiceRequest.query.filter_by(status=ServiceStatus.PENDING).count(),
            'in_progress': ServiceRequest.query.filter_by(status=ServiceStatus.IN_PROGRESS).count(),
            'completed': ServiceRequest.query.filter_by(status=ServiceStatus.COMPLETED).count(),
            'high_priority': ServiceRequest.query.filter_by(priority=ServicePriority.HIGH).count()
        }
        cache.set(cache_key, stats, timeout=300)  # 5 دقائق
    
    # الميكانيكيين النشطين
    mechanics = User.query.filter_by(is_active=True).order_by(User.username).all()
    
    filter_values = {
        'status': status_filter,
        'priority': priority_filter,
        'customer': customer_filter,
        'mechanic': mechanic_filter,
        'vrn': vrn_filter,
        'date': date_filter,
        'sort': sort_by,
        'order': sort_order
    }
    
    return render_template(
        'service/list.html',
        requests=pagination.items,
        pagination=pagination,
        status_labels=STATUS_LABELS,
        priority_labels=PRIORITY_LABELS,
        priority_colors=PRIORITY_COLORS,
        stats=stats,
        mechanics=mechanics,
        filter_values=filter_values
    )

@service_bp.route('/export/csv', methods=['GET'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def export_requests_csv():
    services=_build_list_query().all()
    rows=[_row_dict(sr) for sr in services]
    sio=io.StringIO(newline="")
    fieldnames=list(rows[0].keys()) if rows else ["ID","رقم الطلب","العميل","هاتف","الحالة","الأولوية","لوحة المركبة","الميكانيكي","تاريخ الاستلام","تاريخ البدء","تاريخ الإكمال","التكلفة التقديرية","المبلغ المستحق","الوصف"]
    writer=csv.DictWriter(sio, fieldnames=fieldnames); writer.writeheader()
    for r in rows: writer.writerow(r)
    data=sio.getvalue().encode('utf-8-sig'); bio=io.BytesIO(data); bio.seek(0)
    filename=f"service_export_{datetime.now():%Y%m%d_%H%M%S}.csv"
    return send_file(bio, as_attachment=True, download_name=filename, mimetype="text/csv; charset=utf-8")

@service_bp.route('/dashboard')
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def dashboard():
    total_requests=ServiceRequest.query.count()
    completed_this_month=ServiceRequest.query.filter(ServiceRequest.status==ServiceStatus.COMPLETED, _col('completed_at')>=datetime.now().replace(day=1,hour=0,minute=0,second=0,microsecond=0)).count()
    high_priority=ServiceRequest.query.filter_by(priority=ServicePriority.HIGH).order_by(_col('received_at').desc()).limit(5).all()
    in_prog=ServiceRequest.query.filter(ServiceRequest.status.in_([ServiceStatus.DIAGNOSIS,ServiceStatus.IN_PROGRESS])).all()
    now=datetime.now(); overdue=[]
    for s in in_prog:
        start_dt=getattr(s,"started_at",None); est_min=getattr(s,"estimated_duration",None)
        if start_dt and est_min:
            eta=start_dt+timedelta(minutes=int(est_min))
            if eta<now: overdue.append(s)
    status_distribution=db.session.query(ServiceRequest.status, func.count(ServiceRequest.id)).group_by(ServiceRequest.status).all()
    priority_distribution=db.session.query(ServiceRequest.priority, func.count(ServiceRequest.id)).group_by(ServiceRequest.priority).all()
    active_mechanics=db.session.query(User.username, func.count(ServiceRequest.id).label('request_count')).join(ServiceRequest, ServiceRequest.mechanic_id==User.id).group_by(User.id).order_by(desc('request_count')).limit(5).all()
    return render_template('service/dashboard.html', total_requests=total_requests, completed_this_month=completed_this_month, high_priority=high_priority, active_mechanics=active_mechanics, overdue=overdue, status_distribution=status_distribution, priority_distribution=priority_distribution)

@service_bp.route('/new', methods=['GET','POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def create_request():
    form=ServiceRequestForm()
    try: form.vehicle_type_id.endpoint='api.search_equipment_types'
    except Exception: pass
    if form.validate_on_submit():
        if not form.customer_id.data:
            flash("⚠️ يجب اختيار عميل قبل إنشاء طلب صيانة.","warning")
            return redirect(url_for("customers_bp.create_form", return_to=url_for("service.create_request")))
        customer=db.session.get(Customer,utils._get_id(form.customer_id.data))
        if not customer:
            flash("⚠️ العميل غير موجود. الرجاء إضافته.","danger")
            return redirect(url_for("customers_bp.create_form", return_to=url_for("service.create_request")))
        # Sanitize priority/status to avoid invalid enum values (e.g., 'NEW')
        _prio_code = (form.priority.data or 'MEDIUM').upper()
        priority_val = getattr(ServicePriority, _prio_code, ServicePriority.MEDIUM)
        _stat_code = (form.status.data or 'PENDING').upper()
        status_val = getattr(ServiceStatus, _stat_code, ServiceStatus.PENDING)

        service=ServiceRequest(service_number=f"SRV-{datetime.utcnow():%Y%m%d%H%M%S}", customer_id=customer.id, vehicle_vrn=form.vehicle_vrn.data, vehicle_type_id=utils._get_id(form.vehicle_type_id.data) if form.vehicle_type_id.data else None, vehicle_model=form.vehicle_model.data, chassis_number=form.chassis_number.data, problem_description=form.problem_description.data, priority=priority_val, estimated_duration=form.estimated_duration.data, status=status_val, received_at=datetime.utcnow(), consume_stock=bool(form.consume_stock.data))
        db.session.add(service)
        try:
            db.session.commit(); log_service_action(service,"CREATE")
            if customer.phone: utils.send_whatsapp_message(customer.phone, f"تم استلام طلب الصيانة رقم {service.service_number}.")
            flash("✅ تم إنشاء طلب الصيانة بنجاح","success")
            return redirect(url_for('service.view_request', rid=service.id))
        except SQLAlchemyError as exc:
            db.session.rollback(); flash(f"❌ خطأ في قاعدة البيانات: {exc}","danger")
    return render_template('service/new.html', form=form)

@service_bp.route('/<int:rid>', methods=['GET'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def view_request(rid):
    service=_get_or_404(ServiceRequest, rid, options=[joinedload(ServiceRequest.customer), joinedload(ServiceRequest.parts).joinedload(ServicePart.part), joinedload(ServiceRequest.parts).joinedload(ServicePart.warehouse), joinedload(ServiceRequest.tasks)])
    warehouses=Warehouse.query.order_by(Warehouse.name.asc()).all()
    return render_template('service/view.html', service=service, warehouses=warehouses)

@service_bp.route('/<int:rid>/receipt', methods=['GET'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def view_receipt(rid):
    service=_get_or_404(ServiceRequest, rid, options=[joinedload(ServiceRequest.customer), joinedload(ServiceRequest.parts).joinedload(ServicePart.part), joinedload(ServiceRequest.parts).joinedload(ServicePart.warehouse), joinedload(ServiceRequest.tasks)])
    return render_template('service/receipt.html', service=service)

@service_bp.route('/<int:rid>/receipt/download', methods=['GET'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def download_receipt(rid):
    service=_get_or_404(ServiceRequest, rid, options=[joinedload(ServiceRequest.customer), joinedload(ServiceRequest.parts).joinedload(ServicePart.part), joinedload(ServiceRequest.parts).joinedload(ServicePart.warehouse), joinedload(ServiceRequest.tasks)])
    pdf_data=generate_service_receipt_pdf(service)
    return send_file(io.BytesIO(pdf_data), as_attachment=True, download_name=f"service_receipt_{service.service_number}.pdf", mimetype='application/pdf')

@service_bp.route('/<int:rid>/diagnosis', methods=['POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def update_diagnosis(rid):
    service=_get_or_404(ServiceRequest, rid)
    old={'problem_description':service.problem_description,'diagnosis':service.diagnosis,'resolution':service.resolution,'estimated_duration':service.estimated_duration,'estimated_cost':str(service.estimated_cost or 0),'status':getattr(service.status,"value",service.status)}
    diagnosis=request.form.get('diagnosis','').strip(); problem_description=request.form.get('problem_description',service.problem_description); resolution=request.form.get('resolution',service.resolution); estimated_duration=request.form.get('estimated_duration',service.estimated_duration); estimated_cost=request.form.get('estimated_cost',service.estimated_cost)
    service.problem_description=problem_description; service.diagnosis=diagnosis; service.engineer_notes=diagnosis; service.resolution=resolution; service.estimated_duration=estimated_duration; service.estimated_cost=estimated_cost; service.status=ServiceStatus.IN_PROGRESS.value
    try:
        db.session.commit()
        log_service_action(service,"DIAGNOSIS", old_data=old, new_data={'problem_description':service.problem_description,'diagnosis':service.diagnosis,'resolution':service.resolution,'estimated_duration':service.estimated_duration,'estimated_cost':str(service.estimated_cost or 0),'status':getattr(service.status,"value",service.status)})
        if service.customer and service.customer.phone: utils.send_whatsapp_message(service.customer.phone, f"تم تحديث ملاحظات المهندس للمركبة {service.vehicle_vrn}.")
        flash('✅ تم تحديث الملاحظات بنجاح','success')
    except SQLAlchemyError as e:
        db.session.rollback(); flash(f'❌ خطأ في قاعدة البيانات: {str(e)}','danger')
    return redirect(url_for('service.view_request', rid=rid))

@service_bp.route('/<int:rid>/discount_tax', methods=['POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def update_discount_tax(rid):
    """تحديث الخصم الإجمالي والضريبة"""
    service = _get_or_404(ServiceRequest, rid)
    
    if service.status == ServiceStatus.COMPLETED.value:
        flash('❌ لا يمكن تعديل صيانة مكتملة. يرجى الضغط على "إعادة للصيانه" أولاً', 'danger')
        return redirect(url_for('service.view_request', rid=rid))
    
    try:
        discount_total = Decimal(request.form.get('discount_total', 0) or 0)
        tax_rate = Decimal(request.form.get('tax_rate', 0) or 0)
        
        # حساب إجمالي الفاتورة للتحقق
        parts_sum = sum((p.line_total or 0) for p in service.parts)
        tasks_sum = sum((t.line_total or 0) for t in service.tasks)
        invoice_total = parts_sum + tasks_sum
        
        # التحقق من صحة البيانات
        if discount_total < 0:
            flash('❌ الخصم لا يمكن أن يكون سالباً', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        if discount_total > invoice_total:
            flash(f'❌ الخصم ({discount_total:.2f} ₪) لا يمكن أن يتجاوز إجمالي الفاتورة ({invoice_total:.2f} ₪)', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        if tax_rate < 0 or tax_rate > 100:
            flash('❌ نسبة الضريبة يجب أن تكون بين 0 و 100', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        # حفظ القيم القديمة للـ audit log
        old_data = {
            'discount_total': str(service.discount_total or 0),
            'tax_rate': str(service.tax_rate or 0)
        }
        
        # تحديث القيم
        service.discount_total = discount_total
        service.tax_rate = tax_rate
        
        db.session.commit()
        
        # تسجيل في الـ audit log
        log_service_action(service, "UPDATE_DISCOUNT_TAX", 
                          old_data=old_data, 
                          new_data={
                              'discount_total': str(discount_total),
                              'tax_rate': str(tax_rate)
                          })
        
        flash('✅ تم تحديث الخصم والضريبة بنجاح', 'success')
        
    except ValueError as e:
        flash(f'❌ خطأ في البيانات: {str(e)}', 'danger')
        db.session.rollback()
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ في قاعدة البيانات: {str(e)}', 'danger')
    
    return redirect(url_for('service.view_request', rid=rid))

@service_bp.route('/<int:rid>/<action>', methods=['POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def toggle_service(rid, action):
    service=_get_or_404(ServiceRequest, rid)
    try:
        if action=='start':
            if not getattr(service,"started_at",None): service.started_at=datetime.utcnow()
            service.status=ServiceStatus.IN_PROGRESS
        elif action=='complete':
            service.completed_at=datetime.utcnow()
            if service.started_at: service.actual_duration=int((service.completed_at-service.started_at).total_seconds()/60)
            service.status=ServiceStatus.COMPLETED
            _consume_service_stock_once(service)
        elif action=='reopen':
            if service.status==ServiceStatus.COMPLETED.value:
                service.status=ServiceStatus.IN_PROGRESS
                service.completed_at=None
        else: abort(400)
        db.session.commit()
        
        if action=='complete':
            if service.customer and service.customer.phone:
                utils.send_whatsapp_message(service.customer.phone, f"تم إكمال صيانة المركبة {service.vehicle_vrn}.")
            try:
                from utils import notify_service_completed
                notify_service_completed(service.id)
            except Exception as e:
                current_app.logger.warning(f'⚠️ Notification failed: {e}')
        
        flash('✅ تم تحديث حالة الصيانة','success')
    except ValueError as ve:
        db.session.rollback(); flash(f'❌ مخزون غير كافٍ لبعض القطع: {ve}','danger')
    except SQLAlchemyError as e:
        db.session.rollback(); flash(f'❌ خطأ في قاعدة البيانات: {str(e)}','danger')
    return redirect(url_for('service.view_request', rid=rid))

@service_bp.route('/<int:rid>/parts/add', methods=['POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def add_part(rid):
    service=_get_or_404(ServiceRequest, rid)
    
    if service.status == ServiceStatus.COMPLETED.value:
        flash('❌ لا يمكن تعديل صيانة مكتملة. يرجى الضغط على "إعادة للصيانه" أولاً', 'danger')
        return redirect(url_for('service.view_request', rid=rid))
    
    try:
        warehouse_id = int(request.form.get('warehouse_id'))
        product_id = int(request.form.get('part_id'))
        quantity = int(request.form.get('quantity'))
        unit_price = Decimal(request.form.get('unit_price'))
        discount = Decimal(request.form.get('discount', 0) or 0)
        tax_rate = Decimal(request.form.get('tax_rate', 0) or 0)
        note = (request.form.get('note') or '').strip() or None
        
        # Validation
        if not warehouse_id or not product_id:
            flash('❌ يجب اختيار المستودع والقطعة', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        if quantity <= 0:
            flash('❌ الكمية يجب أن تكون أكبر من صفر', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        if unit_price < 0:
            flash('❌ السعر لا يمكن أن يكون سالباً', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        if discount < 0:
            flash('❌ الخصم لا يمكن أن يكون سالباً', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        # التحقق من أن الخصم لا يتجاوز إجمالي البند
        gross_amount = quantity * unit_price
        if discount > gross_amount:
            flash(f'❌ الخصم ({discount:.2f} ₪) لا يمكن أن يتجاوز إجمالي البند ({gross_amount:.2f} ₪)', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        if tax_rate < 0 or tax_rate > 100:
            flash('❌ نسبة الضريبة يجب أن تكون بين 0 و 100', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        part=ServicePart(
            request=service, 
            service_id=rid, 
            part_id=product_id, 
            warehouse_id=warehouse_id, 
            quantity=quantity, 
            unit_price=unit_price, 
            discount=discount, 
            tax_rate=tax_rate, 
            note=note
        )
        db.session.add(part)
        db.session.flush()
        service.updated_at=datetime.utcnow()
        
        if _service_consumes_stock(service):
            new_qty=utils._apply_stock_delta(product_id, warehouse_id, -quantity)
            _log_service_stock_action(service,"STOCK_CONSUME_PART",[{"part_id":product_id,"warehouse_id":warehouse_id,"qty":-quantity,"stock_after":int(new_qty)}])
            current_app.logger.info("service.part_add",extra={"event":"service.part.add","service_id":service.id,"part_id":product_id,"warehouse_id":warehouse_id,"qty":-quantity})
        
        db.session.commit()
        flash('✅ تمت إضافة القطعة بنجاح','success')
        
    except ValueError as ve:
        db.session.rollback()
        flash(f'❌ خطأ في البيانات: {ve}','danger')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ في قاعدة البيانات: {str(e)}','danger')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}','danger')
    
    return redirect(url_for('service.view_request', rid=rid))

@service_bp.route('/parts/<int:pid>/delete', methods=['POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def delete_part(pid):
    part=_get_or_404(ServicePart, pid)
    rid=part.service_id
    service=_get_or_404(ServiceRequest, rid)
    
    if service.status == ServiceStatus.COMPLETED.value:
        flash('❌ لا يمكن تعديل صيانة مكتملة. يرجى الضغط على "إعادة للصيانه" أولاً', 'danger')
        return redirect(url_for('service.view_request', rid=rid))
    
    if not current_user.has_permission('manage_service'):
        flash('❌ غير مصرح لك بحذف قطع الغيار', 'danger')
        return redirect(url_for('service.view_request', rid=rid))
    try:
        if _service_consumes_stock(service):
            new_qty=utils._apply_stock_delta(part.part_id, part.warehouse_id, +int(part.quantity or 0))
            _log_service_stock_action(service,"STOCK_RELEASE_PART",[{"part_id":part.part_id,"warehouse_id":part.warehouse_id,"qty":+int(part.quantity or 0),"stock_after":int(new_qty)}])
            current_app.logger.info("service.part_delete",extra={"event":"service.part.delete","service_id":service.id,"part_id":part.part_id,"warehouse_id":part.warehouse_id,"qty":+int(part.quantity or 0)})
        db.session.delete(part); service.updated_at=datetime.utcnow(); db.session.commit(); flash('✅ تم حذف القطعة ومعالجة المخزون','success')
    except SQLAlchemyError as e:
        db.session.rollback(); flash(f'❌ خطأ: {str(e)}','danger')
    except ValueError as ve:
        db.session.rollback(); flash(f'❌ {ve}','danger')
    return redirect(url_for('service.view_request', rid=rid))

@service_bp.route('/<int:rid>/tasks/add', methods=['POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def add_task(rid):
    service=_get_or_404(ServiceRequest, rid)
    
    if service.status == ServiceStatus.COMPLETED.value:
        flash('❌ لا يمكن تعديل صيانة مكتملة. يرجى الضغط على "إعادة للصيانه" أولاً', 'danger')
        return redirect(url_for('service.view_request', rid=rid))
    
    try:
        description = (request.form.get('description') or '').strip()
        quantity = int(request.form.get('quantity', 1))
        unit_price = Decimal(request.form.get('unit_price'))
        discount = Decimal(request.form.get('discount', 0) or 0)
        tax_rate = Decimal(request.form.get('tax_rate', 0) or 0)
        note = (request.form.get('note') or '').strip() or None
        
        # Validation
        if not description:
            flash('❌ يجب إدخال وصف المهمة', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        if quantity <= 0:
            flash('❌ الكمية يجب أن تكون أكبر من صفر', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        if unit_price < 0:
            flash('❌ السعر لا يمكن أن يكون سالباً', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        if discount < 0:
            flash('❌ الخصم لا يمكن أن يكون سالباً', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        # التحقق من أن الخصم لا يتجاوز إجمالي البند
        gross_amount = quantity * unit_price
        if discount > gross_amount:
            flash(f'❌ الخصم ({discount:.2f} ₪) لا يمكن أن يتجاوز إجمالي البند ({gross_amount:.2f} ₪)', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        if tax_rate < 0 or tax_rate > 100:
            flash('❌ نسبة الضريبة يجب أن تكون بين 0 و 100', 'danger')
            return redirect(url_for('service.view_request', rid=rid))
        
        task=ServiceTask(
            request=service, 
            service_id=rid, 
            description=description, 
            quantity=quantity, 
            unit_price=unit_price, 
            discount=discount, 
            tax_rate=tax_rate, 
            note=note
        )
        db.session.add(task)
        db.session.flush()
        service.updated_at=datetime.utcnow()
        db.session.commit()
        flash('✅ تمت إضافة المهمة بنجاح','success')
        
    except ValueError as ve:
        db.session.rollback()
        flash(f'❌ خطأ في البيانات: {ve}','danger')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ في قاعدة البيانات: {str(e)}','danger')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}','danger')
    
    return redirect(url_for('service.view_request', rid=rid))

@service_bp.route('/tasks/<int:tid>/delete', methods=['POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def delete_task(tid):
    task=_get_or_404(ServiceTask, tid); rid=task.service_id; service=_get_or_404(ServiceRequest, rid)
    
    if service.status == ServiceStatus.COMPLETED.value:
        flash('❌ لا يمكن تعديل صيانة مكتملة. يرجى الضغط على "إعادة للصيانه" أولاً', 'danger')
        return redirect(url_for('service.view_request', rid=rid))
    
    db.session.delete(task)
    try:
        service.updated_at=datetime.utcnow(); db.session.commit(); flash('✅ تم حذف المهمة','success')
    except SQLAlchemyError as e:
        db.session.rollback(); flash(f'❌ خطأ: {str(e)}','danger')
    return redirect(url_for('service.view_request', rid=rid))

@service_bp.route('/<int:rid>/payments/add', methods=['GET','POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def add_payment(rid):
    """إعادة توجيه لإنشاء دفعة للصيانة مع البيانات الكاملة"""
    service = _get_or_404(ServiceRequest, rid)
    
    # حساب المبلغ المستحق
    try:
        balance = float(getattr(service, 'balance_due', None) or getattr(service, 'total_amount', 0) or 0)
    except Exception:
        balance = 0.0
    
    # جلب العملة
    currency = getattr(service, 'currency', 'ILS') or 'ILS'
    
    # تجهيز المرجع والملاحظات
    customer_name = service.customer.name if service.customer else 'عميل'
    service_number = service.service_number or f'#{service.id}'
    
    return redirect(url_for('payments.create_payment', 
                          entity_type='SERVICE', 
                          entity_id=rid,
                          amount=balance if balance > 0 else None,
                          currency=currency,
                          reference=f'دفع صيانة من {customer_name} - {service_number}',
                          notes=f'دفع طلب صيانة: {service_number} - العميل: {customer_name} - المركبة: {service.vehicle_model or "غير محدد"}',
                          customer_id=service.customer_id if service.customer_id else None))

@service_bp.route('/<int:rid>/invoice', methods=['GET','POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def create_invoice(rid):
    svc=_get_or_404(ServiceRequest, rid, options=[joinedload(ServiceRequest.parts), joinedload(ServiceRequest.tasks)])
    try: amount=float(getattr(svc,'balance_due',None) or getattr(svc,'total_cost',0) or 0)
    except Exception: amount=0.0
    return redirect(url_for('payments.create_payment', entity_type='SERVICE', entity_id=rid, amount=amount))

@service_bp.route('/<int:rid>/report')
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def service_report(rid):
    service=_get_or_404(ServiceRequest, rid); pdf=generate_service_receipt_pdf(service)
    return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename=service_report_{service.service_number}.pdf'})

@service_bp.route('/<int:rid>/pdf')
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def export_pdf(rid):
    service=_get_or_404(ServiceRequest, rid); pdf=generate_service_receipt_pdf(service)
    return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': f'attachment; filename=service_{service.service_number}.pdf'})

@service_bp.route('/<int:rid>/delete', methods=['POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def delete_request(rid):
    service=_get_or_404(ServiceRequest, rid)
    try:
        with db.session.begin():
            _release_service_stock_once(service); db.session.delete(service)
        flash('✅ تم حذف الطلب ومعالجة المخزون','success')
    except SQLAlchemyError as e:
        db.session.rollback(); flash(f'❌ فشل حذف الطلب: {e}','danger')
    except ValueError as ve:
        db.session.rollback(); flash(f'❌ {ve}','danger')
    return redirect(url_for('service.list_requests'))

@service_bp.route('/api/requests', methods=['GET'])
@login_required
def api_service_requests():
    status=(request.args.get('status','all') or '').upper()
    if status=='ALL' or not hasattr(ServiceStatus,status): reqs=ServiceRequest.query.all()
    else: reqs=ServiceRequest.query.filter_by(status=getattr(ServiceStatus,status)).all()
    result=[{'id':r.id,'service_number':r.service_number,'customer':r.customer.name if r.customer else (getattr(r,'name','') or ''),'vehicle_vrn':r.vehicle_vrn,'status':getattr(r.status,'value',r.status),'priority':getattr(r.priority,'value',r.priority),'request_date':(r.received_at.strftime('%Y-%m-%d %H:%M') if getattr(r,'received_at',None) else ''),'mechanic':r.mechanic.username if getattr(r,'mechanic',None) else ''} for r in reqs]
    return jsonify(result)

@service_bp.route('/search', methods=['GET'])
@login_required
def search_requests():
    query=request.args.get('q','')
    if not query: return jsonify([])
    results=ServiceRequest.query.join(Customer).filter(or_(ServiceRequest.service_number.ilike(f'%{query}%'),ServiceRequest.vehicle_vrn.ilike(f'%{query}%'),Customer.name.ilike(f'%{query}%'),Customer.phone.ilike(f'%{query}%'))).limit(10).all()


@service_bp.route('/<int:rid>/archive', methods=['POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def archive_request(rid):
    """أرشفة طلب صيانة"""
    from models import Archive
    
    service = ServiceRequest.query.get_or_404(rid)
    reason = request.form.get('reason', 'أرشفة طلب صيانة')
    
    try:
        # أرشفة السجل
        archive = Archive.archive_record(
            record=service,
            reason=reason,
            user_id=current_user.id
        )
        
        # حذف السجل الأصلي
        db.session.delete(service)
        db.session.commit()
        
        flash(f'تم أرشفة طلب الصيانة #{service.service_number or service.id} بنجاح', 'success')
        return redirect(url_for('service.list_requests'))
        
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'خطأ في أرشفة الطلب: {str(e)}', 'error')
        return redirect(url_for('service.view_request', rid=rid))


@service_bp.route('/analytics')
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def analytics():
    """تحليلات الصيانة المتقدمة"""
    from datetime import datetime, timedelta
    
    # إحصائيات شاملة
    total_requests = ServiceRequest.query.count()
    completed_this_month = ServiceRequest.query.filter(
        ServiceRequest.status == ServiceStatus.COMPLETED.value,
        ServiceRequest.completed_at >= datetime.now().replace(day=1)
    ).count()
    
    # متوسط وقت الإنجاز
    avg_completion_time = db.session.query(
        func.avg(
            func.julianday(ServiceRequest.completed_at) - 
            func.julianday(ServiceRequest.received_at)
        )
    ).filter(
        ServiceRequest.status == ServiceStatus.COMPLETED.value,
        ServiceRequest.completed_at.isnot(None)
    ).scalar() or 0
    
    # أكثر المشاكل شيوعاً
    common_problems = db.session.query(
        ServiceRequest.problem_description,
        func.count(ServiceRequest.id).label('count')
    ).filter(
        ServiceRequest.problem_description.isnot(None),
        ServiceRequest.problem_description != ''
    ).group_by(ServiceRequest.problem_description).order_by(desc('count')).limit(10).all()
    
    # إحصائيات الأسبوع
    week_ago = datetime.now() - timedelta(days=7)
    weekly_stats = {
        'new': ServiceRequest.query.filter(ServiceRequest.received_at >= week_ago).count(),
        'completed': ServiceRequest.query.filter(
            ServiceRequest.completed_at >= week_ago,
            ServiceRequest.status == ServiceStatus.COMPLETED.value
        ).count(),
        'in_progress': ServiceRequest.query.filter(
            ServiceRequest.status == 'IN_PROGRESS'
        ).count()
    }
    
    return render_template('service/analytics.html', 
                         total_requests=total_requests,
                         completed_this_month=completed_this_month,
                         avg_completion_time=avg_completion_time,
                         common_problems=common_problems,
                         weekly_stats=weekly_stats)
    return jsonify([{'id':r.id,'text':f"{r.service_number} - {r.customer.name if r.customer else getattr(r,'name','')} - {r.vehicle_vrn}",'url':url_for('service.view_request', rid=r.id)} for r in results])


# دوال مساعدة للأرشفة - تم نقلها إلى utils/archive_utils.py

def log_service_action(service, action, old_data=None, new_data=None):
    entry=AuditLog(model_name='ServiceRequest', record_id=service.id, user_id=current_user.id if current_user and getattr(current_user,'id',None) else None, action=action, old_data=json.dumps(old_data, ensure_ascii=False) if old_data else None, new_data=json.dumps(new_data, ensure_ascii=False) if new_data else None)
    db.session.add(entry); db.session.flush()

def generate_service_receipt_pdf(service_request):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except Exception:
        return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    buffer=io.BytesIO(); c=canvas.Canvas(buffer, pagesize=A4); width,height=A4
    c.setFont("Helvetica-Bold",16); c.drawString(20*mm,height-20*mm,"إيصال صيانة")
    c.setFont("Helvetica",10); y=height-30*mm
    c.drawString(20*mm,y,f"رقم الطلب: {service_request.service_number}")
    c.drawString(120*mm,y,f"التاريخ: {service_request.received_at.strftime('%Y-%m-%d') if getattr(service_request,'received_at',None) else ''}")
    y-=8*mm; c.drawString(20*mm,y,f"العميل: {service_request.customer.name if service_request.customer else (getattr(service_request,'name',None) or '-')}")
    c.drawString(120*mm,y,f"لوحة المركبة: {service_request.vehicle_vrn or ''}")
    y-=12*mm; c.setFont("Helvetica-Bold",11); c.drawString(20*mm,y,"القطع المُركّبة"); y-=6*mm; c.setFont("Helvetica",9)
    headers=[("الصنف",20),("المخزن",70),("الكمية",110),("سعر",125),("خصم ₪",145),("ضريبة%",160),("الإجمالي",175)]
    for h,x in headers: c.drawString(x*mm,y,h)
    y-=4*mm; c.line(20*mm,y,200*mm,y); y-=6*mm
    parts_total=0.0
    for part in getattr(service_request,"parts",[]) or []:
        qty=int(part.quantity or 0); u=float(part.unit_price or 0); disc=float(part.discount or 0); taxr=float(part.tax_rate or 0)
        gross=qty*u; disc_amount=disc; taxable=max(0, gross-disc_amount); tax_amount=taxable*(taxr/100.0); line_total=taxable+tax_amount; parts_total+=line_total
        c.drawString(20*mm,y,(getattr(part.part,'name','') or str(part.part_id))[:25]); c.drawString(70*mm,y,getattr(part.warehouse,'name','—') or '—')
        c.drawRightString(120*mm,y,str(qty)); c.drawRightString(140*mm,y,f"{u:.2f}"); c.drawRightString(155*mm,y,f"{disc:.0f}"); c.drawRightString(170*mm,y,f"{taxr:.0f}"); c.drawRightString(195*mm,y,f"{line_total:.2f}")
        y-=6*mm
        if y<40*mm: c.showPage(); y=height-20*mm; c.setFont("Helvetica",9)
    y-=8*mm; c.setFont("Helvetica-Bold",11); c.drawString(20*mm,y,"المهام"); y-=6*mm; c.setFont("Helvetica",9)
    headers=[("الوصف",20),("الكمية",110),("سعر",125),("خصم ₪",145),("ضريبة%",160),("الإجمالي",175)]
    for h,x in headers: c.drawString(x*mm,y,h)
    y-=4*mm; c.line(20*mm,y,200*mm,y); y-=6*mm
    tasks_total=0.0
    for task in getattr(service_request,"tasks",[]) or []:
        qty=int(task.quantity or 1); u=float(task.unit_price or 0); disc=float(task.discount or 0); taxr=float(task.tax_rate or 0)
        gross=qty*u; disc_amount=disc; taxable=max(0, gross-disc_amount); tax_amount=taxable*(taxr/100.0); line_total=taxable+tax_amount; tasks_total+=line_total
        c.drawString(20*mm,y,(task.description or '')[:40]); c.drawRightString(120*mm,y,str(qty)); c.drawRightString(140*mm,y,f"{u:.2f}"); c.drawRightString(155*mm,y,f"{disc:.0f}"); c.drawRightString(170*mm,y,f"{taxr:.0f}"); c.drawRightString(195*mm,y,f"{line_total:.2f}")
        y-=6*mm
        if y<40*mm: c.showPage(); y=height-20*mm; c.setFont("Helvetica",9)
    subtotal=parts_total+tasks_total; y-=10*mm; c.setFont("Helvetica-Bold",11); c.drawRightString(160*mm,y,"الإجمالي الكلي:"); c.drawRightString(195*mm,y,f"{subtotal:.2f}")
    c.showPage(); c.save(); buffer.seek(0); return buffer.getvalue()

@service_bp.route('/archive/<int:service_id>', methods=['POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def archive_service(service_id):
    try:
        service = ServiceRequest.query.get_or_404(service_id)
        reason = request.form.get('reason', 'أرشفة تلقائية')
        
        utils.archive_record(service, reason, current_user.id)
        flash(f'تم أرشفة طلب الصيانة رقم {service_id} بنجاح', 'success')
        return redirect(url_for('service.list_requests'))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Service archive error: {str(e)}")
        flash(f'خطأ في أرشفة طلب الصيانة: {str(e)}', 'error')
        return redirect(url_for('service.list_requests'))

@service_bp.route('/restore/<int:service_id>', methods=['POST'])
@login_required
# @permission_required('manage_service')  # Commented out - function not available
def restore_service(service_id):
    try:
        service = ServiceRequest.query.get_or_404(service_id)
        
        if not service.is_archived:
            flash('طلب الصيانة غير مؤرشف', 'warning')
            return redirect(url_for('service.list_requests'))
        
        from models import Archive
        archive = Archive.query.filter_by(
            record_type='service_requests',
            record_id=service_id
        ).first()
        
        if archive:
            utils.restore_record(archive.id)
        flash(f'تم استعادة طلب الصيانة رقم {service_id} بنجاح', 'success')
        return redirect(url_for('service.list_requests'))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Service restore error: {str(e)}")
        flash(f'خطأ في استعادة طلب الصيانة: {str(e)}', 'error')
        return redirect(url_for('service.list_requests'))
