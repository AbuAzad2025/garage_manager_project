from datetime import datetime
from flask import Blueprint, render_template, request, abort, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_
from extensions import db, limiter, csrf
from models import OnlinePayment, OnlinePreOrder, Customer
from utils import log_audit, super_only

admin_reports_bp = Blueprint(
    "admin_reports",
    __name__,
    url_prefix="/admin/reports",
    template_folder="templates/admin/reports",
)

@admin_reports_bp.before_request
@super_only
def _guard_admin_reports():
    pass

def _mask_pan(pan: str) -> str:
    if not pan:
        return ""
    digits = "".join(ch for ch in pan if ch.isdigit())
    if len(digits) <= 4:
        return "*" * max(0, len(digits) - 1) + digits[-1:]
    return "**** **** **** " + digits[-4:]

@admin_reports_bp.route("/cards", methods=["GET"], endpoint="cards")
@login_required
@limiter.limit("30/minute")
def cards():
    q = (
        OnlinePayment.query
        .join(OnlinePreOrder, OnlinePayment.order_id == OnlinePreOrder.id)
        .join(Customer, OnlinePreOrder.customer_id == Customer.id)
    )

    start = request.args.get("start")
    end = request.args.get("end")
    status = request.args.get("status")
    search = (request.args.get("q") or "").strip()

    if start:
        try:
            dt = datetime.strptime(start, "%Y-%m-%d")
            q = q.filter(OnlinePayment.created_at >= dt)
        except Exception:
            pass

    if end:
        try:
            dt = datetime.strptime(end, "%Y-%m-%d")
            q = q.filter(OnlinePayment.created_at < dt.replace(hour=23, minute=59, second=59))
        except Exception:
            pass

    if status and status in ("PENDING", "SUCCESS", "FAILED", "REFUNDED"):
        q = q.filter(OnlinePayment.status == status)

    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            OnlinePayment.payment_ref.ilike(like),
            Customer.name.ilike(like),
            Customer.phone.ilike(like),
        ))

    rows = q.order_by(OnlinePayment.created_at.desc()).limit(500).all()
    return render_template("admin/reports/cards.html", rows=rows)

@admin_reports_bp.route("/cards/<int:pid>/reveal", methods=["POST"], endpoint="cards_reveal")
@login_required
@limiter.limit("5/minute;20/hour;50/day")
def cards_reveal(pid: int):
    op = db.session.get(OnlinePayment, pid)
    if not op:
        abort(404)

    pan_decrypted = op.decrypt_card_number()
    pan_masked = _mask_pan(pan_decrypted or "")

    reveal_enabled = bool(current_app.config.get("REVEAL_PAN_ENABLED", False))
    if not reveal_enabled:
        log_audit(
            "OnlinePayment",
            op.id,
            "reveal_card_attempt",
            old_data=None,
            new_data={"payment_ref": op.payment_ref, "result": "blocked_by_config"}
        )
        return jsonify({
            "ok": False,
            "reason": "disabled_by_config",
            "payment_ref": op.payment_ref,
            "pan_masked": pan_masked,
            "brand": op.card_brand,
            "last4": op.card_last4,
            "holder": op.cardholder_name,
            "expiry": op.card_expiry,
            "amount": float(op.amount or 0),
            "currency": op.currency,
            "created_at": op.created_at.isoformat() if getattr(op, "created_at", None) else None,
        }), 403

    data = request.get_json(silent=True) or request.form or {}
    password = (data.get("password") or "").strip()
    if not password:
        log_audit("OnlinePayment", op.id, "reveal_card_attempt", old_data=None,
                  new_data={"payment_ref": op.payment_ref, "result": "missing_password"})
        return jsonify({"ok": False, "error": "password_required", "pan_masked": pan_masked}), 400

    try:
        check_ok = current_user.check_password(password)
    except Exception:
        check_ok = False

    if not check_ok:
        log_audit("OnlinePayment", op.id, "reveal_card_attempt", old_data=None,
                  new_data={"payment_ref": op.payment_ref, "result": "bad_password"})
        return jsonify({"ok": False, "error": "invalid_password", "pan_masked": pan_masked}), 403

    log_audit("OnlinePayment", op.id, "reveal_card", old_data=None,
              new_data={"payment_ref": op.payment_ref, "result": "success"})
    return jsonify({
        "ok": True,
        "payment_ref": op.payment_ref,
        "pan": pan_decrypted,
        "pan_masked": pan_masked,
        "brand": op.card_brand,
        "last4": op.card_last4,
        "holder": op.cardholder_name,
        "expiry": op.card_expiry,
        "amount": float(op.amount or 0),
        "currency": op.currency,
        "created_at": op.created_at.isoformat() if getattr(op, "created_at", None) else None,
    })
