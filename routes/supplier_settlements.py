
from datetime import datetime, date as _date, time as _time
from decimal import Decimal, ROUND_HALF_UP
from flask import Blueprint, request, jsonify, render_template, url_for, abort
from flask_login import login_required
from sqlalchemy import and_
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
import utils
from models import Supplier, PaymentDirection, PaymentMethod, PaymentStatus, SupplierSettlement, SupplierSettlementStatus, build_supplier_settlement_draft, AuditLog
import json

supplier_settlements_bp = Blueprint("supplier_settlements_bp", __name__, url_prefix="/suppliers")

@supplier_settlements_bp.route("/settlements", methods=["GET"], endpoint="list")
@login_required
# @permission_required("manage_vendors")  # Commented out
def settlements_list():
    """قائمة تسويات الموردين"""
    return render_template("supplier_settlements/list.html")

def _get_supplier_or_404(sid: int) -> Supplier:
    obj = db.session.get(Supplier, sid)
    if not obj:
        abort(404)
    return obj

def _parse_iso_to_datetime(val: str, end: bool = False):
    s = (val or "").strip()
    if not s:
        return None
    try:
        if len(s) == 10:
            d = _date.fromisoformat(s)
            return datetime.combine(d, _time.max if end else _time.min)
        return datetime.fromisoformat(s)
    except Exception:
        return None

def _extract_range_from_request():
    now = datetime.utcnow()
    start_default = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_default = now
    if request.method == "GET":
        frm = request.args.get("from")
        to = request.args.get("to")
    else:
        payload = request.get_json(silent=True) or {}
        frm = payload.get("from") or request.form.get("from")
        to = payload.get("to") or request.form.get("to")
    dfrom = _parse_iso_to_datetime(frm, end=False) if frm else start_default
    dto = _parse_iso_to_datetime(to, end=True) if to else end_default
    if not dfrom or not dto:
        return None, None, "Bad date ISO format"
    if dfrom > dto:
        return None, None, "from must be before to"
    return dfrom, dto, ""

from utils import _q2

def _d2(v) -> Decimal:
    """تحويل إلى Decimal بدقة منزلتين"""
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _due_direction(v: Decimal):
    if v > 0:
        return PaymentDirection.OUT.value
    return PaymentDirection.IN.value

def _currency_mismatch(lines, currency: str) -> bool:
    for l in lines or []:
        c = getattr(l, "currency", None) or currency
        if c != currency:
            return True
    return False

def _overlap_exists(supplier_id: int, dfrom: datetime, dto: datetime) -> bool:
    return db.session.query(SupplierSettlement.id).filter(
        SupplierSettlement.supplier_id == supplier_id,
        SupplierSettlement.status.in_([SupplierSettlementStatus.DRAFT.value, SupplierSettlementStatus.CONFIRMED.value]),
        and_(SupplierSettlement.from_date <= dto, SupplierSettlement.to_date >= dfrom)
    ).first() is not None

@supplier_settlements_bp.route("/<int:supplier_id>/settlements/preview", methods=["GET"])
@login_required
# @permission_required("manage_vendors")  # Commented out
def preview(supplier_id):
    from flask import redirect
    return redirect(url_for('supplier_settlements_bp.supplier_settlement', supplier_id=supplier_id))

