import csv
import io
import uuid
from datetime import datetime

from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_, delete as sa_delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from extensions import db
from utils import _get_or_404, permission_required, format_currency
from forms import (
    ExchangeTransactionForm,
    ExchangeVendorForm,
    ImportForm,
    PartnerShareForm,
    PreOrderForm,
    ProductForm,
    ProductPartnerShareForm,
    ShipmentForm,
    StockLevelForm,
    TransferForm,
)
from models import (
    Customer,
    ExchangeTransaction,
    Partner,
    Payment,
    PaymentDirection,
    PaymentEntityType,
    PaymentStatus,
    PreOrder,
    PreOrderStatus,
    Product,
    ProductPartnerShare,
    Shipment,
    ShipmentItem,
    StockLevel,
    Supplier,
    Transfer,
    Warehouse,
    WarehousePartnerShare,
    WarehouseType,
)

warehouse_bp = Blueprint("warehouse_bp", __name__, url_prefix="/warehouses")


def _get_or_404(model, ident):
    obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj


@warehouse_bp.app_context_processor
def _inject_utils():
    labels = {
        "warehouse_type": {
            "MAIN": "المستودع الرئيسي",
            "PARTNER": "مستودع شريك",
            "EXCHANGE": "مستودع تبادل",
            "TEMP": "مستودع مؤقت",
            "OUTLET": "منفذ بيع",
        },
        "transfer_direction": {"IN": "وارد", "OUT": "صادر", "ADJUSTMENT": "تسوية"},
        "preorder_status": {
            "PENDING": "قيد الانتظار",
            "CONFIRMED": "مؤكد",
            "FULFILLED": "تم التنفيذ",
            "CANCELLED": "ملغى",
        },
    }

    def ar_label(category, key):
        if key is None:
            return ""
        k = getattr(key, "value", key)
        k = str(k)
        return labels.get(category, {}).get(k, k)

    quick = [
        {"title": "كشف المخزون", "endpoint": "warehouse_bp.inventory_summary", "icon": "fa-table"},
        {"title": "إنشاء مستودع", "endpoint": "warehouse_bp.create", "icon": "fa-plus"},
        {"title": "الحجوزات", "endpoint": "warehouse_bp.preorders_list", "icon": "fa-clipboard-list"},
    ]
    return dict(format_currency=format_currency, ar_label=ar_label, AR_LABELS=labels, warehouses_quick_actions=quick)


@warehouse_bp.route("/", methods=["GET"], endpoint="list")
@login_required
@permission_required("view_warehouses")
def list_warehouses():
    q = Warehouse.query
    type_ = (request.args.get("type") or "").strip()
    if type_:
        q = q.filter(Warehouse.warehouse_type == type_.upper())
    parent = request.args.get("parent")
    if parent and str(parent).isdigit():
        q = q.filter(Warehouse.parent_id == int(parent))
    active = request.args.get("active")
    if active in ("0", "1"):
        q = q.filter(Warehouse.is_active == (active == "1"))
    has_partner = request.args.get("has_partner")
    if has_partner in ("0", "1"):
        if has_partner == "1":
            q = q.filter(Warehouse.partner_id.isnot(None))
        else:
            q = q.filter(Warehouse.partner_id.is_(None))
    search = (request.args.get("search") or "").strip()
    if search:
        q = q.filter(Warehouse.name.ilike(f"%{search}%"))
    order = (request.args.get("order") or "name").lower()
    if order == "type":
        q = q.order_by(Warehouse.warehouse_type.asc(), Warehouse.name.asc())
    elif order == "created":
        q = q.order_by(Warehouse.id.desc())
    else:
        q = q.order_by(Warehouse.name.asc())
    warehouses = q.all()
    if request.is_json or (request.args.get("format") or "").lower() == "json":
        data = []
        for w in warehouses:
            wt = getattr(w.warehouse_type, "value", w.warehouse_type)
            data.append(
                {
                    "id": w.id,
                    "name": w.name,
                    "warehouse_type": wt,
                    "warehouse_type_label": _inject_utils()["ar_label"]("warehouse_type", wt),
                    "parent_id": w.parent_id,
                    "partner_id": w.partner_id,
                    "is_active": bool(w.is_active),
                    "capacity": w.capacity,
                    "location": w.location,
                }
            )
        return jsonify({"data": data})
    return render_template(
        "warehouses/list.html",
        warehouses=warehouses,
        filter_type=type_ or "",
        parent=parent or "",
        search=search,
        active=active or "",
        has_partner=has_partner or "",
        order=order,
    )


@warehouse_bp.route("/create", methods=["GET", "POST"], endpoint="create")
@login_required
@permission_required("manage_warehouses")
def create_warehouse():
    from forms import WarehouseForm

    form = WarehouseForm()
    if form.validate_on_submit():
        parent_id = None
        if getattr(form, "parent_id", None) and getattr(form.parent_id, "data", None):
            parent_obj = form.parent_id.data
            parent_id = getattr(parent_obj, "id", None)
        partner_id = None
        if getattr(form, "partner_id", None) and getattr(form.partner_id, "data", None):
            partner_obj = form.partner_id.data
            partner_id = getattr(partner_obj, "id", None)
        wh_type = (form.warehouse_type.data or "").strip().upper()
        share_percent = form.share_percent.data if wh_type == "PARTNER" else 0
        w = Warehouse(
            name=(form.name.data or "").strip(),
            warehouse_type=wh_type,
            location=((form.location.data or "").strip() or None),
            parent_id=parent_id,
            partner_id=partner_id,
            share_percent=share_percent,
            capacity=form.capacity.data,
            is_active=True if form.is_active.data is None else bool(form.is_active.data),
        )
        db.session.add(w)
        try:
            db.session.commit()
            current_app.logger.info("Created warehouse id=%s name=%s type=%s", w.id, w.name, w.warehouse_type)
            flash("تم إنشاء المستودع بنجاح", "success")
            return redirect(url_for("warehouse_bp.list"))
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.exception("Create warehouse failed")
            flash(f"حدث خطأ أثناء إنشاء المستودع: {e.__class__.__name__}", "danger")
    if request.method == "POST" and form.errors:
        for field, errs in form.errors.items():
            for err in errs:
                flash(f"{field}: {err}", "danger")
    return render_template("warehouses/form.html", form=form)


