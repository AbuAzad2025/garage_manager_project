from datetime import datetime, timedelta
from decimal import Decimal

from flask import abort, Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required
from flask_wtf import FlaskForm
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from extensions import db
from forms import PartnerForm, SupplierForm
from utils import permission_required
from models import (
    ExchangeTransaction,
    Partner,
    Payment,
    PaymentDirection,
    PaymentStatus,
    Product,
    StockLevel,
    Supplier,
    SupplierLoanSettlement,
    Warehouse,
    WarehouseType,
)


class CSRFProtectForm(FlaskForm):
    pass


vendors_bp = Blueprint("vendors_bp", __name__, url_prefix="/vendors")


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


@vendors_bp.route("/suppliers", methods=["GET"], endpoint="suppliers_list")
@login_required
@permission_required("manage_vendors")
def suppliers_list():
    form = CSRFProtectForm()
    s = (request.args.get("search") or "").strip()
    q = Supplier.query
    if s:
        term = f"%{s}%"
        q = q.filter(or_(Supplier.name.ilike(term), Supplier.phone.ilike(term), Supplier.identity_number.ilike(term)))
    suppliers = q.order_by(Supplier.name).all()
    return render_template(
        "vendors/suppliers/list.html",
        suppliers=suppliers,
        search=s,
        form=form,
        pay_url=url_for("payments.create_payment"),
    )


@vendors_bp.route("/suppliers/new", methods=["GET", "POST"], endpoint="suppliers_create")
@login_required
@permission_required("manage_vendors")
def suppliers_create():
    form = SupplierForm()
    if form.validate_on_submit():
        supplier = Supplier()
        form.apply_to(supplier)
        db.session.add(supplier)
        try:
            db.session.commit()
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("modal") == "1":
                return jsonify({"success": True, "id": supplier.id, "name": supplier.name})
            flash("✅ تم إضافة المورد بنجاح", "success")
            return redirect(url_for("vendors_bp.suppliers_list"))
        except SQLAlchemyError as e:
            db.session.rollback()
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("modal") == "1":
                return jsonify({"success": False, "errors": {"__all__": [str(e)]}}), 400
            flash(f"❌ خطأ أثناء إضافة المورد: {e}", "danger")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("modal") == "1":
        html = render_template("vendors/suppliers/form.html", form=form, supplier=None)
        return jsonify({"success": True, "html": html})
    return render_template("vendors/suppliers/form.html", form=form, supplier=None)


@vendors_bp.route("/suppliers/<int:id>/edit", methods=["GET", "POST"], endpoint="suppliers_edit")
@login_required
@permission_required("manage_vendors")
def suppliers_edit(id):
    supplier = _get_or_404(Supplier, id)
    form = SupplierForm(obj=supplier)
    form.obj_id = supplier.id
    if form.validate_on_submit():
        form.apply_to(supplier)
        try:
            db.session.commit()
            flash("✅ تم تحديث المورد بنجاح", "success")
            return redirect(url_for("vendors_bp.suppliers_list"))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"❌ خطأ أثناء تحديث المورد: {e}", "danger")
    return render_template("vendors/suppliers/form.html", form=form, supplier=supplier)


@vendors_bp.route("/suppliers/<int:id>/delete", methods=["POST"], endpoint="suppliers_delete")
@login_required
@permission_required("manage_vendors")
def suppliers_delete(id):
    supplier = _get_or_404(Supplier, id)
    try:
        db.session.delete(supplier)
        db.session.commit()
        flash("✅ تم حذف المورد بنجاح", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"❌ خطأ أثناء حذف المورد: {e}", "danger")
    return redirect(url_for("vendors_bp.suppliers_list"))


