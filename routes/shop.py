# routes/shop.py
from datetime import datetime
import uuid, json
from functools import wraps
from types import SimpleNamespace
from flask import Blueprint, flash, redirect, render_template, request, url_for, jsonify, abort, g, current_app
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from flask_wtf import FlaskForm
from extensions import db
from forms import AddToOnlineCartForm, OnlineCartPaymentForm
from models import Customer, OnlineCart, OnlineCartItem, OnlinePreOrder, OnlinePreOrderItem, OnlinePayment, Product, StockLevel, Warehouse, WarehouseType, Payment, PaymentStatus, PaymentDirection, PaymentEntityType
from utils import customer_required, send_whatsapp_message

shop_bp = Blueprint('shop', __name__, url_prefix='/shop', template_folder='templates/shop')

def _get_or_404(model, ident, options=None):
    q = db.session.query(model)
    if options:
        for opt in options: q = q.options(opt)
        obj = q.filter_by(id=ident).first()
    else:
        obj = db.session.get(model, ident)
    if obj is None: abort(404)
    return obj

def _resp(msg, cat='info', code=302, data=None, to='shop.catalog'):
    if request.is_json or request.args.get('format')=='json':
        p={'message':msg,'status':cat}
        if data: p.update(data)
        return jsonify(p),code
    flash(msg,cat); return redirect(url_for(to))

def _json_loads(s):
    try: return json.loads(s) if isinstance(s,str) and s.strip() else {}
    except Exception: return {}

def _warehouse_types():
    raw=current_app.config.get('SHOP_WAREHOUSE_TYPES',['MAIN','INVENTORY'])
    vals=[]
    for t in raw:
        try: vals.append(getattr(WarehouseType,t).value)
        except Exception: vals.append(t)
    return vals

def available_qty(product_id:int)->int:
    q=db.session.query(func.coalesce(func.sum(StockLevel.quantity),0)).select_from(StockLevel)\
        .join(Warehouse,StockLevel.warehouse_id==Warehouse.id)\
        .filter(StockLevel.product_id==product_id,Warehouse.is_active.is_(True))
    ids=current_app.config.get('SHOP_WAREHOUSE_IDS')
    if ids: q=q.filter(Warehouse.id.in_(ids))
    else:
        tvals=_warehouse_types()
        if tvals: q=q.filter(Warehouse.warehouse_type.in_(tvals))
    on_hand=q.scalar() or 0
    reserved=db.session.query(func.coalesce(func.sum(OnlinePreOrderItem.quantity),0)).select_from(OnlinePreOrderItem)\
        .join(OnlinePreOrder,OnlinePreOrderItem.order_id==OnlinePreOrder.id)\
        .filter(OnlinePreOrderItem.product_id==product_id,OnlinePreOrder.status.in_(('PENDING','CONFIRMED'))).scalar() or 0
    return max(0,int(on_hand)-int(reserved))

def _is_super_admin(u)->bool:
    try: return (getattr(getattr(u,'role',None),'name','') or '').lower()=='super_admin'
    except Exception: return False

def online_customer_required(f):
    @wraps(f)
    @login_required
    def inner(*a,**kw):
        if _is_super_admin(current_user):
            g.online_customer=SimpleNamespace(id=current_user.id,phone=getattr(current_user,'phone',None),address=getattr(current_user,'address',None),currency=getattr(current_user,'currency','ILS'),is_online=True,name=getattr(current_user,'username','Super Admin'))
            return f(*a,**kw)
        cust=Customer.query.filter_by(id=current_user.id,is_online=True).first()
        if not cust: return _resp('لم يتم العثور على حساب العميل الإلكتروني.','danger')
        g.online_customer=cust
        return f(*a,**kw)
    return inner

def get_active_cart(customer_id):
    return OnlineCart.query.filter_by(customer_id=customer_id,status='ACTIVE').first()

@shop_bp.route('/', endpoint='catalog')
def catalog():
    q=db.session.query(Product)\
        .join(StockLevel,StockLevel.product_id==Product.id)\
        .join(Warehouse,StockLevel.warehouse_id==Warehouse.id)\
        .filter(Product.is_active.is_(True),Warehouse.is_active.is_(True))
    ids=current_app.config.get('SHOP_WAREHOUSE_IDS')
    if ids: q=q.filter(Warehouse.id.in_(ids))
    else:
        tvals=_warehouse_types()
        if tvals: q=q.filter(Warehouse.warehouse_type.in_(tvals))
    products=q.group_by(Product.id).having(func.coalesce(func.sum(StockLevel.quantity),0)>0).order_by(Product.name).all()
    if request.is_json or request.args.get('format')=='json':
        return jsonify([{'id':p.id,'name':p.name,'price':float(p.price or 0),'stock':available_qty(p.id)} for p in products])
    return render_template('shop/catalog.html',products=products,form=FlaskForm(),avail_map={p.id:available_qty(p.id) for p in products})