@warehouse_bp.route("/<int:warehouse_id>/edit", methods=["GET", "POST"], endpoint="edit")
@login_required
@permission_required("manage_warehouses")
def edit_warehouse(warehouse_id):
    from forms import WarehouseForm

    w = _get_or_404(Warehouse, warehouse_id)
    form = WarehouseForm(obj=w)
    if form.validate_on_submit():
        w.name = (form.name.data or "").strip()
        w.warehouse_type = form.warehouse_type.data
        w.location = (form.location.data or "").strip() or None
        w.capacity = form.capacity.data
        w.is_active = form.is_active.data
        w.parent_id = form.parent_id.data.id if form.parent_id.data else None
        w.partner_id = form.partner_id.data.id if form.partner_id.data else None
        w.share_percent = form.share_percent.data if w.warehouse_type == "PARTNER" else 0
        try:
            db.session.commit()
            flash("تم تحديث بيانات المستودع", "success")
            return redirect(url_for("warehouse_bp.list"))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"حدث خطأ: {e}", "danger")
    return render_template("warehouses/form.html", form=form, warehouse=w)


@warehouse_bp.route("/<int:warehouse_id>/delete", methods=["POST"], endpoint="delete")
@login_required
@permission_required("manage_warehouses")
def delete_warehouse(warehouse_id):
    _get_or_404(Warehouse, warehouse_id)
    try:
        db.session.execute(sa_delete(Warehouse).where(Warehouse.id == warehouse_id))
        db.session.commit()
        db.session.expire_all()
        flash("تم حذف المستودع", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"خطأ أثناء الحذف: {e}", "danger")
    return redirect(url_for("warehouse_bp.list"))


@warehouse_bp.route("/<int:warehouse_id>", methods=["GET"], endpoint="detail")
@login_required
@permission_required("view_warehouses", "view_inventory", "manage_inventory")
def warehouse_detail(warehouse_id):
    w = _get_or_404(Warehouse, warehouse_id)
    stock_levels = StockLevel.query.filter_by(warehouse_id=warehouse_id).options(joinedload(StockLevel.product)).all()
    transfers_in = Transfer.query.filter_by(destination_id=warehouse_id).all()
    transfers_out = Transfer.query.filter_by(source_id=warehouse_id).all()
    return render_template(
        "warehouses/detail.html",
        warehouse=w,
        stock_levels=stock_levels,
        transfers_in=transfers_in,
        transfers_out=transfers_out,
        stock_form=StockLevelForm(),
        transfer_form=TransferForm(),
        exchange_form=ExchangeTransactionForm(),
        share_form=ProductPartnerShareForm(),
        shipment_form=ShipmentForm(),
    )

@warehouse_bp.route("/goto/warehouse-products", methods=["GET"], endpoint="goto_warehouse_products")
@login_required
@permission_required("view_inventory")
def goto_warehouse_products():
    wid = request.args.get("id", type=int)
    if not wid:
        flash("أدخل رقم المستودع.", "warning")
        return redirect(url_for("warehouse_bp.list"))
    return redirect(url_for("warehouse_bp.products", id=wid))


@warehouse_bp.route("/goto/product-card", methods=["GET"], endpoint="goto_product_card")
@login_required
@permission_required("view_parts")
def goto_product_card():
    pid = request.args.get("id", type=int)
    if not pid:
        flash("أدخل رقم القطعة.", "warning")
        return redirect(url_for("warehouse_bp.list"))
    return redirect(url_for("warehouse_bp.product_card", product_id=pid))


@warehouse_bp.route("/inventory", methods=["GET"], endpoint="inventory_summary")
@login_required
@permission_required("view_inventory")
def inventory_summary():
    search = (request.args.get("q") or "").strip()
    selected_ids = request.args.getlist("warehouse_ids", type=int)
    if not selected_ids:
        selected_ids = [w.id for w in Warehouse.query.order_by(Warehouse.name).all()]

    whs = Warehouse.query.filter(Warehouse.id.in_(selected_ids)).order_by(Warehouse.name.asc()).all()
    wh_ids = [w.id for w in whs]

    if wh_ids:
        q = (
            db.session.query(StockLevel)
            .join(Product, StockLevel.product_id == Product.id)
            .filter(StockLevel.warehouse_id.in_(wh_ids))
            .options(joinedload(StockLevel.product))
            .order_by(Product.name.asc())
        )
        if search:
            q = q.filter(Product.name.ilike(f"%{search}%"))
        rows = q.all()
    else:
        rows = []

    pivot = {}
    for sl in rows:
        pid = sl.product_id
        p = sl.product
        if pid not in pivot:
            pivot[pid] = {"product": p, "by": {wid: {"on": 0, "res": 0} for wid in wh_ids}, "total": 0}
        on = int(sl.quantity or 0)
        res = int(getattr(sl, "reserved_quantity", 0) or 0)
        pivot[pid]["by"][sl.warehouse_id] = {"on": on, "res": res}
        pivot[pid]["total"] += on

    rows_data = sorted(pivot.values(), key=lambda d: (d["product"].name or "").lower())

    if (request.args.get("export") or "").lower() == "csv":
        si = io.StringIO()
        writer = csv.writer(si)
        header = ["ID", "القطعة", "SKU"] + [w.name for w in whs] + ["الإجمالي"]
        writer.writerow(header)
        for r in rows_data:
            p = r["product"]
            sku = getattr(p, "sku", None) or ""
            line = [str(getattr(p, "id", "") or ""), (p.name or ""), sku]
            for wid in wh_ids:
                line.append(str(r["by"][wid]["on"]))
            line.append(str(r["total"]))
            writer.writerow(line)
        output = si.getvalue().encode("utf-8-sig")
        return Response(
            output,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=inventory_summary.csv"},
        )

    return render_template(
        "warehouses/inventory_summary.html",
        warehouses=whs,
        rows=rows_data,
        selected_ids=wh_ids,
        search=search,
    )