@vendors_bp.get("/suppliers/<int:supplier_id>/statement", endpoint="suppliers_statement")
@login_required
@permission_required("manage_vendors")
def suppliers_statement(supplier_id: int):
    supplier = _get_or_404(Supplier, supplier_id)
    date_from_s = (request.args.get("from") or "").strip()
    date_to_s = (request.args.get("to") or "").strip()
    try:
        df = datetime.strptime(date_from_s, "%Y-%m-%d") if date_from_s else None
        dt = datetime.strptime(date_to_s, "%Y-%m-%d") if date_to_s else None
    except Exception:
        df, dt = None, None
    if dt:
        dt = dt + timedelta(days=1)

    def q2(x):
        try:
            return Decimal(str(x or 0)).quantize(Decimal("0.01"))
        except Exception:
            return Decimal("0.00")

    tx_query = (
        db.session.query(ExchangeTransaction)
        .join(Warehouse, Warehouse.id == ExchangeTransaction.warehouse_id)
        .options(joinedload(ExchangeTransaction.product))
        .filter(
            Warehouse.warehouse_type == WarehouseType.EXCHANGE.value,
            Warehouse.supplier_id == supplier.id,
        )
    )
    if df:
        tx_query = tx_query.filter(ExchangeTransaction.created_at >= df)
    if dt:
        tx_query = tx_query.filter(ExchangeTransaction.created_at < dt)
    txs = tx_query.all()

    entries = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")

    per_product = {}

    def _pp(pid):
        if pid not in per_product:
            per_product[pid] = {
                "product": None,
                "qty_in": 0,
                "qty_out": 0,
                "qty_paid": 0,
                "qty_unpaid": 0,
                "val_in": Decimal("0.00"),
                "val_out": Decimal("0.00"),
                "val_paid": Decimal("0.00"),
                "val_unpaid": Decimal("0.00"),
                "notes": set(),
            }
        return per_product[pid]

    for tx in txs:
        p = tx.product
        pid = getattr(p, "id", None)
        row = _pp(pid)
        if row["product"] is None:
            row["product"] = p
        qty = int(tx.quantity or 0)
        unit_cost = tx.unit_cost
        used_fallback = False
        if not unit_cost or unit_cost <= 0:
            pc = getattr(p, "purchase_price", None)
            if pc and pc > 0:
                unit_cost = pc
                used_fallback = True
            else:
                unit_cost = 0
        amount = q2(unit_cost) * q2(qty)
        if used_fallback:
            row["notes"].add("تم التسعير من سعر شراء المنتج")
        if unit_cost == 0:
            row["notes"].add("سعر غير متوفر – راجع التسعير")
        d = getattr(tx, "created_at", None)
        dirv = (getattr(tx, "direction", "") or "").upper()
        if dirv in {"IN", "PURCHASE", "CONSIGN_IN"}:
            entries.append({"date": d, "type": "PURCHASE", "ref": f"توريد قطع #{tx.id}", "debit": amount, "credit": Decimal("0.00")})
            total_debit += amount
            row["qty_in"] += qty
            row["val_in"] += amount
        elif dirv in {"OUT", "RETURN", "CONSIGN_OUT"}:
            entries.append({"date": d, "type": "RETURN", "ref": f"مرتجع قطع #{tx.id}", "debit": Decimal("0.00"), "credit": amount})
            total_credit += amount
            row["qty_out"] += qty
            row["val_out"] += amount
        elif dirv in {"SETTLEMENT", "ADJUST"}:
            entries.append({"date": d, "type": "SETTLEMENT", "ref": f"تسوية مخزون #{tx.id}", "debit": Decimal("0.00"), "credit": amount})
            total_credit += amount

    pay_q = (
        db.session.query(Payment)
        .filter(
            Payment.supplier_id == supplier.id,
            Payment.status == PaymentStatus.COMPLETED.value,
            Payment.direction == PaymentDirection.OUTGOING.value,
        )
    )
    if df:
        pay_q = pay_q.filter(Payment.payment_date >= df)
    if dt:
        pay_q = pay_q.filter(Payment.payment_date < dt)
    for pmt in pay_q.all():
        d = pmt.payment_date
        amt = q2(pmt.total_amount)
        ref = pmt.reference or f"دفعة #{pmt.id}"
        entries.append({"date": d, "type": "PAYMENT", "ref": ref, "debit": Decimal("0.00"), "credit": amt})
        total_credit += amt

    stl_q = (
        db.session.query(SupplierLoanSettlement)
        .options(joinedload(SupplierLoanSettlement.loan))
        .filter(SupplierLoanSettlement.supplier_id == supplier.id)
    )
    if df:
        stl_q = stl_q.filter(SupplierLoanSettlement.settlement_date >= df)
    if dt:
        stl_q = stl_q.filter(SupplierLoanSettlement.settlement_date < dt)
    for s in stl_q.all():
        d = s.settlement_date
        amt = q2(s.settled_price)
        ref = f"تسوية قرض #{s.loan_id or s.id}"
        entries.append({"date": d, "type": "SETTLEMENT", "ref": ref, "debit": Decimal("0.00"), "credit": amt})
        total_credit += amt
        pid = getattr(getattr(s, "loan", None), "product_id", None)
        if pid in per_product:
            per_product[pid]["qty_paid"] += 1
            per_product[pid]["val_paid"] += amt

    entries.sort(key=lambda e: (e["date"] or datetime.min, e["type"], e["ref"]))
    balance = Decimal("0.00")
    out = []
    for e in entries:
        d = q2(e["debit"])
        c = q2(e["credit"])
        balance += d - c
        out.append({**e, "debit": d, "credit": c, "balance": balance})

    ex_ids = [
        wid
        for (wid,) in db.session.query(Warehouse.id)
        .filter(Warehouse.supplier_id == supplier.id, Warehouse.warehouse_type == WarehouseType.EXCHANGE.value)
        .all()
    ]
    consignment_value = Decimal("0.00")
    if ex_ids:
        rows = (
            db.session.query(
                Product.id.label("pid"),
                Product.name,
                func.coalesce(func.sum(StockLevel.quantity), 0).label("qty"),
                func.coalesce(Product.purchase_price, 0.0).label("unit_cost"),
            )
            .join(Product, Product.id == StockLevel.product_id)
            .filter(StockLevel.warehouse_id.in_(ex_ids), StockLevel.quantity > 0)
            .group_by(Product.id, Product.name, Product.purchase_price)
            .order_by(Product.name.asc())
            .all()
        )
        for pid, name, qty, unit_cost in rows:
            qty_i = int(qty or 0)
            unit_cost_d = q2(unit_cost)
            value = unit_cost_d * q2(qty_i)
            consignment_value += value
            r = _pp(pid)
            if r["product"] is None:
                r["product"] = {"name": name}
            r["qty_unpaid"] = qty_i
            r["val_unpaid"] = value

    return render_template(
        "vendors/suppliers/statement.html",
        supplier=supplier,
        ledger_entries=out,
        total_debit=total_debit,
        total_credit=total_credit,
        balance=balance,
        consignment_value=consignment_value,
        per_product=per_product,
        date_from=df if df else None,
        date_to=(dt - timedelta(days=1)) if dt else None,
    )


