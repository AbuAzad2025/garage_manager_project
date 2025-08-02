# File: routes/parts.py

from datetime import datetime
import uuid

from flask import (
    Blueprint, flash, jsonify, redirect,
    render_template, request, url_for, abort
)
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from forms import PreOrderForm
from models import (
    Customer, Supplier, Partner, Product,
    Warehouse, PreOrder, StockLevel, Payment,
    ShipmentItem, Shipment, ExchangeTransaction, Transfer
)
from utils import permission_required

parts_bp = Blueprint(
    'parts',
    __name__,
    url_prefix='/parts',
    template_folder='templates/parts'
)


@parts_bp.route('/<int:product_id>', methods=['GET'], endpoint='card')
@login_required
@permission_required('view_parts')
def card(product_id):
    """
    بطاقة المنتج: رصيد المخازن + التحويلات + التبادلات + الشحنات.
    قالب: templates/parts/card.html
    """
    part = Product.query.options(
        db.joinedload(Product.international_supplier),
        db.joinedload(Product.local_supplier),
        db.joinedload(Product.vehicle_type),
        db.joinedload(Product.category),
    ).get_or_404(product_id)

    # كل المخازن
    warehouses = Warehouse.query.order_by(Warehouse.name).all()

    # الرصيد حسب مخزن
    stock = []
    for w in warehouses:
        lvl = StockLevel.query.filter_by(
            product_id=part.id,
            warehouse_id=w.id
        ).first()
        qty = lvl.quantity if lvl else 0
        res = lvl.reserved_quantity if lvl else 0
        stock.append({
            'warehouse': w,
            'on_hand': qty,
            'reserved': res,
            'virtual_available': qty - res
        })

    # التحويلات
    transfers = Transfer.query.filter_by(product_id=part.id) \
        .options(
            db.joinedload(Transfer.source_warehouse),
            db.joinedload(Transfer.destination_warehouse)
        ) \
        .order_by(Transfer.transfer_date.desc()) \
        .all()

    # التبادلات
    exchanges = ExchangeTransaction.query.filter_by(product_id=part.id) \
        .options(db.joinedload(ExchangeTransaction.trader)) \
        .order_by(ExchangeTransaction.timestamp.desc()) \
        .all()

    # الشحنات
    shipments = ShipmentItem.query.filter_by(product_id=part.id) \
        .options(
            db.joinedload(ShipmentItem.shipment),
            db.joinedload(ShipmentItem.warehouse)
        ) \
        .join(Shipment) \
        .order_by(Shipment.arrival_date.desc()) \
        .all()

    return render_template(
        'parts/card.html',
        part=part,
        stock=stock,
        transfers=transfers,
        exchanges=exchanges,
        shipments=shipments
    )


@parts_bp.route('/preorders', methods=['GET'], endpoint='preorders_list')
@login_required
@permission_required('view_preorders')
def preorders_list():
    """
    قائمة الحجوزات المسبقة مع فلترة على:
      - status
      - code (reservation_code)
      - تاريخ الإنشاء date_from/date_to
    يدعم pagination و JSON لواجهات AJAX.
    قالب: templates/parts/preorders_list.html + _preorders_table.html
    """
    q = PreOrder.query

    # فلترة الحالة
    if status := request.args.get('status'):
        q = q.filter(PreOrder.status == status)

    # فلترة الكود
    if code := request.args.get('code'):
        q = q.filter(PreOrder.reservation_code.ilike(f"%{code}%"))

    # فلترة التواريخ
    df = request.args.get('date_from')
    dt = request.args.get('date_to')
    try:
        if df:
            q = q.filter(PreOrder.created_at >= datetime.fromisoformat(df))
        if dt:
            q = q.filter(PreOrder.created_at <= datetime.fromisoformat(dt))
    except ValueError:
        pass  # تجاهل التواريخ غير الصالحة

    # فرز تنازلي
    q = q.order_by(PreOrder.created_at.desc())

    # تقسيم صفحات
    page     = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    preorders   = pagination.items

    # دعم JSON لـ AJAX/DataTables
    if request.args.get('format') == 'json' or request.is_json:
        data = [{
            'id':             p.id,
            'code':           p.reservation_code,
            'entity_type':    p.entity_type,
            'entity_name':    getattr(p, p.entity_type.lower()).name if p.entity_type else None,
            'product':        p.product.name,
            'warehouse':      p.warehouse.name,
            'quantity':       p.quantity,
            'prepaid_amount': float(p.prepaid_amount),
            'status':         p.status,
            'created_at':     p.created_at.isoformat()
        } for p in preorders]
        return jsonify({
            'data': data,
            'meta': {
                'page':      pagination.page,
                'per_page':  pagination.per_page,
                'total':     pagination.total,
                'pages':     pagination.pages
            }
        })

    return render_template(
        'parts/preorders_list.html',
        preorders=preorders,
        pagination=pagination,
        filters={'status': status, 'code': code, 'date_from': df, 'date_to': dt}
    )

