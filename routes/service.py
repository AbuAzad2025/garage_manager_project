# File: routes/service.py

import io
import json
from datetime import datetime, timedelta
from forms import ServiceRequestForm, CustomerForm
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, abort, Response, send_file
)
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, or_, and_, desc
from dateutil.relativedelta import relativedelta

# استيراد الإكستنشنز
from extensions import db

# استيراد النماذج
from models import (
    ServiceRequest, ServicePart, ServiceTask,
    Customer, Product, Warehouse, Payment,
    AuditLog, User, EquipmentType,
    StockLevel, Invoice, InvoiceLine, Partner
)

# استيراد الفورمات
from forms import (
    ServiceRequestForm,
    ServiceTaskForm,
    ServiceDiagnosisForm,
    PaymentForm,
    BaseServicePartForm,
    ServicePartForm
)

# استيراد أدوات WTForms
from wtforms_sqlalchemy.fields import QuerySelectField
from wtforms import DecimalField, SubmitField
from wtforms.validators import Optional, NumberRange

# استيراد الدوال المساعدة من utils
from utils import (
    permission_required,
    generate_pdf_report as generate_service_receipt_pdf,
    send_whatsapp_message
)

service_bp = Blueprint(
    'service',
    __name__,
    url_prefix='/service'
)

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