@warehouse_bp.route("/<int:id>/products", methods=["GET"], endpoint="products")
@login_required
@permission_required("view_inventory")
def products(id):
    base_warehouse = _get_or_404(Warehouse, id)
    all_whs = Warehouse.query.order_by(Warehouse.name).all()
    selected_ids = request.args.getlist("warehouse_ids", type=int) or [id]
    whs = [w for w in all_whs if w.id in selected_ids]
    wh_ids = [w.id for w in whs]
    search = (request.args.get("q") or "").strip()
    q = (
        db.session.query(StockLevel)
        .join(Product, StockLevel.product_id == Product.id)
        .filter(StockLevel.warehouse_id.in_(wh_ids))
        .options(joinedload(StockLevel.product))
        .order_by(Product.name.asc())
    )
    if search:
        q = q.filter(Product.name.ilike(f"%{search}%"))
    rows = q.all()
    pivot = {}
    for sl in rows:
        pid = sl.product_id
        p = sl.product
        if pid not in pivot:
            pivot[pid] = {"product": p, "by": {wid: {"on": 0, "res": 0} for wid in wh_ids}, "total": 0}
        on = int(sl.quantity or 0)
        res = int(getattr(sl, "reserved_quantity", 0) or 0)
        pivot[pid]["by"][sl.warehouse_id] = {"on": on, "res": res}
        pivot[pid]["total"] += on
    rows_data = sorted(pivot.values(), key=lambda d: (d["product"].name or "").lower())
    if (request.args.get("export") or "").lower() == "csv":
        si = io.StringIO()
        writer = csv.writer(si)
        header = ["القطعة", "SKU"] + [w.name for w in whs] + ["الإجمالي"]
        writer.writerow(header)
        for r in rows_data:
            p = r["product"]
            sku = getattr(p, "sku", None) or ""
            line = [p.name or "", sku]
            for wid in wh_ids:
                line.append(str(r["by"][wid]["on"]))
            line.append(str(r["total"]))
            writer.writerow(line)
        output = si.getvalue().encode("utf-8-sig")
        return Response(output, mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=warehouse_products.csv"})
    return render_template(
        "warehouses/products.html",
        warehouse=base_warehouse,
        warehouses=all_whs,
        selected_ids=wh_ids,
        whs=whs,
        rows=rows_data,
        search=search,
        active_warehouse_id=base_warehouse.id,
        active_warehouse=base_warehouse,
        warehouse_id=base_warehouse.id,
    )

@warehouse_bp.route("/<int:id>/add-product", methods=["GET", "POST"], endpoint="add_product")
@login_required
@permission_required("manage_inventory")
def add_product(id):
    log = current_app.logger
    log.info("add_product:start id=%s method=%s path=%s", id, request.method, request.path)

    warehouse = _get_or_404(Warehouse, id)
    form = ProductForm()
    partners_forms, exchange_vendors_forms = [], []

    def _initial_qty():
        q = form.on_hand.data if form.on_hand.data not in (None, "") else form.quantity.data
        try:
            return int(q or 0)
        except Exception:
            return 0

    def _reserved_qty():
        try:
            return int(form.reserved_quantity.data or 0)
        except Exception:
            return 0

    # معلومات عن نوع المستودع (للتتبّع)
    try:
        wtype_raw = warehouse.warehouse_type.value if hasattr(warehouse.warehouse_type, "value") else str(warehouse.warehouse_type)
    except Exception:
        wtype_raw = str(warehouse.warehouse_type)
    wtype = (wtype_raw or "").upper()
    log.debug("add_product:warehouse_type=%s", wtype)

    if request.method == "POST":
        log.debug("add_product:POST keys=%s", list(request.form.keys()))
        valid = form.validate_on_submit()
        log.debug("add_product:validate_on_submit=%s has_csrf=%s",
                  valid, bool(getattr(form, "csrf_token", None)))

        if valid:
            try:
                product = Product()
                form.apply_to(product)
                db.session.add(product)
                db.session.flush()
                log.info("add_product:product_created id=%s name=%r sku=%r",
                         getattr(product, "id", None),
                         getattr(product, "name", None),
                         getattr(product, "sku", None))

                init_qty = max(_initial_qty(), 0)
                init_res = max(_reserved_qty(), 0)
                log.debug("add_product:init_qty=%s init_reserved=%s", init_qty, init_res)

                sl = StockLevel.query.filter_by(
                    warehouse_id=warehouse.id, product_id=product.id
                ).first()
                if not sl:
                    sl = StockLevel(
                        warehouse_id=warehouse.id,
                        product_id=product.id,
                        quantity=0,
                        reserved_quantity=0,
                    )
                    db.session.add(sl)
                    log.debug("add_product:stock_level_created for product_id=%s", product.id)

                sl.quantity = (sl.quantity or 0) + init_qty
                sl.reserved_quantity = max(init_res, 0)
                log.debug("add_product:stock_level_updated qty=%s reserved=%s", sl.quantity, sl.reserved_quantity)

                if warehouse.warehouse_type == WarehouseType.PARTNER.value:
                    partner_ids = request.form.getlist("partner_id")
                    shares = request.form.getlist("share_percentage")
                    share_amounts = request.form.getlist("share_amount")
                    notes_list = request.form.getlist("notes")
                    log.debug("add_product:partners_rows count=%s", len(partner_ids or []))

                    for idx, (partner_id, share) in enumerate(zip(partner_ids, shares)):
                        try:
                            pid = int(partner_id)
                            perc = float(share or 0)
                        except ValueError:
                            log.warning("add_product:skip_partner_row idx=%s partner_id=%r share=%r", idx, partner_id, share)
                            continue
                        try:
                            amt = float(share_amounts[idx]) if idx < len(share_amounts) and share_amounts[idx] not in (None, "", "None") else 0.0
                        except Exception:
                            amt = 0.0
                        note = notes_list[idx].strip() if idx < len(notes_list) and notes_list[idx] not in (None, "", "None") else None
                        db.session.add(ProductPartnerShare(
                            product_id=product.id,
                            partner_id=pid,
                            share_percentage=perc,
                            share_amount=amt,
                            notes=note
                        ))
                        log.debug("add_product:partner_share idx=%s partner_id=%s perc=%s amt=%s", idx, pid, perc, amt)

                elif warehouse.warehouse_type == WarehouseType.EXCHANGE.value:
                    supplier_ids = request.form.getlist("supplier_id")
                    vendor_phones = request.form.getlist("vendor_phone")
                    vendor_paid = request.form.getlist("vendor_paid")
                    vendor_prices = request.form.getlist("vendor_price")

                    maxlen = max(len(supplier_ids or []), len(vendor_phones or []), len(vendor_paid or []), len(vendor_prices or []), 1)
                    log.debug("add_product:exchange_rows count=%s", maxlen)

                    for i in range(maxlen):
                        sid = supplier_ids[i] if i < len(supplier_ids) else None
                        phone = vendor_phones[i] if i < len(vendor_phones) else None
                        paid = vendor_paid[i] if i < len(vendor_paid) else None
                        price = vendor_prices[i] if i < len(vendor_prices) else None

                        sname = None
                        if sid and str(sid).isdigit():
                            sup = db.session.get(Supplier, int(sid))
                            if sup:
                                sname = sup.name

                        note_parts = []
                        if sid and str(sid).isdigit():
                            note_parts.append(f"SupplierID:{sid}{'(' + sname + ')' if sname else ''}")
                        if phone:
                            note_parts.append(f"phone:{phone}")
                        if paid:
                            note_parts.append(f"paid:{paid}")
                        if price:
                            note_parts.append(f"price:{price}")
                        note_txt = " | ".join(note_parts) if note_parts else None

                        db.session.add(ExchangeTransaction(
                            product_id=product.id,
                            warehouse_id=warehouse.id,
                            partner_id=None,
                            quantity=init_qty,
                            direction="IN",
                            notes=note_txt
                        ))
                        log.debug("add_product:exchange_tx i=%s supplier_id=%r phone=%r paid=%r price=%r", i, sid, phone, paid, price)

                db.session.commit()
                log.info("add_product:commit_ok product_id=%s", product.id)
                flash("تمت إضافة القطعة بنجاح", "success")
                return redirect(url_for("warehouse_bp.add_product", id=warehouse.id))

            except Exception as e:
                db.session.rollback()
                log.exception("add_product:exception_during_save")
                flash(f"فشل حفظ المنتج: {e}", "danger")
        else:
            log.warning("add_product:validation_failed errors=%s", form.errors)
            flash("تعذّر حفظ المنتج. تأكّد من الحقول المطلوبة.", "danger")

    # حضّر فورمات الأقسام الديناميكية للواجهة
    if warehouse.warehouse_type == WarehouseType.PARTNER.value:
        partners_forms = [ProductPartnerShareForm()]
    elif warehouse.warehouse_type == WarehouseType.EXCHANGE.value:
        exchange_vendors_forms = [ExchangeVendorForm()]

    log.debug("add_product:render_template wtype=%s partners_forms=%s exchange_forms=%s",
              wtype, len(partners_forms), len(exchange_vendors_forms))

    return render_template(
        "warehouses/add_product.html",
        form=form,
        warehouse=warehouse,
        partners_forms=partners_forms,
        exchange_vendors_forms=exchange_vendors_forms,
        wtype=wtype
    )

@warehouse_bp.route("/<int:id>/import", methods=["GET", "POST"], endpoint="import_products")
@login_required
@permission_required("manage_inventory")
def import_products(id):
    w = _get_or_404(Warehouse, id)
    form = ImportForm()
    file_obj = None
    if request.method == "POST":
        file_obj = request.files.get("file") or getattr(getattr(form, "file", None), "data", None)
        if file_obj:
            try:
                stream = io.StringIO(file_obj.stream.read().decode("utf-8"), newline=None)
            except Exception:
                try:
                    file_obj.seek(0)
                    stream = io.StringIO(file_obj.read().decode("utf-8"), newline=None)
                except Exception:
                    stream = None
            if stream:
                reader = csv.DictReader(stream)
                for row in reader:
                    name = (row.get("name") or "").strip()
                    sku = (row.get("sku") or "").strip() or None
                    if not name:
                        continue
                    p = Product(name=name)
                    if hasattr(p, "sku"):
                        setattr(p, "sku", sku)
                    db.session.add(p)
                db.session.commit()
                return redirect(url_for("warehouse_bp.detail", warehouse_id=w.id))
    return render_template("warehouses/import_products.html", form=form, warehouse=w)


@warehouse_bp.route("/<int:warehouse_id>/stock", methods=["POST"], endpoint="ajax_update_stock")
@login_required
@permission_required("manage_inventory")
def ajax_update_stock(warehouse_id):
    def _to_int(v, default=0):
        try:
            if v in (None, "", "None"):
                return default
            return int(float(v))
        except Exception:
            return default

    form = StockLevelForm()
    if form.validate_on_submit():
        pid = getattr(getattr(form.product_id.data, "id", None), "__int__", lambda: None)() if hasattr(form.product_id.data, "id") else None
        if pid is None:
            pid = _to_int(request.form.get("product_id"), None)
        if pid is None:
            return jsonify({"success": False, "errors": {"product_id": ["قيمة غير صالحة"]}}), 400
        quantity = _to_int(form.quantity.data, 0)
        min_stock = _to_int(form.min_stock.data, 0)
        max_stock = _to_int(form.max_stock.data, 0)
    else:
        pid = _to_int(request.form.get("product_id"), None)
        quantity = _to_int(request.form.get("quantity"), 0)
        min_stock = _to_int(request.form.get("min_stock"), 0)
        max_stock = _to_int(request.form.get("max_stock"), 0)
        if pid is None:
            return jsonify({"success": False, "errors": {"product_id": ["قيمة غير صالحة"]}}), 400
    sl = StockLevel.query.filter_by(warehouse_id=warehouse_id, product_id=pid).first() or StockLevel(warehouse_id=warehouse_id, product_id=pid, quantity=0, reserved_quantity=0)
    sl.quantity = max(quantity, 0)
    sl.min_stock = max(min_stock, 0)
    sl.max_stock = max(max_stock, 0)
    db.session.add(sl)
    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400
    alert = "below_min" if (sl.quantity or 0) <= (sl.min_stock or 0) else None
    return jsonify({"success": True, "quantity": int(sl.quantity or 0), "partner_share": getattr(sl, "partner_share_quantity", None), "company_share": getattr(sl, "company_share_quantity", None), "alert": alert}), 200


@warehouse_bp.route("/<int:warehouse_id>/transfer", methods=["POST"], endpoint="ajax_transfer")
@login_required
@permission_required("manage_inventory", "manage_warehouses", "warehouse_transfer")
def ajax_transfer(warehouse_id):
    data = request.get_json(silent=True) or request.form

    def _i(name):
        v = data.get(name)
        try:
            return int(v) if v is not None and str(v).strip() != "" else None
        except Exception:
            return None

    pid = _i("product_id")
    sid = _i("source_id")
    did = _i("destination_id")
    try:
        qty = int(float(data.get("quantity", 0)))
    except Exception:
        qty = 0
    ds = (data.get("date") or "").strip()
    try:
        tdate = datetime.fromisoformat(ds) if ds else datetime.utcnow()
    except Exception:
        tdate = datetime.utcnow()
    notes = (data.get("notes") or "").strip() or None
    if not (pid and sid and did and qty > 0) or sid == did:
        return jsonify({"success": False, "errors": {"form": "invalid"}}), 400
    if sid != warehouse_id:
        return jsonify({"success": False, "errors": {"warehouse": "mismatch"}}), 400
    src = StockLevel.query.filter_by(warehouse_id=sid, product_id=pid).first()
    available = int((src.quantity or 0) - (src.reserved_quantity or 0)) if src else 0
    if available < qty:
        return jsonify({"success": False, "error": "insufficient_stock", "available": max(available, 0)}), 400
    src.quantity = (src.quantity or 0) - qty
    dst = StockLevel.query.filter_by(warehouse_id=did, product_id=pid).first()
    if not dst:
        dst = StockLevel(warehouse_id=did, product_id=pid, quantity=0, reserved_quantity=0)
        db.session.add(dst)
    dst.quantity = (dst.quantity or 0) + qty
    t = Transfer(transfer_date=tdate, product_id=pid, source_id=sid, destination_id=did, quantity=qty, direction="OUT", notes=notes, user_id=getattr(current_user, "id", None))
    setattr(t, "_skip_stock_apply", True)
    db.session.add(t)
    try:
        db.session.commit()
        return jsonify({"success": True, "transfer_id": t.id, "direction": "OUT"}), 200
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"success": False, "error": "db_error"}), 500


