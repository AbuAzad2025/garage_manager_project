
from datetime import datetime, date as _date, time as _time
from decimal import Decimal, ROUND_HALF_UP
from flask import Blueprint, request, jsonify, render_template, url_for, abort
from flask_login import login_required
from sqlalchemy import and_
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
import utils
from models import Supplier, PaymentDirection, PaymentMethod, PaymentStatus, SupplierSettlement, SupplierSettlementStatus, build_supplier_settlement_draft, AuditLog, SaleStatus
import json

supplier_settlements_bp = Blueprint("supplier_settlements_bp", __name__, url_prefix="/suppliers")

def get_unpriced_supplier_products():
    """
    جلب القطع غير المسعّرة للموردين/التجار
    Returns: list of dicts with product info
    """
    from models import (
        ExchangeTransaction, Product, Supplier, 
        Warehouse, WarehouseType, StockLevel
    )
    from sqlalchemy import or_
    
    unpriced_items = []
    
    # جلب جميع معاملات التبادل مع الموردين
    transactions = db.session.query(
        ExchangeTransaction.supplier_id,
        Supplier.name.label("supplier_name"),
        Product.id.label("product_id"),
        Product.name.label("product_name"),
        Product.sku,
        Product.purchase_price,
        Product.selling_price,
        ExchangeTransaction.unit_cost
    ).join(
        Supplier, Supplier.id == ExchangeTransaction.supplier_id
    ).join(
        Product, Product.id == ExchangeTransaction.product_id
    ).filter(
        ExchangeTransaction.supplier_id.isnot(None),
        or_(
            Product.purchase_price == None,
            Product.purchase_price == 0,
            Product.selling_price == None,
            Product.selling_price == 0,
            ExchangeTransaction.unit_cost == None,
            ExchangeTransaction.unit_cost == 0
        )
    ).distinct().all()
    
    seen_products = set()
    
    for tx in transactions:
        key = (tx.supplier_id, tx.product_id)
        if key in seen_products:
            continue
        seen_products.add(key)
        
        # التحقق من وجود مخزون
        has_stock = db.session.query(StockLevel).filter(
            StockLevel.product_id == tx.product_id,
            StockLevel.quantity > 0
        ).first() is not None
        
        missing = []
        if not tx.purchase_price or tx.purchase_price == 0:
            missing.append("purchase_price")
        if not tx.selling_price or tx.selling_price == 0:
            missing.append("selling_price")
        if not tx.unit_cost or tx.unit_cost == 0:
            missing.append("unit_cost")
        
        unpriced_items.append({
            "supplier_id": tx.supplier_id,
            "supplier_name": tx.supplier_name,
            "product_id": tx.product_id,
            "product_name": tx.product_name,
            "sku": tx.sku,
            "purchase_price": float(tx.purchase_price or 0),
            "selling_price": float(tx.selling_price or 0),
            "unit_cost": float(tx.unit_cost or 0),
            "has_stock": has_stock,
            "missing": missing
        })
    
    return unpriced_items

