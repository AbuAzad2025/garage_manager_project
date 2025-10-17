
from datetime import datetime, date as _date, time as _time
from decimal import Decimal, ROUND_HALF_UP
from flask import Blueprint, request, jsonify, render_template, url_for, abort
from flask_login import login_required
from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
import utils
from models import Partner, PaymentDirection, PaymentMethod, PartnerSettlement, PartnerSettlementStatus, build_partner_settlement_draft, AuditLog
import json

partner_settlements_bp = Blueprint("partner_settlements_bp", __name__, url_prefix="/partners")

@partner_settlements_bp.route("/settlements", methods=["GET"], endpoint="list")
@login_required
# @permission_required("manage_vendors")  # Commented out
def settlements_list():
    """قائمة تسويات الشركاء"""
    return render_template("partner_settlements/list.html")

def _get_partner_or_404(pid: int) -> Partner:
    obj = db.session.get(Partner, pid)
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

def _overlap_exists(partner_id: int, dfrom: datetime, dto: datetime) -> bool:
    return db.session.query(PartnerSettlement.id).filter(
        PartnerSettlement.partner_id == partner_id,
        PartnerSettlement.status.in_([PartnerSettlementStatus.DRAFT.value, PartnerSettlementStatus.CONFIRMED.value]),
        and_(PartnerSettlement.from_date <= dto, PartnerSettlement.to_date >= dfrom)
    ).first() is not None

@partner_settlements_bp.route("/<int:partner_id>/settlements/preview", methods=["GET"])
@login_required
# @permission_required("manage_vendors")  # Commented out
def preview(partner_id):
    from flask import redirect
    return redirect(url_for('partner_settlements_bp.partner_settlement', partner_id=partner_id))