@supplier_settlements_bp.route("/<int:supplier_id>/settlements/create", methods=["POST"])
@login_required
# @permission_required("manage_vendors")  # Commented out
def create(supplier_id):
    supplier = _get_supplier_or_404(supplier_id)
    dfrom, dto, err = _extract_range_from_request()
    if err:
        return jsonify({"success": False, "error": err}), 400
    draft = build_supplier_settlement_draft(supplier.id, dfrom, dto, currency=supplier.currency)
    lines = getattr(draft, "lines", []) or []
    if not lines:
        return jsonify({"success": False, "error": "لا توجد سطور لتسويتها"}), 400
    if _currency_mismatch(lines, supplier.currency):
        return jsonify({"success": False, "error": "عملة غير متطابقة داخل التسوية"}), 400
    if _overlap_exists(supplier.id, dfrom, dto):
        return jsonify({"success": False, "error": "نطاق متداخل مع تسوية سابقة"}), 409
    due = Decimal(str(draft.total_due or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if due == Decimal("0.00"):
        return jsonify({"success": False, "error": "لا توجد مبالغ مستحقة"}), 400
    draft.ensure_code()
    draft.from_date = dfrom
    draft.to_date = dto
    draft.currency = supplier.currency
    try:
        with db.session.begin():
            db.session.add(draft)
            db.session.flush()
            db.session.add(AuditLog(model_name="SupplierSettlement", record_id=draft.id, action="CREATE", old_data=None, new_data=json.dumps({
                "supplier_id": supplier.id, "from": dfrom.isoformat(), "to": dto.isoformat(), "total_due": str(due), "code": draft.code
            })))
    except SQLAlchemyError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    direction = _due_direction(due)
    amount_str = f"{abs(due):.2f}"
    pay_url = url_for(
        "payments.create_payment",
        entity_type="SUPPLIER",
        entity_id=str(supplier.id),
        direction=direction,
        total_amount=amount_str,
        currency=supplier.currency,
        method=PaymentMethod.BANK.value,
        reference=f"SupplierSettle:{draft.code}",
        notes=f"تسوية مورد {supplier.name} {dfrom.date()} - {dto.date()} ({draft.code})",
    )
    return jsonify({"success": True, "id": draft.id, "code": draft.code, "pay_url": pay_url})

@supplier_settlements_bp.route("/settlements/<int:settlement_id>/confirm", methods=["POST"])
@login_required
# @permission_required("manage_vendors")  # Commented out
def confirm(settlement_id):
    ss = db.session.get(SupplierSettlement, settlement_id)
    if not ss:
        abort(404)
    if ss.status != SupplierSettlementStatus.DRAFT.value:
        return jsonify({"success": False, "error": "Only DRAFT can be confirmed"}), 400
    recalc = build_supplier_settlement_draft(ss.supplier_id, ss.from_date, ss.to_date, currency=ss.currency)
    orig = Decimal(str(ss.total_due or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    now_ = Decimal(str(recalc.total_due or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if orig != now_ or len(getattr(ss, "lines", []) or []) != len(getattr(recalc, "lines", []) or []):
        return jsonify({"success": False, "error": "اختلفت البيانات منذ المعاينة، أعد الإنشاء"}), 409
    try:
        with db.session.begin():
            ss.mark_confirmed()
            db.session.flush()
            db.session.add(AuditLog(model_name="SupplierSettlement", record_id=ss.id, action="CONFIRM", old_data=None, new_data=json.dumps({
                "code": ss.code, "from": ss.from_date.isoformat(), "to": ss.to_date.isoformat(), "total_due": str(orig)
            })))
    except SQLAlchemyError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "id": ss.id, "code": ss.code})

@supplier_settlements_bp.route("/settlements/<int:settlement_id>/void", methods=["POST"])
@login_required
# @permission_required("manage_vendors")  # Commented out
def void(settlement_id):
    ss = db.session.get(SupplierSettlement, settlement_id)
    if not ss:
        abort(404)
    if ss.status != SupplierSettlementStatus.DRAFT.value:
        return jsonify({"success": False, "error": "Only DRAFT can be voided"}), 400
    try:
        with db.session.begin():
            db.session.delete(ss)
            db.session.flush()
            db.session.add(AuditLog(model_name="SupplierSettlement", record_id=settlement_id, action="VOID", old_data=None, new_data=None))
    except SQLAlchemyError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})

@supplier_settlements_bp.route("/settlements/<int:settlement_id>", methods=["GET"])
@login_required
# @permission_required("manage_vendors")  # Commented out
def show(settlement_id):
    ss = db.session.get(SupplierSettlement, settlement_id)
    if not ss:
        abort(404)
    return render_template("vendors/suppliers/settlement_preview.html", ss=ss)


@supplier_settlements_bp.route("/exchange-transaction/<int:tx_id>/update-price", methods=["POST"])
@login_required
# @permission_required("manage_vendors")  # Commented out
def update_exchange_transaction_price(tx_id):
    """تحديث سعر قطعة في مستودع التبادل - API"""
    from models import ExchangeTransaction
    
    tx = db.session.get(ExchangeTransaction, tx_id)
    if not tx:
        return jsonify({"success": False, "error": "المعاملة غير موجودة"}), 404
    
    data = request.get_json() or {}
    new_price = data.get("unit_cost")
    
    if new_price is None:
        return jsonify({"success": False, "error": "السعر مطلوب"}), 400
    
    try:
        new_price = Decimal(str(new_price))
        if new_price < 0:
            return jsonify({"success": False, "error": "السعر يجب أن يكون >= 0"}), 400
    except (ValueError, InvalidOperation):
        return jsonify({"success": False, "error": "سعر غير صالح"}), 400
    
    try:
        tx.unit_cost = new_price
        tx.is_priced = True
        db.session.commit()
        
        # حساب القيمة الجديدة
        total_value = float(_q2(tx.quantity * new_price))
        
        return jsonify({
            "success": True,
            "message": "تم تحديث السعر بنجاح",
            "transaction_id": tx.id,
            "new_price": float(new_price),
            "quantity": tx.quantity,
            "total_value": total_value
        })
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


# ===== نظام التسوية الذكي للموردين =====

@supplier_settlements_bp.route("/<int:supplier_id>/settlement", methods=["GET"], endpoint="supplier_settlement")
@login_required
# @permission_required("manage_vendors")  # Commented out
def supplier_settlement(supplier_id):
    """التسوية الذكية للمورد"""
    supplier = _get_supplier_or_404(supplier_id)
    
    # الحصول على الفترة الزمنية
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    if date_from:
        date_from = _parse_iso_to_datetime(date_from, end=False)
    else:
        date_from = datetime(2024, 1, 1)
    
    if date_to:
        date_to = _parse_iso_to_datetime(date_to, end=True)
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
        remaining=balance_data.get("balance", {}).get("amount", 0) if isinstance(balance_data, dict) else 0,
        status="DRAFT",
        code=f"SS-SMART-{supplier_id}-{date_from.strftime('%Y%m%d')}",
        lines=[],
        created_at=date_from,
        updated_at=datetime.utcnow()
    )
    
    return render_template(
        "vendors/suppliers/settlement_preview.html",
        supplier=supplier,
        ss=ss,
        balance_data=balance_data,
        date_from=date_from,
        date_to=date_to
    )


def _calculate_smart_supplier_balance(supplier_id: int, date_from: datetime, date_to: datetime):
    """
    حساب الرصيد الذكي الشامل للمورد
    يشمل: القطع، المبيعات، الصيانة، الديون، الدفعات، المرتجعات
    """
    try:
        from models import (
            Expense, Sale, SaleLine, ExchangeTransaction, Payment, Product,
            ServiceRequest, ServicePart, Warehouse, WarehouseType, StockLevel
        )
        from sqlalchemy import func, desc, or_
        
        supplier = db.session.get(Supplier, supplier_id)
        if not supplier:
            return {"success": False, "error": "المورد غير موجود"}
        
        # ═══════════════════════════════════════════════════════════
        # المدين (Debit - له علينا - نحن ندين له)
        # ═══════════════════════════════════════════════════════════
        
        # 1. القطع من مستودع التبادل (IN direction)
        exchange_items = _get_supplier_exchange_items(supplier_id, date_from, date_to)
        
        # 2. ديون قديمة (إن وجدت - من Expense أو مصادر أخرى)
        old_debts = _get_supplier_old_debts(supplier_id, date_from)
        
        total_debit = Decimal(str(exchange_items["total_value"])) + Decimal(str(old_debts))
        
        # ═══════════════════════════════════════════════════════════
        # الدائن (Credit - علينا له - المورد أخذ أو ندين له)
        # ═══════════════════════════════════════════════════════════
        
        # 3. المبيعات للمورد (اشترى منا) - من Payment المرتبطة بـ sale_id
        sales_to_supplier = _get_sales_to_supplier(supplier_id, date_from, date_to)
        
        # 4. الصيانة للمورد (قدمنا له خدمة) - من Payment المرتبطة بـ service_id
        services_to_supplier = _get_services_to_supplier(supplier_id, date_from, date_to)
        
        # 5. الدفعات النقدية للمورد (OUT direction)
        cash_payments = _get_cash_payments_to_supplier(supplier_id, date_from, date_to)
        
        # 6. المرتجعات (قطع رجعناها له - OUT direction في Exchange)
        returns = _get_returns_to_supplier(supplier_id, date_from, date_to)
        
        total_credit = (Decimal(str(sales_to_supplier["total"])) + 
                       Decimal(str(services_to_supplier["total"])) + 
                       Decimal(str(cash_payments)) + 
                       Decimal(str(returns["total_value"])))
        
        # ═══════════════════════════════════════════════════════════
        # الحساب النهائي
        # ═══════════════════════════════════════════════════════════
        
        balance = total_debit - total_credit
        
        # ═══════════════════════════════════════════════════════════
        # معلومات إضافية
        # ═══════════════════════════════════════════════════════════
        
        # القطع غير المسعّرة
        unpriced_items = exchange_items["unpriced_items"]
        
        # آخر تسوية
        last_settlement = _get_last_supplier_settlement(supplier_id)
        
        # التسويات السابقة
        previous_settlements = _get_previous_supplier_settlements(supplier_id, date_from)
        
        # قيمة العهدة (Consignment) المتبقية
        consignment_value = _get_supplier_consignment_value(supplier_id)
        
        return {
            "success": True,
            "supplier": {
                "id": supplier.id,
                "name": supplier.name,
                "currency": supplier.currency,
                "original_currency": supplier.currency
            },
            "period": {
                "from": date_from.isoformat(),
                "to": date_to.isoformat()
            },
            # المدين (له علينا)
            "debit": {
                "exchange_items": exchange_items,  # القطع مع تفاصيلها
                "old_debts": float(old_debts),
                "total": float(total_debit)
            },
            # الدائن (علينا له)
            "credit": {
                "sales": sales_to_supplier,  # المبيعات مع التفاصيل
                "services": services_to_supplier,  # الصيانة مع التفاصيل
                "cash_payments": cash_payments,  # الدفعات النقدية
                "returns": returns,  # المرتجعات
                "total": float(total_credit)
            },
            # الرصيد (بالشيكل)
            "balance": {
                "amount": float(balance),
                "direction": "دفع للمورد" if balance > 0 else "قبض من المورد" if balance < 0 else "متوازن",
                "payment_direction": "OUT" if balance > 0 else "IN",
                "currency": "ILS",  # كل الحسابات موحدة بالشيكل
                "note": "جميع المبالغ محولة إلى الشيكل (ILS) حسب أسعار الصرف"
            },
            # معلومات إضافية
            "unpriced_items": unpriced_items,
            "last_settlement": last_settlement,
            "previous_settlements": previous_settlements,
            "consignment_value": consignment_value,
            "has_warnings": len(unpriced_items) > 0,
            "currency_note": "⚠️ تنبيه: تم توحيد جميع العملات إلى الشيكل (ILS) باستخدام أسعار الصرف المسجلة"
        }
        
    except ValueError as e:
        # خطأ في تحويل العملة - سعر الصرف غير متوفر
        if "fx.rate_unavailable" in str(e) or "rate_unavailable" in str(e):
            return {
                "success": False,
                "error": "سعر الصرف غير متوفر",
                "error_type": "missing_fx_rate",
                "message": "⚠️ تنبيه: لا يمكن إتمام التسوية لعدم توفر سعر صرف لإحدى العملات.\n\nيرجى:\n1. إدخال سعر الصرف يدوياً من [إعدادات العملات]\n2. أو تفعيل الاتصال بالسيرفرات العالمية\n3. ثم إعادة المحاولة",
                "help_url": "/settings/currencies"
            }
        return {"success": False, "error": f"خطأ في الحساب: {str(e)}"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": f"خطأ في حساب رصيد المورد: {str(e)}"}


def _calculate_supplier_incoming(supplier_id: int, date_from: datetime, date_to: datetime):
    """حساب الوارد من المورد"""
    from models import Expense, ExchangeTransaction
    from sqlalchemy import func
    
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
    from models import Sale, ExchangeTransaction
    from sqlalchemy import func
    
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


def _calculate_payments_to_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    """حساب الدفعات المدفوعة للمورد"""
    from models import Payment
    from sqlalchemy import func
    
    amount = db.session.query(func.sum(Payment.total_amount)).filter(
        Payment.supplier_id == supplier_id,
        Payment.direction == "OUTGOING",
        Payment.status == "COMPLETED",
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).scalar() or 0
    return float(amount)


def _calculate_payments_from_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    """حساب الدفعات المستلمة من المورد"""
    from models import Payment
    from sqlalchemy import func
    
    amount = db.session.query(func.sum(Payment.total_amount)).filter(
        Payment.supplier_id == supplier_id,
        Payment.direction == "INCOMING",
        Payment.status == "COMPLETED",
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).scalar() or 0
    return float(amount)


def _check_unpriced_items_for_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    """التحقق من القطع غير المسعرة للمورد"""
    from models import ExchangeTransaction, Product
    from sqlalchemy import func, or_
    
    # البحث عن القطع التي لا تحتوي على سعر
    unpriced_transactions = db.session.query(ExchangeTransaction).join(Product).filter(
        ExchangeTransaction.supplier_id == supplier_id,
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to,
        or_(
            ExchangeTransaction.unit_cost.is_(None),
            ExchangeTransaction.unit_cost == 0,
            Product.purchase_price.is_(None),
            Product.purchase_price == 0
        )
    ).all()
    
    unpriced_items = []
    for transaction in unpriced_transactions:
        unpriced_items.append({
            "transaction_id": transaction.id,
            "product_name": transaction.product.name if transaction.product else "غير محدد",
            "product_id": transaction.product_id,
            "quantity": transaction.quantity,
            "direction": transaction.direction,
            "date": transaction.created_at.isoformat() if transaction.created_at else None,
            "suggested_price": float(transaction.product.purchase_price) if transaction.product and transaction.product.purchase_price else 0
        })
    
    return {
        "count": len(unpriced_items),
        "items": unpriced_items,
        "total_estimated_value": sum(item["quantity"] * item["suggested_price"] for item in unpriced_items)
    }


def _get_last_supplier_settlement(supplier_id: int):
    """الحصول على آخر تسوية للمورد"""
    from models import SupplierSettlement
    from sqlalchemy import desc
    
    last_settlement = db.session.query(SupplierSettlement).filter(
        SupplierSettlement.supplier_id == supplier_id
    ).order_by(desc(SupplierSettlement.created_at)).first()
    
    if not last_settlement:
        return None
    
    return {
        "id": last_settlement.id,
        "code": last_settlement.code,
        "date": last_settlement.created_at.isoformat() if last_settlement.created_at else None,
        "status": last_settlement.status,
        "total_due": float(last_settlement.total_due) if last_settlement.total_due else 0,
        "currency": last_settlement.currency
    }


def _get_supplier_operations_details(supplier_id: int, date_from: datetime, date_to: datetime):
    """الحصول على تفاصيل العمليات للمورد"""
    from models import ExchangeTransaction, Payment, Expense, Sale
    from sqlalchemy import func, desc
    
    # العمليات الأخيرة
    recent_transactions = db.session.query(ExchangeTransaction).filter(
        ExchangeTransaction.supplier_id == supplier_id,
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to
    ).order_by(desc(ExchangeTransaction.created_at)).limit(10).all()
    
    # الدفعات الأخيرة
    recent_payments = db.session.query(Payment).filter(
        Payment.supplier_id == supplier_id,
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).order_by(desc(Payment.payment_date)).limit(10).all()
    
    # النفقات الأخيرة
    recent_expenses = db.session.query(Expense).filter(
        Expense.payee_type == "SUPPLIER",
        Expense.payee_entity_id == supplier_id,
        Expense.date >= date_from,
        Expense.date <= date_to
    ).order_by(desc(Expense.date)).limit(10).all()
    
    # المبيعات الأخيرة (إذا كان المورد عميلاً أيضاً)
    recent_sales = db.session.query(Sale).filter(
        Sale.customer_id == supplier_id,
        Sale.sale_date >= date_from,
        Sale.sale_date <= date_to
    ).order_by(desc(Sale.sale_date)).limit(10).all()
    
    return {
        "recent_transactions": [
            {
                "id": t.id,
                "product_name": t.product.name if t.product else "غير محدد",
                "quantity": t.quantity,
                "unit_cost": float(t.unit_cost) if t.unit_cost else 0,
                "direction": t.direction,
                "date": t.created_at.isoformat() if t.created_at else None,
                "total_value": float(t.quantity * t.unit_cost) if t.unit_cost else 0
            } for t in recent_transactions
        ],
        "recent_payments": [
            {
                "id": p.id,
                "amount": float(p.total_amount),
                "direction": p.direction,
                "method": p.method,
                "date": p.payment_date.isoformat() if p.payment_date else None,
                "status": p.status
            } for p in recent_payments
        ],
        "recent_expenses": [
            {
                "id": e.id,
                "amount": float(e.amount),
                "description": e.description,
                "date": e.date.isoformat() if e.date else None,
                "payee_name": e.payee_name
            } for e in recent_expenses
        ],
        "recent_sales": [
            {
                "id": s.id,
                "amount": float(s.total_amount),
                "sale_number": s.sale_number,
                "date": s.sale_date.isoformat() if s.sale_date else None,
                "status": s.status
            } for s in recent_sales
        ]
    }


def _get_settlement_recommendation(balance: float, currency: str):
    """اقتراح التسوية مع التحقق من القطع غير المسعرة"""
    if abs(balance) < 0.01:  # متوازن
        return {
            "action": "متوازن",
            "message": "لا توجد تسوية مطلوبة",
            "amount": 0,
            "warnings": []
        }
    elif balance > 0:  # الباقي له
        return {
            "action": "دفع",
            "message": f"يجب دفع {abs(balance):.2f} {currency} للمورد",
            "amount": abs(balance),
            "direction": "OUT",
            "warnings": []
        }
    else:  # الباقي عليه
        return {
            "action": "قبض",
            "message": f"يجب قبض {abs(balance):.2f} {currency} من المورد",
            "amount": abs(balance),
            "direction": "IN",
            "warnings": []
        }


# ═══════════════════════════════════════════════════════════════════════
# دوال مساعدة للتسوية الذكية الشاملة
# Helper Functions for Comprehensive Smart Settlement
# ═══════════════════════════════════════════════════════════════════════

def _check_required_fx_rates(currencies: list) -> dict:
    """
    التحقق من توفر أسعار الصرف المطلوبة
    يرجع قائمة بالعملات المفقودة إن وجدت
    """
    from models import fx_rate
    
    missing_rates = []
    available_rates = {}
    
    for currency in set(currencies):
        if currency == "ILS":
            continue
        
        try:
            rate = fx_rate(currency, "ILS", None, raise_on_missing=False)
            if rate <= 0:
                missing_rates.append(currency)
            else:
                available_rates[currency] = float(rate)
        except:
            missing_rates.append(currency)
    
    return {
        "has_missing": len(missing_rates) > 0,
        "missing_currencies": missing_rates,
        "available_rates": available_rates
    }


def _convert_to_ils(amount: Decimal | float, from_currency: str, at: datetime = None) -> Decimal:
    """
    تحويل أي مبلغ إلى الشيكل (ILS)
    الأولوية: 1- السعر اليدوي المحلي 2- سعر السيرفر 3- خطأ (إدخال يدوي مطلوب)
    """
    from models import convert_amount, money
    
    if not amount or amount == 0:
        return Decimal('0.00')
    
    # تنظيف اسم العملة
    from_currency = (from_currency or "ILS").strip().upper()
    
    # إذا كانت بالفعل ILS، لا حاجة للتحويل
    if from_currency == "ILS":
        return _d2(amount)
    
    # التحويل - يستخدم fx_rate داخلياً:
    # 1. يبحث في قاعدة البيانات المحلية (السعر اليدوي)
    # 2. إن لم يجد، يحاول السيرفرات العالمية
    # 3. إن فشل كلاهما، يرفع ValueError
    converted = convert_amount(
        amount=amount,
        from_code=from_currency,
        to_code="ILS",
        at=at or datetime.utcnow()
    )
    return _d2(converted)


def _get_supplier_exchange_items(supplier_id: int, date_from: datetime, date_to: datetime):
    """جلب القطع من مستودع التبادل مع التفاصيل"""
    from models import ExchangeTransaction, Warehouse, WarehouseType, Product
    
    # جلب مستودعات التبادل للمورد
    exchange_warehouses = db.session.query(Warehouse.id).filter(
        Warehouse.supplier_id == supplier_id,
        Warehouse.warehouse_type == WarehouseType.EXCHANGE.value
    ).all()
    
    warehouse_ids = [w[0] for w in exchange_warehouses]
    
    if not warehouse_ids:
        return {"items": [], "unpriced_items": [], "total_value": 0, "priced_count": 0, "unpriced_count": 0}
    
    # جلب المعاملات IN (قطع أخذناها من المورد)
    transactions = db.session.query(ExchangeTransaction).options(
        joinedload(ExchangeTransaction.product)
    ).filter(
        ExchangeTransaction.warehouse_id.in_(warehouse_ids),
        ExchangeTransaction.direction.in_(['IN', 'PURCHASE', 'CONSIGN_IN']),
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to
    ).all()
    
    items = []
    unpriced_items = []
    total_value = Decimal('0.00')
    
    for tx in transactions:
        prod = tx.product
        qty = Decimal(str(tx.quantity or 0))
        unit_cost = Decimal(str(tx.unit_cost or 0))
        
        # محاولة الحصول على السعر
        if unit_cost == 0:
            if prod and prod.purchase_price:
                unit_cost = Decimal(str(prod.purchase_price))
                fallback_used = True
            else:
                # قطعة غير مسعّرة
                unpriced_items.append({
                    "id": tx.id,
                    "product_id": tx.product_id,
                    "product_name": prod.name if prod else "غير محدد",
                    "product_sku": prod.sku if prod else None,
                    "quantity": int(qty),
                    "date": tx.created_at,
                    "suggested_price": 0
                })
                unit_cost = Decimal('0')
                fallback_used = False
        else:
            fallback_used = False
        
        value = qty * unit_cost
        total_value = total_value + value
        
        items.append({
            "id": tx.id,
            "product_id": tx.product_id,
            "product_name": prod.name if prod else "غير محدد",
            "product_sku": prod.sku if prod else None,
            "quantity": qty,
            "unit_cost": float(unit_cost),
            "total_value": float(value),
            "date": tx.created_at,
            "is_priced": unit_cost > 0,
            "fallback_used": fallback_used
        })
    
    return {
        "items": items,
        "unpriced_items": unpriced_items,
        "total_value": float(total_value),
        "priced_count": len([i for i in items if i["is_priced"]]),
        "unpriced_count": len(unpriced_items)
    }


def _get_supplier_old_debts(supplier_id: int, before_date: datetime):
    """جلب الديون القديمة للمورد (قبل الفترة)"""
    # يمكن إضافة منطق للديون القديمة إذا كانت مسجلة في مكان ما
    # حالياً نرجع 0
    return 0


def _get_sales_to_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    """جلب المبيعات للمورد (اشترى منا) - مع تحويل العملات إلى ILS"""
    from models import Payment, Sale
    
    # البحث عن الدفعات المرتبطة بمبيعات والمورد
    payments = db.session.query(Payment).options(
        joinedload(Payment.sale)
    ).filter(
        Payment.supplier_id == supplier_id,
        Payment.sale_id.isnot(None),
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).all()
    
    sales_list = []
    total_ils = Decimal('0.00')
    
    for payment in payments:
        sale = payment.sale
        if sale:
            amount_original = Decimal(str(payment.total_amount or 0))
            currency = payment.currency or "ILS"
            payment_date = payment.payment_date or datetime.utcnow()
            
            # تحويل إلى ILS
            amount_ils = _convert_to_ils(amount_original, currency, payment_date)
            total_ils = total_ils + amount_ils
            
            sales_list.append({
                "id": sale.id,
                "sale_number": sale.sale_number,
                "date": sale.sale_date,
                "amount_original": float(amount_original),
                "currency": currency,
                "amount_ils": float(amount_ils),
                "payment_id": payment.id,
                "notes": payment.notes or ""
            })
    
    return {
        "items": sales_list,
        "count": len(sales_list),
        "total": float(total_ils)  # الإجمالي بالشيكل
    }


def _get_services_to_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    """جلب الصيانة المقدمة للمورد - مع تحويل العملات إلى ILS"""
    from models import Payment, ServiceRequest
    
    # البحث عن الدفعات المرتبطة بطلبات صيانة والمورد
    payments = db.session.query(Payment).options(
        joinedload(Payment.service)
    ).filter(
        Payment.supplier_id == supplier_id,
        Payment.service_id.isnot(None),
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).all()
    
    services_list = []
    total_ils = Decimal('0.00')
    
    for payment in payments:
        service = payment.service
        if service:
            amount_original = Decimal(str(payment.total_amount or 0))
            currency = payment.currency or "ILS"
            payment_date = payment.payment_date or datetime.utcnow()
            
            # تحويل إلى ILS
            amount_ils = _convert_to_ils(amount_original, currency, payment_date)
            total_ils = total_ils + amount_ils
            
            services_list.append({
                "id": service.id,
                "service_number": service.service_number,
                "date": service.received_at or service.created_at,
                "amount_original": float(amount_original),
                "currency": currency,
                "amount_ils": float(amount_ils),
                "payment_id": payment.id,
                "notes": payment.notes or service.description or ""
            })
    
    return {
        "items": services_list,
        "count": len(services_list),
        "total": float(total_ils)  # الإجمالي بالشيكل
    }


def _get_cash_payments_to_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    """جلب الدفعات النقدية المباشرة للمورد (بدون مبيعات أو صيانة) - مع تحويل العملات"""
    from models import Payment
    
    # الدفعات OUT المباشرة للمورد (بدون sale_id أو service_id)
    payments = db.session.query(Payment).filter(
        Payment.supplier_id == supplier_id,
        Payment.direction == PaymentDirection.OUT.value,
        Payment.status == PaymentStatus.COMPLETED.value,
        Payment.sale_id.is_(None),
        Payment.service_id.is_(None),
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).all()
    
    total_ils = Decimal('0.00')
    for payment in payments:
        amount_original = Decimal(str(payment.total_amount or 0))
        currency = payment.currency or "ILS"
        payment_date = payment.payment_date or datetime.utcnow()
        
        # تحويل إلى ILS
        amount_ils = _convert_to_ils(amount_original, currency, payment_date)
        total_ils = total_ils + amount_ils
    
    return float(total_ils)


def _get_returns_to_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    """جلب المرتجعات للمورد (قطع رجعناها له)"""
    from models import ExchangeTransaction, Warehouse, WarehouseType
    
    # جلب مستودعات التبادل للمورد
    exchange_warehouses = db.session.query(Warehouse.id).filter(
        Warehouse.supplier_id == supplier_id,
        Warehouse.warehouse_type == WarehouseType.EXCHANGE.value
    ).all()
    
    warehouse_ids = [w[0] for w in exchange_warehouses]
    
    if not warehouse_ids:
        return {"items": [], "total_value": 0, "count": 0}
    
    # جلب المعاملات OUT (قطع رجعناها للمورد)
    transactions = db.session.query(ExchangeTransaction).options(
        joinedload(ExchangeTransaction.product)
    ).filter(
        ExchangeTransaction.warehouse_id.in_(warehouse_ids),
        ExchangeTransaction.direction.in_(['OUT', 'RETURN', 'CONSIGN_OUT']),
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to
    ).all()
    
    items = []
    total_value = Decimal('0.00')
    
    for tx in transactions:
        prod = tx.product
        qty = Decimal(str(tx.quantity or 0))
        unit_cost = Decimal(str(tx.unit_cost or 0))
        if unit_cost == 0 and prod and prod.purchase_price:
            unit_cost = Decimal(str(prod.purchase_price))
        value = qty * unit_cost
        total_value = total_value + value
        
        items.append({
            "id": tx.id,
            "product_name": prod.name if prod else "غير محدد",
            "quantity": int(qty),
            "unit_cost": float(unit_cost),
            "total_value": float(value),
            "date": tx.created_at
        })
    
    return {
        "items": items,
        "count": len(items),
        "total_value": float(total_value)
    }


def _get_previous_supplier_settlements(supplier_id: int, before_date: datetime):
    """جلب التسويات السابقة للمورد"""
    from models import SupplierSettlement
    from sqlalchemy import desc
    
    settlements = db.session.query(SupplierSettlement).filter(
        SupplierSettlement.supplier_id == supplier_id,
        SupplierSettlement.created_at < before_date
    ).order_by(desc(SupplierSettlement.created_at)).limit(5).all()
    
    return [{
        "id": s.id,
        "code": s.code,
        "date": s.created_at,
        "status": s.status,
        "total_due": float(s.total_due or 0),
        "currency": s.currency,
        "from_date": s.from_date,
        "to_date": s.to_date
    } for s in settlements]


def _get_supplier_consignment_value(supplier_id: int):
    """حساب قيمة العهدة المتبقية في المخزون"""
    from models import Warehouse, WarehouseType, StockLevel, Product
    from sqlalchemy import func
    
    # جلب مستودعات التبادل للمورد
    exchange_warehouses = db.session.query(Warehouse.id).filter(
        Warehouse.supplier_id == supplier_id,
        Warehouse.warehouse_type == WarehouseType.EXCHANGE.value
    ).all()
    
    warehouse_ids = [w[0] for w in exchange_warehouses]
    
    if not warehouse_ids:
        return 0
    
    # حساب القيمة الإجمالية للعهدة
    rows = db.session.query(
        func.sum(StockLevel.quantity * Product.purchase_price)
    ).join(
        Product, Product.id == StockLevel.product_id
    ).filter(
        StockLevel.warehouse_id.in_(warehouse_ids),
        StockLevel.quantity > 0
    ).scalar() or 0
    
    return float(rows)