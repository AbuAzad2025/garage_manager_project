from datetime import datetime
import csv
import io
from flask import Blueprint
from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from extensions import db
from forms import (
    ExchangeTransactionForm,
    ImportForm,
    ProductPartnerShareForm,
    ShipmentForm,
    StockLevelForm,
    TransferForm,
    WarehouseForm,
)
from models import (
    ExchangeTransaction,
    Product,
    ProductPartnerShare,
    Shipment,
    ShipmentItem,
    ShipmentPartner,
    StockLevel,
    Transfer,
    Warehouse,
)
from routes.payments import create_payment as unified_payment
from utils import permission_required

warehouses_bp = Blueprint(
    'warehouses',
    __name__,
    url_prefix='/warehouses',
    template_folder='templates/warehouses'
)
# ---------------- List & Filter Warehouses ----------------
@warehouses_bp.route('/', methods=['GET'], endpoint='list_warehouses')
@login_required
@permission_required('view_warehouses')
def list_warehouses():
    q = Warehouse.query

    type_ = request.args.get('type')
    if type_:
        q = q.filter(Warehouse.warehouse_type == type_.upper())

    parent = request.args.get('parent')
    if parent and parent.isdigit():
        q = q.filter(Warehouse.parent_id == int(parent))

    search = request.args.get('search', '').strip()
    if search:
        q = q.filter(Warehouse.name.ilike(f'%{search}%'))

    warehouses = q.order_by(Warehouse.name).all()
    return render_template(
        'warehouses/list.html',
        warehouses=warehouses,
        filter_type=type_ or '',
        parent=parent or '',
        search=search
    )

# ---------------- Create Warehouse ----------------
@warehouses_bp.route('/create', methods=['GET', 'POST'], endpoint='create_warehouse')
@login_required
@permission_required('manage_warehouses')
def create_warehouse():
    form = WarehouseForm()
    if form.validate_on_submit():
        w = Warehouse(
            name=form.name.data.strip(),
            warehouse_type=form.warehouse_type.data,
            location=form.location.data.strip() or None,
            parent_id=form.parent_id.data.id if form.parent_id.data else None,
            partner_id=form.partner_id.data.id if form.partner_id.data else None,
            share_percent=form.share_percent.data if form.warehouse_type.data == 'PARTNER' else 0,
            capacity=form.capacity.data,
            is_active=form.is_active.data
        )
        db.session.add(w)
        try:
            db.session.commit()
            flash('✅ تم إنشاء المستودع', 'success')
            return redirect(url_for('warehouses.list_warehouses'))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ: {e}', 'danger')
    return render_template('warehouses/form.html', form=form)

@warehouses_bp.route('/<int:warehouse_id>/products', methods=['GET'], endpoint='products_list')
@login_required
@permission_required('view_inventory')
def products_list(warehouse_id):
    warehouse = Warehouse.query.get_or_404(warehouse_id)
    warehouses = Warehouse.query.order_by(Warehouse.name).all()
    selected_ids = request.args.getlist('warehouse_ids', type=int)
    if not selected_ids:
        selected_ids = [warehouse_id]

    stock_levels = (
        StockLevel.query
        .filter(StockLevel.warehouse_id.in_(selected_ids))
        .options(
            joinedload(StockLevel.product),
            joinedload(StockLevel.warehouse),
        )
        .order_by(Product.name.asc())
        .all()
    )

    stock_form = StockLevelForm()
    return render_template(
        'warehouses/products.html',
        warehouse=warehouse,
        warehouses=warehouses,
        stock_levels=stock_levels,
        stock_form=stock_form,
        active_warehouse_id=warehouse_id
    )

# ---------------- Edit Warehouse ----------------
@warehouses_bp.route('/<int:warehouse_id>/edit', methods=['GET', 'POST'], endpoint='edit_warehouse')
@login_required
@permission_required('manage_warehouses')
def edit_warehouse(warehouse_id):
    w = Warehouse.query.get_or_404(warehouse_id)
    form = WarehouseForm(obj=w)
    if form.validate_on_submit():
        form.populate_obj(w)
        w.parent_id  = form.parent_id.data.id  if form.parent_id.data  else None
        w.partner_id = form.partner_id.data.id if form.partner_id.data else None
        if w.warehouse_type != 'PARTNER':
            w.share_percent = 0
        try:
            db.session.commit()
            flash('✅ تم تحديث المستودع', 'success')
            return redirect(url_for('warehouses.list_warehouses'))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ: {e}', 'danger')
    return render_template('warehouses/form.html', form=form, warehouse=w)