@supplier_settlements_bp.route("/unpriced-items", methods=["GET"])
@login_required
def check_unpriced_items():
    """التحقق من القطع غير المسعّرة للموردين/التجار"""
    unpriced = get_unpriced_supplier_products()
    return jsonify({
        "success": True,
        "count": len(unpriced),
        "items": unpriced
    })

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
    حساب التسوية الذكية الشاملة للمورد
    
    المعادلة المحاسبية الصحيحة:
    ═════════════════════════════════════════════════════════════
    حقوق المورد = القطع المأخوذة منه (من مستودع التبادل)
    التزامات المورد = مبيعات له + صيانة له
    الدفعات المسددة = دفعنا له (OUT) + دفع لنا (IN) + المرتجعات (OUT)
    
    الرصيد النهائي = حقوقه - التزاماته - الدفعات المسددة
    ═════════════════════════════════════════════════════════════
    
    ملاحظات مهمة:
    - جميع العملات تُحول إلى ILS قبل الجمع
    - القطع غير المسعرة: يجب تسعيرها قبل التوثيق
    - المرتجعات (OUT) تُخصم من حقوقه
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
        # 🔵 الرصيد الافتتاحي (الرصيد السابق قبل الفترة)
        # ═══════════════════════════════════════════════════════════
        
        opening_balance = Decimal(str(getattr(supplier, 'opening_balance', 0) or 0))
        
        # ═══════════════════════════════════════════════════════════
        # 🟢 حقوق المورد (ما له علينا - قطع أخذناها منه)
        # ═══════════════════════════════════════════════════════════
        
        # 1. القطع من مستودع التبادل (IN)
        exchange_items = _get_supplier_exchange_items(supplier_id, date_from, date_to)
        
        # حقوق المورد
        supplier_rights = Decimal(str(exchange_items.get("total_value_ils", 0)))
        
        # ═══════════════════════════════════════════════════════════
        # 🔴 التزامات المورد (ما عليه لنا)
        # ═══════════════════════════════════════════════════════════
        
        # 2. مبيعات له (كعميل)
        sales_to_supplier = _get_sales_to_supplier(supplier_id, date_from, date_to)
        
        # 3. صيانة له (كعميل)
        services_to_supplier = _get_services_to_supplier(supplier_id, date_from, date_to)
        
        # 4. الحجوزات المسبقة (إذا كان عميلاً)
        preorders_to_supplier = _get_supplier_preorders(supplier_id, date_from, date_to)
        
        # التزامات المورد
        supplier_obligations = Decimal(str(sales_to_supplier.get("total_ils", 0))) + \
                               Decimal(str(services_to_supplier.get("total_ils", 0))) + \
                               Decimal(str(preorders_to_supplier.get("total_ils", 0) if isinstance(preorders_to_supplier, dict) else 0))
        
        # ═══════════════════════════════════════════════════════════
        # 💰 الدفعات والمرتجعات (كلها تُخصم من الرصيد)
        # ═══════════════════════════════════════════════════════════
        
        # 4. دفعنا له (OUT)
        payments_to_supplier = _get_payments_to_supplier(supplier_id, supplier, date_from, date_to)
        
        # 5. دفع لنا (IN)
        payments_from_supplier = _get_payments_from_supplier(supplier_id, supplier, date_from, date_to)
        
        # 6. مرتجعات له (OUT في Exchange)
        returns_to_supplier = _get_returns_to_supplier(supplier_id, date_from, date_to)
        
        # ═══════════════════════════════════════════════════════════
        # الحساب المحاسبي الصحيح
        # ═══════════════════════════════════════════════════════════
        
        # صافي قبل الدفعات
        net_before_payments = supplier_rights - supplier_obligations
        
        # الدفعات والمرتجعات
        paid_to_supplier = Decimal(str(payments_to_supplier.get("total_ils", 0)))
        received_from_supplier = Decimal(str(payments_from_supplier.get("total_ils", 0)))
        returns_value = Decimal(str(returns_to_supplier.get("total_value_ils", 0)))
        
        # الرصيد النهائي = الرصيد الافتتاحي + (حقوقه - التزاماته) - (دفعنا له) + (دفع لنا) - (مرتجعات له)
        # مثال: رصيد افتتاحي 50 + (له 100 - عليه 30) - دفعنا له 60 + دفع لنا 20 = 80
        balance = opening_balance + net_before_payments - paid_to_supplier + received_from_supplier - returns_value
        
        # القطع غير المسعرة
        unpriced_items = exchange_items.get("unpriced_items", [])
        
        # التسويات السابقة
        previous_settlements = _get_previous_supplier_settlements(supplier_id, date_from)
        
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
            # 🔵 الرصيد الافتتاحي
            "opening_balance": {
                "amount": float(opening_balance),
                "currency": "ILS",
                "direction": "له علينا" if opening_balance > 0 else "عليه لنا" if opening_balance < 0 else "متوازن"
            },
            # 🟢 حقوق المورد
            "rights": {
                "exchange_items": exchange_items,
                "total": float(supplier_rights)
            },
            # 🔴 التزامات المورد
            "obligations": {
                "sales_to_supplier": sales_to_supplier,
                "services_to_supplier": services_to_supplier,
                "preorders_to_supplier": preorders_to_supplier,
                "total": float(supplier_obligations)
            },
            # 💰 الدفعات والمرتجعات
            "payments": {
                "paid_to_supplier": payments_to_supplier,
                "received_from_supplier": payments_from_supplier,
                "returns_to_supplier": returns_to_supplier,
                "total_paid": float(paid_to_supplier),
                "total_received": float(received_from_supplier),
                "total_returns": float(returns_value),
                "total_settled": float(paid_to_supplier + received_from_supplier + returns_value)
            },
            # 🎯 الرصيد
            "balance": {
                "gross": float(net_before_payments),
                "net": float(balance),
                "amount": float(balance),
                "direction": "له علينا" if balance > 0 else "عليه لنا" if balance < 0 else "متوازن",
                "payment_direction": "OUT" if balance > 0 else "IN" if balance < 0 else None,
                "action": "ندفع له" if balance > 0 else "يدفع لنا" if balance < 0 else "لا شيء",
                "currency": "ILS",
                "formula": f"({float(opening_balance):.2f} + {float(supplier_rights):.2f} - {float(supplier_obligations):.2f} - {float(paid_to_supplier):.2f} + {float(received_from_supplier):.2f} - {float(returns_value):.2f}) = {float(balance):.2f}"
            },
            # معلومات إضافية
            "unpriced_items": unpriced_items,
            "has_unpriced": len(unpriced_items) > 0,
            "previous_settlements": previous_settlements,
            "currency_note": "⚠️ جميع المبالغ بالشيكل (ILS) بعد التحويل"
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
    """
    جلب القطع من مستودع التبادل (ما أخذناه من المورد)
    مع تحويل العملات إلى ILS
    
    ✅ يجلب من:
    1. ExchangeTransaction (معاملات التبادل المسجلة)
    2. StockLevel في مستودعات التبادل (المخزون الحالي)
    """
    from models import ExchangeTransaction, Warehouse, WarehouseType, Product, StockLevel
    
    # ═══════════════════════════════════════════════════════════
    # 1. جلب من ExchangeTransaction (المعاملات التاريخية)
    # ═══════════════════════════════════════════════════════════
    transactions = db.session.query(ExchangeTransaction).options(
        joinedload(ExchangeTransaction.product)
    ).filter(
        ExchangeTransaction.supplier_id == supplier_id,
        ExchangeTransaction.direction.in_(['IN', 'PURCHASE', 'CONSIGN_IN']),
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to
    ).all()
    
    items = []
    unpriced_items = []
    total_ils = Decimal('0.00')
    
    # معالجة المعاملات التاريخية
    for tx in transactions:
        prod = tx.product
        qty = Decimal(str(tx.quantity or 0))
        unit_cost = Decimal(str(tx.unit_cost or 0))
        
        # محاولة الحصول على السعر
        if unit_cost == 0:
            if prod and prod.purchase_price:
                unit_cost = Decimal(str(prod.purchase_price))
            else:
                # قطعة غير مسعّرة - يجب تسعيرها قبل التوثيق
                unpriced_items.append({
                    "id": tx.id,
                    "product_id": tx.product_id,
                    "product_name": prod.name if prod else "غير محدد",
                    "product_sku": prod.sku if prod else None,
                    "quantity": int(qty),
                    "date": tx.created_at.strftime("%Y-%m-%d") if tx.created_at else "",
                    "suggested_price": 0
                })
                # تجاهلها في الحساب حتى يتم تسعيرها
                continue
        
        value_ils = qty * unit_cost
        
        # ⚠️ ملاحظة: ExchangeTransaction.unit_cost مُفترض أنه بـ ILS
        # إذا كانت هناك عملات أخرى، استخدم:
        # value_ils = _convert_to_ils(value, transaction_currency, tx.created_at)
        
        total_ils += value_ils
        
        items.append({
            "id": tx.id,
            "product_id": tx.product_id,
            "product_name": prod.name if prod else "غير محدد",
            "product_sku": prod.sku if prod else None,
            "quantity": int(qty),
            "unit_cost": float(unit_cost),
            "total_value": float(value_ils),
            "date": tx.created_at.strftime("%Y-%m-%d") if tx.created_at else "",
            "currency": "ILS"
        })
    
    # ═══════════════════════════════════════════════════════════
    # 2. جلب المخزون الحالي من مستودعات التبادل
    # ═══════════════════════════════════════════════════════════
    exchange_warehouses = db.session.query(Warehouse).filter(
        Warehouse.warehouse_type == WarehouseType.EXCHANGE.value
    ).all()
    
    for wh in exchange_warehouses:
        stocks = db.session.query(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Product.sku,
            StockLevel.quantity,
            Product.purchase_price,
            StockLevel.created_at
        ).join(
            StockLevel, StockLevel.product_id == Product.id
        ).filter(
            StockLevel.warehouse_id == wh.id,
            Product.supplier_id == supplier_id,
            StockLevel.quantity > 0
        ).all()
        
        for stock in stocks:
            qty = Decimal(str(stock.quantity or 0))
            unit_cost = Decimal(str(stock.purchase_price or 0))
            
            if unit_cost == 0:
                unpriced_items.append({
                    "product_id": stock.product_id,
                    "product_name": stock.product_name,
                    "product_sku": stock.sku,
                    "quantity": int(qty),
                    "warehouse_name": wh.name,
                    "date": stock.created_at.strftime("%Y-%m-%d") if stock.created_at else "",
                    "suggested_price": 0
                })
                continue
            
            value_ils = qty * unit_cost
            total_ils += value_ils
            
            items.append({
                "product_id": stock.product_id,
                "product_name": stock.product_name,
                "product_sku": stock.sku,
                "quantity": int(qty),
                "unit_cost": float(unit_cost),
                "total_value": float(value_ils),
                "warehouse_name": wh.name,
                "date": stock.created_at.strftime("%Y-%m-%d") if stock.created_at else "",
                "currency": "ILS",
                "source": "stock"  # للتمييز عن المعاملات
            })
    
    return {
        "items": items,
        "unpriced_items": unpriced_items,
        "total_value_ils": float(total_ils),
        "count": len(items)
    }


