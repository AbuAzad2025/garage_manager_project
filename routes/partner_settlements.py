# File: partner_settlements.py
from datetime import datetime, date as _date, time as _time
from decimal import Decimal, ROUND_HALF_UP
from flask import Blueprint, request, jsonify, render_template, url_for, abort
from flask_login import login_required
from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
from utils import permission_required
from models import Partner, PaymentDirection, PaymentMethod, PartnerSettlement, PartnerSettlementStatus, build_partner_settlement_draft, AuditLog
import json

partner_settlements_bp = Blueprint("partner_settlements_bp", __name__, url_prefix="/partners")

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

def _overlap_exists(partner_id: int, dfrom: datetime, dto: datetime) -> bool:
    return db.session.query(PartnerSettlement.id).filter(
        PartnerSettlement.partner_id == partner_id,
        PartnerSettlement.status.in_([PartnerSettlementStatus.DRAFT.value, PartnerSettlementStatus.CONFIRMED.value]),
        and_(PartnerSettlement.from_date <= dto, PartnerSettlement.to_date >= dfrom)
    ).first() is not None

@partner_settlements_bp.route("/<int:partner_id>/settlements/preview", methods=["GET"])
@login_required
@permission_required("manage_vendors")
def preview(partner_id):
    partner = _get_partner_or_404(partner_id)
    dfrom, dto, err = _extract_range_from_request()
    if err:
        return jsonify({"success": False, "error": err}), 400
    draft = build_partner_settlement_draft(partner.id, dfrom, dto, currency=partner.currency)
    lines = getattr(draft, "lines", []) or []
    data = {
        "success": True,
        "partner": {"id": partner.id, "name": partner.name, "currency": partner.currency},
        "from": dfrom.isoformat(),
        "to": dto.isoformat(),
        "code": draft.code,
        "totals": {
            "gross": _q2(draft.total_gross),
            "share": _q2(draft.total_share),
            "costs": _q2(draft.total_costs),
            "due": _q2(draft.total_due),
        },
        "lines": [{
            "source_type": l.source_type,
            "source_id": l.source_id,
            "description": l.description,
            "product_id": l.product_id,
            "warehouse_id": l.warehouse_id,
            "quantity": _q2(l.quantity) if l.quantity is not None else None,
            "unit_price": _q2(l.unit_price) if l.unit_price is not None else None,
            "gross_amount": _q2(l.gross_amount),
            "share_percent": _q2(l.share_percent),
            "share_amount": _q2(l.share_amount),
        } for l in lines]
    }
    return jsonify(data)

@partner_settlements_bp.route("/<int:partner_id>/settlements/create", methods=["POST"])
@login_required
@permission_required("manage_vendors")
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
@permission_required("manage_vendors")
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
@permission_required("manage_vendors")
def show(settlement_id):
    ps = db.session.get(PartnerSettlement, settlement_id)
    if not ps:
        abort(404)
    return render_template("vendors/partners/settlement_preview.html", ps=ps)