@parts_bp.route('/preorders/create', methods=['GET', 'POST'], endpoint='preorder_create')
@login_required
@permission_required('add_preorder')
def preorder_create():
    """
    إنشاء حجز مسبق:
      - توليد كود عشوائي
      - تحديث reserved_quantity في المنتج
      - إنشاء دفعة عربون Payment
    قالب: templates/parts/preorder_form.html
    """
    form = PreOrderForm()
    # تهيئة قوائم الاختيار
    form.customer_id.query  = Customer.query.order_by(Customer.name).all()
    form.supplier_id.query  = Supplier.query.order_by(Supplier.name).all()
    form.partner_id.query   = Partner.query.order_by(Partner.name).all()
    form.product_id.query   = Product.query.order_by(Product.name).all()
    form.warehouse_id.query = Warehouse.query.order_by(Warehouse.name).all()

    if form.validate_on_submit():
        code = uuid.uuid4().hex[:8].upper()
        et = form.entity_type.data

        preorder = PreOrder(
            customer_id      = form.customer_id.data.id   if et == 'CUSTOMER' else None,
            supplier_id      = form.supplier_id.data.id   if et == 'SUPPLIER' else None,
            partner_id       = form.partner_id.data.id    if et == 'PARTNER' else None,
            product_id       = form.product_id.data.id,
            warehouse_id     = form.warehouse_id.data.id,
            prepaid_amount   = form.prepaid_amount.data,
            quantity         = form.quantity.data,
            tax_rate         = form.tax_rate.data or 0,
            reservation_code = code,
            status           = 'PENDING',
            notes            = form.notes.data
        )
        db.session.add(preorder)
        db.session.flush()  # للحصول على ID

        # تحديث الرصيد المحجوز في المنتج
        prod = Product.query.get(preorder.product_id)
        prod.reserved_quantity = (prod.reserved_quantity or 0) + preorder.quantity

        # إنشاء دفعة عربون مرتبطة
        payment = Payment(
            amount       = preorder.prepaid_amount,
            currency     = 'ILS',
            method       = form.payment_method.data,
            payment_date = datetime.utcnow(),
            reference    = f"Preorder {code}",
            notes        = f"دفعة عربون لحجز {prod.name} (كود: {code})",
            preorder_id  = preorder.id,
            customer_id  = preorder.customer_id,
            supplier_id  = preorder.supplier_id,
            partner_id   = preorder.partner_id
        )
        db.session.add(payment)

        try:
            db.session.commit()
            flash('تم إنشاء الحجز المسبق وتسجيل دفعة العربون.', 'success')
            return redirect(url_for('parts.preorder_detail', preorder_id=preorder.id))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'فشل إنشاء الحجز: {e}', 'danger')

    return render_template('parts/preorder_form.html', form=form)


