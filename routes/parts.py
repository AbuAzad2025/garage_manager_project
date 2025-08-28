from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_
from extensions import db
from models import Product, StockLevel
from utils import permission_required
from barcodes import normalize_barcode, is_valid_ean13

parts_bp = Blueprint('parts_bp', __name__, url_prefix='/parts')

def _to_decimal(val, default=0):
    try:
        return Decimal(str(val)) if val not in (None, "") else Decimal(default)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)

def _wants_json() -> bool:
    accept = (request.headers.get("Accept") or "").lower()
    fmt = (request.args.get("format") or "").lower()
    return ("application/json" in accept and "text/html" not in accept) or fmt == "json"

@parts_bp.get("/", endpoint="parts_list")
@login_required
@permission_required("view_parts")
def parts_list():
    q = (request.args.get("q") or "").strip()
    qry = Product.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Product.name.ilike(like), Product.sku.ilike(like), Product.barcode.ilike(like)))
    items = qry.order_by(Product.id.desc()).limit(100).all()
    data = [{"id": p.id, "name": p.name, "sku": p.sku, "barcode": p.barcode, "unit": p.unit, "category_name": p.category_name, "price": float(p.price or 0), "selling_price": float(p.selling_price or 0), "purchase_price": float(p.purchase_price or 0)} for p in items]
    return jsonify({"ok": True, "count": len(data), "results": data})

@parts_bp.post("/create")
@login_required
@permission_required("manage_inventory")
def parts_create():
    name = (request.form.get("name") or "").strip()
    if not name:
        if _wants_json():
            return jsonify({"ok": False, "error": "name_required"}), 400
        flash("الاسم مطلوب", "warning")
        return redirect(url_for("parts_bp.parts_list"))
    raw_barcode = (request.form.get("barcode") or "").strip() or None
    barcode = normalize_barcode(raw_barcode) if raw_barcode else None
    if barcode and not is_valid_ean13(barcode):
        if _wants_json():
            return jsonify({"ok": False, "error": "invalid_barcode"}), 400
        flash("الباركود غير صالح", "danger")
        return redirect(url_for("parts_bp.parts_list"))
    if barcode and db.session.query(Product.id).filter_by(barcode=barcode).first():
        if _wants_json():
            return jsonify({"ok": False, "error": "barcode_exists"}), 409
        flash("الباركود مستخدم بالفعل", "danger")
        return redirect(url_for("parts_bp.parts_list"))
    product = Product(
        name=name,
        sku=(request.form.get("sku") or "").strip() or None,
        barcode=barcode,
        unit=(request.form.get("unit") or "").strip() or None,
        category_name=(request.form.get("category_name") or request.form.get("category") or "").strip() or None,
        purchase_price=_to_decimal(request.form.get("purchase_price")),
        selling_price=_to_decimal(request.form.get("selling_price")),
        price=_to_decimal(request.form.get("price") or request.form.get("selling_price")),
        notes=(request.form.get("notes") or "").strip() or None,
        min_qty=int(request.form.get("min_qty") or 0),
    )
    try:
        db.session.add(product)
        db.session.commit()
        if _wants_json():
            return jsonify({"ok": True, "id": product.id})
        flash("تم إضافة القطعة بنجاح", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({"ok": False, "error": "db_error", "detail": str(e)}), 500
        flash(f"فشل إنشاء القطعة: {e}", "danger")
    return redirect(url_for("parts_bp.parts_list"))

@parts_bp.post("/<int:id>/edit")
@login_required
@permission_required("manage_inventory")
def parts_edit(id):
    p = db.session.get(Product, id)
    if not p:
        if _wants_json():
            return jsonify({"ok": False, "error": "not_found"}), 404
        flash("القطعة غير موجودة", "danger")
        return redirect(url_for("parts_bp.parts_list"))
    name = (request.form.get("name") or p.name or "").strip()
    if not name:
        if _wants_json():
            return jsonify({"ok": False, "error": "name_required"}), 400
        flash("الاسم مطلوب", "warning")
        return redirect(url_for("parts_bp.parts_list"))
    raw_barcode = (request.form.get("barcode") or "").strip()
    barcode = normalize_barcode(raw_barcode) if raw_barcode else None
    if barcode and not is_valid_ean13(barcode):
        if _wants_json():
            return jsonify({"ok": False, "error": "invalid_barcode"}), 400
        flash("الباركود غير صالح", "danger")
        return redirect(url_for("parts_bp.parts_list"))
    if barcode and db.session.query(Product.id).filter(Product.barcode == barcode, Product.id != p.id).first():
        if _wants_json():
            return jsonify({"ok": False, "error": "barcode_exists"}), 409
        flash("الباركود مستخدم بالفعل", "danger")
        return redirect(url_for("parts_bp.parts_list"))
    p.name = name
    p.sku = (request.form.get("sku") or "").strip() or None
    p.barcode = barcode
    p.unit = (request.form.get("unit") or "").strip() or None
    p.category_name = (request.form.get("category_name") or request.form.get("category") or "").strip() or None
    p.purchase_price = _to_decimal(request.form.get("purchase_price"), p.purchase_price)
    p.selling_price = _to_decimal(request.form.get("selling_price"), p.selling_price)
    p.price = _to_decimal(request.form.get("price") or request.form.get("selling_price"), p.price)
    p.notes = (request.form.get("notes") or "").strip() or None
    p.min_qty = int(request.form.get("min_qty") or (p.min_qty or 0))
    try:
        db.session.commit()
        if _wants_json():
            return jsonify({"ok": True, "id": p.id})
        flash("تم تحديث القطعة بنجاح", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({"ok": False, "error": "db_error", "detail": str(e)}), 500
        flash(f"فشل التحديث: {e}", "danger")
    return redirect(url_for("parts_bp.parts_list"))

@parts_bp.get("/<int:id>/stock")
@login_required
@permission_required("view_parts")
def stock_levels(id):
    p = db.session.get(Product, id)
    if not p:
        if _wants_json():
            return jsonify({"ok": False, "error": "not_found"}), 404
        return "غير موجود", 404
    levels = StockLevel.query.filter_by(product_id=p.id).all()
    data = [{"warehouse": (lvl.warehouse.name if lvl.warehouse else None), "quantity": int(lvl.quantity or 0), "reserved": int(lvl.reserved_quantity or 0)} for lvl in levels]
    if _wants_json():
        return jsonify({"ok": True, "product_id": id, "levels": data})
    lines = [f"{d['warehouse']}: {d['quantity']}" for d in data if d["warehouse"]]
    return "\n".join(lines)

@parts_bp.post("/<int:id>/delete")
@login_required
@permission_required("manage_inventory")
def parts_delete(id):
    p = db.session.get(Product, id)
    if not p:
        if _wants_json():
            return jsonify({"ok": False, "error": "not_found"}), 404
        flash("القطعة غير موجودة", "danger")
        return redirect(url_for("parts_bp.parts_list"))
    try:
        StockLevel.query.filter_by(product_id=p.id).delete()
        db.session.delete(p)
        db.session.commit()
        if _wants_json():
            return jsonify({"ok": True})
        flash("تم حذف القطعة بنجاح", "warning")
    except SQLAlchemyError as e:
        db.session.rollback()
        if _wants_json():
            return jsonify({"ok": False, "error": "db_error", "detail": str(e)}), 500
        flash(f"فشل الحذف: {e}", "danger")
    return redirect(url_for("parts_bp.parts_list"))
