from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, url_for, abort
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
from utils import permission_required
from models import (
    Partner, PaymentDirection, PaymentMethod,
    PartnerSettlement, PartnerSettlementStatus, build_partner_settlement_draft
)

partner_settlements_bp = Blueprint("partner_settlements_bp", __name__, url_prefix="/partners")

def _get_partner_or_404(pid: int) -> Partner:
    obj = db.session.get(Partner, pid)
    if not obj: abort(404)
    return obj

@partner_settlements_bp.route("/<int:partner_id>/settlements/preview", methods=["GET"])
@login_required
@permission_required("manage_vendors")
def preview(partner_id):
    partner = _get_partner_or_404(partner_id)
    try:
        dfrom = request.args.get("from")
        dto   = request.args.get("to")
        dfrom = datetime.fromisoformat(dfrom) if dfrom else datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        dto   = datetime.fromisoformat(dto)   if dto   else datetime.utcnow()
    except Exception:
        return jsonify({"success": False, "error": "Bad date ISO format"}), 400

    draft = build_partner_settlement_draft(partner.id, dfrom, dto, currency=partner.currency)
    data = {
        "success": True,
        "partner": {"id": partner.id, "name": partner.name, "currency": partner.currency},
        "from": dfrom.isoformat(), "to": dto.isoformat(),
        "code": draft.code,
        "totals": {
            "gross": float(draft.total_gross or 0),
            "share": float(draft.total_share or 0),
            "costs": float(draft.total_costs or 0),
            "due":   float(draft.total_due or 0),
        },
        "lines": [{
            "source_type": l.source_type, "source_id": l.source_id, "description": l.description,
            "product_id": l.product_id, "warehouse_id": l.warehouse_id,
            "quantity": float(l.quantity or 0) if l.quantity is not None else None,
            "unit_price": float(l.unit_price or 0) if l.unit_price is not None else None,
            "gross_amount": float(l.gross_amount or 0),
            "share_percent": float(l.share_percent or 0),
            "share_amount": float(l.share_amount or 0),
        } for l in draft.lines]
    }
    return jsonify(data)

@partner_settlements_bp.route("/<int:partner_id>/settlements/create", methods=["POST"])
@login_required
@permission_required("manage_vendors")
def create(partner_id):
    partner = _get_partner_or_404(partner_id)
    try:
        dfrom = request.form.get("from") or (request.json or {}).get("from")
        dto   = request.form.get("to")   or (request.json or {}).get("to")
        dfrom = datetime.fromisoformat(dfrom) if dfrom else datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        dto   = datetime.fromisoformat(dto)   if dto   else datetime.utcnow()
    except Exception:
        return jsonify({"success": False, "error": "Bad date ISO format"}), 400

    draft = build_partner_settlement_draft(partner.id, dfrom, dto, currency=partner.currency)
    draft.ensure_code()
    db.session.add(draft)
    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400

    pay_url = url_for("payments.create_payment",
                      entity_type="partner", entity_id=str(partner.id),
                      direction=PaymentDirection.OUTGOING.value,
                      total_amount=f"{float(draft.total_due or 0):.2f}",
                      currency=partner.currency, method=PaymentMethod.BANK.value,
                      reference=f"PartnerSettle:{draft.code}",
                      notes=f"تسوية شريك {partner.name} {dfrom.date()} - {dto.date()} ({draft.code})")
    return jsonify({"success": True, "id": draft.id, "code": draft.code, "pay_url": pay_url})

@partner_settlements_bp.route("/settlements/<int:settlement_id>/confirm", methods=["POST"])
@login_required
@permission_required("manage_vendors")
def confirm(settlement_id):
    ps = db.session.get(PartnerSettlement, settlement_id)
    if not ps: abort(404)
    if ps.status != PartnerSettlementStatus.DRAFT.value:
        return jsonify({"success": False, "error": "Only DRAFT can be confirmed"}), 400
    ps.mark_confirmed()
    db.session.commit()
    return jsonify({"success": True, "id": ps.id, "code": ps.code})

@partner_settlements_bp.route("/settlements/<int:settlement_id>", methods=["GET"])
@login_required
@permission_required("manage_vendors")
def show(settlement_id):
    ps = db.session.get(PartnerSettlement, settlement_id)
    if not ps: abort(404)
    return render_template("vendors/partners/settlement_preview.html", ps=ps)