# ✅ تعديل ServicePartForm لإضافة حقول الشريك
class ServicePartForm(BaseServicePartForm):
    partner_id = QuerySelectField(
        'الشريك',
        query_factory=lambda: Partner.query.order_by(Partner.name).all(),
        get_label='name',
        allow_blank=True
    )
    share_percentage = DecimalField(
        'نسبة الشريك (%)',
        places=2,
        validators=[Optional(), NumberRange(min=0, max=100)]
    )
    submit = SubmitField('حفظ القطعة')
    
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

    query = ServiceRequest.query
    if status_filter:
        query = query.filter(ServiceRequest.status.in_(status_filter))
    if priority_filter:
        query = query.filter(ServiceRequest.priority.in_(priority_filter))
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

    # إحصائيات جانبية
    stats = {
        'pending':      ServiceRequest.query.filter_by(status='PENDING').count(),
        'in_progress':  ServiceRequest.query.filter_by(status='IN_PROGRESS').count(),
        'completed':    ServiceRequest.query.filter_by(status='COMPLETED').count(),
        'high_priority': ServiceRequest.query.filter_by(priority='HIGH').count()
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
    total_requests         = ServiceRequest.query.count()
    completed_this_month   = ServiceRequest.query.filter(
        ServiceRequest.status == 'COMPLETED',
        ServiceRequest.end_time >= datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ).count()
    high_priority          = ServiceRequest.query.filter_by(priority='HIGH')\
                                .order_by(ServiceRequest.request_date.desc()).limit(5).all()
    active_mechanics       = db.session.query(
                                User.username,
                                func.count(ServiceRequest.id).label('request_count')
                            ).join(ServiceRequest).group_by(User.id)\
                             .order_by(desc('request_count')).limit(5).all()
    overdue                = ServiceRequest.query.filter(
                                ServiceRequest.status.in_(['DIAGNOSIS','IN_PROGRESS']),
                                ServiceRequest.expected_end_date < datetime.now()
                            ).all()
    status_distribution    = db.session.query(
                                ServiceRequest.status,
                                func.count(ServiceRequest.id).label('count')
                            ).group_by(ServiceRequest.status).all()
    priority_distribution  = db.session.query(
                                ServiceRequest.priority,
                                func.count(ServiceRequest.id).label('count')
                            ).group_by(ServiceRequest.priority).all()

    return render_template(
        'dashboard.html',
        total_requests=total_requests,
        completed_this_month=completed_this_month,
        high_priority=high_priority,
        active_mechanics=active_mechanics,
        overdue=overdue,
        status_distribution=status_distribution,
        priority_distribution=priority_distribution
    )


# ------------------ إنشاء طلب صيانة ------------------
@service_bp.route('/new', methods=['GET', 'POST'])
@login_required
@permission_required('manage_service')
def create_request():
    """Create a new ServiceRequest along with an optional Customer in one form.

    * Renders `templates/service/new.html`.
    * Passes **two** separate WTForms instances to the template:
        - `service_form`  → ServiceRequestForm (fields for service itself)
        - `customer_form` → CustomerForm       (fields in the modal)
    * Handles creation of a Customer if not already selected, then creates
      the ServiceRequest record.
    """

    # ----- build forms -----
    service_form  = ServiceRequestForm()
    customer_form = CustomerForm(prefix="customer")

    # Populate vehicle-type choices for the service form
    service_form.vehicle_type_id.query = (
        EquipmentType.query.order_by(EquipmentType.name).all()
    )

    # --------------- handle POST ---------------
    if service_form.validate_on_submit():
        # if user picked an existing customer from Select2
        if service_form.customer_id.data:
            customer = Customer.query.get(service_form.customer_id.data)
        else:
            # create or fetch customer by the inline fields
            customer = (
                Customer.query.filter_by(
                    name=service_form.name.data,
                    phone=service_form.phone.data,
                ).first()
            )
            if not customer:
                customer = Customer(
                    name=service_form.name.data,
                    phone=service_form.phone.data,
                    email=service_form.email.data,
                )
                db.session.add(customer)
                db.session.flush()  # get ID for FK

        # create the service request
        service = ServiceRequest(
            service_number=f"SRV-{datetime.utcnow():%Y%m%d%H%M%S}",
            customer_id=customer.id,
            name=service_form.name.data,
            phone=service_form.phone.data,
            email=service_form.email.data,
            vehicle_vrn=service_form.vehicle_vrn.data,
            vehicle_type_id=(
                service_form.vehicle_type_id.data.id
                if service_form.vehicle_type_id.data
                else None
            ),
            vehicle_model=service_form.vehicle_model.data,
            chassis_number=service_form.chassis_number.data,
            problem_description=service_form.problem_description.data,
            engineer_notes=service_form.engineer_notes.data,
            description=service_form.description.data,
            priority=service_form.priority.data,
            estimated_duration=service_form.estimated_duration.data,
            estimated_cost=service_form.estimated_cost.data,
            tax_rate=service_form.tax_rate.data or 0,
            status=service_form.status.data,
            expected_end_date=(
                datetime.now() + timedelta(minutes=service_form.estimated_duration.data)
                if service_form.estimated_duration.data
                else None
            ),
        )
        db.session.add(service)
        try:
            db.session.commit()
            log_service_action(service, "CREATE")
            if customer.phone:
                send_whatsapp_message(
                    customer.phone,
                    f"تم استلام طلب الصيانة رقم {service.service_number}.",
                )
            flash("✅ تم إنشاء طلب الصيانة بنجاح", "success")
            return redirect(url_for("service.view_request", rid=service.id))
        except SQLAlchemyError as exc:
            db.session.rollback()
            flash(f"❌ خطأ في قاعدة البيانات: {exc}", "danger")

    # GET or failed POST → render template
    return render_template(
        "service/new.html",
        form=service_form,
        customer_form=customer_form,
    )
def view_request(rid):
    service = ServiceRequest.query.get_or_404(rid)
    return render_template('service/view.html', service=service)


# ------------------ صفحة الإيصال (عرض) ------------------
@service_bp.route('/<int:rid>/receipt', methods=['GET'], endpoint='view_receipt')
@login_required
def view_receipt(rid):
    service = ServiceRequest.query.get_or_404(rid)
    return render_template('service/receipt.html', service=service)

# ------------------ تحميل الإيصال PDF ------------------
@service_bp.route('/<int:rid>/receipt/download', methods=['GET'], endpoint='download_receipt')
@login_required
@permission_required('manage_service')
def download_receipt(rid):
    service = ServiceRequest.query.get_or_404(rid)
    pdf_data= generate_service_receipt_pdf(service)
    return send_file(
        io.BytesIO(pdf_data),
        as_attachment=True,
        download_name=f"service_receipt_{service.service_number}.pdf",
        mimetype='application/pdf'
    )

@service_bp.route('/<int:rid>/diagnosis', methods=['POST'])
@login_required
@permission_required('manage_service')
def update_diagnosis(rid):
    service = ServiceRequest.query.get_or_404(rid)
    form    = ServiceDiagnosisForm()
    if form.validate_on_submit():
        service.problem            = form.problem.data
        service.cause              = form.cause.data
        service.solution           = form.solution.data
        service.estimated_duration = form.estimated_duration.data
        service.estimated_cost     = form.estimated_cost.data
        service.status             = 'IN_PROGRESS'
        if form.estimated_duration.data:
            service.expected_end_date = datetime.now() + timedelta(minutes=form.estimated_duration.data)
        try:
            db.session.commit()
            flash('✅ تم تحديث التشخيص بنجاح', 'success')
            if service.customer.phone:
                send_whatsapp_message(
                    service.customer.phone,
                    f"تم تشخيص المركبة {service.vehicle_vrn}."
                )
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ في قاعدة البيانات: {str(e)}', 'danger')
    return redirect(url_for('service.view_request', rid=rid))

# ------------------ بدء/إنهاء الصيانة ------------------
@service_bp.route('/<int:rid>/<action>', methods=['POST'])
@login_required
@permission_required('manage_service')
def toggle_service(rid, action):
    service = ServiceRequest.query.get_or_404(rid)
    if action == 'start':
        service.start_time = datetime.now()
        service.status     = 'IN_PROGRESS'
        flash('✅ تم بدء عملية الصيانة', 'success')
    elif action == 'complete':
        service.end_time   = datetime.now()
        service.status     = 'COMPLETED'
        if service.start_time:
            service.actual_duration = int(
                (service.end_time - service.start_time).total_seconds() / 60
            )
        flash('✅ تم إكمال عملية الصيانة بنجاح', 'success')
    try:
        db.session.commit()
        if action == 'complete' and service.customer.phone:
            send_whatsapp_message(
                service.customer.phone,
                f"تم إكمال صيانة المركبة {service.vehicle_vrn}."
            )
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ في قاعدة البيانات: {str(e)}', 'danger')
    return redirect(url_for('service.view_request', rid=rid))

# ------------------ إضافة قطعة غيار مع دعم الشريك ------------------
@service_bp.route('/<int:rid>/parts/add', methods=['POST'])
@login_required
@permission_required('manage_service')
def add_part(rid):
    service  = ServiceRequest.query.get_or_404(rid)
    form     = ServicePartForm()
    if form.validate_on_submit():
        warehouse = Warehouse.query.get(form.warehouse_id.data)
        product   = Product.query.get(form.part_id.data)
        stock     = StockLevel.query.filter_by(
                        product_id=product.id,
                        warehouse_id=warehouse.id
                    ).first()
        if not stock or stock.quantity < form.quantity.data:
            flash(f'❌ الكمية غير متوفرة. المتاح: {stock.quantity if stock else 0}', 'danger')
            return redirect(url_for('service.view_request', rid=rid))

        stock.quantity     -= form.quantity.data
        product.on_hand    -= form.quantity.data
        part = ServicePart(
            service_id       = rid,
            part_id          = product.id,
            warehouse_id     = warehouse.id,
            quantity         = form.quantity.data,
            unit_price       = form.unit_price.data,
            discount         = form.discount.data or 0,
            tax_rate         = form.tax_rate.data or 0,
            partner_id       = form.partner_id.data.id if form.partner_id.data else None,
            share_percent    = form.share_percentage.data or 0
        )
        db.session.add(part)
        try:
            db.session.commit()
            flash('✅ تمت إضافة القطعة مع توثيق حصة الشريك وخصمها من المخزن', 'success')
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ: {str(e)}', 'danger')
    return redirect(url_for('service.view_request', rid=rid))


# ------------------ حذف قطعة غيار ------------------
@service_bp.route('/parts/<int:pid>/delete', methods=['POST'])
@login_required
@permission_required('manage_service')
def delete_part(pid):
    part      = ServicePart.query.get_or_404(pid)
    rid       = part.service_id
    warehouse = Warehouse.query.get(part.warehouse_id)
    product   = Product.query.get(part.part_id)

    # ارجاع الكمية
    if warehouse and product:
        stock = StockLevel.query.filter_by(
                    product_id=product.id,
                    warehouse_id=warehouse.id
                ).first()
        if stock:
            stock.quantity += part.quantity
            product.on_hand += part.quantity
        else:
            db.session.add(StockLevel(
                product_id=product.id,
                warehouse_id=warehouse.id,
                quantity=part.quantity
            ))

    db.session.delete(part)
    try:
        db.session.commit()
        flash('✅ تم حذف القطعة وإرجاعها للمخزن', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}', 'danger')
    return redirect(url_for('service.view_request', rid=rid))


# ------------------ إضافة مهمة ------------------
@service_bp.route('/<int:rid>/tasks/add', methods=['POST'])
@login_required
@permission_required('manage_service')
def add_task(rid):
    form = ServiceTaskForm()
    if form.validate_on_submit():
        task = ServiceTask(
            service_id  = rid,
            description = form.description.data,
            quantity    = form.quantity.data or 1,
            unit_price  = form.unit_price.data,
            discount    = form.discount.data or 0,
            tax_rate    = form.tax_rate.data or 0,
            note        = form.note.data
        )
        db.session.add(task)
        try:
            db.session.commit()
            flash('✅ تمت إضافة المهمة', 'success')
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ: {str(e)}', 'danger')
    return redirect(url_for('service.view_request', rid=rid))


# ------------------ حذف مهمة ------------------
@service_bp.route('/tasks/<int:tid>/delete', methods=['POST'])
@login_required
@permission_required('manage_service')
def delete_task(tid):
    task = ServiceTask.query.get_or_404(tid)
    rid  = task.service_id
    db.session.delete(task)
    try:
        db.session.commit()
        flash('✅ تم حذف المهمة', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}', 'danger')
    return redirect(url_for('service.view_request', rid=rid))


# ------------------ إضافة دفعة (دفع موحد) ------------------
@service_bp.route('/<int:rid>/payments/add', methods=['GET', 'POST'])
@login_required
@permission_required('manage_service')
def add_payment(rid):
    return redirect(url_for(
        'payments.create_payment',
        entity_type='service',
        entity_id=rid
    ))


# ------------------ إنشاء فاتورة الصيانة ------------------
@service_bp.route('/<int:rid>/invoice', methods=['POST'])
@login_required
@permission_required('manage_service')
def create_invoice(rid):
    service     = ServiceRequest.query.get_or_404(rid)
    parts_total = sum(part.line_total for part in service.parts)
    tasks_total = sum(task.line_total for task in service.tasks)
    total_amount= parts_total + tasks_total

    invoice = Invoice(
        invoice_number  = f"INV-SRV-{datetime.utcnow():%Y%m%d%H%M%S}",
        invoice_date    = datetime.utcnow(),
        due_date        = datetime.utcnow() + timedelta(days=15),
        customer_id     = service.customer_id,
        service_id      = service.id,
        source          = 'SERVICE',
        status          = 'UNPAID',
        total_amount    = total_amount,
        tax_amount      = 0,
        discount_amount = 0
    )
    db.session.add(invoice)

    # بنود الفاتورة من القطع
    for part in service.parts:
        db.session.add(InvoiceLine(
            invoice     = invoice,
            description = f"{part.part.name} - قطعة غيار",
            quantity    = part.quantity,
            unit_price  = part.unit_price,
            discount    = part.discount,
            tax_rate    = part.tax_rate,
            product_id  = part.part_id
        ))
    # بنود الفاتورة من المهام
    for task in service.tasks:
        db.session.add(InvoiceLine(
            invoice     = invoice,
            description = task.description,
            quantity    = task.quantity,
            unit_price  = task.unit_price,
            discount    = task.discount,
            tax_rate    = task.tax_rate
        ))

    try:
        db.session.commit()
        flash('✅ تم إنشاء الفاتورة', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}', 'danger')

    return redirect(url_for('service.view_request', rid=rid))


# ------------------ تقرير الصيانة PDF (عرض inline) ------------------
@service_bp.route('/<int:rid>/report')
@login_required
def service_report(rid):
    service = ServiceRequest.query.get_or_404(rid)
    pdf     = generate_service_receipt_pdf(service)
    return Response(
        pdf,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'inline; filename=service_report_{service.service_number}.pdf'}
    )