@warehouse_bp.route("/<int:warehouse_id>/exchange", methods=["POST"], endpoint="ajax_exchange")
@login_required
@permission_required("manage_inventory")
def ajax_exchange(warehouse_id):
    data = request.form if request.form else (request.get_json(silent=True) or {})

    def _i(k, d=None):
        try:
            v = data.get(k)
            return int(v) if v not in (None, "", "None") else d
        except:
            return d

    def _qty(v):
        try:
            return int(float(v))
        except:
            return 0

    def _f(v):
        try:
            return float(v) if v not in (None, "", "None") else None
        except:
            return None

    pid = _i("product_id")
    partner_id = _i("partner_id")
    qty = _qty(data.get("quantity"))
    direction = (data.get("direction") or "").upper()
    unit_cost = _f(data.get("unit_cost"))
    notes = data.get("notes") or None
    if not (pid and qty > 0 and direction in ("IN", "OUT", "ADJUSTMENT")):
        return jsonify({"success": False, "errors": {"form": "invalid"}}), 400
    ex = ExchangeTransaction(product_id=pid, warehouse_id=warehouse_id, partner_id=partner_id, quantity=qty, direction=direction, unit_cost=unit_cost, is_priced=bool(unit_cost is not None), notes=notes)
    db.session.add(ex)
    try:
        sl = StockLevel.query.filter_by(warehouse_id=warehouse_id, product_id=pid).first()
        if not sl:
            sl = StockLevel(warehouse_id=warehouse_id, product_id=pid, quantity=0, reserved_quantity=0)
            db.session.add(sl)
        if direction == "IN":
            sl.quantity = (sl.quantity or 0) + qty
        elif direction == "OUT":
            if (sl.quantity or 0) < qty:
                raise ValueError("insufficient")
            sl.quantity -= qty
        else:
            sl.quantity = max((sl.quantity or 0) + qty, 0)
        db.session.commit()
        return jsonify({"success": True, "new_quantity": int(sl.quantity or 0)}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@warehouse_bp.route("/<int:warehouse_id>/partner-shares", methods=["GET", "POST"], endpoint="partner_shares")
@login_required
@permission_required("manage_inventory")
def partner_shares(warehouse_id):
    if request.method == "GET":
        try:
            wps = WarehousePartnerShare.query.join(Product, WarehousePartnerShare.product_id == Product.id).filter(WarehousePartnerShare.warehouse_id == warehouse_id).all()
        except Exception:
            wps = []
        rows = wps or ProductPartnerShare.query.join(Product).join(StockLevel, StockLevel.product_id == ProductPartnerShare.product_id).filter(StockLevel.warehouse_id == warehouse_id).all()
        data = []
        for s in rows:
            partner = getattr(s, "partner", None)
            product = getattr(s, "product", None)
            pct = float(getattr(s, "share_percentage", getattr(s, "share_percent", 0)) or 0)
            amt = float(getattr(s, "share_amount", 0) or 0)
            data.append({"id": getattr(s, "id", None), "product": product.name if product else None, "partner": partner.name if partner else None, "share_percentage": pct, "share_amount": amt, "notes": s.notes or ""})
        return jsonify({"success": True, "shares": data}), 200
    payload = request.get_json(silent=True) or {}
    updates = payload.get("shares", [])
    if not isinstance(updates, list):
        return jsonify({"success": False, "error": "invalid_payload"}), 400
    try:
        valid_products = {sl.product_id for sl in StockLevel.query.filter_by(warehouse_id=warehouse_id).all()}
        for item in updates:
            pid = item.get("product_id")
            prt = item.get("partner_id")
            if not (isinstance(pid, int) and isinstance(prt, int)):
                continue
            if valid_products and pid not in valid_products:
                continue
            pct = float(item.get("share_percentage", item.get("share_percent", 0)) or 0)
            try:
                amt = float(item.get("share_amount", 0) or 0)
            except Exception:
                amt = 0.0
            notes = (item.get("notes") or "").strip() or None
            try:
                row = WarehousePartnerShare.query.filter_by(warehouse_id=warehouse_id, product_id=pid, partner_id=prt).first()
                if row:
                    row.share_percentage = pct
                    row.share_amount = amt
                    row.notes = notes
                else:
                    db.session.add(WarehousePartnerShare(warehouse_id=warehouse_id, product_id=pid, partner_id=prt, share_percentage=pct, share_amount=amt, notes=notes))
            except Exception:
                row2 = ProductPartnerShare.query.filter_by(product_id=pid, partner_id=prt).first()
                if row2:
                    row2.share_percentage = pct
                    row2.share_amount = amt
                    row2.notes = notes
                else:
                    db.session.add(ProductPartnerShare(product_id=pid, partner_id=prt, share_percentage=pct, share_amount=amt, notes=notes))
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@warehouse_bp.route("/<int:id>/transfers", methods=["GET"], endpoint="transfers")
@login_required
@permission_required("view_inventory")
def transfers(id):
    warehouse = _get_or_404(Warehouse, id)
    transfers = Transfer.query.filter(or_(Transfer.source_id == id, Transfer.destination_id == id)).order_by(Transfer.transfer_date.desc()).all()
    return render_template("warehouses/transfers_list.html", warehouse=warehouse, transfers=transfers)


@warehouse_bp.route("/<int:id>/transfers/create", methods=["GET", "POST"], endpoint="create_transfer")
@login_required
@permission_required("manage_inventory")
def create_transfer(id=None, warehouse_id=None):
    wid = warehouse_id or id
    warehouse = _get_or_404(Warehouse, wid)
    form = TransferForm()
    if form.validate_on_submit():
        t = Transfer(transfer_date=form.date.data or datetime.utcnow(), product_id=form.product_id.data.id, source_id=form.source_id.data.id, destination_id=form.destination_id.data.id, quantity=form.quantity.data, direction=form.direction.data, notes=form.notes.data, user_id=current_user.id)
        db.session.add(t)
        try:
            src = StockLevel.query.filter_by(warehouse_id=t.source_id, product_id=t.product_id).first()
            if not src or (src.quantity or 0) < t.quantity:
                raise ValueError("الكمية غير متوفرة في المصدر")
            src.quantity -= t.quantity
            dst = StockLevel.query.filter_by(warehouse_id=t.destination_id, product_id=t.product_id).first()
            if not dst:
                dst = StockLevel(warehouse_id=t.destination_id, product_id=t.product_id, quantity=0, reserved_quantity=0)
                db.session.add(dst)
            dst.quantity += t.quantity
            db.session.commit()
            flash("تم إضافة التحويل بنجاح", "success")
            return redirect(url_for("warehouse_bp.transfers", id=wid))
        except Exception as e:
            db.session.rollback()
            flash(f"خطأ أثناء إضافة التحويل: {e}", "danger")
    return render_template("warehouses/transfers_form.html", warehouse=warehouse, form=form)


@warehouse_bp.route("/parts/<int:product_id>", methods=["GET"], endpoint="product_card")
@login_required
@permission_required("view_parts")
def product_card(product_id):
    part = Product.query.options(joinedload(Product.supplier_international), joinedload(Product.supplier_local), joinedload(Product.supplier_general), joinedload(Product.vehicle_type), joinedload(Product.category)).filter_by(id=product_id).first()
    if part is None:
        abort(404)
    warehouses = Warehouse.query.order_by(Warehouse.name).all()
    stock = []
    for w in warehouses:
        lvl = StockLevel.query.filter_by(product_id=part.id, warehouse_id=w.id).first()
        qty = (lvl.quantity or 0) if lvl else 0
        res = getattr(lvl, "reserved_quantity", 0) if lvl else 0
        stock.append({"warehouse": w, "on_hand": qty, "reserved": res, "virtual_available": qty - res})
    transfers = Transfer.query.filter_by(product_id=part.id).options(joinedload(Transfer.source_warehouse), joinedload(Transfer.destination_warehouse)).order_by(Transfer.transfer_date.desc()).all()
    exchanges = ExchangeTransaction.query.filter_by(product_id=part.id).options(joinedload(ExchangeTransaction.partner)).order_by(getattr(ExchangeTransaction, "created_at", ExchangeTransaction.id).desc()).all()
    shipments = ShipmentItem.query.filter_by(product_id=part.id).join(Shipment).options(joinedload(ShipmentItem.shipment), joinedload(ShipmentItem.warehouse)).order_by(func.coalesce(Shipment.actual_arrival, Shipment.expected_arrival, Shipment.shipment_date).desc()).all()
    return render_template("parts/card.html", part=part, stock=stock, transfers=transfers, exchanges=exchanges, shipments=shipments)


@warehouse_bp.route("/preorders", methods=["GET"], endpoint="preorders_list")
@login_required
@permission_required("view_preorders")
def preorders_list():
    q = PreOrder.query
    status = request.args.get("status")
    code = request.args.get("code")
    df = request.args.get("date_from")
    dt = request.args.get("date_to")
    if status:
        q = q.filter(PreOrder.status == status)
    if code:
        q = q.filter(PreOrder.reference.ilike(f"%{code}%"))
    try:
        if df:
            q = q.filter(PreOrder.created_at >= datetime.fromisoformat(df))
        if dt:
            q = q.filter(PreOrder.created_at <= datetime.fromisoformat(dt))
    except ValueError:
        pass
    q = q.order_by(PreOrder.created_at.desc())
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    preorders = pagination.items
    if request.args.get("format") == "json" or request.is_json:
        def _entity_info(p):
            if p.customer_id:
                return "customer", (p.customer.name if p.customer else None)
            if p.supplier_id:
                return "supplier", (p.supplier.name if p.supplier else None)
            if p.partner_id:
                return "partner", (p.partner.name if p.partner else None)
            return None, None

        data = []
        for p in preorders:
            etype, ename = _entity_info(p)
            data.append(
                {
                    "id": p.id,
                    "code": p.reference,
                    "entity_type": etype,
                    "entity_name": ename,
                    "product": p.product.name if p.product else None,
                    "warehouse": p.warehouse.name if p.warehouse else None,
                    "quantity": p.quantity,
                    "prepaid_amount": float(p.prepaid_amount or 0),
                    "status": p.status,
                    "status_label": _inject_utils()["ar_label"]("preorder_status", p.status),
                    "created_at": p.created_at.isoformat(),
                }
            )
        return jsonify({"data": data, "meta": {"page": pagination.page, "per_page": pagination.per_page, "total": pagination.total, "pages": pagination.pages}})
    return render_template("parts/preorders_list.html", preorders=preorders, pagination=pagination, filters={"status": status, "code": code, "date_from": df, "date_to": dt})

from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import uuid, random

@warehouse_bp.route("/preorders/create", methods=["GET", "POST"], endpoint="preorder_create")
@login_required
@permission_required("add_preorder")
def preorder_create():
    form = PreOrderForm()

    def _gen_ref():
        base = datetime.utcnow().strftime("PR%Y%m%d")
        for _ in range(10):
            code = f"{base}-{str(random.randint(0, 9999)).zfill(4)}"
            if not db.session.query(PreOrder.id).filter_by(reference=code).first():
                return code
        return uuid.uuid4().hex[:10].upper()

    if form.validate_on_submit():
        customer_id  = int(form.customer_id.data)
        product_id   = int(form.product_id.data)
        warehouse_id = int(form.warehouse_id.data)
        qty          = int(form.quantity.data or 1)
        prepaid      = float(form.prepaid_amount.data or 0)
        tax          = float(form.tax_rate.data or 0)

        user_ref = (form.reference.data or "").strip()
        if user_ref and db.session.query(PreOrder.id).filter_by(reference=user_ref).first():
            flash("مرجع الحجز مستخدم مسبقًا. غيّر المرجع أو اتركه فارغًا ليُولَّد تلقائيًا.", "danger")
            return render_template("parts/preorder_form.html", form=form), 200
        code = user_ref or _gen_ref()

        preorder = PreOrder(
            reference=code,
            preorder_date=form.preorder_date.data or datetime.utcnow(),
            expected_date=form.expected_date.data or None,
            customer_id=customer_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            quantity=qty,
            prepaid_amount=prepaid,
            tax_rate=tax,
            status=form.status.data,
            notes=form.notes.data or None,
            payment_method=form.payment_method.data or "cash",
        )
        db.session.add(preorder)
        db.session.flush()

        sl = StockLevel.query.filter_by(product_id=product_id, warehouse_id=warehouse_id).first()
        if not sl:
            sl = StockLevel(product_id=product_id, warehouse_id=warehouse_id, quantity=0, reserved_quantity=0)
            db.session.add(sl)
        sl.reserved_quantity = (sl.reserved_quantity or 0) + qty

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            if "preorders.reference" in str(e).lower() and not user_ref:
                preorder.reference = _gen_ref()
                db.session.add(preorder)
                try:
                    db.session.commit()
                except SQLAlchemyError as ee:
                    db.session.rollback()
                    flash(f"تعذر حفظ الحجز: {getattr(ee, 'orig', ee)}", "danger")
                    return render_template("parts/preorder_form.html", form=form), 200
            else:
                flash("مرجع الحجز مستخدم مسبقًا. غيّر المرجع أو اتركه فارغًا ليُولَّد تلقائيًا.", "danger")
                return render_template("parts/preorder_form.html", form=form), 200
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"تعذر حفظ الحجز: {getattr(e, 'orig', e)}", "danger")
            return render_template("parts/preorder_form.html", form=form), 200

        if prepaid > 0:
            pay = Payment(
                entity_type=(PaymentEntityType.PREORDER.value if hasattr(PaymentEntityType, "PREORDER") else "PREORDER"),
                preorder_id=preorder.id,
                direction=(PaymentDirection.INCOMING.value if hasattr(PaymentDirection, "INCOMING") else "INCOMING"),
                status=(PaymentStatus.COMPLETED.value if hasattr(PaymentStatus, "COMPLETED") else "COMPLETED"),
                payment_date=datetime.utcnow(),
                total_amount=prepaid,
                currency="ILS",
                method=form.payment_method.data or "cash",
                reference=f"Preorder {preorder.reference}",
                notes=f"دفعة عربون لحجز {preorder.product.name if preorder.product else ''} (كود: {preorder.reference})",
            )
            db.session.add(pay)
            try:
                db.session.commit()
                flash("تم إنشاء الحجز وتسجيل العربون", "success")
            except SQLAlchemyError as e:
                db.session.rollback()
                flash(f"تم إنشاء الحجز، لكن تعذر تسجيل الدفعة: {getattr(e, 'orig', e)}", "warning")
        else:
            flash("تم إنشاء الحجز بنجاح", "success")

        return redirect(url_for("warehouse_bp.preorder_detail", preorder_id=preorder.id))

    elif request.method == "POST":
        flash("فشل إنشاء الحجز. تحقق من الحقول المطلوبة.", "danger")

    return render_template("parts/preorder_form.html", form=form)