def _get_sales_to_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    """
    مبيعات للمورد (كعميل) - تُخصم من حقوقه
    """
    from models import Sale, SaleLine, Product, Supplier
    
    supplier = db.session.get(Supplier, supplier_id)
    if not supplier or not supplier.customer_id:
        return {"items": [], "total_ils": 0.0, "count": 0}
    
    sales = db.session.query(
        Sale.id.label("sale_id"),
        Sale.sale_number,
        Sale.sale_date,
        Sale.currency,
        Sale.total_amount,
        Sale.status
    ).filter(
        Sale.customer_id == supplier.customer_id,
        Sale.sale_date >= date_from,
        Sale.sale_date <= date_to,
        Sale.status == SaleStatus.CONFIRMED
    ).order_by(Sale.sale_date).all()
    
    items = []
    total_ils = Decimal('0.00')
    
    for sale in sales:
        # جلب تفاصيل الأسطر
        sale_lines = db.session.query(
            Product.name.label("product_name"),
            SaleLine.quantity,
            SaleLine.unit_price
        ).join(
            Product, Product.id == SaleLine.product_id
        ).filter(
            SaleLine.sale_id == sale.sale_id
        ).all()
        
        amount_ils = _convert_to_ils(Decimal(str(sale.total_amount or 0)), sale.currency, sale.sale_date)
        total_ils += amount_ils
        
        items.append({
            "sale_id": sale.sale_id,
            "sale_number": sale.sale_number,
            "date": sale.sale_date.strftime("%Y-%m-%d") if sale.sale_date else "",
            "products": [{"name": sl.product_name, "qty": sl.quantity, "price": float(sl.unit_price)} for sl in sale_lines],
            "amount": float(sale.total_amount or 0),
            "currency": sale.currency,
            "amount_ils": float(amount_ils),
            "status": sale.status
        })
    
    return {
        "items": items,
        "total_ils": float(total_ils),
        "count": len(items)
    }