# ------------------ تصدير PDF ------------------
@service_bp.route('/<int:rid>/pdf')
@login_required
def export_pdf(rid):
    service = ServiceRequest.query.get_or_404(rid)
    pdf     = generate_service_receipt_pdf(service)
    return Response(
        pdf,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename=service_{service.service_number}.pdf'}
    )


# ------------------ حذف الطلب بالكامل ------------------
@service_bp.route('/<int:rid>/delete', methods=['POST'])
@login_required
@permission_required('manage_service')
def delete_request(rid):
    service = ServiceRequest.query.get_or_404(rid)
    db.session.delete(service)
    try:
        db.session.commit()
        flash('✅ تم حذف الطلب بنجاح', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ فشل حذف الطلب: {e}', 'danger')
    return redirect(url_for('service.list_requests'))


# ------------------ واجهة API لطلبات الصيانة ------------------
@service_bp.route('/api/requests', methods=['GET'])
@login_required
def api_service_requests():
    status   = request.args.get('status', 'all')
    if status == 'all':
        reqs = ServiceRequest.query.all()
    else:
        reqs = ServiceRequest.query.filter_by(status=status).all()
    result = [{
        'id':               r.id,
        'service_number':  r.service_number,
        'customer':        r.customer.name,
        'vehicle_vrn':     r.vehicle_vrn,
        'status':          STATUS_LABELS.get(r.status, r.status),
        'priority':        r.priority,
        'request_date':    r.request_date.strftime('%Y-%m-%d %H:%M'),
        'expected_end_date': r.expected_end_date.strftime('%Y-%m-%d %H:%M') if r.expected_end_date else '',
        'mechanic':         r.mechanic.username if r.mechanic else ''
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
        'text': f"{r.service_number} - {r.customer.name} - {r.vehicle_vrn}",
        'url':  url_for('service.view_request', rid=r.id)
    } for r in results])