@warehouse_bp.route("/preorders/<int:preorder_id>", methods=["GET"], endpoint="preorder_detail")
@login_required
@permission_required("view_preorders")
def preorder_detail(preorder_id):
    preorder = PreOrder.query.options(joinedload(PreOrder.customer), joinedload(PreOrder.supplier), joinedload(PreOrder.partner), joinedload(PreOrder.product), joinedload(PreOrder.warehouse), joinedload(PreOrder.payments)).filter_by(id=preorder_id).first()
    if preorder is None:
        abort(404)
    return render_template("parts/preorder_detail.html", preorder=preorder)


@warehouse_bp.route("/preorders/<int:preorder_id>/fulfill", methods=["POST"], endpoint="preorder_fulfill")
@login_required
@permission_required("edit_preorder")
def preorder_fulfill(preorder_id):
    preorder = _get_or_404(PreOrder, preorder_id)
    if preorder.status != "FULFILLED":
        try:
            preorder.status = "FULFILLED"
            sl = StockLevel.query.filter_by(product_id=preorder.product_id, warehouse_id=preorder.warehouse_id).first()
            if not sl:
                sl = StockLevel(product_id=preorder.product_id, warehouse_id=preorder.warehouse_id, quantity=0, reserved_quantity=0)
                db.session.add(sl)
            sl.reserved_quantity = max((sl.reserved_quantity or 0) - preorder.quantity, 0)
            sl.quantity = (sl.quantity or 0) + preorder.quantity
            db.session.commit()
            flash("تم تنفيذ الحجز", "success")
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"فشل تنفيذ الحجز: {e}", "danger")
    else:
        flash("هذا الحجز تم تنفيذه مسبقاً", "info")
    return redirect(url_for("warehouse_bp.preorder_detail", preorder_id=preorder_id))