@vendors_bp.route("/partners", methods=["GET"], endpoint="partners_list")
@login_required
@permission_required("manage_vendors")
def partners_list():
    form = CSRFProtectForm()
    s = (request.args.get("search") or "").strip()
    q = Partner.query
    if s:
        term = f"%{s}%"
        q = q.filter(or_(Partner.name.ilike(term), Partner.phone_number.ilike(term), Partner.identity_number.ilike(term)))
    partners = q.order_by(Partner.name).all()
    return render_template(
        "vendors/partners/list.html",
        partners=partners,
        search=s,
        form=form,
        pay_url=url_for("payments.create_payment"),
    )


@vendors_bp.route("/partners/new", methods=["GET", "POST"], endpoint="partners_create")
@login_required
@permission_required("manage_vendors")
def partners_create():
    form = PartnerForm()
    if form.validate_on_submit():
        partner = Partner()
        form.apply_to(partner)
        db.session.add(partner)
        try:
            db.session.commit()
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("modal") == "1":
                return jsonify({"success": True, "id": partner.id, "name": partner.name})
            flash("✅ تم إضافة الشريك بنجاح", "success")
            return redirect(url_for("vendors_bp.partners_list"))
        except SQLAlchemyError as e:
            db.session.rollback()
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("modal") == "1":
                return jsonify({"success": False, "errors": {"__all__": [str(e)]}}), 400
            flash(f"❌ خطأ أثناء إضافة الشريك: {e}", "danger")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("modal") == "1":
        html = render_template("vendors/partners/form.html", form=form, partner=None)
        return jsonify({"success": True, "html": html})
    return render_template("vendors/partners/form.html", form=form, partner=None)


@vendors_bp.route("/partners/<int:id>/edit", methods=["GET", "POST"], endpoint="partners_edit")
@login_required
@permission_required("manage_vendors")
def partners_edit(id):
    partner = _get_or_404(Partner, id)
    form = PartnerForm(obj=partner)
    form.obj_id = partner.id
    if form.validate_on_submit():
        form.apply_to(partner)
        try:
            db.session.commit()
            flash("✅ تم تحديث الشريك بنجاح", "success")
            return redirect(url_for("vendors_bp.partners_list"))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"❌ خطأ أثناء تحديث الشريك: {e}", "danger")
    return render_template("vendors/partners/form.html", form=form, partner=partner)


@vendors_bp.route("/partners/<int:id>/delete", methods=["POST"], endpoint="partners_delete")
@login_required
@permission_required("manage_vendors")
def partners_delete(id):
    partner = _get_or_404(Partner, id)
    try:
        db.session.delete(partner)
        db.session.commit()
        flash("✅ تم حذف الشريك بنجاح", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"❌ خطأ أثناء حذف الشريك: {e}", "danger")
    return redirect(url_for("vendors_bp.partners_list"))