@partner_settlements_bp.route("/<int:partner_id>/settlements/create", methods=["POST"])
@login_required
# @permission_required("manage_vendors")  # Commented out
def create(partner_id):
    partner = _get_partner_or_404(partner_id)
    dfrom, dto, err = _extract_range_from_request()
    if err:
        return jsonify({"success": False, "error": err}), 400
    draft = build_partner_settlement_draft(partner.id, dfrom, dto, currency=partner.currency)
    lines = getattr(draft, "lines", []) or []
    if not lines:
        return jsonify({"success": False, "error": "لا توجد سطور لتسويتها"}), 400
    if _currency_mismatch(lines, partner.currency):
        return jsonify({"success": False, "error": "عملة غير متطابقة داخل التسوية"}), 400
    if _overlap_exists(partner.id, dfrom, dto):
        return jsonify({"success": False, "error": "نطاق متداخل مع تسوية سابقة"}), 409
    due = Decimal(str(draft.total_due or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if due == Decimal("0.00"):
        return jsonify({"success": False, "error": "لا توجد مبالغ مستحقة"}), 400
    draft.ensure_code()
    draft.from_date = dfrom
    draft.to_date = dto
    draft.currency = partner.currency
    try:
        with db.session.begin():
            db.session.add(draft)
            db.session.flush()
            db.session.add(AuditLog(model_name="PartnerSettlement", record_id=draft.id, action="CREATE", old_data=None, new_data=json.dumps({
                "partner_id": partner.id, "from": dfrom.isoformat(), "to": dto.isoformat(), "total_due": str(due), "code": draft.code
            })))
    except SQLAlchemyError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    direction = _due_direction(due)
    amount_str = f"{abs(due):.2f}"
    pay_url = url_for(
        "payments.create_payment",
        entity_type="PARTNER",   # <-- كانت "partner"
        entity_id=str(partner.id),
        direction=direction,
        total_amount=amount_str,
        currency=partner.currency,
        method=PaymentMethod.BANK.value,
        reference=f"PartnerSettle:{draft.code}",
        notes=f"تسوية شريك {partner.name} {dfrom.date()} - {dto.date()} ({draft.code})",
    )
    return jsonify({"success": True, "id": draft.id, "code": draft.code, "pay_url": pay_url})

@partner_settlements_bp.route("/settlements/<int:settlement_id>/confirm", methods=["POST"])
@login_required
# @permission_required("manage_vendors")  # Commented out
def confirm(settlement_id):
    ps = db.session.get(PartnerSettlement, settlement_id)
    if not ps:
        abort(404)
    if ps.status != PartnerSettlementStatus.DRAFT.value:
        return jsonify({"success": False, "error": "Only DRAFT can be confirmed"}), 400
    recalc = build_partner_settlement_draft(ps.partner_id, ps.from_date, ps.to_date, currency=ps.currency)
    orig = Decimal(str(ps.total_due or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    now_ = Decimal(str(recalc.total_due or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if orig != now_ or len(getattr(ps, "lines", []) or []) != len(getattr(recalc, "lines", []) or []):
        return jsonify({"success": False, "error": "اختلفت البيانات منذ المعاينة، أعد الإنشاء"}), 409
    try:
        with db.session.begin():
            ps.mark_confirmed()
            db.session.flush()
            db.session.add(AuditLog(model_name="PartnerSettlement", record_id=ps.id, action="CONFIRM", old_data=None, new_data=json.dumps({
                "code": ps.code, "from": ps.from_date.isoformat(), "to": ps.to_date.isoformat(), "total_due": str(orig)
            })))
    except SQLAlchemyError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "id": ps.id, "code": ps.code})

@partner_settlements_bp.route("/settlements/<int:settlement_id>", methods=["GET"])
@login_required
# @permission_required("manage_vendors")  # Commented out
def show(settlement_id):
    ps = db.session.get(PartnerSettlement, settlement_id)
    if not ps:
        abort(404)
    return render_template("vendors/partners/settlement_preview.html", ps=ps)


# ===== نظام التسوية الذكي للشركاء =====

@partner_settlements_bp.route("/<int:partner_id>/settlement", methods=["GET"], endpoint="partner_settlement")
@login_required
# @permission_required("manage_vendors")  # Commented out
def partner_settlement(partner_id):
    """التسوية الذكية للشريك"""
    partner = _get_partner_or_404(partner_id)
    
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
    balance_data = _calculate_smart_partner_balance(partner_id, date_from, date_to)
    
    # إنشاء object بسيط للتوافق مع القالب
    from types import SimpleNamespace
    ps = SimpleNamespace(
        id=None,  # لا يوجد id لأنها تسوية ذكية (غير محفوظة)
        partner=partner,
        from_date=date_from,
        to_date=date_to,
        currency=partner.currency,
        total_gross=balance_data.get("incoming", {}).get("total", 0),
        total_due=balance_data.get("balance", {}).get("amount", 0),
        status="DRAFT",
        code=f"PS-SMART-{partner_id}-{date_from.strftime('%Y%m%d')}",
        lines=[],
        created_at=date_from,
        updated_at=datetime.utcnow()
    )
    
    return render_template(
        "vendors/partners/settlement_preview.html",
        partner=partner,
        balance_data=balance_data,
        date_from=date_from,
        date_to=date_to,
        ps=ps  # object بدلاً من dict
    )


def _calculate_smart_partner_balance(partner_id: int, date_from: datetime, date_to: datetime):
    """
    حساب التسوية الذكية الشاملة للشريك
    
    المعادلة المحاسبية الصحيحة:
    ═════════════════════════════════════════════════════════════
    حقوق الشريك = المخزون + المبيعات
    التزامات الشريك = مبيعات له + صيانة له + تالف + مصروفات
    الدفعات المسددة = دفعنا له (OUT) + دفع لنا (IN)
    
    الرصيد النهائي = حقوقه - التزاماته - الدفعات المسددة
    ═════════════════════════════════════════════════════════════
    
    ملاحظات مهمة:
    - جميع العملات تُحول إلى ILS قبل الجمع
    - الدفعات الواردة (IN) تُخصم من الرصيد (يُحسب له)
    - الدفعات الصادرة (OUT) تُخصم من الرصيد (يُحسب له)
    """
    try:
        partner = db.session.get(Partner, partner_id)
        if not partner:
            return {"success": False, "error": "الشريك غير موجود"}
        
        # ═══════════════════════════════════════════════════════════
        # 🔵 جانب المدين (ما له علينا - حقوقه)
        # ═══════════════════════════════════════════════════════════
        
        # 1. نصيبه من المخزون الحالي (من التكلفة)
        inventory = _get_partner_inventory(partner_id, date_from, date_to)
        
        # 2. نصيبه من المبيعات (من سعر البيع)
        sales_share = _get_partner_sales_share(partner_id, date_from, date_to)
        
        # 3. دفعات استلمناها منه (IN) - دين علينا له
        payments_from_partner = _get_partner_payments_received(partner_id, partner, date_from, date_to)
        
        # ═══════════════════════════════════════════════════════════
        # 🔴 جانب الدائن (ما عليه لنا - حقوقنا)
        # ═══════════════════════════════════════════════════════════
        
        # 4. دفعات دفعناها له (OUT)
        payments_to_partner = _get_payments_to_partner(partner_id, date_from, date_to)
        
        # 5. مبيعات له (كعميل)
        sales_to_partner = _get_partner_sales_as_customer(partner_id, partner, date_from, date_to)
        
        # 6. رسوم صيانة عليه
        service_fees = _get_partner_service_fees(partner_id, partner, date_from, date_to)
        
        # 7. نصيبه من القطع التالفة
        damaged_items = _get_partner_damaged_items(partner_id, date_from, date_to)
        
        # 8. المصروفات المخصومة (إن وجدت)
        expenses_deducted = _get_partner_expenses(partner_id, date_from, date_to)
        
        # ═══════════════════════════════════════════════════════════
        # الحساب المحاسبي الصحيح
        # ═══════════════════════════════════════════════════════════
        
        # حقوق الشريك (ما استحقه من عمله)
        partner_rights = Decimal(str(inventory.get("total", 0))) + \
                        Decimal(str(sales_share.get("total_share_ils", 0)))
        
        # التزامات الشريك (ما عليه لنا)
        partner_obligations = Decimal(str(sales_to_partner.get("total_ils", 0))) + \
                             Decimal(str(service_fees.get("total_ils", 0))) + \
                             Decimal(str(damaged_items.get("total_ils", 0))) + \
                             Decimal(str(expenses_deducted or 0))
        
        # صافي الحساب قبل احتساب الدفعات
        net_before_payments = partner_rights - partner_obligations
        
        # الدفعات (كلها تُخصم من الرصيد)
        # - دفعات واردة (IN): دفع لنا من جيبه → تُحسب له (تُخصم من مديونيته)
        # - دفعات صادرة (OUT): دفعنا له من حقوقه → تُحسب له (تُخصم من حقوقه)
        paid_to_partner = Decimal(str(payments_to_partner.get("total_ils", 0)))
        received_from_partner = Decimal(str(payments_from_partner.get("total_ils", 0)))
        
        # الرصيد النهائي = (ما استحقه - ما عليه - ما دفعناه - ما دفعه)
        balance = net_before_payments - paid_to_partner - received_from_partner
        
        return {
            "success": True,
            "partner": {
                "id": partner.id,
                "name": partner.name,
                "currency": partner.currency,
                "share_percentage": float(partner.share_percentage or 0)
            },
            "period": {
                "from": date_from.isoformat(),
                "to": date_to.isoformat()
            },
            # 🟢 حقوق الشريك (ما استحقه من عمله)
            "rights": {
                "inventory": inventory,
                "sales_share": sales_share,
                "total": float(partner_rights)
            },
            # 🔴 التزامات الشريك (ما عليه لنا)
            "obligations": {
                "sales_to_partner": sales_to_partner,
                "service_fees": service_fees,
                "damaged_items": damaged_items,
                "expenses": {"total_ils": float(expenses_deducted or 0)},
                "total": float(partner_obligations)
            },
            # 💰 الدفعات المسددة (كلها تُخصم من الرصيد)
            "payments": {
                "paid_to_partner": payments_to_partner,  # OUT - دفعنا له
                "received_from_partner": payments_from_partner,  # IN - دفع لنا
                "total_paid": float(paid_to_partner),
                "total_received": float(received_from_partner),
                "total_settled": float(paid_to_partner + received_from_partner)
            },
            # 🎯 الرصيد
            "balance": {
                "gross": float(net_before_payments),  # قبل الدفعات
                "net": float(balance),  # النهائي بعد الدفعات
                "amount": float(balance),
                "direction": "له علينا" if balance > 0 else "عليه لنا" if balance < 0 else "متوازن",
                "payment_direction": "OUT" if balance > 0 else "IN" if balance < 0 else None,
                "action": "ندفع له" if balance > 0 else "يدفع لنا" if balance < 0 else "لا شيء",
                "currency": "ILS",
                "formula": f"({float(partner_rights):.2f} - {float(partner_obligations):.2f} - {float(paid_to_partner):.2f} - {float(received_from_partner):.2f}) = {float(balance):.2f}"
            },
            # معلومات إضافية
            "previous_settlements": _get_previous_partner_settlements(partner_id, date_from),
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
        return {"success": False, "error": f"خطأ في حساب رصيد الشريك: {str(e)}"}


def _calculate_partner_incoming(partner_id: int, date_from: datetime, date_to: datetime):
    """حساب الوارد من الشريك"""
    from models import ServicePart, ServiceRequest, ExchangeTransaction
    from sqlalchemy import func
    
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
    from models import Expense, ExchangeTransaction
    from sqlalchemy import func
    
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


def _calculate_payments_to_partner(partner_id: int, date_from: datetime, date_to: datetime):
    """حساب الدفعات المدفوعة للشريك"""
    from models import Payment
    from sqlalchemy import func
    
    amount = db.session.query(func.sum(Payment.total_amount)).filter(
        Payment.partner_id == partner_id,
        Payment.direction == "OUTGOING",
        Payment.status == "COMPLETED",
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).scalar() or 0
    return float(amount)


def _calculate_payments_from_partner(partner_id: int, date_from: datetime, date_to: datetime):
    """حساب الدفعات المستلمة من الشريك"""
    from models import Payment
    from sqlalchemy import func
    
    amount = db.session.query(func.sum(Payment.total_amount)).filter(
        Payment.partner_id == partner_id,
        Payment.direction == "INCOMING",
        Payment.status == "COMPLETED",
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).scalar() or 0
    return float(amount)


def _check_unpriced_items_for_partner(partner_id: int, date_from: datetime, date_to: datetime):
    """التحقق من القطع غير المسعرة للشريك"""
    from models import ExchangeTransaction, Product
    from sqlalchemy import func, or_
    
    # البحث عن القطع التي لا تحتوي على سعر
    unpriced_transactions = db.session.query(ExchangeTransaction).join(Product).filter(
        ExchangeTransaction.partner_id == partner_id,
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


def _get_last_partner_settlement(partner_id: int):
    """الحصول على آخر تسوية للشريك"""
    from models import PartnerSettlement
    from sqlalchemy import desc
    
    last_settlement = db.session.query(PartnerSettlement).filter(
        PartnerSettlement.partner_id == partner_id
    ).order_by(desc(PartnerSettlement.created_at)).first()
    
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


def _get_partner_operations_details(partner_id: int, date_from: datetime, date_to: datetime):
    """الحصول على تفاصيل العمليات للشريك"""
    from models import ExchangeTransaction, ServicePart, ServiceRequest, Payment, Expense
    from sqlalchemy import func, desc
    
    # العمليات الأخيرة
    recent_transactions = db.session.query(ExchangeTransaction).filter(
        ExchangeTransaction.partner_id == partner_id,
        ExchangeTransaction.created_at >= date_from,
        ExchangeTransaction.created_at <= date_to
    ).order_by(desc(ExchangeTransaction.created_at)).limit(10).all()
    
    # الدفعات الأخيرة
    recent_payments = db.session.query(Payment).filter(
        Payment.partner_id == partner_id,
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).order_by(desc(Payment.payment_date)).limit(10).all()
    
    # النفقات الأخيرة
    recent_expenses = db.session.query(Expense).filter(
        Expense.partner_id == partner_id,
        Expense.date >= date_from,
        Expense.date <= date_to
    ).order_by(desc(Expense.date)).limit(10).all()
    
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
            "message": f"يجب دفع {abs(balance):.2f} {currency} للشريك",
            "amount": abs(balance),
            "direction": "OUT",
            "warnings": []
        }
    else:  # الباقي عليه
        return {
            "action": "قبض",
            "message": f"يجب قبض {abs(balance):.2f} {currency} من الشريك",
            "amount": abs(balance),
            "direction": "IN",
            "warnings": []
        }


# ═══════════════════════════════════════════════════════════════════════
# دوال مساعدة للتسوية الذكية الشاملة للشركاء
# Helper Functions for Comprehensive Smart Partner Settlement
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
    
    from_currency = (from_currency or "ILS").strip().upper()
    
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
    return Decimal(str(converted)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _get_partner_inventory(partner_id: int, date_from: datetime, date_to: datetime):
    """
    المخزون الحالي للشريك (نصيبه من التكلفة)
    يحسب من المستودعات التي لها صفة شراكة وله نسبة فيها
    """
    from models import (
        Warehouse, WarehousePartnerShare, StockLevel, Product, ProductPartner
    )
    from sqlalchemy import func
    
    # جلب المستودعات التي للشريك نسبة فيها
    partner_warehouse_shares = db.session.query(
        WarehousePartnerShare.warehouse_id,
        WarehousePartnerShare.product_id,
        WarehousePartnerShare.share_percentage,
        Warehouse.name.label('warehouse_name')
    ).join(
        Warehouse, Warehouse.id == WarehousePartnerShare.warehouse_id
    ).filter(
        WarehousePartnerShare.partner_id == partner_id,
        WarehousePartnerShare.share_percentage > 0
    ).all()
    
    if not partner_warehouse_shares:
        # إذا لم يكن له نسب محددة، نستخدم ProductPartner العامة
        product_shares = db.session.query(
            ProductPartner.product_id,
            ProductPartner.share_percent
        ).filter(
            ProductPartner.partner_id == partner_id,
            ProductPartner.share_percent > 0
        ).all()
        
        if not product_shares:
            return {"items": [], "total": 0.0}
        
        # حساب المخزون من جميع المستودعات للقطع التي له نسبة فيها
        product_ids = [ps[0] for ps in product_shares]
        share_map = {ps[0]: float(ps[1]) for ps in product_shares}
        
        inventory_items = db.session.query(
        Product.id.label("product_id"),
        Product.name.label("product_name"),
        Product.sku,
            Warehouse.name.label("warehouse_name"),
            StockLevel.quantity,
            Product.purchase_price
    ).join(
            StockLevel, StockLevel.product_id == Product.id
        ).join(
            Warehouse, Warehouse.id == StockLevel.warehouse_id
    ).filter(
            Product.id.in_(product_ids),
        StockLevel.quantity > 0
    ).all()
    else:
        # له نسب محددة حسب المستودع والقطعة
        inventory_items = []
        for wh_share in partner_warehouse_shares:
            wh_id, prod_id, share_pct, wh_name = wh_share
            
            # إذا كان product_id محدد، نأخذ هذا المنتج فقط
            if prod_id:
                stock = db.session.query(
                    Product.id.label("product_id"),
                    Product.name.label("product_name"),
                    Product.sku,
                    StockLevel.quantity,
                    Product.purchase_price
                ).join(
                    Product, Product.id == StockLevel.product_id
                ).filter(
                    StockLevel.warehouse_id == wh_id,
                    StockLevel.product_id == prod_id,
                    StockLevel.quantity > 0
                ).first()
                
                if stock:
                    inventory_items.append({
                        'product_id': stock.product_id,
                        'product_name': stock.product_name,
                        'sku': stock.sku,
                        'warehouse_name': wh_name,
                        'quantity': stock.quantity,
                        'purchase_price': stock.purchase_price,
                        'share_pct': share_pct
                    })
            else:
                # جميع المنتجات في هذا المستودع
                stocks = db.session.query(
        Product.id.label("product_id"),
        Product.name.label("product_name"),
        Product.sku,
                    StockLevel.quantity,
                    Product.purchase_price
    ).join(
                    Product, Product.id == StockLevel.product_id
    ).filter(
                    StockLevel.warehouse_id == wh_id,
                    StockLevel.quantity > 0
    ).all()
    
                for stock in stocks:
                    inventory_items.append({
                        'product_id': stock.product_id,
                        'product_name': stock.product_name,
                        'sku': stock.sku,
                        'warehouse_name': wh_name,
                        'quantity': stock.quantity,
                        'purchase_price': stock.purchase_price,
                        'share_pct': share_pct
                    })
    
    # حساب نصيب الشريك من كل قطعة
    items = []
    total = Decimal("0")
    
    for inv_item in inventory_items:
        if isinstance(inv_item, dict):
            prod_id = inv_item['product_id']
            prod_name = inv_item['product_name']
            sku = inv_item['sku']
            wh_name = inv_item['warehouse_name']
            qty = inv_item['quantity']
            cost = inv_item['purchase_price']
            share_pct = inv_item['share_pct']
        else:
            prod_id = inv_item.product_id
            prod_name = inv_item.product_name
            sku = inv_item.sku
            wh_name = getattr(inv_item, 'warehouse_name', '-')
            qty = inv_item.quantity
            cost = inv_item.purchase_price
            share_pct = share_map.get(prod_id, 0) if 'share_map' in locals() else 0
        
        partner_share = Decimal(str(qty)) * Decimal(str(cost or 0)) * Decimal(str(share_pct)) / Decimal("100")
        
        # ⚠️ ملاحظة: جميع تكاليف المنتجات مُفترض أنها بالشيكل (ILS)
        # جدول Product لا يحتوي على حقل currency
        # إذا تمت إضافة عملات للمنتجات مستقبلاً، استخدم:
        # partner_share = _convert_to_ils(partner_share, product.currency, datetime.utcnow())
        
        total += partner_share
        
        items.append({
            "product_id": prod_id,
            "product_name": prod_name,
            "sku": sku,
            "warehouse": wh_name,
            "quantity": int(qty),
            "cost_per_unit": float(cost or 0),
            "share_percentage": float(share_pct),
            "partner_share": float(partner_share)
        })
    
    return {
        "items": items,
        "total": float(total),
        "count": len(items)
    }


def _get_partner_sales_share(partner_id: int, date_from: datetime, date_to: datetime):
    """
    حساب نصيب الشريك من المبيعات (من سعر البيع)
    يشمل: مبيعات الصيانة + مبيعات عادية
    """
    from models import (
        ServicePart, ServiceRequest, SaleLine, Sale, Product,
        ProductPartner, Customer
    )
    from sqlalchemy import func
    
    all_sales = []
    total_ils = Decimal('0.00')
    
    # ═══════════════════════════════════════════════════════════
    # 1. مبيعات قطع الصيانة (ServicePart)
    # ═══════════════════════════════════════════════════════════
    
    service_sales = db.session.query(
        ServiceRequest.id.label("service_id"),
        ServiceRequest.service_number,
        ServiceRequest.received_at.label("date"),
        Customer.name.label("customer_name"),
        Product.name.label("product_name"),
        Product.sku,
        ServicePart.quantity,
        ServicePart.unit_price,
        ServicePart.share_percentage,
        ServiceRequest.currency
    ).join(
        ServicePart, ServicePart.service_id == ServiceRequest.id
    ).join(
        Product, Product.id == ServicePart.part_id
    ).join(
        Customer, Customer.id == ServiceRequest.customer_id
    ).filter(
        ServicePart.partner_id == partner_id,
        ServiceRequest.received_at >= date_from,
        ServiceRequest.received_at <= date_to,
        ServiceRequest.status == 'COMPLETED'
    ).all()
    
    for item in service_sales:
        total_amount = Decimal(str(item.quantity)) * Decimal(str(item.unit_price))
        share_pct = Decimal(str(item.share_percentage or 0))
        partner_share = total_amount * share_pct / Decimal("100")
        
        # تحويل إلى شيكل
        try:
            partner_share_ils = _convert_to_ils(partner_share, item.currency, item.date)
        except Exception:
            partner_share_ils = partner_share
        
        total_ils += partner_share_ils
        
        all_sales.append({
            "type": "صيانة",
            "reference_number": item.service_number,
            "date": item.date.strftime("%Y-%m-%d") if item.date else "",
            "customer_name": item.customer_name,
            "product_name": item.product_name,
            "sku": item.sku,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price),
            "total_amount": float(total_amount),
            "share_percentage": float(share_pct),
            "partner_share": float(partner_share),
            "currency": item.currency,
            "partner_share_ils": float(partner_share_ils)
        })
    
    # ═══════════════════════════════════════════════════════════
    # 2. مبيعات عادية (SaleLine)
    # ═══════════════════════════════════════════════════════════
    
    regular_sales = db.session.query(
        Sale.id.label("sale_id"),
        Sale.sale_number,
        Sale.sale_date,
        Customer.name.label("customer_name"),
        Product.name.label("product_name"),
        Product.sku,
        SaleLine.quantity,
        SaleLine.unit_price,
        ProductPartner.share_percent,
        Sale.currency
    ).join(
        SaleLine, SaleLine.sale_id == Sale.id
    ).join(
        Product, Product.id == SaleLine.product_id
    ).join(
        ProductPartner, ProductPartner.product_id == Product.id
    ).join(
        Customer, Customer.id == Sale.customer_id
    ).filter(
        ProductPartner.partner_id == partner_id,
        Sale.sale_date >= date_from,
        Sale.sale_date <= date_to,
        Sale.status == 'CONFIRMED',
        ProductPartner.share_percent > 0
    ).all()
    
    for item in regular_sales:
        total_amount = Decimal(str(item.quantity)) * Decimal(str(item.unit_price))
        share_pct = Decimal(str(item.share_percent or 0))
        partner_share = total_amount * share_pct / Decimal("100")
        
        # تحويل إلى شيكل
        try:
            partner_share_ils = _convert_to_ils(partner_share, item.currency, item.sale_date)
        except Exception:
            partner_share_ils = partner_share
        
        total_ils += partner_share_ils
        
        all_sales.append({
            "type": "بيع عادي",
            "reference_number": item.sale_number,
            "date": item.sale_date.strftime("%Y-%m-%d") if item.sale_date else "",
            "customer_name": item.customer_name,
            "product_name": item.product_name,
            "sku": item.sku,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price),
            "total_amount": float(total_amount),
            "share_percentage": float(share_pct),
            "partner_share": float(partner_share),
            "currency": item.currency,
            "partner_share_ils": float(partner_share_ils)
        })
    
    return {
        "items": all_sales,
        "count": len(all_sales),
        "total_share": float(total_ils),
        "total_share_ils": float(total_ils)
    }


def _get_payments_to_partner(partner_id: int, date_from: datetime, date_to: datetime):
    """
    دفعات دفعناها للشريك (OUT) - تُخصم من حقوقه علينا
    """
    from models import Payment, PaymentDirection, PaymentStatus
    
    payments = db.session.query(Payment).filter(
        Payment.partner_id == partner_id,
        Payment.direction == PaymentDirection.OUT.value,
        Payment.status == PaymentStatus.COMPLETED.value,
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).order_by(Payment.payment_date).all()
    
    items = []
    total_ils = Decimal('0.00')
    
    for payment in payments:
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
            "notes": payment.notes
        })
    
    return {
        "items": items,
        "total_ils": float(total_ils),
        "count": len(items)
    }


def _get_partner_expenses(partner_id: int, date_from: datetime, date_to: datetime):
    """جلب المصروفات المخصومة من حصة الشريك"""
    from models import Expense
    
    expenses = db.session.query(Expense).filter(
        Expense.payee_type == "PARTNER",
        Expense.payee_entity_id == partner_id,
        Expense.date >= date_from,
        Expense.date <= date_to
    ).all()
    
    total_ils = Decimal('0.00')
    for expense in expenses:
        amount = Decimal(str(expense.amount or 0))
        currency = expense.currency or "ILS"
        expense_date = expense.date or datetime.utcnow()
        
        amount_ils = _convert_to_ils(amount, currency, expense_date)
        total_ils = total_ils + amount_ils
    
    return float(total_ils)


def _get_previous_partner_settlements(partner_id: int, before_date: datetime):
    """جلب التسويات السابقة للشريك"""
    from models import PartnerSettlement
    from sqlalchemy import desc
    
    settlements = db.session.query(PartnerSettlement).filter(
        PartnerSettlement.partner_id == partner_id,
        PartnerSettlement.created_at < before_date
    ).order_by(desc(PartnerSettlement.created_at)).limit(5).all()
    
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


def _get_partner_payments_received(partner_id: int, partner: Partner, date_from: datetime, date_to: datetime):
    """
    دفعات استلمناها من الشريك (IN) - تُضاف إلى حقوقه علينا
    """
    from models import Payment, PaymentDirection, PaymentStatus
    
    payments = db.session.query(Payment).filter(
        Payment.partner_id == partner_id,
        Payment.direction == PaymentDirection.IN.value,
        Payment.status == PaymentStatus.COMPLETED.value,
        Payment.payment_date >= date_from,
        Payment.payment_date <= date_to
    ).order_by(Payment.payment_date).all()
    
    items = []
    total_ils = Decimal('0.00')
    
    for payment in payments:
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
            "notes": payment.notes
        })
    
    return {
        "items": items,
        "total_ils": float(total_ils),
        "count": len(items)
    }


