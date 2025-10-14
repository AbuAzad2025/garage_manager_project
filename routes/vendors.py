# vendors.py - Vendors Management Routes
# Location: /garage_manager/routes/vendors.py
# Description: Vendor and supplier management routes

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from flask import abort, Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import joinedload
from extensions import db
from forms import PartnerForm, SupplierForm
from utils import permission_required, D, q2, archive_record, restore_record
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
    Expense,
    Sale,
    SaleLine,
    ServicePart,
    ServiceRequest,
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
    q = Supplier.query.filter(Supplier.is_archived == False)
    if s:
        term = f"%{s}%"
        q = q.filter(or_(Supplier.name.ilike(term), Supplier.phone.ilike(term), Supplier.identity_number.ilike(term)))
    suppliers = q.order_by(Supplier.name).all()
    
    # حساب الملخصات الإجمالية لجميع الموردين
    total_balance = 0.0
    total_purchases = 0.0
    total_payments = 0.0
    suppliers_with_debt = 0
    suppliers_with_credit = 0
    
    for supplier in suppliers:
        try:
            from models import fx_rate
            
            # حساب المشتريات (النفقات من المورد) - تحويل للشيقل
            expenses = Expense.query.filter(
                Expense.payee_type == 'SUPPLIER',
                Expense.payee_entity_id == supplier.id
            ).all()
            purchases_total = 0.0
            for e in expenses:
                amount = float(e.amount or 0)
                if e.currency and e.currency != 'ILS':
                    try:
                        rate = fx_rate(e.currency, 'ILS', e.date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                        else:
                            print(f"⚠️ WARNING: سعر صرف مفقود لـ {e.currency}/ILS في المصروف #{e.id}")
                    except ValueError as ve:
                        print(f"⚠️ ERROR: {str(ve)} - Expense #{e.id}")
                    except Exception as ex:
                        print(f"⚠️ ERROR: خطأ في تحويل العملة للمصروف #{e.id}: {str(ex)}")
                purchases_total += amount
            
            # حساب الدفعات للمورد - استخدام fx_rate_used
            payments = Payment.query.filter(
                Payment.supplier_id == supplier.id,
                Payment.direction == 'outgoing'
            ).all()
            payments_total = 0.0
            for p in payments:
                amount = float(p.total_amount or 0)
                if p.fx_rate_used:
                    amount *= float(p.fx_rate_used)
                elif p.currency and p.currency != 'ILS':
                    try:
                        rate = fx_rate(p.currency, 'ILS', p.payment_date, raise_on_missing=False)
                        if rate > 0:
                            amount = float(amount * float(rate))
                        else:
                            print(f"⚠️ WARNING: سعر صرف مفقود لـ {p.currency}/ILS في الدفعة #{p.id}")
                    except ValueError as ve:
                        print(f"⚠️ ERROR: {str(ve)} - Payment #{p.id}")
                    except Exception as ex:
                        print(f"⚠️ ERROR: خطأ في تحويل العملة للدفعة #{p.id}: {str(ex)}")
                payments_total += amount
            
            # الرصيد = المشتريات - المدفوعات (موجب يعني مستحق للمورد)
            balance = purchases_total - payments_total
            
            total_purchases += float(purchases_total)
            total_payments += float(payments_total)
            total_balance += balance
            
            if balance > 0:
                suppliers_with_debt += 1  # مستحق دفع للمورد
            elif balance < 0:
                suppliers_with_credit += 1  # المورد مدين لنا
                
        except Exception as e:
            print(f"Error calculating supplier {supplier.id} balance: {str(e)}")
            pass
    
    summary = {
        'total_suppliers': len(suppliers),
        'total_balance': total_balance,
        'total_purchases': total_purchases,
        'total_payments': total_payments,
        'suppliers_with_debt': suppliers_with_debt,
        'suppliers_with_credit': suppliers_with_credit,
        'average_balance': total_balance / len(suppliers) if suppliers else 0
    }
    
    return render_template(
        "vendors/suppliers/list.html",
        suppliers=suppliers,
        search=s,
        form=form,
        pay_url=url_for("payments.create_payment"),
        summary=summary,
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
    else:
        # إظهار أخطاء الـ validation
        if request.method == "POST":
            print(f"[WARNING] Supplier Form validation errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"خطأ في {field}: {error}", "danger")
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

    w_count = db.session.query(Warehouse.id).filter(Warehouse.supplier_id == id).count()
    pay_count = db.session.query(Payment.id).filter(Payment.supplier_id == id).count()
    stl_count = db.session.query(SupplierLoanSettlement.id).filter(SupplierLoanSettlement.supplier_id == id).count()

    if any([w_count, pay_count, stl_count]):
        parts = []
        if w_count: parts.append(f"مستودعات مرتبطة: {w_count}")
        if pay_count: parts.append(f"دفعات مرتبطة: {pay_count}")
        if stl_count: parts.append(f"تسويات قروض: {stl_count}")
        flash("لا يمكن حذف المورد لوجود مراجع مرتبطة — " + "، ".join(parts), "danger")
        return redirect(url_for("vendors_bp.suppliers_list"))

    try:
        db.session.delete(supplier)
        db.session.commit()
        flash("تم حذف المورد بنجاح", "success")
    except IntegrityError:
        db.session.rollback()
        flash("لا يمكن حذف المورد لوجود بيانات مرتبطة به. الرجاء فك الارتباط أولًا.", "danger")
    except SQLAlchemyError as e:
        db.session.rollback()
        flash("تعذّر تنفيذ العملية. الرجاء المحاولة لاحقًا.", "danger")
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

    # حركات التوريد/المرتجع من مستودعات العهدة (EXCHANGE) للمورد
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
        unit_cost = D(getattr(tx, "unit_cost", 0))
        used_fallback = False
        if unit_cost <= 0:
            pc = getattr(p, "purchase_price", None)
            if pc and D(pc) > 0:
                unit_cost = D(pc)
                used_fallback = True
            else:
                unit_cost = Decimal("0")

        amount = q2(unit_cost) * q2(qty)
        if used_fallback:
            row["notes"].add("تم التسعير من سعر شراء المنتج")
        if unit_cost == 0:
            row["notes"].add("سعر غير متوفر – راجع التسعير")

        d = getattr(tx, "created_at", None)
        dirv = (getattr(tx, "direction", "") or "").upper()
        
        # اسم المنتج للبيان
        prod_name = getattr(p, 'name', 'منتج') if p else 'منتج'

        # المدين = قيمة التوريد (يزيد ما ندين به للمورد)
        # الدائن = قيمة المرتجع/التسويات (تُخفّض ما ندين به)
        if dirv in {"IN", "PURCHASE", "CONSIGN_IN"}:
            statement = f"توريد {prod_name} - كمية: {qty}"
            entries.append({"date": d, "type": "PURCHASE", "ref": f"توريد قطع #{tx.id}", "statement": statement, "debit": amount, "credit": Decimal("0.00")})
            total_debit += amount
            row["qty_in"] += qty
            row["val_in"] += amount
        elif dirv in {"OUT", "RETURN", "CONSIGN_OUT"}:
            statement = f"مرتجع {prod_name} - كمية: {qty}"
            entries.append({"date": d, "type": "RETURN", "ref": f"مرتجع قطع #{tx.id}", "statement": statement, "debit": Decimal("0.00"), "credit": amount})
            total_credit += amount
            row["qty_out"] += qty
            row["val_out"] += amount
        elif dirv in {"SETTLEMENT", "ADJUST"}:
            statement = f"تسوية مخزون {prod_name} - كمية: {qty}"
            entries.append({"date": d, "type": "SETTLEMENT", "ref": f"تسوية مخزون #{tx.id}", "statement": statement, "debit": Decimal("0.00"), "credit": amount})
            total_credit += amount

    # الدفعات الخارجة للمورد (OUTGOING) — تُسجّل دائن لأنها تُخفّض ما ندين به
    pay_q = (
        db.session.query(Payment)
        .filter(
            Payment.supplier_id == supplier.id,
            Payment.status == PaymentStatus.COMPLETED.value,
            Payment.direction == PaymentDirection.OUT.value,
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
        # توليد البيان للدفعة
        payment_method = getattr(pmt, 'payment_method', 'نقداً')
        notes = getattr(pmt, 'notes', '') or ''
        statement = f"سداد {payment_method} للمورد"
        if notes:
            statement += f" - {notes[:30]}"
        entries.append({"date": d, "type": "PAYMENT", "ref": ref, "statement": statement, "debit": Decimal("0.00"), "credit": amt})
        total_credit += amt

    # تسويات القروض مع المورد — دائن أيضًا (تُخفّض الالتزام)
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
        # توليد البيان للتسوية
        loan = getattr(s, "loan", None)
        statement = "تسوية قرض مع المورد"
        if loan:
            product = getattr(loan, "product", None)
            if product:
                statement = f"تسوية قرض - {product.name}"
        entries.append({"date": d, "type": "SETTLEMENT", "ref": ref, "statement": statement, "debit": Decimal("0.00"), "credit": amt})
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

    # قيمة العهدة المتبقية عندنا (مخزون العهدة)
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
    q = Partner.query.filter(Partner.is_archived == False)
    if s:
        term = f"%{s}%"
        q = q.filter(or_(Partner.name.ilike(term), Partner.phone_number.ilike(term), Partner.identity_number.ilike(term)))
    partners = q.order_by(Partner.name).all()
    
    # حساب الأرصدة للشركاء
    for partner in partners:
        try:
            # balance_in_ils هو property، لا يمكن تعيينه مباشرة
            # سنستخدمه مباشرة في القالب
            pass
        except:
            pass
    
    return render_template(
        "vendors/partners/list.html",
        partners=partners,
        search=s,
        form=form,
        pay_url=url_for("payments.create_payment"),
    )

@vendors_bp.get("/partners/<int:partner_id>/statement", endpoint="partners_statement")
@login_required
@permission_required("manage_vendors")
def partners_statement(partner_id: int):
    partner = _get_or_404(Partner, partner_id)

    date_from_s = (request.args.get("from") or "").strip()
    date_to_s = (request.args.get("to") or "").strip()
    try:
        df = datetime.strptime(date_from_s, "%Y-%m-%d") if date_from_s else None
        dt = datetime.strptime(date_to_s, "%Y-%m-%d") if date_to_s else None
    except Exception:
        df, dt = None, None
    if dt:
        dt = dt + timedelta(days=1)

    q = (
        db.session.query(Payment)
        .filter(
            Payment.partner_id == partner.id,
            Payment.status == PaymentStatus.COMPLETED.value,
        )
    )
    if df:
        q = q.filter(Payment.payment_date >= df)
    if dt:
        q = q.filter(Payment.payment_date < dt)

    entries = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")

    for p in q.all():
        d = p.payment_date
        amt = q2(p.total_amount or 0)
        ref = p.reference or f"سند #{p.id}"
        dirv = getattr(p, "direction", None)
        
        # توليد البيان للدفعة
        payment_method = getattr(p, 'payment_method', 'نقداً')
        notes = getattr(p, 'notes', '') or ''
        
        # OUT => مدين (خارج منا للشريك)
        # IN => دائن (وارد منا من الشريك)
        if dirv == PaymentDirection.OUT.value:
            statement = f"سداد {payment_method} للشريك"
            if notes:
                statement += f" - {notes[:30]}"
            entries.append({"date": d, "type": "PAYMENT_OUT", "ref": ref, "statement": statement, "debit": amt, "credit": Decimal("0.00")})
            total_debit += amt
        else:
            statement = f"قبض {payment_method} من الشريك"
            if notes:
                statement += f" - {notes[:30]}"
            entries.append({"date": d, "type": "PAYMENT_IN", "ref": ref, "statement": statement, "debit": Decimal("0.00"), "credit": amt})
            total_credit += amt

    entries.sort(key=lambda e: (e["date"] or datetime.min, e["type"], e["ref"]))

    balance = Decimal("0.00")
    out = []
    for e in entries:
        d = q2(e["debit"])
        c = q2(e["credit"])
        balance += d - c
        out.append({**e, "debit": d, "credit": c, "balance": balance})

    return render_template(
        "vendors/partners/statement.html",
        partner=partner,
        ledger_entries=out,
        total_debit=total_debit,
        total_credit=total_credit,
        balance=balance,
        date_from=df if df else None,
        date_to=(dt - timedelta(days=1)) if dt else None,
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
    else:
        # إظهار أخطاء الـ validation
        if request.method == "POST":
            print(f"[WARNING] Partner Form validation errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"خطأ في {field}: {error}", "danger")
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
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("modal") == "1"
    try:
        linked_wh = (
            db.session.query(Warehouse)
            .filter(Warehouse.partner_id == partner.id)
            .all()
        )
        bad_wh = [
            w for w in linked_wh
            if getattr(w.warehouse_type, "value", w.warehouse_type) == WarehouseType.PARTNER.value
        ]
        if bad_wh:
            msg = "لا يمكن حذف الشريك لوجود مستودعات نوع PARTNER مرتبطة به."
            details = [{"id": w.id, "name": w.name} for w in bad_wh]
            if is_ajax:
                return jsonify({"success": False, "error": "has_partner_warehouses", "detail": msg, "warehouses": details}), 400
            else:
                names = "، ".join(f"#{w['id']} - {w['name']}" for w in details)
                flash(f"❌ {msg} المستودعات: {names}", "danger")
                return redirect(url_for("vendors_bp.partners_list"))
        db.session.delete(partner)
        db.session.commit()
        if is_ajax:
            return jsonify({"success": True}), 200
        flash("✅ تم حذف الشريك بنجاح", "success")
        return redirect(url_for("vendors_bp.partners_list"))
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({"success": False, "error": "delete_failed", "detail": str(e)}), 400
        flash(f"❌ خطأ أثناء حذف الشريك: {e}", "danger")
        return redirect(url_for("vendors_bp.partners_list"))


# ===== نظام التسوية الذكي =====

@vendors_bp.route("/suppliers/<int:supplier_id>/smart-settlement", methods=["GET"], endpoint="supplier_smart_settlement")
@login_required
@permission_required("manage_vendors")
def supplier_smart_settlement(supplier_id):
    """التسوية الذكية للمورد"""
    supplier = _get_or_404(Supplier, supplier_id)
    
    # الحصول على الفترة الزمنية
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    if date_from:
        date_from = datetime.fromisoformat(date_from)
    else:
        date_from = datetime(2024, 1, 1)
    
    if date_to:
        date_to = datetime.fromisoformat(date_to)
    else:
        date_to = datetime.utcnow()
    
    # حساب الرصيد الذكي
    balance_data = _calculate_smart_supplier_balance(supplier_id, date_from, date_to)
    
    # إنشاء object بسيط للتوافق مع القالب
    from types import SimpleNamespace
    ss = SimpleNamespace(
        id=None,  # لا يوجد id لأنها تسوية ذكية (غير محفوظة)
        supplier=supplier,
        from_date=date_from,
        to_date=date_to,
        currency=supplier.currency,
        total_gross=balance_data.get("incoming", {}).get("total", 0) if isinstance(balance_data, dict) else 0,
        total_due=balance_data.get("balance", {}).get("amount", 0) if isinstance(balance_data, dict) else 0,
        status="DRAFT",
        code=f"SS-SMART-{supplier_id}-{date_from.strftime('%Y%m%d')}",
        lines=[],
        created_at=date_from,
        updated_at=datetime.utcnow()
    )
    
    # استخدام settlement_preview بدلاً من smart_settlement (غير موجود)
    return render_template(
        "vendors/suppliers/settlement_preview.html",
        supplier=supplier,
        ss=ss,  # object بدلاً من dict
        entity=supplier,
        entity_type="supplier",
        balance_data=balance_data,
        date_from=date_from,
        date_to=date_to
    )


@vendors_bp.route("/partners/<int:partner_id>/smart-settlement", methods=["GET"], endpoint="partner_smart_settlement")
@login_required
@permission_required("manage_vendors")
def partner_smart_settlement(partner_id):
    """التسوية الذكية للشريك"""
    partner = _get_or_404(Partner, partner_id)
    
    # الحصول على الفترة الزمنية
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    if date_from:
        date_from = datetime.fromisoformat(date_from)
    else:
        date_from = datetime(2024, 1, 1)
    
    if date_to:
        date_to = datetime.fromisoformat(date_to)
    else:
        date_to = datetime.utcnow()
    
    # حساب الرصيد الذكي
    balance_data = _calculate_smart_partner_balance(partner_id, date_from, date_to)
    
    # إنشاء object بسيط للتوافق مع القالب
    from types import SimpleNamespace
    ps = SimpleNamespace(
        id=None,  # لا يوجد id لأنها تسوية ذكية (غير محفوظة)
        partner=partner,
        from_date=date_from,
        to_date=date_to,
        currency=partner.currency,
        total_gross=balance_data.get("incoming", {}).get("total", 0) if isinstance(balance_data, dict) else 0,
        total_due=balance_data.get("balance", {}).get("amount", 0) if isinstance(balance_data, dict) else 0,
        status="DRAFT",
        code=f"PS-SMART-{partner_id}-{date_from.strftime('%Y%m%d')}",
        lines=[],
        created_at=date_from,
        updated_at=datetime.utcnow()
    )
    
    # استخدام settlement_preview بدلاً من smart_settlement (غير موجود)
    return render_template(
        "vendors/partners/settlement_preview.html",
        partner=partner,
        ps=ps,  # object بدلاً من dict
        entity=partner,
        entity_type="partner",
        balance_data=balance_data,
        date_from=date_from,
        date_to=date_to
    )


def _calculate_smart_supplier_balance(supplier_id: int, date_from: datetime, date_to: datetime):
    """حساب الرصيد الذكي للمورد"""
    try:
        supplier = db.session.get(Supplier, supplier_id)
        if not supplier:
            return {"success": False, "error": "المورد غير موجود"}
        
        # 1. الوارد من المورد (المشتريات + القطع المعطاة له)
        incoming = _calculate_supplier_incoming(supplier_id, date_from, date_to)
        
        # 2. الصادر للمورد (المبيعات + القطع المأخوذة منه)
        outgoing = _calculate_supplier_outgoing(supplier_id, date_from, date_to)
        
        # 3. الدفعات
        payments_to_supplier = _calculate_payments_to_supplier(supplier_id, date_from, date_to)
        payments_from_supplier = _calculate_payments_from_supplier(supplier_id, date_from, date_to)
        
        # 4. حساب الرصيد النهائي
        total_incoming = incoming["total"] + payments_from_supplier
        total_outgoing = outgoing["total"] + payments_to_supplier
        
        balance = total_incoming - total_outgoing
        
        return {
            "success": True,
            "supplier": {
                "id": supplier.id,
                "name": supplier.name,
                "currency": supplier.currency
            },
            "period": {
                "from": date_from.isoformat(),
                "to": date_to.isoformat()
            },
            "incoming": {
                "purchases": incoming["purchases"],
                "products_given": incoming["products_given"],
                "payments_received": payments_from_supplier,
                "total": total_incoming
            },
            "outgoing": {
                "sales": outgoing["sales"],
                "products_taken": outgoing["products_taken"],
                "payments_made": payments_to_supplier,
                "total": total_outgoing
            },
            "balance": {
                "amount": balance,
                "direction": "للمورد" if balance > 0 else "على المورد" if balance < 0 else "متوازن",
                "currency": supplier.currency
            },
            "recommendation": _get_settlement_recommendation(balance, supplier.currency)
        }
        
    except Exception as e:
        return {"success": False, "error": f"خطأ في حساب رصيد المورد: {str(e)}"}


def _calculate_smart_partner_balance(partner_id: int, date_from: datetime, date_to: datetime):
    """حساب الرصيد الذكي للشريك"""
    try:
        partner = db.session.get(Partner, partner_id)
        if not partner:
            return {"success": False, "error": "الشريك غير موجود"}
        
        # 1. الوارد من الشريك
        incoming = _calculate_partner_incoming(partner_id, date_from, date_to)
        
        # 2. الصادر للشريك
        outgoing = _calculate_partner_outgoing(partner_id, date_from, date_to)
        
        # 3. الدفعات
        payments_to_partner = _calculate_payments_to_partner(partner_id, date_from, date_to)
        payments_from_partner = _calculate_payments_from_partner(partner_id, date_from, date_to)
        
        # 4. حساب الرصيد النهائي
        total_incoming = incoming["total"] + payments_from_partner
        total_outgoing = outgoing["total"] + payments_to_partner
        
        balance = total_incoming - total_outgoing
        
        return {
            "success": True,
            "partner": {
                "id": partner.id,
                "name": partner.name,
                "currency": partner.currency
            },
            "period": {
                "from": date_from.isoformat(),
                "to": date_to.isoformat()
            },
            "incoming": {
                "sales_share": incoming["sales_share"],
                "products_given": incoming["products_given"],
                "payments_received": payments_from_partner,
                "total": total_incoming
            },
            "outgoing": {
                "purchases_share": outgoing["purchases_share"],
                "products_taken": outgoing["products_taken"],
                "payments_made": payments_to_partner,
                "total": total_outgoing
            },
            "balance": {
                "amount": balance,
                "direction": "للشريك" if balance > 0 else "على الشريك" if balance < 0 else "متوازن",
                "currency": partner.currency
            },
            "recommendation": _get_settlement_recommendation(balance, partner.currency)
        }
        
    except Exception as e:
        return {"success": False, "error": f"خطأ في حساب رصيد الشريك: {str(e)}"}


def _calculate_supplier_incoming(supplier_id: int, date_from: datetime, date_to: datetime):
    """حساب الوارد من المورد"""
    # المشتريات (النفقات من نوع مشتريات)
    purchases = db.session.query(func.sum(Expense.amount)).filter(
        Expense.payee_type == "SUPPLIER",
        Expense.payee_entity_id == supplier_id,
        Expense.date >= date_from,
        Expense.date <= date_to
    ).scalar() or 0
    
    # القطع المعطاة للمورد (ExchangeTransaction مع اتجاه OUT)
    products_given = db.session.query(func.sum(ExchangeTransaction.quantity * ExchangeTransaction.unit_cost)).filter(
        ExchangeTransaction.supplier_id == supplier_id,
        ExchangeTransaction.direction == "OUT",
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to
    ).scalar() or 0
    
    return {
        "purchases": float(purchases),
        "products_given": float(products_given),
        "total": float(purchases + products_given)
    }


def _calculate_supplier_outgoing(supplier_id: int, date_from: datetime, date_to: datetime):
    """حساب الصادر للمورد"""
    # المبيعات للمورد (إذا كان عميل أيضاً)
    sales = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.customer_id == supplier_id,  # إذا كان المورد عميل أيضاً
        Sale.sale_date >= date_from,
        Sale.sale_date <= date_to
    ).scalar() or 0
    
    # القطع المأخوذة من المورد (ExchangeTransaction مع اتجاه IN)
    products_taken = db.session.query(func.sum(ExchangeTransaction.quantity * ExchangeTransaction.unit_cost)).filter(
        ExchangeTransaction.supplier_id == supplier_id,
        ExchangeTransaction.direction == "IN",
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to
    ).scalar() or 0
    
    return {
        "sales": float(sales),
        "products_taken": float(products_taken),
        "total": float(sales + products_taken)
    }


def _calculate_partner_incoming(partner_id: int, date_from: datetime, date_to: datetime):
    """حساب الوارد من الشريك"""
    # حصة الشريك من المبيعات (من خلال ServicePart)
    sales_share = db.session.query(func.sum(ServicePart.quantity * ServicePart.unit_price)).join(
        ServiceRequest, ServiceRequest.id == ServicePart.service_id
    ).filter(
        ServicePart.partner_id == partner_id,
        ServiceRequest.received_at >= date_from,
        ServiceRequest.received_at <= date_to
    ).scalar() or 0
    
    # القطع المعطاة للشريك
    products_given = db.session.query(func.sum(ExchangeTransaction.quantity * ExchangeTransaction.unit_cost)).filter(
        ExchangeTransaction.partner_id == partner_id,
        ExchangeTransaction.direction == "OUT",
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to
    ).scalar() or 0
    
    return {
        "sales_share": float(sales_share),
        "products_given": float(products_given),
        "total": float(sales_share + products_given)
    }


def _calculate_partner_outgoing(partner_id: int, date_from: datetime, date_to: datetime):
    """حساب الصادر للشريك"""
    # حصة الشريك من المشتريات
    purchases_share = db.session.query(func.sum(Expense.amount)).filter(
        Expense.partner_id == partner_id,
        Expense.date >= date_from,
        Expense.date <= date_to
    ).scalar() or 0
    
    # القطع المأخوذة من الشريك
    products_taken = db.session.query(func.sum(ExchangeTransaction.quantity * ExchangeTransaction.unit_cost)).filter(
        ExchangeTransaction.partner_id == partner_id,
        ExchangeTransaction.direction == "IN",
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to
    ).scalar() or 0
    
    return {
        "purchases_share": float(purchases_share),
        "products_taken": float(products_taken),
        "total": float(purchases_share + products_taken)
    }


def _calculate_payments_to_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    """حساب الدفعات المدفوعة للمورد"""
    amount = db.session.query(func.sum(Payment.total_amount)).filter(
        Payment.supplier_id == supplier_id,
        Payment.direction == "OUT",
        Payment.status == "COMPLETED",
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).scalar() or 0
    return float(amount)


def _calculate_payments_from_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    """حساب الدفعات المستلمة من المورد"""
    amount = db.session.query(func.sum(Payment.total_amount)).filter(
        Payment.supplier_id == supplier_id,
        Payment.direction == "INCOMING",
        Payment.status == "COMPLETED",
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).scalar() or 0
    return float(amount)


def _calculate_payments_to_partner(partner_id: int, date_from: datetime, date_to: datetime):
    """حساب الدفعات المدفوعة للشريك"""
    amount = db.session.query(func.sum(Payment.total_amount)).filter(
        Payment.partner_id == partner_id,
        Payment.direction == "OUT",
        Payment.status == "COMPLETED",
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).scalar() or 0
    return float(amount)


def _calculate_payments_from_partner(partner_id: int, date_from: datetime, date_to: datetime):
    """حساب الدفعات المستلمة من الشريك"""
    amount = db.session.query(func.sum(Payment.total_amount)).filter(
        Payment.partner_id == partner_id,
        Payment.direction == "INCOMING",
        Payment.status == "COMPLETED",
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).scalar() or 0
    return float(amount)


def _get_settlement_recommendation(balance: float, currency: str):
    """اقتراح التسوية"""
    if abs(balance) < 0.01:  # متوازن
        return {
            "action": "متوازن",
            "message": "لا توجد تسوية مطلوبة",
            "amount": 0
        }
    elif balance > 0:  # الباقي له
        return {
            "action": "دفع",
            "message": f"يجب دفع {abs(balance):.2f} {currency} للمورد/الشريك",
            "amount": abs(balance),
            "direction": "OUTGOING"
        }
    else:  # الباقي عليه
        return {
            "action": "قبض",
            "message": f"يجب قبض {abs(balance):.2f} {currency} من المورد/الشريك",
            "amount": abs(balance),
            "direction": "INCOMING"
        }

@vendors_bp.route("/suppliers/archive/<int:supplier_id>", methods=["POST"])
@login_required
@permission_required("manage_vendors")
def archive_supplier(supplier_id):
    print(f"🔍 [SUPPLIER ARCHIVE] بدء أرشفة المورد رقم: {supplier_id}")
    print(f"🔍 [SUPPLIER ARCHIVE] المستخدم: {current_user.username if current_user else 'غير معروف'}")
    print(f"🔍 [SUPPLIER ARCHIVE] البيانات المرسلة: {dict(request.form)}")
    
    try:
        from models import Archive
        
        supplier = Supplier.query.get_or_404(supplier_id)
        print(f"✅ [SUPPLIER ARCHIVE] تم العثور على المورد: {supplier.name}")
        
        reason = request.form.get('reason', 'أرشفة تلقائية')
        print(f"📝 [SUPPLIER ARCHIVE] سبب الأرشفة: {reason}")
        
        archive_record(supplier, reason, current_user.id)
        flash(f'تم أرشفة المورد {supplier.name} بنجاح', 'success')
        return redirect(url_for('vendors_bp.suppliers_list'))
        
    except Exception as e:
        print(f"❌ [SUPPLIER ARCHIVE] خطأ في أرشفة المورد: {str(e)}")
        print(f"❌ [SUPPLIER ARCHIVE] نوع الخطأ: {type(e).__name__}")
        import traceback
        print(f"❌ [SUPPLIER ARCHIVE] تفاصيل الخطأ: {traceback.format_exc()}")
        
        db.session.rollback()
        flash(f'خطأ في أرشفة المورد: {str(e)}', 'error')
        return redirect(url_for('vendors_bp.suppliers_list'))

@vendors_bp.route("/partners/archive/<int:partner_id>", methods=["POST"])
@login_required
@permission_required("manage_vendors")
def archive_partner(partner_id):
    """أرشفة شريك"""
    print(f"🔍 [PARTNER ARCHIVE] بدء أرشفة الشريك رقم: {partner_id}")
    print(f"🔍 [PARTNER ARCHIVE] المستخدم: {current_user.username if current_user else 'غير معروف'}")
    print(f"🔍 [PARTNER ARCHIVE] البيانات المرسلة: {dict(request.form)}")
    
    try:
        from models import Archive
        
        partner = Partner.query.get_or_404(partner_id)
        print(f"✅ [PARTNER ARCHIVE] تم العثور على الشريك: {partner.name}")
        
        reason = request.form.get('reason', 'أرشفة تلقائية')
        print(f"📝 [PARTNER ARCHIVE] سبب الأرشفة: {reason}")
        
        archive_record(partner, reason, current_user.id)
        
        flash(f'تم أرشفة الشريك {partner.name} بنجاح', 'success')
        print(f"🎉 [PARTNER ARCHIVE] تمت العملية بنجاح - إعادة توجيه...")
        return redirect(url_for('vendors_bp.partners_list'))
        
    except Exception as e:
        print(f"❌ [PARTNER ARCHIVE] خطأ في أرشفة الشريك: {str(e)}")
        print(f"❌ [PARTNER ARCHIVE] نوع الخطأ: {type(e).__name__}")
        import traceback
        print(f"❌ [PARTNER ARCHIVE] تفاصيل الخطأ: {traceback.format_exc()}")
        
        db.session.rollback()
        flash(f'خطأ في أرشفة الشريك: {str(e)}', 'error')
        return redirect(url_for('vendors_bp.partners_list'))

@vendors_bp.route("/suppliers/restore/<int:supplier_id>", methods=["POST"])
@login_required
@permission_required("manage_vendors")
def restore_supplier(supplier_id):
    """استعادة مورد"""
    print(f"🔍 [SUPPLIER RESTORE] بدء استعادة المورد رقم: {supplier_id}")
    print(f"🔍 [SUPPLIER RESTORE] المستخدم: {current_user.username if current_user else 'غير معروف'}")
    
    try:
        supplier = Supplier.query.get_or_404(supplier_id)
        print(f"✅ [SUPPLIER RESTORE] تم العثور على المورد: {supplier.name}")
        
        if not supplier.is_archived:
            flash('المورد غير مؤرشف', 'warning')
            return redirect(url_for('vendors_bp.suppliers_list'))
        
        # البحث عن الأرشيف
        from models import Archive
        archive = Archive.query.filter_by(
            record_type='suppliers',
            record_id=supplier_id
        ).first()
        
        if archive:
            print(f"✅ [SUPPLIER RESTORE] تم العثور على الأرشيف: {archive.id}")
            restore_record(archive.id)
            print(f"✅ [SUPPLIER RESTORE] تم استعادة المورد بنجاح")
        
        flash(f'تم استعادة المورد {supplier.name} بنجاح', 'success')
        print(f"🎉 [SUPPLIER RESTORE] تمت العملية بنجاح - إعادة توجيه...")
        return redirect(url_for('vendors_bp.suppliers_list'))
        
    except Exception as e:
        print(f"❌ [SUPPLIER RESTORE] خطأ في استعادة المورد: {str(e)}")
        print(f"❌ [SUPPLIER RESTORE] نوع الخطأ: {type(e).__name__}")
        import traceback
        print(f"❌ [SUPPLIER RESTORE] تفاصيل الخطأ: {traceback.format_exc()}")
        
        db.session.rollback()
        flash(f'خطأ في استعادة المورد: {str(e)}', 'error')
        return redirect(url_for('vendors_bp.suppliers_list'))

@vendors_bp.route("/partners/restore/<int:partner_id>", methods=["POST"])
@login_required
@permission_required("manage_vendors")
def restore_partner(partner_id):
    """استعادة شريك"""
    print(f"🔍 [PARTNER RESTORE] بدء استعادة الشريك رقم: {partner_id}")
    print(f"🔍 [PARTNER RESTORE] المستخدم: {current_user.username if current_user else 'غير معروف'}")
    
    try:
        partner = Partner.query.get_or_404(partner_id)
        print(f"✅ [PARTNER RESTORE] تم العثور على الشريك: {partner.name}")
        
        if not partner.is_archived:
            flash('الشريك غير مؤرشف', 'warning')
            return redirect(url_for('vendors_bp.partners_list'))
        
        # البحث عن الأرشيف
        from models import Archive
        archive = Archive.query.filter_by(
            record_type='partners',
            record_id=partner_id
        ).first()
        
        if archive:
            print(f"✅ [PARTNER RESTORE] تم العثور على الأرشيف: {archive.id}")
            restore_record(archive.id)
            print(f"✅ [PARTNER RESTORE] تم استعادة الشريك بنجاح")
        
        flash(f'تم استعادة الشريك {partner.name} بنجاح', 'success')
        print(f"🎉 [PARTNER RESTORE] تمت العملية بنجاح - إعادة توجيه...")
        return redirect(url_for('vendors_bp.partners_list'))
        
    except Exception as e:
        print(f"❌ [PARTNER RESTORE] خطأ في استعادة الشريك: {str(e)}")
        print(f"❌ [PARTNER RESTORE] نوع الخطأ: {type(e).__name__}")
        import traceback
        print(f"❌ [PARTNER RESTORE] تفاصيل الخطأ: {traceback.format_exc()}")
        
        db.session.rollback()
        flash(f'خطأ في استعادة الشريك: {str(e)}', 'error')
        return redirect(url_for('vendors_bp.partners_list'))