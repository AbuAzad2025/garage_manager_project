from flask import Blueprint, request
from extensions import db
from models import Product, StockLevel

parts_bp = Blueprint('parts_bp', __name__, url_prefix='/parts')

@parts_bp.route('/create', methods=['POST'])
def parts_create():
    name = request.form.get('name')
    if not name:
        return "هذا الحقل مطلوب"
    selling_price = request.form.get('selling_price')
    product = Product(
        name=name,
        sku=request.form.get('sku'),
        barcode=request.form.get('barcode'),
        unit=request.form.get('unit'),
        category=request.form.get('category'),
        purchase_price=request.form.get('purchase_price'),
        selling_price=selling_price,
        price=selling_price,
        notes=request.form.get('notes'),
    )
    db.session.add(product)
    db.session.flush()
    return "تم إضافة القطعة بنجاح"

@parts_bp.route('/<int:id>/edit', methods=['POST'])
def parts_edit(id):
    product = Product.query.get_or_404(id)
    name = request.form.get('name')
    if not name:
        return "هذا الحقل مطلوب"
    product.name = name
    product.sku = request.form.get('sku', product.sku)
    product.unit = request.form.get('unit', product.unit)
    product.category_name = request.form.get('category', product.category_name)
    product.purchase_price = request.form.get('purchase_price', product.purchase_price)
    selling_price = request.form.get('selling_price')
    if selling_price is not None:
        product.selling_price = selling_price
        product.price = selling_price
    product.notes = request.form.get('notes', product.notes)
    db.session.flush()
    return "تم تحديث القطعة بنجاح"

@parts_bp.route('/', methods=['GET'])
def parts_list():
    return "القطع"

@parts_bp.route('/<int:id>/stock')
def stock_levels(id):
    product = Product.query.get_or_404(id)
    levels = StockLevel.query.filter_by(product_id=product.id).all()
    body = []
    for level in levels:
        if level.warehouse:
            body.append(f"{level.warehouse.name}: {int(level.quantity)}")
    return "\n".join(body)

@parts_bp.route('/<int:id>/delete', methods=['POST'])
def parts_delete(id):
    product = Product.query.get_or_404(id)
    StockLevel.query.filter_by(product_id=product.id).delete()
    db.session.delete(product)
    db.session.flush()
    return "تم حذف القطعة بنجاح"