@warehouse_bp.route("/preorders/<int:preorder_id>/cancel", methods=["POST"], endpoint="preorder_cancel")
@login_required
@permission_required("delete_preorder")
def preorder_cancel(preorder_id):
    preorder = _get_or_404(PreOrder, preorder_id)
    ref = preorder.reference or str(preorder.id)
    if preorder.status in ("CANCELLED", "FULFILLED"):
        flash("لا يمكن إلغاء هذا الحجز", "warning")
        return redirect(url_for("warehouse_bp.preorder_detail", preorder_id=preorder.id))
    try:
        sl = StockLevel.query.filter_by(product_id=preorder.product_id, warehouse_id=preorder.warehouse_id).first()
        if sl:
            sl.reserved_quantity = max((sl.reserved_quantity or 0) - preorder.quantity, 0)
        refunded_val = getattr(PaymentStatus, "REFUNDED", "REFUNDED")
        refunded_val = refunded_val.value if hasattr(refunded_val, "value") else refunded_val
        for pay in preorder.payments:
            if hasattr(pay, "status"):
                pay.status = refunded_val
            pay.notes = f"استرداد عربون الحجز {ref}"
        preorder.status = "CANCELLED"
        db.session.commit()
        flash("تم إلغاء الحجز واسترداد العربون", "success")
    except SQLAlchemyError:
        db.session.rollback()
        flash("حدث خطأ أثناء إلغاء الحجز", "danger")
    return redirect(url_for("warehouse_bp.preorder_detail", preorder_id=preorder.id))

