
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from flask import abort, Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from sqlalchemy import func, or_, and_
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import joinedload
from extensions import db
from forms import PartnerForm, SupplierForm
import utils
from utils import D, q2, archive_record, restore_record
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
    ServiceStatus,
    _find_partner_share_percentage,
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
# @permission_required("manage_vendors")  # Commented out
def suppliers_list():
    form = CSRFProtectForm()
    s = (request.args.get("search") or "").strip()
    q = Supplier.query.filter(Supplier.is_archived == False)
    if s:
        term = f"%{s}%"
        q = q.filter(or_(Supplier.name.ilike(term), Supplier.phone.ilike(term), Supplier.identity_number.ilike(term)))
    suppliers = q.order_by(Supplier.name).all()
    
    # ✅ حساب الملخصات الإجمالية لجميع الموردين - موحد من balance_in_ils
    total_balance = 0.0
    total_debit = 0.0
    total_credit = 0.0
    suppliers_with_debt = 0
    suppliers_with_credit = 0
    
    for supplier in suppliers:
        balance = float(supplier.balance_in_ils or 0)
        total_balance += balance
        
        if balance > 0:
            suppliers_with_debt += 1
            total_debit += balance
        elif balance < 0:
            suppliers_with_credit += 1
            total_credit += abs(balance)
    
    summary = {
        'total_suppliers': len(suppliers),
        'total_balance': total_balance,
        'total_debit': total_debit,  # ✅ إضافة
        'total_credit': total_credit,  # ✅ إضافة
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
# @permission_required("manage_vendors")  # Commented out
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
# @permission_required("manage_vendors")  # Commented out
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
# @permission_required("manage_vendors")  # Commented out
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
# @permission_required("manage_vendors")  # Commented out
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
    # البحث مباشرة في ExchangeTransaction.supplier_id
    tx_query = (
        db.session.query(ExchangeTransaction)
        .options(joinedload(ExchangeTransaction.product))
        .filter(
            ExchangeTransaction.supplier_id == supplier.id,
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

        # جمع تفاصيل المنتج
        item_detail = {
            "product": prod_name,
            "qty": qty,
            "unit_cost": float(unit_cost),
            "total": float(amount),
            "direction": dirv,
            "tx_id": tx.id
        }
        
        # المدين = قيمة التوريد (يزيد ما ندين به للمورد)
        # الدائن = قيمة المرتجع/التسويات (تُخفّض ما ندين به)
        if dirv in {"IN", "PURCHASE", "CONSIGN_IN"}:
            statement = f"توريد {prod_name} - كمية: {qty}"
            entries.append({
                "date": d, 
                "type": "PURCHASE", 
                "ref": f"توريد قطع #{tx.id}", 
                "statement": statement, 
                "debit": amount, 
                "credit": Decimal("0.00"),
                "details": [item_detail],
                "has_details": True
            })
            total_debit += amount
            row["qty_in"] += qty
            row["val_in"] += amount
        elif dirv in {"OUT", "RETURN", "CONSIGN_OUT"}:
            statement = f"مرتجع {prod_name} - كمية: {qty}"
            entries.append({
                "date": d, 
                "type": "RETURN", 
                "ref": f"مرتجع قطع #{tx.id}", 
                "statement": statement, 
                "debit": Decimal("0.00"), 
                "credit": amount,
                "details": [item_detail],
                "has_details": True
            })
            total_credit += amount
            row["qty_out"] += qty
            row["val_out"] += amount
        elif dirv in {"SETTLEMENT", "ADJUST"}:
            statement = f"تسوية مخزون {prod_name} - كمية: {qty}"
            entries.append({
                "date": d, 
                "type": "SETTLEMENT", 
                "ref": f"تسوية مخزون #{tx.id}", 
                "statement": statement, 
                "debit": Decimal("0.00"), 
                "credit": amount,
                "details": [item_detail],
                "has_details": True
            })
            total_credit += amount

    # المبيعات للمورد (كعميل) — تُسجّل دائن (تُخفّض ما ندين به)
    sales_data = []
    if supplier.customer_id:
        from models import Sale, SaleStatus, SaleLine, Product
        sale_q = (
            db.session.query(Sale)
            .options(joinedload(Sale.lines).joinedload(SaleLine.product))
            .filter(
                Sale.customer_id == supplier.customer_id,
                Sale.status == SaleStatus.CONFIRMED.value,
            )
        )
        if df:
            sale_q = sale_q.filter(Sale.sale_date >= df)
        if dt:
            sale_q = sale_q.filter(Sale.sale_date < dt)
        
        for sale in sale_q.all():
            d = sale.sale_date
            amt = q2(sale.total_amount or 0)
            ref = sale.sale_number or f"فاتورة #{sale.id}"
            
            # جمع بنود الفاتورة
            items = []
            for line in (sale.lines or []):
                prod_name = line.product.name if line.product else "منتج"
                items.append({
                    "product": prod_name,
                    "qty": line.quantity,
                    "price": float(line.unit_price or 0),
                    "total": float(q2(line.quantity * line.unit_price))
                })
            
            statement = f"مبيعات للمورد - {ref}"
            entries.append({
                "date": d, 
                "type": "SALE", 
                "ref": ref, 
                "statement": statement, 
                "debit": Decimal("0.00"), 
                "credit": amt,
                "details": items,
                "has_details": len(items) > 0
            })
            total_credit += amt
            sales_data.append({"ref": ref, "date": d, "amount": amt, "items": items})
    
    # الصيانة للمورد (كعميل) — تُسجّل دائن
    services_data = []
    if supplier.customer_id:
        from models import ServiceRequest, ServicePart, ServiceTask
        service_q = (
            db.session.query(ServiceRequest)
            .options(joinedload(ServiceRequest.parts), joinedload(ServiceRequest.tasks))
            .filter(
                ServiceRequest.customer_id == supplier.customer_id,
                ServiceRequest.status == ServiceStatus.COMPLETED.value,
            )
        )
        if df:
            service_q = service_q.filter(ServiceRequest.received_at >= df)
        if dt:
            service_q = service_q.filter(ServiceRequest.received_at < dt)
        
        for service in service_q.all():
            d = service.received_at
            amt = q2(service.total_amount or 0)
            ref = service.service_number or f"صيانة #{service.id}"
            
            # جمع قطع الغيار والخدمات
            items = []
            for part in (service.parts or []):
                items.append({
                    "type": "قطعة",
                    "name": part.part.name if part.part else "قطعة غيار",
                    "qty": part.quantity,
                    "price": float(part.unit_price or 0),
                    "total": float(q2(part.quantity * part.unit_price))
                })
            for task in (service.tasks or []):
                items.append({
                    "type": "خدمة",
                    "name": task.description or "خدمة",
                    "qty": task.quantity or 1,
                    "price": float(task.unit_price or 0),
                    "total": float(q2((task.quantity or 1) * task.unit_price))
                })
            
            statement = f"صيانة للمورد - {ref}"
            entries.append({
                "date": d, 
                "type": "SERVICE", 
                "ref": ref, 
                "statement": statement, 
                "debit": Decimal("0.00"), 
                "credit": amt,
                "details": items,
                "has_details": len(items) > 0
            })
            total_credit += amt
            services_data.append({"ref": ref, "date": d, "amount": amt, "items": items})
    
    # الحجوزات المسبقة للمورد (كعميل) — تُسجّل دائن
    preorders_data = []
    if supplier.customer_id:
        from models import PreOrder
        preorder_q = (
            db.session.query(PreOrder)
            .options(joinedload(PreOrder.product))
            .filter(
                PreOrder.customer_id == supplier.customer_id,
                PreOrder.status.in_(['CONFIRMED', 'COMPLETED']),
            )
        )
        if df:
            preorder_q = preorder_q.filter(PreOrder.preorder_date >= df)
        if dt:
            preorder_q = preorder_q.filter(PreOrder.preorder_date < dt)
        
        for preorder in preorder_q.all():
            d = preorder.preorder_date
            amt = q2(preorder.total_amount or 0)
            ref = f"حجز #{preorder.id}"
            prod_name = preorder.product.name if preorder.product else "منتج"
            
            items = [{
                "product": prod_name,
                "qty": preorder.quantity,
                "price": float(preorder.unit_price or 0),
                "total": float(amt)
            }]
            
            statement = f"حجز مسبق للمورد - {ref}"
            entries.append({
                "date": d, 
                "type": "PREORDER", 
                "ref": ref, 
                "statement": statement, 
                "debit": Decimal("0.00"), 
                "credit": amt,
                "details": items,
                "has_details": True
            })
            total_credit += amt
            preorders_data.append({"ref": ref, "date": d, "amount": amt, "items": items})

    # ✅ جميع الدفعات (IN و OUT) للمورد
    pay_q = (
        db.session.query(Payment)
        .filter(
            Payment.supplier_id == supplier.id,
            Payment.status.in_([PaymentStatus.COMPLETED.value, PaymentStatus.PENDING.value]),
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
        
        # فحص حالة الدفعة
        payment_status = getattr(pmt, 'status', 'COMPLETED')
        is_bounced = payment_status in ['BOUNCED', 'FAILED', 'REJECTED']
        is_pending = payment_status == 'PENDING'
        
        # استخراج طريقة الدفع
        method_value = getattr(pmt, 'method', 'cash')
        if hasattr(method_value, 'value'):
            method_value = method_value.value
        method_raw = str(method_value).lower()
        
        method_arabic = {
            'cash': 'نقداً',
            'card': 'بطاقة',
            'cheque': 'شيك',
            'bank': 'تحويل بنكي',
            'online': 'إلكتروني'
        }.get(method_raw, method_raw)
        
        # تفاصيل الدفعة
        payment_details = {
            'method': method_arabic,
            'method_raw': method_raw,
            'check_number': getattr(pmt, 'check_number', None) if method_raw == 'cheque' else None,
            'check_bank': getattr(pmt, 'check_bank', None),
            'check_due_date': getattr(pmt, 'check_due_date', None) if method_raw == 'cheque' else None,
            'receiver_name': getattr(pmt, 'receiver_name', None) or '',
            'status': payment_status,
            'is_bounced': is_bounced,
            'is_pending': is_pending
        }
        
        # البيان
        notes = getattr(pmt, 'notes', '') or ''
        
        # ✅ استخراج Direction value
        direction_value = pmt.direction.value if hasattr(pmt.direction, 'value') else str(pmt.direction)
        is_out = direction_value == 'OUT'  # من الشركة للمورد
        
        # البيان حسب Direction
        if is_out:
            if is_bounced:
                statement = f"❌ شيك مرفوض - {method_arabic} للمورد"
            elif is_pending and method_raw == 'cheque':
                statement = f"⏳ شيك معلق - {method_arabic} للمورد"
            else:
                statement = f"سداد {method_arabic} للمورد"
        else:  # IN
            if is_bounced:
                statement = f"❌ شيك مرفوض - {method_arabic} من المورد"
            elif is_pending and method_raw == 'cheque':
                statement = f"⏳ شيك معلق - {method_arabic} من المورد"
            else:
                statement = f"قبض {method_arabic} من المورد"
        
        if notes:
            statement += f" - {notes[:30]}"
        
        # القيد المحاسبي
        entry_type = "CHECK_BOUNCED" if is_bounced else ("CHECK_PENDING" if is_pending and method_raw == 'cheque' else "PAYMENT")
        
        # ✅ حساب debit/credit حسب Direction:
        # OUT (للمورد) → credit (نخفف ما ندين به له)
        # IN (من المورد) → debit (يزيد ما يدين به لنا)
        if is_bounced:
            # الشيك المرتد → عكس الاتجاه
            debit_val = Decimal("0.00") if is_out else amt
            credit_val = amt if is_out else Decimal("0.00")
        else:
            # حسب Direction
            debit_val = Decimal("0.00") if is_out else amt  # IN → مدين
            credit_val = amt if is_out else Decimal("0.00")  # OUT → دائن
        
        entries.append({
            "date": d,
            "type": entry_type,
            "ref": ref,
            "statement": statement,
            "debit": debit_val,
            "credit": credit_val,
            "payment_details": payment_details,
            "notes": notes
        })
        
        if is_bounced:
            total_debit += debit_val
            total_credit += credit_val
        else:
            total_debit += debit_val
            total_credit += credit_val

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

    expense_q = Expense.query.filter(
        or_(
            Expense.supplier_id == supplier.id,
            and_(Expense.payee_type == "SUPPLIER", Expense.payee_entity_id == supplier.id)
        )
    )
    if df:
        expense_q = expense_q.filter(Expense.date >= df)
    if dt:
        expense_q = expense_q.filter(Expense.date < dt)
    
    for exp in expense_q.all():
        d = exp.date
        amt = q2(exp.amount or 0)
        
        if exp.currency and exp.currency != "ILS" and amt > 0:
            try:
                from models import convert_amount
                convert_date = d if d else (df if df else supplier.created_at)
                amt = convert_amount(amt, exp.currency, "ILS", convert_date)
            except Exception as e:
                try:
                    from flask import current_app
                    current_app.logger.error(f"Error converting expense #{exp.id} amount: {e}")
                except Exception:
                    pass
        
        exp_type_name = getattr(getattr(exp, 'type', None), 'name', 'مصروف')
        ref = f"مصروف #{exp.id}"
        statement = f"مصروف: {exp_type_name}"
        if exp.description:
            statement += f" - {exp.description}"
        
        entries.append({
            "date": d,
            "type": "EXPENSE",
            "ref": ref,
            "statement": statement,
            "debit": amt,
            "credit": Decimal("0.00")
        })
        total_debit += amt

    # إضافة الرصيد الافتتاحي كأول قيد
    opening_balance = Decimal(getattr(supplier, 'opening_balance', 0) or 0)
    if opening_balance != 0 and supplier.currency and supplier.currency != "ILS":
        try:
            from models import convert_amount
            convert_date = df if df else supplier.created_at
            opening_balance = convert_amount(opening_balance, supplier.currency, "ILS", convert_date)
        except Exception as e:
            try:
                from flask import current_app
                current_app.logger.error(f"Error converting supplier #{supplier.id} opening balance: {e}")
            except Exception:
                pass
    
    if opening_balance != 0:
        # تاريخ الرصيد الافتتاحي: تاريخ إنشاء المورد أو أول معاملة
        opening_date = supplier.created_at
        if entries:
            first_entry_date = min((e["date"] for e in entries if e["date"]), default=supplier.created_at)
            if first_entry_date and first_entry_date < supplier.created_at:
                opening_date = first_entry_date
        
        opening_entry = {
            "date": opening_date,
            "type": "OPENING_BALANCE",
            "ref": "OB-SUP",
            "statement": "الرصيد الافتتاحي",
            "debit": abs(opening_balance) if opening_balance < 0 else Decimal("0.00"),  # سالب = عليه = مدين
            "credit": opening_balance if opening_balance > 0 else Decimal("0.00"),      # موجب = له = دائن
        }
        entries.insert(0, opening_entry)
        if opening_balance < 0:  # سالب = عليه = مدين
            total_debit += abs(opening_balance)
        else:  # موجب = له = دائن
            total_credit += opening_balance

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

    # ✅ إضافة التسوية الذكية للملخص المحاسبي
    from routes.supplier_settlements import _calculate_smart_supplier_balance
    balance_data = _calculate_smart_supplier_balance(
        supplier_id,
        df if df else datetime(2024, 1, 1),
        (dt - timedelta(days=1)) if dt else datetime.utcnow()
    )
    
    balance_unified = balance_data.get('balance', {}).get('amount', 0) if balance_data.get('success') else supplier.balance_in_ils
    
    return render_template(
        "vendors/suppliers/statement.html",
        supplier=supplier,
        ledger_entries=out,
        total_debit=total_debit,
        total_credit=total_credit,
        balance=balance_unified,
        balance_data=balance_data,
        consignment_value=consignment_value,
        per_product=per_product,
        date_from=df if df else None,
        date_to=(dt - timedelta(days=1)) if dt else None,
    )

@vendors_bp.route("/partners", methods=["GET"], endpoint="partners_list")
@login_required
# @permission_required("manage_vendors")  # Commented out
def partners_list():
    form = CSRFProtectForm()
    s = (request.args.get("search") or "").strip()
    q = Partner.query.filter(Partner.is_archived == False)
    if s:
        term = f"%{s}%"
        q = q.filter(or_(Partner.name.ilike(term), Partner.phone_number.ilike(term), Partner.identity_number.ilike(term)))
    partners = q.order_by(Partner.name).all()
    
    # ✅ حساب الرصيد الحقيقي باستخدام التسوية الذكية لكل شريك
    from routes.partner_settlements import _calculate_smart_partner_balance
    smart_start = datetime(2024, 1, 1)
    smart_end = datetime.utcnow()
    
    # ✅ حساب الملخصات الإجمالية لجميع الشركاء - بناءً على الرصيد الذكي
    total_balance = 0.0
    total_debit = 0.0
    total_credit = 0.0
    partners_with_debt = 0
    partners_with_credit = 0
    
    for partner in partners:
        smart_balance = None
        try:
            balance_data = _calculate_smart_partner_balance(partner.id, smart_start, smart_end)
            if balance_data.get("success"):
                smart_balance = float(balance_data.get("balance", {}).get("amount", 0) or 0)
        except Exception:
            smart_balance = None
        
        balance = smart_balance if smart_balance is not None else float(partner.balance_in_ils or 0)
        partner.current_balance = balance
        partner.current_balance_source = "smart" if smart_balance is not None else "stored"
        
        total_balance += balance
        
        if balance > 0:
            partners_with_debt += 1  # مستحق دفع للشريك (له علينا)
            total_debit += balance  # ✅ إضافة للمدين
        elif balance < 0:
            partners_with_credit += 1  # الشريك مدين لنا (عليه لنا)
            total_credit += abs(balance)  # ✅ إضافة للدائن (قيمة موجبة)
    
    summary = {
        'total_partners': len(partners),
        'total_balance': total_balance,
        'total_debit': total_debit,  # ✅ إضافة
        'total_credit': total_credit,  # ✅ إضافة
        'partners_with_debt': partners_with_debt,
        'partners_with_credit': partners_with_credit,
        'average_balance': total_balance / len(partners) if partners else 0
    }
    
    return render_template(
        "vendors/partners/list.html",
        partners=partners,
        search=s,
        form=form,
        pay_url=url_for("payments.create_payment"),
        summary=summary,
    )

@vendors_bp.get("/partners/<int:partner_id>/statement", endpoint="partners_statement")
@login_required
# @permission_required("manage_vendors")  # Commented out
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

    entries = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    
    # المبيعات للشريك (كعميل) — تُسجّل دائن - ⚡ محسّن
    if partner.customer_id:
        from models import Sale, SaleStatus, _find_partner_share_percentage
        sale_q = (
            db.session.query(Sale)
            .options(joinedload(Sale.lines))
            .filter(
                Sale.customer_id == partner.customer_id,
                Sale.status == SaleStatus.CONFIRMED.value,
            )
        )
        if df:
            sale_q = sale_q.filter(Sale.sale_date >= df)
        if dt:
            sale_q = sale_q.filter(Sale.sale_date < dt)
        
        for sale in sale_q.all():
            d = sale.sale_date
            amt = q2(sale.total_amount or 0)
            ref = sale.sale_number or f"فاتورة #{sale.id}"
            
            items = []
            for line in (sale.lines or []):
                product_id = line.product_id if hasattr(line, 'product_id') else None
                warehouse_id = line.warehouse_id if hasattr(line, 'warehouse_id') else None
                share_pct = _find_partner_share_percentage(partner.id, product_id, warehouse_id) if product_id else 0.0
                line_total = float(q2(line.net_amount or 0))
                share_amount = line_total * (share_pct / 100.0) if share_pct else 0.0
                
                items.append({
                    "type": "قطعة",
                    "name": line.product.name if line.product else "منتج",
                    "qty": line.quantity or 0,
                    "price": float(q2(line.unit_price or 0)),
                    "total": line_total,
                    "share_pct": share_pct,
                    "share_amount": share_amount
                })
            
            statement = f"مبيعات للشريك - {ref}"
            entries.append({
                "date": d, 
                "type": "SALE", 
                "ref": ref, 
                "statement": statement, 
                "debit": Decimal("0.00"), 
                "credit": amt,
                "details": items,
                "has_details": len(items) > 0
            })
            total_credit += amt
    
    # الصيانة للشريك (كعميل) — تُسجّل دائن - ⚡ محسّن
    if partner.customer_id:
        from models import ServiceRequest, _find_partner_share_percentage
        service_q = (
            db.session.query(ServiceRequest)
            .options(joinedload(ServiceRequest.parts), joinedload(ServiceRequest.tasks))
            .filter(
                ServiceRequest.customer_id == partner.customer_id,
                ServiceRequest.status == ServiceStatus.COMPLETED.value,
            )
        )
        if df:
            service_q = service_q.filter(ServiceRequest.received_at >= df)
        if dt:
            service_q = service_q.filter(ServiceRequest.received_at < dt)
        
        for service in service_q.all():
            d = service.received_at
            amt = q2(service.total_amount or 0)
            ref = service.service_number or f"صيانة #{service.id}"
            
            items = []
            for part in (service.parts or []):
                product_id = part.part_id if hasattr(part, 'part_id') else None
                warehouse_id = part.warehouse_id if hasattr(part, 'warehouse_id') else None
                share_pct = float(part.share_percentage or 0) if part.partner_id == partner.id else _find_partner_share_percentage(partner.id, product_id, warehouse_id) if product_id else 0.0
                part_total = float(q2(part.quantity * part.unit_price))
                share_amount = part_total * (share_pct / 100.0) if share_pct else 0.0
                
                items.append({
                    "type": "قطعة",
                    "name": part.part.name if part.part else "قطعة غيار",
                    "qty": part.quantity,
                    "price": float(part.unit_price or 0),
                    "total": part_total,
                    "share_pct": share_pct,
                    "share_amount": share_amount
                })
            for task in (service.tasks or []):
                items.append({
                    "type": "خدمة",
                    "name": task.description or "خدمة",
                    "qty": task.quantity or 1,
                    "price": float(task.unit_price or 0),
                    "total": float(q2((task.quantity or 1) * task.unit_price)),
                    "share_pct": 0,
                    "share_amount": 0
                })
            
            statement = f"صيانة للشريك - {ref}"
            entries.append({
                "date": d, 
                "type": "SERVICE", 
                "ref": ref, 
                "statement": statement, 
                "debit": Decimal("0.00"), 
                "credit": amt,
                "details": items,
                "has_details": len(items) > 0
            })
            total_credit += amt

    # الدفعات
    q = (
        db.session.query(Payment)
        .filter(
            Payment.partner_id == partner.id,
            Payment.status.in_([PaymentStatus.COMPLETED.value, PaymentStatus.PENDING.value]),
        )
    )
    if df:
        q = q.filter(Payment.payment_date >= df)
    if dt:
        q = q.filter(Payment.payment_date < dt)

    for p in q.all():
        d = p.payment_date
        amt = q2(p.total_amount or 0)
        ref = p.reference or f"سند #{p.id}"
        dirv = getattr(p, "direction", None)
        
        # فحص حالة الدفعة
        payment_status = getattr(p, 'status', 'COMPLETED')
        is_bounced = payment_status in ['BOUNCED', 'FAILED', 'REJECTED']
        is_pending = payment_status == 'PENDING'
        
        # استخراج طريقة الدفع
        method_value = getattr(p, 'method', 'cash')
        if hasattr(method_value, 'value'):
            method_value = method_value.value
        method_raw = str(method_value).lower()
        
        method_arabic = {
            'cash': 'نقداً',
            'card': 'بطاقة',
            'cheque': 'شيك',
            'bank': 'تحويل بنكي',
            'online': 'إلكتروني'
        }.get(method_raw, method_raw)
        
        # تفاصيل الدفعة
        payment_details = {
            'method': method_arabic,
            'method_raw': method_raw,
            'check_number': getattr(p, 'check_number', None) if method_raw == 'cheque' else None,
            'check_bank': getattr(p, 'check_bank', None),
            'check_due_date': getattr(p, 'check_due_date', None) if method_raw == 'cheque' else None,
            'receiver_name': getattr(p, 'receiver_name', None) or '',
            'status': payment_status,
            'is_bounced': is_bounced,
            'is_pending': is_pending
        }
        
        # البيان
        notes = getattr(p, 'notes', '') or ''
        
        # OUT => مدين (خارج منا للشريك)
        # IN => دائن (وارد منا من الشريك)
        if dirv == PaymentDirection.OUT.value:
            if is_bounced:
                statement = f"❌ شيك مرفوض - {method_arabic} للشريك"
            elif is_pending and method_raw == 'cheque':
                statement = f"⏳ شيك معلق - {method_arabic} للشريك"
            else:
                statement = f"سداد {method_arabic} للشريك"
            
            if notes:
                statement += f" - {notes[:30]}"
            
            entry_type = "CHECK_BOUNCED" if is_bounced else ("CHECK_PENDING" if is_pending and method_raw == 'cheque' else "PAYMENT_OUT")
            
            entries.append({
                "date": d,
                "type": entry_type,
                "ref": ref,
                "statement": statement,
                "debit": Decimal("0.00") if is_bounced else amt,  # المرتد يُعكس
                "credit": amt if is_bounced else Decimal("0.00"),
                "payment_details": payment_details,
                "notes": notes
            })
            
            if is_bounced:
                total_credit += amt
            else:
                total_debit += amt
        else:
            if is_bounced:
                statement = f"❌ شيك مرفوض - {method_arabic} من الشريك"
            elif is_pending and method_raw == 'cheque':
                statement = f"⏳ شيك معلق - {method_arabic} من الشريك"
            else:
                statement = f"قبض {method_arabic} من الشريك"
            
            if notes:
                statement += f" - {notes[:30]}"
            
            entry_type = "CHECK_BOUNCED" if is_bounced else ("CHECK_PENDING" if is_pending and method_raw == 'cheque' else "PAYMENT_IN")
            
            entries.append({
                "date": d,
                "type": entry_type,
                "ref": ref,
                "statement": statement,
                "debit": amt if is_bounced else Decimal("0.00"),
                "credit": Decimal("0.00") if is_bounced else amt,
                "payment_details": payment_details,
                "notes": notes
            })
            
            if is_bounced:
                total_debit += amt
            else:
                total_credit += amt

    expense_q = Expense.query.filter(
        or_(
            Expense.partner_id == partner.id,
            and_(Expense.payee_type == "PARTNER", Expense.payee_entity_id == partner.id)
        )
    )
    if df:
        expense_q = expense_q.filter(Expense.date >= df)
    if dt:
        expense_q = expense_q.filter(Expense.date < dt)
    
    for exp in expense_q.all():
        d = exp.date
        amt = q2(exp.amount or 0)
        
        if exp.currency and exp.currency != "ILS" and amt > 0:
            try:
                from models import convert_amount
                convert_date = d if d else (df if df else partner.created_at)
                amt = convert_amount(amt, exp.currency, "ILS", convert_date)
            except Exception as e:
                try:
                    from flask import current_app
                    current_app.logger.error(f"Error converting expense #{exp.id} amount: {e}")
                except Exception:
                    pass
        
        exp_type_name = getattr(getattr(exp, 'type', None), 'name', 'مصروف')
        ref = f"مصروف #{exp.id}"
        statement = f"مصروف: {exp_type_name}"
        if exp.description:
            statement += f" - {exp.description}"
        
        entries.append({
            "date": d,
            "type": "EXPENSE",
            "ref": ref,
            "statement": statement,
            "debit": amt,
            "credit": Decimal("0.00")
        })
        total_debit += amt

    # إضافة الرصيد الافتتاحي كأول قيد
    opening_balance = Decimal(getattr(partner, 'opening_balance', 0) or 0)
    if opening_balance != 0 and partner.currency and partner.currency != "ILS":
        try:
            from models import convert_amount
            convert_date = df if df else partner.created_at
            opening_balance = convert_amount(opening_balance, partner.currency, "ILS", convert_date)
        except Exception as e:
            try:
                from flask import current_app
                current_app.logger.error(f"Error converting partner #{partner.id} opening balance: {e}")
            except Exception:
                pass
    
    if opening_balance != 0:
        # تاريخ الرصيد الافتتاحي: تاريخ إنشاء الشريك أو أول معاملة
        opening_date = partner.created_at
        if entries:
            first_entry_date = min((e["date"] for e in entries if e["date"]), default=partner.created_at)
            if first_entry_date and first_entry_date < partner.created_at:
                opening_date = first_entry_date
        
        opening_entry = {
            "date": opening_date,
            "type": "OPENING_BALANCE",
            "ref": "OB-PARTNER",
            "statement": "الرصيد الافتتاحي",
            "debit": abs(opening_balance) if opening_balance < 0 else Decimal("0.00"),  # سالب = عليه = مدين
            "credit": opening_balance if opening_balance > 0 else Decimal("0.00"),      # موجب = له = دائن
        }
        entries.insert(0, opening_entry)
        if opening_balance < 0:  # سالب = عليه = مدين
            total_debit += abs(opening_balance)
        else:  # موجب = له = دائن
            total_credit += opening_balance

    entries.sort(key=lambda e: (e["date"] or datetime.min, e["type"], e["ref"]))

    balance = Decimal("0.00")
    out = []
    for e in entries:
        d = q2(e["debit"])
        c = q2(e["credit"])
        balance += d - c
        out.append({**e, "debit": d, "credit": c, "balance": balance})
    
    # ✅ إضافة التسوية الذكية للملخص المحاسبي
    from routes.partner_settlements import _calculate_smart_partner_balance
    balance_data = _calculate_smart_partner_balance(
        partner_id,
        df if df else datetime(2024, 1, 1),
        (dt - timedelta(days=1)) if dt else datetime.utcnow()
    )
    
    balance_unified = balance_data.get('balance', {}).get('amount', 0) if balance_data.get('success') else partner.balance_in_ils
    
    inventory_items = []
    try:
        from models import WarehousePartnerShare, StockLevel, Product, Warehouse, _find_partner_share_percentage
        
        shares_q = db.session.query(WarehousePartnerShare).filter(
            WarehousePartnerShare.partner_id == partner.id
        ).all()
        
        for share in shares_q:
            warehouse_id = share.warehouse_id
            product_id = share.product_id
            
            if warehouse_id and product_id:
                stock = db.session.query(StockLevel).filter(
                    StockLevel.warehouse_id == warehouse_id,
                    StockLevel.product_id == product_id,
                    StockLevel.quantity > 0
                ).first()
                
                if stock:
                    product = db.session.get(Product, product_id)
                    warehouse = db.session.get(Warehouse, warehouse_id)
                    
                    if product and warehouse:
                        share_pct = float(share.share_percentage or 0)
                        product_value = float(stock.quantity) * float(product.purchase_price or 0)
                        partner_share_value = product_value * (share_pct / 100.0) if share_pct else 0.0
                        
                        inventory_items.append({
                            'product_name': product.name,
                            'sku': product.sku or '—',
                            'warehouse_name': warehouse.name,
                            'quantity': stock.quantity,
                            'purchase_price': float(product.purchase_price or 0),
                            'product_value': product_value,
                            'share_pct': share_pct,
                            'partner_share_value': partner_share_value
                        })
            elif warehouse_id:
                warehouse = db.session.get(Warehouse, warehouse_id)
                if warehouse:
                    stocks = db.session.query(StockLevel, Product).join(
                        Product, Product.id == StockLevel.product_id
                    ).filter(
                        StockLevel.warehouse_id == warehouse_id,
                        StockLevel.quantity > 0
                    ).all()
                    
                    for stock, product in stocks:
                        share_pct = _find_partner_share_percentage(partner.id, product.id, warehouse_id)
                        product_value = float(stock.quantity) * float(product.purchase_price or 0)
                        partner_share_value = product_value * (share_pct / 100.0) if share_pct else 0.0
                        
                        inventory_items.append({
                            'product_name': product.name,
                            'sku': product.sku or '—',
                            'warehouse_name': warehouse.name,
                            'quantity': stock.quantity,
                            'purchase_price': float(product.purchase_price or 0),
                            'product_value': product_value,
                            'share_pct': share_pct,
                            'partner_share_value': partner_share_value
                        })
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.error(f"Error fetching partner inventory: {e}")
        except Exception:
            pass

    return render_template(
        "vendors/partners/statement.html",
        partner=partner,
        ledger_entries=out,
        total_debit=total_debit,
        total_credit=total_credit,
        balance=balance_unified,
        balance_data=balance_data,
        inventory_items=inventory_items,
        date_from=df if df else None,
        date_to=(dt - timedelta(days=1)) if dt else None,
    )

@vendors_bp.route("/partners/new", methods=["GET", "POST"], endpoint="partners_create")
@login_required
# @permission_required("manage_vendors")  # Commented out
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
# @permission_required("manage_vendors")  # Commented out
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
# @permission_required("manage_vendors")  # Commented out
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
# @permission_required("manage_vendors")  # Commented out
def supplier_smart_settlement(supplier_id):
    """التسوية الذكية للمورد - redirect to new endpoint"""
    # توجيه للـ endpoint الجديد
    params = {}
    if request.args.get('date_from'):
        params['date_from'] = request.args.get('date_from')
    if request.args.get('date_to'):
        params['date_to'] = request.args.get('date_to')
    
    return redirect(url_for('supplier_settlements_bp.supplier_settlement', 
                           supplier_id=supplier_id, **params))


@vendors_bp.route("/partners/<int:partner_id>/smart-settlement", methods=["GET"], endpoint="partner_smart_settlement")
@login_required
# @permission_required("manage_vendors")  # Commented out
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
    
    # توجيه للـ endpoint الجديد
    params = {}
    if request.args.get('date_from'):
        params['date_from'] = request.args.get('date_from')
    if request.args.get('date_to'):
        params['date_to'] = request.args.get('date_to')
    
    return redirect(url_for('partner_settlements_bp.partner_settlement', 
                           partner_id=partner_id, **params))


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
    """حساب الوارد من المورد مع تحويل العملات"""
    from decimal import Decimal
    from models import convert_amount
    
    # المشتريات (النفقات من نوع مشتريات) - مع تحويل العملات
    expenses = Expense.query.filter(
        or_(
            Expense.supplier_id == supplier_id,
            and_(Expense.payee_type == "SUPPLIER", Expense.payee_entity_id == supplier_id)
        ),
        Expense.date >= date_from,
        Expense.date <= date_to
    ).all()
    
    purchases = Decimal('0.00')
    for exp in expenses:
        amt = Decimal(str(exp.amount or 0))
        if exp.currency == "ILS":
            purchases += amt
        else:
            try:
                purchases += convert_amount(amt, exp.currency, "ILS", exp.date)
            except Exception:
                pass
    
    # القطع المعطاة للمورد (ExchangeTransaction مع اتجاه OUT)
    exchanges = ExchangeTransaction.query.filter(
        ExchangeTransaction.supplier_id == supplier_id,
        ExchangeTransaction.direction == "OUT",
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to
    ).all()
    
    products_given = Decimal('0.00')
    for ex in exchanges:
        amt = Decimal(str(ex.quantity or 0)) * Decimal(str(ex.unit_cost or 0))
        ex_currency = getattr(ex, 'currency', 'ILS')
        if ex_currency == "ILS":
            products_given += amt
        else:
            try:
                products_given += convert_amount(amt, ex_currency, "ILS", ex.created_at)
            except Exception:
                pass
    
    return {
        "purchases": float(purchases),
        "products_given": float(products_given),
        "total": float(purchases + products_given)
    }


def _calculate_supplier_outgoing(supplier_id: int, date_from: datetime, date_to: datetime):
    from routes.supplier_settlements import _get_sales_to_supplier
    return _get_sales_to_supplier(supplier_id, date_from, date_to)


def _calculate_partner_incoming(partner_id: int, date_from: datetime, date_to: datetime):
    """حساب الوارد من الشريك مع تحويل العملات"""
    from decimal import Decimal
    from models import convert_amount
    
    # حصة الشريك من المبيعات (من خلال ServicePart)
    service_parts = db.session.query(ServicePart, ServiceRequest).join(
        ServiceRequest, ServiceRequest.id == ServicePart.service_id
    ).filter(
        ServicePart.partner_id == partner_id,
        ServiceRequest.received_at >= date_from,
        ServiceRequest.received_at <= date_to
    ).all()
    
    sales_share = Decimal('0.00')
    for sp, sr in service_parts:
        amt = Decimal(str(sp.quantity or 0)) * Decimal(str(sp.unit_price or 0))
        sr_currency = getattr(sr, 'currency', 'ILS')
        if sr_currency == "ILS":
            sales_share += amt
        else:
            try:
                sales_share += convert_amount(amt, sr_currency, "ILS", sr.received_at)
            except Exception:
                pass
    
    # القطع المعطاة للشريك
    exchanges = ExchangeTransaction.query.filter(
        ExchangeTransaction.partner_id == partner_id,
        ExchangeTransaction.direction == "OUT",
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to
    ).all()
    
    products_given = Decimal('0.00')
    for ex in exchanges:
        amt = Decimal(str(ex.quantity or 0)) * Decimal(str(ex.unit_cost or 0))
        ex_currency = getattr(ex, 'currency', 'ILS')
        if ex_currency == "ILS":
            products_given += amt
        else:
            try:
                products_given += convert_amount(amt, ex_currency, "ILS", ex.created_at)
            except Exception:
                pass
    
    return {
        "sales_share": float(sales_share),
        "products_given": float(products_given),
        "total": float(sales_share + products_given)
    }


def _calculate_partner_outgoing(partner_id: int, date_from: datetime, date_to: datetime):
    """حساب الصادر للشريك مع تحويل العملات"""
    from decimal import Decimal
    from models import convert_amount
    
    # حصة الشريك من المشتريات - مع تحويل العملات
    expenses = Expense.query.filter(
        or_(
            Expense.partner_id == partner_id,
            and_(Expense.payee_type == "PARTNER", Expense.payee_entity_id == partner_id)
        ),
        Expense.date >= date_from,
        Expense.date <= date_to
    ).all()
    
    purchases_share = Decimal('0.00')
    for exp in expenses:
        amt = Decimal(str(exp.amount or 0))
        if exp.currency == "ILS":
            purchases_share += amt
        else:
            try:
                purchases_share += convert_amount(amt, exp.currency, "ILS", exp.date)
            except Exception:
                pass
    
    # القطع المأخوذة من الشريك
    exchanges = ExchangeTransaction.query.filter(
        ExchangeTransaction.partner_id == partner_id,
        ExchangeTransaction.direction == "IN",
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to
    ).all()
    
    products_taken = Decimal('0.00')
    for ex in exchanges:
        amt = Decimal(str(ex.quantity or 0)) * Decimal(str(ex.unit_cost or 0))
        ex_currency = getattr(ex, 'currency', 'ILS')
        if ex_currency == "ILS":
            products_taken += amt
        else:
            try:
                products_taken += convert_amount(amt, ex_currency, "ILS", ex.created_at)
            except Exception:
                pass
    
    return {
        "purchases_share": float(purchases_share),
        "products_taken": float(products_taken),
        "total": float(purchases_share + products_taken)
    }


def _calculate_payments_to_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    from routes.supplier_settlements import _get_payments_to_supplier
    supplier = db.session.get(Supplier, supplier_id)
    result = _get_payments_to_supplier(supplier_id, supplier, date_from, date_to)
    return result.get("total_ils", 0.0)


def _calculate_payments_from_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    from routes.supplier_settlements import _get_payments_from_supplier
    supplier = db.session.get(Supplier, supplier_id)
    result = _get_payments_from_supplier(supplier_id, supplier, date_from, date_to)
    return result.get("total_ils", 0.0)


def _calculate_payments_to_partner(partner_id: int, date_from: datetime, date_to: datetime):
    from routes.partner_settlements import _get_payments_to_partner
    partner = db.session.get(Partner, partner_id)
    result = _get_payments_to_partner(partner_id, partner, date_from, date_to)
    return result.get("total_ils", 0.0)


def _calculate_payments_from_partner(partner_id: int, date_from: datetime, date_to: datetime):
    from routes.partner_settlements import _get_partner_payments_received
    partner = db.session.get(Partner, partner_id)
    result = _get_partner_payments_received(partner_id, partner, date_from, date_to)
    return result.get("total_ils", 0.0)


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
# @permission_required("manage_vendors")  # Commented out
def archive_supplier(supplier_id):
    
    try:
        from models import Archive
        
        supplier = Supplier.query.get_or_404(supplier_id)
        
        reason = request.form.get('reason', 'أرشفة تلقائية')
        
        utils.archive_record(supplier, reason, current_user.id)
        flash(f'تم أرشفة المورد {supplier.name} بنجاح', 'success')
        return redirect(url_for('vendors_bp.suppliers_list'))
        
    except Exception as e:
        import traceback
        
        db.session.rollback()
        flash(f'خطأ في أرشفة المورد: {str(e)}', 'error')
        return redirect(url_for('vendors_bp.suppliers_list'))

@vendors_bp.route("/partners/archive/<int:partner_id>", methods=["POST"])
@login_required
# @permission_required("manage_vendors")  # Commented out
def archive_partner(partner_id):
    """أرشفة شريك"""
    
    try:
        from models import Archive
        
        partner = Partner.query.get_or_404(partner_id)
        
        reason = request.form.get('reason', 'أرشفة تلقائية')
        
        utils.archive_record(partner, reason, current_user.id)
        
        flash(f'تم أرشفة الشريك {partner.name} بنجاح', 'success')
        print(f"🎉 [PARTNER ARCHIVE] تمت العملية بنجاح - إعادة توجيه...")
        return redirect(url_for('vendors_bp.partners_list'))
        
    except Exception as e:
        import traceback
        
        db.session.rollback()
        flash(f'خطأ في أرشفة الشريك: {str(e)}', 'error')
        return redirect(url_for('vendors_bp.partners_list'))

@vendors_bp.route("/suppliers/restore/<int:supplier_id>", methods=["POST"])
@login_required
# @permission_required("manage_vendors")  # Commented out
def restore_supplier(supplier_id):
    """استعادة مورد"""
    
    try:
        supplier = Supplier.query.get_or_404(supplier_id)
        
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
            utils.restore_record(archive.id)
        
        flash(f'تم استعادة المورد {supplier.name} بنجاح', 'success')
        print(f"🎉 [SUPPLIER RESTORE] تمت العملية بنجاح - إعادة توجيه...")
        return redirect(url_for('vendors_bp.suppliers_list'))
        
    except Exception as e:
        import traceback
        
        db.session.rollback()
        flash(f'خطأ في استعادة المورد: {str(e)}', 'error')
        return redirect(url_for('vendors_bp.suppliers_list'))

@vendors_bp.route("/partners/restore/<int:partner_id>", methods=["POST"])
@login_required
# @permission_required("manage_vendors")  # Commented out
def restore_partner(partner_id):
    """استعادة شريك"""
    
    try:
        partner = Partner.query.get_or_404(partner_id)
        
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
            utils.restore_record(archive.id)
        
        flash(f'تم استعادة الشريك {partner.name} بنجاح', 'success')
        print(f"🎉 [PARTNER RESTORE] تمت العملية بنجاح - إعادة توجيه...")
        return redirect(url_for('vendors_bp.partners_list'))
        
    except Exception as e:
        import traceback
        
        db.session.rollback()
        flash(f'خطأ في استعادة الشريك: {str(e)}', 'error')
        return redirect(url_for('vendors_bp.partners_list'))