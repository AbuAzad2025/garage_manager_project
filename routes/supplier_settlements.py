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