@parts_bp.route('/preorders/<int:preorder_id>', methods=['GET'], endpoint='preorder_detail')
@login_required
@permission_required('view_preorders')
def preorder_detail(preorder_id):
    """
    عرض تفاصيل الحجز المسبق وقائمة الدفعات المرتبطة.
    قالب: templates/parts/preorder_detail.html
    """
    preorder = PreOrder.query.options(
        db.joinedload(PreOrder.customer),
        db.joinedload(PreOrder.supplier),
        db.joinedload(PreOrder.partner),
        db.joinedload(PreOrder.product),
        db.joinedload(PreOrder.warehouse),
        db.joinedload(PreOrder.payments)
    ).get_or_404(preorder_id)

    return render_template('parts/preorder_detail.html', preorder=preorder)


@parts_bp.route('/preorders/<int:preorder_id>/fulfill', methods=['POST'], endpoint='preorder_fulfill')
@login_required
@permission_required('edit_preorder')
def preorder_fulfill(preorder_id):
    """
    تنفيذ الحجز:
      - تخفيض reserved_quantity
      - إضافة الكمية الفعلية إلى المخزن StockLevel
    """
    preorder = PreOrder.query.get_or_404(preorder_id)
    if preorder.status != 'FULFILLED':
        try:
            preorder.status       = 'FULFILLED'
            preorder.fulfilled_at = datetime.utcnow()

            prod = Product.query.get(preorder.product_id)
            prod.reserved_quantity = max((prod.reserved_quantity or 0) - preorder.quantity, 0)

            lvl = StockLevel.query.filter_by(
                product_id   = preorder.product_id,
                warehouse_id = preorder.warehouse_id
            ).first()
            if lvl:
                lvl.quantity += preorder.quantity
            else:
                lvl = StockLevel(
                    product_id   = preorder.product_id,
                    warehouse_id = preorder.warehouse_id,
                    quantity     = preorder.quantity
                )
                db.session.add(lvl)

            db.session.commit()
            flash('تم تنفيذ الحجز.', 'success')
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'فشل تنفيذ الحجز: {e}', 'danger')
    else:
        flash('هذا الحجز قد تم تنفيذه سابقاً.', 'info')

    return redirect(url_for('parts.preorder_detail', preorder_id=preorder_id))


@parts_bp.route('/preorders/<int:preorder_id>/cancel', methods=['POST'], endpoint='preorder_cancel')
@login_required
@permission_required('delete_preorder')
def preorder_cancel(preorder_id):
    """
    إلغاء الحجز:
      - استرجاع reserved_quantity
      - وسم دفعات العربون كـ REFUNDED
    """
    preorder = PreOrder.query.get_or_404(preorder_id)
    if preorder.status not in ('CANCELLED', 'FULFILLED'):
        try:
            prod = Product.query.get(preorder.product_id)
            prod.reserved_quantity = max((prod.reserved_quantity or 0) - preorder.quantity, 0)

            for pay in preorder.payments:
                pay.status = 'REFUNDED'
                pay.notes = f"استرداد عربون الحجز {preorder.reservation_code}"

            preorder.status       = 'CANCELLED'
            preorder.cancelled_at = datetime.utcnow()

            db.session.commit()
            flash('تم إلغاء الحجز واسترداد العربون.', 'success')
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'فشل إلغاء الحجز: {e}', 'danger')
    else:
        flash('لا يمكن إلغاء هذا الحجز.', 'warning')

    return redirect(url_for('parts.preorders_list'))


# ——————————————————————————————————————————————————————————————
# واجهات JSON صغيرة (لـ Select2 أو forms ديناميكي)
# ——————————————————————————————————————————————————————————————