# ------------------ إحصائيات الصيانة ------------------
@service_bp.route('/stats')
@login_required
def service_stats():
    total_requests     = ServiceRequest.query.count()
    completed_requests = ServiceRequest.query.filter_by(status='COMPLETED').count()
    pending_requests   = ServiceRequest.query.filter_by(status='PENDING').count()
    avg_duration       = db.session.query(func.avg(ServiceRequest.actual_duration))\
                           .filter(ServiceRequest.actual_duration.isnot(None))\
                           .scalar() or 0

    monthly_costs = db.session.query(
        func.date_trunc('month', ServiceRequest.end_time).label('month'),
        func.sum(ServicePart.unit_price * ServicePart.quantity).label('parts_total'),
        func.sum(ServiceTask.unit_price * ServiceTask.quantity).label('labor_total')
    ).join(ServicePart, isouter=True).join(ServiceTask, isouter=True)\
     .filter(
        ServiceRequest.status == 'COMPLETED',
        ServiceRequest.end_time >= datetime.now() - relativedelta(months=6)
    ).group_by('month').all()

    months, parts_costs, labor_costs = [], [], []
    for month, parts, labor in monthly_costs:
        months.append(month.strftime('%b %Y'))
        parts_costs.append(float(parts or 0))
        labor_costs.append(float(labor or 0))

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
        user_id    = current_user.id,
        action     = action,
        old_data   = json.dumps(old_data, ensure_ascii=False) if old_data else None,
        new_data   = json.dumps(new_data, ensure_ascii=False) if new_data else None
    )
    db.session.add(entry)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()