def _get_services_to_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    """
    رسوم صيانة على المورد (كعميل) - تُخصم من حقوقه
    """
    from models import ServiceRequest, Supplier
    
    supplier = db.session.get(Supplier, supplier_id)
    if not supplier or not supplier.customer_id:
        return {"items": [], "total_ils": 0.0, "count": 0}
    
    services = db.session.query(ServiceRequest).filter(
        ServiceRequest.customer_id == supplier.customer_id,
        ServiceRequest.received_at >= date_from,
        ServiceRequest.received_at <= date_to,
        ServiceRequest.status == 'COMPLETED'
    ).order_by(ServiceRequest.received_at).all()
    
    items = []
    total_ils = Decimal('0.00')
    
    for service in services:
        amount_ils = _convert_to_ils(Decimal(str(service.total_amount or 0)), service.currency, service.received_at)
        total_ils += amount_ils
        
        items.append({
            "service_id": service.id,
            "service_number": service.service_number,
            "date": service.received_at.strftime("%Y-%m-%d") if service.received_at else "",
            "description": service.description or service.problem_description,
            "amount": float(service.total_amount or 0),
            "currency": service.currency,
            "amount_ils": float(amount_ils),
            "status": service.status
        })
    
    return {
        "items": items,
        "total_ils": float(total_ils),
        "count": len(items)
    }


