from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, url_for, abort
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
from utils import permission_required
from models import (
    Supplier, PaymentDirection, PaymentMethod,
    SupplierSettlement, SupplierSettlementStatus, build_supplier_settlement_draft
)

supplier_settlements_bp = Blueprint("supplier_settlements_bp", __name__, url_prefix="/suppliers")

def _get_supplier_or_404(sid: int) -> Supplier:
    obj = db.session.get(Supplier, sid)
    if not obj: abort(404)
    return obj

@supplier_settlements_bp.route("/<int:supplier_id>/settlements/preview", methods=["GET"])
@login_required
@permission_required("manage_vendors")
def preview(supplier_id):
    supplier = _get_supplier_or_404(supplier_id)
    try:
        dfrom = request.args.get("from")
        dto   = request.args.get("to")
        dfrom = datetime.fromisoformat(dfrom) if dfrom else datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        dto   = datetime.fromisoformat(dto)   if dto   else datetime.utcnow()
    except Exception:
        return jsonify({"success": False, "error": "Bad date ISO format"}), 400

    draft = build_supplier_settlement_draft(supplier.id, dfrom, dto, currency=supplier.currency)
    data = {
        "success": True,
        "supplier": {"id": supplier.id, "name": supplier.name, "currency": supplier.currency},
        "from": dfrom.isoformat(), "to": dto.isoformat(),
        "code": draft.code,
        "totals": {
            "gross": float(draft.total_gross or 0),
            "due":   float(draft.total_due or 0),
        },
        "lines": [{
            "source_type": l.source_type, "source_id": l.source_id, "description": l.description,
            "product_id": l.product_id,
            "quantity": float(l.quantity or 0) if l.quantity is not None else None,
            "unit_price": float(l.unit_price or 0) if l.unit_price is not None else None,
            "gross_amount": float(l.gross_amount or 0),
        } for l in draft.lines]
    }
    return jsonify(data)

@supplier_settlements_bp.route("/<int:supplier_id>/settlements/create", methods=["POST"])
@login_required
@permission_required("manage_vendors")
def create(supplier_id):
    supplier = _get_supplier_or_404(supplier_id)
    try:
        dfrom = request.form.get("from") or (request.json or {}).get("from")
        dto   = request.form.get("to")   or (request.json or {}).get("to")
        dfrom = datetime.fromisoformat(dfrom) if dfrom else datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        dto   = datetime.fromisoformat(dto)   if dto   else datetime.utcnow()
    except Exception:
        return jsonify({"success": False, "error": "Bad date ISO format"}), 400

    draft = build_supplier_settlement_draft(supplier.id, dfrom, dto, currency=supplier.currency)
    draft.ensure_code()
    db.session.add(draft)
    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400

    pay_url = url_for("payments.create_payment",
                      entity_type="supplier", entity_id=str(supplier.id),
                      direction=PaymentDirection.OUTGOING.value,
                      total_amount=f"{float(draft.total_due or 0):.2f}",
                      currency=supplier.currency, method=PaymentMethod.BANK.value,
                      reference=f"SupplierSettle:{draft.code}",
                      notes=f"تسوية مورد {supplier.name} {dfrom.date()} - {dto.date()} ({draft.code})")
    return jsonify({"success": True, "id": draft.id, "code": draft.code, "pay_url": pay_url})

@supplier_settlements_bp.route("/settlements/<int:settlement_id>/confirm", methods=["POST"])
@login_required
@permission_required("manage_vendors")
def confirm(settlement_id):
    ss = db.session.get(SupplierSettlement, settlement_id)
    if not ss: abort(404)
    if ss.status != SupplierSettlementStatus.DRAFT.value:
        return jsonify({"success": False, "error": "Only DRAFT can be confirmed"}), 400
    ss.mark_confirmed()
    db.session.commit()
    return jsonify({"success": True, "id": ss.id, "code": ss.code})

@supplier_settlements_bp.route("/settlements/<int:settlement_id>", methods=["GET"])
@login_required
@permission_required("manage_vendors")
def show(settlement_id):
    ss = db.session.get(SupplierSettlement, settlement_id)
    if not ss: abort(404)
    return render_template("vendors/suppliers/settlement_preview.html", ss=ss)