@shop_bp.route('/order', methods=['POST'], endpoint='place_order')
@online_customer_required
def place_order():
    cart=get_active_cart(g.online_customer.id)
    if not cart or not cart.items: return _resp('سلتك فارغة.','warning')
    return redirect(url_for('shop.checkout'))

@shop_bp.route('/cart/add/<int:product_id>', methods=['POST'], endpoint='add_to_cart')
@online_customer_required
def add_to_cart(product_id):
    product=_get_or_404(Product,product_id)
    form=AddToOnlineCartForm()
    if not form.validate_on_submit(): return _resp('بيانات غير صحيحة.','danger')
    qty=int(form.quantity.data or 0)
    if qty<=0: return _resp('كمية غير صالحة.','danger')
    if qty>available_qty(product.id): return _resp('الكمية المطلوبة غير متوفرة!','danger')
    cart=get_active_cart(g.online_customer.id) or OnlineCart(customer_id=g.online_customer.id,session_id=uuid.uuid4().hex,status='ACTIVE')
    db.session.add(cart); db.session.flush()
    item=OnlineCartItem.query.filter_by(cart_id=cart.id,product_id=product.id).first()
    if item:
        if (item.quantity+qty)>available_qty(product.id): return _resp('الكمية المطلوبة تتجاوز المتوفر!','danger')
        item.quantity+=qty
    else:
        db.session.add(OnlineCartItem(cart_id=cart.id,product_id=product.id,quantity=qty,price=product.price or 0))
    try:
        db.session.commit(); return _resp('تمت إضافة المنتج إلى السلة.','success',code=200)
    except SQLAlchemyError as e:
        db.session.rollback(); return _resp(f'خطأ أثناء الإضافة: {e}','danger')

@shop_bp.route('/cart', endpoint='cart')
@online_customer_required
def cart():
    cart=get_active_cart(g.online_customer.id)
    items=cart.items if cart else []
    subtotal=sum(i.quantity*float(i.price or 0) for i in items)
    rate=float(current_app.config.get('SHOP_PREPAID_RATE',0.2))
    prepaid=round(subtotal*rate,2)
    return render_template('shop/cart.html',cart=cart,items=items,subtotal=subtotal,prepaid_amount=prepaid,form=FlaskForm())

@shop_bp.route('/cart/update/<int:item_id>', methods=['POST'], endpoint='update_cart_item')
@online_customer_required
def update_cart_item(item_id):
    item=_get_or_404(OnlineCartItem,item_id)
    if item.cart.customer_id!=g.online_customer.id: return _resp('غير مصرح.','danger',to='shop.cart')
    new_qty=request.form.get('quantity',type=int)
    if not new_qty or new_qty<=0: return _resp('كمية غير صالحة.','danger',to='shop.cart')
    if new_qty>available_qty(item.product_id)+item.quantity: return _resp('الكمية المطلوبة غير متوفرة!','danger',to='shop.cart')
    item.quantity=new_qty
    try:
        db.session.commit(); return _resp('تم تحديث الكمية.','success',code=200,to='shop.cart')
    except SQLAlchemyError as e:
        db.session.rollback(); return _resp(f'خطأ أثناء التحديث: {e}','danger',to='shop.cart')

@shop_bp.route('/cart/remove/<int:item_id>', methods=['POST'], endpoint='remove_from_cart')
@online_customer_required
def remove_from_cart(item_id):
    item=_get_or_404(OnlineCartItem,item_id)
    if item.cart.customer_id!=g.online_customer.id: return _resp('غير مصرح.','danger',to='shop.cart')
    db.session.delete(item)
    try:
        db.session.commit(); return _resp('تم حذف العنصر.','info',code=200,to='shop.cart')
    except SQLAlchemyError as e:
        db.session.rollback(); return _resp(f'خطأ أثناء الحذف: {e}','danger',to='shop.cart')