def _get_payments_to_supplier(supplier_id: int, supplier, date_from: datetime, date_to: datetime):
    """
    دفعات دفعناها للمورد (OUT) - تُخصم من حقوقه
    
    تشمل:
    1. الدفعات المرتبطة مباشرة بـ supplier_id
    2. الدفعات المرتبطة بـ customer_id (العميل المرتبط بالمورد)
    3. الدفعات المرتبطة بمبيعات للعميل (entity_type = SALE)
    """
    from models import Payment, PaymentDirection, PaymentStatus, PaymentEntityType, Sale
    
    items = []
    total_ils = Decimal('0.00')
    
    # 1. الدفعات المرتبطة مباشرة بالمورد
    direct_payments = db.session.query(Payment).filter(
        Payment.supplier_id == supplier_id,
        Payment.direction == PaymentDirection.OUT,
        Payment.status == PaymentStatus.COMPLETED,
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).all()
    
    for payment in direct_payments:
        amount_ils = _convert_to_ils(Decimal(str(payment.total_amount or 0)), payment.currency, payment.payment_date)
        total_ils += amount_ils
        
        items.append({
            "payment_id": payment.id,
            "payment_number": payment.payment_number,
            "date": payment.payment_date.strftime("%Y-%m-%d") if payment.payment_date else "",
            "method": payment.method,
            "check_number": payment.check_number,
            "amount": float(payment.total_amount or 0),
            "currency": payment.currency,
            "amount_ils": float(amount_ils),
            "notes": payment.notes,
            "source": "supplier"
        })
    
    # 2. الدفعات المرتبطة بالعميل المرتبط بالمورد
    if supplier.customer_id:
        customer_payments = db.session.query(Payment).filter(
            Payment.customer_id == supplier.customer_id,
            Payment.direction == PaymentDirection.OUT,
            Payment.status == PaymentStatus.COMPLETED,
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to
        ).all()
        
        for payment in customer_payments:
            if not any(item['payment_id'] == payment.id for item in items):
                amount_ils = _convert_to_ils(Decimal(str(payment.total_amount or 0)), payment.currency, payment.payment_date)
                total_ils += amount_ils
                
                items.append({
                    "payment_id": payment.id,
                    "payment_number": payment.payment_number,
                    "date": payment.payment_date.strftime("%Y-%m-%d") if payment.payment_date else "",
                    "method": payment.method,
                    "check_number": payment.check_number,
                    "amount": float(payment.total_amount or 0),
                    "currency": payment.currency,
                    "amount_ils": float(amount_ils),
                    "notes": payment.notes,
                    "source": "customer"
                })
        
        # 3. الدفعات المرتبطة بمبيعات للعميل (entity_type = SALE)
        sale_payments = db.session.query(Payment).join(
            Sale, Sale.id == Payment.sale_id
        ).filter(
            Payment.entity_type == PaymentEntityType.SALE,
            Sale.customer_id == supplier.customer_id,
            Payment.direction == PaymentDirection.OUT,
            Payment.status == PaymentStatus.COMPLETED,
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to
        ).all()
        
        for payment in sale_payments:
            if not any(item['payment_id'] == payment.id for item in items):
                amount_ils = _convert_to_ils(Decimal(str(payment.total_amount or 0)), payment.currency, payment.payment_date)
                total_ils += amount_ils
                
                items.append({
                    "payment_id": payment.id,
                    "payment_number": payment.payment_number,
                    "date": payment.payment_date.strftime("%Y-%m-%d") if payment.payment_date else "",
                    "method": payment.method,
                    "check_number": payment.check_number,
                    "amount": float(payment.total_amount or 0),
                    "currency": payment.currency,
                    "amount_ils": float(amount_ils),
                    "notes": payment.notes,
                    "source": "sale"
                })
    
    # ترتيب حسب التاريخ
    items.sort(key=lambda x: x['date'])
    
    return {
        "items": items,
        "total_ils": float(total_ils),
        "count": len(items)
    }


