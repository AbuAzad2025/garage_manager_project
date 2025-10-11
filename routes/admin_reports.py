# admin_reports.py - Admin Reports Routes
# Location: /garage_manager/routes/admin_reports.py
# Description: Administrative reports and analytics routes

from datetime import datetime, date as _date, time as _time, timedelta
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

@admin_reports_bp.route("/", methods=["GET"], endpoint="index")
@login_required
def admin_reports_index():
    """صفحة التقارير الإدارية الرئيسية"""
    return render_template("admin/reports/index.html")

def _mask_pan(pan: str) -> str:
    if not pan:
        return ""
    digits = "".join(ch for ch in pan if ch.isdigit())
    if len(digits) <= 4:
        return "*" * max(0, len(digits) - 1) + digits[-1:]
    return "**** **** **** " + digits[-4:]

def _parse_yyyy_mm_dd(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

@admin_reports_bp.route("/cards", methods=["GET"], endpoint="cards")
@login_required
@super_only
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
    sd = _parse_yyyy_mm_dd(start) if start else None
    ed = _parse_yyyy_mm_dd(end) if end else None
    if sd:
        q = q.filter(OnlinePayment.created_at >= datetime.combine(sd, _time.min))
    if ed:
        q = q.filter(OnlinePayment.created_at < datetime.combine(ed + timedelta(days=1), _time.min))
    if status and status in ("PENDING", "SUCCESS", "FAILED", "REFUNDED"):
        q = q.filter(OnlinePayment.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(OnlinePayment.payment_ref.ilike(like), Customer.name.ilike(like), Customer.phone.ilike(like)))
    rows = q.order_by(OnlinePayment.created_at.desc()).limit(500).all()
    return render_template("admin/reports/cards.html", rows=rows)

@admin_reports_bp.route("/cards/<int:pid>/reveal", methods=["POST"], endpoint="cards_reveal")
@login_required
@super_only
@limiter.limit("5/minute;20/hour;50/day")
def cards_reveal(pid: int):
    op = db.session.get(OnlinePayment, pid)
    if not op:
        abort(404)
    pan_decrypted = op.decrypt_card_number() or ""
    pan_masked = _mask_pan(pan_decrypted)
    reveal_enabled = bool(current_app.config.get("REVEAL_PAN_ENABLED", False))
    if not reveal_enabled:
        log_audit("OnlinePayment", op.id, "reveal_card_attempt", None, {"payment_ref": op.payment_ref, "result": "blocked_by_config"})
        resp = jsonify({
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
        })
        resp.headers["Cache-Control"] = "no-store"
        return resp, 403
    data = request.get_json(silent=True) or request.form or {}
    password = (data.get("password") or "").strip()
    if not password:
        log_audit("OnlinePayment", op.id, "reveal_card_attempt", None, {"payment_ref": op.payment_ref, "result": "missing_password"})
        resp = jsonify({"ok": False, "error": "password_required", "pan_masked": pan_masked})
        resp.headers["Cache-Control"] = "no-store"
        return resp, 400
    try:
        check_ok = current_user.check_password(password)
    except Exception:
        check_ok = False
    if not check_ok:
        log_audit("OnlinePayment", op.id, "reveal_card_attempt", None, {"payment_ref": op.payment_ref, "result": "bad_password"})
        resp = jsonify({"ok": False, "error": "invalid_password", "pan_masked": pan_masked})
        resp.headers["Cache-Control"] = "no-store"
        return resp, 403
    digits = "".join(ch for ch in pan_decrypted if ch.isdigit())
    if op.card_last4 and digits[-4:] != (op.card_last4 or ""):
        log_audit("OnlinePayment", op.id, "reveal_card_mismatch", None, {"payment_ref": op.payment_ref, "result": "last4_mismatch"})
        resp = jsonify({"ok": False, "error": "card_data_mismatch", "pan_masked": pan_masked})
        resp.headers["Cache-Control"] = "no-store"
        return resp, 409
    log_audit("OnlinePayment", op.id, "reveal_card", None, {"payment_ref": op.payment_ref, "result": "success"})
    resp = jsonify({
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
    resp.headers["Cache-Control"] = "no-store"
    return resp