@parts_bp.route('/api/add_customer', methods=['POST'], endpoint='api_add_customer')
@login_required
@permission_required('add_customer')
def api_add_customer():
    data = request.get_json() or {}
    if not (name := data.get('name')):
        return jsonify({'error': 'اسم العميل مطلوب'}), 400

    cust = Customer(
        name      = name,
        phone     = data.get('phone'),
        email     = data.get('email'),
        address   = data.get('address'),
        whatsapp  = data.get('whatsapp'),
        category  = data.get('category', 'عادي'),
        is_active = True
    )
    db.session.add(cust)
    try:
        db.session.commit()
        return jsonify({'id': cust.id, 'name': cust.name}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@parts_bp.route('/api/add_supplier', methods=['POST'], endpoint='api_add_supplier')
@login_required
@permission_required('add_supplier')
def api_add_supplier():
    data = request.get_json() or {}
    if not (name := data.get('name')):
        return jsonify({'error': 'اسم المورد مطلوب'}), 400

    sup = Supplier(
        name            = name,
        is_local        = data.get('is_local', True),
        identity_number = data.get('identity_number'),
        contact         = data.get('contact'),
        phone           = data.get('phone'),
        address         = data.get('address'),
        notes           = data.get('notes'),
        balance         = 0
    )
    db.session.add(sup)
    try:
        db.session.commit()
        return jsonify({'id': sup.id, 'name': sup.name}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@parts_bp.route('/api/add_partner', methods=['POST'], endpoint='api_add_partner')
@login_required
@permission_required('add_partner')
def api_add_partner():
    data = request.get_json() or {}
    if not (name := data.get('name')):
        return jsonify({'error': 'اسم الشريك مطلوب'}), 400

    p = Partner(
        name              = name,
        contact_info      = data.get('contact_info'),
        identity_number   = data.get('identity_number'),
        phone_number      = data.get('phone_number'),
        address           = data.get('address'),
        balance           = 0,
        share_percentage  = data.get('share_percentage', 0)
    )
    db.session.add(p)
    try:
        db.session.commit()
        return jsonify({'id': p.id, 'name': p.name}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ---------------------- Part Tracking ----------------------
@parts_bp.route('/<int:part_id>/tracking', methods=['GET'])
def part_tracking(part_id):
    part = Product.query.get_or_404(part_id)
    
    # سجل الحركات
    movements = db.session.query(
        Transfer,
        Warehouse.name.label('from_warehouse'),
        Warehouse.name.label('to_warehouse')
    ).join(Warehouse, Transfer.source_id == Warehouse.id
    ).join(Warehouse, Transfer.destination_id == Warehouse.id
    ).filter(Transfer.product_id == part_id).all()
    
    # حالة التوريد
    suppliers = db.session.query(
        Supplier,
        func.sum(Transfer.quantity).label('total_received')
    ).join(Transfer, Transfer.supplier_id == Supplier.id
    ).filter(Transfer.product_id == part_id).group_by(Supplier.id).all()
    
    return render_template('parts/tracking.html', 
                          part=part, 
                          movements=movements,
                          suppliers=suppliers)

# ---------------------- Availability Check ----------------------
@parts_bp.route('/availability', methods=['GET'])
def parts_availability():
    # فحص توفر القطع عبر المخازن
    q = db.session.query(
        Product.id,
        Product.name,
        Warehouse.name.label('warehouse'),
        StockLevel.quantity,
        StockLevel.min_stock
    ).join(StockLevel, StockLevel.product_id == Product.id
    ).join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
    
    # فلاتر
    if warehouse_id := request.args.get('warehouse_id'):
        q = q.filter(StockLevel.warehouse_id == warehouse_id)
    if min_qty := request.args.get('min_qty'):
        q = q.filter(StockLevel.quantity <= min_qty)
    
    results = q.all()
    return render_template('parts/availability.html', results=results)

# ---------------------- Low Stock Alerts ----------------------
@parts_bp.route('/alerts', methods=['GET'])
def low_stock_alerts():
    # قطع تحت الحد الأدنى
    alerts = db.session.query(
        Product.name,
        Warehouse.name.label('warehouse'),
        StockLevel.quantity,
        StockLevel.min_stock
    ).join(StockLevel, StockLevel.product_id == Product.id
    ).join(Warehouse, Warehouse.id == StockLevel.warehouse_id
    ).filter(StockLevel.quantity <= StockLevel.min_stock).all()
    
    return render_template('parts/alerts.html', alerts=alerts)