def _get_payments_from_supplier(supplier_id: int, supplier, date_from: datetime, date_to: datetime):
    """
    دفعات استلمناها من المورد (IN) - تُحسب له (تُخصم)
    
    تشمل:
    1. الدفعات المرتبطة مباشرة بـ supplier_id
    2. الدفعات المرتبطة بـ customer_id (العميل المرتبط بالمورد)
    3. الدفعات المرتبطة بمبيعات للعميل (entity_type = SALE)
    """
    from models import Payment, PaymentDirection, PaymentStatus, PaymentEntityType, Sale
    
    items = []
    total_ils = Decimal('0.00')
    
    # 1. الدفعات المرتبطة مباشرة بالمورد
    direct_payments = db.session.query(Payment).filter(
        Payment.supplier_id == supplier_id,
        Payment.direction == PaymentDirection.IN,
        Payment.status == PaymentStatus.COMPLETED,
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).all()
    
    for payment in direct_payments:
        amount_ils = _convert_to_ils(Decimal(str(payment.total_amount or 0)), payment.currency, payment.payment_date)
        total_ils += amount_ils
        
        items.append({
            "payment_id": payment.id,
            "payment_number": payment.payment_number,
            "date": payment.payment_date.strftime("%Y-%m-%d") if payment.payment_date else "",
            "method": payment.method,
            "check_number": payment.check_number,
            "amount": float(payment.total_amount or 0),
            "currency": payment.currency,
            "amount_ils": float(amount_ils),
            "notes": payment.notes,
            "source": "supplier"
        })
    
    # 2. الدفعات المرتبطة بالعميل المرتبط بالمورد
    if supplier.customer_id:
        customer_payments = db.session.query(Payment).filter(
            Payment.customer_id == supplier.customer_id,
            Payment.direction == PaymentDirection.IN,
            Payment.status == PaymentStatus.COMPLETED,
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to
        ).all()
        
        for payment in customer_payments:
            if not any(item['payment_id'] == payment.id for item in items):
                amount_ils = _convert_to_ils(Decimal(str(payment.total_amount or 0)), payment.currency, payment.payment_date)
                total_ils += amount_ils
                
                items.append({
                    "payment_id": payment.id,
                    "payment_number": payment.payment_number,
                    "date": payment.payment_date.strftime("%Y-%m-%d") if payment.payment_date else "",
                    "method": payment.method,
                    "check_number": payment.check_number,
                    "amount": float(payment.total_amount or 0),
                    "currency": payment.currency,
                    "amount_ils": float(amount_ils),
                    "notes": payment.notes,
                    "source": "customer"
                })
        
        # 3. الدفعات المرتبطة بمبيعات للعميل (entity_type = SALE)
        sale_payments = db.session.query(Payment).join(
            Sale, Sale.id == Payment.sale_id
        ).filter(
            Payment.entity_type == PaymentEntityType.SALE,
            Sale.customer_id == supplier.customer_id,
            Payment.direction == PaymentDirection.IN,
            Payment.status == PaymentStatus.COMPLETED,
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to
        ).all()
        
        for payment in sale_payments:
            if not any(item['payment_id'] == payment.id for item in items):
                amount_ils = _convert_to_ils(Decimal(str(payment.total_amount or 0)), payment.currency, payment.payment_date)
                total_ils += amount_ils
                
                items.append({
                    "payment_id": payment.id,
                    "payment_number": payment.payment_number,
                    "date": payment.payment_date.strftime("%Y-%m-%d") if payment.payment_date else "",
                    "method": payment.method,
                    "check_number": payment.check_number,
                    "amount": float(payment.total_amount or 0),
                    "currency": payment.currency,
                    "amount_ils": float(amount_ils),
                    "notes": payment.notes,
                    "source": "sale"
                })
    
    # ترتيب حسب التاريخ
    items.sort(key=lambda x: x['date'])
    
    return {
        "items": items,
        "total_ils": float(total_ils),
        "count": len(items)
    }