@warehouse_bp.route("/<int:warehouse_id>/pay", methods=["POST"], endpoint="pay_warehouse")
@login_required
@permission_required("manage_payments")
def pay_warehouse(warehouse_id):
    amount = request.form.get("amount", type=float)
    if not amount or amount <= 0:
        flash("قيمة غير صالحة", "danger")
        return redirect(url_for("warehouse_bp.detail", warehouse_id=warehouse_id))
    return redirect(url_for("payments.create_payment", entity_type="SUPPLIER", entity_id=warehouse_id, amount=amount))


@warehouse_bp.route("/api/add_customer", methods=["POST"], endpoint="api_add_customer")
@login_required
@permission_required("add_customer")
def api_add_customer():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "اسم العميل مطلوب"}), 400
    cust = Customer(name=name, phone=data.get("phone"), email=data.get("email"), address=data.get("address"), whatsapp=data.get("whatsapp"), category=data.get("category", "عادي"), is_active=True)
    db.session.add(cust)
    try:
        db.session.commit()
        return jsonify({"id": cust.id, "name": cust.name}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@warehouse_bp.route("/api/add_supplier", methods=["POST"], endpoint="api_add_supplier")
@login_required
@permission_required("add_supplier")
def api_add_supplier():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "اسم المورد مطلوب"}), 400
    sup = Supplier(name=name, is_local=data.get("is_local", True), identity_number=data.get("identity_number"), contact=data.get("contact"), phone=data.get("phone"), address=data.get("address"), notes=data.get("notes"), balance=0)
    db.session.add(sup)
    try:
        db.session.commit()
        return jsonify({"id": sup.id, "name": sup.name}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@warehouse_bp.route("/api/add_partner", methods=["POST"], endpoint="api_add_partner")
@login_required
@permission_required("add_partner")
def api_add_partner():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "اسم الشريك مطلوب"}), 400
    p = Partner(name=name, contact_info=data.get("contact_info"), identity_number=data.get("identity_number"), phone_number=data.get("phone_number"), address=data.get("address"), balance=0, share_percentage=data.get("share_percentage", 0))
    db.session.add(p)
    try:
        db.session.commit()
        return jsonify({"id": p.id, "name": p.name}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@warehouse_bp.route("/<int:id>/shipments/create", methods=["GET"], endpoint="create_warehouse_shipment")
@login_required
@permission_required("manage_inventory")
def create_warehouse_shipment(id):
    return redirect(url_for("shipments_bp.create_shipment", destination_id=id))