# ---------------- Delete Warehouse ----------------
@warehouses_bp.route('/<int:warehouse_id>/delete', methods=['POST'], endpoint='delete_warehouse')
@login_required
@permission_required('manage_warehouses')
def delete_warehouse(warehouse_id):
    w = Warehouse.query.get_or_404(warehouse_id)
    try:
        db.session.delete(w)
        db.session.commit()
        flash('✅ تم حذف المستودع', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'❌ خطأ أثناء الحذف: {e}', 'danger')
    return redirect(url_for('warehouses.list_warehouses'))

# ---------------- Warehouse Detail ----------------
@warehouses_bp.route('/<int:warehouse_id>', methods=['GET'], endpoint='warehouse_detail')
@login_required
@permission_required('view_warehouses')
def warehouse_detail(warehouse_id):
    w = Warehouse.query.get_or_404(warehouse_id)
    stock_levels  = StockLevel.query.filter_by(warehouse_id=warehouse_id).all()
    transfers_in  = Transfer.query.filter_by(destination_id=warehouse_id).all()
    transfers_out = Transfer.query.filter_by(source_id=warehouse_id).all()
    return render_template(
        'warehouses/detail.html',
        warehouse=w,
        stock_levels=stock_levels,
        transfers_in=transfers_in,
        transfers_out=transfers_out,
        stock_form=StockLevelForm(),
        transfer_form=TransferForm(),
        exchange_form=ExchangeTransactionForm(),
        share_form=ProductPartnerShareForm(),
        shipment_form=ShipmentForm()
    )

# ---------------- AJAX: Update Stock Level ----------------
@warehouses_bp.route('/<int:warehouse_id>/stock', methods=['POST'], endpoint='ajax_update_stock')
@login_required
@permission_required('manage_inventory')
def ajax_update_stock(warehouse_id):
    form = StockLevelForm()
    if form.validate_on_submit():
        pid = form.product_id.data.id
        sl = StockLevel.query.filter_by(
            warehouse_id=warehouse_id, product_id=pid
        ).first() or StockLevel(warehouse_id=warehouse_id, product_id=pid)
        sl.quantity  = form.quantity.data
        sl.min_stock = form.min_stock.data or 0
        sl.max_stock = form.max_stock.data or None
        db.session.add(sl)
        try:
            db.session.commit()
            alert = 'below_min' if sl.quantity <= sl.min_stock else None
            return jsonify({
                'success': True,
                'quantity': sl.quantity,
                'partner_share': sl.partner_share_quantity,
                'company_share': sl.company_share_quantity,
                'alert': alert
            })
        except SQLAlchemyError as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': False, 'errors': form.errors}), 400

# ---------------- AJAX: Transfer Stock ----------------
@warehouses_bp.route('/<int:warehouse_id>/transfer', methods=['POST'], endpoint='ajax_transfer')
@login_required
@permission_required('manage_inventory')
def ajax_transfer(warehouse_id):
    form = TransferForm()
    if form.validate_on_submit():
        t = Transfer(
            product_id=form.product_id.data,
            source_id=form.source_id.data,
            destination_id=form.destination_id.data,
            quantity=form.quantity.data,
            direction=form.direction.data,
            notes=form.notes.data,
            user_id=current_user.id,
            transfer_date=datetime.utcnow()
        )
        db.session.add(t)
        try:
            src = StockLevel.query.filter_by(
                warehouse_id=t.source_id, product_id=t.product_id
            ).first()
            if not src or src.quantity < t.quantity:
                raise ValueError('الكمية غير متوفرة في المصدر')
            src.quantity -= t.quantity
            dst = StockLevel.query.filter_by(
                warehouse_id=t.destination_id, product_id=t.product_id
            ).first() or StockLevel(
                warehouse_id=t.destination_id,
                product_id=t.product_id,
                quantity=0
            )
            dst.quantity += t.quantity
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': False, 'errors': form.errors}), 400

# ---------------- AJAX: Exchange Transaction ----------------
@warehouses_bp.route('/<int:warehouse_id>/exchange', methods=['POST'], endpoint='ajax_exchange')
@login_required
@permission_required('manage_inventory')
def ajax_exchange(warehouse_id):
    form = ExchangeTransactionForm()
    if form.validate_on_submit():
        ex = ExchangeTransaction(
            product_id=form.product_id.data.id,
            warehouse_id=warehouse_id,
            partner_id=form.partner_id.data.id if form.partner_id.data else None,
            quantity=form.quantity.data,
            direction=form.direction.data,
            notes=form.notes.data
        )
        db.session.add(ex)
        try:
            sl = StockLevel.query.filter_by(
                warehouse_id=warehouse_id, product_id=ex.product_id
            ).first() or StockLevel(
                warehouse_id=warehouse_id,
                product_id=ex.product_id,
                quantity=0
            )
            if ex.direction == 'IN':
                sl.quantity += ex.quantity
            else:
                if sl.quantity < ex.quantity:
                    raise ValueError('الكمية غير كافية للتعديل')
                sl.quantity -= ex.quantity
            db.session.commit()
            return jsonify({'success': True, 'new_quantity': sl.quantity})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': False, 'errors': form.errors}), 400