def generate_service_receipt_pdf(service_request):
    """
    يولّد إيصال صيانة PDF يضم:
      - رقم وتاريخ الطلب
      - بيانات العميل
      - قائمة القطع والمهام مع الشريك ونسبة الشريك وصافي السطر
      - إجمالي قبل وبعد خصم الشريك
      - الضريبة والإجمالي النهائي
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(20*mm, height - 20*mm, "إيصال صيانة")

    # بيانات الطلب
    c.setFont("Helvetica", 10)
    y = height - 30*mm
    c.drawString(20*mm, y, f"رقم الطلب: {service_request.service_number}")
    c.drawString(120*mm, y, f"التاريخ: {service_request.request_date.strftime('%Y-%m-%d')}")
    y -= 8*mm
    c.drawString(20*mm, y, f"العميل: {service_request.customer.name}")
    c.drawString(120*mm, y, f"لوحة المركبة: {service_request.vehicle_vrn}")

    # جدول القطع
    y -= 12*mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20*mm, y, "القطع المُركّبة")
    y -= 6*mm
    c.setFont("Helvetica", 9)
    c.drawString(20*mm, y, "الصنف")
    c.drawString(60*mm, y, "الشريك")
    c.drawString(95*mm, y, "نسبة")
    c.drawString(110*mm, y, "الكمية")
    c.drawString(125*mm, y, "سعر")
    c.drawString(145*mm, y, "الإجمالي")
    c.drawString(170*mm, y, "الصافي")
    y -= 4*mm
    c.line(20*mm, y, 190*mm, y)
    y -= 6*mm

    net_subtotal = 0
    parts_total = 0

    for part in service_request.parts:
        line_total = part.line_total
        partner_share = float(part.share_percentage or 0)
        net_line = line_total * (1 - partner_share / 100)
        parts_total += line_total
        net_subtotal += net_line

        c.drawString(20*mm, y, part.part.name[:20])
        c.drawString(60*mm, y, part.partner.name if part.partner else "—")
        c.drawRightString(105*mm, y, f"{partner_share:.0f}%")
        c.drawRightString(120*mm, y, str(part.quantity))
        c.drawRightString(140*mm, y, f"{float(part.unit_price):.2f}")
        c.drawRightString(165*mm, y, f"{line_total:.2f}")
        c.drawRightString(190*mm, y, f"{net_line:.2f}")
        y -= 6*mm
        if y < 40*mm:
            c.showPage()
            y = height - 20*mm

    # جدول المهام
    y -= 8*mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20*mm, y, "المهام")
    y -= 6*mm
    c.setFont("Helvetica", 9)
    c.drawString(20*mm, y, "الوصف")
    c.drawString(95*mm, y, "الكمية")
    c.drawString(125*mm, y, "سعر")
    c.drawString(145*mm, y, "الإجمالي")
    c.drawString(170*mm, y, "الصافي")
    y -= 4*mm
    c.line(20*mm, y, 190*mm, y)
    y -= 6*mm

    tasks_total = 0
    for task in service_request.tasks:
        line_total = task.line_total
        tasks_total += line_total
        net_subtotal += line_total

        c.drawString(20*mm, y, task.description[:25])
        c.drawRightString(115*mm, y, str(task.quantity))
        c.drawRightString(140*mm, y, f"{float(task.unit_price):.2f}")
        c.drawRightString(165*mm, y, f"{line_total:.2f}")
        c.drawRightString(190*mm, y, f"{line_total:.2f}")
        y -= 6*mm
        if y < 40*mm:
            c.showPage()
            y = height - 20*mm

    # الملخص
    subtotal = parts_total + tasks_total
    tax = net_subtotal * (service_request.tax_rate or 0) / 100
    total = net_subtotal + tax

    y -= 10*mm
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(160*mm, y, "الإجمالي قبل خصم الشريك:")
    c.drawRightString(190*mm, y, f"{subtotal:.2f}")
    y -= 6*mm
    c.drawRightString(160*mm, y, "الصافي بعد خصم الشريك:")
    c.drawRightString(190*mm, y, f"{net_subtotal:.2f}")
    y -= 6*mm
    c.drawRightString(160*mm, y, f"الضريبة ({service_request.tax_rate or 0}%):")
    c.drawRightString(190*mm, y, f"{tax:.2f}")
    y -= 6*mm
    c.drawRightString(160*mm, y, "الإجمالي النهائي:")
    c.drawRightString(190*mm, y, f"{total:.2f}")

    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer.getvalue()