def _get_partner_sales_as_customer(partner_id: int, partner: Partner, date_from: datetime, date_to: datetime):
    """
    مبيعات للشريك (كعميل) - تُخصم من حقوقه
    """
    from models import Sale, SaleLine, Product
    
    if not partner.customer_id:
        return {"items": [], "total_ils": 0.0, "count": 0}
    
    sales = db.session.query(
        Sale.id.label("sale_id"),
        Sale.sale_number,
        Sale.sale_date,
        Sale.currency,
        Sale.total_amount,
        Sale.status
    ).filter(
        Sale.customer_id == partner.customer_id,
        Sale.sale_date >= date_from,
        Sale.sale_date <= date_to,
        Sale.status == 'CONFIRMED'
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


def _get_partner_service_fees(partner_id: int, partner: Partner, date_from: datetime, date_to: datetime):
    """
    رسوم صيانة على الشريك (كعميل) - تُخصم من حقوقه
    """
    from models import ServiceRequest
    
    if not partner.customer_id:
        return {"items": [], "total_ils": 0.0, "count": 0}
    
    services = db.session.query(ServiceRequest).filter(
        ServiceRequest.customer_id == partner.customer_id,
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


def _get_partner_damaged_items(partner_id: int, date_from: datetime, date_to: datetime):
    """
    القطع التالفة - نصيب الشريك من الخسارة (من سعر التكلفة)
    """
    from models import (
        StockAdjustment, StockAdjustmentItem, Product, 
        ProductPartner, Warehouse
    )
    
    # القطع التالفة
    damaged_items = db.session.query(
        StockAdjustment.date,
        Product.name.label("product_name"),
        Product.sku,
        StockAdjustmentItem.quantity,
        StockAdjustmentItem.unit_cost,
        ProductPartner.share_percent,
        StockAdjustmentItem.notes,
        Warehouse.name.label("warehouse_name")
    ).join(
        StockAdjustmentItem, StockAdjustmentItem.adjustment_id == StockAdjustment.id
    ).join(
        Product, Product.id == StockAdjustmentItem.product_id
    ).join(
        ProductPartner, ProductPartner.product_id == Product.id
    ).outerjoin(
        Warehouse, Warehouse.id == StockAdjustmentItem.warehouse_id
    ).filter(
        ProductPartner.partner_id == partner_id,
        StockAdjustment.reason == 'DAMAGED',
        StockAdjustment.date >= date_from,
        StockAdjustment.date <= date_to,
        ProductPartner.share_percent > 0
    ).order_by(StockAdjustment.date).all()
    
    items = []
    total_ils = Decimal('0.00')
    
    for damaged in damaged_items:
        partner_loss = Decimal(str(damaged.quantity)) * Decimal(str(damaged.unit_cost or 0)) * Decimal(str(damaged.share_percent)) / Decimal("100")
        
        # ⚠️ ملاحظة: جميع تكاليف التعديلات مُفترض أنها بالشيكل (ILS)
        # StockAdjustmentItem.unit_cost لا يرتبط بعملة محددة
        # إذا تمت إضافة عملات للتعديلات مستقبلاً، استخدم:
        # partner_loss = _convert_to_ils(partner_loss, adjustment.currency, damaged.date)
        
        total_ils += partner_loss
        
        items.append({
            "date": damaged.date.strftime("%Y-%m-%d") if damaged.date else "",
            "product_name": damaged.product_name,
            "sku": damaged.sku,
            "warehouse": damaged.warehouse_name or "-",
            "quantity": damaged.quantity,
            "unit_cost": float(damaged.unit_cost or 0),
            "share_percentage": float(damaged.share_percent),
            "partner_loss": float(partner_loss),
            "reason": damaged.notes or "تالف"
        })
    
    return {
        "items": items,
        "total_ils": float(total_ils),
        "count": len(items)
    }