# ---------------- AJAX: Partner Shares ----------------
@warehouses_bp.route('/<int:warehouse_id>/partner-shares', methods=['GET', 'POST'], endpoint='ajax_partner_shares')
@login_required
@permission_required('manage_inventory')
def ajax_partner_shares(warehouse_id):
    if request.method == 'GET':
        shares = ProductPartnerShare.query.join(Product).filter(
            ProductPartnerShare.product.has(
                StockLevel.warehouse_id == warehouse_id
            )
        ).all()
        data = [{
            'id': s.id,
            'product': s.product.name,
            'partner': s.partner.name,
            'share_percentage': float(s.share_percentage),
            'share_amount': float(s.share_amount or 0),
            'notes': s.notes
        } for s in shares]
        return jsonify({'success': True, 'shares': data})

    updates = request.json.get('shares', [])
    try:
        product_ids = [
            sl.product_id for sl in StockLevel.query.filter_by(warehouse_id=warehouse_id)
        ]
        ProductPartnerShare.query.filter(
            ProductPartnerShare.product_id.in_(product_ids)
        ).delete(synchronize_session='fetch')
        for item in updates:
            db.session.add(ProductPartnerShare(
                product_id=item['product_id'],
                partner_id=item['partner_id'],
                share_percentage=item.get('share_percentage', 0),
                share_amount=item.get('share_amount', 0),
                notes=item.get('notes', '')
            ))
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# ---------------- Transfers List ----------------
@warehouses_bp.route('/<int:warehouse_id>/transfers', methods=['GET'], endpoint='list_transfers')
def list_transfers(warehouse_id):
    warehouse = Warehouse.query.get_or_404(warehouse_id)
    transfers = Transfer.query.filter(
        or_(Transfer.source_id==warehouse_id,
            Transfer.destination_id==warehouse_id)
    ).order_by(Transfer.transfer_date.desc()).all()
    return render_template(
        'warehouses/transfers_list.html',
        warehouse=warehouse,
        transfers=transfers
    )
# ---------------- Create Transfer ----------------
@warehouses_bp.route('/<int:warehouse_id>/transfers/create', methods=['GET', 'POST'], endpoint='create_transfer')
@login_required
@permission_required('manage_inventory')
def create_transfer(warehouse_id):
    warehouse = Warehouse.query.get_or_404(warehouse_id)
    form = TransferForm()
    if form.validate_on_submit():
        t = Transfer(
            transfer_date=form.date.data or datetime.utcnow(),
            product_id=form.product_id.data,
            source_id=form.source_id.data,
            destination_id=form.destination_id.data,
            quantity=form.quantity.data,
            direction=form.direction.data,
            notes=form.notes.data,
            user_id=current_user.id
        )
        db.session.add(t)
        try:
            # تحديث المخزون
            src = StockLevel.query.filter_by(
                warehouse_id=t.source_id, product_id=t.product_id
            ).first()
            if not src or src.quantity < t.quantity:
                raise ValueError('الكمية غير متوفرة في المصدر')
            src.quantity -= t.quantity

            dst = StockLevel.query.filter_by(
                warehouse_id=t.destination_id, product_id=t.product_id
            ).first() or StockLevel(
                warehouse_id=t.destination_id,
                product_id=t.product_id,
                quantity=0
            )
            dst.quantity += t.quantity

            db.session.commit()
            flash('✅ تم إضافة التحويل بنجاح', 'success')
            return redirect(url_for('warehouses.list_transfers', warehouse_id=warehouse_id))
        except Exception as e:
            db.session.rollback()
            flash(f'❌ خطأ أثناء إضافة التحويل: {e}', 'danger')
    return render_template('warehouses/transfers_form.html',
                           warehouse=warehouse, form=form)

