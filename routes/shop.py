# routes/shop.py

from datetime import datetime
import uuid
import json
from functools import wraps

from flask import (
    Blueprint, flash, redirect, render_template,
    request, url_for, jsonify, abort, g
)
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from forms import AddToOnlineCartForm, OnlineCartPaymentForm
from models import (
    Customer, OnlineCart, OnlineCartItem,
    OnlinePreOrder, OnlinePreOrderItem,
    Product, OnlinePayment
)
from utils import customer_required, send_whatsapp_message

shop_bp = Blueprint(
    'shop',
    __name__,
    url_prefix='/shop',
    template_folder='templates/shop'
)

# === Helper: Unified response/flash
def shop_response(message, category='info', code=302, json_data=None, redirect_to='shop.catalog'):
    if request.is_json or request.args.get('format') == 'json':
        resp = {'message': message, 'status': category}
        if json_data: resp.update(json_data)
        return jsonify(resp), code
    flash(message, category)
    return redirect(url_for(redirect_to))

# === Decorator: Online customer required (adds to g)
def online_customer_required(f):
    @wraps(f)
    @login_required
    @customer_required
    def decorated_function(*args, **kwargs):
        customer = Customer.query.filter_by(id=current_user.id, is_online=True).first()
        if not customer:
            return shop_response('لم يتم العثور على حساب العميل الإلكتروني.', 'danger')
        g.online_customer = customer
        return f(*args, **kwargs)
    return decorated_function

# === Common: get cart (ACTIVE)
def get_active_cart(customer_id):
    return OnlineCart.query.filter_by(customer_id=customer_id, status='ACTIVE').first()

# === Common: check product quantity
def available_quantity(product):
    return product.on_hand - product.reserved_quantity

# -------------------- عرض الكاتالوج --------------------
@shop_bp.route('/', endpoint='catalog')
def catalog():
    products = Product.query.filter(
        Product.is_active.is_(True),
        Product.on_hand > 0
    ).order_by(Product.name).all()
    if request.args.get('format') == 'json' or request.is_json:
        return jsonify([{
            'id':    p.id,
            'name':  p.name,
            'price': float(p.price),
            'stock': p.on_hand
        } for p in products])
    return render_template('shop/catalog.html', products=products)

# -------------------- إنشاء طلب من السلة --------------------
@shop_bp.route('/order', methods=['POST'], endpoint='place_order')
@online_customer_required
def place_order():
    customer = g.online_customer
    cart = get_active_cart(customer.id)
    if not cart or not cart.items:
        return shop_response('سلتك فارغة.', 'warning')
    return redirect(url_for('shop.checkout'))

# -------------------- إضافة منتج للسلة --------------------
@shop_bp.route('/cart/add/<int:product_id>', methods=['POST'], endpoint='add_to_cart')
@online_customer_required
def add_to_cart(product_id):
    customer = g.online_customer
    product = Product.query.get_or_404(product_id)
    form = AddToOnlineCartForm()
    if not form.validate_on_submit():
        return shop_response('بيانات غير صحيحة.', 'danger')
    qty = form.quantity.data
    # تحقق الكمية المتوفرة
    if qty > available_quantity(product):
        return shop_response('الكمية المطلوبة غير متوفرة!', 'danger')
    cart = get_active_cart(customer.id) or OnlineCart(
        customer_id=customer.id,
        session_id=uuid.uuid4().hex,
        status='ACTIVE'
    )
    db.session.add(cart)
    db.session.flush()
    item = OnlineCartItem.query.filter_by(
        cart_id=cart.id, product_id=product.id
    ).first()
    if item:
        if item.quantity + qty > available_quantity(product):
            return shop_response('الكمية المطلوبة تتجاوز المتوفر!', 'danger')
        item.quantity += qty
    else:
        db.session.add(OnlineCartItem(
            cart_id=cart.id,
            product_id=product.id,
            quantity=qty,
            price=product.price
        ))
    try:
        db.session.commit()
        return shop_response('تمت إضافة المنتج إلى السلة بنجاح.', 'success', code=200)
    except SQLAlchemyError as e:
        db.session.rollback()
        return shop_response(f'خطأ أثناء الإضافة: {e}', 'danger')

# -------------------- عرض السلة --------------------
@shop_bp.route('/cart', endpoint='cart')
@online_customer_required
def cart():
    customer = g.online_customer
    cart = get_active_cart(customer.id)
    items = cart.items if cart else []
    subtotal = sum(i.quantity * float(i.price) for i in items)
    prepaid = round(subtotal * 0.2, 2)
    return render_template(
        'shop/cart.html',
        cart=cart,
        items=items,
        subtotal=subtotal,
        prepaid_amount=prepaid
    )

# -------------------- تحديث كمية منتج --------------------
@shop_bp.route('/cart/update/<int:item_id>', methods=['POST'], endpoint='update_cart_item')
@online_customer_required
def update_cart_item(item_id):
    item = OnlineCartItem.query.get_or_404(item_id)
    customer = g.online_customer
    if item.cart.customer_id != customer.id:
        return shop_response('غير مصرح لك بهذا الإجراء.', 'danger', redirect_to='shop.cart')
    new_qty = request.form.get('quantity', type=int)
    if not new_qty or new_qty <= 0:
        return shop_response('كمية غير صالحة.', 'danger', redirect_to='shop.cart')
    # تحقق الكمية
    product = Product.query.get(item.product_id)
    if new_qty > available_quantity(product) + item.quantity:
        return shop_response('الكمية المطلوبة غير متوفرة!', 'danger', redirect_to='shop.cart')
    item.quantity = new_qty
    try:
        db.session.commit()
        return shop_response('تم تحديث الكمية بنجاح.', 'success', code=200, redirect_to='shop.cart')
    except SQLAlchemyError as e:
        db.session.rollback()
        return shop_response(f'خطأ أثناء التحديث: {e}', 'danger', redirect_to='shop.cart')