def _get_supplier_preorders(supplier_id: int, date_from: datetime, date_to: datetime):
    """
    حجوزات مسبقة للمورد (إذا كان عميلاً)
    """
    from models import PreOrder, Supplier
    
    supplier = db.session.get(Supplier, supplier_id)
    if not supplier or not supplier.customer_id:
        return {"items": [], "total_ils": 0.0, "count": 0}
    
    items = []
    total_ils = Decimal('0.00')
    
    # جلب الحجوزات المسبقة
    preorders = db.session.query(PreOrder).filter(
        PreOrder.customer_id == supplier.customer_id,
        PreOrder.status.in_(['CONFIRMED', 'COMPLETED', 'DELIVERED']),
        PreOrder.created_at >= date_from,
        PreOrder.created_at <= date_to
    ).all()
    
    for po in preorders:
        # تحويل إلى ILS
        amount_ils = _convert_to_ils(
            Decimal(str(po.total_amount or 0)),
            po.currency or 'ILS',
            po.created_at or datetime.utcnow()
        )
        total_ils += amount_ils
        
        items.append({
            "preorder_id": po.id,
            "preorder_number": po.preorder_number or f"PO-{po.id}",
            "date": po.created_at.strftime("%Y-%m-%d") if po.created_at else "",
            "total_amount": float(po.total_amount or 0),
            "amount_ils": float(amount_ils),
            "currency": po.currency or 'ILS',
            "status": po.status
        })
    
    return {
        "items": items,
        "total_ils": float(total_ils),
        "count": len(items)
    }


def _get_returns_to_supplier(supplier_id: int, date_from: datetime, date_to: datetime):
    """
    مرتجعات للمورد (OUT من Exchange) - قطع رجعناها له
    """
    from models import ExchangeTransaction, Warehouse, WarehouseType, Product
    
    # جلب مستودعات التبادل
    exchange_warehouses = db.session.query(Warehouse.id).filter(
        Warehouse.supplier_id == supplier_id,
        Warehouse.warehouse_type == WarehouseType.EXCHANGE.value
    ).all()
    
    warehouse_ids = [w[0] for w in exchange_warehouses]
    
    if not warehouse_ids:
        return {"items": [], "total_value_ils": 0.0, "count": 0}
    
    # المعاملات OUT (قطع رجعناها للمورد)
    transactions = db.session.query(ExchangeTransaction).options(
        joinedload(ExchangeTransaction.product)
    ).filter(
        ExchangeTransaction.warehouse_id.in_(warehouse_ids),
        ExchangeTransaction.direction.in_(['OUT', 'RETURN', 'CONSIGN_OUT']),
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to
    ).all()
    
    items = []
    total_ils = Decimal('0.00')
    
    for tx in transactions:
        prod = tx.product
        qty = Decimal(str(tx.quantity or 0))
        unit_cost = Decimal(str(tx.unit_cost or 0))
        
        if unit_cost == 0 and prod and prod.purchase_price:
            unit_cost = Decimal(str(prod.purchase_price))
        
        value_ils = qty * unit_cost
        total_ils += value_ils
        
        items.append({
            "id": tx.id,
            "product_name": prod.name if prod else "غير محدد",
            "product_sku": prod.sku if prod else None,
            "quantity": int(qty),
            "unit_cost": float(unit_cost),
            "total_value": float(value_ils),
            "date": tx.created_at.strftime("%Y-%m-%d") if tx.created_at else "",
            "currency": "ILS"
        })
    
    return {
        "items": items,
        "total_value_ils": float(total_ils),
        "count": len(items)
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


def _get_supplier_old_debts(supplier_id: int, before_date: datetime):
    """جلب الديون القديمة للمورد (قبل الفترة)"""
    # يمكن إضافة منطق للديون القديمة إذا كانت مسجلة في مكان ما
    # حالياً نرجع 0
    return 0


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