# ---------------- Import Products ----------------
@warehouses_bp.route('/<int:warehouse_id>/import', methods=['GET', 'POST'], endpoint='import_products')
@login_required
@permission_required('manage_inventory')
def import_products(warehouse_id):
    w = Warehouse.query.get_or_404(warehouse_id)
    form = ImportForm()
    if form.validate_on_submit():
        f = form.file.data
        stream = io.StringIO(f.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)
        for row in reader:
            p = Product(
                name=row.get('name'),
                sku=row.get('sku'),
                warehouse_id=w.id
            )
            db.session.add(p)
        db.session.commit()
        return redirect(url_for('warehouses.warehouse_detail', warehouse_id=w.id))
    return render_template(
        'warehouses/import_products.html',
        form=form,
        warehouse=w
    )

# ---------------- Warehouse Shipments List ----------------
@warehouses_bp.route('/<int:warehouse_id>/shipments', methods=['GET'], endpoint='list_warehouse_shipments')
@login_required
@permission_required('view_inventory')
def list_warehouse_shipments(warehouse_id):
    warehouse = Warehouse.query.get_or_404(warehouse_id)
    shipments = Shipment.query.filter_by(destination_id=warehouse.id).all()
    return render_template(
        'shipments/list.html',
        warehouse=warehouse,
        shipments=shipments,
        form=ShipmentForm()
    )

@warehouses_bp.route('/<int:warehouse_id>/shipments/create', methods=['GET', 'POST'], endpoint='create_warehouse_shipment')
@login_required
@permission_required('manage_inventory')
def create_warehouse_shipment(warehouse_id):
    w = Warehouse.query.get_or_404(warehouse_id)
    form = ShipmentForm()
    if form.validate_on_submit():
        sh = Shipment(
            shipment_number    = form.shipment_number.data,
            shipment_date      = form.shipment_date.data or datetime.utcnow(),
            expected_arrival   = form.expected_arrival.data,
            actual_arrival     = form.actual_arrival.data,
            origin             = form.origin.data,
            destination_id     = form.destination_id.data,
            carrier            = form.carrier.data,
            tracking_number    = form.tracking_number.data,
            status             = form.status.data,
            value_before       = form.value_before.data,
            shipping_cost      = form.shipping_cost.data,
            customs            = form.customs.data,
            vat                = form.vat.data,
            insurance          = form.insurance.data,
            total_value        = form.total_value.data,
            notes              = form.notes.data,
            currency           = form.currency.data
        )
        db.session.add(sh)
        try:
            # إضافة العناصر وتحديث المخزون
            for itm in form.items.data:
                si = ShipmentItem(
                    shipment        = sh,
                    product_id      = itm['product_id'].id,
                    warehouse_id    = w.id,
                    quantity        = itm['quantity'],
                    unit_cost       = itm['unit_cost'],
                    declared_value  = itm.get('declared_value') or 0,
                    notes           = itm.get('notes', '')
                )
                db.session.add(si)
                sl = StockLevel.query.filter_by(
                    warehouse_id=w.id, product_id=si.product_id
                ).first() or StockLevel(
                    warehouse_id=w.id, product_id=si.product_id, quantity=0
                )
                sl.quantity += si.quantity

            # إضافة مساهمات الشركاء إن وجدت
            for pl in form.partner_links.data:
                db.session.add(ShipmentPartner(
                    shipment            = sh,
                    partner_id          = pl['partner_id'].id,
                    identity_number     = pl.get('identity_number'),
                    phone_number        = pl.get('phone_number'),
                    address             = pl.get('address'),
                    unit_price_before_tax = pl.get('unit_price_before_tax') or 0,
                    expiry_date         = pl.get('expiry_date'),
                    share_percentage    = pl.get('share_percentage') or 0,
                    share_amount        = pl.get('share_amount') or 0,
                    notes               = pl.get('notes', '')
                ))

            db.session.commit()
            flash('✅ تم إنشاء الشحنة وتحديث المخزون', 'success')
            return redirect(url_for('warehouses.list_warehouse_shipments', warehouse_id=w.id))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'❌ خطأ أثناء إنشاء الشحنة: {e}', 'danger')

    return render_template(
        'shipments/_form.html',
        action='create',
        form=form,
        warehouse=w
    )# ---------------- Unified Payment for Warehouse ----------------
@warehouses_bp.route('/<int:warehouse_id>/pay', methods=['POST'], endpoint='pay_warehouse')
@login_required
@permission_required('manage_payments')
def pay_warehouse(warehouse_id):
    amount = request.form.get('amount')
    result = unified_payment(
        entity_type='warehouse',
        entity_id=warehouse_id,
        amount=amount,
        user_id=current_user.id
    )
    if result.get('success'):
        flash('✅ تم تسجيل الدفع', 'success')
    else:
        flash(f"❌ خطأ في الدفع: {result.get('error', 'Unknown')}", 'danger')
    return redirect(url_for('warehouses.warehouse_detail', warehouse_id=warehouse_id))
