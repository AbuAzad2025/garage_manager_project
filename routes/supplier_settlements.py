# File: supplier_settlements.py
from datetime import datetime, date as _date, time as _time
from decimal import Decimal, ROUND_HALF_UP
from flask import Blueprint, request, jsonify, render_template, url_for, abort
from flask_login import login_required
from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
from utils import permission_required
from models import Supplier, PaymentDirection, PaymentMethod, SupplierSettlement, SupplierSettlementStatus, build_supplier_settlement_draft, AuditLog
import json

supplier_settlements_bp = Blueprint("supplier_settlements_bp", __name__, url_prefix="/suppliers")

@supplier_settlements_bp.route("/settlements", methods=["GET"], endpoint="list")
@login_required
@permission_required("manage_vendors")
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

def _q2(v) -> float:
    return float(Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def _due_direction(v: Decimal):
    if v > 0:
        return PaymentDirection.OUTGOING.value
    return PaymentDirection.INCOMING.value

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
@permission_required("manage_vendors")
def preview(supplier_id):
    supplier = _get_supplier_or_404(supplier_id)
    dfrom, dto, err = _extract_range_from_request()
    if err:
        return jsonify({"success": False, "error": err}), 400
    draft = build_supplier_settlement_draft(supplier.id, dfrom, dto, currency=supplier.currency)
    lines = getattr(draft, "lines", []) or []
    data = {
        "success": True,
        "supplier": {"id": supplier.id, "name": supplier.name, "currency": supplier.currency},
        "from": dfrom.isoformat(),
        "to": dto.isoformat(),
        "code": draft.code,
        "totals": {
            "gross": _q2(draft.total_gross),
            "due": _q2(draft.total_due),
        },
        "lines": [{
            "source_type": l.source_type,
            "source_id": l.source_id,
            "description": l.description,
            "product_id": l.product_id,
            "product_name": getattr(l, 'product_name', None),
            "product_sku": getattr(l, 'product_sku', None),
            "quantity": _q2(l.quantity) if l.quantity is not None else None,
            "unit_price": _q2(l.unit_price) if l.unit_price is not None else None,
            "gross_amount": _q2(l.gross_amount),
        } for l in lines],
    }
    return jsonify(data)

@supplier_settlements_bp.route("/<int:supplier_id>/settlements/create", methods=["POST"])
@login_required
@permission_required("manage_vendors")
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
@permission_required("manage_vendors")
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
@permission_required("manage_vendors")
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
@permission_required("manage_vendors")
def show(settlement_id):
    ss = db.session.get(SupplierSettlement, settlement_id)
    if not ss:
        abort(404)
    return render_template("vendors/suppliers/settlement_preview.html", ss=ss)


# ===== نظام التسوية الذكي للموردين =====

@supplier_settlements_bp.route("/<int:supplier_id>/settlement", methods=["GET"], endpoint="supplier_settlement")
@login_required
@permission_required("manage_vendors")
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
    
    return render_template(
        "vendors/suppliers/smart_settlement.html",
        supplier=supplier,
        balance_data=balance_data,
        date_from=date_from,
        date_to=date_to
    )


def _calculate_smart_supplier_balance(supplier_id: int, date_from: datetime, date_to: datetime):
    """حساب الرصيد الذكي للمورد مع التفاصيل المتقدمة"""
    try:
        from models import Expense, Sale, ExchangeTransaction, Payment, Product
        from sqlalchemy import func, desc
        
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
        
        # 5. التحقق من القطع غير المسعرة
        unpriced_items = _check_unpriced_items_for_supplier(supplier_id, date_from, date_to)
        
        # 6. آخر تسوية
        last_settlement = _get_last_supplier_settlement(supplier_id)
        
        # 7. تفاصيل العمليات
        operations_details = _get_supplier_operations_details(supplier_id, date_from, date_to)
        
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
            "recommendation": _get_settlement_recommendation(balance, supplier.currency),
            "unpriced_items": unpriced_items,
            "last_settlement": last_settlement,
            "operations_details": operations_details
        }
        
    except Exception as e:
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
            "direction": "OUTGOING",
            "warnings": []
        }
    else:  # الباقي عليه
        return {
            "action": "قبض",
            "message": f"يجب قبض {abs(balance):.2f} {currency} من المورد",
            "amount": abs(balance),
            "direction": "INCOMING",
            "warnings": []
        }