@shop_bp.route('/checkout', methods=['GET','POST'], endpoint='checkout')
@online_customer_required
def checkout():
    cart=get_active_cart(g.online_customer.id)
    if not cart or not cart.items: return _resp('سلتك فارغة.','warning',to='shop.catalog')
    subtotal=sum(i.quantity*float(i.price or 0) for i in cart.items)
    rate=float(current_app.config.get('SHOP_PREPAID_RATE',0.2))
    prepaid=round(subtotal*rate,2)
    form=OnlineCartPaymentForm()
    if form.validate_on_submit():
        try:
            with db.session.begin():
                payment_status='PAID' if prepaid>=subtotal else ('PARTIAL' if prepaid>0 else 'PENDING')
                preorder=OnlinePreOrder(customer_id=g.online_customer.id,cart_id=cart.id,order_number=f"PO-{uuid.uuid4().hex[:8].upper()}",prepaid_amount=prepaid,total_amount=subtotal,status='CONFIRMED',payment_status=payment_status,payment_method=form.payment_method.data,shipping_address=form.shipping_address.data or getattr(g.online_customer,'address',None),billing_address=form.billing_address.data or getattr(g.online_customer,'address',None))
                db.session.add(preorder); db.session.flush()
                for itm in cart.items:
                    db.session.add(OnlinePreOrderItem(order_id=preorder.id,product_id=itm.product_id,quantity=itm.quantity,price=itm.price))
                op=OnlinePayment(payment_ref=f"PAY-{uuid.uuid4().hex[:8].upper()}",order_id=preorder.id,amount=prepaid,currency=getattr(g.online_customer,'currency','ILS'),method=form.payment_method.data,gateway="ONLINE",status='SUCCESS',transaction_data=_json_loads(form.transaction_data.data))
                db.session.add(op)
                if prepaid>0:
                    db.session.add(Payment(entity_type=PaymentEntityType.PREORDER.value,preorder_id=preorder.id,direction=PaymentDirection.INCOMING.value,status=PaymentStatus.COMPLETED.value,method=(form.payment_method.data or 'online'),total_amount=prepaid,currency=getattr(g.online_customer,'currency','ILS'),payment_date=datetime.utcnow(),reference=f"Online Preorder {preorder.order_number}",notes="Online prepaid via checkout"))
                cart.status='CONVERTED'
            try:
                if getattr(g.online_customer,'phone',None):
                    send_whatsapp_message(g.online_customer.phone,f"✅ تم تأكيد طلبك {preorder.order_number} بقيمة عربون {prepaid} {getattr(g.online_customer,'currency','ILS')}")
            except Exception:
                pass
            if request.is_json or request.args.get('format')=='json':
                return _resp('تم إتمام الطلب والدفع بنجاح!','success',code=200,to='shop.preorder_receipt',data={'preorder_id':preorder.id})
            return redirect(url_for('shop.preorder_receipt',preorder_id=preorder.id))
        except SQLAlchemyError as e:
            db.session.rollback(); return _resp(f'خطأ أثناء الدفع: {e}','danger')
    return render_template('shop/pay_online.html',form=form,cart=cart,subtotal=subtotal,prepaid_amount=prepaid)

@shop_bp.route('/preorders', endpoint='preorder_list')
@online_customer_required
def preorder_list():
    preorders=OnlinePreOrder.query.filter_by(customer_id=g.online_customer.id).order_by(OnlinePreOrder.created_at.desc()).all()
    return render_template('shop/preorder_list.html',preorders=preorders)

@shop_bp.route('/preorder/<int:preorder_id>/receipt', endpoint='preorder_receipt')
@online_customer_required
def preorder_receipt(preorder_id):
    preorder=_get_or_404(OnlinePreOrder,preorder_id)
    if preorder.customer_id!=g.online_customer.id: abort(403)
    return render_template('shop/preorder_receipt.html',preorder=preorder)

@shop_bp.route('/preorder/<int:preorder_id>/cancel', methods=['POST'], endpoint='cancel_preorder')
@online_customer_required
def cancel_preorder(preorder_id):
    po=_get_or_404(OnlinePreOrder,preorder_id)
    if po.customer_id!=g.online_customer.id: return _resp('غير مصرح.','danger',to='shop.preorder_list')
    if po.status not in ('PENDING','CONFIRMED'): return _resp('لا يمكن إلغاء هذا الطلب.','warning',to='shop.preorder_list')
    try:
        with db.session.begin():
            po.status='CANCELLED'
        return _resp('تم إلغاء الطلب.','success',code=200,to='shop.preorder_list')
    except SQLAlchemyError as e:
        db.session.rollback(); return _resp(f'خطأ أثناء الإلغاء: {e}','danger',to='shop.preorder_list')

@shop_bp.context_processor
def inject_cart_count():
    if current_user.is_authenticated and getattr(current_user,'is_online',False):
        cart=get_active_cart(current_user.id)
        return {'cart_count': sum(i.quantity for i in cart.items) if cart else 0}
    return {'cart_count': 0}