# -------------------- حذف منتج من السلة --------------------
@shop_bp.route('/cart/remove/<int:item_id>', methods=['POST'], endpoint='remove_from_cart')
@online_customer_required
def remove_from_cart(item_id):
    item = OnlineCartItem.query.get_or_404(item_id)
    customer = g.online_customer
    if item.cart.customer_id != customer.id:
        return shop_response('غير مصرح لك بهذا الإجراء.', 'danger', redirect_to='shop.cart')
    db.session.delete(item)
    try:
        db.session.commit()
        return shop_response('تم حذف العنصر من السلة.', 'info', code=200, redirect_to='shop.cart')
    except SQLAlchemyError as e:
        db.session.rollback()
        return shop_response(f'خطأ أثناء الحذف: {e}', 'danger', redirect_to='shop.cart')

# -------------------- الدفع وإتمام الطلب --------------------
@shop_bp.route('/checkout', methods=['GET', 'POST'], endpoint='checkout')
@online_customer_required
def checkout():
    customer = g.online_customer
    cart = get_active_cart(customer.id)
    if not cart or not cart.items:
        return shop_response('سلتك فارغة.', 'warning', redirect_to='shop.catalog')
    subtotal = sum(i.quantity * float(i.price) for i in cart.items)
    prepaid = round(subtotal * 0.2, 2)
    form = OnlineCartPaymentForm()
    if form.validate_on_submit():
        try:
            with db.session.begin():
                payment_status = 'PAID' if prepaid >= subtotal else 'PARTIAL'
                preorder = OnlinePreOrder(
                    customer_id=customer.id,
                    cart_id=cart.id,
                    order_number=f"PO-{uuid.uuid4().hex[:8].upper()}",
                    prepaid_amount=prepaid,
                    total_amount=subtotal,
                    status='CONFIRMED',
                    payment_status=payment_status,
                    payment_method=form.payment_method.data,
                    shipping_address=form.shipping_address.data or customer.address,
                    billing_address=form.billing_address.data or customer.address,
                    created_at=datetime.utcnow()
                )
                db.session.add(preorder)
                db.session.flush()
                for itm in cart.items:
                    product = Product.query.get(itm.product_id)
                    product.reserved_quantity += itm.quantity
                    db.session.add(OnlinePreOrderItem(
                        order_id=preorder.id,
                        product_id=itm.product_id,
                        quantity=itm.quantity,
                        price=itm.price
                    ))
                payment = OnlinePayment(
                    payment_ref=f"PAY-{uuid.uuid4().hex[:8].upper()}",
                    order_id=preorder.id,
                    amount=prepaid,
                    currency='ILS',
                    method=form.payment_method.data,
                    gateway="ONLINE",
                    status='SUCCESS',
                    transaction_data=form.transaction_data.data or "{}"
                )
                db.session.add(payment)
                cart.status = 'CONVERTED'
            # إشعار خارجي
            if customer.phone:
                try:
                    send_whatsapp_message(customer.phone, f"✅ تم تأكيد طلبك {preorder.order_number} بقيمة {prepaid} ₪")
                except Exception:
                    pass
            return shop_response('تم إتمام الطلب والدفع بنجاح!', 'success', code=200,
                                 redirect_to='shop.preorder_receipt', json_data={'preorder_id': preorder.id})
        except SQLAlchemyError as e:
            db.session.rollback()
            return shop_response(f'خطأ أثناء الدفع: {e}', 'danger')
    return render_template(
        'shop/pay_online.html',
        form=form,
        cart=cart,
        subtotal=subtotal,
        prepaid_amount=prepaid
    )

# -------------------- قائمة الطلبات --------------------
@shop_bp.route('/preorders', endpoint='preorder_list')
@online_customer_required
def preorder_list():
    customer = g.online_customer
    preorders = OnlinePreOrder.query.filter_by(
        customer_id=customer.id
    ).order_by(OnlinePreOrder.created_at.desc()).all()
    return render_template('shop/preorder_list.html', preorders=preorders)

# -------------------- إيصال الطلب --------------------
@shop_bp.route('/preorder/<int:preorder_id>/receipt', endpoint='preorder_receipt')
@online_customer_required
def preorder_receipt(preorder_id):
    preorder = OnlinePreOrder.query.get_or_404(preorder_id)
    customer = g.online_customer
    if preorder.customer_id != customer.id:
        abort(403)
    return render_template('shop/preorder_receipt.html', preorder=preorder)

# ✅ إضافة عدد عناصر السلة للـ context في جميع القوالب
@shop_bp.context_processor
def inject_cart_count():
    if current_user.is_authenticated and hasattr(current_user, 'is_online') and current_user.is_online:
        cart = get_active_cart(current_user.id)
        cart_count = sum(item.quantity for item in cart.items) if cart else 0
        return {'cart_count': cart_count}
    return {'cart_count': 0}

